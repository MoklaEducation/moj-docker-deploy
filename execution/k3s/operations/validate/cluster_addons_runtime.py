#!/usr/bin/env python3
"""Reconcile and verify the Phase 6 certificate capability."""

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import tempfile
import time

import yaml

import cluster_core_access as access


BOOTSTRAP_KINDS = {"Namespace", "ClusterRoleBinding", "ResourceQuota", "LimitRange", "NetworkPolicy"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--releases", type=pathlib.Path, required=True)
    parser.add_argument("--values", type=pathlib.Path, required=True)
    parser.add_argument("--resources", type=pathlib.Path, required=True)
    parser.add_argument("--acquire", type=pathlib.Path, required=True)
    parser.add_argument("--phase-5-report", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(command, *, stdin=None, timeout=300, check=True):
    result = subprocess.run(
        [str(item) for item in command], input=stdin, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(f"{' '.join(str(item) for item in command[:3])} failed: {detail[0] if detail else result.returncode}")
    return result


def kubectl(kubeconfig, *arguments, stdin=None, timeout=300, check=True):
    return run(["k3s", "kubectl", "--kubeconfig", kubeconfig, *arguments], stdin=stdin, timeout=timeout, check=check)


def helm(helm_binary, kubeconfig, *arguments, timeout=600, check=True):
    return run([helm_binary, "--kubeconfig", kubeconfig, *arguments], timeout=timeout, check=check)


def dump_documents(documents):
    return yaml.safe_dump_all(documents, sort_keys=False)


def apply_documents(kubeconfig, documents, field_manager):
    kubectl(
        kubeconfig, "apply", "--server-side", f"--field-manager={field_manager}", "-f", "-",
        stdin=dump_documents(documents),
    )


def identity_path(repository, identity):
    return repository / pathlib.PurePosixPath(identity["kubeconfig_output"])


def identity_valid(repository, identity, server):
    try:
        access.validate_kubeconfig(identity_path(repository, identity), identity["name"], server)
        return True
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return False


def release_values_match(helm_binary, kubeconfig, release, values):
    result = helm(
        helm_binary, kubeconfig, "get", "values", release["name"],
        "--namespace", release["namespace"], "--output", "yaml", check=False,
    )
    if result.returncode != 0:
        return False
    return (yaml.safe_load(result.stdout) or {}) == values


def project_drift(kubeconfig, documents, field_manager="mokla-cluster-addons"):
    result = kubectl(
        kubeconfig, "diff", "--server-side", f"--field-manager={field_manager}",
        "-f", "-", stdin=dump_documents(documents), check=False,
    )
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(f"kubectl diff failed: {detail[0] if detail else result.returncode}")
    if result.stdout:
        print(result.stdout, end="")
    return result.returncode == 1


def wait_for_certificates(kubeconfig, namespace):
    for deployment in ("cert-manager", "cert-manager-cainjector", "cert-manager-webhook", "certificate-smoke"):
        kubectl(kubeconfig, "-n", namespace, "rollout", "status", f"deployment/{deployment}", "--timeout=300s")
    for certificate in ("mokla-test-ca", "phase6-test-tls"):
        kubectl(kubeconfig, "-n", namespace, "wait", "--for=condition=Ready", f"certificate/{certificate}", "--timeout=300s")


def certificate_smoke(kubeconfig, platform):
    addons = platform["cluster_addons"]
    namespace = addons["namespaces"]["certificates"]
    hostname = addons["certificates"]["hostname"]
    secret = json.loads(kubectl(kubeconfig, "-n", namespace, "get", "secret", "phase6-test-tls", "-o", "json").stdout)
    ca_certificate = base64.b64decode(secret["data"]["ca.crt"], validate=True)
    leaf_certificate = base64.b64decode(secret["data"]["tls.crt"], validate=True)
    with tempfile.TemporaryDirectory(prefix="mokla-phase6-certificate-") as directory:
        ca_path = pathlib.Path(directory) / "ca.crt"
        leaf_path = pathlib.Path(directory) / "tls.crt"
        ca_path.write_bytes(ca_certificate)
        leaf_path.write_bytes(leaf_certificate)
        run(["openssl", "verify", "-CAfile", ca_path, leaf_path])
        run(["openssl", "x509", "-in", leaf_path, "-noout", "-checkend", "86400"])
        san = run(["openssl", "x509", "-in", leaf_path, "-noout", "-ext", "subjectAltName"]).stdout
        if f"DNS:{hostname}" not in san:
            raise RuntimeError("issued certificate SAN does not match the configured hostname")
        response = None
        for _ in range(30):
            response = run([
                "curl", "--fail", "--silent", "--show-error", "--cacert", ca_path,
                "--resolve", f"{hostname}:443:{platform['k3s']['node_ip']}", f"https://{hostname}/",
            ], timeout=15, check=False)
            if response.returncode == 0 and response.stdout.strip() == "phase6-certificate-ok":
                break
            time.sleep(2)
        else:
            detail = (response.stderr or response.stdout).strip().splitlines()[-1:] if response else []
            raise RuntimeError(f"private HTTPS certificate smoke failed: {detail[0] if detail else 'unexpected response'}")
    return {"issuer_ready": True, "certificate_ready": True, "chain_valid": True, "san_valid": True, "https_valid": True}


def main():
    args = parse_args()
    runtime = {"mode": args.mode, "checks": [], "overall_status": "fail"}
    try:
        repository = args.repository.resolve()
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        releases = yaml.safe_load(args.releases.read_text(encoding="utf-8"))
        values = yaml.safe_load(args.values.read_text(encoding="utf-8"))
        documents = [document for document in yaml.safe_load_all(args.resources.read_text(encoding="utf-8")) if document]
        phase5 = json.loads(args.phase_5_report.read_text(encoding="utf-8"))
        if phase5.get("overall_status") != "pass":
            raise RuntimeError("current passing Phase 5 evidence is required")

        release = releases["releases"]["certificates"]
        identity = platform["cluster_addons"]["identity"]
        admin_kubeconfig = repository / platform["k3s"]["kubeconfig_output"]
        server, ca_data = access.load_admin_cluster(admin_kubeconfig)
        addon_kubeconfig = identity_path(repository, identity)
        ready = identity_valid(repository, identity, server)
        bootstrap_documents = [document for document in documents if document.get("kind") in BOOTSTRAP_KINDS]
        routine_documents = [document for document in documents if document.get("kind") not in BOOTSTRAP_KINDS]
        namespace_exists = kubectl(
            admin_kubeconfig, "get", "namespace", release["namespace"], check=False,
        ).returncode == 0
        validation_documents = [
            document for document in bootstrap_documents
            if namespace_exists or not document.get("metadata", {}).get("namespace")
        ]

        kubectl(admin_kubeconfig, "apply", "--server-side", "--dry-run=server", "--field-manager=mokla-cluster-addons-bootstrap", "-f", "-", stdin=dump_documents(validation_documents))
        bootstrap_drift = project_drift(
            admin_kubeconfig, validation_documents, "mokla-cluster-addons-bootstrap",
        )
        if args.mode == "apply":
            if bootstrap_drift:
                apply_documents(admin_kubeconfig, bootstrap_documents, "mokla-cluster-addons-bootstrap")
            if not ready:
                access.issue_identity(admin_kubeconfig, repository, identity, server, ca_data, "phase6")
                ready = True
        if not ready:
            runtime.update({
                "credential_mode": "bootstrap-required",
                "restricted_credentials_ready": False,
                "drift_before": True,
                "checks": [{"id": "cluster_addons.access", "status": "pending", "evidence": "add-on identity requires explicit apply"}],
                "overall_status": "bootstrap_required",
            })
        else:
            access.validate_kubeconfig(addon_kubeconfig, identity["name"], server)
            with tempfile.TemporaryDirectory(prefix="mokla-phase6-chart-") as directory:
                chart = pathlib.Path(directory) / "cert-manager.tgz"
                run([args.acquire, "certificates", chart])
                values_match = release_values_match(repository / "execution/k3s/.controller-venv/bin/helm", addon_kubeconfig, release, values)
                values_drift = not values_match
                resources_drift = project_drift(addon_kubeconfig, routine_documents) if values_match else True
                drift_before = bootstrap_drift or values_drift or resources_drift
                if args.mode == "apply":
                    if values_drift:
                        helm(
                            repository / "execution/k3s/.controller-venv/bin/helm", addon_kubeconfig,
                            "upgrade", "--install", release["name"], chart,
                            "--namespace", release["namespace"], "--values", args.values,
                            "--wait", "--timeout", "5m", "--history-max", "5",
                        )
                    if resources_drift:
                        apply_documents(addon_kubeconfig, routine_documents, "mokla-cluster-addons")
            wait_for_certificates(addon_kubeconfig, release["namespace"])
            smoke = certificate_smoke(addon_kubeconfig, platform)
            runtime.update({
                "credential_mode": "fixed-test-identity",
                "restricted_credentials_ready": True,
                "drift_before": drift_before,
                "release": {"name": release["name"], "namespace": release["namespace"], "version": release["chart"]["version"]},
                "certificate_smoke": smoke,
                "deferred": {"metrics": True, "logs": True, "backups": True, "off_host_recovery": True},
                "checks": [
                    {"id": "cluster_addons.access", "status": "pass", "evidence": "fixed test identity authenticated"},
                    {"id": "cluster_addons.certificates", "status": "pass", "evidence": "private issuer, chain, SAN, and HTTPS passed"},
                ],
                "overall_status": "pass",
            })
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"Phase 6 runtime: fail ({exc})", file=sys.stderr)
        runtime["checks"].append({"id": "cluster_addons.runtime", "status": "fail", "evidence": type(exc).__name__})
        runtime["error"] = str(exc)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 6 runtime: {runtime['overall_status']}")
    return 0 if runtime["overall_status"] in ("pass", "bootstrap_required") else 1


if __name__ == "__main__":
    sys.exit(main())