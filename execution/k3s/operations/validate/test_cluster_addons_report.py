#!/usr/bin/env python3
"""Focused tests for durable Phase 6 evidence."""

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("cluster_addons_report.py")
SPEC = importlib.util.spec_from_file_location("cluster_addons_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClusterAddonsReportTests(unittest.TestCase):
    def test_lifecycle_and_certificate_smoke_survive_check(self):
        phase5 = {"phase": "phase-5-cluster-core", "overall_status": "pass"}
        render = {"rendered_sha256": "abc", "object_count": 66}
        first = MODULE.build_report(
            "test", "apply", phase5, render,
            {"overall_status": "pass", "certificate_smoke": {"https_valid": True}},
        )
        second = MODULE.build_report("test", "check", phase5, render, {"overall_status": "pass"}, first)
        self.assertEqual(["apply", "check"], [item["mode"] for item in second["lifecycle"]["runs"]])
        self.assertTrue(second["certificate_smoke"]["https_valid"])

    def test_bootstrap_required_is_a_valid_evidence_state(self):
        report = MODULE.build_report("test", "check", {}, {}, {"overall_status": "bootstrap_required"})
        self.assertEqual("bootstrap_required", report["overall_status"])
        self.assertTrue(report["deferred"]["backups"])

    def test_check_preserves_apply_time_alert_delivery(self):
        applied = MODULE.build_report(
            "test", "apply", {}, {},
            {"overall_status": "pass", "metrics_smoke": {"alert_delivery": "passed", "probe_id": "probe-1"}},
        )
        checked = MODULE.build_report(
            "test", "check", {}, {},
            {"overall_status": "pass", "metrics_smoke": {"alert_delivery": "not_run_in_check_mode"}},
            applied,
        )
        self.assertEqual("passed", checked["metrics_smoke"]["alert_delivery"])
        self.assertEqual("probe-1", checked["metrics_smoke"]["probe_id"])

    def test_check_preserves_apply_time_log_proofs(self):
        applied = MODULE.build_report(
            "test", "apply", {}, {},
            {"overall_status": "pass", "logs_smoke": {"ingestion": "passed", "redaction": "passed", "events": "passed", "probe_id": "probe-2"}},
        )
        checked = MODULE.build_report(
            "test", "check", {}, {},
            {"overall_status": "pass", "logs_smoke": {"ingestion": "not_run_in_check_mode", "redaction": "not_run_in_check_mode", "events": "not_run_in_check_mode"}},
            applied,
        )
        self.assertEqual("passed", checked["logs_smoke"]["ingestion"])
        self.assertEqual("passed", checked["logs_smoke"]["redaction"])
        self.assertEqual("passed", checked["logs_smoke"]["events"])
        self.assertEqual("probe-2", checked["logs_smoke"]["probe_id"])


if __name__ == "__main__":
    unittest.main()