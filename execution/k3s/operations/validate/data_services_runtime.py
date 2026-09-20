#!/usr/bin/env python3
"""Validate live MariaDB and Redis contracts over authenticated TLS."""

import argparse
import datetime as dt
import json
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import time

import yaml

try:
    import pymysql
    import redis
except ImportError:
    pymysql = None
    redis = None


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--secrets", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--sops", default="sops")
    return parser.parse_args()


def load_inputs(platform_path, secrets_path, sops_command):
    platform = yaml.safe_load(platform_path.read_text(encoding="utf-8"))
    decrypted = subprocess.run(
        [sops_command, "--decrypt", str(secrets_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if decrypted.returncode:
        raise RuntimeError("SOPS decryption failed")
    values = yaml.safe_load(decrypted.stdout)
    if not isinstance(values, dict):
        raise RuntimeError("decrypted secrets are not a mapping")
    return platform, values


def tls_context(ca_certificate, minimum_version):
    context = ssl.create_default_context(cadata=ca_certificate)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    versions = {"TLSv1.2": ssl.TLSVersion.TLSv1_2, "TLSv1.3": ssl.TLSVersion.TLSv1_3}
    context.minimum_version = versions[minimum_version]
    return context


def timed_check(check):
    started = time.monotonic()
    try:
        check()
    except Exception:
        return "fail", round((time.monotonic() - started) * 1000)
    return "pass", round((time.monotonic() - started) * 1000)


def validate_runtime(platform, values):
    data_services = platform["data_services"]
    tls = data_services["tls"]
    address = data_services["bind_address"]
    tls_enabled = tls["enabled"]
    ca_certificate = values[tls["ca_certificate_secret_key"]] if tls_enabled else None
    context = tls_context(ca_certificate, tls["minimum_version"]) if tls_enabled else None

    def check_mariadb():
        connection_options = dict(
            host=address,
            port=data_services["mariadb"]["port"],
            user=data_services["mariadb"]["probe_username"],
            password=values[data_services["mariadb"]["probe_password_secret_key"]].strip(),
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
        )
        if tls_enabled:
            connection_options["ssl"] = context
        connection = pymysql.connect(**connection_options)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("unexpected MariaDB probe result")
        finally:
            connection.close()

    def check_redis():
        client_options = dict(
            host=address,
            port=data_services["redis"]["port"],
            username=data_services["redis"]["probe_username"],
            password=values[data_services["redis"]["probe_password_secret_key"]].strip(),
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        ca_file = None
        if tls_enabled:
            ca_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8")
            ca_file.write(ca_certificate)
            ca_file.flush()
            client_options.update(ssl=True, ssl_ca_certs=ca_file.name, ssl_check_hostname=True)
        client = redis.Redis(**client_options)
        try:
            if client.ping() is not True:
                raise RuntimeError("unexpected Redis probe result")
        finally:
            client.close()
            if ca_file is not None:
                ca_file.close()

    checks = []
    for service, probe in (("mariadb", check_mariadb), ("redis", check_redis)):
        status, duration_ms = timed_check(probe)
        checks.append({
            "id": f"data_services.runtime.{service}",
            "status": status,
            "evidence": f"Authenticated {'TLS ' if tls_enabled else ''}{service} probe {'succeeded' if status == 'pass' else 'failed'} in {duration_ms} ms",
            "remediation": "Verify endpoint routing, certificate identity, credentials, and service health." if status == "fail" else "",
        })
    return checks


def write_report(path, platform, checks):
    report = {
        "schema_version": "1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "endpoint": platform["data_services"]["bind_address"],
        "provisioning_mode": platform["data_services"]["provisioning_mode"],
        "delivery_profile": platform["data_services"]["delivery_profile"],
        "tls_enabled": platform["data_services"]["tls"]["enabled"],
        "checks": checks,
        "overall_status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report["overall_status"]


def main():
    args = parse_args()
    if pymysql is None or redis is None or not shutil.which(args.sops):
        print("Phase 3 runtime services: fail (controller protocol dependencies are unavailable)", file=sys.stderr)
        return 1
    try:
        platform, values = load_inputs(args.platform, args.secrets, args.sops)
        checks = validate_runtime(platform, values)
        status = write_report(args.report, platform, checks)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError):
        print("Phase 3 runtime services: fail (runtime validation could not complete)", file=sys.stderr)
        return 1
    finally:
        values = None
    print(f"Phase 3 runtime services: {status}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())