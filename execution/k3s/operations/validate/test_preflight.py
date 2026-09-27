#!/usr/bin/env python3
"""Focused regression tests for Phase 1 controller validation."""

import importlib.util
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock


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

    def test_scm_collection_is_checked_by_installed_identity(self):
        report = PREFLIGHT.Report()
        result = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"/collections": {"k3s.orchestration": {"version": "1.2.2"}}}),
        )
        with tempfile.TemporaryDirectory() as directory:
            requirements = pathlib.Path(directory) / "requirements.yml"
            requirements.write_text(
                "collections:\n"
                "  - name: https://github.com/k3s-io/k3s-ansible.git\n"
                "    type: git\n"
                "    version: 1.2.2\n"
                "    installed_name: k3s.orchestration\n",
                encoding="utf-8",
            )
            with mock.patch.object(PREFLIGHT.subprocess, "run", return_value=result):
                PREFLIGHT.check_collections(requirements, report, "ansible-galaxy")

        check = self.find_check(report, "controller.collections.pinned")
        self.assertEqual("pass", check["status"])

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

    def test_managed_k3s_interfaces_do_not_conflict_with_repeat_runs(self):
        result = types.SimpleNamespace(
            returncode=0,
            stdout=(
                "2: eth0    inet 192.168.1.151/24 brd 192.168.1.255 scope global eth0\n"
                "4: cni0    inet 10.42.0.1/24 brd 10.42.0.255 scope global cni0\n"
                "5: flannel.1    inet 10.42.0.0/32 scope global flannel.1\n"
                "6: vpn0    inet 10.42.9.1/24 brd 10.42.9.255 scope global vpn0\n"
            ),
        )
        with mock.patch.object(PREFLIGHT.subprocess, "run", return_value=result):
            interfaces, error = PREFLIGHT.local_ipv4_networks("ip")

        self.assertEqual("", error)
        self.assertEqual(["192.168.1.151/24", "10.42.9.1/24"], [str(interface) for interface in interfaces])


if __name__ == "__main__":
    unittest.main()