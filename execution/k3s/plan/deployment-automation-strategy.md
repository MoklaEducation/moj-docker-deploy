# Deployment Automation Strategy

Status: proposed architecture and migration plan.

## Purpose

Define a simpler, faster, and more reliable operator interface for deploying and
validating the k3s platform without weakening the existing phase ownership, safety, or
evidence boundaries.

The current implementation has successfully built a repeatable Phase 1-6 platform. The
next automation iteration should improve operator experience and execution efficiency,
not replace working Ansible, Docker Compose, Kustomize, Helm, SOPS, or phase validation.

## Current State

The public interface is:

```bash
./execution/k3s/bootstrap.sh check --environment test --through cluster-addons
./execution/k3s/bootstrap.sh apply --environment test --through cluster-addons
```

`bootstrap.sh` runs phases sequentially:

```text
preflight
  -> host baseline
  -> host data services
  -> k3s installation
  -> cluster core
  -> cluster add-ons
```

This design has important strengths:

- one public entry point;
- explicit `check` and `apply` behavior;
- phase dependencies fail closed;
- desired state remains version-controlled;
- every phase owns its resources and evidence;
- Ansible, Kustomize, and Helm are used where each fits best;
- SOPS/age protects committed secret sources; and
- repeat application has demonstrated stable state.

The main limitations are now in orchestration:

- checking a late phase reruns every earlier phase;
- routine health checks and full desired-state checks are coupled;
- the shell orchestrator manually threads many temporary files and exit statuses;
- phase entry points use inconsistent argument conventions;
- environment and SOPS setup must be repeated in each shell;
- terminal output is long while the final operator summary is small;
- Phase 6 deterministic validation downloads and renders each chart twice; and
- evidence is phase-specific but lacks one common run identity and summary.

The phase model should be retained. The orchestration around it should evolve.

## Recommended Commands Today

This strategy document is located at:

```text
execution/k3s/plan/deployment-automation-strategy.md
```

The current supported operator entry point remains:

```text
execution/k3s/bootstrap.sh
```

Run commands from the repository root. Prepare each new operator shell with:

```bash
ENVIRONMENT="test"
K3S_DIR="$PWD/execution/k3s"

export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

./execution/k3s/operations/setup/controller.sh check
test -r "$SOPS_AGE_KEY_FILE"
sops --decrypt "$K3S_DIR/environments/$ENVIRONMENT/secrets.sops.yml" >/dev/null
```

For an occasional complete test-cluster installation or reconciliation:

```bash
./execution/k3s/bootstrap.sh apply \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

Verify the resulting platform with the complete read-only check:

```bash
./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

For routine quick inspection before the future `status` command exists:

```bash
systemctl is-active k3s docker
docker ps
k3s kubectl \
  --kubeconfig "$K3S_DIR/environments/$ENVIRONMENT/.generated/cluster-addons.kubeconfig" \
  get nodes
k3s kubectl \
  --kubeconfig "$K3S_DIR/environments/$ENVIRONMENT/.generated/cluster-addons.kubeconfig" \
  get pods -A
```

Generated evidence is written beneath:

```text
execution/k3s/.evidence/<environment>/
```

The current commands are the recommended path for occasional test installations. The
automation redesign is an optimization for speed, ergonomics, structured evidence, and
multiple environments; it is not a prerequisite for continuing to use the existing
test-cluster workflow.

## Recommended Commands After Migration

Stages 1-3 should expose these preferred commands from the repository root:

```bash
mise run status
mise run check
mise run apply
mise run validate
mise run history
```

Mise should delegate to the runner rather than contain deployment logic. The equivalent
direct interface should remain available for automation and diagnosis:

```bash
python3 execution/k3s/platformctl.py status --environment test
python3 execution/k3s/platformctl.py check --environment test
python3 execution/k3s/platformctl.py apply --environment test
python3 execution/k3s/platformctl.py validate --environment test
```

During migration, `execution/k3s/bootstrap.sh` remains a compatibility entry point. Do
not remove it until direct bootstrap, `platformctl`, and Mise executions have proven
equivalent behavior and exit codes.

