#!/usr/bin/env python3
"""Focused tests for Phase 4 runtime validation state handling."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("k3s_runtime.py")
SPEC = importlib.util.spec_from_file_location("k3s_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class K3sRuntimeTests(unittest.TestCase):
    def test_completed_helm_job_does_not_make_traefik_unready(self):
        pods = [
            {
                "metadata": {"name": "helm-install-traefik-example"},
                "status": {"phase": "Succeeded", "conditions": []},
            },
            {
                "metadata": {"name": "traefik-example"},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
            },
        ]

        self.assertTrue(MODULE.component_is_ready(pods, "traefik"))

    def test_unready_running_replica_fails_component(self):
        pods = [
            {
                "metadata": {"name": "coredns-example"},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}]},
            },
        ]

        self.assertFalse(MODULE.component_is_ready(pods, "coredns"))

    def test_preinstall_state_is_successful_and_pending(self):
        repository = pathlib.Path(__file__).parents[4]
        platform = repository / "execution/k3s/environments/test/platform.yml"
        with tempfile.TemporaryDirectory() as directory:
            facts = pathlib.Path(directory) / "facts.json"
            report = pathlib.Path(directory) / "report.json"
            facts.write_text(json.dumps({"phase_state": "preinstall_ready"}), encoding="utf-8")
            with mock.patch("sys.argv", ["k3s_runtime.py", "--platform", str(platform), "--repository", str(repository), "--facts", str(facts), "--report", str(report)]):
                self.assertEqual(0, MODULE.main())
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual("preinstall_ready", result["overall_status"])
            self.assertEqual("pending", result["checks"][0]["status"])


if __name__ == "__main__":
    unittest.main()