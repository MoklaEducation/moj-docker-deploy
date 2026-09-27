# Evolution and Failure Management

Status: implementation guidance for all deployment phases.

## Purpose

Define how the platform plans evolve when implementation reveals missing information,
invalid assumptions, environmental differences, or new failure modes. The objective is
not a perfect first implementation. It is a platform that becomes increasingly useful,
predictable, recoverable, and understandable through controlled iterations.

This guide applies to Phases 1-9 and to later upgrades. Phase documents describe the
intended behavior; implementation evidence determines whether those descriptions remain
correct.

[Strategy Visualizations](strategy-visualizations.md) provides a visual companion for
the phase, capability, maturity, ownership, failure, and evidence relationships below.

## Core Principles

1. Treat each plan as a versioned, testable hypothesis rather than an immutable design.
2. Change one ownership boundary at a time and validate it before expanding scope.
3. Prefer a small working path with explicit limitations over a broad partial system.
4. Turn every important discovery into code, validation, configuration, or documentation.
5. Fail before mutation when inputs, identity, ownership, or safety are uncertain.
6. Prefer deterministic roll-forward for declarative state; use rollback only when its
   state and data compatibility are proven.
7. A successful backup, deployment, or alert configuration is incomplete until its
   recovery or delivery path has been exercised.
8. Preserve exact evidence for failures as well as successes, without preserving secrets.
9. Keep one owner for every resource and operation across Ansible, Kustomize, Helm, shell,
   and any future GitOps controller.

## Iteration Unit

Implement each phase as a sequence of small capabilities. A capability should be narrow
enough to build, exercise, and revise in one short iteration, for example:

- establish one firewall rule group;
- deploy MariaDB with authentication but before backup scheduling;
- install one add-on release;
- validate one recovery artifact type;
- publish one application contract interface.

For every capability, follow this loop:

1. State the expected behavior and cheapest check that could disprove it.
2. Implement the smallest end-to-end path on a disposable test target.
3. Exercise the happy path and one likely failure path.
4. Capture commands, versions, timings, state transitions, and redacted output.
5. Classify each unexpected result using the failure model below.
6. Update implementation, tests, schema, plan, and runbook where applicable.
7. Run the same check again, then run a second apply/check for stability.
8. Rebuild from clean state before declaring the capability mature.

Do not defer all integration until every phase is implemented. After every major
ownership boundary, rerun the checks for its dependencies and consumers.

## Maturity Model

Track capability maturity explicitly:

| Level | Meaning | Required evidence |
| --- | --- | --- |
| 0: Defined | Inputs, owner, intended state, and acceptance check exist | Reviewed plan |
| 1: Demonstrated | Happy path works once in the test environment | First-run evidence |
| 2: Repeatable | Clean build and second apply are stable | Clean-run and idempotence evidence |
| 3: Failure-aware | Expected failures stop safely with useful diagnostics | Failure-path tests |
| 4: Recoverable | Resume, roll-forward, rollback, or rebuild behavior is proven | Recovery evidence |
| 5: Operable | Monitoring, alerts, limits, runbooks, and ownership exist | Operational evidence |
| 6: Reproducible | Another operator can execute it without hidden knowledge | Independent rehearsal |

A capability may enter routine test use at Level 3 or 4. It must reach the level required
by its phase completion gate before application readiness. Record limitations honestly;
do not describe an untested capability as recoverable or production-ready.

## Failure Classification

Every failure must be assigned one primary class. The class determines whether retry or
mutation is allowed.

