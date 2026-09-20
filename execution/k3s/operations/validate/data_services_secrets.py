#!/usr/bin/env python3
"""Validate Phase 3 SOPS secrets without exposing decrypted values."""

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml


PLACEHOLDER_PATTERN = re.compile(r"(?:REPLACE_|CHANGEME|TEST_ONLY|PLACEHOLDER|EXAMPLE)", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--secrets", type=pathlib.Path, required=True)
    parser.add_argument("--sops", default="sops")
    parser.add_argument("--openssl", default="openssl")
    return parser.parse_args()


def required_secret_keys(platform):
    tls = platform["data_services"]["tls"]
    data_services = platform["data_services"]
    keys = {
        data_services["mariadb"]["probe_password_secret_key"],
        data_services["redis"]["probe_password_secret_key"],
    }
    if tls["enabled"]:
        keys.update((
            tls["server_certificate_secret_key"],
            tls["server_private_key_secret_key"],
            tls["ca_certificate_secret_key"],
        ))
    if platform["backup"]["enabled"]:
        keys.add("restic_password")
        keys.update(platform["backup"]["repository_credential_secret_keys"])
    if data_services["provisioning_mode"] == "helper-managed":
        keys.update(("mariadb_root_password", "redis_password"))
    return keys


def validate_values(platform, values):
    errors = []
    if not isinstance(values, dict):
        return [("data_services.secrets.document", "decrypted secret document must be a mapping")]
    missing = sorted(required_secret_keys(platform) - set(values))
    if missing:
        errors.append(("data_services.secrets.required_keys", f"missing {len(missing)} required secret keys"))
    invalid = []
    for key in sorted(required_secret_keys(platform) & set(values)):
        value = values[key]
        if not isinstance(value, str) or not value.strip() or PLACEHOLDER_PATTERN.search(value):
            invalid.append(key)
    if invalid:
        errors.append(("data_services.secrets.non_placeholder", f"{len(invalid)} required secret values are empty or placeholders"))
    return errors


def run_openssl(command, input_text=None):
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def validate_tls_material(platform, values, openssl_command):
    tls = platform["data_services"]["tls"]
    certificate = values[tls["server_certificate_secret_key"]]
    private_key = values[tls["server_private_key_secret_key"]]
    ca_certificate = values[tls["ca_certificate_secret_key"]]
    errors = []

    certificate_result = run_openssl([openssl_command, "x509", "-noout", "-checkend", "86400"], certificate)
    ca_result = run_openssl([openssl_command, "x509", "-noout", "-checkend", "86400"], ca_certificate)
    key_result = run_openssl([openssl_command, "pkey", "-noout", "-check"], private_key)
    if certificate_result.returncode or ca_result.returncode or key_result.returncode:
        errors.append(("data_services.secrets.tls.parseable", "TLS certificate, CA, or private key is invalid or expires within 24 hours"))
        return errors

    certificate_public = run_openssl([openssl_command, "x509", "-pubkey", "-noout"], certificate)
    key_public = run_openssl([openssl_command, "pkey", "-pubout"], private_key)
    if certificate_public.returncode or key_public.returncode or certificate_public.stdout != key_public.stdout:
        errors.append(("data_services.secrets.tls.key_matches", "TLS private key does not match the server certificate"))

    with tempfile.TemporaryDirectory(prefix="mokla-phase3-tls-") as directory:
        directory_path = pathlib.Path(directory)
        certificate_path = directory_path / "server.crt"
        ca_path = directory_path / "ca.crt"
        certificate_path.write_text(certificate, encoding="utf-8")
        ca_path.write_text(ca_certificate, encoding="utf-8")
        os.chmod(certificate_path, 0o600)
        os.chmod(ca_path, 0o600)
        verify_result = run_openssl([openssl_command, "verify", "-CAfile", str(ca_path), str(certificate_path)])
        address_result = run_openssl([
            openssl_command,
            "x509",
            "-in",
            str(certificate_path),
            "-noout",
            "-checkip",
            platform["data_services"]["bind_address"],
        ])
    if verify_result.returncode:
        errors.append(("data_services.secrets.tls.chain", "server certificate is not issued by the configured CA"))
    if address_result.returncode:
        errors.append(("data_services.secrets.tls.identity", "server certificate does not cover the configured bind address"))
    return errors


def main():
    args = parse_args()
    if not args.secrets.is_file():
        print("data_services.secrets.encrypted: encrypted secret file is missing", file=sys.stderr)
        return 1
    sops_command = shutil.which(args.sops)
    if not sops_command:
        print("data_services.secrets.tooling: sops is required", file=sys.stderr)
        return 1
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        print("data_services.secrets.platform: platform configuration is unreadable", file=sys.stderr)
        return 1
    decrypted = subprocess.run(
        [sops_command, "--decrypt", str(args.secrets)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if decrypted.returncode:
        print("data_services.secrets.decryptable: SOPS decryption failed", file=sys.stderr)
        return 1
    try:
        values = yaml.safe_load(decrypted.stdout)
    except yaml.YAMLError:
        print("data_services.secrets.document: decrypted secret document is invalid YAML", file=sys.stderr)
        return 1
    openssl_command = shutil.which(args.openssl) if platform["data_services"]["tls"]["enabled"] else None
    errors = validate_values(platform, values)
    if platform["data_services"]["tls"]["enabled"] and not openssl_command:
        errors.append(("data_services.secrets.tooling", "openssl is required when TLS is enabled"))
    if not errors and platform["data_services"]["tls"]["enabled"]:
        errors.extend(validate_tls_material(platform, values, openssl_command))
    decrypted = None
    values = None
    if errors:
        print("Phase 3 secrets: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    print("Phase 3 secrets: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())