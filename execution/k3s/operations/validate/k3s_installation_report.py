#!/usr/bin/env python3
"""Write allow-listed Phase 4 installation evidence."""

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
    "role_version", "phase_state", "version", "checksum", "config_hash", "node_name",
    "node_ip", "api_bind_address", "cluster_cidr", "service_cidr", "data_dir",
    "local_storage_path", "service_active", "service_enabled", "docker_data_root", "checks",
    "service_start_before", "service_start_after",
}
FORBIDDEN = re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|AGE-SECRET-KEY-|ENC\[|token\s*[=:]|client-key-data", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--phase-1-report", type=pathlib.Path, required=True)
    parser.add_argument("--phase-2-report", type=pathlib.Path, required=True)
    parser.add_argument("--phase-3-report", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-report", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-output", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-status", type=int, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def parse_recap(text):
    for line in reversed(text.splitlines()):
        match = RECAP_PATTERN.match(line)
        if match:
            return {key: int(value) if key != "host" else value for key, value in match.groupdict().items()}
    return None


def main():
    args = parse_args()
    prior = [load_json(path) for path in (args.phase_1_report, args.phase_2_report, args.phase_3_report)]
    raw_facts = load_json(args.facts)
    runtime = load_json(args.runtime_report)
    facts = {key: raw_facts[key] for key in ALLOWED_FACT_KEYS if key in raw_facts}
    checks = list(facts.pop("checks", []))
    checks.extend(runtime.get("checks", []))
    checks.append({
        "id": "k3s.ansible.completed",
        "status": "pass" if args.ansible_status == 0 else "fail",
        "evidence": "Ansible completed successfully" if args.ansible_status == 0 else "Ansible stopped on a Phase 4 safety or convergence failure",
        "remediation": "" if args.ansible_status == 0 else "Review the named failure and do not bypass adoption or immutable-state guards.",
    })
    failed = args.ansible_status != 0 or not facts or not runtime or any(check.get("status") == "fail" for check in checks)
    pending = any(check.get("status") == "pending" for check in checks)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    recap = parse_recap(args.ansible_output.read_text(encoding="utf-8", errors="replace"))
    existing = load_json(args.report)
    lifecycle_runs = existing.get("lifecycle", {}).get("runs", [])
    start_before = facts.get("service_start_before") or None
    start_after = facts.get("service_start_after") or None
    overall_status = "fail" if failed else ("preinstall_ready" if pending else "pass")
    lifecycle_runs.append({
        "generated_at": generated_at,
        "mode": args.mode,
        "ansible_recap": recap,
        "service_start_before": start_before,
        "service_start_after": start_after,
        "service_restarted": bool(start_before and start_after and start_before != start_after),
        "runtime_scope": "full_smoke" if args.mode == "apply" else "read_only_observation",
        "overall_status": overall_status,
    })
    report = {
        "schema_version": "1",
        "phase": "phase-4-k3s-installation",
        "generated_at": generated_at,
        "environment": args.environment,
        "mode": args.mode,
        "prior_phases": [
            {"phase": item.get("phase"), "overall_status": item.get("overall_status"), "generated_at": item.get("generated_at") or item.get("finished_at")}
            for item in prior
        ],
        "ansible_recap": recap,
        "checks": checks,
        "facts": facts,
        "runtime": {key: runtime.get(key) for key in ("node", "kubelet_version", "components", "smoke_namespace")},
        "lifecycle": {
            "runs": lifecycle_runs[-20:],
            "controlled_restart": existing.get("lifecycle", {}).get("controlled_restart"),
            "reboot": existing.get("lifecycle", {}).get("reboot"),
        },
        "overall_status": overall_status,
    }
    rendered = json.dumps(report, sort_keys=True)
    if FORBIDDEN.search(rendered):
        raise ValueError("refusing to write secret-bearing Phase 4 evidence")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 4 k3s installation: {report['overall_status']}")
    print(f"Report: {args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())