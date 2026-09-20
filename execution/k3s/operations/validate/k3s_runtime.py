#!/usr/bin/env python3
"""Run disposable Phase 4 Kubernetes API and networking smoke checks."""

import argparse
import json
import pathlib
import subprocess
import sys
import time

import yaml


NAMESPACE = "platform-install-smoke"
IMAGE = "docker.io/library/busybox:1.36.1"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path, required=True)
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
        message = (result.stderr or result.stdout).strip().splitlines()[-1:]
        detail = message[0] if message else f"exit {result.returncode}"
        raise RuntimeError(f"kubectl {' '.join(arguments)} failed: {detail}")
    return result


def apply(kubeconfig, manifest):
    run(kubeconfig, "apply", "-f", "-", stdin=yaml.safe_dump(manifest, sort_keys=False))


def wait_ready(kubeconfig, resource, timeout=180):
    run(kubeconfig, "-n", NAMESPACE, "wait", "--for=condition=Ready", resource, f"--timeout={timeout}s", timeout=timeout + 10)


def component_is_ready(system_pods, name):
    matches = [
        pod for pod in system_pods
        if name in pod["metadata"]["name"] and pod.get("status", {}).get("phase") == "Running"
    ]
    return bool(matches) and all(
        any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in pod.get("status", {}).get("conditions", []))
        for pod in matches
    )


