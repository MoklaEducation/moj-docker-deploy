#!/usr/bin/env python3
"""Validate the Phase 5 encrypted Secret template without exposing plaintext."""

import argparse
import json
import pathlib
import subprocess
import sys

import yaml
from jsonschema import Draft202012Validator


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=pathlib.Path, required=True)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--sops", default="sops")
    return parser.parse_args()


def validate_source(source, schema, recipient, sops_command="sops"):
    encrypted = source.read_text(encoding="utf-8")
    if "ENC[" not in encrypted or "sops:" not in encrypted:
        raise ValueError("template is not recognizably SOPS-encrypted")
    if recipient not in encrypted:
        raise ValueError("template does not use the configured age recipient")
    result = subprocess.run(
        [sops_command, "--decrypt", "--output-type", "yaml", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("SOPS could not decrypt the template")
    document = yaml.safe_load(result.stdout)
    validator = Draft202012Validator(json.loads(schema.read_text(encoding="utf-8")))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        raise ValueError("decrypted template does not match the Secret source schema")
    if document["stringData"].get("replace_with_required_key") != "not-a-production-secret":
        raise ValueError("template must remain explicitly non-production")


def main():
    args = parse_args()
    try:
        validate_source(args.template, args.schema, args.recipient, args.sops)
    except (OSError, TypeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"Phase 5 secret template: fail ({exc})", file=sys.stderr)
        return 1
    print("Phase 5 secret template: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())