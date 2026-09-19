#!/usr/bin/env python3
"""Tests for Phase 3 report redaction and recap parsing."""

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/data_services_report.py"
SPEC = importlib.util.spec_from_file_location("data_services_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DataServicesReportTests(unittest.TestCase):
    def test_recap_is_parsed(self):
        recap = MODULE.parse_recap("localhost : ok=24 changed=0 unreachable=0 failed=0 skipped=2 rescued=0 ignored=0\n")
        self.assertEqual(24, recap["ok"])
        self.assertEqual(0, recap["changed"])

    def test_secret_markers_are_rejected(self):
        for value in (
            "-----BEGIN PRIVATE KEY-----",
            "AGE-SECRET-KEY-1EXAMPLE",
            "ENC[AES256_GCM,data:example]",
            "https://user:password@example.invalid/repository",
            "password=secret",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE.assert_redacted({"evidence": value})

    def test_non_secret_digest_and_paths_are_allowed(self):
        MODULE.assert_redacted({"image": "mariadb:11.8@sha256:" + "a" * 64, "path": "/srv/mokla/data-services"})


if __name__ == "__main__":
    unittest.main()