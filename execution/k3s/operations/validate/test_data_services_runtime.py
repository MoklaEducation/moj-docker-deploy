#!/usr/bin/env python3
"""Tests for live data-service validation and redacted evidence."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).parents[2]
MODULE_PATH = ROOT / "operations/validate/data_services_runtime.py"
SPEC = importlib.util.spec_from_file_location("data_services_runtime", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query):
        if query != "SELECT 1":
            raise AssertionError(query)

    def fetchone(self):
        return (1,)


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def close(self):
        return None


class FakeRedis:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def ping(self):
        return True

    def close(self):
        return None


class DataServicesRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.platform = {
            "data_services": {
                "delivery_profile": "hardened",
                "provisioning_mode": "external",
                "bind_address": "10.20.30.40",
                "tls": {"enabled": True, "minimum_version": "TLSv1.2", "ca_certificate_secret_key": "ca"},
                "mariadb": {"port": 3306, "probe_username": "monitor", "probe_password_secret_key": "mariadb_probe_password"},
                "redis": {"port": 6379, "probe_username": "monitor", "probe_password_secret_key": "redis_probe_password"},
            }
        }
        self.values = {"ca": "test-ca", "mariadb_probe_password": "maria-secret", "redis_probe_password": "redis-secret"}

    def test_authenticated_protocol_checks_pass_without_secret_evidence(self):
        with mock.patch.object(MODULE, "tls_context", return_value=object()), \
                mock.patch.object(MODULE.pymysql, "connect", return_value=FakeConnection()) as mariadb_connect, \
                mock.patch.object(MODULE.redis, "Redis", FakeRedis), \
                mock.patch.object(MODULE.tempfile, "NamedTemporaryFile", mock.mock_open()):
            checks = MODULE.validate_runtime(self.platform, self.values)
        self.assertEqual(["pass", "pass"], [check["status"] for check in checks])
        self.assertEqual("maria-secret", mariadb_connect.call_args.kwargs["password"])
        self.assertNotIn("secret", json.dumps(checks))

    def test_failed_probe_is_redacted_and_fails_report(self):
        with mock.patch.object(MODULE, "tls_context", return_value=object()), \
                mock.patch.object(MODULE.pymysql, "connect", side_effect=RuntimeError("password=do-not-leak")), \
                mock.patch.object(MODULE.redis, "Redis", FakeRedis), \
                mock.patch.object(MODULE.tempfile, "NamedTemporaryFile", mock.mock_open()):
            checks = MODULE.validate_runtime(self.platform, self.values)
        with tempfile.TemporaryDirectory() as directory:
            report_path = pathlib.Path(directory) / "runtime.json"
            status = MODULE.write_report(report_path, self.platform, checks)
            rendered = report_path.read_text(encoding="utf-8")
        self.assertEqual("fail", status)
        self.assertNotIn("do-not-leak", rendered)

    def test_plaintext_authenticated_protocol_checks(self):
        self.platform["data_services"]["tls"] = {"enabled": False}
        self.platform["data_services"]["delivery_profile"] = "development"
        self.values["mariadb_probe_password"] += "\n"
        self.values["redis_probe_password"] += "\n"
        redis_client = mock.Mock(side_effect=FakeRedis)
        with mock.patch.object(MODULE.pymysql, "connect", return_value=FakeConnection()) as mariadb_connect, \
            mock.patch.object(MODULE.redis, "Redis", redis_client):
            checks = MODULE.validate_runtime(self.platform, self.values)
        self.assertEqual(["pass", "pass"], [check["status"] for check in checks])
        self.assertNotIn("ssl", mariadb_connect.call_args.kwargs)
        self.assertNotIn("ssl", redis_client.call_args.kwargs)
        self.assertEqual("maria-secret", mariadb_connect.call_args.kwargs["password"])
        self.assertEqual("redis-secret", redis_client.call_args.kwargs["password"])


if __name__ == "__main__":
    unittest.main()