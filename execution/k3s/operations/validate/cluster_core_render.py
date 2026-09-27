#!/usr/bin/env python3
"""Render and validate Phase 5 Kustomize resources without cluster interaction."""

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

import yaml


ALLOWED_CLUSTER_KINDS = {"Namespace", "ClusterRole", "ClusterRoleBinding"}
REQUIRED_NAMESPACE_KINDS = {"ResourceQuota", "LimitRange", "NetworkPolicy", "RoleBinding"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=pathlib.Path, required=True)
    parser.add_argument("--overlay", type=pathlib.Path, required=True)
    parser.add_argument("--facts", type=pathlib.Path)
    return parser.parse_args()


def render_overlay(overlay):
    result = subprocess.run(
        ["k3s", "kubectl", "kustomize", str(overlay)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError(detail[0] if detail else "Kustomize render failed")
    return result.stdout


def object_id(document):
    metadata = document.get("metadata", {})
    return document.get("kind", ""), metadata.get("namespace", ""), metadata.get("name", "")


def quota_hard(quota):
    return {
        "requests.cpu": str(quota["requests_cpu"]),
        "requests.memory": str(quota["requests_memory"]),
        "limits.cpu": str(quota["limits_cpu"]),
        "limits.memory": str(quota["limits_memory"]),
        "pods": str(quota["pods"]),
        "persistentvolumeclaims": str(quota["persistentvolumeclaims"]),
        "local-path.storageclass.storage.k8s.io/requests.storage": str(quota["requests_storage"]),
    }


def validate_documents(documents, platform):
    errors = []
    core = platform["cluster_core"]
    namespaces = core["namespaces"]
    expected_namespaces = {
        namespaces["platform"], namespaces["observability"],
        namespaces["backup"], namespaces["application"],
    }
    identifiers = [object_id(document) for document in documents]
    if len(identifiers) != len(set(identifiers)):
        errors.append(("cluster_core.render.unique", "render contains duplicate resource identities"))

    rendered_namespaces = {
        document["metadata"]["name"] for document in documents if document.get("kind") == "Namespace"
    }
    if rendered_namespaces != expected_namespaces:
        errors.append(("cluster_core.render.namespaces", "rendered namespaces do not match the active environment contract"))

    objects_by_namespace = {namespace: set() for namespace in expected_namespaces}
    quota_roles = {
        namespaces["platform"]: "platform",
        namespaces["observability"]: "observability",
        namespaces["backup"]: "backup",
        namespaces["application"]: "application",
    }
    for document in documents:
        kind, namespace, name = object_id(document)
        metadata = document.get("metadata", {})
        labels = metadata.get("labels", {})
        if labels.get("app.kubernetes.io/managed-by") != core["managed_by"]:
            errors.append(("cluster_core.render.managed_label", f"{kind}/{name} lacks the managed-by label"))
        if kind in {"Secret", "CustomResourceDefinition"}:
            errors.append(("cluster_core.render.forbidden_kind", f"{kind}/{name} is not owned by Phase 5"))
        if not namespace and kind not in ALLOWED_CLUSTER_KINDS:
            errors.append(("cluster_core.render.cluster_scope", f"cluster-scoped {kind}/{name} is not allowlisted"))
        if namespace in objects_by_namespace:
            objects_by_namespace[namespace].add(kind)

        if kind == "Namespace":
            for mode in ("enforce", "audit", "warn"):
                if labels.get(f"pod-security.kubernetes.io/{mode}") != core["pod_security"][mode]:
                    errors.append(("cluster_core.render.pod_security", f"Namespace/{name} has incorrect {mode} policy"))
            if name == namespaces["application"] and labels.get("app.kubernetes.io/part-of") != core["application_umbrella"]:
                errors.append(("cluster_core.render.application_label", f"Namespace/{name} lacks the application umbrella label"))

        if kind == "ResourceQuota" and namespace in quota_roles:
            actual = {key: str(value) for key, value in document.get("spec", {}).get("hard", {}).items()}
            expected = quota_hard(core["quotas"][quota_roles[namespace]])
            if actual != expected:
                errors.append(("cluster_core.render.quota", f"ResourceQuota/{namespace}/{name} differs from platform.yml"))

        if kind == "LimitRange" and namespace in expected_namespaces:
            entries = document.get("spec", {}).get("limits", [])
            expected_limits = core["limits"]
            expected = {
                "defaultRequest": {
                    "cpu": str(expected_limits["default_request_cpu"]),
                    "memory": str(expected_limits["default_request_memory"]),
                },
                "default": {
                    "cpu": str(expected_limits["default_cpu"]),
                    "memory": str(expected_limits["default_memory"]),
                },
            }
            if len(entries) != 1 or entries[0].get("type") != "Container" or any(entries[0].get(key) != value for key, value in expected.items()):
                errors.append(("cluster_core.render.limits", f"LimitRange/{namespace}/{name} differs from platform.yml"))

        if kind in {"ClusterRole", "Role"}:
            for rule in document.get("rules", []):
                resources = set(rule.get("resources", []))
                if "secrets" in resources or "customresourcedefinitions" in resources or "nodes" in resources and set(rule.get("verbs", [])) - {"get", "list", "watch"}:
                    errors.append(("cluster_core.render.rbac", f"{kind}/{name} contains forbidden permissions"))

    for namespace, kinds in objects_by_namespace.items():
        missing = REQUIRED_NAMESPACE_KINDS - kinds
        if missing:
            errors.append(("cluster_core.render.namespace_policy", f"{namespace} lacks: {', '.join(sorted(missing))}"))
        policies = [
            document for document in documents
            if document.get("kind") == "NetworkPolicy" and document.get("metadata", {}).get("namespace") == namespace
        ]
        names = {document["metadata"]["name"] for document in policies}
        if not {"default-deny", "allow-dns"}.issubset(names):
            errors.append(("cluster_core.render.network", f"{namespace} lacks default-deny or DNS policy"))
    return errors


def build_facts(rendered, documents):
    return {
        "rendered_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "object_count": len(documents),
        "managed_objects": [
            {"kind": kind, "namespace": namespace or None, "name": name}
            for kind, namespace, name in sorted(object_id(document) for document in documents)
        ],
    }


def main():
    args = parse_args()
    try:
        platform = yaml.safe_load(args.platform.read_text(encoding="utf-8"))
        first = render_overlay(args.overlay)
        second = render_overlay(args.overlay)
        if first != second:
            raise RuntimeError("two renders from identical inputs differ")
        documents = [document for document in yaml.safe_load_all(first) if document]
        errors = validate_documents(documents, platform)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, yaml.YAMLError) as exc:
        print(f"Phase 5 render validation: fail ({exc})", file=sys.stderr)
        return 1
    if errors:
        print("Phase 5 render validation: fail", file=sys.stderr)
        for check_id, message in errors:
            print(f"{check_id}: {message}", file=sys.stderr)
        return 1
    facts = build_facts(first, documents)
    if args.facts:
        args.facts.parent.mkdir(parents=True, exist_ok=True)
        args.facts.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Phase 5 render validation: pass ({facts['object_count']} objects, {facts['rendered_sha256']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())