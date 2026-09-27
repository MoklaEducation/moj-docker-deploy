#!/usr/bin/env python3
"""Validate deterministic Phase 6 release configuration and rendered resources."""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import yaml


IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
DURATION = re.compile(r"^([1-9][0-9]*)h$")
NODE_AGENT_HOST_PATHS = {"/", "/proc", "/sys"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--releases", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path)
    return parser.parse_args()


def object_id(document):
    metadata = document.get("metadata", {})
    return document.get("kind", ""), metadata.get("namespace", ""), metadata.get("name", "")


def pod_specs(document):
    spec = document.get("spec", {})
    if document.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    if document.get("kind") in {"Deployment", "DaemonSet", "StatefulSet", "Job", "CronJob"}:
        template = spec.get("template", {}).get("spec", {})
        return [template] if template else []
    if document.get("kind") == "Pod":
        return [spec]
    return []


def enabled_release_names(platform):
    names = ["certificates"]
    if platform["cluster_addons"]["capabilities"]["metrics"]:
        names.extend(("metrics", "node_metrics"))
    return names


def node_agent_exception(document, spec):
    metadata = document.get("metadata", {})
    host_paths = {
        volume["hostPath"].get("path")
        for volume in spec.get("volumes", []) if volume.get("hostPath")
    }
    mounts = [
        mount for container in spec.get("containers", [])
        for mount in container.get("volumeMounts", []) if mount.get("name") in {"proc", "sys", "root"}
    ]
    return (
        document.get("kind") == "DaemonSet"
        and metadata.get("namespace") == "observability-agents"
        and metadata.get("name") == "node-exporter"
        and spec.get("hostNetwork") is True
        and spec.get("hostPID") is True
        and not spec.get("hostIPC", False)
        and host_paths == NODE_AGENT_HOST_PATHS
        and mounts
        and all(mount.get("readOnly") is True for mount in mounts)
    )


def validate(platform, releases, documents, repository):
    errors = []
    addons = platform["cluster_addons"]
    inventory = releases["releases"]
    release = inventory["certificates"]
    expected_namespace = addons["namespaces"]["certificates"]
    if release["name"] != "cert-manager" or release["namespace"] != expected_namespace:
        errors.append(("cluster_addons.release", "certificate release name or namespace differs from the contract"))
    release_names = enabled_release_names(platform)
    for release_name in release_names:
        item = inventory[release_name]
        if str(item["chart"]["version"]) not in item["chart"]["url"]:
            errors.append(("cluster_addons.chart.version", f"{release_name} chart URL does not contain the pinned version"))
        if not re.fullmatch(r"[0-9a-f]{64}", item["chart"]["sha256"]):
            errors.append(("cluster_addons.chart.sha256", f"{release_name} chart checksum is not SHA-256"))
        if not all(IMAGE.fullmatch(image) for image in item["images"].values()):
            errors.append(("cluster_addons.images", f"{release_name} inventory contains a mutable image"))

    identity_path = repository / pathlib.PurePosixPath(addons["identity"]["kubeconfig_output"])
    ignored = subprocess.run(
        ["git", "-C", str(repository), "check-ignore", "--quiet", str(identity_path)], check=False,
    ).returncode == 0
    if not ignored:
        errors.append(("cluster_addons.identity.ignored", "add-on kubeconfig output is not ignored by Git"))

    duration = DURATION.fullmatch(addons["certificates"]["duration"])
    renew_before = DURATION.fullmatch(addons["certificates"]["renew_before"])
    if not duration or not renew_before or int(renew_before.group(1)) >= int(duration.group(1)):
        errors.append(("cluster_addons.certificates.duration", "renew_before must be shorter than duration"))

    identifiers = [object_id(document) for document in documents]
    if len(identifiers) != len(set(identifiers)):
        errors.append(("cluster_addons.render.unique", "render contains duplicate object identities"))
    namespaces = {doc["metadata"]["name"]: doc for doc in documents if doc.get("kind") == "Namespace"}
    namespace = namespaces.get(expected_namespace, {})
    labels = namespace.get("metadata", {}).get("labels", {})
    if labels.get("pod-security.kubernetes.io/enforce") != "restricted":
        errors.append(("cluster_addons.render.pod_security", "certificate namespace must enforce restricted Pod Security"))
    if addons["capabilities"]["metrics"]:
        agent_namespace = namespaces.get(addons["namespaces"]["node_agents"], {})
        agent_labels = agent_namespace.get("metadata", {}).get("labels", {})
        if agent_labels.get("pod-security.kubernetes.io/enforce") != "privileged" or agent_labels.get("platform.mokla/security-exception") != "node-observability-host-access":
            errors.append(("cluster_addons.render.node_security", "node-agent namespace lacks its scoped host-access exception"))

    rendered_images = set()
    for document in documents:
        for spec in pod_specs(document):
            host_access = spec.get("hostNetwork") or spec.get("hostPID") or spec.get("hostIPC") or any(volume.get("hostPath") for volume in spec.get("volumes", []))
            if host_access and not node_agent_exception(document, spec):
                errors.append(("cluster_addons.render.host_access", f"{object_id(document)} requests host access"))
            pod_security = spec.get("securityContext", {})
            if pod_security.get("seccompProfile", {}).get("type") != "RuntimeDefault":
                errors.append(("cluster_addons.render.seccomp", f"{object_id(document)} lacks RuntimeDefault seccomp"))
            for container in spec.get("initContainers", []) + spec.get("containers", []):
                image = container.get("image", "")
                rendered_images.add(image)
                if not IMAGE.fullmatch(image):
                    errors.append(("cluster_addons.render.image", f"{object_id(document)} has mutable image {image}"))
                if not container.get("resources", {}).get("requests") or not container.get("resources", {}).get("limits"):
                    errors.append(("cluster_addons.render.resources", f"{object_id(document)} lacks resource bounds"))
                security = container.get("securityContext", {})
                if security.get("privileged") or security.get("allowPrivilegeEscalation") is not False:
                    errors.append(("cluster_addons.render.security", f"{object_id(document)} has unsafe container security"))

        if document.get("kind") in {"Prometheus", "Alertmanager"}:
            spec = document.get("spec", {})
            image = spec.get("image", "")
            rendered_images.add(image)
            if not IMAGE.fullmatch(image):
                errors.append(("cluster_addons.render.image", f"{object_id(document)} has mutable image {image}"))
            if not spec.get("resources", {}).get("requests") or not spec.get("resources", {}).get("limits"):
                errors.append(("cluster_addons.render.resources", f"{object_id(document)} lacks resource bounds"))

    allowed_images = {
        image for release_name in release_names for image in inventory[release_name]["images"].values()
    } | {platform["cluster_core"]["smoke_image"]}
    if not rendered_images.issubset(allowed_images):
        errors.append(("cluster_addons.render.inventory", "rendered workload images differ from the release inventory"))

    certificates = [doc for doc in documents if doc.get("kind") == "Certificate" and doc.get("metadata", {}).get("name") == "phase6-test-tls"]
    ingresses = [doc for doc in documents if doc.get("kind") == "Ingress" and doc.get("metadata", {}).get("name") == "certificate-smoke"]
    expected = addons["certificates"]
    if len(certificates) != 1 or certificates[0].get("spec", {}).get("dnsNames") != [expected["hostname"]] or certificates[0].get("spec", {}).get("duration") != expected["duration"] or certificates[0].get("spec", {}).get("renewBefore") != expected["renew_before"]:
        errors.append(("cluster_addons.render.certificate", "test Certificate differs from platform.yml"))
    if len(ingresses) != 1 or ingresses[0].get("spec", {}).get("ingressClassName") != expected["ingress_class"] or ingresses[0].get("spec", {}).get("rules", [{}])[0].get("host") != expected["hostname"]:
        errors.append(("cluster_addons.render.ingress", "test Ingress differs from platform.yml"))
    return errors


def build_facts(rendered, releases, documents):
    inventory = releases["releases"]
    return {
        "rendered_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "object_count": len(documents),
        "charts": {
            name: {"name": release["name"], "version": release["chart"]["version"], "sha256": release["chart"]["sha256"]}
            for name, release in inventory.items()
        },
        "images": {name: release["images"] for name, release in inventory.items()},
        "managed_objects": [
            {"kind": kind, "namespace": namespace or None, "name": name}
            for kind, namespace, name in sorted(object_id(document) for document in documents)
        ],
    }


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        releases = yaml.safe_load(args.releases.read_text(encoding="utf-8"))
        rendered = args.manifest.read_text(encoding="utf-8")
        parseable = re.sub(r"(?m)^(\s*)- =$", r"\1- '='", rendered)
        documents = [document for document in yaml.safe_load_all(parseable) if document]
        errors = validate(platform, releases, documents, args.repository.resolve())
    except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError) as exc:
        print(f"Phase 6 render validation: fail ({exc})", file=sys.stderr)
        return 1
    if errors:
        print("Phase 6 render validation: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    facts = build_facts(rendered, releases, documents)
    if args.facts:
        args.facts.parent.mkdir(parents=True, exist_ok=True)
        args.facts.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 6 render validation: pass ({facts['object_count']} objects, {facts['rendered_sha256']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())