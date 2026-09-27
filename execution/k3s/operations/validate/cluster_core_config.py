#!/usr/bin/env python3
"""Validate Phase 5 cluster-core configuration without mutating the cluster."""

import argparse
import pathlib
import subprocess
import sys

import yaml


MEMORY_SUFFIXES = {"K": 1000, "M": 1000**2, "G": 1000**3}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--age-identity", type=pathlib.Path, required=True)
    return parser.parse_args()


def cpu_millicores(value):
    text = str(value)
    return int(text[:-1]) if text.endswith("m") else int(float(text) * 1000)


def memory_bytes(value):
    text = str(value)
    return int(text[:-1]) * MEMORY_SUFFIXES[text[-1].upper()]


def validate_configuration(platform, repository, actual_age_recipient=None):
    errors = []
    core = platform["cluster_core"]
    namespaces = core["namespaces"]
    active = {
        namespaces["platform"], namespaces["observability"],
        namespaces["backup"], namespaces["application"],
    }

    expected_application = {
        "test": "judge-test", "production": "judge-prod", "staging": "judge-staging",
    }.get(platform["environment_name"])
    if expected_application and namespaces["application"] != expected_application:
        errors.append(("cluster_core.namespaces.environment", f"application namespace must be {expected_application}"))
    if len(active) != 4:
        errors.append(("cluster_core.namespaces.unique", "active namespace names must be unique"))
    if active.intersection(namespaces["reserved"]):
        errors.append(("cluster_core.namespaces.reserved", "active and reserved namespaces must not overlap"))

    allowed_storage = set(core["storage"]["allowed_namespaces"])
    if allowed_storage != active:
        errors.append(("cluster_core.storage.scope", "local-path allowed namespaces must exactly match active managed namespaces"))

    identities = core["identities"]
    if identities["operator"]["name"] == identities["automation"]["name"]:
        errors.append(("cluster_core.identities.names", "operator and automation identity names must differ"))
    if identities["operator"]["group"] == identities["automation"]["group"]:
        errors.append(("cluster_core.identities.groups", "operator and automation groups must differ"))
    for identity_name, identity in identities.items():
        output = pathlib.PurePosixPath(identity["kubeconfig_output"])
        if output.is_absolute() or ".." in output.parts or ".generated" not in output.parts:
            errors.append((f"cluster_core.identities.{identity_name}.path", "kubeconfig must be repository-relative under an ignored .generated directory"))
            continue
        candidate = repository / pathlib.Path(*output.parts)
        ignored = subprocess.run(
            ["git", "-C", str(repository), "check-ignore", "--quiet", "--", str(candidate)],
            check=False,
        )
        if ignored.returncode != 0:
            errors.append((f"cluster_core.identities.{identity_name}.ignored", "kubeconfig output must be ignored by Git"))

    for quota_name, quota in core["quotas"].items():
        if cpu_millicores(quota["requests_cpu"]) > cpu_millicores(quota["limits_cpu"]):
            errors.append((f"cluster_core.quotas.{quota_name}.cpu", "CPU request quota must not exceed CPU limit quota"))
        if memory_bytes(quota["requests_memory"]) > memory_bytes(quota["limits_memory"]):
            errors.append((f"cluster_core.quotas.{quota_name}.memory", "memory request quota must not exceed memory limit quota"))
        if quota["persistentvolumeclaims"] == 0 and memory_bytes(quota["requests_storage"]) > 0:
            errors.append((f"cluster_core.quotas.{quota_name}.storage", "storage quota requires at least one permitted PVC"))

    limits = core["limits"]
    if cpu_millicores(limits["default_request_cpu"]) > cpu_millicores(limits["default_cpu"]):
        errors.append(("cluster_core.limits.cpu", "default CPU request must not exceed the default limit"))
    if memory_bytes(limits["default_request_memory"]) > memory_bytes(limits["default_memory"]):
        errors.append(("cluster_core.limits.memory", "default memory request must not exceed the default limit"))

    if actual_age_recipient and core["secret_delivery"]["age_recipient"] != actual_age_recipient:
        errors.append(("cluster_core.secret_delivery.recipient", "configured age recipient does not match the controller identity"))
    return errors


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        result = subprocess.run(
            ["age-keygen", "-y", str(args.age_identity)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("age-keygen could not read the controller identity")
        errors = validate_configuration(platform, args.repository.resolve(), result.stdout.strip())
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, yaml.YAMLError) as exc:
        print(f"Phase 5 configuration: fail ({exc})", file=sys.stderr)
        return 1
    if errors:
        print("Phase 5 configuration: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    print("Phase 5 configuration: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())