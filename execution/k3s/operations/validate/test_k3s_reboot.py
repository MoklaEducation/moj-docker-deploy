#!/usr/bin/env python3
"""Focused tests for Phase 4 reboot recovery invariants."""

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("k3s_reboot.py")
SPEC = importlib.util.spec_from_file_location("k3s_reboot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def snapshot(boot_id="boot-1", node="node-1", container="1"):
    return {
        "boot_id": boot_id,
        "node_identity_hash": node,
        "node_ready": True,
        "version": "v1.36.3+k3s1",
        "k3s_active": True,
        "k3s_enabled": True,
        "docker_active": True,
        "containers": {
            "mariadb": {"identity_hash": f"mariadb-{container}", "healthy": True},
            "redis": {"identity_hash": f"redis-{container}", "healthy": True},
        },
    }


class K3sRebootTests(unittest.TestCase):
    def test_valid_recovery_requires_changed_boot(self):
        checks = MODULE.recovery_checks(snapshot(), snapshot(boot_id="boot-2"), "v1.36.3+k3s1")

        self.assertTrue(all(checks.values()))

    def test_same_boot_does_not_pass(self):
        checks = MODULE.recovery_checks(snapshot(), snapshot(), "v1.36.3+k3s1")

        self.assertFalse(checks["boot_changed"])

    def test_changed_container_identity_does_not_pass(self):
        checks = MODULE.recovery_checks(snapshot(), snapshot(boot_id="boot-2", container="2"), "v1.36.3+k3s1")

        self.assertFalse(checks["data_service_identity_preserved"])


if __name__ == "__main__":
    unittest.main()