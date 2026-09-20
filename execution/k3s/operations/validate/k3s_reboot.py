#!/usr/bin/env python3
"""Prepare and verify operator-approved Phase 4 reboot recovery evidence."""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

import yaml


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(*arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {arguments[0]} {arguments[1] if len(arguments) > 1 else ''}".strip())
    return result.stdout.strip()


def identity(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def snapshot(platform, repository):
    kubeconfig = repository / platform["k3s"]["kubeconfig_output"]
    node = json.loads(run("k3s", "kubectl", "--kubeconfig", str(kubeconfig), "get", "node", platform["k3s"]["node_name"], "-o", "json"))
    ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in node["status"]["conditions"])
    containers = {}
    for service in ("mariadb", "redis"):
        name = f"mokla-{platform['environment_name']}-{service}-1"
        state = json.loads(run("docker", "inspect", "--format", "{{json .State}}", name))
        containers[service] = {
            "identity_hash": identity(run("docker", "inspect", "--format", "{{.Id}}", name)),
            "healthy": state.get("Running") is True and state.get("Health", {}).get("Status") == "healthy",
        }
    return {
        "boot_id": run("cat", "/proc/sys/kernel/random/boot_id"),
        "node_identity_hash": identity(node["metadata"]["uid"]),
        "node_ready": ready,
        "version": node["status"]["nodeInfo"]["kubeletVersion"],
        "k3s_active": run("systemctl", "is-active", "k3s") == "active",
        "k3s_enabled": run("systemctl", "is-enabled", "k3s") == "enabled",
        "docker_active": run("systemctl", "is-active", "docker") == "active",
        "containers": containers,
    }


def recovery_checks(before, after, expected_version):
    return {
        "boot_changed": before["boot_id"] != after["boot_id"],
        "k3s_recovered": after["k3s_active"] and after["k3s_enabled"],
        "docker_recovered": after["docker_active"],
        "node_identity_preserved": before["node_identity_hash"] == after["node_identity_hash"],
        "node_ready": after["node_ready"],
        "version_preserved": after["version"] == expected_version,
        "data_service_identity_preserved": all(
            before["containers"][name]["identity_hash"] == after["containers"][name]["identity_hash"]
            for name in ("mariadb", "redis")
        ),
        "data_services_healthy": all(after["containers"][name]["healthy"] for name in ("mariadb", "redis")),
    }


def main():
    args = parse_args()
    platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    lifecycle = report.setdefault("lifecycle", {})
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if args.action == "prepare":
        if report.get("overall_status") != "pass" or lifecycle.get("controlled_restart", {}).get("status") != "pass":
            raise ValueError("passing Phase 4 and controlled-restart evidence are required")
        lifecycle["reboot"] = {"status": "awaiting_reboot", "prepared_at": now, "before": snapshot(platform, args.repository)}
        status = "awaiting_reboot"
    else:
        reboot = lifecycle.get("reboot", {})
        if reboot.get("status") != "awaiting_reboot" or not reboot.get("before"):
            raise ValueError("prepare reboot evidence before verification")
        after = snapshot(platform, args.repository)
        checks = recovery_checks(reboot["before"], after, platform["k3s"]["version"])
        reboot.update({"verified_at": now, "status": "pass" if all(checks.values()) else "fail", "checks": checks})
        reboot.pop("before", None)
        status = reboot["status"]
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 4 reboot validation: {status}")
    return 0 if status in ("awaiting_reboot", "pass") else 1


if __name__ == "__main__":
    sys.exit(main())