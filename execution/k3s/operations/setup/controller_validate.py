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
    parser.add_argument("--python-requirements", type=pathlib.Path, required=True)
    parser.add_argument("--collection-requirements", type=pathlib.Path, required=True)
    return parser.parse_args()


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


def check_collections(path):
    requirements = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = subprocess.run(
        ["ansible-galaxy", "collection", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ["ansible-galaxy could not list installed collections"]
    installed = {}
    for collection_root in json.loads(result.stdout).values():
        for name, metadata in collection_root.items():
            if name in installed:
                continue
            if isinstance(metadata, dict):
                installed[name] = metadata.get("version")
            elif metadata:
                installed[name] = metadata[0].get("version")
    failures = []
    for requirement in requirements["collections"]:
        expected = str(requirement["version"])
        actual = installed.get(requirement["name"])
        if actual != expected:
            failures.append(f"{requirement['name']} expected {expected}, found {actual or 'missing'}")
    return failures


def main():
    args = parse_args()
    failures = check_python_requirements(args.python_requirements) + check_collections(args.collection_requirements)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("pinned Python dependencies and Ansible collections: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