| Class | Examples | Required behavior |
| --- | --- | --- |
| Invalid input | Missing field, invalid CIDR, incompatible options | Fail before mutation and identify the field |
| Missing dependency | Package, artifact, DNS record, secret reference unavailable | Fail with the missing dependency and owner |
| Unsupported target | Wrong OS, architecture, filesystem, or capacity | Fail in preflight |
| Identity mismatch | Wrong host, environment, cluster, or backup source | Fail closed; never repair automatically |
| Authentication | Expired or invalid credentials | Fail without retry or credential disclosure |
| Authorization | Insufficient or unexpectedly broad access | Fail and report the denied/unexpected action |
| Transient external | Temporary DNS, registry, mirror, or network failure | Bounded retry with backoff and timeout |
| Capacity | Disk, memory, inode, quota, or port exhaustion | Stop before existing services are destabilized |
| Partial mutation | Some steps completed before failure | Checkpoint state and provide a safe next action |
| Integrity | Digest, backup, schema, or restored-data mismatch | Stop and quarantine/reject the artifact |
| Policy | RBAC, pod security, network, or supply-chain violation | Fail until policy or an approved exception changes |
| Cleanup | Disposable resource or temporary state remains | Fail qualification and list retained resources |
| Unknown state | Outcome cannot be determined safely | Fail closed and require investigation |

Do not convert authentication, authorization, integrity, policy, identity, or unknown-state
failures into retries. Repetition does not make those conditions safer.

## Workflow Failure Contract

Each operator workflow must define:

- preconditions and postconditions;
- stable step and check identifiers;
- target/environment identity validation;
- whether each step is read-only, reversible, idempotent, or destructive;
- timeout and bounded retry policy;
- checkpoint and resume behavior;
- cleanup behavior for temporary resources;
- safe next actions for each expected failure;
- output and exit-code contract;
- evidence and redaction requirements.

Separate these operations when relevant:

- `check`: inspect prerequisites and current state without mutation;
- `plan`: resolve exact intended changes and immutable artifact/backup identifiers;
- `apply`: converge declared state;
- `validate`: prove behavior after convergence;
- `rollback`: return to a specifically identified compatible state;
- `recover`: rebuild or restore according to a reviewed recovery plan;
- `destroy`: remove only a verified disposable target.

An ordinary `apply` must never silently invoke destructive recovery, rotate credentials,
delete persistent data, reset k3s, or broaden access to make a check pass.

## Retry, Resume, Roll-forward, and Rollback

Use the following decision order after a failure:

1. **Retry** only when the operation is idempotent and the cause is demonstrably transient.
2. **Resume** only from a recorded checkpoint after revalidating target identity and
   completed postconditions.
3. **Roll forward** by correcting declared state when the current state is understood and
   convergence is safe.
4. **Rollback** only to a named known-good version after proving API, schema, data, and
   persistent-storage compatibility.
5. **Rebuild or restore** when state integrity is uncertain or the target cannot be safely
   converged.
6. **Stop for investigation** when ownership, identity, integrity, or effects are unknown.

Never blindly repeat database imports, k3s datastore replacement, persistent-volume
restores, destructive cleanup, or credential rotation.

## Discovery Management

Record material discoveries in a lightweight findings log. A finding is material when it
changes safety, ownership, repeatability, recovery, security, capacity, or an interface
consumed by a later phase.

Use this structure:

```text
ID:
Date:
Environment and target:
Phase and capability:
Repository revision and configuration hash:
Observed behavior:
Expected behavior:
Redacted evidence:
Failure class:
Immediate containment:
Decision and rationale:
Required code/config/test/document changes:
Owner and due date:
Status:
```

Resolve each finding through one or more durable outcomes:

- implementation correction;
- new or strengthened automated check;
- shared schema or environment configuration change;
- plan/runbook clarification;
- architecture decision record;
- measured operational limit;
- explicitly approved, time-bounded exception.

A command entered manually during diagnosis is not a completed fix. Encode it in the
owning automation or document it as a deliberate operator procedure with validation.

## Updating Plans and Contracts

When implementation contradicts a plan:

1. Preserve the failing evidence.
2. Determine whether the implementation, plan, or underlying architecture is wrong.
3. Identify affected owners and downstream phase contracts.
4. Update the smallest authoritative source first.
5. Update dependent implementation, validation, and documentation in the same change.
6. State whether existing evidence is invalidated.
7. Repeat the affected clean build or recovery test.

