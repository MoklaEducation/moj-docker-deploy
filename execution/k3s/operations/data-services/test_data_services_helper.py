#!/usr/bin/env python3
"""CLI safety tests for the data-service operator helper."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


HELPER = pathlib.Path(__file__).with_name("data-services")
K3S_DIR = HELPER.parents[2]


class DataServicesHelperTests(unittest.TestCase):
    def run_helper(self, *arguments):
        return subprocess.run([str(HELPER), *arguments], capture_output=True, text=True, check=False)

    def test_setup_requires_explicit_provision_acknowledgement(self):
        result = self.run_helper("setup", "--environment", "test")
        self.assertEqual(2, result.returncode)
        self.assertIn("--provision-host-services", result.stderr)

    def test_check_rejects_provision_flag(self):
        result = self.run_helper("check", "--environment", "test", "--provision-host-services")
        self.assertEqual(2, result.returncode)

    def test_encrypt_secrets_requires_source(self):
        result = self.run_helper("encrypt-secrets", "--environment", "test")
        self.assertEqual(2, result.returncode)
        self.assertIn("--from", result.stderr)

    @unittest.skipUnless(shutil.which("ansible-playbook"), "ansible-playbook is required")
    def test_external_mode_skips_local_service_role(self):
        playbook = """---
- hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars:
    data_services:
      provisioning_mode: external
  roles:
    - role: data-services
      when: data_services.provisioning_mode == 'helper-managed'
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = pathlib.Path(temporary_directory) / "external.yml"
            playbook_path.write_text(playbook, encoding="utf-8")
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "--check", str(playbook_path)],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "ANSIBLE_ROLES_PATH": str(K3S_DIR / "host" / "roles")},
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(
            result.stdout,
            r"localhost\s+: ok=0\s+changed=0\s+unreachable=0\s+failed=0\s+skipped=[1-9][0-9]*",
        )


if __name__ == "__main__":
    unittest.main()