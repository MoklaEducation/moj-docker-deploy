#!/usr/bin/env python3
"""Focused regression tests for the platform configuration schema."""

import copy
import json
import pathlib
import unittest

import yaml
from jsonschema import Draft202012Validator


ROOT = pathlib.Path(__file__).parents[2]
SCHEMA = json.loads((ROOT / "operations/validate/schemas/platform.schema.json").read_text(encoding="utf-8"))
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


class PlatformSchemaTests(unittest.TestCase):
    def assert_invalid(self, path, value):
        platform = copy.deepcopy(PLATFORM)
        target = platform
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value
        self.assertTrue(list(VALIDATOR.iter_errors(platform)), path)

    def test_test_environment_matches_complete_contract(self):
        self.assertEqual([], list(VALIDATOR.iter_errors(PLATFORM)))

    def test_phase_2_host_fields_are_required(self):
        for field in (
            "config_root", "state_root", "evidence_root", "minimum_free_disk_percent",
            "timezone", "automation_user", "ssh_port", "disable_swap",
            "allow_automatic_security_updates", "allow_automatic_reboot", "journald_max_use",
        ):
            platform = copy.deepcopy(PLATFORM)
            del platform["host"][field]
            self.assertTrue(list(VALIDATOR.iter_errors(platform)), field)

    def test_phase_2_docker_fields_are_required(self):
        for field in (
            "apt_repository", "repository_key_fingerprint", "engine_version",
            "compose_plugin_version", "data_root", "log_max_size", "log_max_files",
        ):
            platform = copy.deepcopy(PLATFORM)
            del platform["docker"][field]
            self.assertTrue(list(VALIDATOR.iter_errors(platform)), field)

    def test_unsafe_phase_2_values_are_rejected(self):
        invalid_values = (
            (("host", "storage_root"), "relative/path"),
            (("host", "ssh_port"), 0),
            (("host", "allow_automatic_reboot"), True),
            (("host", "minimum_free_disk_percent"), 100),
            (("docker", "apt_repository"), "http://example.invalid/docker"),
            (("docker", "repository_key_fingerprint"), "not-a-fingerprint"),
            (("docker", "engine_version"), "REPLACE_WITH_REVIEWED_VERSION"),
            (("docker", "compose_plugin_version"), "REPLACE_WITH_REVIEWED_VERSION"),
            (("docker", "log_max_files"), 0),
        )
        for path, value in invalid_values:
            with self.subTest(path=path):
                self.assert_invalid(path, value)


if __name__ == "__main__":
    unittest.main()