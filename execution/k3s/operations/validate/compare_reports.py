#!/usr/bin/env python3
"""Compare two Phase 1 reports for stable check outcomes."""

import argparse
import json
import pathlib
import sys


def load_report(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stable_view(report):
    return {
        "phase": report.get("phase"),
        "environment": report.get("environment"),
        "connection_mode": report.get("connection_mode"),
        "overall_status": report.get("overall_status"),
        "checks": [(check.get("id"), check.get("status")) for check in report.get("checks", [])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=pathlib.Path, required=True)
    parser.add_argument("--second", type=pathlib.Path, required=True)
    args = parser.parse_args()
    first = stable_view(load_report(args.first))
    second = stable_view(load_report(args.second))
    if first != second:
        print("Phase 1 reports differ in stable outcomes:", file=sys.stderr)
        print(json.dumps({"first": first, "second": second}, indent=2), file=sys.stderr)
        return 1
    print(f"stable Phase 1 outcomes match: {len(second['checks'])} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
