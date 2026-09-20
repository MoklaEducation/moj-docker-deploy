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

## Ownership Modes

For test/development machines, `provisioning_mode: helper-managed` authorizes the
repository helper to manage local Compose services, files, runtime credentials, and UFW
rules. The current development profile uses authenticated plaintext on private listeners;
TLS, systemd, and backup are disabled.

The production contract is externally managed. MariaDB, Redis, backup storage,
certificates, credentials, endpoint lifecycle, upgrades, recovery, and rotation are
supplied and operated outside this repository. Configure `provisioning_mode: external`
with private endpoints, TLS, and least-privilege probe credentials. In external mode,
run only the check flow; repository-managed provisioning is refused.

## Operational Order

### 1. Prepare the controller and environment

From the repository root, select the environment and load the controller paths:

```bash
ENVIRONMENT="test"
K3S_DIR="$PWD/execution/k3s"
export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"
SECRETS_FILE="$K3S_DIR/environments/$ENVIRONMENT/secrets.sops.yml"

if ! ./execution/k3s/operations/setup/controller.sh check; then
  ./execution/k3s/operations/setup/controller.sh install
  ./execution/k3s/operations/setup/controller.sh check
fi

test -r "$SOPS_AGE_KEY_FILE" || {
  echo "Age identity is missing or unreadable: $SOPS_AGE_KEY_FILE" >&2
  exit 1
}
test -r "$SECRETS_FILE" || {
  echo "Encrypted secrets are missing or unreadable: $SECRETS_FILE" >&2
  exit 1
}
```

`controller.sh install` installs the repository-pinned Python dependencies, age, SOPS,
and Ansible collections when the initial non-mutating check finds them absent.

Review `platform.yml` before provisioning. For this host, confirm the development
profile, `helper-managed` mode, private address `192.168.1.151`, allowed client CIDRs,
pinned image digests, runtime IDs, data paths, and disabled TLS/systemd/backup controls.

If credentials need to be initialized or rotated, create a restrictive temporary YAML
file outside Git and use `encrypt-secrets`; do not print decrypted values:

```bash
./execution/k3s/operations/data-services/data-services encrypt-secrets \
  --environment "$ENVIRONMENT" --from /secure/temporary/secrets.yml --remove-source
```

### 2. Satisfy apply preconditions

Before the first helper-managed setup:

- confirm recovery-console access;
- review existing MariaDB/Redis services, containers, configuration, and target paths;
- decide explicitly whether existing state is rejected or handled by a separate migration;
- confirm the configured private address is assigned to the host; and
- confirm SOPS can decrypt the environment secret document with the selected age identity.

The role refuses implicit adoption of unmanaged services or non-empty unmarked data
directories. Do not delete or reset data to bypass that guard.

### 3. Provision the development services

Run the explicit setup action, not `check`, for a first deployment. Setup executes the
ordered Phase 1 preflight, Phase 2 host baseline, Phase 3 desired state, container health,
private-listener checks, and authenticated protocol probes:

```bash
./execution/k3s/operations/data-services/data-services setup \
  --environment "$ENVIRONMENT" --provision-host-services
```

A successful run must end with both `Phase 3 runtime services: pass` and
`Phase 3 host data services: pass`.

### 4. Verify an existing deployment

Use the non-provisioning check after setup, during routine validation, or for externally
managed endpoints. It validates configuration, encrypted secrets, the prerequisite
phases, and live MariaDB/Redis behavior without converging services:

```bash
./execution/k3s/operations/data-services/data-services check \
  --environment "$ENVIRONMENT"
```

On a fresh helper-managed host with no services, this command is expected to fail its
live probes; it is not a provisioning preview.

### 5. Reapply and verify repeatability

First repeat setup without changing configuration, secrets, or managed files. The
following acceptance sequence records container identity, creates a temporary MariaDB
marker through the mounted client configuration, performs the unchanged setup, compares
identity and start timestamps, verifies persistence, and removes the temporary database:

