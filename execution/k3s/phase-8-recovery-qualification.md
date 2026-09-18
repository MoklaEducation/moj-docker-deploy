# Phase 8 Implementation Plan: Recovery Qualification

Status: ready for implementation after Phase 7 passes.

## Mission

Prove that the complete platform can be recovered onto a clean supported VM using only
the repository, approved external secrets, and off-host backups. Measure recovery point
and recovery time, validate restored state end to end, and turn every required manual
decision into a documented input or automated step.

This rehearsal is destructive only to a dedicated recovery target. It must not modify,
stop, restore over, or redirect traffic to the source environment.

## Recovery Objectives

Define and approve before implementation:

- RTO start: declaration that the source platform is unavailable;
- RTO stop: Phase 7 validation passes on the recovered target;
- separate RPO targets for MariaDB, Redis when persistent, k3s state, Kubernetes
  persistent data, and encrypted desired-state secrets;
- maximum acceptable age for each backup type;
- minimum data-integrity checks and allowed data loss;
- recovery owner, observer, approver, and abort authority.

Do not invent target values in automation. Store non-secret objectives in the environment
schema and report measured results against them.

## Preconditions

- A complete Phase 7 report passes for the source environment and exact repository
  revision.
- Required off-host snapshots exist, are integrity-checked, and meet declared freshness.
- A new Ubuntu 24.04 LTS x86_64 VM meets Phase 1 sizing/network requirements.
- The recovery VM has a distinct identity, isolated DNS names, and no route by which it
  can receive production traffic.
- Required SOPS age keys, restic credentials, ACME/notification credentials, k3s token,
  and other external secrets are available through the approved operator channel.
- The operator has console access and can destroy/recreate only the recovery VM.
- The exact pinned k3s version and dependency artifacts remain available.

## Recovery Modes and Authority

The runbook must distinguish:

- **Rebuild:** reproduce packages, users, firewall, Docker, k3s binaries, manifests,
  charts, and configuration from repository-owned desired state.
- **Restore:** recover authoritative runtime state that cannot be reconstructed, including
  MariaDB logical data, persistent Redis data when configured, k3s server identity/state,
  and selected persistent volumes.
- **Reissue:** recreate recoverable external artifacts such as staging certificates when
  restoration is neither required nor safer than issuance.

For every artifact, record exactly one authoritative source and one owner. Never combine
an old rendered configuration with a different repository revision or silently select
the newest backup independently for each layer.

## Intended File Ownership

```text
execution/k3s/operations/recovery/
  recover-platform.sh
  plan-recovery.sh
  inventory-backups.sh
  validate-target.sh
  destroy-target.sh
  runbooks/
    platform-recovery.md
    k3s-state.md
    data-services.md
    persistent-volumes.md
    secret-recovery.md
  schemas/
    recovery-plan.schema.json
    recovery-report.schema.json
```

Reuse Phase 1-7 commands. Recovery orchestration owns ordering and evidence, not duplicate
host, backup, restore, or validation implementations.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh recover plan \
  --source-environment test \
  --target-environment recovery-test \
  --target-host <recovery-host> \
  --recovery-point <timestamp>

./execution/k3s/bootstrap.sh recover execute \
  --plan <ignored-plan.json> \
  --confirm-target <recovery-host-identity>
