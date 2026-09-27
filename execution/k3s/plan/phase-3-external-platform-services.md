# Phase 3 Extension Plan: External Platform Services

Status: requirements defined; implementation not started

## Mission

Provide the small set of platform dependencies that Kubernetes workloads consume but
that are intentionally operated outside the k3s cluster. Extend the existing Phase 3
Docker, SOPS/age, private-network, health-check, and repeatability patterns so the same
service definitions can run first on the k3s VM and later on a dedicated Proxmox VM.

This is a Phase 3 responsibility extension, not Phase 2.2. Phase 2 owns the operating
system, Docker Engine, storage roots, firewall foundation, and automation prerequisites.
Phase 3 owns services that run on those foundations. The numbered Phase 1-9 gates remain
unchanged.

## Naming And Classification

Use **external platform services** as the umbrella term for services consumed by the
platform but operated outside k3s. External means external to the cluster, not
necessarily external to the VM or LAN.

Classify them by responsibility:

| Class | Initial services | Purpose |
| --- | --- | --- |
| Data services | MariaDB, Redis | Application and identity data/cache dependencies |
| Object storage | MinIO | S3-compatible target for encrypted test backups |
| Integration services | Alert webhook receiver | Verifiable destination for Alertmanager delivery |
| Backup clients | restic | Client workflow writing encrypted backup data to object storage |

Restic is a client and repository format, not a continuously running service. Grafana,
Prometheus, Alertmanager, Loki, Alloy, and cert-manager remain k3s cluster add-ons and do
not move into this category.

Avoid **baseline services** because it can be confused with the Phase 2 host baseline.
Use **host data services** only for the existing MariaDB/Redis implementation when its
same-host placement matters.

## Goals

1. Preserve one declarative service contract across co-located and isolated test profiles.
2. Keep every image version and executable artifact immutable and reviewable.
3. Keep credentials SOPS/age-encrypted and absent from rendered logs and evidence.
4. Expose only stable private endpoints required by named k3s consumers.
5. Prove check, apply, second-apply, restart, backup, restore, and migration behavior.
6. Separate service lifecycle from k3s lifecycle without adding unnecessary infrastructure.
7. Make movement to a dedicated VM an environment change, not a service redesign.

## Non-Goals

- Deploying these services inside Kubernetes.
- Providing high availability, clustering, or automatic failover.
- Claiming physical failure isolation when VMs share one Proxmox host.
- Replacing SOPS/age with Vault, Key Vault, or another secret controller.
- Operating public DNS, public certificate issuance, or public service endpoints.
- Moving existing MariaDB or Redis data implicitly.
- Installing Mimir or another remote observability backend.
- Treating same-host MinIO as an off-host disaster-recovery destination.

## Deployment Profiles

### Co-located development

```text
Proxmox host
└── platform VM
    ├── Docker: MariaDB, Redis, MinIO, webhook receiver
    └── k3s: cluster core, add-ons, and later applications
```

Use this profile for the lowest-cost implementation loop. It validates service startup,
credentials, endpoint contracts, k3s egress policies, alert delivery, S3 compatibility,
and backup mechanics.

The profile has one VM and one physical failure domain. MinIO here is a functional test
repository only. Evidence must call its backup resilience `not_qualified`.

### Isolated test

```text
Proxmox host
├── k3s VM
│   └── k3s cluster and add-ons
└── platform-services VM
    └── MariaDB, Redis, MinIO, webhook receiver
```

Use this profile as the primary pre-production qualification topology. It must prove
private network reachability, host firewall rules, Kubernetes NetworkPolicy, independent
service restarts, stable endpoint migration, and k3s VM rebuild without rebuilding the
service VM.

Separate VMs on one Proxmox host provide process, filesystem, operating-system, and VM
lifecycle isolation. They do not provide physical disaster-recovery isolation.

### Recovery-qualified

Place the backup repository on another physical host, NAS, or external S3-compatible
service. This profile is required before claiming off-host backup resilience. MariaDB,
Redis, and the webhook receiver may remain on the services VM if their accepted
availability and recovery contracts permit it.

## Configuration Contract

Extend the shared environment schema with non-secret placement and endpoint data. The
exact final shape is an implementation decision, but it must express the equivalent of:

```yaml
external_platform_services:
  profile: co-located-development # isolated-test | recovery-qualified
  provisioning_mode: helper-managed # external
  target_connection:
    mode: local # ssh
    inventory_host: platform_services
  bind_address: 192.168.1.151
  allowed_client_cidrs: [10.42.0.0/16, 192.168.1.0/24]

  object_storage:
    provider: minio
    api_endpoint: http://192.168.1.151:9000
    console_endpoint: http://192.168.1.151:9001
    bucket: mokla-test-backups
    data_path: /srv/mokla/platform-services/minio/data
    credential_secret_keys: [minio_root_user, minio_root_password]

  alert_receiver:
    endpoint: http://192.168.1.151:9080/alerts
    data_policy: disposable
    retention_hours: 24
```

URLs must not contain usernames, passwords, tokens, or signed query parameters. Use
specific private addresses, never wildcard listeners. The co-located profile may use the
k3s VM address; the isolated profile uses the services VM address without changing
consumer Secret names or service semantics.