```bash
set -euo pipefail

PROJECT_NAME="mokla-$ENVIRONMENT"
MARIADB_CONTAINER="$PROJECT_NAME-mariadb-1"
REDIS_CONTAINER="$PROJECT_NAME-redis-1"
REPEATABILITY_DIR="$(mktemp -d)"
BEFORE_STATE="$REPEATABILITY_DIR/before"
AFTER_STATE="$REPEATABILITY_DIR/after"

cleanup_repeatability_check() {
  docker exec "$MARIADB_CONTAINER" mariadb \
    --defaults-extra-file=/run/secrets/mariadb-health.cnf \
    -e 'DROP DATABASE IF EXISTS mokla_phase3_acceptance;' \
    >/dev/null 2>&1 || true
  rm -rf "$REPEATABILITY_DIR"
}
trap cleanup_repeatability_check EXIT

docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' \
  "$MARIADB_CONTAINER" "$REDIS_CONTAINER" >"$BEFORE_STATE"

docker exec -i "$MARIADB_CONTAINER" mariadb \
  --defaults-extra-file=/run/secrets/mariadb-health.cnf <<'SQL'
CREATE DATABASE IF NOT EXISTS mokla_phase3_acceptance;
CREATE TABLE IF NOT EXISTS mokla_phase3_acceptance.marker
  (value VARCHAR(32) PRIMARY KEY);
INSERT IGNORE INTO mokla_phase3_acceptance.marker
  VALUES ('phase3-repeatability');
SQL

./execution/k3s/operations/data-services/data-services setup \
  --environment "$ENVIRONMENT" --provision-host-services

docker inspect --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' \
  "$MARIADB_CONTAINER" "$REDIS_CONTAINER" >"$AFTER_STATE"
cmp "$BEFORE_STATE" "$AFTER_STATE"

docker exec -i "$MARIADB_CONTAINER" mariadb \
  --defaults-extra-file=/run/secrets/mariadb-health.cnf <<'SQL'
SELECT value FROM mokla_phase3_acceptance.marker;
DROP DATABASE mokla_phase3_acceptance;
SQL
```

Acceptance requires setup to report `changed=0`, `cmp` to return success, and the query
to print `phase3-repeatability`. A later managed configuration or credential change may
legitimately cause one controlled Compose recreation; run the unchanged-input sequence
again after convergence to establish the new stable baseline.

### 6. Use recovery helpers only when applicable

`repair-test-permissions` exists only for hosts affected by the original root-only Redis
mount deployment. It verifies repository ownership markers and adjusts managed
permissions without restarting services or deleting data:

```bash
./execution/k3s/operations/data-services/repair-test-permissions \
  --environment test --apply-permission-repair
```

It is not part of normal setup, routine validation, or production operation.

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

## Validation Results

- Final non-mutating check: Phase 1 `ok=16 changed=0 failed=0`; Phase 2
  `ok=76 changed=0 failed=0 skipped=5`; Phase 3 Ansible
  `ok=15 changed=0 failed=0 skipped=31`; both live protocol probes passed.
- Converging apply: `ok=34 changed=2 unreachable=0 failed=0 skipped=14`.
- Immediate repeated setup: `ok=33 changed=0 unreachable=0 failed=0 skipped=13`.
- Both setup runs reported `Phase 3 runtime services: pass` and
  `Phase 3 host data services: pass`.
- Before and after the second setup, MariaDB retained container ID prefix `5be94f022f8`
  and start time `2026-09-20T02:08:37.097934817Z`; Redis retained ID prefix
  `e7372267e4b` and start time `2026-09-20T02:08:37.095680955Z`.
- A temporary `phase3-repeatability` MariaDB marker survived the second setup and its
  acceptance database was removed afterward.
- All 55 k3s operation tests passed: 40 validation, 8 backup/restore safety, 2 controller
  setup, and 5 data-service helper tests, with 1 expected skip.
- Tracked shell syntax, Ansible syntax, `git diff --check`, and VS Code diagnostics passed.

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

In helper-managed development mode, the role owns precondition and adoption guards,
offline rendering, service-readable managed paths, host-networked Compose services,
runtime credentials, exact UFW inputs, health checks, and redacted evidence. Deferred
systemd and backup/restore implementations remain in the repository but are gated off by
the active profile. Applications, databases, users, grants, schemas, k3s, and Kubernetes
resources remain outside this implementation.

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