#!/usr/bin/env python3
"""Provision or validate restricted Phase 5 client-certificate kubeconfigs."""

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import time

import yaml


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ensure", "check"))
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--admin-kubeconfig", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(kubeconfig, *arguments, stdin=None, check=True):
    result = subprocess.run(
        ["k3s", "kubectl", "--kubeconfig", str(kubeconfig), *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(detail[0] if detail else f"kubectl exited {result.returncode}")
    return result


def load_admin_cluster(path):
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    context_name = document["current-context"]
    context = next(item["context"] for item in document["contexts"] if item["name"] == context_name)
    cluster = next(item["cluster"] for item in document["clusters"] if item["name"] == context["cluster"])
    return cluster["server"], cluster["certificate-authority-data"]


def output_path(repository, identity):
    return repository / pathlib.Path(*pathlib.PurePosixPath(identity["kubeconfig_output"]).parts)


def validate_kubeconfig(path, expected_name, expected_server, minimum_seconds=86400):
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("kubeconfig mode is not 0600")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if document.get("current-context") != expected_name:
        raise ValueError("kubeconfig current context does not match the identity")
    if len(document.get("clusters", [])) != 1 or document["clusters"][0]["cluster"].get("server") != expected_server:
        raise ValueError("kubeconfig server does not match the cluster")
    if len(document.get("users", [])) != 1 or document["users"][0].get("name") != expected_name:
        raise ValueError("kubeconfig user does not match the identity")
    user = document["users"][0].get("user", {})
    certificate = base64.b64decode(user.get("client-certificate-data", ""), validate=True)
    base64.b64decode(user.get("client-key-data", ""), validate=True)
    result = subprocess.run(
        ["openssl", "x509", "-inform", "PEM", "-checkend", str(minimum_seconds), "-noout"],
        input=certificate,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("client certificate is expired or near expiry")


def write_kubeconfig(path, name, server, ca_data, certificate, private_key):
    document = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "mokla", "cluster": {"server": server, "certificate-authority-data": ca_data}}],
        "users": [{"name": name, "user": {
            "client-certificate-data": base64.b64encode(certificate).decode("ascii"),
            "client-key-data": base64.b64encode(private_key).decode("ascii"),
        }}],
        "contexts": [{"name": name, "context": {"cluster": "mokla", "user": name}}],
        "current-context": name,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            yaml.safe_dump(document, stream, sort_keys=False)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def issue_identity(admin_kubeconfig, repository, identity, server, ca_data):
    name = identity["name"]
    csr_name = f"{name}-phase5"
    with tempfile.TemporaryDirectory(prefix="mokla-phase5-access-") as directory:
        key_path = pathlib.Path(directory) / "client.key"
        csr_path = pathlib.Path(directory) / "client.csr"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(key_path)],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["openssl", "req", "-new", "-key", str(key_path), "-out", str(csr_path), "-subj", f"/CN={name}/O={identity['group']}"],
            capture_output=True,
            check=True,
        )
        manifest = {
            "apiVersion": "certificates.k8s.io/v1",
            "kind": "CertificateSigningRequest",
            "metadata": {"name": csr_name},
            "spec": {
                "request": base64.b64encode(csr_path.read_bytes()).decode("ascii"),
                "signerName": "kubernetes.io/kube-apiserver-client",
                "expirationSeconds": identity["certificate_validity_days"] * 86400,
                "usages": ["client auth"],
            },
        }
        run(admin_kubeconfig, "delete", "certificatesigningrequest", csr_name, "--ignore-not-found=true", check=False)
        try:
            run(admin_kubeconfig, "create", "-f", "-", stdin=yaml.safe_dump(manifest, sort_keys=False))
            run(admin_kubeconfig, "certificate", "approve", csr_name)
            certificate = None
            for _ in range(30):
                response = json.loads(run(admin_kubeconfig, "get", "certificatesigningrequest", csr_name, "-o", "json").stdout)
                encoded = response.get("status", {}).get("certificate")
                if encoded:
                    certificate = base64.b64decode(encoded, validate=True)
                    break
                time.sleep(1)
            if not certificate:
                raise RuntimeError(f"certificate was not issued for {name}")
            path = output_path(repository, identity)
            write_kubeconfig(path, name, server, ca_data, certificate, key_path.read_bytes())
            validate_kubeconfig(path, name, server)
        finally:
            run(admin_kubeconfig, "delete", "certificatesigningrequest", csr_name, "--ignore-not-found=true", check=False)


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        server, ca_data = load_admin_cluster(args.admin_kubeconfig)
        statuses = {}
        for role, identity in platform["cluster_core"]["identities"].items():
            path = output_path(args.repository.resolve(), identity)
            try:
                validate_kubeconfig(path, identity["name"], server)
                status = "valid"
            except (OSError, TypeError, ValueError, yaml.YAMLError):
                if args.action == "check":
                    raise RuntimeError(f"{role} kubeconfig is missing, invalid, or near expiry")
                issue_identity(args.admin_kubeconfig, args.repository.resolve(), identity, server, ca_data)
                status = "issued"
            response = run(path, "auth", "whoami", "-o", "json")
            username = json.loads(response.stdout).get("status", {}).get("userInfo", {}).get("username")
            if username != identity["name"]:
                raise RuntimeError(f"{role} credential authenticated as an unexpected identity")
            statuses[role] = status
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"Phase 5 restricted access: fail ({exc})", file=sys.stderr)
        return 1
    print("Phase 5 restricted access: pass (" + ", ".join(f"{role}={status}" for role, status in sorted(statuses.items())) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())