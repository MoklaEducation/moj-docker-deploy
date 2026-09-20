#!/usr/bin/env python3
"""Write redacted Phase 3 convergence evidence from allow-listed facts."""

import argparse
import datetime as dt
import json
import pathlib
import re


RECAP_PATTERN = re.compile(
    r"^(?P<host>\S+)\s+:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)"
)
ALLOWED_FACT_KEYS = {"checks", "configuration_hashes", "delivery_profile", "images", "network", "role_version", "services"}
FORBIDDEN_PATTERNS = re.compile(
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|AGE-SECRET-KEY-|ENC\[|AKIA[0-9A-Z]{16}|password\s*[=:]",
    re.IGNORECASE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--phase-1-report", type=pathlib.Path, required=True)
    parser.add_argument("--phase-2-report", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-report", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-output", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-status", type=int, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def parse_recap(text):
    for line in reversed(text.splitlines()):
        match = RECAP_PATTERN.match(line)
        if match:
            return {key: int(value) if key != "host" else value for key, value in match.groupdict().items()}
    return None


def assert_redacted(report):
    rendered = json.dumps(report, sort_keys=True)
    if FORBIDDEN_PATTERNS.search(rendered) or re.search(r"\w+://[^/@\s]+@", rendered):
        raise ValueError("refusing to write secret-bearing Phase 3 evidence")


def main():
    args = parse_args()
    phase_1 = load_json(args.phase_1_report, {})
    phase_2 = load_json(args.phase_2_report, {})
    raw_facts = load_json(args.facts, {})
    runtime = load_json(args.runtime_report, {})
    facts = {key: raw_facts[key] for key in ALLOWED_FACT_KEYS if key in raw_facts}
    recap = parse_recap(args.ansible_output.read_text(encoding="utf-8", errors="replace"))
    checks = list(facts.pop("checks", []))
    runtime_checks = runtime.get("checks", []) if isinstance(runtime, dict) else []
    if runtime_checks:
        checks.extend(runtime_checks)
    else:
        checks.append({
            "id": "data_services.runtime.completed",
            "status": "fail",
            "evidence": "Live protocol validation did not produce a report",
            "remediation": "Run the Phase 3 check with reachable TLS endpoints and valid SOPS credentials.",
        })
    checks.append({
        "id": "data_services.ansible.completed",
        "status": "pass" if args.ansible_status == 0 else "fail",
        "evidence": "Ansible completed successfully" if args.ansible_status == 0 else "Ansible stopped on a failed Phase 3 gate",
        "remediation": "Review the named failure; never bypass adoption or secret safety gates." if args.ansible_status else "",
    })
    failed = args.ansible_status != 0 or any(check.get("status") == "fail" for check in checks)
    pending = any(check.get("status") == "pending" for check in checks)
    report = {
        "schema_version": "1",
        "phase": "phase-3-host-data-services",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": args.environment,
        "mode": args.mode,
        "phase_1": {"overall_status": phase_1.get("overall_status"), "finished_at": phase_1.get("finished_at")},
        "phase_2": {"overall_status": phase_2.get("overall_status"), "generated_at": phase_2.get("generated_at")},
        "ansible_recap": recap,
        "checks": checks,
        "facts": facts,
        "runtime": {
            "endpoint": runtime.get("endpoint"),
            "provisioning_mode": runtime.get("provisioning_mode"),
            "delivery_profile": runtime.get("delivery_profile"),
            "tls_enabled": runtime.get("tls_enabled"),
        },
        "overall_status": "fail" if failed else ("partial" if pending else "pass"),
    }
    assert_redacted(report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3 host data services: {report['overall_status']}")
    print(f"Report: {args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())