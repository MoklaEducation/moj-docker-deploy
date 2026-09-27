#!/usr/bin/env python3
"""Write redacted Phase 2 evidence from Ansible's recap and allow-listed facts."""

import argparse
import datetime as dt
import json
import pathlib
import re


RECAP_PATTERN = re.compile(
    r"^(?P<host>\S+)\s+:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)"
)
ALLOWED_FACT_KEYS = {
    "checks", "firewall", "packages", "reboot_required", "services", "storage"
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--phase-1-report", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-output", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-status", type=int, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def parse_recap(text):
    for line in reversed(text.splitlines()):
        match = RECAP_PATTERN.match(line)
        if match:
            return {key: int(value) if key != "host" else value for key, value in match.groupdict().items()}
    return None


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def main():
    args = parse_args()
    phase_1 = load_json(args.phase_1_report, {})
    raw_facts = load_json(args.facts, {})
    facts = {key: raw_facts[key] for key in ALLOWED_FACT_KEYS if key in raw_facts}
    recap = parse_recap(args.ansible_output.read_text(encoding="utf-8", errors="replace"))
    prior = load_json(args.report, {})
    apply_runs = prior.get("apply_runs", []) if isinstance(prior.get("apply_runs"), list) else []
    if args.mode == "apply" and recap:
        apply_runs = (apply_runs + [recap])[-2:]
    checks = facts.get("checks", [])
    checks.append({
        "id": "host_baseline.ansible.completed",
        "status": "pass" if args.ansible_status == 0 else "fail",
        "evidence": "Ansible completed successfully" if args.ansible_status == 0 else "Ansible stopped on a failed safety or convergence task",
        "remediation": "Review the named Ansible failure; do not bypass safety assertions." if args.ansible_status else "",
    })
    reboot_required = bool(facts.get("reboot_required", False))
    has_failed_check = any(check.get("status") == "fail" for check in checks)
    has_pending_changes = args.mode == "check" and bool(recap and recap["changed"])
    overall_status = "fail" if args.ansible_status or has_failed_check or has_pending_changes else "pass"
    report = {
        "schema_version": "1",
        "phase": "phase-2-host-baseline",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": args.environment,
        "mode": args.mode,
        "phase_1": {
            "phase": phase_1.get("phase"),
            "environment": phase_1.get("environment"),
            "finished_at": phase_1.get("finished_at"),
            "overall_status": phase_1.get("overall_status"),
            "remote_checks": phase_1.get("remote_checks"),
        },
        "role_version": "1",
        "ansible_recap": recap,
        "apply_runs": apply_runs,
        "reboot_required": reboot_required,
        "checks": checks,
        "facts": {key: value for key, value in facts.items() if key not in {"checks", "reboot_required"}},
        "overall_status": overall_status,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 2 host baseline: {report['overall_status']}")
    print(f"reboot_required={str(reboot_required).lower()}")
    print(f"Report: {args.report}")
    return 0 if overall_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())