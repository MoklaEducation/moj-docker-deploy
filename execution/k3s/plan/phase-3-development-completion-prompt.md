# Phase 3 Development Completion Prompt

Copy the prompt below into a coding-agent session opened at the repository root.

```text
Finish Phase 3 as a lightweight, repeatable development-enablement layer.

Read first:

1. execution/k3s/plan/phase-3-host-data-services.md
2. execution/k3s/plan/progress/phase-3-host-data-services-progress.md
3. execution/k3s/operations/data-services/README.md
4. the current Phase 1 and Phase 2 progress documents

The Current Delivery Profile in the Phase 3 plan is authoritative. Older TLS, systemd,
backup, restore, and production-hardening requirements are deferred and must not block
this phase.

Objective

Provide one working MariaDB container and one working Redis container on the test host so
k3s-layer development can proceed. Optimize for simple, repeatable, non-destructive
provisioning, not production readiness.

Required behavior

- Use Docker/Compose containers only. Do not install native MariaDB or Redis servers.
- Keep one MariaDB engine and one Redis service for the environment.
- Use reviewed version-pinned images; retain digest pins if they already work.
- Store data under service subdirectories of `/srv/mokla/data-services`.
- Keep passwords in the existing SOPS document. Never commit or print plaintext secrets.
- Extend SOPS later with application-scoped credentials when application phases create
  separate logical databases and users. Do not create DMOJ or Keycloak databases now.
- Bind services to the configured private address, never `0.0.0.0` or a public address.
- Make MariaDB execute an authenticated `SELECT 1` and Redis return authenticated `PONG`.
- Run setup repeatedly without deleting data, resetting credentials, or recreating
  unchanged healthy containers.
- Preserve Phase 1 and Phase 2 behavior and evidence.

Explicit relaxations

The following are not Phase 3 completion requirements for this disposable environment:

- TLS, certificate generation, certificate validation, or certificate rotation;
- dedicated least-privilege health users; root/default credentials are acceptable for
  development probes when read from protected files and never exposed in arguments/logs;
- strict per-service UID/GID isolation or separate secret roots; set only the ownership
  and modes needed by the selected containers to function repeatably;
- systemd supervision; `docker compose up --detach --wait` and Compose restart policies
  are sufficient;
- off-host or local backup automation, restic, schedules, retention, snapshots, restore
  qualification, or simulated backup failure;
- external allowed-source and denied-source test vantage points;
- production image scan acceptance, monitoring, alerting, disaster recovery, HA, or
  migration/adoption workflows beyond refusing destructive implicit adoption.

Existing code for deferred capabilities may remain if it is inert and does not complicate
or block the development path. Prefer removing it from active setup/check dispatch or
making it explicitly disabled for the development profile. Do not spend time repairing a
deferred subsystem merely to preserve the previous completion definition.

Implementation goals

1. Simplify the environment contract.
   - Allow TLS to be disabled for the development profile.
   - When TLS is disabled, do not require certificate keys, CA material, renewal owner, or
     TLS-specific validation.
   - Keep MariaDB/Redis passwords required and non-placeholder in SOPS.
   - Disable backup/restore requirements and validation for this profile.
   - Keep private address, ports, image versions, data paths, and memory settings explicit.

2. Simplify container configuration.
   - Render MariaDB and Redis configurations without TLS when disabled.
   - Use host networking or private-address port binding consistently with the current
     design, but never expose wildcard/public listeners.
   - Keep health checks credential-safe and ensure they fail on authentication errors.
   - Use bind-mounted service data directories, not data inside the source checkout.
   - Configure only permissions required by the pinned image users. Encode them in the
     repeatable desired state; do not require a one-time repair helper.

3. Simplify lifecycle ownership.
   - The explicit helper remains the provisioning entry point:

       ./execution/k3s/operations/data-services/data-services setup \
         --environment test --provision-host-services

   - It may invoke Ansible and Docker Compose directly.
   - Do not require systemd units or backup timers for completion.
   - Keep check mode non-mutating.
   - Refuse unknown existing containers or non-empty unmarked data directories rather
     than deleting or silently adopting them.

4. Simplify runtime validation and evidence.
   - Runtime probes must support plaintext authenticated connections when TLS is disabled.
   - Evidence must record image references, private endpoint/ports, container health,
     MariaDB `SELECT 1`, Redis `PONG`, and setup repeatability.
   - Mark TLS, backup, restore, systemd, and external network checks `not_applicable` or
     omit them for this profile. They must not make the final status partial or failed.
   - Keep evidence redacted and deterministic.

5. Prove repeatability.
   - Record both container IDs and start timestamps after the first successful setup.
   - Create a temporary MariaDB acceptance database/table/marker solely for this test.
   - Run setup a second time.
   - Confirm both container IDs/start timestamps are unchanged and the marker remains.
   - Remove the temporary acceptance database after verification.
   - Confirm no credentials or existing service data were reset.

Definition of done

Use a fresh shell:

  cd /path/to/moj-docker-deploy
  ENVIRONMENT="test"
  K3S_DIR="$PWD/execution/k3s"
  export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
  export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
  export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

Run in this order:

  ./execution/k3s/operations/setup/controller.sh check
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-baseline
  ./execution/k3s/operations/data-services/data-services check --environment "$ENVIRONMENT"
  ./execution/k3s/operations/data-services/data-services setup \
    --environment "$ENVIRONMENT" --provision-host-services

  # Record container IDs/start times and create a temporary MariaDB persistence marker.

  ./execution/k3s/operations/data-services/data-services setup \
    --environment "$ENVIRONMENT" --provision-host-services
  ./execution/k3s/operations/data-services/data-services check --environment "$ENVIRONMENT"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-data-services

Phase 3 is done only when:

- all commands above exit `0`;
- both containers are healthy;
- authenticated MariaDB `SELECT 1` and Redis `PONG` pass;
- listeners are on the configured private address, not wildcard/public;
- the second setup does not recreate unchanged containers;
- the MariaDB persistence marker survives the second setup;
- Phase 1 and Phase 2 remain green;
- final Phase 3 evidence reports `overall_status: pass` without secrets;
- the full available unit/static validation suite and `git diff --check` pass.

Documentation and commits

- Update `execution/k3s/plan/progress/phase-3-host-data-services-progress.md` with the
  revised scope, exact commands, recaps, container repeatability proof, and final evidence.
- List TLS, strict identity isolation, systemd, backup/restore, external network tests,
  and production hardening as deferred, not failed Phase 3 gates.
- Remove stale claims that Redis fails if its current authenticated probe passes.
- Preserve unrelated `dmoj/repo` changes.
- Stage only intended Phase 3 files, inspect the staged diff, run
  `git diff --cached --check`, and create focused follow-up commits.
- Do not amend prior commits or push unless explicitly requested.

Do not mark Phase 3 production-ready. Mark it complete only as a disposable,
repeatable development dependency that unblocks the next k3s layer.
```