## Current Flaws, Existing Safeguards, and Mitigations

The following distinguishes observed implementation limitations from risks that are
already partly controlled. Existing safeguards should be preserved during migration.

| Current flaw or risk | Existing safeguard | Residual problem | Recommended mitigation |
| --- | --- | --- | --- |
| A late-phase command reruns every earlier phase. | Sequential execution proves dependencies before continuing. | Routine checks are slow and one transient early dependency prevents inspecting a later phase. | The Python phase registry validates reusable dependency evidence and runs a cheap live prerequisite check; `--fresh` retains the complete path. |
| There is no fast whole-platform status command. | Individual systemd, Docker, Kubernetes, and phase checks exist. | Operators must remember several commands or run the much slower cumulative check. | `platformctl status`, exposed by `mise run status`, composes only safe live-health primitives and reports the owning phase for failures. |
| The public command requires repeated environment and SOPS shell setup. | Phase 1 fails closed when the identity is missing or cannot decrypt the secret file. Some scoped helpers already default to the environment identity path. | The main workflow remains easy to invoke incorrectly in a fresh shell. | Mise supplies repository-derived defaults; the runner validates paths before execution. Production still requires explicit environment selection. |
| `bootstrap.sh` manually manages phase-specific temporary files, traps, subprocess statuses, and reports. | `set -euo pipefail`, restrictive temporary secret permissions, and explicit status checks prevent many silent failures. | Complexity grows with each phase, cleanup declarations are repeated, and behavior is difficult to test as one unit. | `platformctl` owns one mode-`0700` run directory, one cleanup lifecycle, typed subprocess results, and atomic report publication. |
| Phase scripts use different positional and named command interfaces. | Every current wrapper validates its arguments before calling the implementation. | Adding a phase requires custom wiring and increases the chance of passing arguments or report paths incorrectly. | Introduce a versioned common phase contract with named inputs and stable exit codes while retaining compatibility wrappers. |
| Phase 6 validation renders twice and reacquires every chart for each render. | Every download is pinned by URL and SHA-256, and duplicate rendering proves determinism. | Healthy repeated checks perform unnecessary network transfers and become dependent on upstream availability. | Cache archives by SHA-256, verify cached bytes on every use, and render twice from the same verified immutable archive. |
| Evidence files do not share a top-level run identity or consolidated summary. | Each phase emits redacted JSON and records selected prerequisite status. Some reports preserve prior mutating smoke evidence. | Correlating one end-to-end execution, its logs, and its exact phase results is cumbersome. | Allocate a run ID and run directory, preserve phase reports, and atomically write one index and summary referencing their hashes. |
| Evidence freshness and invalidation rules are not yet uniformly enforced. | Later phases require a passing predecessor report and capture selected config/render hashes. Phase 7 explicitly requires current matching evidence. | A passing report alone does not prove that every relevant input, host boot, dependency, or maximum-age condition still matches. | Canonical phase fingerprints include config, repository, host, cluster, boot, dependency, and age fields; mismatches invalidate that phase and its dependants. |
| No environment-scoped operation lock prevents two applies or an apply and validation from overlapping. | Apply operations are sequential inside one bootstrap process. | Two independently started processes can still race over Helm, Ansible, evidence, or disposable probes. | Acquire an environment-scoped `flock` before mutation or qualification and report the active run rather than waiting indefinitely. |
| Console output is verbose but the final summary is sparse. | Detailed Ansible and validation output is available for diagnosis. | Important phase state is difficult to scan, and terminal logs are not grouped by one run. | Default to a concise phase table, store complete logs under the run directory, and provide `--verbose` and `--json`. |
| Report writing is not governed by one atomic publication contract. | Report generators validate and redact selected data before writing; secret-pattern guards exist in later phases. | Interruption or disk failure can leave inconsistent current evidence, and redaction behavior is not expressed through one shared interface. | Write temporary reports, validate schema and redaction, `fsync` where required, rename atomically, then update the run index. |
| Tool setup is split between host packages, the controller virtual environment, and custom download logic. | Versions and checksums are pinned, and `controller.sh check` validates the active toolchain. | Operators must know which setup path owns each command, and local/CI activation can differ. | Mise initially activates the existing toolchain; move installation ownership only after equivalent version and checksum validation is proven. |
| Deterministic checks are primarily exercised manually on the controller. | Focused Python tests and shell validation already exist. | Configuration and rendering defects may be found only during a live operator run. | CI runs secret-free schema, unit, shell syntax, and deterministic render checks; live convergence remains separately controlled. |

