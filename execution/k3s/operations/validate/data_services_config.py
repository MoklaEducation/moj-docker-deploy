#!/usr/bin/env python3
"""Validate Phase 3 data-service configuration without mutating the host."""

import argparse
import ipaddress
import pathlib
import re
import sys
import urllib.parse

import yaml


IMAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._/-]*:(?P<tag>[^:@]+)@sha256:[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(r"(?:REPLACE_|CHANGEME|EXAMPLE\.INVALID|PLACEHOLDER)", re.IGNORECASE)
SCHEDULE_PATTERN = re.compile(r"^\*-\*-\* (?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9] UTC$")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    return parser.parse_args()


def memory_bytes(value):
    match = re.fullmatch(r"([1-9][0-9]*)([kKmMgG])", value)
    if not match:
        return 0
    factors = {"k": 1024, "m": 1024**2, "g": 1024**3}
    return int(match.group(1)) * factors[match.group(2).lower()]


def is_placeholder(value):
    return isinstance(value, str) and bool(PLACEHOLDER_PATTERN.search(value))


def validate_image(check_id, image, errors):
    match = IMAGE_PATTERN.fullmatch(image)
    if is_placeholder(image) or not match:
        errors.append((check_id, "image must use a readable tag and immutable sha256 digest"))
        return
    tag = match.group("tag")
    if tag == "latest" or not any(character.isdigit() for character in tag):
        errors.append((check_id, "image tag must identify a reviewed version and cannot be latest"))


def validate_repository(platform, actual_paths, errors):
    check_id = "backup.repository.safe_off_host"
    backup = platform["backup"]
    repository = backup["restic_repository"]
    if backup["repository_mode"] == "local-development":
        if platform["environment_name"] != "test" or not backup["local_repository_risk_accepted"]:
            errors.append(("backup.repository.local_development", "local repository requires the test environment and explicit host-loss risk acceptance"))
            return
        repository_path = pathlib.PurePosixPath(repository)
        storage_root = pathlib.PurePosixPath(platform["host"]["storage_root"])
        excluded_paths = {
            pathlib.PurePosixPath(platform["docker"]["data_root"]),
            actual_paths["data_services.mariadb.data_path"],
            actual_paths["data_services.redis.data_path"],
            actual_paths["backup.staging_path"],
            pathlib.PurePosixPath(backup["restore"]["target_root"]),
        }
        if not repository_path.is_absolute() or storage_root not in repository_path.parents:
            errors.append(("backup.repository.local_path", "local repository must be an absolute child of the configured storage root"))
        if any(repository_path == path or repository_path in path.parents or path in repository_path.parents for path in excluded_paths):
            errors.append(("backup.repository.local_path", "local repository must not overlap data, staging, restore, or Docker roots"))
        if backup["repository_credential_secret_keys"]:
            errors.append(("backup.repository.local_credentials", "local repository must not declare provider credentials"))
        return
    if backup["repository_mode"] != "off-host":
        errors.append((check_id, "repository mode is unsupported"))
        return
    if is_placeholder(repository) or any(character.isspace() for character in repository):
        errors.append((check_id, "restic repository must be a real non-placeholder off-host location"))
        return
    if repository.startswith(("/", "file:", "local:")):
        errors.append((check_id, "restic repository must be off-host"))
        return
    scheme, separator, location = repository.partition(":")
    if not separator or scheme not in {"azure", "gs", "rclone", "rest", "s3", "sftp"}:
        errors.append((check_id, "restic repository type is unsupported or missing"))
        return
    candidate = location
    if scheme == "s3" and location.startswith(("http://", "https://")):
        candidate = location
    elif scheme == "rest":
        candidate = location
    parsed = urllib.parse.urlsplit(candidate) if "://" in candidate else None
    if parsed and (parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
        errors.append((check_id, "restic repository must not embed credentials, query values, or fragments"))


def validate_configuration(platform):
    errors = []
    data_services = platform["data_services"]
    mariadb = data_services["mariadb"]
    redis = data_services["redis"]
    backup = platform["backup"]
    host = platform["host"]

    try:
        bind_address = ipaddress.ip_address(data_services["bind_address"])
    except ValueError:
        errors.append(("data_services.bind_address.private", "bind address is not valid IPv4"))
    else:
        if bind_address.version != 4 or not bind_address.is_private or bind_address.is_loopback or bind_address.is_unspecified:
            errors.append(("data_services.bind_address.private", "bind address must be a specific non-loopback private IPv4 address"))
        if data_services["provisioning_mode"] == "helper-managed" and str(bind_address) != platform["host_address"]:
            errors.append(("data_services.bind_address.host_match", "bind address must match the configured host address"))

    for value in data_services["allowed_client_cidrs"]:
        try:
            network = ipaddress.ip_network(value, strict=True)
        except ValueError:
            errors.append(("data_services.allowed_client_cidrs.private", f"invalid client CIDR: {value}"))
            continue
        rfc1918 = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        )
        if network.version != 4 or network.prefixlen == 0 or not any(network.subnet_of(parent) for parent in rfc1918):
            errors.append(("data_services.allowed_client_cidrs.private", f"client CIDR must be restricted private IPv4: {value}"))

    development_profile = data_services["delivery_profile"] == "development"
    tls = data_services["tls"]
    if development_profile:
        if tls["enabled"]:
            errors.append(("data_services.tls.development_disabled", "TLS must be disabled for the development profile"))
        if data_services["systemd_supervision_enabled"]:
            errors.append(("data_services.systemd.development_disabled", "systemd supervision must be disabled for the development profile"))
        if backup["enabled"]:
            errors.append(("backup.development_disabled", "backup automation must be disabled for the development profile"))
    elif not tls["enabled"]:
        errors.append(("data_services.tls.required", "TLS must be enabled for the hardened profile"))
    if tls["enabled"]:
        if is_placeholder(tls["renewal_owner"]):
            errors.append(("data_services.tls.renewal_owner", "certificate renewal owner must be explicit"))
        secret_key_names = {
            tls["server_certificate_secret_key"],
            tls["server_private_key_secret_key"],
            tls["ca_certificate_secret_key"],
        }
        if len(secret_key_names) != 3 or any(is_placeholder(value) for value in secret_key_names):
            errors.append(("data_services.tls.secret_keys", "TLS secret key references must be distinct and non-placeholder"))

    validate_image("data_services.mariadb.image.pinned", mariadb["image"], errors)
    validate_image("data_services.redis.image.pinned", redis["image"], errors)
    for service_name, service in (("mariadb", mariadb), ("redis", redis)):
        review_values = [service["compatibility_rationale"], *service["image_scan"].values()]
        if any(is_placeholder(value) for value in review_values if isinstance(value, str)):
            errors.append((f"data_services.{service_name}.image_reviewed", "image compatibility and scan review must be recorded"))
    if mariadb["port"] == redis["port"]:
        errors.append(("data_services.ports.distinct", "MariaDB and Redis ports must differ"))
    reserved_ports = set(platform["network"]["public_ingress_ports"]) | {host["ssh_port"], 6443}
    if mariadb["port"] in reserved_ports or redis["port"] in reserved_ports:
        errors.append(("data_services.ports.unreserved", "data-service ports conflict with host platform ports"))
    if not redis["authentication_enabled"]:
        errors.append(("data_services.redis.authentication", "Redis authentication must be enabled"))
    if redis["maxmemory"] >= memory_bytes(redis["memory_limit"]):
        errors.append(("data_services.redis.memory_headroom", "Redis maxmemory must be below its container memory limit"))

    storage_root = pathlib.PurePosixPath(host["storage_root"])
    config_root = pathlib.PurePosixPath(host["config_root"])
    expected_paths = {
        "data_services.mariadb.data_path": storage_root / "data-services/mariadb/data",
        "data_services.mariadb.config_path": config_root / "data-services/mariadb",
        "data_services.redis.data_path": storage_root / "data-services/redis/data",
        "data_services.redis.config_path": config_root / "data-services/redis",
        "backup.staging_path": storage_root / "backup-staging",
    }
    actual_paths = {
        "data_services.mariadb.data_path": pathlib.PurePosixPath(mariadb["data_path"]),
        "data_services.mariadb.config_path": pathlib.PurePosixPath(mariadb["config_path"]),
        "data_services.redis.data_path": pathlib.PurePosixPath(redis["data_path"]),
        "data_services.redis.config_path": pathlib.PurePosixPath(redis["config_path"]),
        "backup.staging_path": pathlib.PurePosixPath(backup["staging_path"]),
    }
    for check_id, expected in expected_paths.items():
        if actual_paths[check_id] != expected:
            errors.append((check_id, f"path must be {expected}"))
    docker_root = pathlib.PurePosixPath(platform["docker"]["data_root"])
    if any(path == docker_root or docker_root in path.parents for key, path in actual_paths.items() if ".data_path" in key):
        errors.append(("data_services.paths.outside_docker", "service data paths must be outside Docker's data root"))

    if backup["enabled"]:
        validate_repository(platform, actual_paths, errors)
        if not SCHEDULE_PATTERN.fullmatch(backup["schedule"]):
            errors.append(("backup.schedule.daily_utc", "schedule must select an explicit daily UTC time"))
        if any(is_placeholder(value) for value in backup["repository_credential_secret_keys"]):
            errors.append(("backup.repository.secret_keys", "repository credential key names must be non-placeholder"))

    if backup["enabled"]:
        restore = backup["restore"]
        restore_target = pathlib.PurePosixPath(restore["target_root"])
        primary_paths = {actual_paths["data_services.mariadb.data_path"], actual_paths["data_services.redis.data_path"]}
        if restore_target == storage_root or storage_root not in restore_target.parents:
            errors.append(("backup.restore.target_isolated", "restore target must be a dedicated child of the storage root"))
        if any(restore_target == path or restore_target in path.parents or path in restore_target.parents for path in primary_paths):
            errors.append(("backup.restore.target_isolated", "restore target must not overlap primary service data"))
        try:
            restore_address = ipaddress.ip_address(restore["bind_address"])
        except ValueError:
            errors.append(("backup.restore.loopback_only", "restore bind address is invalid"))
        else:
            if not restore_address.is_loopback:
                errors.append(("backup.restore.loopback_only", "restore probes must bind only to loopback"))
        service_ports = {mariadb["port"], redis["port"]}
        restore_ports = {restore["mariadb_port"], restore["redis_port"]}
        if len(restore_ports) != 2 or service_ports & restore_ports:
            errors.append(("backup.restore.ports_isolated", "restore ports must be unique and distinct from primary ports"))

    return errors


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        errors = validate_configuration(platform)
    except (KeyError, TypeError, OSError, yaml.YAMLError) as exc:
        print(f"phase 3 configuration validation failed: invalid structured input ({type(exc).__name__})", file=sys.stderr)
        return 1
    if errors:
        print("Phase 3 configuration: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    print("Phase 3 configuration: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())