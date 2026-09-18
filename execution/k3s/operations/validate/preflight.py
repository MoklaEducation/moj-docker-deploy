#!/usr/bin/env python3
"""Validate controller inputs and write the Phase 1 evidence report."""

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

import yaml
from jsonschema import Draft202012Validator


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--environment-dir", type=pathlib.Path, required=True)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    return parser.parse_args()


class Report:
    def __init__(self):
        self.started = dt.datetime.now(dt.timezone.utc)
        self.checks = []

    def add(self, check_id, status, evidence, remediation):
        self.checks.append({"id": check_id, "status": status, "evidence": evidence, "remediation": remediation})

    def write(self, args, connection_mode, repository):
        finished = dt.datetime.now(dt.timezone.utc)
        failed = any(check["status"] == "fail" for check in self.checks)
        report = {
            "schema_version": "1",
            "phase": "phase-1-preflight",
            "started_at": self.started.isoformat().replace("+00:00", "Z"),
            "finished_at": finished.isoformat().replace("+00:00", "Z"),
            "repository": repository,
            "environment": args.environment,
            "connection_mode": connection_mode,
            "checks": self.checks,
            "overall_status": "fail" if failed else "pass",
            "remote_checks": "not_implemented",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Phase 1 preflight: {report['overall_status']}")
        print(f"Report: {args.report}")
        return 1 if failed else 0


def read_yaml(path, report, check_id):
    if not path.is_file():
        report.add(check_id, "fail", f"missing file: {path.name}", f"Create {path.name} from the environment example.")
        return None
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        report.add(check_id, "fail", f"could not parse {path.name}: {type(exc).__name__}", f"Fix the YAML syntax in {path.name}.")
        return None


def check_inventory(inventory, report):
    if isinstance(inventory, dict) and isinstance(inventory.get("all"), dict):
        platform_group = inventory["all"].get("children", {}).get("platform_host", {})
    else:
        platform_group = inventory.get("platform_host", {}) if isinstance(inventory, dict) else {}
    hosts = platform_group.get("hosts", {}) if isinstance(platform_group, dict) else platform_group
    if isinstance(hosts, (list, dict)) and len(hosts) == 1:
        report.add("inventory.single_platform_host", "pass", "exactly one platform_host is configured", "")
    else:
        report.add("inventory.single_platform_host", "fail", "platform_host must contain exactly one host", "Define one platform_host with connection settings.")


def check_controller_commands(connection_mode, report):
    required = ["bash", "python3", "ansible-playbook", "ansible-galaxy"]
    if connection_mode == "ssh":
        required.append("ssh")
    for command in required:
        result = subprocess.run(["bash", "-lc", f"command -v {command}"], capture_output=True, text=True)
        report.add(f"controller.command.{command}", "pass" if result.returncode == 0 else "fail", result.stdout.strip() or "not found", f"Install {command} on the controller.")
    for command in ("sops", "age"):
        result = subprocess.run(["bash", "-lc", f"command -v {command}"], capture_output=True, text=True)
        report.add(f"controller.command.{command}", "pass" if result.returncode == 0 else "fail", result.stdout.strip() or "not found", f"Install {command}; secrets must remain encrypted.")


def repository_state(repository_path):
    try:
        commit = subprocess.run(["git", "-C", str(repository_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", str(repository_path), "status", "--porcelain"], capture_output=True, text=True, check=False).stdout != ""
        return {"commit": commit, "dirty_worktree": dirty}
    except OSError:
        return {"commit": None, "dirty_worktree": None}


def main():
    args = parse_args()
    report = Report()
    if not args.environment_dir.is_dir():
        report.add("environment.exists", "fail", f"unknown environment: {args.environment}", "Create the environment directory and its required input files.")
        return report.write(args, None, repository_state(args.repository))

    report.add("environment.exists", "pass", args.environment, "")
    inventory = read_yaml(args.environment_dir / "inventory.yml", report, "inventory.parse")
    platform = read_yaml(args.environment_dir / "platform.yml", report, "platform.parse")
    connection_mode = platform.get("connection", {}).get("mode") if isinstance(platform, dict) else None
    if platform is not None:
        try:
            schema = json.loads(args.schema.read_text(encoding="utf-8"))
            errors = sorted(Draft202012Validator(schema).iter_errors(platform), key=lambda error: list(error.path))
            if errors:
                details = "; ".join(".".join(map(str, error.path)) + ": " + error.message for error in errors[:5])
                report.add("platform.schema.valid", "fail", details, "Correct platform.yml to match platform.schema.json.")
            else:
                report.add("platform.schema.valid", "pass", "platform.yml conforms to the schema", "")
        except (OSError, json.JSONDecodeError) as exc:
            report.add("platform.schema.valid", "fail", f"schema unavailable: {type(exc).__name__}", "Restore the version-controlled platform schema.")
    if connection_mode in ("local", "ssh"):
        report.add("connection.mode.valid", "pass", connection_mode, "")
    else:
        report.add("connection.mode.valid", "fail", "connection.mode must be local or ssh", "Set connection.mode to local for the current single-machine workflow.")
    if inventory is not None:
        check_inventory(inventory, report)
    check_controller_commands(connection_mode, report)

    secret_path = args.environment_dir / "secrets.sops.yml"
    if not secret_path.is_file():
        report.add("secrets.encrypted", "fail", "missing secrets.sops.yml", "Create an encrypted SOPS file; do not commit plaintext secrets.")
    else:
        secret_text = secret_path.read_text(encoding="utf-8", errors="replace")
        encrypted = "sops:" in secret_text and "ENC[" in secret_text
        report.add("secrets.encrypted", "pass" if encrypted else "fail", "SOPS metadata detected" if encrypted else "file is not recognizably encrypted", "Encrypt the required secret values with SOPS and age.")
    return report.write(args, connection_mode, repository_state(args.repository))


if __name__ == "__main__":
    sys.exit(main())