These recommendations do not claim to eliminate infrastructure failure. They reduce
avoidable operator error, repeated work, ambiguous evidence, and orchestration races
while preserving the existing fail-closed behavior.

## What the Recommendation Adds

### Mise adds convenience, not deployment intelligence

Mise addresses command length, environment activation, task discovery, and local/CI tool
consistency. It does not decide whether old evidence is safe, whether a certificate is
healthy, or whether live Kubernetes state can be skipped. Those decisions remain in the
runner and phase implementations.

### The Python runner adds reliable orchestration, not another configuration system

`platformctl` reads the existing environment and release configuration. It does not
invent another source of desired state. Its value is explicit dependency evaluation,
structured subprocess handling, locking, run identity, evidence validation, and concise
reporting.

### The common phase contract preserves isolation

Each phase continues to own its configuration, resources, checks, and detailed evidence.
The common contract removes custom invocation wiring; it does not merge phases or permit
one phase to mutate another phase's resources.

### Evidence reuse adds speed without replacing live checks

Fingerprint-based reuse avoids deep reruns only when identity, inputs, dependencies,
status, and age match. Lightweight live health remains mandatory before apply, and full
fresh validation remains mandatory for qualification.

### Immutable artifact caching removes network repetition, not verification

Charts and controller artifacts are cached by their declared digest. Every consumption
still verifies the digest, so caching improves speed and upstream outage tolerance
without accepting mutable downloads.

### CI adds earlier feedback, not an exclusive control plane

CI catches deterministic defects before merge. It does not become the only deployment or
recovery mechanism, and it receives no production secret material until a separately
reviewed trusted-runner design exists.

## Remaining Risks After Adoption

The proposed architecture does not solve:

- single-node downtime or physical host loss;
- unqualified off-host backup and restore;
- application-specific deployment, migration, and rollback behavior;
- incorrect desired-state decisions that pass their current tests;
- compromise of the trusted controller or age identity; or
- upstream defects in k3s, charts, images, Ansible collections, or operating-system
  packages.

Those risks remain owned by capacity, security, backup, recovery, application, and
upgrade plans. Automation should expose them clearly rather than implying that a shorter
command makes the platform highly available or production-ready.

## Desired Operator Experience

The routine interface should be small and discoverable:

```bash
mise run status
mise run check
mise run apply
mise run validate
mise run history
```

Scoped development and remediation should remain possible:

```bash
mise run phase:check cluster-addons
mise run phase:apply cluster-addons
mise run scenario certificate
```

Production-affecting operations must remain explicit:

```bash
mise run apply -- --environment production
mise run reboot -- --environment production --confirm
mise run restore -- --environment production --target TARGET --confirm
```

The exact syntax can change during implementation, but the distinction between fast
status, drift checking, convergence, qualification, and recovery must remain clear.

## Operation Classes

### Status

A fast, read-only operational snapshot. It checks current service health without proving
that all desired state and evidence contracts are current.

Examples:

- Docker and k3s systemd state;
- Docker container health;
- Kubernetes node and workload readiness;
- PVC, certificate, Prometheus, Alertmanager, Loki, and Alloy health; and
- pending reboot state.

Target duration should be seconds, not minutes.

### Check

A non-mutating desired-state and drift evaluation. It validates configuration, secret
availability, host state, rendered resources, live resource drift, and dependency
evidence.

