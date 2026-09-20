#!/usr/bin/env python3
"""Restart managed k3s and record identity and data-service preservation evidence."""

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

import yaml


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(*arguments, check=True):
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {arguments[0]} {arguments[1] if len(arguments) > 1 else ''}".strip())
    return result


def service_start_identity():
    return run("systemctl", "show", "k3s", "--property=ExecMainStartTimestampMonotonic", "--value").stdout.strip()


def node_state(kubeconfig, node_name):
    result = run("k3s", "kubectl", "--kubeconfig", str(kubeconfig), "get", "node", node_name, "-o", "json")
    node = json.loads(result.stdout)
    ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in node["status"]["conditions"])
    return {
        "uid": node["metadata"]["uid"],
        "ready": ready,
        "version": node["status"]["nodeInfo"]["kubeletVersion"],
    }


def data_service_state(environment):
    state = {}
    for service in ("mariadb", "redis"):
        name = f"mokla-{environment}-{service}-1"
        result = run("docker", "inspect", "--format", "{{json .State}}", name)
        details = json.loads(result.stdout)
        state[service] = {
            "id": run("docker", "inspect", "--format", "{{.Id}}", name).stdout.strip(),
            "running": details.get("Running") is True,
            "healthy": details.get("Health", {}).get("Status") == "healthy",
        }
    return state


def validate_transition(before, after, expected_version):
    return {
        "service_restarted": bool(before["service_start"] and before["service_start"] != after["service_start"]),
        "node_identity_preserved": before["node"]["uid"] == after["node"]["uid"],
        "node_ready": after["node"]["ready"] is True,
        "version_preserved": after["node"]["version"] == expected_version,
        "data_service_identity_preserved": all(
            before["data_services"][name]["id"] == after["data_services"][name]["id"]
            for name in ("mariadb", "redis")
        ),
        "data_services_healthy": all(
            after["data_services"][name]["running"] and after["data_services"][name]["healthy"]
            for name in ("mariadb", "redis")
        ),
    }


def main():
    args = parse_args()
    platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("overall_status") != "pass" or report.get("facts", {}).get("phase_state") != "installed":
        raise ValueError("a passing installed Phase 4 report is required before restart validation")
    kubeconfig = args.repository / platform["k3s"]["kubeconfig_output"]
    before = {
        "service_start": service_start_identity(),
        "node": node_state(kubeconfig, platform["k3s"]["node_name"]),
        "data_services": data_service_state(platform["environment_name"]),
    }
    outcome = {"status": "fail"}
    try:
        run("sudo", "-n", "systemctl", "restart", "k3s")
        deadline = time.monotonic() + 180
        after = None
        while time.monotonic() < deadline:
            try:
                candidate = {
                    "service_start": service_start_identity(),
                    "node": node_state(kubeconfig, platform["k3s"]["node_name"]),
                    "data_services": data_service_state(platform["environment_name"]),
                }
                if candidate["node"]["ready"]:
                    after = candidate
                    break
            except (OSError, RuntimeError, json.JSONDecodeError):
                pass
            time.sleep(5)
        if after is None:
            raise RuntimeError("k3s node did not return Ready after controlled restart")
        checks = validate_transition(before, after, platform["k3s"]["version"])
        outcome = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "pass" if all(checks.values()) else "fail",
            "service_start_before": before["service_start"],
            "service_start_after": after["service_start"],
            "checks": checks,
        }
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        outcome = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "fail",
            "error": type(exc).__name__,
        }
    report.setdefault("lifecycle", {})["controlled_restart"] = outcome
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 4 controlled restart: {outcome['status']}")
    return 0 if outcome["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())