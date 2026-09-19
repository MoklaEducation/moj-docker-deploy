#!/usr/bin/env python3
"""Write redacted Phase 3 backup and restore operation evidence."""

import argparse
import datetime as dt
import json
import pathlib
import re


SNAPSHOT_PATTERN = re.compile(r"(?:snapshot|verified_snapshot|restore_snapshot)=([0-9a-f]+)")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("backup", "verify", "restore"), required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--status", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--target")
    return parser.parse_args()


def main():
    args = parse_args()
    output = args.output.read_text(encoding="utf-8", errors="replace")
    match = SNAPSHOT_PATTERN.search(output)
    snapshot = args.snapshot or (match.group(1) if match else None)
    report = {
        "schema_version": "1",
        "phase": "phase-3-backup" if args.operation in {"backup", "verify"} else "phase-3-restore",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": args.environment,
        "operation": args.operation,
        "snapshot_id": snapshot,
        "target": args.target if args.operation == "restore" else None,
        "status": "pass" if args.status == 0 and snapshot else "fail",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 3 {args.operation}: {report['status']}")
    print(f"Report: {args.report}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())