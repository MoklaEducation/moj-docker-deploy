#!/usr/bin/env python3
"""Validate live Phase 3 data and external platform service contracts."""

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

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
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
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


def minio_command(platform, *arguments, stdin=None, check=True):
    external = platform["external_platform_services"]
    storage = external["object_storage"]
    container = f"mokla-{platform['environment_name']}-minio-1"
    script = (
        "export MC_CONFIG_DIR=/tmp/mc-runtime; "
        f"export MC_HOST_mokla=\"http://$(cat /run/secrets/minio-restic-access-key):$(cat /run/secrets/minio-restic-secret-key)@{external['bind_address']}:{storage['api_port']}\"; "
        "exec mc \"$@\""
    )
    result = subprocess.run(
        ["docker", "exec", "-i", container, "/bin/bash", "-ec", script, "--", *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError("MinIO protocol operation failed")
    return result


def request_json(url, method="GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=5) as response:
        content = response.read()
        return response.status, json.loads(content) if content else None


def restic_environment(platform, values):
    external = platform["external_platform_services"]
    storage = external["object_storage"]
    environment = dict(os.environ)
    environment.update({
        "RESTIC_REPOSITORY": f"s3:http://{external['bind_address']}:{storage['api_port']}/{storage['bucket']}/restic-smoke",
        "RESTIC_PASSWORD": values["restic_password"].strip(),
        "AWS_ACCESS_KEY_ID": values[storage["restic_access_key_secret_key"]].strip(),
        "AWS_SECRET_ACCESS_KEY": values[storage["restic_secret_key_secret_key"]].strip(),
    })
    return environment


def run_restic(environment, *arguments, stdin=None, check=True):
    result = subprocess.run(
        ["restic", *arguments], input=stdin, capture_output=True, text=True,
        timeout=180, check=False, env=environment,
    )
    if check and result.returncode:
        raise RuntimeError("restic operation failed")
    return result


def validate_runtime(platform, values, mode="check"):
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
    external = platform.get("external_platform_services")
    if external:
        storage = external["object_storage"]
        receiver = external["alert_receiver"]

        def check_minio():
            health_url = f"http://{external['bind_address']}:{storage['api_port']}/minio/health/live"
            with urllib.request.urlopen(health_url, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError("MinIO health endpoint failed")
            bucket = f"mokla/{storage['bucket']}"
            minio_command(platform, "ls", bucket)
            if minio_command(platform, "admin", "info", "mokla", check=False).returncode == 0:
                raise RuntimeError("MinIO restic identity unexpectedly has administrative access")
            if mode == "apply":
                key = f"{bucket}/phase3-probe-{uuid.uuid4().hex}"
                marker = uuid.uuid4().hex
                try:
                    minio_command(platform, "pipe", key, stdin=marker)
                    if minio_command(platform, "cat", key).stdout != marker:
                        raise RuntimeError("MinIO object checksum probe failed")
                finally:
                    minio_command(platform, "rm", "--force", key)

        def check_alert_receiver():
            base = receiver["endpoint"].removesuffix("/alerts")
            status, health = request_json(f"{base}/health")
            if status != 200 or health != {"status": "ok"}:
                raise RuntimeError("alert receiver health endpoint failed")
            if mode == "apply":
                probe_id = uuid.uuid4().hex
                request_json(f"{base}/events", method="DELETE")
                status, accepted = request_json(receiver["endpoint"], method="POST", payload={
                    "alerts": [{"status": "firing", "labels": {"alertname": "MoklaPhase3Probe", "probe_id": probe_id}}],
                })
                if status != 202 or accepted != {"accepted": 1}:
                    raise RuntimeError("alert receiver did not accept the controlled event")
                _, events = request_json(f"{base}/events")
                if [event.get("probe_id") for event in events.get("events", [])] != [probe_id]:
                    raise RuntimeError("alert receiver did not retain the controlled identifier")
                request_json(f"{base}/events", method="DELETE")

        def check_restic_repository():
            environment = restic_environment(platform, values)
            snapshots = run_restic(environment, "snapshots", "--json", check=False)
            if snapshots.returncode != 0:
                if mode != "apply":
                    raise RuntimeError("restic test repository is not initialized")
                run_restic(environment, "init")
            if mode == "apply":
                marker = uuid.uuid4().hex
                run_restic(
                    environment, "backup", "--stdin", "--stdin-filename", "phase3-marker.txt",
                    "--tag", "external-platform-services-smoke", stdin=marker,
                )
                run_restic(environment, "check")
                with tempfile.TemporaryDirectory(prefix="mokla-phase3-restic-") as directory:
                    run_restic(environment, "restore", "latest", "--target", directory)
                    restored = list(pathlib.Path(directory).rglob("phase3-marker.txt"))
                    if len(restored) != 1 or restored[0].read_text(encoding="utf-8") != marker:
                        raise RuntimeError("restic restored marker did not match")
                run_restic(
                    environment, "forget", "--tag", "external-platform-services-smoke",
                    "--keep-last", "1", "--prune",
                )

        for service, read_only_description, apply_description, probe in (
            ("minio", "health, bucket access, and admin denial", "object write/read/delete and admin denial", check_minio),
            ("alert_receiver", "health", "controlled delivery and cleanup", check_alert_receiver),
            ("restic_repository", "repository query", "snapshot, check, restore, and retention", check_restic_repository),
        ):
            status, duration_ms = timed_check(probe)
            checks.append({
                "id": f"external_platform_services.runtime.{service}",
                "status": status,
                "evidence": f"Private {service} {apply_description if mode == 'apply' else read_only_description} {'succeeded' if status == 'pass' else 'failed'} in {duration_ms} ms",
                "remediation": "Verify the private endpoint, container health, least-privilege credentials, and firewall policy." if status == "fail" else "",
            })
    return checks


def write_report(path, platform, checks):
    external = platform.get("external_platform_services")
    report = {
        "schema_version": "1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "endpoint": platform["data_services"]["bind_address"],
        "provisioning_mode": platform["data_services"]["provisioning_mode"],
        "delivery_profile": platform["data_services"]["delivery_profile"],
        "tls_enabled": platform["data_services"]["tls"]["enabled"],
        "external_platform_services": None if not external else {
            "profile": external["profile"],
            "bind_address": external["bind_address"],
            "object_storage_provider": external["object_storage"]["provider"],
            "alert_receiver_data_policy": external["alert_receiver"]["data_policy"],
        },
        "checks": checks,
        "overall_status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report["overall_status"]


def main():
    args = parse_args()
    if pymysql is None or redis is None or not shutil.which(args.sops) or not shutil.which("restic"):
        print("Phase 3 runtime services: fail (controller protocol dependencies are unavailable)", file=sys.stderr)
        return 1
    try:
        platform, values = load_inputs(args.platform, args.secrets, args.sops)
        checks = validate_runtime(platform, values, args.mode)
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