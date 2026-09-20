# Phase 3 Host Data Services Progress

Status: development profile complete

Last updated: 2026-09-20

This document records verified Phase 3 implementation facts. The normative requirements
remain in [phase-3-host-data-services.md](../phase-3-host-data-services.md).

## Scope Decision

On 2026-09-20, Phase 3 was narrowed to development enablement. Its purpose is to provide
repeatable disposable MariaDB and Redis containers that unblock the k3s layers. TLS,
strict per-service UID/GID and secret-directory isolation, systemd supervision, backup,
snapshot, restore, retention, disaster recovery, image-policy hardening, and external
allowed/denied network qualification are deferred and no longer block this phase.

The development completion gate is satisfied. The services remain containerized,
passwords remain SOPS-backed, listeners remain private/non-wildcard, and implicit data
deletion or adoption remains prohibited.

## Status Snapshot

- Phase 1, Phase 2, and the Phase 3 development profile pass on `192.168.1.151`.
- MariaDB `11.8.6` and Redis `8.2.4` image digests remain pinned.
- Authenticated plaintext MariaDB `SELECT 1` and Redis `PING` probes pass with redacted
  evidence; trailing newlines in imported passwords are normalized consistently.
- MariaDB listens on `192.168.1.151:3306`. Redis listens on
  `192.168.1.151:6379` and loopback, with no wildcard listener for either service.
- Managed file ownership matches the pinned image runtime identities. Redis health now
  requires exact `PONG` output rather than accepting authentication error output.
- Changed bind-mounted inputs force one Compose recreation. An unchanged setup is a
  no-op, preserving container identity and data.
- TLS, systemd, backup/restore, and external-source qualification are recorded as
  `not_applicable` for development. They remain mandatory production design work.
- `provisioning_mode` separates explicit helper-managed setup from externally managed
  production endpoints. Setup requires `--provision-host-services`.

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
  operations/certificates/
    generate-test-data-services
    README.md
  operations/data-services/
    data-services
    repair-test-permissions
    README.md
    test_data_services_helper.py
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

## Ownership Modes

The production contract is externally managed. MariaDB, Redis, restic/backup storage,
certificates, passwords, endpoint lifecycle, upgrades, recovery, and rotation are supplied
and operated outside this repository. Configure `provisioning_mode: external` with the
private connection details, CA, and least-privilege probe credentials. In this mode the
check flow owns only authenticated TLS health validation (`SELECT 1` and `PING`) and
redacted evidence; it skips local Compose, systemd, filesystem, UFW, backup, certificate,
credential, and service lifecycle management.

For test/development machines, `helper-managed` mode and the certificate/secret helpers
provide a fast bootstrap path. That convenience does not redefine production ownership.

## Validation Results

- Converging apply: `ok=34 changed=2 unreachable=0 failed=0 skipped=14`.
- Immediate repeated setup: `ok=33 changed=0 unreachable=0 failed=0 skipped=13`.
- Both runs reported `Phase 3 runtime services: pass` and
  `Phase 3 host data services: pass`.
- Before and after the second setup, MariaDB retained container ID prefix `5be94f022f8`
  and start time `2026-09-20T02:08:37.097934817Z`; Redis retained ID prefix
  `e7372267e4b` and start time `2026-09-20T02:08:37.095680955Z`.
- A temporary `phase3-repeatability` MariaDB marker survived the second setup and its
  acceptance database was removed afterward.
- Phase 2 remained clean at `ok=76 changed=0 failed=0 skipped=5` after Phase 3 firewall
  rules were installed.
- Focused schema, configuration, secret, and runtime tests passed 27 tests; focused
  runtime/report tests passed 9 tests; Ansible syntax validation passed.

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

## Apply Preconditions

Before Phase 3 apply, provide or approve all of the following without sending secret
values through chat:

- confirmed recovery-console access; and
- explicit disposition of existing services, containers, configuration, and target paths.

The current test-only choices are a disposable Redis policy, a local restic repository,
and test-controller PKI. They must not be promoted to production unchanged.

## Operator Commands

```bash
# Non-mutating configuration and live-service validation
./execution/k3s/operations/data-services/data-services check --environment test

# Explicit test-host provisioning through the ordered Ansible phases
./execution/k3s/operations/data-services/data-services setup \
  --environment test --provision-host-services

# Recover original test-host Redis mount ownership without deleting data
./execution/k3s/operations/data-services/repair-test-permissions \
  --environment test --apply-permission-repair
```

For production endpoints set `data_services.provisioning_mode: external`, supply the
connection/TLS/probe credential contract externally, and run only the check command. The
external mode skips local Compose, systemd, filesystem, firewall, backup/restic,
certificate, password, and service lifecycle ownership.

## Remaining Work

Production hardening remains separate: TLS and certificate rotation, dedicated
least-privilege probes, systemd supervision, off-host backup and restore rehearsal,
image-policy remediation, and allowed/denied external network qualification. None of
these deferred controls is implied by development-profile completion.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-19 | Added the complete Phase 3 schema shape and explicit blocked test inputs. | Focused platform schema suite passed, 7 tests. |
| 2026-09-19 | Added semantic and encrypted-secret gates, public dispatch, guarded host role, offline rendering, and redacted convergence evidence. | Full unit suite passed; Phase 1 and Phase 2 public checks remained clean; direct Phase 3 check mode passed with zero changes. |
| 2026-09-19 | Added locked logical backup, conditional retention, snapshot verification, marker-based isolated restore, lifecycle evidence, and failure-path safety regressions. | Rendered script syntax, 8 focused safety tests, all playbook syntax checks, and the then-current 40-test suite passed. |
| 2026-09-19 | Configured the test host address, pinned and scanned current service images, added a bounded local-restic exception, and added renewable test PKI with SOPS import. | Semantic and encrypted-secret validation passed; certificate chain/SAN and image command compatibility passed; public Phase 3 check reached `ok=14 changed=0 failed=0 skipped=28`. |
| 2026-09-19 | Split optional helper-managed provisioning from external service validation and added authenticated TLS protocol probes with redacted evidence. | Focused provisioning, credential, runtime, report, and helper tests passed; absent services produce explicit MariaDB and Redis runtime failures. |
| 2026-09-20 | Ran the first helper-managed apply and diagnosed runtime failures. Added a guarded permission-repair helper and corrected Phase 2 UFW validation to coexist with later-phase rules. | Redis starts after permission repair; Phase 2 check passes with `ok=76 changed=0 failed=0 skipped=5`; Phase 3 remains blocked on Redis and MariaDB authentication behavior. |
| 2026-09-20 | Narrowed Phase 3 to repeatable disposable development services; deferred TLS, strict identity isolation, systemd, backup/restore, and external network qualification. | Documentation gate updated; functional convergence and repeatability remain to be proven. |
| 2026-09-20 | Completed authenticated plaintext development services, strict health output checks, conditional evidence, and change-triggered Compose lifecycle. | Apply passed; second setup had `changed=0`; container identities and start times were stable; MariaDB marker persisted; both protocol probes and private-listener checks passed. |