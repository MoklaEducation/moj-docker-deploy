#!/usr/bin/env python3
"""Focused regression tests for Phase 1 controller validation."""

import importlib.util
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("preflight.py")
SPEC = importlib.util.spec_from_file_location("phase_1_preflight", MODULE_PATH)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class MissingCommandTests(unittest.TestCase):
    def find_check(self, report, check_id):
        return next(check for check in report.checks if check["id"] == check_id)

    def test_missing_ansible_galaxy_is_reported(self):
        report = PREFLIGHT.Report()
        requirements = pathlib.Path(__file__).parents[2] / "host" / "requirements.yml"

        PREFLIGHT.check_collections(requirements, report, None)

        check = self.find_check(report, "controller.collections.pinned")
        self.assertEqual("fail", check["status"])
        self.assertIn("unavailable", check["evidence"])

    def test_missing_sops_is_reported_for_encrypted_file(self):
        report = PREFLIGHT.Report()
        with tempfile.TemporaryDirectory() as directory:
            secret_path = pathlib.Path(directory) / "secrets.sops.yml"
            secret_path.write_text("value: ENC[test]\nsops: {}\n", encoding="utf-8")

            PREFLIGHT.check_secrets(pathlib.Path(directory), report, None)

        check = self.find_check(report, "secrets.decryptable")
        self.assertEqual("fail", check["status"])
        self.assertIn("unavailable", check["evidence"])

    def test_missing_ip_is_reported(self):
        interfaces, error = PREFLIGHT.local_ipv4_networks(None)

        self.assertEqual([], interfaces)
        self.assertEqual("ip is unavailable", error)


if __name__ == "__main__":
    unittest.main()