#!/usr/bin/env python3
"""Focused tests for Phase 2 evidence generation."""

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("host_baseline_report.py")
SPEC = importlib.util.spec_from_file_location("host_baseline_report", MODULE_PATH)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class HostBaselineReportTests(unittest.TestCase):
    def test_recap_is_parsed(self):
        recap = REPORT.parse_recap(
            "localhost : ok=42 changed=3 unreachable=0 failed=0 skipped=2 rescued=0 ignored=0\n"
        )
        self.assertEqual(
            {"host": "localhost", "ok": 42, "changed": 3, "unreachable": 0, "failed": 0},
            recap,
        )

    def test_missing_recap_is_safe(self):
        self.assertIsNone(REPORT.parse_recap("fatal: safety assertion failed\n"))

    def test_check_mode_changes_are_pending(self):
        recap = REPORT.parse_recap(
            "localhost : ok=42 changed=1 unreachable=0 failed=0 skipped=2 rescued=0 ignored=0\n"
        )
        self.assertEqual(1, recap["changed"])


if __name__ == "__main__":
    unittest.main()