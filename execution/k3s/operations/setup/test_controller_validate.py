#!/usr/bin/env python3
"""Focused tests for independent controller dependency validation."""

import importlib.metadata
import importlib.util
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).with_name("controller_validate.py")
SPEC = importlib.util.spec_from_file_location("controller_validate", MODULE_PATH)
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class MissingDependencyTests(unittest.TestCase):
    def test_python_selection_excludes_matching_packages(self):
        versions = {"matching": "1.0", "outdated": "1.0"}

        def version(package):
            if package == "missing":
                raise importlib.metadata.PackageNotFoundError(package)
            return versions[package]

        with tempfile.TemporaryDirectory() as directory:
            requirements = pathlib.Path(directory) / "requirements.txt"
            requirements.write_text("matching==1.0\noutdated==2.0\nmissing==3.0\n", encoding="utf-8")
            with mock.patch.object(VALIDATE.importlib.metadata, "version", side_effect=version):
                failures = VALIDATE.check_python_requirements(requirements)

        self.assertEqual(2, len(failures))

    def test_collection_selection_excludes_matching_collections(self):
        installed = {"/collections": {"matching.collection": {"version": "1.0"}, "outdated.collection": {"version": "1.0"}}}
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps(installed))

        with tempfile.TemporaryDirectory() as directory:
            requirements = pathlib.Path(directory) / "requirements.yml"
            requirements.write_text(
                "collections:\n"
                "  - name: matching.collection\n    version: 1.0\n"
                "  - name: outdated.collection\n    version: 2.0\n"
                "  - name: missing.collection\n    version: 3.0\n",
                encoding="utf-8",
            )
            with mock.patch.object(VALIDATE.subprocess, "run", return_value=result):
                failures, missing = VALIDATE.inspect_collections(requirements)

        self.assertEqual(["outdated.collection", "missing.collection"], [item["name"] for item in missing])
        self.assertEqual(2, len(failures))

    def test_scm_collection_uses_installed_identity_and_clean_install_requirement(self):
        installed = {"/collections": {"k3s.orchestration": {"version": "1.2.1"}}}
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps(installed))

        with tempfile.TemporaryDirectory() as directory:
            requirements = pathlib.Path(directory) / "requirements.yml"
            requirements.write_text(
                "collections:\n"
                "  - name: https://github.com/k3s-io/k3s-ansible.git\n"
                "    type: git\n"
                "    version: 1.2.2\n"
                "    installed_name: k3s.orchestration\n",
                encoding="utf-8",
            )
            with mock.patch.object(VALIDATE.subprocess, "run", return_value=result):
                failures, missing = VALIDATE.inspect_collections(requirements)

        self.assertEqual(["k3s.orchestration expected 1.2.2, found 1.2.1"], failures)
        self.assertEqual(
            [{"name": "https://github.com/k3s-io/k3s-ansible.git", "type": "git", "version": "1.2.2"}],
            missing,
        )


if __name__ == "__main__":
    unittest.main()