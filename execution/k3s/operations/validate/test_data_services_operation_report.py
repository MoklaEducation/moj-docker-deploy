#!/usr/bin/env python3
"""Tests for redacted Phase 3 operation evidence parsing."""

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/data_services_operation_report.py"
SPEC = importlib.util.spec_from_file_location("data_services_operation_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DataServicesOperationReportTests(unittest.TestCase):
    def test_only_snapshot_identifier_is_parsed(self):
        text = "repository=https://user:secret@example.invalid\nsnapshot=abc123\n"
        self.assertEqual("abc123", MODULE.SNAPSHOT_PATTERN.search(text).group(1))

    def test_secret_text_has_no_snapshot_match(self):
        self.assertIsNone(MODULE.SNAPSHOT_PATTERN.search("password=secret"))


if __name__ == "__main__":
    unittest.main()