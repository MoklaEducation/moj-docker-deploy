#!/usr/bin/env python3
"""Update a Phase 1 report with the result of remote Ansible checks."""

import argparse
import json
import pathlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--ansible-status", type=int, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    report["remote_checks"] = "pass" if args.ansible_status == 0 else "fail"
    if args.ansible_status != 0:
        report["overall_status"] = "fail"
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1 preflight: {report['overall_status']}")
    print(f"Report: {args.report}")
    return args.ansible_status


if __name__ == "__main__":
    raise SystemExit(main())
