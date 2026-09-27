#!/usr/bin/env python3
"""Focused tests for Phase 5 runtime ownership helpers."""

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import yaml


MODULE_PATH = pathlib.Path(__file__).with_name("cluster_core_runtime.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("cluster_core_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClusterCoreRuntimeTests(unittest.TestCase):
    def test_routine_subset_excludes_rbac(self):
        documents = [
            {"kind": "Namespace"}, {"kind": "NetworkPolicy"},
            {"kind": "ClusterRole"}, {"kind": "RoleBinding"},
        ]
        routine = [item for item in documents if item["kind"] in MODULE.ROUTINE_KINDS]
        self.assertEqual(["Namespace", "NetworkPolicy"], [item["kind"] for item in routine])

    def test_secure_pod_meets_restricted_baseline(self):
        pod = MODULE.secure_pod("probe", "example@sha256:" + "a" * 64, "sleep 1")
        container = pod["spec"]["containers"][0]
        self.assertFalse(pod["spec"]["automountServiceAccountToken"])
        self.assertTrue(container["securityContext"]["runAsNonRoot"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], container["securityContext"]["capabilities"]["drop"])

    def test_desired_subset_ignores_server_metadata(self):
        document = yaml.safe_load("""
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: example
  namespace: judge-test
  labels: {app.kubernetes.io/managed-by: mokla-cluster-core}
  uid: ignored
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: example}
subjects: [{kind: Group, name: example, apiGroup: rbac.authorization.k8s.io}]
""")
        self.assertNotIn("uid", MODULE.desired_subset(document)["metadata"])

    def test_initial_validation_skips_objects_in_absent_namespaces(self):
        documents = [
            {"kind": "Namespace", "metadata": {"name": "judge-test"}},
            {"kind": "ResourceQuota", "metadata": {"name": "budget", "namespace": "judge-test"}},
            {"kind": "ClusterRole", "metadata": {"name": "observer"}},
        ]
        selected = MODULE.documents_with_existing_namespaces(documents, set())
        self.assertEqual(["Namespace", "ClusterRole"], [item["kind"] for item in selected])

    def test_prune_stale_deletes_owned_allowlisted_object(self):
        with tempfile.TemporaryDirectory() as directory:
            report = pathlib.Path(directory) / "previous.json"
            report.write_text('{"managed_objects":[{"kind":"NetworkPolicy","namespace":"judge-test","name":"stale"}]}', encoding="utf-8")
            responses = [
                mock.Mock(returncode=0, stdout='{"metadata":{"labels":{"app.kubernetes.io/managed-by":"mokla-cluster-core"}}}'),
                mock.Mock(returncode=0, stdout=""),
            ]
            with mock.patch.object(MODULE, "run", side_effect=responses):
                pruned = MODULE.prune_stale("kubeconfig", report, set())
        self.assertEqual([{"kind": "NetworkPolicy", "namespace": "judge-test", "name": "stale"}], pruned)

    def test_prune_stale_refuses_unowned_object(self):
        with tempfile.TemporaryDirectory() as directory:
            report = pathlib.Path(directory) / "previous.json"
            report.write_text('{"managed_objects":[{"kind":"NetworkPolicy","namespace":"judge-test","name":"stale"}]}', encoding="utf-8")
            response = mock.Mock(returncode=0, stdout='{"metadata":{"labels":{}}}')
            with mock.patch.object(MODULE, "run", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "refusing to prune unowned"):
                    MODULE.prune_stale("kubeconfig", report, set())


if __name__ == "__main__":
    unittest.main()