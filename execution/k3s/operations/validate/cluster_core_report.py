#!/usr/bin/env python3
"""Write allowlisted Phase 5 cluster-core evidence."""

import argparse
import datetime as dt
import json
import pathlib
import re


FORBIDDEN = re.compile(
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|AGE-SECRET-KEY-|ENC\[|token\s*[=:]|client-key-data|client-certificate-data",
    re.IGNORECASE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--phase-4-report", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-report", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_report(environment, mode, phase4, runtime, existing=None):
    existing = existing or {}
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    runtime_status = runtime.get("overall_status", "fail")
    runs = existing.get("lifecycle", {}).get("runs", [])
    runs.append({
        "generated_at": generated_at,
        "mode": mode,
        "credential_mode": runtime.get("credential_mode"),
        "drift_before": runtime.get("drift_before"),
        "pruned_count": len(runtime.get("pruned", [])),
        "smoke_executed": bool(runtime.get("smoke")),
        "overall_status": runtime_status,
    })
    return {
        "schema_version": "1",
        "phase": "phase-5-cluster-core",
        "generated_at": generated_at,
        "environment": environment,
        "mode": mode,
        "prior_phases": [{
            "phase": phase4.get("phase"),
            "overall_status": phase4.get("overall_status"),
            "generated_at": phase4.get("generated_at"),
            "cluster_config_hash": phase4.get("facts", {}).get("config_hash"),
        }],
        "rendered_sha256": runtime.get("rendered_sha256"),
        "managed_objects": runtime.get("managed_objects", []),
        "object_count": runtime.get("object_count"),
        "credential_mode": runtime.get("credential_mode"),
        "restricted_credentials_ready": runtime.get("restricted_credentials_ready", False),
        "drift_before": runtime.get("drift_before"),
        "access_drift": runtime.get("access_drift", []),
        "authorization": runtime.get("authorization", {}),
        "network_storage_smoke": runtime.get("smoke", {}),
        "storage": runtime.get("storage", {}),
        "pruned": runtime.get("pruned", []),
        "checks": runtime.get("checks", []),
        "lifecycle": {"runs": runs[-20:]},
        "overall_status": runtime_status,
    }


def main():
    args = parse_args()
    phase4 = load_json(args.phase_4_report)
    runtime = load_json(args.runtime_report)
    report = build_report(args.environment, args.mode, phase4, runtime, load_json(args.report))
    rendered = json.dumps(report, sort_keys=True)
    if FORBIDDEN.search(rendered):
        raise ValueError("refusing to write secret-bearing Phase 5 evidence")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 5 cluster core: {report['overall_status']}")
    print(f"Report: {args.report}")
    return 0 if report["overall_status"] in ("pass", "bootstrap_required") else 1


if __name__ == "__main__":
    raise SystemExit(main())