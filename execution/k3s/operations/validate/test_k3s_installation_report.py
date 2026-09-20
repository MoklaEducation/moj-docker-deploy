#!/usr/bin/env python3
"""Focused tests for durable Phase 4 installation evidence."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("k3s_installation_report.py")
SPEC = importlib.util.spec_from_file_location("k3s_installation_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class K3sInstallationReportTests(unittest.TestCase):
    def run_report(self, directory, mode, before, after):
        root = pathlib.Path(directory)
        prior_paths = []
        for phase in range(1, 4):
            path = root / f"phase-{phase}.json"
            path.write_text(json.dumps({"phase": f"phase-{phase}", "overall_status": "pass"}), encoding="utf-8")
            prior_paths.append(path)
        facts = root / "facts.json"
        facts.write_text(json.dumps({
            "phase_state": "installed",
            "service_start_before": before,
            "service_start_after": after,
            "checks": [],
        }), encoding="utf-8")
        runtime = root / "runtime.json"
        runtime.write_text(json.dumps({"overall_status": "pass", "checks": []}), encoding="utf-8")
        output = root / "ansible.txt"
        output.write_text("localhost : ok=10 changed=0 unreachable=0 failed=0 skipped=0\n", encoding="utf-8")
        report = root / "report.json"
        argv = [
            "k3s_installation_report.py", "--environment", "test", "--mode", mode,
            "--phase-1-report", str(prior_paths[0]), "--phase-2-report", str(prior_paths[1]),
            "--phase-3-report", str(prior_paths[2]), "--facts", str(facts),
            "--runtime-report", str(runtime), "--ansible-output", str(output),
            "--ansible-status", "0", "--report", str(report),
        ]
        with mock.patch("sys.argv", argv):
            self.assertEqual(0, MODULE.main())
        return json.loads(report.read_text(encoding="utf-8"))

    def test_lifecycle_runs_survive_later_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_report(directory, "apply", "100", "100")
            second = self.run_report(directory, "check", "100", "100")

        self.assertEqual(1, len(first["lifecycle"]["runs"]))
        self.assertEqual(2, len(second["lifecycle"]["runs"]))
        self.assertEqual("full_smoke", second["lifecycle"]["runs"][0]["runtime_scope"])
        self.assertEqual("read_only_observation", second["lifecycle"]["runs"][1]["runtime_scope"])

    def test_changed_service_identity_records_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_report(directory, "apply", "100", "200")

        self.assertTrue(report["lifecycle"]["runs"][0]["service_restarted"])


if __name__ == "__main__":
    unittest.main()