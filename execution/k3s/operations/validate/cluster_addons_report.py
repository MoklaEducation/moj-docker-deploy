#!/usr/bin/env python3
"""Write allowlisted Phase 6 cluster-addons evidence."""

import argparse
import datetime as dt
import json
import pathlib
import re


FORBIDDEN = re.compile(
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|AGE-SECRET-KEY-|ENC\[|client-key-data|client-certificate-data",
    re.IGNORECASE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), required=True)
    parser.add_argument("--phase-5-report", type=pathlib.Path, required=True)
    parser.add_argument("--render-facts", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-report", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser.parse_args()


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_report(environment, mode, phase5, render, runtime, existing=None):
    existing = existing or {}
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    runs = existing.get("lifecycle", {}).get("runs", [])
    runs.append({
        "generated_at": generated_at,
        "mode": mode,
        "credential_mode": runtime.get("credential_mode"),
        "drift_before": runtime.get("drift_before"),
        "overall_status": runtime.get("overall_status", "fail"),
    })
    certificate_smoke = runtime.get("certificate_smoke") or existing.get("certificate_smoke", {})
    metrics_smoke = runtime.get("metrics_smoke") or existing.get("metrics_smoke", {})
    if metrics_smoke.get("alert_delivery") == "not_run_in_check_mode":
        prior_delivery = existing.get("metrics_smoke", {}).get("alert_delivery")
        if prior_delivery:
            metrics_smoke["alert_delivery"] = prior_delivery
            if existing.get("metrics_smoke", {}).get("probe_id"):
                metrics_smoke["probe_id"] = existing["metrics_smoke"]["probe_id"]
    return {
        "schema_version": "1",
        "phase": "phase-6-cluster-addons",
        "generated_at": generated_at,
        "environment": environment,
        "mode": mode,
        "profile": "private-test",
        "prior_phases": [{
            "phase": phase5.get("phase"),
            "overall_status": phase5.get("overall_status"),
            "generated_at": phase5.get("generated_at"),
            "rendered_sha256": phase5.get("rendered_sha256"),
        }],
        "rendered_sha256": render.get("rendered_sha256"),
        "object_count": render.get("object_count"),
        "charts": render.get("charts", {}),
        "images": render.get("images", {}),
        "credential_mode": runtime.get("credential_mode"),
        "drift_before": runtime.get("drift_before"),
        "releases": runtime.get("releases", []),
        "certificate_smoke": certificate_smoke,
        "metrics_smoke": metrics_smoke,
        "deferred": runtime.get("deferred", {"metrics": True, "logs": True, "backups": True, "off_host_recovery": True}),
        "checks": runtime.get("checks", []),
        "lifecycle": {"runs": runs[-20:]},
        "overall_status": runtime.get("overall_status", "fail"),
    }


def main():
    args = parse_args()
    report = build_report(
        args.environment, args.mode, load_json(args.phase_5_report), load_json(args.render_facts),
        load_json(args.runtime_report), load_json(args.report),
    )
    rendered = json.dumps(report, sort_keys=True)
    if FORBIDDEN.search(rendered):
        raise ValueError("refusing to write secret-bearing Phase 6 evidence")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 6 cluster add-ons: {report['overall_status']}")
    print(f"Report: {args.report}")
    return 0 if report["overall_status"] in ("pass", "bootstrap_required") else 1


if __name__ == "__main__":
    raise SystemExit(main())