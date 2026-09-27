# Phase 7 Implementation Plan: Platform Validation

Status: ready for implementation after Phase 6 passes.

## Mission

Provide one repeatable acceptance workflow that evaluates the assembled host, data
services, k3s cluster, cluster core, and add-ons as a platform. Aggregate stable checks
from prior phases, add cross-layer failure scenarios, and produce one redacted release
candidate report that determines whether recovery qualification may begin.

Phase 7 validates existing desired state. It does not repair drift, apply configuration,
deploy applications, or substitute for Phase 8 clean-host recovery.

## Preconditions

- Passing current evidence exists for Phases 1-6 for the same environment, host, cluster
  identity, repository revision, and declared configuration hash.
- No pending reboot, failed backup, active upgrade, unresolved add-on rollout, or expired
  exception exists.
- The operator can access the restricted validation identity and approved administrative
  endpoints.
- An allowed external probe location and, where feasible, a denied-source probe are
  available.
- Test notifications and staging certificate operations are authorized.

Stale or mismatched evidence is a failure, not a warning. Define maximum evidence age per
phase in the shared schema.

## Goals

1. Expose one non-mutating operator command for complete platform acceptance.
2. Reuse prior check implementations by stable ID rather than duplicating them.
3. Test cross-layer behavior and bounded fault scenarios.
4. Verify security exposure, secret absence, capacity headroom, and backup freshness.
5. Produce human-readable and machine-readable reports tied to exact desired state.
6. Block Phase 8 on failed required checks or unapproved/expired exceptions.

## Intended File Ownership

```text
execution/k3s/operations/validate/
  validate-platform.sh
  check-registry.yml
  scenarios/
    host-reboot.sh
    service-restart.sh
    alert-route.sh
    certificate.sh
    network-boundaries.sh
    backup-failure.sh
  schemas/
    validation-report.schema.json
  templates/
    platform-validation.md.j2
```

