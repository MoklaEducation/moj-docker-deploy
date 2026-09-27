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
    document
    for path in (
        ROOT / "cluster/addons/certificates/resources/test.yaml",
        ROOT / "cluster/addons/metrics/resources/test.yaml",
        ROOT / "cluster/addons/node-metrics/resources/test.yaml",
    )
    for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
    if document
]


def node_exporter_document():
    return {
        "apiVersion": "apps/v1", "kind": "DaemonSet",
        "metadata": {"name": "node-exporter", "namespace": "observability-agents"},
        "spec": {"template": {"spec": {
            "hostNetwork": True, "hostPID": True, "hostIPC": False,
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": [
                {"name": "proc", "hostPath": {"path": "/proc"}},
                {"name": "sys", "hostPath": {"path": "/sys"}},
                {"name": "root", "hostPath": {"path": "/"}},
            ],
            "containers": [{
                "name": "node-exporter",
                "image": RELEASES["releases"]["node_metrics"]["images"]["node_exporter"],
                "resources": {"requests": {"cpu": "50m"}, "limits": {"cpu": "200m"}},
                "securityContext": {"allowPrivilegeEscalation": False, "privileged": False},
                "volumeMounts": [
                    {"name": "proc", "mountPath": "/host/proc", "readOnly": True},
                    {"name": "sys", "mountPath": "/host/sys", "readOnly": True},
                    {"name": "root", "mountPath": "/host/root", "readOnly": True},
                ],
            }],
        }}},
    }


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

    def test_scoped_node_exporter_host_access_is_allowed(self):
        documents = copy.deepcopy(DOCUMENTS) + [node_exporter_document()]
        self.assertEqual([], MODULE.validate(PLATFORM, RELEASES, documents, ROOT.parents[1]))

    def test_node_exporter_extra_host_path_is_rejected(self):
        daemonset = node_exporter_document()
        daemonset["spec"]["template"]["spec"]["volumes"].append({"name": "etc", "hostPath": {"path": "/etc"}})
        errors = MODULE.validate(PLATFORM, RELEASES, copy.deepcopy(DOCUMENTS) + [daemonset], ROOT.parents[1])
        self.assertIn("cluster_addons.render.host_access", {item[0] for item in errors})

    def test_invalid_renewal_window_is_rejected(self):
        platform = copy.deepcopy(PLATFORM)
        platform["cluster_addons"]["certificates"]["renew_before"] = "168h"
        errors = MODULE.validate(platform, RELEASES, DOCUMENTS, ROOT.parents[1])
        self.assertIn("cluster_addons.certificates.duration", {item[0] for item in errors})


if __name__ == "__main__":
    unittest.main()