The existing `data_services` contract remains authoritative for MariaDB and Redis during
the first implementation. Do not duplicate those values under
`external_platform_services`. A later schema consolidation may move them only with a
compatibility migration and unchanged application-facing endpoints.

## Secret Contract

Continue using the established SOPS/age workflow:

- commit only encrypted environment secret sources;
- keep the age identity outside Git on the trusted controller;
- decrypt to restrictive temporary files or pipe directly to the consumer;
- never place plaintext under repository or evidence paths;
- use separate credentials for MinIO administration, backup clients, and health probes;
- do not embed credentials in endpoint URLs or Compose files;
- rotate one service without requiring unrelated service recreation;
- preserve stable Kubernetes Secret names for future consumers.

Minimum new encrypted keys are:

- `minio_root_user` and `minio_root_password` for initial service bootstrap;
- `minio_restic_access_key` and `minio_restic_secret_key` for least-privilege backup use;
- an optional webhook token only if the selected receiver supports authenticated delivery.

The restic repository password remains separate from MinIO credentials. The webhook
receiver should use no authentication in the private disposable test profile unless
authentication itself is under test.

## Service Requirements

### Common controls

Every managed service must:

- use a reviewed image reference pinned by digest;
- have explicit CPU, memory, storage, and log limits;
- bind only to the declared private address and required ports;
- have a protocol-level health check, not only a running-container check;
- store persistent data under an explicitly owned path;
- reject implicit adoption of non-empty unmarked data directories;
- restart only when a managed input changes;
- preserve container identity during an unchanged second apply;
- recover after a VM reboot without interactive action;
- emit bounded logs without credentials or request authorization values;
- expose no public endpoint or host Docker socket.

### MariaDB and Redis

Retain the current Phase 3 contract and implementation until an isolated services VM is
introduced. Migration must use service-aware backup/restore or an explicitly reviewed
data migration; never copy live database files casually or initialize over existing
state.

Moving these services must preserve their private endpoint contract, authentication,
data behavior, and application ownership boundaries. Application databases, users,
schemas, grants, and Redis key semantics remain application responsibilities.

### MinIO

MinIO must provide a private S3-compatible API for test backup workflows:

- pin the image by digest and record compatibility with the selected restic version;
- bind the S3 API and administrative console to the private service address;
- keep the console inaccessible from unapproved networks;
- use a dedicated bucket and least-privilege restic access key;
- use an explicit persistent data path and storage-capacity threshold;
- verify authenticated bucket access, object write/read/delete, and checksum equality;
- define whether versioning is enabled and bound retained capacity accordingly;
- never use the repository being protected as MinIO's own only backup;
- report same-host repositories as functional-only, not off-host protection.

### Alert webhook receiver

The test receiver must be intentionally small and disposable:

- expose one private HTTP endpoint to Alertmanager;
- accept a controlled alert and record a timestamp, stable test identifier, and delivery
  count without retaining credentials or sensitive labels;
- expose a health endpoint and a bounded query or inspection method for validation;
- limit event count or retention so storage cannot grow without bound;
- support deterministic cleanup between acceptance runs;
- reject or ignore unrelated paths and methods;
- not become the production notification destination by accident.

A nonexistent URL is useful only for failure-path tests. Phase 6 completion requires one
successful end-to-end delivery to a reachable receiver.

### Restic integration

Use restic as a pinned backup client rather than a resident service:

- configure its S3 repository URL without embedded credentials;
- provide MinIO credentials and repository password from separate SOPS keys;
- create snapshots only after the owning service has produced a consistent source;
- run `restic check` and enforce retention only after a successful snapshot;
- restore into isolated paths and disposable consumers, never over live primary data;
- record snapshot IDs, hashes, duration, size, and validation status without secrets;
- inject a failed-destination test and prove primary data and prior snapshots remain safe.

## Networking Contract

Host firewall and Kubernetes NetworkPolicy must agree on the exact flows:

| Source | Destination | Initial purpose |
| --- | --- | --- |
| Approved k3s pods | MariaDB TCP 3306 | Application database access |
| Approved k3s pods | Redis TCP 6379 | Application cache/queue access |
| Backup workloads or controller | MinIO S3 API TCP 9000 | Backup and restore |
| Approved admin CIDRs | MinIO console TCP 9001 | Private administration |
| Alertmanager | Webhook receiver TCP 9080 | Controlled alert delivery |

Ports are initial test values and remain configurable. Deny wildcard exposure, arbitrary
pod egress, and access from an unapproved disposable probe. Use repository-managed pod
labels for NetworkPolicy selectors.

Docker Hub image pulls occur through the host container runtime and are not authorized by
pod NetworkPolicy. Record host-level registry endpoints separately from workload egress.

## Intended Ownership

Build on the current host automation rather than creating a second orchestration engine:

```text
execution/k3s/
  environments/<environment>/
    inventory.yml
    platform.yml
    secrets.sops.yml
  host/
    playbooks/
      host-data-services.yml
      external-platform-services.yml
    roles/
      data-services/                 # existing MariaDB and Redis ownership
      external-platform-services/   # MinIO and webhook receiver
  operations/
    platform-services/
      platform-services             # check/setup/migrate entry point
      README.md
```