`check-registry.yml` maps stable check IDs to owning phase commands, severity, timeout,
required evidence, and remediation owner. Phase 7 orchestrates; the owning phase remains
the source of truth for each detailed check.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh validate --environment test
```

Support:

- `--output <ignored-directory>`;
- `--scenario <id>` for a scoped rerun;
- `--skip-disruptive` only for development diagnostics, never for a qualifying report;
- `--explain <check-id>` to show purpose and remediation without running it.

Validation is read-only except for bounded disposable probes and explicitly named fault
scenarios. Every mutating scenario must restore prior state in a trap/finalizer and report
cleanup success.

## Validation Domains

### Provenance and desired state

- Record repository commit, dirty status, environment/schema versions, host identity,
  configuration hashes, image digests, chart versions, and k3s version.
- Fail qualification on a dirty implementation worktree unless an explicit test-only
  override is recorded.
- Compare live managed resources and host configuration hashes with declared state.
- Detect unmanaged or duplicate ownership for core/add-on resources.

### Host and data services

- Re-run Phase 1 host suitability checks that remain meaningful after convergence.
- Verify SSH/firewall/time/disk/journal/Docker/k3s systemd health and no pending reboot.
- Verify MariaDB/Redis version, digest, TLS/authentication, allowed/denied connectivity,
  storage capacity, and last backup status.
- Verify no unexpected public listener or Docker-published data-service port exists.

### Cluster and policies

- Verify API, node, DNS, ingress, ServiceLB, storage, and all system/add-on workloads.
- Re-run RBAC allow/deny tests using restricted identities.
- Exercise default-deny and specifically allowed network flows with disposable probes.
- Verify quota/limit/pod-security policy and local-path reclaim behavior.
- Detect mutable images and workloads missing required requests/limits.

### Certificates and ingress

- Validate staging certificate status, SAN, chain, expiry, issuer, and HTTPS response.
- Verify expiry alerts and renewal evidence or an unexpired approved exception.
- Test Traefik health and trusted-proxy/TLS policy without deploying an application.

### Observability and alerting

- Verify all required Prometheus targets, rule evaluation, Alertmanager route, Grafana
  data sources/dashboards, Alloy collection, and Loki query health.
- Generate a unique harmless marker and locate the corresponding metric/log evidence.
- Send one controlled alert and confirm receipt at the external destination.
- Verify monitoring blind-spot and backup-freshness alerts are loaded.
- Run a secret-shaped canary through an isolated test logger and prove redaction/drop;
  never use a real secret.

### Backup and capacity

- Verify latest host, MariaDB/Redis, k3s state, and Kubernetes backup artifacts are
  off-host, fresh, integrity-checked, and covered by retention policy.
- Do not perform a full restore; verify the latest Phase 3 isolated restore and Phase 6
  namespace restore evidence are current.
- Measure CPU, memory, root/storage filesystem, PVC, image, log, and backup growth.
- Calculate remaining capacity against the declared application reserve and fail if
  below threshold.

## Required Fault Scenarios

Run on the disposable test environment only:

1. Reboot the host and verify Docker data services, k3s, core, and add-ons recover within
   the configured time.
2. Restart MariaDB, Redis, k3s, and one selected add-on independently and verify bounded
   recovery plus expected alert behavior.
3. Force one backup upload failure using a test repository/credential, verify non-zero
   status and alerting, then restore valid configuration and complete a successful backup.
4. Attempt forbidden RBAC and network actions and verify denial.
5. Roll back one reversible non-stateful add-on configuration change to the recorded
   known-good revision.

Do not simulate disk corruption, delete data, rotate production credentials, or interrupt
the only production environment in Phase 7.

## Check and Exception Model

Each result contains stable ID, owner phase, severity, status, start/end time, evidence,
and remediation. Status is `pass`, `fail`, `warning`, `not_applicable`, or `exception`.

An exception requires:

- exact check ID and reason;
- approver/owner;
- creation and expiry date;
- compensating control;
- follow-up task;
- explicit statement whether it blocks production.

Expired, missing-owner, or production-blocking exceptions fail qualification. Warnings do
not fail automatically but must appear prominently in the report.

## Report and Security Contract

Produce JSON conforming to `validation-report.schema.json` and a rendered Markdown
summary under the ignored evidence directory. Include exact inputs, all check results,
timings, fault scenarios, capacity, backup ages, exceptions, and overall decision.

Calculate a SHA-256 digest of each report. Optionally sign the digest when an accepted
operator signing mechanism exists. Never include kubeconfigs, tokens, private keys,
passwords, secret manifests, authorization headers, cookies, database rows, or sensitive
logs. Scan reports for known secret values and secret-shaped patterns before finalizing.

## Idempotence and Failure Behavior

- Repeated validation against unchanged healthy state yields the same outcome apart from
  timestamps and measured values.
- Every disposable resource has a unique prefix and deterministic cleanup.
- Cleanup failure makes the scenario fail and lists retained resources.
- A failed check does not trigger automatic repair or continue into Phase 8.
- Timeouts are explicit per check; hung checks terminate and fail with diagnostic context.
- Parallel checks may run only when they cannot alter or overload shared state.

## Implementation Sequence

1. Define the report schema, stable check registry, severity rules, and evidence-age
   policy.
2. Wrap prior phase checks without duplicating their logic.
3. Add cross-layer external exposure, provenance, secret, and capacity checks.
4. Add bounded fault scenarios and cleanup guards.
5. Add report rendering, digesting, redaction scanning, and exit-code aggregation.
6. Run one failing fixture, one cleanup-failure fixture, and one complete passing test
   environment qualification.

## Acceptance Tests

Prove:

1. Healthy unchanged platform produces overall `pass` and exit code 0.
2. Any required check failure produces non-zero and identifies owner/remediation.
3. Stale/mismatched phase evidence is rejected.
4. All required fault scenarios recover and clean up.
5. External allowed/denied, RBAC, certificate, alert, log-redaction, backup, and capacity
   checks produce direct evidence.
6. A seeded secret value never appears in generated output.
7. Reports validate against schema and their digests verify.
8. Validation makes no persistent desired-state change.

## Completion Gate

Phase 7 completes only when one full, non-skipped test-environment run passes against the
exact committed desired state, all disruptive scenarios clean up, application capacity
headroom remains, reports are redacted and verifiable, and no blocking exception exists.

## Non-Goals

- Repairing drift, installing components, full clean-host restore, application testing,
  production cutover, penetration testing, or destructive disaster simulation.