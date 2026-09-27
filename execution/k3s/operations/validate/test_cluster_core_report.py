#!/usr/bin/env python3
"""Focused tests for durable Phase 5 evidence."""

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("cluster_core_report.py")
SPEC = importlib.util.spec_from_file_location("cluster_core_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClusterCoreReportTests(unittest.TestCase):
    def test_lifecycle_preserves_apply_and_check_runs(self):
        phase4 = {"phase": "phase-4-k3s-installation", "overall_status": "pass", "generated_at": "earlier", "facts": {"config_hash": "abc"}}
        runtime = {"overall_status": "pass", "rendered_sha256": "def", "managed_objects": [], "smoke": {"dns_allowed": True}}
        first = MODULE.build_report("test", "apply", phase4, runtime)
        second = MODULE.build_report("test", "check", phase4, runtime, first)
        self.assertEqual(["apply", "check"], [item["mode"] for item in second["lifecycle"]["runs"]])

    def test_bootstrap_required_is_retained(self):
        report = MODULE.build_report("test", "check", {}, {"overall_status": "bootstrap_required"})
        self.assertEqual("bootstrap_required", report["overall_status"])
        self.assertFalse(report["restricted_credentials_ready"])


if __name__ == "__main__":
    unittest.main()