Ansible owns target-host prerequisites, files, firewall rules, and service lifecycle.
Docker Compose owns the external platform service containers. k3s manifests own only
consumer references and NetworkPolicies, never these containers or their host paths.

The role must work against either the existing local `platform_host` or a dedicated
`platform_services` inventory host. Do not fork separate Compose definitions for each
placement profile; render one service model from environment inputs.

## Operator Interface

Provide a focused interface conceptually equivalent to:

```bash
./execution/k3s/operations/platform-services/platform-services check \
  --environment test
./execution/k3s/operations/platform-services/platform-services setup \
  --environment test --provision-host-services
./execution/k3s/operations/platform-services/platform-services migrate \
  --environment test --target-profile isolated-test
```

`check` validates configuration, SOPS inputs, target identity, listeners, health, and
protocol behavior without provisioning. `setup` is explicit and repeatable. `migrate`
must be a guarded workflow with source backup, target preflight, isolated restore,
consumer cutover, post-cutover checks, and a defined rollback point.

The ordinary k3s bootstrap may validate required external endpoints but must not silently
provision or migrate a separate services VM. Phase 6 should consume passing external
platform service evidence before applying add-ons that depend on MinIO or the webhook.

## Implementation Sequence

1. Add the external platform service schema and semantic validation.
2. Implement the co-located MinIO and webhook receiver with pinned images and SOPS inputs.
3. Add protocol probes, firewall validation, evidence, and second-apply checks.
4. Integrate Alertmanager delivery and restic S3 backup/restore acceptance tests.
5. Define a `platform_services` inventory group and provision a dedicated test VM.
6. Apply the unchanged service model to the isolated VM.
7. Migrate test state and switch only declared endpoints and allowed network inputs.
8. Re-run dependent Phase 3, Phase 5, Phase 6, reboot, and restore checks.
9. Move the backup repository outside the physical Proxmox failure domain before making
   an off-host recovery claim.

## Acceptance Tests

Prove for each active profile:

1. Configuration, encrypted secrets, Compose rendering, and image references validate.
2. Check mode does not mutate the target or create decrypted repository files.
3. First setup succeeds and an unchanged second setup preserves container identities.
4. Services bind only to declared private addresses and host firewall rules match inputs.
5. Allowed k3s consumers connect; an unlabeled pod and an unapproved LAN source cannot.
6. MariaDB and Redis authenticated probes pass without application-specific state.
7. MinIO object write/read/checksum/delete passes with the least-privilege backup identity.
8. Restic snapshot, integrity check, retention preview, isolated restore, and restored-data
   validation pass.
9. Alertmanager delivers a controlled identifier exactly as expected and the receiver is
   cleaned afterward.
10. Restarting containers and rebooting the services VM restore health without manual
    changes.
11. Logs, process arguments, temporary files, and evidence contain no decrypted secret.
12. Migration to the isolated profile preserves service contracts and has a proven
    rollback before source retirement.

For `co-located-development`, record physical and VM isolation as `not_qualified`. For
`isolated-test`, record VM isolation as passing but physical isolation as
`not_qualified`. Only `recovery-qualified` may pass the off-host storage requirement.

## Evidence And Completion

Write a redacted report under:

```text
execution/k3s/.evidence/<environment>/external-platform-services.json
```

Record the selected profile, target identity, desired-state hash, pinned images,
listeners, firewall summary, protocol checks, object-storage checks, alert delivery,
restic snapshot/restore results, first/second setup results, reboot result, migration
result when applicable, failure-domain qualification, and overall status. Never record
passwords, access keys, repository passwords, signed URLs, private keys, or decrypted
configuration.

The co-located profile completes when its functional and repeatability checks pass, but
it does not satisfy off-host recovery. The isolated profile completes when the same
desired state is reproduced on a separate VM and network boundaries pass. Recovery
qualification remains gated on backup storage outside the physical Proxmox host.

## Failure And Migration Rules

- Never delete or overwrite existing service data to make setup pass.
- Never adopt an unmanaged container, bucket, repository, or non-empty data directory
  implicitly.
- A failed apply stops dependent service changes and preserves healthy existing services.
- A failed backup or alert delivery does not restart MariaDB, Redis, or k3s.
- Do not cut consumers over until target protocol, authorization, backup, and restore
  checks pass.
- Keep the source services stopped but recoverable during the agreed rollback window;
  do not run writable source and target database instances concurrently.
- Retiring co-located services is a separate confirmed operation after rollback expiry.

## Relationship To Later Phases

- Phase 5 owns default-deny and baseline cluster policy; it does not provision these
  external services.
- Phase 6 owns the exact Alertmanager and backup NetworkPolicies and consumes the webhook
  and MinIO contracts from this plan.
- Phase 7 validates the integrated platform and reports actual failure-domain status.
- Phase 8 requires recovery-qualified backup storage before claiming clean-host recovery.
- Phase 9 publishes stable application-facing MariaDB/Redis interfaces without exposing
  credentials or infrastructure placement.