`check` may safely reuse prior dependency evidence only when its repository revision,
input fingerprint, environment, host identity, boot identity, status, and maximum age
remain valid.

### Apply

Converge declared state in dependency order. Apply operations remain sequential,
idempotent, and fail closed. They may skip a dependency only when current evidence and a
lightweight live prerequisite check both pass.

### Validate

Run Phase 7 platform qualification. This is intentionally slower and includes bounded
probes and approved disruptive scenarios. It must not be reduced to a cached task.

### Recover

Back up, restore, rebuild, and upgrade remain separate explicit operations with stronger
confirmation and evidence requirements than ordinary apply.

## Compared Approaches

### 1. Continue With the Current Shell Orchestrator

Description: keep adding phases and flags directly to `bootstrap.sh`.

Advantages:

- no migration cost;
- no new runtime dependency;
- current behavior is understood and tested; and
- shell is appropriate for invoking external tools.

Disadvantages:

- control flow and cleanup complexity grow with every phase;
- structured dependency and evidence decisions are awkward;
- reusable phase selection and resumability become fragile;
- tests require extensive subprocess fixtures; and
- operator output remains difficult to summarize consistently.

Assessment: acceptable as a compatibility layer, but not the preferred long-term
orchestrator.

### 2. Mise Tasks Only

Description: define all phase logic and dependencies directly as Mise tasks.

Advantages:

- short commands and built-in task discovery;
- repository-scoped environment variables;
- tool version management;
- static task dependencies;
- consistent local and CI entry points; and
- low initial implementation effort.

Disadvantages:

- live infrastructure state cannot safely be modeled only through file timestamps;
- evidence freshness and identity matching still require scripts;
- conditional dependency reuse becomes complicated task-shell logic;
- task definitions can become another large orchestration program; and
- locking, atomic reports, resume state, and structured summaries require helpers.

Assessment: excellent operator facade, insufficient as the only orchestration engine.

### 3. Python Runner Only

Description: replace shell orchestration with a repository-owned `platformctl` Python
command.

Advantages:

- strong structured-data and error handling;
- testable dependency and evidence rules;
- atomic files, run IDs, locking, and cleanup are straightforward;
- concise terminal summaries and detailed log capture;
- safe phase selection and resumability; and
- no additional language beyond the existing controller Python environment.

Disadvantages:

- command discovery and tool installation must be implemented or documented;
- environment setup still needs a wrapper;
- careless expansion could create a bespoke deployment framework; and
- migration effort is higher than adding task aliases.

Assessment: suitable for orchestration correctness, but less convenient than Mise as the
human-facing interface.

### 4. Mise Plus a Small Python Runner

Description: use Mise for commands, environment, and tool setup; use a small Python
runner for phase dependencies, evidence, and execution policy.

Advantages:

- short, discoverable commands;
- one repository-defined environment;
- structured, testable orchestration;
- phase implementations remain independent;
- safe evidence reuse can improve execution time;
- the current bootstrap interface can remain compatible; and
- responsibility is clear: Mise launches; Python decides; existing tools converge.

Disadvantages:

- two thin integration layers must be maintained;
- contributors need Mise for the preferred interface; and
- boundaries must be enforced so logic does not split arbitrarily between TOML and
  Python.

Assessment: recommended.

### 5. Make, Just, or Taskfile

Description: use a general task runner instead of Mise.

Advantages:

- all can provide short aliases;
- Make is widely installed;
- Just has simple command recipes; and
- Taskfile provides YAML tasks and dependencies.

Disadvantages:

- Make's timestamp model is unsafe for live infrastructure state;
- Just adds command convenience but little tool management;
- Taskfile adds another runtime without a material advantage here; and
- none removes the need for structured evidence-aware orchestration.

Assessment: viable facades, but Mise is a better fit because it is already used on the
controller and combines tasks, environment setup, and tool versions.

### 6. Ansible-Only Orchestration

Description: move Kubernetes and add-on orchestration into Ansible roles and playbooks.

Advantages:

- one execution engine;
- mature inventory, handlers, check mode, and task reporting; and
- existing host automation already uses Ansible.

