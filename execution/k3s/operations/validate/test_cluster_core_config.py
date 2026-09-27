#!/usr/bin/env python3
"""Focused tests for Phase 5 cluster-core semantic configuration."""

import copy
import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/cluster_core_config.py"
SPEC = importlib.util.spec_from_file_location("cluster_core_config", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))
REPOSITORY = ROOT.parents[1]
RECIPIENT = PLATFORM["cluster_core"]["secret_delivery"]["age_recipient"]


class ClusterCoreConfigTests(unittest.TestCase):
    def assert_invalid(self, check_id, update):
        platform = copy.deepcopy(PLATFORM)
        update(platform)
        errors = MODULE.validate_configuration(platform, REPOSITORY, RECIPIENT)
        self.assertIn(check_id, {item[0] for item in errors})

    def test_current_environment_is_valid(self):
        self.assertEqual([], MODULE.validate_configuration(PLATFORM, REPOSITORY, RECIPIENT))

    def test_application_namespace_matches_environment(self):
        self.assert_invalid(
            "cluster_core.namespaces.environment",
            lambda platform: platform["cluster_core"]["namespaces"].update(application="judge-prod"),
        )

    def test_active_namespace_cannot_be_reserved(self):
        self.assert_invalid(
            "cluster_core.namespaces.reserved",
            lambda platform: platform["cluster_core"]["namespaces"]["reserved"].append("judge-test"),
        )

    def test_storage_allowlist_must_match_active_namespaces(self):
        self.assert_invalid(
            "cluster_core.storage.scope",
            lambda platform: platform["cluster_core"]["storage"]["allowed_namespaces"].remove("judge-test"),
        )

    def test_identities_must_be_separate(self):
        self.assert_invalid(
            "cluster_core.identities.names",
            lambda platform: platform["cluster_core"]["identities"]["automation"].update(name="mokla-platform-operator"),
        )

    def test_quota_requests_cannot_exceed_limits(self):
        self.assert_invalid(
            "cluster_core.quotas.application.cpu",
            lambda platform: platform["cluster_core"]["quotas"]["application"].update(requests_cpu="5"),
        )

    def test_age_recipient_must_match_identity(self):
        errors = MODULE.validate_configuration(PLATFORM, REPOSITORY, "age1different")
        self.assertIn("cluster_core.secret_delivery.recipient", {item[0] for item in errors})


if __name__ == "__main__":
    unittest.main()