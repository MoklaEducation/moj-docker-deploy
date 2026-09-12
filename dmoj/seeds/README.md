# Seed Data Folder

This folder stores database seed dumps for test-machine bootstrap.

Expected usage:
1. Generate a seed from a known-good running environment:
   - ./scripts/teststack/seed/test-seed-export
2. Bootstrap a test stack from that seed:
   - ./scripts/teststack/lifecycle/test-bootstrap

Notes:
- Seed files are ignored by git on purpose.
- Seed data may contain real user information. Handle and transfer securely.
