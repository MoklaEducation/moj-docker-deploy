# Phase 3 Implementation Plan: Host Data Services

Status: ready for implementation after Phase 2 passes.

## Mission

Deploy MariaDB and Redis on the same VM as the future k3s server while keeping both
services outside Kubernetes. The services must be reproducible, privately reachable,
observable at host level, included in encrypted off-host backup operations, and proven
recoverable without a working Kubernetes cluster.

Use systemd-managed Docker Compose with images pinned by immutable digest. Do not install
database packages directly on the host and do not use k3s containerd for these services.

## Architectural Context

The initial platform intentionally uses one failure domain: loss of the VM can remove
k3s, MariaDB, and Redis together. Resilience comes from repeatable host convergence and
tested off-host recovery, not local high availability.

This phase creates database service infrastructure only. Application plans later own
database names, users, grants, schema migrations, Redis key semantics, and application
data validation. Phase 3 must expose a stable connection and recovery contract without
assuming DMOJ or Keycloak details.

Read, in order:

1. [k3s Cluster Blueprint](README.md)
2. [Repeatable k3s Deployment Strategy](repeatable-deployment.md)
3. [Phase 1 Preflight](phase-1-preflight.md)
4. [Phase 2 Host Baseline](phase-2-host-baseline.md)

If a conflict exists, the blueprint wins, followed by the deployment strategy, followed
by this plan.

## Preconditions

- Phase 1 passes for the selected environment immediately before apply.
- Phase 2 evidence reports success, no pending reboot, and clean second-run idempotence.
- Docker Engine and Docker Compose are installed at the configured pinned versions.
- The configured private service address is assigned to the host and is not a public or
  wildcard address.
- Off-host backup storage and encryption-key custody have been selected.
- SOPS/age secret delivery is operational; placeholder secrets are not accepted.
- The operator has a tested console/recovery path and has reviewed the rendered service,
  firewall, and backup changes.
- No existing MariaDB/Redis data directory or service will be adopted implicitly.

If a configured target directory is non-empty, apply must stop with a migration-required
message unless a separately reviewed adoption flag and procedure are present. Do not
overwrite or import the current Compose data automatically.

## Goals

1. Run one digest-pinned MariaDB service and one digest-pinned Redis service outside k3s.
2. Keep service data, configuration, secrets, logs, and backup staging in explicit,
   separately owned host paths.
3. Restrict network access to declared administrative and future pod-network sources.
4. Use encrypted transport for database connections.
5. Provide health checks independent of application schemas and k3s.
6. Create encrypted, integrity-checked off-host backups on a monitored schedule.
7. Prove restore into isolated service instances without modifying the primary services.
8. Preserve a stable interface that later Kubernetes `Service`/`EndpointSlice` resources
   can consume.

## Non-Goals

- Installing k3s or deploying Kubernetes resources.
- Creating DMOJ, Keycloak, or other application databases, users, grants, or schemas.
- Migrating existing Compose database content.
- Providing database replication, clustering, automatic failover, or zero downtime.
- Backing up live MariaDB files as a substitute for a logical database backup.
- Exposing MariaDB, Redis, admin UIs, Docker, or backup endpoints publicly.
- Selecting application Redis durability semantics; the environment must declare them.

## Fixed Service Model

| Concern | Decision |
| --- | --- |
| Runtime | Phase 2 Docker Engine and Compose plugin |
| Supervisor | A project-owned systemd unit invoking Docker Compose |
| Network mode | Host networking; no Docker-published ports or bridge NAT |
| MariaDB storage | Bind-mounted dedicated host directory |
| Redis storage | Bind-mounted directory when persistent; explicit disposable mode otherwise |
| Image policy | Version-readable tag plus immutable digest; digest controls execution |
| Secrets | SOPS/age in Git, decrypted to root-only runtime files on the host |
| MariaDB backup | Consistent logical dump, compressed, then captured by restic |
| Redis backup | Consistent RDB snapshot when persistent; configuration-only when disposable |
| Off-host backup | Restic repository outside the VM |
| Restore test | Parallel isolated containers and directories, never primary paths |

Host networking is chosen so the host firewall remains the network-policy authority and
Docker port publishing cannot bypass UFW through its NAT rules. Compose files must not
contain `ports:` entries for either service.

## Configuration Contract

Consume the Phase 1 environment schema. Its required data-service and backup values are
equivalent to:

```yaml
data_services:
  bind_address: 10.0.0.10
  allowed_client_cidrs:
    - 10.42.0.0/16
    - 10.0.0.0/24
  tls:
    enabled: true
    minimum_version: TLSv1.2
    server_certificate_secret_key: data_services_tls_certificate
    server_private_key_secret_key: data_services_tls_private_key
    ca_certificate_secret_key: data_services_ca_certificate

  mariadb:
    image: docker.io/library/mariadb:<reviewed-version>@sha256:<digest>
    port: 3306
    character_set: utf8mb4
    collation: utf8mb4_unicode_ci
    data_path: /srv/mokla/data-services/mariadb/data
    config_path: /etc/mokla/data-services/mariadb
    backup_timeout_seconds: 1800

  redis:
    image: docker.io/library/redis:<reviewed-version>@sha256:<digest>
    port: 6379
    data_policy: disposable
    data_path: /srv/mokla/data-services/redis/data
    config_path: /etc/mokla/data-services/redis
    maxmemory: <measured-byte-limit>
    maxmemory_policy: allkeys-lru

backup:
  restic_repository: <off-host repository URL without embedded credentials>
  schedule: "daily at an explicitly selected UTC time"
  staging_path: /srv/mokla/backup-staging
  retention:
    daily: 7
    weekly: 4
    monthly: 6
  minimum_expected_frequency_hours: 26
```

Replace angle-bracket values before implementation. `bind_address` must be a specific
stable private host address, never `0.0.0.0`. The future pod CIDR may be allowed before
k3s exists, but acceptance must prove that no unintended external source can connect.
Phase 3 must not create a second source for these values.

Required encrypted secret keys:

- `mariadb_root_password`;
- `redis_password` when authentication is enabled;
- `restic_password` and provider-specific repository credentials;
- TLS server certificate, private key, and issuing CA certificate;
- optional TLS CA private key only when this host is explicitly responsible for renewal.

Prefer issuing the service certificate outside the target host. Never place the CA
private key on the host unless an accepted certificate lifecycle requires it.

## Intended File Ownership

```text
execution/k3s/host/
  playbooks/
    host-data-services.yml
  roles/
    data-services/
      defaults/main.yml
      handlers/main.yml
      tasks/
        main.yml
        validate.yml
        filesystem.yml
        secrets.yml
        compose.yml
        firewall.yml
        systemd.yml
        health.yml
        backup.yml
        verify.yml
      templates/
        compose.yml.j2
        mariadb.cnf.j2
        redis.conf.j2
        mokla-data-services.service.j2
        data-services-report.json.j2

execution/k3s/operations/
  backup/
    backup-data-services.sh
    verify-backup.sh
    systemd/
      mokla-data-backup.service
      mokla-data-backup.timer
  restore/
    restore-data-services.sh
    verify-restored-data.sh
```

Scripts hold orchestration only. Configuration and desired state remain in Ansible
templates and environment inputs. Generated Compose, configuration, and systemd files
are deployed under `/etc/mokla`; generated evidence remains ignored.

## Operator Interface

Required convergence commands:

```bash
./execution/k3s/bootstrap.sh check --environment test --through host-data-services
./execution/k3s/bootstrap.sh apply --environment test --through host-data-services
```

These commands run prerequisite phases in order. Phase 3 cannot bypass Phase 1 or a
converged Phase 2.

Required lifecycle commands may be routed through a later stable operator wrapper, but
must have non-interactive script entry points from this phase:

```text
backup data-services --environment <name>
backup verify --environment <name> --snapshot <id>
restore data-services --environment <name> --snapshot <id> --target <isolated-target>
```

Restore must require an explicit snapshot and isolated target. Restoring over primary
paths is outside Phase 3 and must be rejected.

## Required Host State

### Filesystem separation

Use separate roots with restrictive ownership:

```text
/etc/mokla/data-services/              rendered non-secret configuration
/etc/mokla/secrets/data-services/      root-only runtime secret files
/srv/mokla/data-services/mariadb/      MariaDB durable data
/srv/mokla/data-services/redis/        Redis data when persistent
/srv/mokla/backup-staging/             temporary logical backup artifacts
/var/log/mokla/                        host operation status/evidence as configured
```

- Secret directories use mode `0700`; secret files use `0600` and root ownership.
- Do not put secrets in Compose environment values, command arguments, labels, logs, or
  `docker inspect` output. Use mounted secret files and supported `*_FILE` variables or
  service configuration files.
- Data directories must not be children of Docker's data root or k3s storage paths.
- Backup staging must be on a filesystem with enough free space for the largest expected
  logical dump plus safety margin.
- Remove temporary plaintext backup artifacts after restic confirms a snapshot.

### Compose and systemd lifecycle

