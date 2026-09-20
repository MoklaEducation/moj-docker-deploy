#!/usr/bin/env python3
"""Focused tests for Phase 3 semantic configuration validation."""

import copy
import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/data_services_config.py"
SPEC = importlib.util.spec_from_file_location("data_services_config", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))


def valid_platform():
    platform = copy.deepcopy(PLATFORM)
    platform["data_services"]["delivery_profile"] = "hardened"
    platform["data_services"]["systemd_supervision_enabled"] = True
    platform["data_services"]["tls"]["enabled"] = True
    platform["backup"]["enabled"] = True
    platform["host_address"] = "10.20.30.40"
    platform["data_services"]["bind_address"] = "10.20.30.40"
    platform["data_services"]["tls"]["renewal_owner"] = "platform-operator"
    platform["data_services"]["mariadb"]["image"] = "docker.io/library/mariadb:11.8.3@sha256:" + "a" * 64
    platform["data_services"]["redis"]["image"] = "docker.io/library/redis:8.2.1@sha256:" + "b" * 64
    for service_name in ("mariadb", "redis"):
        service = platform["data_services"][service_name]
        service["compatibility_rationale"] = "Reviewed supported release for the initial platform"
        service["image_scan"] = {
            "scanner": "trivy 0.66.0",
            "scanned_at": "2026-09-19",
            "findings": "Reviewed findings accepted for test",
            "approved_by": "platform-operator",
        }
    platform["backup"]["restic_repository"] = "s3:https://objects.internal.example/backups/mokla-test"
    platform["backup"]["repository_mode"] = "off-host"
    platform["backup"]["local_repository_risk_accepted"] = False
    platform["backup"]["repository_credential_secret_keys"] = ["restic_aws_access_key_id", "restic_aws_secret_access_key"]
    return platform


class DataServicesConfigTests(unittest.TestCase):
    def assert_rejected(self, platform, check_id):
        self.assertIn(check_id, {error_id for error_id, _ in MODULE.validate_configuration(platform)})

    def test_complete_safe_configuration_passes(self):
        self.assertEqual([], MODULE.validate_configuration(valid_platform()))

    def test_current_test_configuration_passes(self):
        self.assertEqual([], MODULE.validate_configuration(PLATFORM))

    def test_development_profile_rejects_hardened_subsystems(self):
        platform = copy.deepcopy(PLATFORM)
        platform["data_services"]["tls"]["enabled"] = True
        platform["data_services"]["systemd_supervision_enabled"] = True
        platform["backup"]["enabled"] = True
        check_ids = {check_id for check_id, _ in MODULE.validate_configuration(platform)}
        self.assertIn("data_services.tls.development_disabled", check_ids)
        self.assertIn("data_services.systemd.development_disabled", check_ids)
        self.assertIn("backup.development_disabled", check_ids)

    def test_public_wildcard_and_mismatched_bind_addresses_are_rejected(self):
        for address, check_id in (
            ("0.0.0.0", "data_services.bind_address.private"),
            ("8.8.8.8", "data_services.bind_address.private"),
            ("10.20.30.41", "data_services.bind_address.host_match"),
        ):
            with self.subTest(address=address):
                platform = valid_platform()
                platform["data_services"]["bind_address"] = address
                self.assert_rejected(platform, check_id)

    def test_external_endpoint_does_not_need_to_match_platform_host(self):
        platform = valid_platform()
        platform["data_services"]["provisioning_mode"] = "external"
        platform["data_services"]["bind_address"] = "10.20.30.41"
        self.assertEqual([], MODULE.validate_configuration(platform))

    def test_unpinned_and_latest_images_are_rejected(self):
        for image in (
            "docker.io/library/mariadb:11.8.3",
            "docker.io/library/mariadb:latest@sha256:" + "a" * 64,
            "docker.io/library/mariadb:stable@sha256:" + "a" * 64,
        ):
            with self.subTest(image=image):
                platform = valid_platform()
                platform["data_services"]["mariadb"]["image"] = image
                self.assert_rejected(platform, "data_services.mariadb.image.pinned")

    def test_unsafe_repository_locations_are_rejected(self):
        for repository in (
            "/srv/mokla/restic",
            "s3:https://user:password@objects.example/backups",
            "s3:https://objects.example/backups?token=secret",
            "s3:https://backup.example.invalid/mokla-test",
        ):
            with self.subTest(repository=repository):
                platform = valid_platform()
                platform["backup"]["restic_repository"] = repository
                self.assert_rejected(platform, "backup.repository.safe_off_host")

    def test_local_repository_requires_bounded_test_exception(self):
        platform = valid_platform()
        platform["backup"]["repository_mode"] = "local-development"
        platform["backup"]["local_repository_risk_accepted"] = True
        platform["backup"]["restic_repository"] = "/srv/mokla/restic-repository"
        platform["backup"]["repository_credential_secret_keys"] = []
        self.assertEqual([], MODULE.validate_configuration(platform))

        for environment, accepted, path, check_id in (
            ("production", True, "/srv/mokla/restic-repository", "backup.repository.local_development"),
            ("test", False, "/srv/mokla/restic-repository", "backup.repository.local_development"),
            ("test", True, "/srv/mokla/backup-staging/repository", "backup.repository.local_path"),
        ):
            with self.subTest(environment=environment, accepted=accepted, path=path):
                candidate = copy.deepcopy(platform)
                candidate["environment_name"] = environment
                candidate["backup"]["local_repository_risk_accepted"] = accepted
                candidate["backup"]["restic_repository"] = path
                self.assert_rejected(candidate, check_id)

    def test_restore_must_be_isolated_and_loopback_only(self):
        platform = valid_platform()
        platform["backup"]["restore"]["target_root"] = platform["data_services"]["mariadb"]["data_path"]
        platform["backup"]["restore"]["bind_address"] = "10.20.30.40"
        platform["backup"]["restore"]["mariadb_port"] = platform["data_services"]["mariadb"]["port"]
        check_ids = {check_id for check_id, _ in MODULE.validate_configuration(platform)}
        self.assertIn("backup.restore.target_isolated", check_ids)
        self.assertIn("backup.restore.loopback_only", check_ids)
        self.assertIn("backup.restore.ports_isolated", check_ids)

    def test_redis_requires_authentication_and_memory_headroom(self):
        platform = valid_platform()
        platform["data_services"]["redis"]["authentication_enabled"] = False
        platform["data_services"]["redis"]["maxmemory"] = 512 * 1024 * 1024
        check_ids = {check_id for check_id, _ in MODULE.validate_configuration(platform)}
        self.assertIn("data_services.redis.authentication", check_ids)
        self.assertIn("data_services.redis.memory_headroom", check_ids)


if __name__ == "__main__":
    unittest.main()