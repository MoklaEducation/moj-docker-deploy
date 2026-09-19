#!/usr/bin/env python3
"""Validate pinned Python dependencies and Ansible collections."""

import argparse
import importlib.metadata
import json
import pathlib
import subprocess
import sys

import yaml


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-requirements", type=pathlib.Path)
    parser.add_argument("--collection-requirements", type=pathlib.Path)
    parser.add_argument("--write-missing-collection-requirements", type=pathlib.Path)
    args = parser.parse_args()
    if args.python_requirements is None and args.collection_requirements is None:
        parser.error("at least one requirements file is required")
    if args.write_missing_collection_requirements is not None and args.collection_requirements is None:
        parser.error("--write-missing-collection-requirements requires --collection-requirements")
    return args


def check_python_requirements(path):
    failures = []
    for line in path.read_text(encoding="utf-8").splitlines():
        package, separator, expected = line.partition("==")
        if not separator:
            continue
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"{package} expected {expected}, found missing")
            continue
        if actual != expected:
            failures.append(f"{package} expected {expected}, found {actual}")
    return failures


def inspect_collections(path):
    requirements = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        result = subprocess.run(
            ["ansible-galaxy", "collection", "list", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return [f"ansible-galaxy unavailable: {type(exc).__name__}"], None
    if result.returncode != 0:
        return ["ansible-galaxy could not list installed collections"], None
    installed = {}
    try:
        installed_locations = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ["ansible-galaxy returned invalid JSON"], None
    for collection_root in installed_locations.values():
        for name, metadata in collection_root.items():
            if name in installed:
                continue
            if isinstance(metadata, dict):
                installed[name] = metadata.get("version")
            elif metadata:
                installed[name] = metadata[0].get("version")
    failures = []
    missing = []
    for requirement in requirements["collections"]:
        expected = str(requirement["version"])
        actual = installed.get(requirement["name"])
        if actual != expected:
            failures.append(f"{requirement['name']} expected {expected}, found {actual or 'missing'}")
            missing.append(requirement)
    return failures, missing


def main():
    args = parse_args()
    failures = []
    if args.python_requirements is not None:
        failures.extend(check_python_requirements(args.python_requirements))
    if args.collection_requirements is not None:
        collection_failures, missing_collections = inspect_collections(args.collection_requirements)
        if args.write_missing_collection_requirements is not None:
            if missing_collections is None:
                failures.extend(collection_failures)
            else:
                args.write_missing_collection_requirements.write_text(
                    yaml.safe_dump({"collections": missing_collections}, sort_keys=False), encoding="utf-8"
                )
        else:
            failures.extend(collection_failures)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("pinned Python dependencies and Ansible collections: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
