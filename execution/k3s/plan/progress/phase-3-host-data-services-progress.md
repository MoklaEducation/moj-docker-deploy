# Phase 3 Host Data Services Progress

Status: implementation in progress; environment acceptance blocked on operator-owned inputs

Last updated: 2026-09-19

This document records verified Phase 3 implementation facts. The normative requirements
remain in [phase-3-host-data-services.md](../phase-3-host-data-services.md).

## Status Snapshot

- Phase 1 and Phase 2 remain the accepted prerequisite baseline.
- Phase 3 host mutation has not run.
- No MariaDB or Redis container, data directory, firewall rule, runtime secret, backup,
  or restore target has been created by Phase 3.
- The shared environment schema now contains the complete Phase 3 structural contract.
- Phase 3 check/apply dispatch, guarded Ansible desired state, lifecycle scripts, and
  redacted report writers are implemented and statically validated.
- Direct Ansible check mode passed with `ok=14 changed=0 failed=0 skipped=24`; it wrote
  only the requested controller facts file and skipped every host mutation.
- The public Phase 3 check stops before secret decryption and Phase 3 Ansible because
  operator-owned values remain intentionally blocked.
- Current blockers have stable IDs: `data_services.bind_address.private`,
  `data_services.tls.renewal_owner`, both `image.pinned` and `image_reviewed` checks, and
  `backup.repository.safe_off_host`.
- External allowed-source and denied-source test vantage points are not yet available.

## Implementation Inventory

```text
execution/k3s/
  bootstrap.sh
  environments/test/
    platform.yml
    platform.yml.example
    secrets.sops.yml.example
  host/
    playbooks/host-data-services.yml
    roles/data-services/
      defaults/main.yml
      handlers/main.yml
      tasks/*.yml
      templates/*
  operations/backup/
    backup
    test_backup_restore_safety.py
  operations/restore/
    restore
  operations/validate/
    data_services_config.py
    data_services_secrets.py
    data_services_report.py
    data_services_operation_report.py
    test_data_services_config.py
    test_data_services_secrets.py
    test_data_services_report.py
    test_data_services_operation_report.py
    test_platform_schema.py
    schemas/platform.schema.json
  plan/progress/phase-3-host-data-services-progress.md
```

The role owns precondition and adoption guards, offline rendering, separated filesystem
and secret roots, host-networked Compose services, exact UFW inputs, systemd lifecycle,
health checks, logical backup and retention ordering, and isolated restore cleanup.
Applications, databases, users, grants, schemas, k3s, and Kubernetes resources remain
outside this implementation.

## Validation Results

The complete explicit unit suite passed 40 tests. Python compilation, shell syntax,
inventory discovery, all three playbook syntax checks, controller dependency validation,
wrapper argument rejection, VS Code diagnostics, and `git diff --check` passed.

Public read-only results:

- Phase 1 check: exit `0`, `ok=16 changed=0 failed=0`.
- Phase 2 check: exit `0`, `ok=76 changed=0 failed=0 skipped=5`.
- Phase 3 public check: exit `1` at semantic validation, before secret decryption or
  Phase 3 Ansible, due only to the recorded operator placeholders.
- Direct Phase 3 role check for implementation validation: exit `0`,
  `ok=14 changed=0 failed=0 skipped=24`.
- Rendered backup, verification, and restore scripts passed `bash -n`.

Run static validation from a fresh shell:

```bash
cd /path/to/moj-docker-deploy
ENVIRONMENT="test"
K3S_DIR="$PWD/execution/k3s"
export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

./execution/k3s/operations/setup/controller.sh check
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT"
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-baseline
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-data-services
```

The last command is expected to fail until every operator blocker below is resolved.

## Operator Blockers

Before Phase 3 apply, provide or approve all of the following without sending secret
values through chat:

- a stable non-loopback private host address and reviewed allowed client CIDRs;
- reviewed MariaDB and Redis version tags, immutable digests, compatibility rationale,
  and image scan findings;
- a real off-host restic repository, provider credential key names, retention, schedule,
  and encryption-key custody;
- real MariaDB, Redis, restic, and TLS values in the ignored encrypted SOPS file;
- a valid service certificate and explicit renewal owner;
- measured Redis memory and accepted persistence semantics;
- external allowed and denied test vantage points;
- confirmed recovery-console access; and
- explicit disposition of existing services, containers, configuration, and target paths.

## Remaining Work

- Replace every blocked environment value through reviewed operator input and update the
  ignored encrypted SOPS document directly, never through chat.
- Run first apply, second apply, and final public check.
- Run real off-host backup, snapshot verification, marker-based isolated restore,
  systemd stop/start durability, overlapping-lock, and simulated upload-failure tests.
- Verify TLS/authenticated connectivity from an allowed external source and rejection
  from a denied external source.
- Record image scan results, evidence redaction scans, and exact first/second apply recaps.

No apply, image pull, container start, UFW mutation, secret installation, backup,
retention, restore, service stop/start, or external network test has been run in this
implementation session. Phase 3 environment acceptance remains blocked.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-19 | Added the complete Phase 3 schema shape and explicit blocked test inputs. | Focused platform schema suite passed, 7 tests. |
| 2026-09-19 | Added semantic and encrypted-secret gates, public dispatch, guarded host role, offline rendering, and redacted convergence evidence. | Full unit suite passed; Phase 1 and Phase 2 public checks remained clean; direct Phase 3 check mode passed with zero changes. |
| 2026-09-19 | Added locked logical backup, conditional retention, snapshot verification, marker-based isolated restore, lifecycle evidence, and failure-path safety regressions. | Rendered script syntax, 8 focused safety tests, all playbook syntax checks, and the 40-test suite passed. |