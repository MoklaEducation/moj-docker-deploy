#!/usr/bin/env python3
"""Focused tests for controlled k3s restart invariants."""

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("k3s_restart.py")
SPEC = importlib.util.spec_from_file_location("k3s_restart", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def snapshot(service_start="100", node_uid="node-1", version="v1.36.3+k3s1", container_suffix="1"):
    return {
        "service_start": service_start,
        "node": {"uid": node_uid, "ready": True, "version": version},
        "data_services": {
            "mariadb": {"id": f"mariadb-{container_suffix}", "running": True, "healthy": True},
            "redis": {"id": f"redis-{container_suffix}", "running": True, "healthy": True},
        },
    }


class K3sRestartTests(unittest.TestCase):
    def test_valid_restart_preserves_cluster_and_data_services(self):
        checks = MODULE.validate_transition(snapshot(), snapshot(service_start="200"), "v1.36.3+k3s1")

        self.assertTrue(all(checks.values()))

    def test_changed_data_service_identity_fails(self):
        checks = MODULE.validate_transition(snapshot(), snapshot(service_start="200", container_suffix="2"), "v1.36.3+k3s1")

        self.assertFalse(checks["data_service_identity_preserved"])

    def test_unchanged_service_start_fails(self):
        checks = MODULE.validate_transition(snapshot(), snapshot(), "v1.36.3+k3s1")

        self.assertFalse(checks["service_restarted"])


if __name__ == "__main__":
    unittest.main()