- Use one Compose project name derived deterministically from the environment.
- Pin both image references by digest and retain readable version tags.
- Use `restart: unless-stopped`, init handling where needed, explicit health checks,
  resource limits, and bounded container logs.
- Use `network_mode: host`; define no published ports.
- Mount configuration read-only and service data read-write only where required.
- Add container security options supported by the official images without breaking their
  initialization; document any required writable paths or Linux capabilities.
- A root-owned systemd unit runs `docker compose up --detach --remove-orphans` and stops
  with `docker compose stop`. Ordinary stop must never remove data or volumes.
- Do not run `docker compose down --volumes` in apply, stop, backup, or restore paths.
- Wait for health checks and fail apply if either service does not become healthy within
  its configured timeout.

### MariaDB configuration

- Bind only to the configured private address and port.
- Require TLS for non-loopback clients and enforce the configured minimum TLS version.
- Initialize only the server and root/bootstrap credential. Do not create application
  databases or users.
- Set explicit character set and collation defaults.
- Enable durable settings appropriate for a single-node transactional database; do not
  trade durability for benchmark performance without a recorded decision.
- Bound logs and expose them to host collection without recording SQL statements or
  credentials by default.
- Health checks authenticate through a root-only defaults file or a purpose-specific
  health credential without exposing a password in process arguments.

### Redis configuration

- Bind only to the configured private address and loopback when operationally required.
- Enable protected mode and authentication/ACLs; do not use a password in the process
  command line.
- Require TLS for non-loopback clients when enabled by the accepted service contract.
- Set explicit memory limit and eviction policy from environment configuration.
- If `data_policy` is `persistent`, enable and document the selected RDB/AOF policy and
  include consistent state in backup/restore tests.
- If `data_policy` is `disposable`, disable assumptions of Redis data recovery, back up
  configuration only, and prove recovery starts a healthy empty service. The final
  application plan must confirm that losing queued or cached keys is acceptable.
- Disable dangerous unauthenticated administrative access from client networks.

### Firewall contract

- Permit MariaDB and Redis only from declared client CIDRs to their exact destination
  address and port.
- Keep both ports denied from public and undeclared private sources.
- Because host networking is used, UFW remains authoritative; verify the effective
  netfilter path rather than assuming declared rules are sufficient.
- Test externally from at least one allowed source and one denied source. A local socket
  test alone is insufficient.
- Do not weaken Phase 2 SSH, API, or ingress rules.

## Backup Design

### MariaDB

1. Acquire a per-service backup lock so schedules and manual runs cannot overlap.
2. Verify MariaDB health and sufficient staging capacity.
3. Produce a consistent logical dump with routines, events, triggers, and all current
   databases using a root-only client defaults file.
4. Compress the dump, calculate a cryptographic checksum, and write metadata containing
   image digest, server version, UTC timestamp, environment, and dump options.
5. Send the dump, checksum, non-secret configuration, and metadata to restic.
6. Verify the new snapshot exists and run `restic check` at the accepted frequency.
7. Apply retention only after successful snapshot verification.
8. Remove plaintext staging artifacts and expose success/failure for later monitoring.

Never feed the live MariaDB data directory directly to restic as the supported backup.

### Redis

For persistent mode, request a consistent snapshot, wait for completion, copy the
resulting persistence artifact into staging, checksum it, and include it in the same
restic operation. For disposable mode, record that data was intentionally excluded and
back up only the sanitized configuration and policy metadata.

### Scheduling and failure behavior

- Use a systemd service and timer with randomized delay bounded by configuration.
- A failed dump or restic upload must leave the previous valid snapshot untouched,
  return non-zero, and be visible to Phase 6 observability later.
- Do not prune snapshots when the current backup failed.
- Do not log secret-bearing repository URLs or credentials.
- Record last-success timestamp in a root-owned status file suitable for node-exporter
  textfile collection later.

## Restore Qualification

The required Phase 3 restore test is isolated and destructive only to its dedicated test
paths:

1. Create a temporary MariaDB probe database and marker row using a test-only credential.
2. For persistent Redis, create a probe key with a documented expiration policy.
3. Run the production backup workflow and capture the restic snapshot ID.
4. Allocate isolated restore directories and alternate loopback-only ports.
5. Restore backup artifacts into staging and verify checksums before use.
6. Start separate digest-identical MariaDB and Redis containers with unique names.
7. Import the MariaDB logical dump; never copy it over the primary data directory.
8. Restore Redis persistence when selected, or verify an empty healthy Redis in
   disposable mode.
