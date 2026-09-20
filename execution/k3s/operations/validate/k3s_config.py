#!/usr/bin/env python3
"""Validate Phase 4 k3s configuration without mutating the host."""

import argparse
import ipaddress
import pathlib
import re
import subprocess
import sys

import yaml


VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+\+k3s\d+$")
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(r"(?:REPLACE_|CHANGEME|PLACEHOLDER|LATEST|STABLE)", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    return parser.parse_args()


def paths_overlap(left, right):
    return left == right or left in right.parents or right in left.parents


def validate_configuration(platform, repository):
    errors = []
    k3s = platform["k3s"]

    if PLACEHOLDER_PATTERN.search(k3s["version"]) or not VERSION_PATTERN.fullmatch(k3s["version"]):
        errors.append(("k3s.version.pinned", "version must be an exact vX.Y.Z+k3sN release"))
    if not CHECKSUM_PATTERN.fullmatch(k3s["checksum"]):
        errors.append(("k3s.checksum.valid", "checksum must be a lowercase SHA-256 value"))

    addresses = {}
    for field in ("node_ip", "api_bind_address"):
        try:
            address = ipaddress.ip_address(k3s[field])
        except ValueError:
            errors.append((f"k3s.{field}.valid", f"{field} must be a valid IPv4 address"))
            continue
        addresses[field] = address
        if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback:
            errors.append((f"k3s.{field}.assigned", f"{field} must be a specific non-loopback IPv4 address"))
        if str(address) != platform["host_address"]:
            errors.append((f"k3s.{field}.host_match", f"{field} must match host_address"))

    try:
        cluster_network = ipaddress.ip_network(k3s["cluster_cidr"], strict=True)
        service_network = ipaddress.ip_network(k3s["service_cidr"], strict=True)
        cluster_dns = ipaddress.ip_address(k3s["cluster_dns"])
    except ValueError:
        errors.append(("k3s.network.valid", "cluster CIDR, service CIDR, and cluster DNS must be canonical IPv4 values"))
    else:
        if cluster_network.version != 4 or service_network.version != 4 or cluster_network.overlaps(service_network):
            errors.append(("k3s.network.disjoint", "cluster and service CIDRs must be disjoint IPv4 networks"))
        if k3s["cluster_cidr"] != platform["network"]["pod_cidr"] or k3s["service_cidr"] != platform["network"]["service_cidr"]:
            errors.append(("k3s.network.frozen", "k3s CIDRs must match the Phase 1 network contract"))
        if cluster_dns not in service_network or cluster_dns == service_network.network_address:
            errors.append(("k3s.cluster_dns.service_cidr", "cluster DNS must be a usable address in the service CIDR"))

    tls_sans = k3s["tls_sans"]
    if platform["host_address"] not in tls_sans:
        errors.append(("k3s.tls_sans.host_address", "TLS SANs must contain host_address"))
    if any(value in {"0.0.0.0", "*"} or PLACEHOLDER_PATTERN.search(value) for value in tls_sans):
        errors.append(("k3s.tls_sans.safe", "TLS SANs must not contain wildcards, unspecified addresses, or placeholders"))

    storage_root = pathlib.PurePosixPath(platform["host"]["storage_root"])
    data_dir = pathlib.PurePosixPath(k3s["data_dir"])
    local_storage = pathlib.PurePosixPath(k3s["local_storage_path"])
    expected_root = storage_root / "k3s"
    if expected_root not in data_dir.parents or expected_root not in local_storage.parents:
        errors.append(("k3s.paths.storage_root", f"k3s paths must be children of {expected_root}"))
    if paths_overlap(data_dir, local_storage):
        errors.append(("k3s.paths.disjoint", "data_dir and local_storage_path must not overlap"))
    protected_paths = [
        pathlib.PurePosixPath(platform["docker"]["data_root"]),
        pathlib.PurePosixPath(platform["data_services"]["mariadb"]["data_path"]),
        pathlib.PurePosixPath(platform["data_services"]["redis"]["data_path"]),
    ]
    if any(paths_overlap(path, protected) for path in (data_dir, local_storage) for protected in protected_paths):
        errors.append(("k3s.paths.isolated", "k3s paths must not overlap Docker or data-service roots"))

    kubeconfig = pathlib.PurePosixPath(k3s["kubeconfig_output"])
    if kubeconfig.is_absolute() or ".." in kubeconfig.parts:
        errors.append(("k3s.kubeconfig.repository_relative", "kubeconfig output must be a repository-relative path without parent traversal"))
    else:
        candidate = repository / pathlib.Path(*kubeconfig.parts)
        ignored = subprocess.run(
            ["git", "-C", str(repository), "check-ignore", "--quiet", "--", str(candidate)],
            check=False,
        )
        if ignored.returncode != 0:
            errors.append(("k3s.kubeconfig.ignored", "kubeconfig output must be ignored by Git"))

    if not k3s["secrets_encryption"]:
        errors.append(("k3s.secrets_encryption.enabled", "secrets encryption must be enabled"))
    return errors


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        errors = validate_configuration(platform, args.repository.resolve())
    except (KeyError, TypeError, OSError, yaml.YAMLError) as exc:
        print(f"Phase 4 configuration: fail ({type(exc).__name__})", file=sys.stderr)
        return 1
    if errors:
        print("Phase 4 configuration: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    print("Phase 4 configuration: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())