Disadvantages:

- Helm and Kubernetes resources become indirect and harder to inspect;
- rich validation and evidence logic still needs custom modules or scripts;
- cluster ownership boundaries become less obvious; and
- Ansible check mode cannot fully predict all Kubernetes and Helm behavior.

Assessment: retain Ansible for host convergence, not as the universal platform engine.

### 7. GitOps With Flux or Argo CD

Description: continuously reconcile Kubernetes resources from Git.

Advantages:

- strong Kubernetes deployment audit trail;
- automatic drift reconciliation;
- clear application promotion workflows; and
- mature health and synchronization models.

Disadvantages:

- it cannot prepare the host, deploy external Docker services, or install k3s before the
  cluster exists;
- it introduces controllers, credentials, CRDs, and recovery dependencies;
- it changes resource ownership for Phase 5 and Phase 6; and
- it is excessive for current single-operator platform bootstrap.

Assessment: defer. Reconsider for application delivery after the application-ready
handoff, not as a replacement for host and cluster bootstrap.

### 8. Terraform or OpenTofu

Description: model VM, network, DNS, and provider infrastructure as declarative state.

Advantages:

- appropriate if VM and external infrastructure provisioning enters scope;
- plans infrastructure changes before apply; and
- integrates well with provider APIs.

Disadvantages:

- it does not replace host configuration or Kubernetes workload management;
- state storage and credentials add operational requirements; and
- the current repository starts from an existing supported host.

Assessment: use separately if infrastructure provisioning becomes a requirement. Do not
use it to replace the current host and cluster configuration tools.

### 9. CI/CD Pipeline as the Primary Runner

Description: execute deployment directly from GitHub Actions or another CI platform.

Advantages:

- repeatable execution environment;
- review and approval integration;
- durable logs; and
- natural offline test and policy gates.

Disadvantages:

- private network access requires a trusted self-hosted runner;
- production credentials and recovery access become CI dependencies;
- interactive recovery is awkward; and
- CI does not itself solve phase orchestration.

Assessment: use CI for offline validation immediately. Add controlled live deployment
only after runner security, approvals, concurrency, and secret delivery are designed.

## Decision

Adopt a hybrid architecture:

```text
operator or CI
  -> Mise task facade
     -> platformctl phase runner
        -> existing phase-owned implementations
           -> Ansible for host state
           -> Docker Compose for external services
           -> Kustomize for cluster core
           -> Helm for add-ons
           -> Python and shell for validation
        -> versioned, redacted evidence
```

Mise owns:

- command names and descriptions;
- repository-local environment defaults;
- controller tool activation and, where approved, installation;
- forwarding operator arguments; and
- offline developer and CI task aliases.

`platformctl` owns:

- phase registry and dependency ordering;
- execution mode and mutation policy;
- evidence freshness and identity validation;
- input fingerprints and safe dependency reuse;
- process locking;
- run directories, logs, summaries, and exit codes; and
- resume and invalidation behavior.

Existing phase code owns:

- configuration validation;
- actual convergence and live checks;
- resource-specific rollback behavior; and
- detailed phase evidence.

Do not place Kubernetes reconciliation, evidence interpretation, secret processing, or
complex conditional control flow in `mise.toml`.

## Proposed Phase Contract

Every phase should eventually expose the same conceptual interface:

```text
status     fast live health, no mutation
check      full phase-local desired-state validation, no mutation
apply      phase-local convergence followed by validation
describe   metadata, dependencies, owned paths, and available operations
```

Each invocation receives named arguments and returns a stable exit code. It writes a
redacted JSON result atomically to a caller-provided run directory. Standard output is a
short human summary; detailed output goes to the run log.

The runner registry records:

- stable phase ID and display name;
- dependency phase IDs;
- owned command;
- supported operations;
- files contributing to the input fingerprint;
- evidence schema and path;
- maximum evidence age by operation and environment profile;
- whether reboot invalidates reusable evidence; and
- whether the operation is mutating or disruptive.

