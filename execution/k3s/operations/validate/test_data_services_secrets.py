#!/usr/bin/env python3
"""Focused tests for the Phase 3 encrypted secret contract."""

import copy
import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/data_services_secrets.py"
SPEC = importlib.util.spec_from_file_location("data_services_secrets", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))


def expected_values(platform):
    return {key: f"fixture-value-for-{key}" for key in MODULE.required_secret_keys(platform)}


class DataServicesSecretsTests(unittest.TestCase):
    def test_complete_non_placeholder_contract_passes(self):
        self.assertEqual([], MODULE.validate_values(PLATFORM, expected_values(PLATFORM)))

    def test_provider_specific_keys_are_required(self):
        platform = copy.deepcopy(PLATFORM)
        platform["backup"]["repository_credential_secret_keys"] = ["restic_aws_access_key_id"]
        values = expected_values(platform)
        del values["restic_aws_access_key_id"]
        errors = MODULE.validate_values(platform, values)
        self.assertIn("data_services.secrets.required_keys", {check_id for check_id, _ in errors})

    def test_redis_password_is_conditional_on_authentication(self):
        platform = copy.deepcopy(PLATFORM)
        platform["data_services"]["redis"]["authentication_enabled"] = False
        self.assertNotIn("redis_password", MODULE.required_secret_keys(platform))

    def test_placeholder_values_are_rejected_without_echoing_them(self):
        values = expected_values(PLATFORM)
        placeholder = "TEST_ONLY_REPLACE_BEFORE_PHASE_3"
        values["mariadb_root_password"] = placeholder
        errors = MODULE.validate_values(PLATFORM, values)
        rendered = repr(errors)
        self.assertIn("data_services.secrets.non_placeholder", rendered)
        self.assertNotIn(placeholder, rendered)

    def test_non_mapping_document_is_rejected(self):
        errors = MODULE.validate_values(PLATFORM, ["not", "a", "mapping"])
        self.assertEqual("data_services.secrets.document", errors[0][0])


if __name__ == "__main__":
    unittest.main()