#!/usr/bin/env python3
"""Reconcile and verify enabled Phase 6 cluster add-on capabilities."""

import argparse
import base64
import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

import yaml

import cluster_core_access as access


BOOTSTRAP_KINDS = {"Namespace", "ClusterRoleBinding", "ResourceQuota", "LimitRange", "NetworkPolicy"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--releases", type=pathlib.Path, required=True)
    parser.add_argument("--release", action="append", nargs=2, metavar=("NAME", "VALUES"), required=True)
    parser.add_argument("--resources", action="append", type=pathlib.Path, required=True)
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


def wait_for_metrics(kubeconfig):
    namespace = "observability"
    for deployment in ("monitoring-grafana", "monitoring-kube-state-metrics", "monitoring-kube-prometheus-operator"):
        kubectl(kubeconfig, "-n", namespace, "rollout", "status", f"deployment/{deployment}", "--timeout=600s")
    for statefulset in ("alertmanager-monitoring-kube-prometheus-alertmanager", "prometheus-monitoring-kube-prometheus-prometheus"):
        kubectl(kubeconfig, "-n", namespace, "rollout", "status", f"statefulset/{statefulset}", "--timeout=600s")
    kubectl(kubeconfig, "-n", "observability-agents", "rollout", "status", "daemonset/node-exporter", "--timeout=600s")


def service_proxy(kubeconfig, service, port, path, *, payload=None, expect_json=True):
    raw = f"/api/v1/namespaces/observability/services/http:{service}:{port}/proxy{path}"
    if payload is None:
        result = kubectl(kubeconfig, "get", f"--raw={raw}")
        response = result.stdout
    else:
        service_document = json.loads(kubectl(
            kubeconfig, "-n", "observability", "get", "service", service, "-o", "json",
        ).stdout)
        request = urllib.request.Request(
            f"http://{service_document['spec']['clusterIP']}:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as direct_response:
            response = direct_response.read().decode("utf-8")
    if not expect_json:
        return response.strip()
    return json.loads(response) if response.strip() else {}


def receiver_request(endpoint, path, *, method="GET"):
    base = endpoint.rsplit("/", 1)[0]
    request = urllib.request.Request(f"{base}{path}", method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
    return json.loads(body) if body else {}


def metrics_smoke(kubeconfig, platform, mode):
    prometheus_service = "monitoring-kube-prometheus-prometheus"
    query = urllib.parse.quote("node_uname_info", safe="")
    for _ in range(45):
        prometheus = service_proxy(kubeconfig, prometheus_service, 9090, f"/api/v1/query?query={query}")
        results = prometheus.get("data", {}).get("result", [])
        if prometheus.get("status") == "success" and results:
            break
        time.sleep(2)
    else:
        raise RuntimeError("Prometheus did not return node-exporter metrics")
    grafana = service_proxy(kubeconfig, "monitoring-grafana", 80, "/api/health")
    if grafana.get("database") != "ok":
        raise RuntimeError("Grafana health check did not report a healthy database")
    service_proxy(kubeconfig, "monitoring-kube-prometheus-alertmanager", 9093, "/-/ready", expect_json=False)
    smoke = {
        "prometheus_ready": True,
        "node_metrics_ready": True,
        "grafana_ready": True,
        "alertmanager_ready": True,
        "alert_delivery": "not_run_in_check_mode",
    }
    if mode != "apply":
        return smoke

    endpoint = platform["cluster_addons"]["metrics"]["alert_receiver_endpoint"]
    if endpoint != platform["external_platform_services"]["alert_receiver"]["endpoint"]:
        raise RuntimeError("Phase 6 alert receiver differs from the Phase 3 service contract")
    probe_id = uuid.uuid4().hex
    receiver_request(endpoint, "/events", method="DELETE")
    now = dt.datetime.now(dt.timezone.utc)
    service_proxy(kubeconfig, "monitoring-kube-prometheus-alertmanager", 9093, "/api/v2/alerts", payload=[{
        "labels": {"alertname": "MoklaPhase6Probe", "probe_id": probe_id, "severity": "test"},
        "annotations": {"summary": "Phase 6 alert delivery probe"},
        "startsAt": now.isoformat(),
        "endsAt": (now + dt.timedelta(minutes=2)).isoformat(),
    }])
    try:
        for _ in range(30):
            events = receiver_request(endpoint, "/events").get("events", [])
            if any(event.get("probe_id") == probe_id and event.get("alertname") == "MoklaPhase6Probe" for event in events):
                smoke["alert_delivery"] = "passed"
                smoke["probe_id"] = probe_id
                break
            time.sleep(2)
        else:
            raise RuntimeError("Alertmanager webhook probe was not delivered to the Phase 3 receiver")
    finally:
        receiver_request(endpoint, "/events", method="DELETE")
    return smoke


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
        configured_releases = [(name, pathlib.Path(values_path)) for name, values_path in args.release]
        documents = [
            document
            for resource_path in args.resources
            for document in yaml.safe_load_all(resource_path.read_text(encoding="utf-8"))
            if document
        ]
        phase5 = json.loads(args.phase_5_report.read_text(encoding="utf-8"))
        if phase5.get("overall_status") != "pass":
            raise RuntimeError("current passing Phase 5 evidence is required")

        release_inventory = releases["releases"]
        identity = platform["cluster_addons"]["identity"]
        admin_kubeconfig = repository / platform["k3s"]["kubeconfig_output"]
        server, ca_data = access.load_admin_cluster(admin_kubeconfig)
        addon_kubeconfig = identity_path(repository, identity)
        ready = identity_valid(repository, identity, server)
        bootstrap_documents = [document for document in documents if document.get("kind") in BOOTSTRAP_KINDS]
        routine_documents = [document for document in documents if document.get("kind") not in BOOTSTRAP_KINDS]
        existing_namespaces = {
            release_inventory[name]["namespace"]
            for name, _ in configured_releases
            if kubectl(admin_kubeconfig, "get", "namespace", release_inventory[name]["namespace"], check=False).returncode == 0
        }
        validation_documents = [
            document for document in bootstrap_documents
            if not document.get("metadata", {}).get("namespace")
            or document["metadata"]["namespace"] in existing_namespaces
        ]

        kubectl(admin_kubeconfig, "apply", "--server-side", "--dry-run=server", "--field-manager=mokla-cluster-addons-bootstrap", "-f", "-", stdin=dump_documents(validation_documents))
        bootstrap_drift = project_drift(
            admin_kubeconfig, validation_documents, "mokla-cluster-addons-bootstrap",
        )
        if args.mode == "apply":
            if bootstrap_drift:
                foundation_documents = [document for document in bootstrap_documents if not document.get("metadata", {}).get("namespace")]
                namespaced_documents = [document for document in bootstrap_documents if document.get("metadata", {}).get("namespace")]
                apply_documents(admin_kubeconfig, foundation_documents, "mokla-cluster-addons-bootstrap")
                for document in foundation_documents:
                    if document.get("kind") == "Namespace":
                        kubectl(
                            admin_kubeconfig, "wait", "--for=jsonpath={.status.phase}=Active",
                            f"namespace/{document['metadata']['name']}", "--timeout=60s",
                        )
                apply_documents(admin_kubeconfig, namespaced_documents, "mokla-cluster-addons-bootstrap")
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
            release_results = []
            with tempfile.TemporaryDirectory(prefix="mokla-phase6-chart-") as directory:
                values_drift = False
                helm_binary = repository / "execution/k3s/.controller-venv/bin/helm"
                for release_name, values_path in configured_releases:
                    release = release_inventory[release_name]
                    values = yaml.safe_load(values_path.read_text(encoding="utf-8"))
                    chart = pathlib.Path(directory) / f"{release_name}.tgz"
                    run([args.acquire, release_name, chart])
                    matches = release_values_match(helm_binary, addon_kubeconfig, release, values)
                    values_drift = values_drift or not matches
                    if args.mode == "apply" and not matches:
                        helm(
                            helm_binary, addon_kubeconfig,
                            "upgrade", "--install", release["name"], chart,
                            "--namespace", release["namespace"], "--create-namespace", "--values", values_path,
                            "--wait", "--timeout", "5m", "--history-max", "5",
                        )
                    release_results.append({
                        "capability": release_name,
                        "name": release["name"],
                        "namespace": release["namespace"],
                        "version": release["chart"]["version"],
                        "drift_before": not matches,
                    })
                resources_drift = project_drift(addon_kubeconfig, routine_documents) if routine_documents else False
                drift_before = bootstrap_drift or values_drift or resources_drift
                if args.mode == "apply" and resources_drift:
                        apply_documents(addon_kubeconfig, routine_documents, "mokla-cluster-addons")
            wait_for_certificates(addon_kubeconfig, release_inventory["certificates"]["namespace"])
            if platform["cluster_addons"]["capabilities"]["metrics"]:
                wait_for_metrics(addon_kubeconfig)
            smoke = certificate_smoke(addon_kubeconfig, platform)
            monitoring_smoke = metrics_smoke(addon_kubeconfig, platform, args.mode) if platform["cluster_addons"]["capabilities"]["metrics"] else {}
            runtime.update({
                "credential_mode": "fixed-test-identity",
                "restricted_credentials_ready": True,
                "drift_before": drift_before,
                "releases": release_results,
                "certificate_smoke": smoke,
                "metrics_smoke": monitoring_smoke,
                "deferred": {"metrics": False, "logs": True, "backups": True, "off_host_recovery": True},
                "checks": [
                    {"id": "cluster_addons.access", "status": "pass", "evidence": "fixed test identity authenticated"},
                    {"id": "cluster_addons.certificates", "status": "pass", "evidence": "private issuer, chain, SAN, and HTTPS passed"},
                    {"id": "cluster_addons.metrics", "status": "pass", "evidence": "Prometheus, node metrics, Grafana, and Alertmanager passed"},
                    {"id": "cluster_addons.alert_delivery", "status": "pass" if monitoring_smoke.get("alert_delivery") == "passed" else "not_run", "evidence": monitoring_smoke.get("alert_delivery")},
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