## Evidence Reuse Rules

Evidence may replace rerunning a deep dependency check only when all required fields
match:

- environment and profile;
- host and cluster identity;
- repository revision or approved dirty-worktree fingerprint;
- phase input hash;
- dependency evidence hashes;
- relevant tool and platform versions;
- host boot ID when reboot-sensitive;
- passing status; and
- configured maximum age.

Even when evidence is reusable, apply should perform a cheap dependency health check.
Qualification must reject stale or mismatched evidence and must not use task timestamp
caching as proof of live state.

## Caching and Performance

Use caching only for immutable or reproducible inputs:

- cache Helm chart archives by declared SHA-256;
- verify the checksum every time the archive is consumed;
- cache installed controller tools by exact version and checksum;
- reuse rendered output only when every input hash matches; and
- run independent read-only probes concurrently when they cannot overload or mutate a
  shared service.

Do not cache conclusions about live health, connectivity, certificate readiness, alert
delivery, log ingestion, storage attachment, or workload readiness.

Apply operations remain sequential. Phase 7 may parallelize independent read-only checks
but must serialize disruptive scenarios.

## Concurrency, Failure, and Security

- Acquire an environment-scoped file lock before apply, validate, backup, restore,
  upgrade, or rebuild.
- Permit concurrent `status` only when it cannot interfere with an active operation.
- Create one mode-`0700` temporary run directory and register one cleanup handler.
- Write reports through a temporary file, validate them, then rename atomically.
- Preserve detailed failure logs without secret values.
- Never store an age private key or decrypted secret in `mise.toml`, command arguments,
  evidence, or reusable rendered output.
- Allow a local ignored environment override to select an age identity path; production
  must require an explicit environment selection.
- Do not provide a general `--skip-check` option for qualifying runs. Development-only
  skips must be explicit exceptions in evidence.

## Proposed Mise Responsibilities

An initial `mise.toml` should remain thin. Conceptually:

```toml
[env]
ENVIRONMENT = "test"
K3S_DIR = "{{ config_root }}/execution/k3s"
ANSIBLE_CONFIG = "{{ config_root }}/execution/k3s/host/ansible.cfg"
SOPS_AGE_KEY_FILE = "{{ config_root }}/execution/k3s/environments/test/age-identity.txt"

[tasks.status]
description = "Show fast platform health"
run = "python3 execution/k3s/platformctl.py status --environment $ENVIRONMENT"

[tasks.check]
description = "Check declared platform state"
run = "python3 execution/k3s/platformctl.py check --environment $ENVIRONMENT"

[tasks.apply]
description = "Converge declared platform state"
run = "python3 execution/k3s/platformctl.py apply --environment $ENVIRONMENT"

[tasks.validate]
description = "Run platform qualification"
run = "python3 execution/k3s/platformctl.py validate --environment $ENVIRONMENT"
```

This is illustrative rather than the final Mise syntax contract. Implementation must
test argument forwarding, environment overrides, shell portability, and secret-path
handling with the pinned Mise release before adoption.

## Migration Plan

### Stage 1: Mise Facade

Goal: reduce operator commands without changing deployment behavior.

1. Add a pinned or explicitly accepted Mise version and installation/check procedure.
2. Add thin tasks for controller setup, full check, full apply, and focused tests.
3. Set repository-derived paths automatically.
4. Default to `test`; require explicit selection and confirmation for production.
5. Keep the existing `bootstrap.sh` commands working unchanged.
6. Add shell completion instructions and task descriptions.

Acceptance:

- Mise and direct bootstrap commands invoke identical underlying behavior;
- the SOPS identity is discovered without manual exports;
- command arguments and exit codes are preserved; and
- no secret values appear in task listings or process arguments.

### Stage 2: Fast Status and Output Control

Goal: separate routine operations from full convergence checks.

1. Implement a read-only `status` command using existing health primitives.
2. Add quiet default output with a phase summary table.
3. Save detailed logs under a unique ignored run directory.
4. Add `--verbose` and `--json` output modes.
5. Add an environment-scoped operation lock.

