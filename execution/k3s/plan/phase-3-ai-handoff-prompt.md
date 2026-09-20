# Phase 3 AI Continuation Handoff Prompt

Copy the prompt below into a new coding-agent session opened at the repository root.

```text
Continue and finish Phase 3 host data services in this repository according to:

  execution/k3s/plan/phase-3-host-data-services.md

Treat that file as the Phase 3 specification. Before editing, read these documents in
order and resolve conflicts using their stated precedence:

1. execution/k3s/README.md
2. execution/k3s/repeatable-deployment.md
3. execution/k3s/plan/phase-1-preflight.md
4. execution/k3s/plan/phase-2-host-baseline.md
5. execution/k3s/plan/progress/phase-1-preflight-progress.md
6. execution/k3s/plan/progress/phase-2-host-baseline-progress.md
7. execution/k3s/plan/phase-3-host-data-services.md
8. execution/k3s/plan/progress/phase-3-host-data-services-progress.md
9. execution/k3s/operations/data-services/README.md

Goal

Finish the partially deployed Phase 3 test environment and preserve the split between
optional helper provisioning and mandatory external-service validation.

The repository may provision digest-pinned, systemd-managed MariaDB and Redis containers,
test certificates/passwords, and a local-development restic repository to bootstrap a
test machine quickly. These are convenience implementations, not a production ownership
requirement. MariaDB, Redis, backup storage/restic access, certificates, passwords, and
their lifecycle are externally owned in production.

For production, set `data_services.provisioning_mode: external` and provide private
endpoint, port, CA, least-privilege probe identity, and encrypted probe credential inputs
through the environment contract. The check flow owns only validation from the controller
vantage point: TLS trust and endpoint identity, MariaDB authentication plus `SELECT 1`,
Redis authentication plus `PING`, redacted evidence, and failure reporting. It must not
install, configure, restart, back up, rotate credentials/certificates, or otherwise manage
externally owned production services.

Use containers exclusively for the data-service runtimes. Do not install MariaDB, Redis,
or their server packages natively on the host. Deploy one MariaDB container and one Redis
container for the environment unless an incompatible service contract proves that a
separate instance is required.

Do not implement Phase 4 or deploy k3s, Kubernetes resources, application databases,
application users, grants, schemas, DMOJ, or Keycloak. Do not migrate or adopt existing
data implicitly.

Current repository baseline

- Phase 1 and Phase 2 are implemented. Phase 2 was corrected to validate only its own UFW
  invariants so reviewed Phase 3 rules do not make the baseline fail.
- The public Phase 2 command is:
  ./execution/k3s/bootstrap.sh check --environment test --through host-baseline
- The latest verified Phase 2 result is `ok=76 changed=0 failed=0 skipped=5` with passing
  evidence after Phase 3 installed narrowly scoped data-service UFW rules.
- Phase 3 schema, semantic/SOPS validation, Ansible role, Compose/systemd lifecycle,
  backup/restore helpers, runtime protocol validator, evidence integration, and operator
  helper are implemented. Commit `9894b1a` separates optional setup from validation.
- The test environment is `helper-managed` at `192.168.1.151`. A first apply created the
  MariaDB and Redis containers, data/config roots, runtime secrets, and UFW rules, but
  service convergence did not complete.
- Redis originally crash-looped because root-only host mounts were unreadable by its
  non-root image user. The guarded recovery helper is:
  ./execution/k3s/operations/data-services/repair-test-permissions \
    --environment test --apply-permission-repair
  It verifies the ownership marker and pinned image identities, changes only required
  modes/ownership, and never restarts services or deletes data. The test host repair was
  applied successfully and Redis now starts.
- The permission helper is recovery-only. Update the Ansible desired state before another
  apply or it may restore the original root-only ownership.
- Runtime acceptance still fails. Redis's generated ACL hashes a password containing a
  trailing newline while the health client strips it; its health script also returns zero
  after `WRONGPASS`/`NOAUTH`. MariaDB starts but its health path has TLS/client-option and
  remote root-authentication defects. Fix these in code rather than resetting data or
  weakening the external Python TLS probe.
- The permission helper, its safety test/documentation, the Phase 2 composable-UFW fix,
  and this handoff/progress update are currently uncommitted. Preserve and validate them;
  do not assume they are part of commit `9894b1a`.
- The encrypted test secret file and age identity are ignored local files. Never print,
  commit, replace, or expose their values.
- Preserve unrelated worktree changes, especially the nested dmoj/repo state. Never
  reset, clean, or stage unrelated files.
- The existing local DMOJ and Keycloak Compose files use separate MariaDB containers.
  Do not carry that test-stack topology into this host platform. The Phase 3 production
  contract uses one shared MariaDB engine; later application phases own separate logical
  databases, users, grants, schemas, and application credentials within it.

Working method

1. Inspect the current branch, status, recent commits, Phase 1/2 implementation, and
   existing tests. Do not rewrite or amend existing commits.
2. Establish a concrete Phase 3 progress document at:
   execution/k3s/plan/progress/phase-3-host-data-services-progress.md
   Record verified facts, blockers, commands, results, and gaps as work proceeds.
3. Compare the Phase 3 specification with the current schema and environment files.
   Add strict structural and semantic validation before host mutation. Add focused tests
   for valid inputs and every important rejection path.
4. Implement in the specification's sequence, using small testable changes. After each
   substantive edit, run the narrowest relevant test before continuing.
5. Keep Python responsible for structured validation and redacted report generation,
   Ansible responsible for host desired state, and shell responsible only for orchestration.
6. Preserve check mode as non-mutating. It may render and validate temporary files on the
   controller, but it must not start containers, write decrypted secrets to the host,
   contact the backup repository, alter firewall state, or report transient operations as
   desired-state drift.
7. Make apply safety-first and idempotent. A second apply must report no unintended
   changes and must not recreate unchanged healthy containers.
8. Stop and report a precise blocker when an operator-owned prerequisite is absent. Do
   not weaken validation, insert fake values, silently switch designs, or mark acceptance
   complete to work around a missing prerequisite.
9. Continue through all work that can be safely implemented and tested despite a blocker.
   Clearly distinguish implementation completion from environment acceptance completion.
10. Commit only coherent, validated Phase 3 changes. Stage exact paths, inspect the staged
    diff, exclude unrelated changes and generated evidence, and do not push unless asked.

Mandatory safety rules

- Run as the configured non-root automation user; never run bootstrap as root.
- Never reveal decrypted secrets in command output, diffs, logs, Compose environment
  values, process arguments, Docker labels, docker inspect output, or evidence.
- Secret paths must remain inaccessible to unrelated users. Ownership and modes must also
  permit the pinned non-root service identities to traverse/read only their required
  files; do not make credentials or private keys world-readable.
- Use mounted secret files and supported *_FILE mechanisms or protected service config.
- Never use docker compose down --volumes in apply, stop, backup, or restore paths.
- Never delete, overwrite, initialize, import, or adopt a non-empty MariaDB/Redis target
  directory without a separately reviewed migration/adoption procedure.
- Never restore over primary paths. Restore requires an explicit snapshot and an isolated
  guarded target.
- Never back up live MariaDB data files as the supported backup. Use a consistent logical
  dump with routines, events, triggers, checksum, metadata, compression, and cleanup.
- Never prune restic snapshots after a failed dump, upload, or snapshot verification.
- Never expose service ports publicly or add Compose ports entries. Use host networking
  and exact destination-address UFW rules.
- Never place a CA private key on the host unless the accepted certificate lifecycle
  explicitly requires it.
- Never automatically reboot, downgrade a database, reset credentials, or reinitialize
  data to make a health check pass.
- Never record secret-bearing repository URLs or provider credentials.
- Never install native MariaDB or Redis server packages or write service data into the
  source checkout, Docker data root, k3s paths, or an undifferentiated shared directory.
- Never use the MariaDB root/bootstrap credential for an application.

Operator-owned prerequisites and decision gates

Before any Phase 3 apply, verify or ask the operator to provide/approve all of these:

- A specific stable private bind address assigned to the host, not loopback, wildcard, or
  public space.
- Reviewed allowed client CIDRs, including the future pod CIDR where appropriate.
- Exact MariaDB and Redis version-readable image references pinned by immutable digest,
  with compatibility rationale and image scan findings.
- For production, externally operated MariaDB and Redis endpoints and lifecycle ownership.
- A real externally operated off-host backup/restic repository without embedded
  credentials, its provider-specific secret keys, retention, UTC schedule, and
  encryption-key custody. The local helper repository is test-only.
- Externally supplied non-placeholder MariaDB/Redis probe credentials, backup credentials,
  and TLS trust material in the encrypted environment contract. Test helper generation is
  available only to bootstrap non-production environments quickly.
- A valid externally managed server certificate/private key/CA chain for the bind address
  or approved names, with an explicit renewal owner.
- Redis persistence semantics and measured maxmemory value.
- External test vantage points for at least one allowed source and one denied source.
- Confirmed console/provider recovery access.
- Explicit disposition of any existing MariaDB/Redis containers, services, data, config,
  or target directories.

Ask concise blocking questions only when a decision is truly required. Do not send secret
values through chat; instruct the operator to place them directly in the encrypted local
secret workflow.

Required implementation surface

The following surface is already implemented; repair and validate it rather than creating
a parallel framework:

- execution/k3s/host/playbooks/host-data-services.yml
- execution/k3s/host/roles/data-services/ with defaults, handlers, tasks, and templates
- execution/k3s/operations/backup/ non-interactive backup and verification scripts
- execution/k3s/operations/restore/ guarded isolated restore and verification scripts
- Phase 3 schema/semantic validators, report generator, and focused tests
- bootstrap.sh check/apply support through host-data-services
- redacted reports under ignored execution/k3s/.evidence/<environment>/
- execution/k3s/plan/progress/phase-3-host-data-services-progress.md

Use `/srv/mokla/data-services` as the designated service data root, with independently
owned subdirectories such as `mariadb/data` and `redis/data`. Keep rendered non-secret
configuration under `/etc/mokla/data-services`, runtime secrets under
`/etc/mokla/secrets/data-services`, and backup staging under the configured
`/srv/mokla/backup-staging` path. Use bind mounts, not opaque Docker named volumes, for
durable service data. Any future data-service container receives its own sibling data,
configuration, secret, and backup ownership boundaries.

Keep the implemented contracts below and finish their runtime validation:

- Complete schema fields and semantic checks for addresses, CIDRs, paths, ports, image
  tag-plus-digest syntax, TLS, Redis policy, restic URL hygiene, schedule, retention, and
  backup frequency. Extend the existing Phase 1 environment schema and encrypted secret
  contract; do not create a second source for these values.
- Preconditions proving Phase 1 and converged Phase 2 evidence, no pending reboot,
  correct Docker/Compose versions, safe storage parents, and no implicit adoption.
- Offline rendering and validation of MariaDB, Redis, Compose, and systemd configuration.
- Deterministic Compose project naming, host networking, no published ports, health
  checks, resource limits, bounded logging, explicit mounts, and safe security options.
- MariaDB private binding, TLS, durable settings, explicit charset/collation, and a
  credential-safe health check.
- Redis private binding, protected/authenticated access, TLS contract, memory/eviction
  policy, and explicit persistent or disposable behavior.
- One shared MariaDB engine prepared for later separate logical databases and
  least-privilege users. Do not create DMOJ or Keycloak databases in Phase 3. Extend the
  existing SOPS document with service-scoped application credentials only when the
  owning application phase defines and provisions those database objects.
- One Redis service only where explicit key namespaces and compatible durability,
  eviction, security, and lifecycle requirements make sharing safe. Do not treat Redis
  numbered databases as tenant isolation; require a separately justified instance when
  contracts are incompatible.
- Exact UFW rules that preserve Phase 2 rules and support external positive/negative tests.
- A root-owned systemd unit with safe start/stop behavior and no data removal.
- Locked logical backup, capacity check, checksums, metadata, restic snapshot verification,
  conditional retention, cleanup, status output, and systemd service/timer.
- Guarded isolated restore using unique names, paths, and loopback-only alternate ports;
  checksum verification; marker validation; primary-service health checks; and cleanup.
- Evidence generation for convergence, backup, and restore with deterministic check IDs
  and strict redaction.
- Failure-path tests, including non-empty data roots, unsafe restore targets, overlapping
  backup locks, failed upload/no prune, placeholder secrets, public/wildcard binding,
  unpinned images, ports entries, and evidence redaction.

Validation order

Use a fresh shell context for operator commands:

  cd /path/to/moj-docker-deploy
  ENVIRONMENT="test"
  K3S_DIR="$PWD/execution/k3s"
  export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
  export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
  export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

  ./execution/k3s/operations/setup/controller.sh install
  ./execution/k3s/operations/setup/controller.sh check
  test -r "$SOPS_AGE_KEY_FILE"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-baseline

Before Phase 3 apply, run all available unit tests, Python compilation, shell syntax,
Ansible inventory, every playbook syntax check, Compose config rendering, check mode,
and git diff --check. Install no lint tool merely to claim validation; report unavailable
optional tools honestly.

The required Phase 3 lifecycle is:

  ./execution/k3s/operations/data-services/data-services check --environment "$ENVIRONMENT"
  ./execution/k3s/operations/data-services/data-services setup \
    --environment "$ENVIRONMENT" --provision-host-services
  ./execution/k3s/operations/data-services/data-services setup \
    --environment "$ENVIRONMENT" --provision-host-services
  ./execution/k3s/operations/data-services/data-services check --environment "$ENVIRONMENT"

The setup command is valid only for `helper-managed` test/development environments. In
`external` production mode, run only `check`; local Compose, systemd, filesystem, UFW,
backup, certificate, and credential ownership must remain skipped.

Then run the implemented backup, backup verification, isolated restore qualification,
allowed-source test, denied-source test, systemd stop/start durability test, and simulated
backup-upload failure test. Never run apply, backup, restore, firewall tests, or service
stop/start without confirming their prerequisites and blast radius first.

Lifecycle entry points must be non-interactive and accept the specification's explicit
inputs:

  backup data-services --environment "$ENVIRONMENT"
  backup verify --environment "$ENVIRONMENT" --snapshot <snapshot-id>
  restore data-services --environment "$ENVIRONMENT" \
    --snapshot <snapshot-id> --target <isolated-target>

Reject a missing snapshot, a non-isolated or primary target, a non-empty unsafe target,
and any attempt to bind restore probes beyond loopback.

Acceptance discipline

Do not call Phase 3 complete unless every completion gate in the specification has real
recorded evidence. In particular:

- A mock repository is useful for unit/integration development but does not prove an
  encrypted off-host backup.
- Local firewall inspection does not prove denied-source behavior.
- Configuration rendering does not prove TLS/authenticated client connectivity.
- A backup snapshot does not prove restore qualification.
- Check mode does not prove apply idempotence.
- Placeholder secrets do not satisfy preconditions.

If infrastructure prevents a gate, leave status as blocked or partially validated, record
exactly what passed and what remains, and provide the next operator command without
fabricating results.

Completion and commits

Maintain a concise progress document with:

- status snapshot and explicit blocked/pass state;
- selected immutable versions/digests and rationale;
- implementation inventory;
- copy-pasteable clean-machine commands with exports at the start of each independent block;
- tests and exact recaps;
- evidence paths and redaction checks;
- issues encountered and resolutions;
- remaining gaps and operator actions;
- update log.

Before each commit:

1. Run the narrow and full available validation suites.
2. Run git diff --check and inspect git status.
3. Stage only Phase 3 files intended for that commit.
4. Inspect git diff --cached and git diff --cached --check.
5. Commit with a concise message; do not amend prior Phase 1/2 commits.
6. Do not push unless explicitly requested.

At the end, report commits created, exact tests and acceptance actions run, evidence
results, unapplied or blocked operations, remaining operator prerequisites, and working
tree state. Preserve unrelated changes throughout.
```