9. Verify the MariaDB marker and Redis policy outcome.
10. Stop and remove only the isolated containers and test directories.
11. Remove the probe data from the primary services and record the result.

The primary services must remain healthy and available throughout the isolated restore
test. A later full-host recovery phase will test rebuilding onto a clean VM.

## Idempotence Requirements

- A second apply changes no Compose, service configuration, systemd, firewall, secret,
  ownership, or directory state when inputs are unchanged.
- Secret files change only when decrypted secret content changes; reports never expose
  that content.
- Apply may recreate a container only when its image digest or effective configuration
  changes.
- Ordinary convergence never initializes a new data directory over an existing one and
  never resets a credential implicitly.
- Backup timers and status files do not cause Ansible drift.
- Check mode renders and validates intended files without starting containers, decrypting
  secrets onto the host, contacting the backup repository, or changing firewall state.

## Failure and Rollback Behavior

- Pull and verify new images before replacing running containers.
- Retain the previously deployed digest in evidence and provide an explicit rollback
  procedure; do not automatically downgrade a database after it may have upgraded data.
- Treat MariaDB major-version changes as migrations requiring backup, restored-copy
  testing, compatibility review, and a separate upgrade plan.
- On failed configuration validation, leave the currently running service unchanged.
- On failed startup, preserve data and logs, stop progression, and require operator
  review. Never delete or reinitialize data to make a health check pass.
- Backup failure does not stop the database services, but it blocks Phase 3 completion
  and later application readiness.

## Implementation Sequence

1. Add Phase 3 semantic validation for the existing environment and secret schemas.
2. Select exact MariaDB and Redis versions/digests and record compatibility rationale.
3. Implement filesystem and root-only secret delivery.
4. Render and validate service configuration and Compose definitions offline.
5. Implement firewall rules and external allowed/denied connectivity fixtures.
6. Install the systemd-managed Compose lifecycle and health assertions.
7. Implement logical backup, checksums, restic upload, retention, and status output.
8. Implement the isolated restore workflow with strict target guards.
9. Run first apply, second apply, backup, backup verification, restore qualification, and
   negative network tests on a disposable VM.
10. Document image upgrade and existing-data adoption as separate future procedures.

## Acceptance Tests

Run and record at minimum:

```bash
./execution/k3s/bootstrap.sh check --environment test --through host-data-services
./execution/k3s/bootstrap.sh apply --environment test --through host-data-services
./execution/k3s/bootstrap.sh apply --environment test --through host-data-services
```

Then invoke the implemented backup, verification, and isolated restore entry points.
Acceptance evidence must prove:

1. Both containers run the configured immutable digests and become healthy.
2. Neither Compose service publishes a Docker port or uses a bridge-NAT exposure path.
3. TLS and authentication succeed for an allowed client.
4. Allowed-source connectivity succeeds and denied-source connectivity fails for both
   service ports.
5. No secret appears in Git, Compose rendering, process arguments, `docker inspect`,
   ordinary logs, or evidence reports.
6. A logical MariaDB backup and selected Redis-policy backup reach off-host restic storage
   with checksums and metadata.
7. Backup freshness and last-success status are machine-readable.
8. The isolated restore recovers the MariaDB marker and expected Redis state/policy while
   primary services remain healthy.
9. The second apply reports no unintended changes and does not recreate healthy
   unchanged containers.
10. Stopping and starting the systemd unit preserves all durable state.
11. A simulated backup upload failure returns non-zero, retains the prior snapshot, skips
   pruning, and exposes failure status.

Run shell lint, YAML lint, `ansible-lint`, Ansible syntax/check mode, Compose rendering,
and disposable-VM integration tests. Scan selected images and record accepted findings;
do not silently substitute a newer digest during testing.

## Evidence Contract

Write redacted reports under:

```text
execution/k3s/.evidence/<environment>/phase-3-host-data-services.json
execution/k3s/.evidence/<environment>/phase-3-backup.json
execution/k3s/.evidence/<environment>/phase-3-restore.json
```

Record environment and host identity, previous-phase evidence IDs, image references and
digests, non-secret configuration hashes, service health, listening addresses, firewall
test results, backup snapshot ID, checksums, retention result, restore target, marker
validation, first/second-run recap, and overall status. Never record credentials, private
keys, decrypted secret content, or secret-bearing URLs.

## Completion Gate

Phase 3 is complete only when first and second convergence runs pass, network isolation
is externally verified, encrypted off-host backup succeeds, isolated restore
qualification succeeds, failure behavior is exercised, evidence is redacted, and the
services can be recovered without k3s or application manifests.