Acceptance:

- status completes quickly on a healthy host;
- failures identify the owning phase and next diagnostic command;
- full logs remain available; and
- simultaneous mutating operations are rejected.

### Stage 3: Common Phase Interface

Goal: preserve isolation while removing orchestration duplication.

1. Define and test a versioned phase command contract.
2. Wrap Phase 1-6 implementations behind named phase-local commands.
3. Create a Python registry containing dependencies and metadata.
4. Move temporary-file, exit-code, and report orchestration from `bootstrap.sh` into the
   runner.
5. Keep `bootstrap.sh` as a compatibility wrapper around `platformctl`.

Acceptance:

- each phase can be checked independently;
- aggregate execution preserves dependency order;
- direct and compatibility commands produce equivalent results; and
- existing phase tests continue to pass.

### Stage 4: Safe Evidence Reuse

Goal: avoid rerunning unchanged deep dependencies.

1. Define canonical input fingerprints per phase.
2. Add evidence age, host identity, boot identity, repository state, and dependency hash
   checks.
3. Add `--fresh` to force all checks.
4. Add explicit evidence invalidation from a selected phase.
5. Add a concise history and current-state query.

Acceptance:

- a valid late-phase check skips expensive unchanged dependencies;
- config, commit, host, boot, version, or dependency changes invalidate the correct
  phases;
- apply still performs lightweight prerequisite health checks; and
- Phase 7 rejects stale or mismatched evidence.

### Stage 5: Immutable Artifact Cache

Goal: reduce network and rendering cost without trusting mutable state.

1. Cache chart archives by SHA-256 outside source control.
2. Verify cached content before every use.
3. Download atomically when missing or invalid.
4. Record artifact hashes in run evidence.
5. Add bounded cache cleanup that never removes artifacts used by an active run.

Acceptance:

- repeat Phase 6 checks do not redownload unchanged charts;
- corrupted cached artifacts are rejected and safely reacquired; and
- two renders from identical inputs remain deterministic.

### Stage 6: CI Integration

Goal: move deterministic failures earlier without making CI the only recovery path.

1. Run schema validation, unit tests, shell syntax checks, and deterministic renders in
   CI.
2. Validate Mise tasks and the phase registry.
3. Scan pinned images and artifacts according to the accepted policy.
4. Keep live deployment manual until a trusted self-hosted runner, concurrency controls,
   approvals, and secret delivery are accepted.

Acceptance:

- pull requests fail before merge on deterministic configuration or render defects;
- CI requires no production secret material for offline checks; and
- operators retain a local recovery path when CI is unavailable.

## Initial Scope

The smallest useful implementation is Stages 1 and 2:

- add Mise as a thin facade;
- remove repeated shell environment setup;
- expose `status`, `check`, and `apply`;
- retain the existing bootstrap implementation; and
- improve output and operation locking.

Do not begin evidence skipping until Phase 7 defines evidence freshness and identity
rules. Do not move Kubernetes resources to GitOps or VM state to Terraform merely to
reduce command length.

## Success Criteria

The automation redesign succeeds when:

1. A routine operator uses no more than `status`, `check`, `apply`, and `validate`.
2. Phase ownership and independent validation remain visible.
3. Repeated healthy checks avoid unnecessary downloads and deep dependency work.
4. A failed operation identifies the exact phase, check, log, and remediation.
5. Simultaneous mutation is prevented.
6. Evidence cannot be reused across mismatched configuration, host, cluster, boot, or
   repository identity.
7. Existing direct commands remain available during migration.
8. No secret value is exposed through Mise, process arguments, logs, or evidence.
9. The complete fresh validation path remains available and is used for qualification.

## Deferred Decisions

- whether Mise should install all controller binaries or initially activate the existing
  `.controller-venv` toolchain;
- the exact evidence maximum age per phase and profile;
- whether run history remains JSON files or gains a small query index;
- when application delivery justifies Flux or Argo CD; and
- whether VM provisioning belongs in this repository or a separate infrastructure
  project.