#!/usr/bin/env python3
"""Focused tests for Phase 5 rendered policy validation."""

import copy
import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/cluster_core_render.py"
SPEC = importlib.util.spec_from_file_location("cluster_core_render", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))
DOCUMENTS = list(yaml.safe_load_all(MODULE.render_overlay(ROOT / "cluster/core/overlays/test")))


class ClusterCoreRenderTests(unittest.TestCase):
    def test_current_overlay_is_valid(self):
        self.assertEqual([], MODULE.validate_documents(DOCUMENTS, PLATFORM))

    def test_rejects_secret(self):
        documents = copy.deepcopy(DOCUMENTS)
        documents.append({
            "apiVersion": "v1", "kind": "Secret",
            "metadata": {
                "name": "forbidden", "namespace": "judge-test",
                "labels": {"app.kubernetes.io/managed-by": "mokla-cluster-core"},
            },
        })
        errors = MODULE.validate_documents(documents, PLATFORM)
        self.assertIn("cluster_core.render.forbidden_kind", {item[0] for item in errors})

    def test_rejects_quota_drift(self):
        documents = copy.deepcopy(DOCUMENTS)
        quota = next(item for item in documents if item["kind"] == "ResourceQuota" and item["metadata"]["namespace"] == "judge-test")
        quota["spec"]["hard"]["requests.cpu"] = "9"
        errors = MODULE.validate_documents(documents, PLATFORM)
        self.assertIn("cluster_core.render.quota", {item[0] for item in errors})

    def test_rejects_secret_read_rbac(self):
        documents = copy.deepcopy(DOCUMENTS)
        role = next(item for item in documents if item["kind"] == "ClusterRole" and item["metadata"]["name"] == "mokla:platform-operator")
        role["rules"].append({"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"]})
        errors = MODULE.validate_documents(documents, PLATFORM)
        self.assertIn("cluster_core.render.rbac", {item[0] for item in errors})


if __name__ == "__main__":
    unittest.main()