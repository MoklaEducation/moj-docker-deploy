#!/usr/bin/env python3
"""Focused tests for protected Phase 5 kubeconfig handling."""

import importlib.util
import pathlib
import stat
import subprocess
import tempfile
import unittest

import yaml


MODULE_PATH = pathlib.Path(__file__).with_name("cluster_core_access.py")
SPEC = importlib.util.spec_from_file_location("cluster_core_access", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClusterCoreAccessTests(unittest.TestCase):
    def test_loads_current_cluster_from_admin_kubeconfig(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "admin.kubeconfig"
            path.write_text(yaml.safe_dump({
                "current-context": "active",
                "contexts": [{"name": "active", "context": {"cluster": "cluster-a", "user": "admin"}}],
                "clusters": [{"name": "cluster-a", "cluster": {"server": "https://api.example:6443", "certificate-authority-data": "Y2E="}}],
            }), encoding="utf-8")
            self.assertEqual(("https://api.example:6443", "Y2E="), MODULE.load_admin_cluster(path))

    def test_written_kubeconfig_is_private_and_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "identity.kubeconfig"
            MODULE.write_kubeconfig(path, "identity", "https://api.example:6443", "Y2E=", b"certificate", b"private-key")
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            self.assertEqual("identity", document["current-context"])
            self.assertEqual("identity", document["users"][0]["name"])

    def test_validates_pem_certificate_issued_by_kubernetes_style_signer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            key = root / "client.key"
            certificate = root / "client.crt"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "ec",
                "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                "-subj", "/CN=identity/O=group", "-days", "2",
                "-keyout", str(key), "-out", str(certificate),
            ], capture_output=True, check=True)
            kubeconfig = root / "identity.kubeconfig"
            MODULE.write_kubeconfig(
                kubeconfig, "identity", "https://api.example:6443", "Y2E=",
                certificate.read_bytes(), key.read_bytes(),
            )
            MODULE.validate_kubeconfig(kubeconfig, "identity", "https://api.example:6443")


if __name__ == "__main__":
    unittest.main()