def smoke(kubeconfig, platform):
    checks = []
    deadline = time.monotonic() + 180
    node = None
    while time.monotonic() < deadline:
        result = run(kubeconfig, "get", "node", platform["k3s"]["node_name"], "-o", "json", check=False)
        if result.returncode == 0:
            candidate = json.loads(result.stdout)
            ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in candidate["status"]["conditions"])
            if ready and candidate["status"]["nodeInfo"]["kubeletVersion"] == platform["k3s"]["version"]:
                node = candidate
                break
        time.sleep(5)
    if node is None:
        raise RuntimeError("node identity, readiness, or version did not converge")
    kubelet_version = node["status"]["nodeInfo"]["kubeletVersion"]
    checks.append({"id": "k3s.runtime.node", "status": "pass", "evidence": "Configured node is Ready at the exact release", "remediation": ""})

    required = ("coredns", "local-path-provisioner", "metrics-server", "traefik")
    components = {name: False for name in required}
    while time.monotonic() < deadline:
        system_pods = json.loads(run(kubeconfig, "-n", "kube-system", "get", "pods", "-o", "json").stdout)["items"]
        for name in required:
            components[name] = component_is_ready(system_pods, name)
        if all(components.values()):
            break
        time.sleep(5)
    if not all(components.values()):
        raise RuntimeError("one or more bundled k3s components did not become Ready")
    checks.append({"id": "k3s.runtime.components", "status": "pass", "evidence": "Bundled DNS, ingress, metrics, and local storage components are Ready", "remediation": ""})

    run(kubeconfig, "delete", "namespace", NAMESPACE, "--ignore-not-found=true", "--wait=true", check=False)
    run(kubeconfig, "create", "namespace", NAMESPACE)
    server = {
        "apiVersion": "v1", "kind": "Pod", "metadata": {"name": "http-server", "namespace": NAMESPACE, "labels": {"app": "http-server"}},
        "spec": {"containers": [{"name": "server", "image": IMAGE, "command": ["sh", "-c", "mkdir -p /www && echo phase4-ok >/www/index.html && httpd -f -p 8080 -h /www"]}]},
    }
    service = {
        "apiVersion": "v1", "kind": "Service", "metadata": {"name": "http-server", "namespace": NAMESPACE},
        "spec": {"selector": {"app": "http-server"}, "ports": [{"port": 8080, "targetPort": 8080}]},
    }
    client = {
        "apiVersion": "v1", "kind": "Pod", "metadata": {"name": "client", "namespace": NAMESPACE},
        "spec": {"containers": [{"name": "client", "image": IMAGE, "command": ["sh", "-c", "sleep 600"]}]},
    }
    pvc = {
        "apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "smoke-data", "namespace": NAMESPACE},
        "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "16Mi"}}},
    }
    writer = {
        "apiVersion": "v1", "kind": "Pod", "metadata": {"name": "storage-writer", "namespace": NAMESPACE},
        "spec": {"containers": [{"name": "writer", "image": IMAGE, "command": ["sh", "-c", "echo phase4-persistent >/data/marker && sleep 600"], "volumeMounts": [{"name": "data", "mountPath": "/data"}]}], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "smoke-data"}}]},
    }
    for manifest in (server, service, client, pvc, writer):
        apply(kubeconfig, manifest)
    wait_ready(kubeconfig, "pod/http-server")
    wait_ready(kubeconfig, "pod/client")
    wait_ready(kubeconfig, "pod/storage-writer")

    run(kubeconfig, "-n", NAMESPACE, "exec", "client", "--", "nslookup", f"http-server.{NAMESPACE}.svc.cluster.local")
    response = run(kubeconfig, "-n", NAMESPACE, "exec", "client", "--", "wget", "-qO-", "http://http-server:8080").stdout.strip()
    if response != "phase4-ok":
        raise RuntimeError("ClusterIP response did not match")
    run(kubeconfig, "-n", NAMESPACE, "exec", "client", "--", "wget", "-qO", "/dev/null", "http://example.com")
    for service_name in ("mariadb", "redis"):
        port = str(platform["data_services"][service_name]["port"])
        run(kubeconfig, "-n", NAMESPACE, "exec", "client", "--", "nc", "-z", "-w", "5", platform["data_services"]["bind_address"], port)
    checks.extend([
        {"id": "k3s.runtime.dns", "status": "pass", "evidence": "A disposable pod resolved a ClusterIP service", "remediation": ""},
        {"id": "k3s.runtime.cluster_ip", "status": "pass", "evidence": "A disposable pod reached a ClusterIP endpoint", "remediation": ""},
        {"id": "k3s.runtime.egress", "status": "pass", "evidence": "A disposable pod reached an external HTTP endpoint", "remediation": ""},
        {"id": "k3s.runtime.data_services", "status": "pass", "evidence": "A disposable pod reached the permitted MariaDB and Redis TCP endpoints", "remediation": ""},
    ])

    run(kubeconfig, "-n", NAMESPACE, "delete", "pod", "storage-writer", "--wait=true")
    reader = {
        "apiVersion": "v1", "kind": "Pod", "metadata": {"name": "storage-reader", "namespace": NAMESPACE},
        "spec": {"containers": [{"name": "reader", "image": IMAGE, "command": ["sh", "-c", "sleep 600"], "volumeMounts": [{"name": "data", "mountPath": "/data"}]}], "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "smoke-data"}}]},
    }
    apply(kubeconfig, reader)
    wait_ready(kubeconfig, "pod/storage-reader")
    marker = run(kubeconfig, "-n", NAMESPACE, "exec", "storage-reader", "--", "cat", "/data/marker").stdout.strip()
    if marker != "phase4-persistent":
        raise RuntimeError("local-path data did not survive pod recreation")
    checks.append({"id": "k3s.runtime.local_storage", "status": "pass", "evidence": "PVC data survived pod recreation", "remediation": ""})
    return checks, node["metadata"]["name"], kubelet_version, components


def main():
    args = parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
    facts = json.loads(args.facts.read_text(encoding="utf-8"))
    report = {"smoke_namespace": NAMESPACE, "checks": []}
    if facts.get("phase_state") == "preinstall_ready":
        report["checks"].append({"id": "k3s.runtime.available", "status": "pending", "evidence": "Runtime checks await explicit installation", "remediation": "Run explicit apply through k3s-installation"})
        report["overall_status"] = "preinstall_ready"
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Phase 4 runtime: preinstall_ready")
        return 0

    kubeconfig = args.repository / platform["k3s"]["kubeconfig_output"]
    try:
        checks, node, version, components = smoke(kubeconfig, platform)
        report.update({"checks": checks, "node": node, "kubelet_version": version, "components": components, "overall_status": "pass"})
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"Phase 4 runtime validation failed: {exc}", file=sys.stderr)
        report["checks"].append({"id": "k3s.runtime.completed", "status": "fail", "evidence": type(exc).__name__, "remediation": "Inspect k3s service and pod events; do not disable UFW to bypass networking failures."})
        report["overall_status"] = "fail"
    finally:
        try:
            run(kubeconfig, "delete", "namespace", NAMESPACE, "--ignore-not-found=true", "--wait=true", timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 4 runtime: {report['overall_status']}")
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())