#!/usr/bin/env python3
"""Focused tests for Phase 4 k3s semantic configuration."""

import copy
import importlib.util
import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/k3s_config.py"
SPEC = importlib.util.spec_from_file_location("k3s_config", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))
REPOSITORY = ROOT.parents[1]


class K3sConfigTests(unittest.TestCase):
    def assert_invalid(self, check_id, update):
        platform = copy.deepcopy(PLATFORM)
        update(platform)
        self.assertIn(check_id, {item[0] for item in MODULE.validate_configuration(platform, REPOSITORY)})

    def test_current_environment_is_valid(self):
        self.assertEqual([], MODULE.validate_configuration(PLATFORM, REPOSITORY))

    def test_rejects_placeholder_and_mutable_versions(self):
        for version in ("REPLACE_WITH_REVIEWED_VERSION", "stable", "latest"):
            with self.subTest(version=version):
                self.assert_invalid("k3s.version.pinned", lambda platform: platform["k3s"].update(version=version))

    def test_rejects_bad_checksum(self):
        self.assert_invalid("k3s.checksum.valid", lambda platform: platform["k3s"].update(checksum="abc"))

    def test_rejects_changed_cidr(self):
        self.assert_invalid("k3s.network.frozen", lambda platform: platform["k3s"].update(cluster_cidr="10.44.0.0/16"))

    def test_rejects_overlapping_cidrs(self):
        self.assert_invalid("k3s.network.disjoint", lambda platform: platform["k3s"].update(service_cidr="10.42.0.0/24"))

    def test_rejects_unassigned_bind_address(self):
        self.assert_invalid("k3s.api_bind_address.assigned", lambda platform: platform["k3s"].update(api_bind_address="0.0.0.0"))

    def test_rejects_path_overlap(self):
        self.assert_invalid("k3s.paths.disjoint", lambda platform: platform["k3s"].update(local_storage_path=platform["k3s"]["data_dir"] + "/storage"))

    def test_rejects_unignored_kubeconfig(self):
        self.assert_invalid("k3s.kubeconfig.ignored", lambda platform: platform["k3s"].update(kubeconfig_output="bootstrap-admin.kubeconfig"))


if __name__ == "__main__":
    unittest.main()