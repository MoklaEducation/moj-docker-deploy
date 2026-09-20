#!/usr/bin/env python3
"""Tests for Phase 3 report redaction and recap parsing."""

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


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

    def test_runtime_failure_makes_phase_report_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            phase_1 = root / "phase1.json"
            phase_2 = root / "phase2.json"
            facts = root / "facts.json"
            runtime = root / "runtime.json"
            output = root / "ansible.txt"
            report = root / "report.json"
            phase_1.write_text('{"overall_status":"pass"}', encoding="utf-8")
            phase_2.write_text('{"overall_status":"pass"}', encoding="utf-8")
            facts.write_text('{"checks":[]}', encoding="utf-8")
            runtime.write_text(json.dumps({
                "endpoint": "10.20.30.40",
                "provisioning_mode": "external",
                "checks": [{"id": "data_services.runtime.redis", "status": "fail", "evidence": "probe failed", "remediation": "repair"}],
            }), encoding="utf-8")
            output.write_text("localhost : ok=1 changed=0 unreachable=0 failed=0\n", encoding="utf-8")
            argv = ["report", "--environment", "test", "--mode", "check", "--phase-1-report", str(phase_1),
                    "--phase-2-report", str(phase_2), "--facts", str(facts), "--runtime-report", str(runtime),
                    "--ansible-output", str(output), "--ansible-status", "0", "--report", str(report)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(1, MODULE.main())
            self.assertEqual("fail", json.loads(report.read_text(encoding="utf-8"))["overall_status"])


if __name__ == "__main__":
    unittest.main()