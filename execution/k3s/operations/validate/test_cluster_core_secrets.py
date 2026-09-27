#!/usr/bin/env python3
"""Focused tests for the Phase 5 encrypted Secret template."""

import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/cluster_core_secrets.py"
SPEC = importlib.util.spec_from_file_location("cluster_core_secrets", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))


class ClusterCoreSecretTests(unittest.TestCase):
    def test_encrypted_template_is_decryptable_and_valid(self):
        MODULE.validate_source(
            ROOT / "cluster/core/secrets/template.secret.sops.yaml",
            ROOT / "cluster/core/secrets/secret-source.schema.json",
            PLATFORM["cluster_core"]["secret_delivery"]["age_recipient"],
            str(ROOT / ".controller-venv/bin/sops"),
        )

    def test_wrong_recipient_is_rejected_without_plaintext(self):
        with self.assertRaisesRegex(ValueError, "configured age recipient"):
            MODULE.validate_source(
                ROOT / "cluster/core/secrets/template.secret.sops.yaml",
                ROOT / "cluster/core/secrets/secret-source.schema.json",
                "age1wrong",
                str(ROOT / ".controller-venv/bin/sops"),
            )


if __name__ == "__main__":
    unittest.main()