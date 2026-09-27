#!/usr/bin/env python3
"""Static safety regressions for Phase 3 backup and restore workflows."""

import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
TEMPLATES = ROOT / "host/roles/data-services/templates"


class BackupRestoreSafetyTests(unittest.TestCase):
    def test_compose_uses_host_network_without_published_ports_or_named_volumes(self):
        text = (TEMPLATES / "compose.yml.j2").read_text(encoding="utf-8")
        self.assertEqual(2, text.count("network_mode: host"))
        self.assertNotIn("ports:", text)
        self.assertNotIn("\nvolumes:", text)

    def test_backup_is_logical_and_not_live_data_copy(self):
        text = (TEMPLATES / "mokla-data-backup.j2").read_text(encoding="utf-8")
        self.assertIn("mariadb-dump", text)
        self.assertIn("--single-transaction", text)
        self.assertNotIn("restic backup {{ data_services.mariadb.data_path", text)
        self.assertIn("mokla_restore_probe", text)
        self.assertIn("restore-marker.txt", text)

    def test_retention_follows_snapshot_verification(self):
        text = (TEMPLATES / "mokla-data-backup.j2").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)
        self.assertIn("flock --nonblock", text)
        self.assertLess(text.index('restic snapshots --json "$snapshot_id"'), text.index("restic forget"))
        self.assertLess(text.index("restic check"), text.index("restic forget"))

    def test_restore_requires_snapshot_marker_and_isolated_target(self):
        text = (TEMPLATES / "mokla-data-restore-test.j2").read_text(encoding="utf-8")
        self.assertIn('[[ "$snapshot" =~ ^[0-9a-f]+$ ]]', text)
        self.assertIn('[[ "$target" == "$restore_root"/*', text)
        self.assertIn(".mokla-isolated-restore", text)
        self.assertIn("sha256sum --check", text)
        self.assertIn("restored MariaDB marker does not match", text)

    def test_workflows_never_remove_primary_data_or_volumes(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in TEMPLATES.glob("*"))
        self.assertNotIn("down --volumes", combined)
        self.assertNotIn('rm -rf -- "$primary_', combined)

    def test_backup_credentials_are_not_mounted_into_service_containers(self):
        compose = (TEMPLATES / "compose.yml.j2").read_text(encoding="utf-8")
        backup = (TEMPLATES / "mokla-data-backup.j2").read_text(encoding="utf-8")
        self.assertIn("data_services_runtime_secret_root", compose)
        self.assertNotIn("data_services_backup_secret_root", compose)
        self.assertIn("data_services_backup_secret_root", backup)

    def test_restore_does_not_pass_passwords_in_host_arguments(self):
        restore = (TEMPLATES / "mokla-data-restore-test.j2").read_text(encoding="utf-8")
        self.assertNotIn("docker exec -e", restore)
        self.assertNotIn("MYSQL_PWD=", restore)

    def test_role_refuses_unmarked_non_empty_data(self):
        validate = (ROOT / "host/roles/data-services/tasks/validate.yml").read_text(encoding="utf-8")
        self.assertIn(".mokla-managed", validate)
        self.assertIn("Refuse unsafe Phase 3 adoption", validate)


if __name__ == "__main__":
    unittest.main()