```

`plan` is read-only. It resolves candidate snapshots, verifies compatibility/freshness,
and emits a reviewable plan with immutable backup IDs. `execute` accepts only that plan;
it must never choose newer snapshots implicitly.

## Destructive Guards

- Require an environment flag marking the target as disposable recovery infrastructure.
- Resolve and compare machine ID, SSH host key fingerprint, IPs, DNS names, k3s node ID,
  and backup source identity. Abort on any source/target overlap.
- Require an exact target identity confirmation separate from command invocation.
- Refuse production environment names, known production IPs/DNS, mounted source backup
  paths, and any target already serving traffic.
- Never use broad SSH host-key bypass. Trust the new target fingerprint explicitly.
- Keep DNS and outbound notification/ACME behavior in recovery-test mode. Route alerts to
  a test receiver and use staging issuers.
- Default every cleanup/destruction operation to dry-run and require the same identity
  checks as execution.
- Abort without cleanup of evidence when a safety check fails.

## Recovery Plan

The immutable plan records:

- source and target identities;
- repository revision, environment/schema version, and k3s version;
- recovery point and timezone;
- exact restic snapshot/object IDs and checksums for host/k3s, MariaDB, Redis,
  Kubernetes objects, and selected volumes;
- consistency relationships and known skew among snapshots;
- required keys/credentials by reference, never value;
- ordered steps, expected duration, validation, rollback/abort point, and owner;
- expected RPO per data class.

Fail planning when snapshots are missing, stale, incompatible, corrupt, or ambiguously
associated with the source environment.

## Recovery Sequence

1. Start the RTO clock and capture target identity/safety evidence.
2. Run Phase 1 preflight against the clean target.
3. Apply the Phase 2 host baseline without copying mutable source-host state.
4. Restore Phase 3 MariaDB/Redis backup artifacts into staging directories and verify
   checksums before starting primary target services.
5. Deploy pinned empty data-service containers, import MariaDB logical dumps, restore
   Redis persistence only when policy requires it, and run Phase 3 integrity checks.
6. Install the exact pinned k3s binary/configuration with service startup controlled for
   restoration. Restore server token, configuration, certificates, and SQLite/state only
   from their coherent snapshot using the procedure supported by that pinned k3s version.
7. Verify recovered cluster identity, API health, node identity expectations, and no
   references that could affect the source environment.
8. Reconcile Phase 5 core and Phase 6 add-on desired state from the exact repository
   revision. Restore selected Kubernetes objects/volumes only where the recovery matrix
   marks backup state authoritative.
9. Reissue staging certificates where policy chooses reissue; keep notifications routed
   to test endpoints.
10. Run data integrity markers, Kubernetes object/PVC checks, then the complete Phase 7
    validation workflow against the recovery target.
11. Stop the RTO clock only when all required validation checks pass.
12. Preserve evidence and either retain the isolated target for approved investigation or
    destroy it through the guarded cleanup workflow.

## k3s State Requirements

- Restore only into the same exact k3s version first; upgrades occur after qualification.
- Treat the server token, SQLite datastore, server TLS material, and required config as a
  coherent recovery set.
- Follow the documented procedure for the pinned k3s release, including service stop,
  ownership/mode restoration, and startup ordering.
- Never merge source and newly generated server identity material.
- If direct k3s-state restoration cannot be proven reliable, fail Phase 8. Reconstructing
  only repository objects is a separate disaster strategy and must be explicitly approved
  with its state-loss implications.

## Data and Persistent Volume Requirements

- Restore MariaDB only from logical dumps and verify schema, table counts/checksums, users,
  TLS, and known non-sensitive marker records.
- For persistent Redis, verify persistence mode, keyspace statistics, TTL behavior, and
  marker values. For disposable Redis, prove a healthy empty instance and document the
  expected loss.
- Restore only explicitly inventoried Kubernetes PVCs. Validate ownership, modes,
  checksums/application-level markers, and that no source host path is referenced.
- Do not infer cross-service transactional consistency. Report snapshot skew and validate
  against the approved consistency model.
- Keep all recovered endpoints inaccessible from unintended networks.

## Secret Recovery

- Decrypt SOPS inputs only on the trusted controller or target as defined by prior phases.
- Restore runtime-generated secrets only if the recovery matrix declares them
  authoritative; otherwise regenerate/reissue them and update dependent state safely.
- Verify permissions and successful use without printing values.
- Scan process arguments, journals, reports, shell tracing, temporary files, and command
  output for secret leakage.
- Rotate test credentials after the rehearsal if exposure cannot be ruled out.

## Failure and Resume Behavior

- Record each step as not started, running, passed, failed, or cleaned up in a checkpoint
  file tied to plan hash and target identity.
- Resume only from explicitly idempotent boundaries after rechecking identity and prior
  artifacts. Database imports and k3s state replacement must not be blindly repeated.
- A failed integrity check stops recovery before dependent layers start.
- Do not alter the source environment to make the rehearsal pass.
- Manual interventions are timestamped with actor, reason, command/action, and result.
  Any undocumented host mutation fails qualification even if final validation passes.

## Acceptance Tests

Prove:

1. Planning is read-only and pins exact compatible snapshots.
2. Source/target overlap and production-target fixtures are rejected.
3. A clean VM reaches the declared host state with no image or manual preparation.
4. MariaDB and configured Redis state meet integrity and RPO checks.
5. k3s identity/state, core resources, add-ons, selected PVCs, and staging certificates
   recover or reissue according to the recovery matrix.
6. The complete Phase 7 workflow passes on the recovered target.
7. Measured total and step-level recovery times meet RTO.
8. No source traffic, data, backup, or service is modified.
9. No plaintext secret enters Git, evidence, logs, process arguments, or retained files.
10. A second rehearsal from a newly created VM follows the same documented workflow;
    before Phase 9, at minimum rerun planning and target guards plus one full rehearsal
    after any recovery-path change.

## Evidence and Completion Gate

Write `execution/k3s/.evidence/<target-environment>/phase-8-recovery.json` plus a Markdown
timeline. Include plan/report hashes, source/target identities, immutable backup IDs and
ages, measured RTO/RPO, step timings, data/cluster validation, manual interventions,
cleanup status, and final decision. Reference but do not copy sensitive earlier evidence.

Phase 8 completes only when a clean-host rehearsal passes Phase 7, meets every approved
RTO/RPO, uses no undocumented mutation, preserves source isolation, leaks no secret, and
leaves a reproducible runbook reviewed by the recovery owner.

## Non-Goals

- Production failover, DNS cutover, HA, in-place source repair, application data beyond
  currently declared platform state, or changing backup/retention policy during recovery.