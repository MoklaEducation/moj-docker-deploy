#!/usr/bin/env python3
"""Reconcile and exercise the Phase 5 cluster core."""

import argparse
import json
import pathlib
import subprocess
import sys
import time

import yaml

import cluster_core_access as access
import cluster_core_render as render


ROUTINE_KINDS = {"Namespace", "ResourceQuota", "LimitRange", "NetworkPolicy"}
ACCESS_KINDS = {"ClusterRole", "ClusterRoleBinding", "RoleBinding"}
PRUNE_KINDS = {"ResourceQuota", "LimitRange", "NetworkPolicy"}
SMOKE_PREFIX = "phase5-core-smoke"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "apply", "smoke"), required=True)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--overlay", type=pathlib.Path, required=True)
    parser.add_argument("--phase-4-report", type=pathlib.Path, required=True)
    parser.add_argument("--previous-report", type=pathlib.Path)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(kubeconfig, *arguments, stdin=None, timeout=180, check=True):
    result = subprocess.run(
        ["k3s", "kubectl", "--kubeconfig", str(kubeconfig), *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(f"kubectl {' '.join(arguments)} failed: {detail[0] if detail else result.returncode}")
    return result


def dump_documents(documents):
    return yaml.safe_dump_all(documents, sort_keys=False)


def kubeconfig_path(repository, identity):
    return repository / pathlib.Path(*pathlib.PurePosixPath(identity["kubeconfig_output"]).parts)


def credentials_valid(platform, repository):
    try:
        server = f"https://{platform['k3s']['api_bind_address']}:6443"
        for identity in platform["cluster_core"]["identities"].values():
            access.validate_kubeconfig(kubeconfig_path(repository, identity), identity["name"], server)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return False
    return True


def server_validate_and_diff(kubeconfig, documents):
    manifest = dump_documents(documents)
    run(kubeconfig, "apply", "--server-side", "--dry-run=server", "--field-manager=mokla-cluster-core", "-f", "-", stdin=manifest)
    difference = run(
        kubeconfig, "diff", "--server-side", "--field-manager=mokla-cluster-core", "-f", "-",
        stdin=manifest, check=False,
    )
    if difference.returncode not in (0, 1):
        detail = (difference.stderr or difference.stdout).strip().splitlines()[-1:]
        raise RuntimeError(f"kubectl diff failed: {detail[0] if detail else difference.returncode}")
    if difference.stdout:
        print(difference.stdout, end="")
    return difference.returncode == 1


def apply_documents(kubeconfig, documents):
    run(
        kubeconfig, "apply", "--server-side", "--field-manager=mokla-cluster-core", "-f", "-",
        stdin=dump_documents(documents),
    )


def namespaces_present(kubeconfig, documents):
    names = {document["metadata"]["name"] for document in documents if document.get("kind") == "Namespace"}
    return {
        name for name in names
        if run(kubeconfig, "get", "namespace", name, check=False).returncode == 0
    }


def documents_with_existing_namespaces(documents, existing_namespaces):
    return [
        document for document in documents
        if not document.get("metadata", {}).get("namespace")
        or document["metadata"]["namespace"] in existing_namespaces
    ]


def desired_subset(document):
    metadata = document.get("metadata", {})
    subset = {
        "apiVersion": document.get("apiVersion"),
        "kind": document.get("kind"),
        "metadata": {
            "name": metadata.get("name"),
            "labels": metadata.get("labels", {}),
        },
    }
    if metadata.get("namespace"):
        subset["metadata"]["namespace"] = metadata["namespace"]
    for key in ("rules", "roleRef", "subjects"):
        if key in document:
            subset[key] = document[key]
    return subset


def live_access_drift(kubeconfig, documents):
    drift = []
    for document in documents:
        kind, namespace, name = render.object_id(document)
        arguments = []
        if namespace:
            arguments.extend(("-n", namespace))
        result = run(kubeconfig, *arguments, "get", kind.lower(), name, "-o", "json", check=False)
        if result.returncode != 0:
            drift.append(f"{kind}/{namespace + '/' if namespace else ''}{name}:missing")
            continue
        live = json.loads(result.stdout)
        if desired_subset(live) != desired_subset(document):
            drift.append(f"{kind}/{namespace + '/' if namespace else ''}{name}:changed")
    return drift


def prune_stale(kubeconfig, previous_report, desired_ids):
    if not previous_report or not previous_report.exists():
        return []
    try:
        previous = json.loads(previous_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    pruned = []
    for item in previous.get("managed_objects", []):
        identifier = (item.get("kind"), item.get("namespace") or "", item.get("name"))
        if identifier in desired_ids or item.get("kind") not in PRUNE_KINDS or not item.get("namespace"):
            continue
        result = run(
            kubeconfig, "-n", item["namespace"], "get", item["kind"].lower(), item["name"],
            "-o", "json", check=False,
        )
        if result.returncode != 0:
            continue
        live = json.loads(result.stdout)
        if live.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/managed-by") != "mokla-cluster-core":
            raise RuntimeError(f"refusing to prune unowned {item['kind']}/{item['namespace']}/{item['name']}")
        run(kubeconfig, "-n", item["namespace"], "delete", item["kind"].lower(), item["name"], "--wait=true")
        pruned.append({"kind": item["kind"], "namespace": item["namespace"], "name": item["name"]})
    return pruned


def can_i(kubeconfig, verb, resource, namespace=None):
    arguments = ["auth", "can-i", verb, resource]
    if namespace:
        arguments.extend(("--namespace", namespace))
    result = run(kubeconfig, *arguments, check=False)
    answer = result.stdout.strip()
    if answer not in {"yes", "no"} or result.returncode not in {0, 1}:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(f"kubectl {' '.join(arguments)} failed: {detail[0] if detail else result.returncode}")
    return answer == "yes"


def authorization_checks(platform, repository):
    core = platform["cluster_core"]
    namespace = core["namespaces"]["application"]
    operator = kubeconfig_path(repository, core["identities"]["operator"])
    automation = kubeconfig_path(repository, core["identities"]["automation"])
    checks = {
        "operator_get_pods": can_i(operator, "get", "pods", namespace),
        "operator_delete_pods": can_i(operator, "delete", "pods", namespace),
        "operator_read_secrets_denied": not can_i(operator, "get", "secrets", namespace),
        "operator_modify_nodes_denied": not can_i(operator, "patch", "nodes"),
        "automation_manage_policies": can_i(automation, "patch", "networkpolicies.networking.k8s.io", namespace),
        "automation_smoke_pods": can_i(automation, "create", "pods", namespace),
        "automation_read_secrets_denied": not can_i(automation, "get", "secrets", namespace),
        "automation_modify_nodes_denied": not can_i(automation, "patch", "nodes"),
        "automation_create_crds_denied": not can_i(automation, "create", "customresourcedefinitions.apiextensions.k8s.io"),
        "automation_cross_namespace_denied": not can_i(automation, "create", "pods", core["namespaces"]["observability"]),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"authorization checks failed: {failed}")
    return checks


def secure_pod(name, image, command, labels=None, volumes=None, mounts=None):
    container = {
        "name": name,
        "image": image,
        "command": ["sh", "-c", command],
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "runAsNonRoot": True,
            "runAsUser": 65534,
            "runAsGroup": 65534,
        },
    }
    if mounts:
        container["volumeMounts"] = mounts
    spec = {
        "automountServiceAccountToken": False,
        "restartPolicy": "Never",
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [container],
    }
    if volumes:
        spec["volumes"] = volumes
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": name, "labels": labels or {}},
        "spec": spec,
    }


def wait_ready(kubeconfig, namespace, pod):
    run(kubeconfig, "-n", namespace, "wait", "--for=condition=Ready", f"pod/{pod}", "--timeout=180s", timeout=190)


def cleanup_smoke(kubeconfig, namespace):
    run(
        kubeconfig, "-n", namespace, "delete", "pod,service,persistentvolumeclaim",
        "-l", "platform.mokla/smoke=phase5", "--ignore-not-found=true", "--wait=true", check=False,
    )


def smoke(platform, repository):
    core = platform["cluster_core"]
    namespace = core["namespaces"]["application"]
    kubeconfig = kubeconfig_path(repository, core["identities"]["automation"])
    image = core["smoke_image"]
    labels = {"platform.mokla/smoke": "phase5"}
    client_labels = {**labels, "platform.mokla/data-services-client": "true"}
    server = secure_pod(f"{SMOKE_PREFIX}-server", image, "mkdir -p /tmp/www && echo phase5-ok >/tmp/www/index.html && httpd -f -p 8080 -h /tmp/www", labels)
    client = secure_pod(f"{SMOKE_PREFIX}-client", image, "sleep 600", client_labels)
    denied = secure_pod(f"{SMOKE_PREFIX}-denied", image, "sleep 600", labels)
    pvc = {
        "apiVersion": "v1", "kind": "PersistentVolumeClaim",
        "metadata": {"name": f"{SMOKE_PREFIX}-data", "labels": labels},
        "spec": {"storageClassName": core["storage"]["class_name"], "accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "16Mi"}}},
    }
    volume = [{"name": "data", "persistentVolumeClaim": {"claimName": f"{SMOKE_PREFIX}-data"}}]
    mounts = [{"name": "data", "mountPath": "/data"}]
    writer = secure_pod(f"{SMOKE_PREFIX}-writer", image, "echo phase5-persistent >/data/marker && sleep 600", labels, volume, mounts)
    service = {
        "apiVersion": "v1", "kind": "Service",
        "metadata": {"name": f"{SMOKE_PREFIX}-server", "labels": labels},
        "spec": {"selector": {"platform.mokla/smoke": "phase5", "smoke-role": "server"}, "ports": [{"port": 8080, "targetPort": 8080}]},
    }
    server["metadata"]["labels"]["smoke-role"] = "server"
    checks = {}
    volume_name = None
    cleanup_smoke(kubeconfig, namespace)
    try:
        for document in (server, service, client, denied, pvc, writer):
            run(kubeconfig, "-n", namespace, "create", "-f", "-", stdin=yaml.safe_dump(document, sort_keys=False))
        for pod in (server["metadata"]["name"], client["metadata"]["name"], denied["metadata"]["name"], writer["metadata"]["name"]):
            wait_ready(kubeconfig, namespace, pod)

        run(kubeconfig, "-n", namespace, "exec", client["metadata"]["name"], "--", "nslookup", "kubernetes.default.svc.cluster.local")
        checks["dns_allowed"] = True
        denied_egress = run(kubeconfig, "-n", namespace, "exec", denied["metadata"]["name"], "--", "wget", "-T", "5", "-qO", "/dev/null", "http://example.com", timeout=15, check=False)
        checks["external_egress_denied"] = denied_egress.returncode != 0

        server_ip = json.loads(run(kubeconfig, "-n", namespace, "get", "pod", server["metadata"]["name"], "-o", "json").stdout)["status"]["podIP"]
        denied_ingress = run(kubeconfig, "-n", namespace, "exec", client["metadata"]["name"], "--", "nc", "-z", "-w", "3", server_ip, "8080", timeout=10, check=False)
        checks["ingress_denied"] = denied_ingress.returncode != 0

        for service_name in ("mariadb", "redis"):
            port = str(platform["data_services"][service_name]["port"])
            run(kubeconfig, "-n", namespace, "exec", client["metadata"]["name"], "--", "nc", "-z", "-w", "5", platform["data_services"]["bind_address"], port, timeout=15)
        checks["data_services_allowed"] = True

        claim = json.loads(run(kubeconfig, "-n", namespace, "get", "persistentvolumeclaim", pvc["metadata"]["name"], "-o", "json").stdout)
        volume_name = claim.get("spec", {}).get("volumeName")
        run(kubeconfig, "-n", namespace, "delete", "pod", writer["metadata"]["name"], "--wait=true")
        reader = secure_pod(f"{SMOKE_PREFIX}-reader", image, "sleep 600", labels, volume, mounts)
        run(kubeconfig, "-n", namespace, "create", "-f", "-", stdin=yaml.safe_dump(reader, sort_keys=False))
        wait_ready(kubeconfig, namespace, reader["metadata"]["name"])
        marker = run(kubeconfig, "-n", namespace, "exec", reader["metadata"]["name"], "--", "cat", "/data/marker").stdout.strip()
        checks["storage_persisted"] = marker == "phase5-persistent"
        if not all(checks.values()):
            raise RuntimeError("one or more network or storage smoke assertions failed")
    finally:
        cleanup_smoke(kubeconfig, namespace)

    if volume_name:
        for _ in range(30):
            if run(kubeconfig, "get", "persistentvolume", volume_name, check=False).returncode != 0:
                checks["storage_reclaimed"] = True
                break
            time.sleep(1)
        else:
            checks["storage_reclaimed"] = False
            raise RuntimeError("local-path volume was not reclaimed after smoke cleanup")
    leftovers = json.loads(run(kubeconfig, "-n", namespace, "get", "pods,services,persistentvolumeclaims", "-l", "platform.mokla/smoke=phase5", "-o", "json").stdout)
    checks["cleanup_complete"] = not leftovers.get("items")
    if not checks["cleanup_complete"]:
        raise RuntimeError("smoke resources remain after cleanup")
    return checks


def main():
    args = parse_args()
    repository = args.repository.resolve()
    runtime = {"checks": [], "overall_status": "fail", "mode": args.mode}
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        phase4 = json.loads(args.phase_4_report.read_text(encoding="utf-8"))
        if phase4.get("overall_status") != "pass":
            raise RuntimeError("current passing Phase 4 evidence is required")
        rendered = render.render_overlay(args.overlay)
        documents = [document for document in yaml.safe_load_all(rendered) if document]
        validation_errors = render.validate_documents(documents, platform)
        if validation_errors:
            raise RuntimeError("offline rendered policy validation failed")
        facts = render.build_facts(rendered, documents)
        admin_kubeconfig = repository / platform["k3s"]["kubeconfig_output"]
        restricted_ready = credentials_valid(platform, repository)
        routine = [document for document in documents if document["kind"] in ROUTINE_KINDS]
        access_documents = [document for document in documents if document["kind"] in ACCESS_KINDS]

        if args.mode == "apply" and not restricted_ready:
            namespace_documents = [document for document in documents if document["kind"] == "Namespace"]
            server_validate_and_diff(admin_kubeconfig, namespace_documents)
            apply_documents(admin_kubeconfig, namespace_documents)
            drift_before = server_validate_and_diff(admin_kubeconfig, documents)
            apply_documents(admin_kubeconfig, documents)
            access_platform = platform["cluster_core"]["identities"]
            server, ca_data = access.load_admin_cluster(admin_kubeconfig)
            for identity in access_platform.values():
                access.issue_identity(admin_kubeconfig, repository, identity, server, ca_data)
            restricted_ready = True
            credential_mode = "bootstrap-issued"
        elif not restricted_ready:
            existing_namespaces = namespaces_present(admin_kubeconfig, documents)
            validation_documents = documents_with_existing_namespaces(documents, existing_namespaces)
            drift_before = server_validate_and_diff(admin_kubeconfig, validation_documents)
            credential_mode = "bootstrap-required"
        else:
            automation = kubeconfig_path(repository, platform["cluster_core"]["identities"]["automation"])
            drift_before = server_validate_and_diff(automation, routine)
            credential_mode = "restricted"

        if args.mode in ("apply", "smoke") and not restricted_ready:
            raise RuntimeError("restricted credentials must be issued before smoke tests")

        pruned = []
        if restricted_ready:
            automation = kubeconfig_path(repository, platform["cluster_core"]["identities"]["automation"])
            access_drift = live_access_drift(automation, access_documents)
            if access_drift:
                raise RuntimeError("bootstrap-owned RBAC drift detected: " + ", ".join(access_drift))
            if args.mode == "apply":
                apply_documents(automation, routine)
                desired_ids = {render.object_id(document) for document in documents}
                pruned = prune_stale(automation, args.previous_report, desired_ids)
            auth_checks = authorization_checks(platform, repository)
        else:
            access_drift = []
            auth_checks = {}

        smoke_checks = smoke(platform, repository) if args.mode in ("apply", "smoke") else {}
        storage_class = json.loads(run(
            admin_kubeconfig if not restricted_ready else kubeconfig_path(repository, platform["cluster_core"]["identities"]["automation"]),
            "get", "storageclass", platform["cluster_core"]["storage"]["class_name"], "-o", "json",
        ).stdout)
        annotations = storage_class.get("metadata", {}).get("annotations", {})
        storage = {
            "class": storage_class["metadata"]["name"],
            "default": annotations.get("storageclass.kubernetes.io/is-default-class") == "true",
            "reclaim_policy": storage_class.get("reclaimPolicy"),
            "volume_binding_mode": storage_class.get("volumeBindingMode"),
        }
        if storage["default"] != platform["cluster_core"]["storage"]["remain_default"]:
            raise RuntimeError("live local-path default status differs from the platform contract")
        runtime.update({
            **facts,
            "credential_mode": credential_mode,
            "restricted_credentials_ready": restricted_ready,
            "drift_before": drift_before,
            "access_drift": access_drift,
            "authorization": auth_checks,
            "smoke": smoke_checks,
            "storage": storage,
            "pruned": pruned,
            "checks": [
                {"id": "cluster_core.render", "status": "pass", "evidence": "Deterministic render and offline policy validation passed"},
                {"id": "cluster_core.server_validation", "status": "pass", "evidence": "Server-side dry-run and diff completed"},
                {"id": "cluster_core.access", "status": "pass" if restricted_ready else "pending", "evidence": credential_mode},
            ],
            "overall_status": "pass" if restricted_ready else "bootstrap_required",
        })
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"Phase 5 runtime: fail ({exc})", file=sys.stderr)
        runtime["checks"].append({"id": "cluster_core.runtime", "status": "fail", "evidence": type(exc).__name__})
        runtime["error"] = str(exc)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 5 runtime: {runtime['overall_status']}")
    return 0 if runtime["overall_status"] in ("pass", "bootstrap_required") else 1


if __name__ == "__main__":
    sys.exit(main())