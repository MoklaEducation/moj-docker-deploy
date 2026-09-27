#!/usr/bin/env python3
"""Focused tests for Phase 6 rendered resource policy."""

import copy
import importlib.util
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = pathlib.Path(__file__).with_name("cluster_addons_render.py")
SPEC = importlib.util.spec_from_file_location("cluster_addons_render", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLATFORM = yaml.safe_load((ROOT / "environments/test/platform.yml").read_text(encoding="utf-8"))
RELEASES = yaml.safe_load((ROOT / "cluster/addons/releases.yaml").read_text(encoding="utf-8"))
DOCUMENTS = [
    document for document in yaml.safe_load_all(
        (ROOT / "cluster/addons/certificates/resources/test.yaml").read_text(encoding="utf-8")
    ) if document
]


class ClusterAddonsRenderTests(unittest.TestCase):
    def test_owned_resources_match_platform_contract(self):
        self.assertEqual([], MODULE.validate(PLATFORM, RELEASES, DOCUMENTS, ROOT.parents[1]))

    def test_mutable_workload_image_is_rejected(self):
        documents = copy.deepcopy(DOCUMENTS)
        deployment = next(document for document in documents if document.get("kind") == "Deployment")
        deployment["spec"]["template"]["spec"]["containers"][0]["image"] = "busybox:latest"
        errors = MODULE.validate(PLATFORM, RELEASES, documents, ROOT.parents[1])
        self.assertIn("cluster_addons.render.image", {item[0] for item in errors})

    def test_host_path_is_rejected(self):
        documents = copy.deepcopy(DOCUMENTS)
        deployment = next(document for document in documents if document.get("kind") == "Deployment")
        deployment["spec"]["template"]["spec"]["volumes"] = [{"name": "host", "hostPath": {"path": "/"}}]
        errors = MODULE.validate(PLATFORM, RELEASES, documents, ROOT.parents[1])
        self.assertIn("cluster_addons.render.host_access", {item[0] for item in errors})

    def test_invalid_renewal_window_is_rejected(self):
        platform = copy.deepcopy(PLATFORM)
        platform["cluster_addons"]["certificates"]["renew_before"] = "168h"
        errors = MODULE.validate(platform, RELEASES, DOCUMENTS, ROOT.parents[1])
        self.assertIn("cluster_addons.certificates.duration", {item[0] for item in errors})


if __name__ == "__main__":
    unittest.main()