Use an architecture decision record when a change affects failure domains, ownership,
security boundaries, persistent-data authority, recovery strategy, public interfaces, or
the application contract. Minor implementation discoveries can remain in the findings
log and relevant phase plan.

## Cross-Phase Invariants

Preserve these invariants throughout evolution:

- Phase 1 owns the complete shared input schema.
- Host resources are owned by Ansible; repository Kubernetes resources by Kustomize;
  third-party add-on releases by Helm.
- Direct apply and a future GitOps controller never concurrently own the same object.
- Phase 4 bootstrap-admin credentials are not routine deployment credentials.
- MariaDB and Redis are outside k3s but remain in the same VM failure domain.
- Off-host backup and restore evidence are required for recoverability claims.
- Applications remain absent until the Phase 9 gate is open.
- A passing report is valid only for its recorded target, desired-state hash, versions,
  and evidence age.
- A breaking contract or recovery-path change invalidates dependent evidence.

## Test Cadence

Use the following minimum cadence:

| Event | Required test |
| --- | --- |
| Every focused implementation change | Owning capability check and second apply/check |
| Phase completion | Full phase acceptance tests |
| Every major ownership boundary | Dependent phase checks plus integration validation |
| Backup/storage/identity change | Targeted restore rehearsal |
| k3s/add-on upgrade | Upgrade, rollback assessment, reboot, and Phase 7 validation |
| Recovery workflow change | New clean-VM Phase 8 rehearsal |
| Application contract change | Phase 9 conformance and affected application validation |
| Before production promotion | Clean test deployment, Phase 7, and current recovery evidence |

Run an early Phase 8 rehearsal with synthetic data as soon as the first complete backup
chain exists. Finding recovery defects early is cheaper than postponing all recovery work
until the nominal implementation is complete.

## Exceptions and Technical Debt

An exception must include:

- affected check or invariant;
- reason it cannot be resolved now;
- risk and affected environments;
- compensating control;
- accountable owner;
- approval and expiry date;
- removal test and follow-up work.

Expired exceptions fail the relevant gate. Do not use exceptions for unknown state,
unverified backups, plaintext secrets, target identity ambiguity, or destructive-operation
guards. Those conditions always block progression.

Keep technical debt near the owning phase and link it to the finding that created it.
Prioritize debt that weakens recovery, security boundaries, observability, or deterministic
rebuilds over cosmetic or convenience improvements.

## Review Metrics

Use trends to decide whether the platform is improving:

- clean-build success rate and duration;
- second-apply unexpected change count;
- mean time to identify and recover from controlled failures;
- backup age and restore success rate;
- number and age of exceptions;
- manual undocumented interventions per run;
- cleanup failures and orphaned resources;
- secret-redaction failures;
- capacity headroom and growth rate;
- percentage of required checks automated;
- independent rehearsal success rate.

Metrics support decisions; they are not targets to game. A slower complete recovery test
is more valuable than a fast workflow that omits data-integrity validation.

## Phase Progression Decision

A phase may advance only when:

- its required maturity and acceptance checks pass;
- second apply/check has no unexplained changes;
- expected failures are bounded and actionable;
- cleanup succeeds;
- required evidence is current and redacted;
- no blocking or expired exception exists;
- ownership and downstream contracts remain valid;
- unresolved limitations are explicit and accepted.

If a later phase exposes an earlier defect, reopen the owning phase, invalidate affected
evidence, fix and requalify that boundary, then rerun only the downstream checks whose
assumptions changed. Do not preserve a false green status for schedule convenience.

## Desired Outcome

The system is useful when routine operations are predictable and unusual failures have a
safe path to diagnosis and recovery. Success does not mean failures disappear. It means
failures are bounded, visible, attributable, reproducible where practical, and converted
into durable improvements for the next iteration.