#!/usr/bin/env python3
"""Validate controller inputs and write the Phase 1 evidence report."""

import argparse
import datetime as dt
import ipaddress
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request

import yaml
from jsonschema import Draft202012Validator


MANAGED_K3S_INTERFACES = {"cni0", "flannel.1"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--environment-dir", type=pathlib.Path, required=True)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    return parser.parse_args()


class Report:
    def __init__(self):
        self.started = dt.datetime.now(dt.timezone.utc)
        self.checks = []
        self.facts = {}

    def add(self, check_id, status, evidence, remediation):
        self.checks.append({"id": check_id, "status": status, "evidence": evidence, "remediation": remediation})

    def write(self, args, connection_mode, repository):
        finished = dt.datetime.now(dt.timezone.utc)
        failed = any(check["status"] == "fail" for check in self.checks)
        report = {
            "schema_version": "1",
            "phase": "phase-1-preflight",
            "started_at": self.started.isoformat().replace("+00:00", "Z"),
            "finished_at": finished.isoformat().replace("+00:00", "Z"),
            "repository": repository,
            "environment": args.environment,
            "connection_mode": connection_mode,
            "facts": self.facts,
            "checks": self.checks,
            "overall_status": "fail" if failed else "pass",
            "remote_checks": "not_implemented",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Phase 1 preflight: {report['overall_status']}")
        print(f"Report: {args.report}")
        return 1 if failed else 0


def read_yaml(path, report, check_id):
    if not path.is_file():
        report.add(check_id, "fail", f"missing file: {path.name}", f"Create {path.name} from the environment example.")
        return None
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        report.add(check_id, "fail", f"could not parse {path.name}: {type(exc).__name__}", f"Fix the YAML syntax in {path.name}.")
        return None


def check_inventory(inventory, report):
    if isinstance(inventory, dict) and isinstance(inventory.get("all"), dict):
        platform_group = inventory["all"].get("children", {}).get("platform_host", {})
    else:
        platform_group = inventory.get("platform_host", {}) if isinstance(inventory, dict) else {}
    hosts = platform_group.get("hosts", {}) if isinstance(platform_group, dict) else platform_group
    if isinstance(hosts, (list, dict)) and len(hosts) == 1:
        report.add("inventory.single_platform_host", "pass", "exactly one platform_host is configured", "")
    else:
        report.add("inventory.single_platform_host", "fail", "platform_host must contain exactly one host", "Define one platform_host with connection settings.")


def check_controller_commands(connection_mode, report):
    required = ["bash", "python3", "ansible-playbook", "ansible-galaxy", "ip"]
    if connection_mode == "ssh":
        required.append("ssh")
    commands = {}
    for command in required + ["sops", "age"]:
        path = shutil.which(command)
        commands[command] = path
        remediation = f"Install {command} on the controller."
        if command in ("sops", "age"):
            remediation = f"Install {command}; secrets must remain encrypted."
        report.add(f"controller.command.{command}", "pass" if path else "fail", path or "not found", remediation)
    return commands


def check_collections(requirements_path, report, ansible_galaxy):
    try:
        requirements = yaml.safe_load(requirements_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        report.add("controller.collections.pinned", "fail", f"could not read requirements: {type(exc).__name__}", "Restore host/requirements.yml.")
        return
    if not ansible_galaxy:
        report.add("controller.collections.pinned", "fail", "not checked because ansible-galaxy is unavailable", "Install ansible-core and the pinned collections from host/requirements.yml.")
        return
    result = subprocess.run([ansible_galaxy, "collection", "list", "--format", "json"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        report.add("controller.collections.pinned", "fail", "ansible-galaxy could not list installed collections", "Install the pinned collections from host/requirements.yml.")
        return
    try:
        installed_locations = json.loads(result.stdout)
    except json.JSONDecodeError:
        report.add("controller.collections.pinned", "fail", "ansible-galaxy returned invalid JSON", "Use a supported ansible-galaxy version.")
        return
    installed = {}
    for collection_root in installed_locations.values():
        for name, versions in collection_root.items():
            if name in installed:
                continue
            if isinstance(versions, dict):
                installed[name] = versions.get("version")
            elif isinstance(versions, list) and versions:
                installed[name] = versions[0].get("version")
    mismatches = []
    for requirement in requirements.get("collections", []):
        expected = str(requirement["version"])
        installed_name = requirement.get("installed_name", requirement["name"])
        actual = installed.get(installed_name)
        if actual != expected:
            mismatches.append(f"{installed_name} expected {expected}, found {actual or 'missing'}")
    if mismatches:
        report.add("controller.collections.pinned", "fail", "; ".join(mismatches), "Install the exact versions listed in host/requirements.yml.")
    else:
        report.add("controller.collections.pinned", "pass", "all required collections match pinned versions", "")


def check_secrets(environment_dir, report, sops_command):
    secret_path = environment_dir / "secrets.sops.yml"
    if not secret_path.is_file():
        report.add("secrets.encrypted", "fail", "missing secrets.sops.yml", "Create an encrypted SOPS file; do not commit plaintext secrets.")
        return

    secret_text = secret_path.read_text(encoding="utf-8", errors="replace")
    encrypted = "sops:" in secret_text and "ENC[" in secret_text
    report.add("secrets.encrypted", "pass" if encrypted else "fail", "SOPS metadata detected" if encrypted else "file is not recognizably encrypted", "Encrypt the required secret values with SOPS and age.")
    if not encrypted:
        return

    if not sops_command:
        report.add("secrets.decryptable", "fail", "not checked because sops is unavailable", "Install SOPS and provide the matching age identity.")
        return
    decrypted = subprocess.run([sops_command, "--decrypt", str(secret_path)], capture_output=True, text=True, check=False)
    if decrypted.returncode != 0:
        report.add("secrets.decryptable", "fail", "SOPS could not decrypt the environment secret file", "Provide the matching age identity to SOPS.")
        return
    report.add("secrets.decryptable", "pass", "SOPS decryption succeeded", "")

    try:
        values = yaml.safe_load(decrypted.stdout)
    except yaml.YAMLError:
        report.add("secrets.required_keys", "fail", "decrypted secret document is invalid YAML", "Repair the encrypted secret document.")
        return
    required_keys = {
        "mariadb_root_password",
        "redis_password",
        "restic_password",
        "data_services_tls_certificate",
        "data_services_tls_private_key",
        "data_services_ca_certificate",
        "k3s_token_policy",
    }
    missing = sorted(required_keys - set(values) if isinstance(values, dict) else required_keys)
    if missing:
        report.add("secrets.required_keys", "fail", f"missing {len(missing)} required secret keys", "Add the missing keys without printing their values.")
    else:
        report.add("secrets.required_keys", "pass", "all required secret keys are present", "")


def local_ipv4_networks(ip_command):
    if not ip_command:
        return [], "ip is unavailable"
    result = subprocess.run([ip_command, "-4", "-o", "addr", "show"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return [], "ip could not list local IPv4 addresses"
    networks = []
    for line in result.stdout.splitlines():
        fields = line.split()
        try:
            if fields[1].rstrip(":") in MANAGED_K3S_INTERFACES:
                continue
            address = ipaddress.ip_interface(fields[3])
            networks.append(address)
        except (IndexError, ValueError):
            continue
    return networks, ""


def local_ipv4_routes(ip_command):
    if not ip_command:
        return [], "ip is unavailable"
    result = subprocess.run([ip_command, "-4", "route", "show"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return [], "ip could not list local IPv4 routes"
    return [line.strip() for line in result.stdout.splitlines() if line.strip()], ""


def check_network(platform, report, ip_command):
    network = platform.get("network", {}) if isinstance(platform, dict) else {}
    try:
        host_address = ipaddress.ip_address(platform["host_address"])
        pod_network = ipaddress.ip_network(network["pod_cidr"])
        service_network = ipaddress.ip_network(network["service_cidr"])
        administrative_networks = [ipaddress.ip_network(value) for value in network["administrative_cidrs"]]
        additional_networks = [ipaddress.ip_network(value) for value in network.get("additional_cidrs", [])]
    except (KeyError, ValueError) as exc:
        report.add("network.cidr.valid", "fail", f"invalid network configuration: {type(exc).__name__}", "Correct the configured IPv4 addresses and CIDRs.")
        return

    if pod_network.overlaps(service_network):
        report.add("network.cidr.no_overlap", "fail", "pod and service CIDRs overlap", "Choose non-overlapping pod and service CIDRs.")
    else:
        report.add("network.cidr.no_overlap", "pass", "pod and service CIDRs do not overlap", "")

    local_interfaces, error = local_ipv4_networks(ip_command)
    if error:
        report.add("network.interfaces.readable", "fail", error, "Install iproute2 and ensure local interface facts are readable.")
        return
    report.add("network.interfaces.readable", "pass", f"found {len(local_interfaces)} local IPv4 interfaces", "")
    report.facts["network"] = {
        "local_ipv4_interfaces": [str(interface) for interface in local_interfaces],
        "host_address": str(host_address),
        "pod_cidr": str(pod_network),
        "service_cidr": str(service_network),
    }
    routes, route_error = local_ipv4_routes(ip_command)
    if route_error:
        report.add("network.routes.readable", "fail", route_error, "Install iproute2 and ensure local route facts are readable.")
    else:
        report.facts["network"]["local_ipv4_routes"] = routes
        report.add("network.routes.readable", "pass", f"found {len(routes)} local IPv4 routes", "")
        if network.get("outbound_https_endpoints") and not any(route.split()[0] == "default" for route in routes):
            report.add("network.default_route.present", "fail", "no IPv4 default route is configured", "Provide a route for the configured outbound HTTPS endpoints.")
        else:
            report.add("network.default_route.present", "pass", "default route requirement satisfied", "")

    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    report.facts["host"] = {"hostname": hostname, "fqdn": fqdn}
    configured_fqdn = platform.get("host_fqdn")
    if configured_fqdn in ("localhost", hostname, fqdn):
        report.add("host.hostname.consistent", "pass", f"configured {configured_fqdn}, detected {hostname}", "")
    else:
        report.add("host.hostname.consistent", "warning", f"configured {configured_fqdn}, detected {hostname}", "Review the hostname mismatch; Phase 1 does not change host identity.")
    if any(interface.ip == host_address for interface in local_interfaces):
        report.add("host.address.assigned", "pass", str(host_address), "")
    else:
        report.add("host.address.assigned", "fail", f"{host_address} is not assigned locally", "Set host_address to an address assigned to this machine.")

    conflicts = []
    for interface in local_interfaces:
        if interface.network.overlaps(pod_network) or interface.network.overlaps(service_network):
            conflicts.append(str(interface.network))
    for configured in administrative_networks + additional_networks:
        if configured.overlaps(pod_network) or configured.overlaps(service_network):
            conflicts.append(str(configured))
    if conflicts:
        report.add("network.cidr.no_local_overlap", "fail", ", ".join(sorted(set(conflicts))), "Choose pod and service CIDRs that do not overlap local or configured networks.")
    else:
        report.add("network.cidr.no_local_overlap", "pass", "pod and service CIDRs do not overlap configured local networks", "")

    dns_failures = []
    for name in network.get("dns_names", []):
        try:
            socket.getaddrinfo(name, None)
        except socket.gaierror:
            dns_failures.append(name)
    if dns_failures:
        report.add("network.dns.resolves", "fail", ", ".join(dns_failures), "Correct DNS or remove unreachable names from the environment contract.")
    else:
        report.add("network.dns.resolves", "pass", f"resolved {len(network.get('dns_names', []))} configured names", "")

    https_failures = []
    for endpoint in network.get("outbound_https_endpoints", []):
        try:
            with urllib.request.urlopen(endpoint, timeout=10) as response:
                if response.status < 200 or response.status >= 400:
                    https_failures.append(f"{endpoint} ({response.status})")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            https_failures.append(f"{endpoint} ({type(exc).__name__})")
    if https_failures:
        report.add("network.https.reachable", "fail", "; ".join(https_failures), "Verify outbound HTTPS access and the configured endpoint list.")
    else:
        report.add("network.https.reachable", "pass", f"reached {len(network.get('outbound_https_endpoints', []))} configured endpoints", "")


def repository_state(repository_path):
    try:
        commit = subprocess.run(["git", "-C", str(repository_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", str(repository_path), "status", "--porcelain"], capture_output=True, text=True, check=False).stdout != ""
        return {"commit": commit, "dirty_worktree": dirty}
    except OSError:
        return {"commit": None, "dirty_worktree": None}


def main():
    args = parse_args()
    report = Report()
    if not args.environment_dir.is_dir():
        report.add("environment.exists", "fail", f"unknown environment: {args.environment}", "Create the environment directory and its required input files.")
        return report.write(args, None, repository_state(args.repository))

    report.add("environment.exists", "pass", args.environment, "")
    inventory = read_yaml(args.environment_dir / "inventory.yml", report, "inventory.parse")
    platform = read_yaml(args.environment_dir / "platform.yml", report, "platform.parse")
    connection_mode = platform.get("target_connection", {}).get("mode") if isinstance(platform, dict) else None
    if platform is not None:
        try:
            schema = json.loads(args.schema.read_text(encoding="utf-8"))
            errors = sorted(Draft202012Validator(schema).iter_errors(platform), key=lambda error: list(error.path))
            if errors:
                details = "; ".join(".".join(map(str, error.path)) + ": " + error.message for error in errors[:5])
                report.add("platform.schema.valid", "fail", details, "Correct platform.yml to match platform.schema.json.")
            else:
                report.add("platform.schema.valid", "pass", "platform.yml conforms to the schema", "")
        except (OSError, json.JSONDecodeError) as exc:
            report.add("platform.schema.valid", "fail", f"schema unavailable: {type(exc).__name__}", "Restore the version-controlled platform schema.")
    if connection_mode in ("local", "ssh"):
        report.add("target_connection.mode.valid", "pass", connection_mode, "")
    else:
        report.add("target_connection.mode.valid", "fail", "target_connection.mode must be local or ssh", "Set target_connection.mode to local for the current single-machine workflow.")
    if inventory is not None:
        check_inventory(inventory, report)
    commands = check_controller_commands(connection_mode, report)
    if platform is not None:
        check_network(platform, report, commands["ip"])
    check_collections(args.environment_dir.parent.parent / "host" / "requirements.yml", report, commands["ansible-galaxy"])

    check_secrets(args.environment_dir, report, commands["sops"])
    return report.write(args, connection_mode, repository_state(args.repository))


if __name__ == "__main__":
    sys.exit(main())