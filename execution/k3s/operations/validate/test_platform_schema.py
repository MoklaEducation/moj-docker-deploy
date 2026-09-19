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

    def test_phase_3_data_service_fields_are_required(self):
        required_fields = {
            "data_services": ("bind_address", "allowed_client_cidrs", "tls", "mariadb", "redis"),
            "mariadb": (
                "image", "compatibility_rationale", "image_scan", "port", "character_set", "collation", "data_path", "config_path",
                "backup_timeout_seconds", "health_timeout_seconds", "memory_limit", "cpus",
            ),
            "redis": (
                "image", "compatibility_rationale", "image_scan", "port", "authentication_enabled", "data_policy", "data_path", "config_path",
                "maxmemory", "maxmemory_policy", "health_timeout_seconds", "memory_limit", "cpus",
            ),
        }
        for section, fields in required_fields.items():
            for field in fields:
                with self.subTest(section=section, field=field):
                    platform = copy.deepcopy(PLATFORM)
                    target = platform["data_services"] if section == "data_services" else platform["data_services"][section]
                    del target[field]
                    self.assertTrue(list(VALIDATOR.iter_errors(platform)), field)

    def test_phase_3_backup_fields_are_required(self):
        for field in (
            "repository_mode", "local_repository_risk_accepted", "restic_repository",
            "repository_credential_secret_keys", "staging_path", "schedule",
            "randomized_delay_seconds", "retention", "minimum_expected_frequency_hours",
            "minimum_free_space_mb", "restore",
        ):
            with self.subTest(field=field):
                platform = copy.deepcopy(PLATFORM)
                del platform["backup"][field]
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

    def test_structurally_invalid_phase_3_values_are_rejected(self):
        invalid_values = (
            (("data_services", "mariadb", "port"), 0),
            (("data_services", "mariadb", "data_path"), "relative/path"),
            (("data_services", "mariadb", "memory_limit"), "unbounded"),
            (("data_services", "redis", "data_policy"), "best-effort"),
            (("data_services", "redis", "maxmemory"), 0),
            (("data_services", "redis", "maxmemory_policy"), "unknown"),
            (("backup", "repository_credential_secret_keys"), ["INVALID-KEY"]),
            (("backup", "retention", "daily"), 0),
            (("backup", "restore", "target_root"), "relative/path"),
            (("backup", "restore", "redis_port"), 70000),
        )
        for path, value in invalid_values:
            with self.subTest(path=path):
                self.assert_invalid(path, value)


if __name__ == "__main__":
    unittest.main()