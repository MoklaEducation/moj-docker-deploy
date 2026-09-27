#!/usr/bin/env python3
"""Focused tests for protected bootstrap kubeconfig handling."""

import importlib.util
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

import yaml


MODULE_PATH = pathlib.Path(__file__).with_name("kubeconfig_contract.py")
SPEC = importlib.util.spec_from_file_location("kubeconfig_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def document(server="https://127.0.0.1:6443"):
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "default", "cluster": {"server": server, "certificate-authority-data": "ca"}}],
        "users": [{"name": "default", "user": {"client-certificate-data": "cert", "client-key-data": "key"}}],
        "contexts": [{"name": "default", "context": {"cluster": "default", "user": "default"}}],
        "current-context": "default",
    }


class KubeconfigContractTests(unittest.TestCase):
    def test_validate_accepts_declared_endpoint(self):
        MODULE.validate(document("https://192.168.1.151:6443"), "https://192.168.1.151:6443", {"192.168.1.151"})

    def test_validate_rejects_endpoint_outside_tls_sans(self):
        with self.assertRaises(ValueError):
            MODULE.validate(document("https://192.168.1.151:6443"), "https://192.168.1.151:6443", {"bastion151"})

    def test_prepare_rewrites_endpoint_and_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "kubeconfig"
            path.write_text(yaml.safe_dump(document()), encoding="utf-8")
            with mock.patch("sys.argv", ["kubeconfig_contract.py", "prepare", "--path", str(path), "--server", "https://192.168.1.151:6443", "--tls-san", "192.168.1.151"]):
                self.assertEqual(0, MODULE.main())
            prepared = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual("https://192.168.1.151:6443", prepared["clusters"][0]["cluster"]["server"])
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))


if __name__ == "__main__":
    unittest.main()