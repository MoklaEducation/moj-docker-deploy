# Phase 3 External Platform Services Progress

Status: co-located development profile complete

Last updated: 2026-09-27

The normative requirements remain in
[phase-3-external-platform-services.md](../phase-3-external-platform-services.md).

## Implemented Profile

The existing Phase 3 helper and Ansible role own four Docker Compose services on the test
VM:

- MariaDB and Redis under the established host data-service contract;
- MinIO as private S3-compatible object storage;
- a repository-owned, memory-only HTTP receiver for Alertmanager testing.

The profile is `co-located-development`. All services remain outside k3s but share its VM
and physical Proxmox failure domain. This proves functional behavior and repeatability;
it does not qualify off-host recovery.

## Selected Inputs

- MinIO-compatible server: frozen Bitnami legacy MinIO `2025.7.23-debian-12-r3`, pinned
  by linux/amd64 manifest digest. The official MinIO registry was not anonymously
  accessible during implementation, so this image is accepted only for disposable
  testing and must be replaced or explicitly re-approved before production.
- Alert receiver runtime: official Python `3.13.7-alpine3.22`, pinned by linux/amd64
  manifest digest, running the repository-owned standard-library receiver as UID/GID
  `65534` with a read-only root filesystem.
- Private endpoints: MinIO API `192.168.1.151:9000`, MinIO console
  `192.168.1.151:9001`, and alert receiver `192.168.1.151:9080`.
- Persistent MinIO data: `/srv/mokla/platform-services/minio/data`.
- SOPS/age stores separate MinIO root and restic credentials. The webhook is
  unauthenticated only within the private disposable test boundary.

## Endpoint And Credential Contract

| Consumer | Endpoint | Credential reference | Boundary |
| --- | --- | --- | --- |
| Restic/controller | `s3:http://192.168.1.151:9000/mokla-test-backups/restic-smoke` | `minio_restic_access_key`, `minio_restic_secret_key`, and `restic_password` | Bucket-scoped object access; MinIO administration is denied |
| MinIO bootstrap/operator | `http://192.168.1.151:9000` | `minio_root_user` and `minio_root_password` | Service bootstrap and explicit administration only |
| MinIO operator console | `http://192.168.1.151:9001` | `minio_root_user` and `minio_root_password` | Restricted to configured administrative CIDRs |
| Alertmanager test route | `http://192.168.1.151:9080/alerts` | None in the private disposable test profile | Accepts controlled test alert payloads only |
| Health validation | `http://192.168.1.151:9000/minio/health/live` and `http://192.168.1.151:9080/health` | None | Health probes expose no credentials or retained alert data |
| Test inspection/cleanup | `http://192.168.1.151:9080/events` | None | `GET` inspects sanitized events; `DELETE` clears test state |

Credential names are references into the ignored SOPS/age document at
`execution/k3s/environments/test/secrets.sops.yml`; this progress record and durable
evidence never contain their values. Credentials are not embedded in endpoint URLs,
Compose files, process arguments, or logs. The committed
`secrets.sops.yml.example` documents the required key names with placeholders only.

The MinIO root identity is not a workload or backup credential. Restic and future backup
consumers must use the bucket-scoped restic identity. The unauthenticated webhook and its
`/events` inspection interface are test-only and must not be promoted as a production
notification service.

## Operator Interface

The extension is part of Phase 3 and adds no parallel bootstrap path:

```bash
./execution/k3s/operations/data-services/data-services setup \
  --environment test --provision-host-services
./execution/k3s/operations/data-services/data-services check --environment test
```

`setup` performs the mutating object, webhook, and restic smoke tests. `check` performs
read-only protocol checks against all four services and the initialized restic repository.

## Verified Behavior

- Initial convergence created MinIO and the alert receiver and applied narrow UFW rules.
- MariaDB, Redis, MinIO, and the alert receiver are healthy on private listeners.
- MinIO owns the declared bucket and a separate restic user with bucket-scoped policy.
- The restic identity can access its bucket and is denied MinIO administrative access.
- Apply writes, reads, verifies, and deletes a disposable MinIO object.
- Apply sends a controlled alert, verifies only its sanitized identifier is retained,
  and clears receiver state.
- Restic initializes the test repository, creates a marker snapshot, runs `restic check`,
  restores into a temporary isolated directory, verifies content, and retains only the
  latest smoke snapshot.
- An unchanged setup reported `changed=0` and preserved all four container IDs and start
  timestamps.
- A subsequent check reported `changed=0`; all five protocol checks passed and receiver
  event state remained empty.
- The complete validation suite passed 102 tests. Python compilation, shell syntax,
  Ansible syntax, `git diff --check`, editor diagnostics, and evidence secret-pattern
  scanning passed.
- A final public check through `cluster-core` passed Phases 1-5. Phase 3 retained its
  successful apply-time external-service qualification and Phase 5 reported no drift.
- Durable redacted evidence remains part of
  `execution/k3s/.evidence/test/phase-3-host-data-services.json`.

## Remaining Profiles

- `isolated-test`: reproduce the service contract on a dedicated Proxmox VM and qualify
  the cross-VM firewall, NetworkPolicy, restart, and migration boundaries.
- `recovery-qualified`: move backup storage outside the physical Proxmox host and perform
  clean-host recovery before claiming off-host resilience.
- Replace or re-approve the frozen legacy MinIO distribution and perform vulnerability
  scanning before any production use.