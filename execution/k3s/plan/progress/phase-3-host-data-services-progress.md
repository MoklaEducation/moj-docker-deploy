# Phase 3 Host Data Services Progress

Status: optional test-host provisioning ready; live services and environment acceptance not yet established

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
- Direct Ansible check mode passed with `ok=14 changed=0 failed=0 skipped=28`; it wrote
  only the requested controller facts file and skipped every host mutation.
- The public Phase 3 check passes configuration and encrypted-secret validation, reaches
  Phase 3 Ansible, and remains non-mutating.
- The test host address is explicitly configured as `192.168.1.151`; Phase 3 also checks
  that the address is assigned to the target before mutation.
- MariaDB `11.8.6` and Redis `8.2.4` official `linux/amd64` image digests are pinned.
- Trivy `0.66.0` scans were recorded and accepted for this test environment. MariaDB
  reported 308 findings, including 1 critical and 25 high, all fixable. The lower-surface
  Redis Alpine image reported 78 findings, including 2 critical and 21 high, all fixable.
  Production promotion requires a separate review and should prefer rebuilt images with
  fewer fixable findings.
- The test environment explicitly accepts a local-development restic repository. This
  validates backup mechanics but does not protect against host loss and is not accepted
  for non-test environments.
- The semantic configuration and encrypted secret/TLS validation gates now pass.
- `provisioning_mode` separates explicit helper-managed host setup from externally
  managed production endpoints. The setup helper requires `--provision-host-services`.
- Phase 3 now requires live authenticated TLS probes: MariaDB must execute `SELECT 1`
  and Redis must return `PONG`. Because services have not been provisioned, the current
  runtime check correctly fails both probes.
- A controller-side test CA and service certificate covering `192.168.1.151` are stored
  beneath the ignored environment `.generated` directory. The certificate, server key,
  and CA certificate are assigned through SOPS; the CA key remains controller-side.
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
  operations/certificates/
    generate-test-data-services
    README.md
  operations/data-services/
    data-services
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

## Validation Results

The complete explicit unit suite passed 49 tests. Python compilation, shell syntax,
inventory discovery, all three playbook syntax checks, controller dependency validation,
wrapper argument rejection, VS Code diagnostics, and `git diff --check` passed.

Public read-only results:

- Phase 1 check: exit `0`, `ok=16 changed=0 failed=0`.
- Phase 2 check: exit `0`, `ok=76 changed=0 failed=0 skipped=5`.
- Before live protocol gates were added, Phase 3 Ansible check reached
  `ok=14 changed=0 failed=0 skipped=28`. The current public check intentionally returns
  failure until both configured services answer authenticated TLS probes.
- Direct Phase 3 role check for implementation validation: exit `0`,
  `ok=14 changed=0 failed=0 skipped=28`.
- Rendered backup, verification, and restore scripts passed `bash -n`.
- The generated test certificate passed chain and `192.168.1.151` SAN verification.
- Image compatibility probes confirmed Redis 8.2.4 provides `redis-server` and
  `redis-cli`, and MariaDB 11.8.6 provides `mariadb`, `mariadb-admin`, and `mariadb-dump`.

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
```

For production endpoints set `data_services.provisioning_mode: external`, configure
dedicated probe users and their SOPS key names, and run only the check command. The
external mode skips local Compose, systemd, filesystem, firewall, and backup ownership.

## Remaining Work

- Replace the local-development restic repository with off-host storage before treating
  backup as disaster-recovery protection.
- Run first apply, second apply, and final public check.
- Run real off-host backup, snapshot verification, marker-based isolated restore,
  systemd stop/start durability, overlapping-lock, and simulated upload-failure tests.
- Verify TLS/authenticated connectivity from an allowed external source and rejection
  from a denied external source.
- Record image scan results, evidence redaction scans, and exact first/second apply recaps.

No Phase 3 apply, service deployment, UFW mutation, host secret installation, backup,
retention, restore, service stop/start, or external network acceptance test has been run.
Image layers were pulled only for vulnerability and command-availability checks.
Allowed-source and denied-source tests are intentionally deferred and must be completed
before final environment acceptance.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-19 | Added the complete Phase 3 schema shape and explicit blocked test inputs. | Focused platform schema suite passed, 7 tests. |
| 2026-09-19 | Added semantic and encrypted-secret gates, public dispatch, guarded host role, offline rendering, and redacted convergence evidence. | Full unit suite passed; Phase 1 and Phase 2 public checks remained clean; direct Phase 3 check mode passed with zero changes. |
| 2026-09-19 | Added locked logical backup, conditional retention, snapshot verification, marker-based isolated restore, lifecycle evidence, and failure-path safety regressions. | Rendered script syntax, 8 focused safety tests, all playbook syntax checks, and the then-current 40-test suite passed. |
| 2026-09-19 | Configured the test host address, pinned and scanned current service images, added a bounded local-restic exception, and added renewable test PKI with SOPS import. | Semantic and encrypted-secret validation passed; certificate chain/SAN and image command compatibility passed; public Phase 3 check reached `ok=14 changed=0 failed=0 skipped=28`. |
| 2026-09-19 | Split optional helper-managed provisioning from external service validation and added authenticated TLS protocol probes with redacted evidence. | Focused provisioning, credential, runtime, report, and helper tests passed; absent services produce explicit MariaDB and Redis runtime failures. |