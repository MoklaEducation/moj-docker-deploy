# Phase 4 AI Implementation Handoff Prompt

Copy the prompt below into a coding-agent session opened at the repository root.

```text
Implement Phase 4: the first single-node k3s installation for the disposable `test`
environment.

Read first, in this order:

1. execution/k3s/plan/phase-4-k3s-installation.md
2. execution/k3s/plan/progress/phase-3-host-data-services-progress.md
3. execution/k3s/plan/phase-3-host-data-services.md
4. execution/k3s/plan/progress/phase-2-host-baseline-progress.md
5. execution/k3s/repeatable-deployment.md
6. execution/k3s/README.md
7. the current bootstrap, schema, environment, Ansible roles, tests, and evidence writers

Authority and delivery profile

The `Current Development Profile Addendum` in
`execution/k3s/plan/phase-4-k3s-installation.md` is authoritative for the current test
environment and overrides conflicting production-oriented requirements later in that
plan.

This is a disposable, single-node development cluster. Optimize for a functional,
repeatable cluster that provides useful end-to-end validation. Do not block Phase 4 on:

- off-host MariaDB, Redis, k3s token, configuration, or SQLite backups;
- backup/restore qualification;
- public DNS or publicly trusted certificates;
- cert-manager or certificate-rotation automation;
- multi-node Flannel rules;
- external allowed/denied network test vantage points; or
- production firewall segmentation and logging.

Do not claim those deferred capabilities are complete. Protect generated credentials and
state locally with the required restrictive modes.

Objective

Install one exact k3s release on the prepared host and prove that its API, node, bundled
components, DNS, ClusterIP networking, local storage, pod egress, and permitted access to
the Phase 3 data services work. Preserve the existing Docker-managed MariaDB and Redis
containers and keep k3s containerd state separate from Docker state.

Fixed topology

- One k3s server and no agents.
- Default SQLite datastore; never use Phase 3 MariaDB as the k3s datastore.
- Bundled containerd, Flannel, CoreDNS, Traefik, ServiceLB, local-path provisioner,
  metrics-server when present, and network-policy controller.
- No embedded etcd, external datastore, custom CNI, GitOps, application workloads, or
  Phase 5 namespace/RBAC work.
- k3s state and local-path storage under dedicated `/srv/mokla/k3s` descendants, outside
  `/srv/mokla/docker` and `/srv/mokla/data-services`.

Current baseline to verify, not merely assume

- Phases 1-3 have passing evidence for environment `test` on `192.168.1.151`.
- Phase 2 reports no pending reboot.
- The pod CIDR is `10.42.0.0/16`; the service CIDR is `10.43.0.0/16`; both passed overlap
  validation.
- UFW is active with routed traffic denied by default. TCP 6443 is allowed only from the
  administrative CIDR `192.168.1.0/24`; ports 80 and 443 have the existing reviewed
  ingress policy.
- Phase 3 permits its MariaDB and Redis ports from the pod CIDR.
- MariaDB and Redis runtime probes pass and unchanged setup preserves their identity and
  data.
- No k3s binary, unit, or listener should exist before the first apply.
- The environment currently contains an unresolved k3s version placeholder and lacks the
  rest of the Phase 4 configuration contract.
- Preserve all unrelated worktree changes, especially nested `dmoj/repo` state and any
  uncommitted Phase 3/4 documentation. Never reset, clean, stage, or overwrite unrelated
  files.
- Never print, replace, or commit the ignored age identity, SOPS plaintext, kubeconfig,
  server token, or other credentials.

Implementation decisions you are authorized to make

Choose and record practical development values without another architecture round:

- an exact currently supported k3s release and its official SHA-256 for linux/amd64;
- a stable environment-specific node name, preferably matching the stable host identity;
- node IP and API bind address derived from `host_address`;
- API TLS SANs containing the stable private IP and, when locally resolvable, the stable
  development hostname;
- cluster DNS `10.43.0.10` for the configured service CIDR;
- data and local-storage paths under `/srv/mokla/k3s`;
- an ignored controller-side kubeconfig path; and
- k3s secrets encryption enabled.

Use k3s-managed bootstrap CA and serving certificates. Do not introduce public PKI or
cert-manager. Placeholders must fail validation before host mutation.

Before choosing the Ansible dependency, verify how the selected upstream
`k3s-io/k3s-ansible` release is actually packaged. Do not invent a Galaxy collection
name. If it is consumable through Ansible Galaxy SCM requirements, pin an immutable tag
or commit in `execution/k3s/host/requirements.yml`. If the repository cannot be consumed
as the collection assumed by the plan, document the mismatch and choose the smallest
pinned, maintainable integration consistent with the plan; do not copy a large upstream
role tree into this repository.

Required implementation

1. Extend the environment contract.
   - Replace the k3s placeholder with concrete reviewed values.
   - Expand `platform.schema.json`, `platform.yml.example`, and semantic validation for
     version, checksum, node identity, addresses, SANs, CIDRs, cluster DNS, paths,
     kubeconfig output, and secrets encryption.
   - Reject placeholders, mutable version channels, malformed checksums, wildcard or
     unassigned bind addresses, unsafe paths, path overlap, CIDR changes/overlap, and
     kubeconfig paths that are not ignored or cannot be protected.
   - Add focused positive and negative tests before host mutation.

2. Extend the public orchestration boundary.
   - Add `k3s-installation` to the supported `bootstrap.sh --through` values and usage.
   - Preserve execution order: Phase 1, Phase 2, Phase 3, then Phase 4.
   - Check mode must remain non-mutating and must not install, start, restart, upgrade, or
     uninstall k3s.
   - Apply must require the existing explicit `apply --through k3s-installation` boundary.
   - Keep temporary files mode `0600`, clean them with traps, and never place credentials
     in command arguments, normal logs, or evidence.

3. Implement the local k3s role and playbook.
   - Create the Phase 4 playbook and a focused local role under the ownership layout in
     the Phase 4 plan.
   - Validate passing Phase 3 evidence and no pending reboot before mutation.
   - Inspect for an existing k3s binary, unit, configuration, data path, token, and
     listener. Refuse unknown or unsafe adoption.
   - Create restrictive managed path parents and ownership markers. Reject symlinks,
     overlapping roots, and non-empty unmarked targets.
   - Render explicit k3s configuration with the fixed topology and concrete values.
   - Verify the exact release checksum before first installation.
   - Enable and start k3s only after all pre-mutation gates pass.
   - Never run the uninstall script, delete SQLite, rotate the server token, or reset
     kubeconfig during ordinary convergence.
   - Detect installed-version changes and immutable identity/CIDR/data-path changes before
     mutation. Fail with an upgrade- or rebuild-required message rather than changing
     them through ordinary apply.

4. Implement the minimal development UFW integration.
   - Keep UFW enabled and retain restricted TCP 6443 plus existing 80/443 policy.
   - Add only rules required for the configured pod/service networking, DNS, ClusterIP,
     pod egress, and explicitly permitted pod-to-MariaDB/Redis traffic under the existing
     routed-deny policy.
   - Do not broadly expose pod or service CIDRs on external interfaces.
   - Do not expose kubelet port 10250 externally.
   - Do not open Flannel VXLAN port 8472 externally for this single-node cluster.
   - Prefer explicit, idempotent rules derived from configuration. Verify effective rule
     combinations rather than checking unrelated output substrings.
   - Treat working pod networking through UFW as an acceptance requirement; do not solve
     failures by disabling UFW globally.

5. Handle credentials and kubeconfig safely.
   - Leave the generated server token root-only on the host for this disposable profile;
     no off-host token backup is required for completion.
   - Retrieve the bootstrap administrator kubeconfig to the configured ignored path with
     mode `0600` and `no_log` protection.
   - Rewrite only the API server endpoint to a configured TLS SAN.
   - Do not merge it into a global kubeconfig.
   - Validate certificate trust and endpoint identity without printing client keys,
     bearer tokens, or full kubeconfig content.
   - Label this credential as temporary bootstrap administrator access; Phase 5 owns
     restricted routine identities.

6. Implement runtime validation and redacted evidence.
   - Require the k3s unit to be enabled and active and the node to be `Ready` with the
     exact configured node name and version.
   - Verify the API endpoint and its administrative-source UFW restriction.
   - In a temporary namespace, prove CoreDNS, ClusterIP connectivity, pod egress, and a
     disposable local-path PVC whose data survives pod recreation. Remove fixtures.
   - Verify bundled component health without replacing bundled components.
   - From a disposable pod, test that Phase 3 MariaDB and Redis network endpoints are
     reachable from the allowed pod CIDR. Do not expose or create application credentials;
     Phase 3's authenticated controller probes remain the credential-level proof.
   - Verify Docker MariaDB/Redis remain healthy and Docker and k3s containerd use distinct
     roots.
   - Write `execution/k3s/.evidence/test/phase-4-k3s-installation.json` with prior-phase
     statuses, selected versions/checksum, non-secret config hash, component and smoke-test
     results, Ansible recap, mode, and overall status.
   - Redact secrets by allow-listing evidence fields. Missing runtime checks must fail or
     be explicitly `not_applicable` only when the development addendum defers them.

7. Prove lifecycle behavior.
   - First apply installs and converges the exact release.
   - An immediate unchanged second apply does not restart k3s or report unintended
     changes.
   - Final check mode reports zero changes and runs safe live validation.
   - Prove a controlled k3s restart preserves cluster identity and does not disturb
     MariaDB or Redis.
   - Reboot validation remains required, but never reboot automatically. Stop and request
     explicit operator approval immediately before reboot, then resume validation after
     the host returns.
   - Negative tests must prove incorrect checksum, unsupported version change, CIDR or
     identity change, and unsafe non-empty paths fail before mutation.

Working method

- Create and maintain
  `execution/k3s/plan/progress/phase-4-k3s-installation-progress.md`.
- Start from the existing schema/bootstrap boundary, add the smallest validation slice,
  run its focused tests, and then proceed incrementally.
- Use Python for structured validation and report generation, Ansible for host desired
  state, and shell only for orchestration.
- Reuse established Phase 1-3 conventions for evidence, redaction, check mode, temporary
  files, and tests.
- Do not weaken or regress Phase 1-3 to make Phase 4 pass.
- Do not implement Phase 5 resources, application databases/users, DMOJ, Keycloak,
  GitOps, production backup, or production PKI.
- Do not commit, amend, push, reboot, or perform destructive cleanup unless the user
  explicitly requests that action.

Validation sequence

Before first apply, use a fresh shell:

  cd /path/to/moj-docker-deploy
  ENVIRONMENT="test"
  K3S_DIR="$PWD/execution/k3s"
  export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
  export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
  export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

  ./execution/k3s/operations/setup/controller.sh check
  test -r "$SOPS_AGE_KEY_FILE"
  test -r "$K3S_DIR/environments/$ENVIRONMENT/secrets.sops.yml"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT"
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-baseline
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-data-services
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through k3s-installation

The first Phase 4 check must exit zero and prove that the proposed installation is safe
without requiring k3s to already exist. Separate pre-install checks from post-install live
checks in evidence so absent k3s is expected only before the first apply.

After the user approves host mutation:

  ./execution/k3s/bootstrap.sh apply --environment "$ENVIRONMENT" --through k3s-installation
  ./execution/k3s/bootstrap.sh apply --environment "$ENVIRONMENT" --through k3s-installation
  ./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through k3s-installation

Then run focused unit tests, Python compilation, tracked shell syntax checks, Ansible
inventory/syntax checks, rendered configuration validation, `git diff --check`, and the
full available k3s operations test suite. Do not feed Python executables or unrendered
Jinja templates to `bash -n`.

Definition of done

Phase 4 development profile is complete only when:

- all Phase 1-4 public checks and evidence report pass;
- the exact checksum-verified k3s release is installed;
- the node is Ready with the configured identity and version;
- bundled components, DNS, ClusterIP, pod egress, and local-path persistence pass;
- permitted pod-to-data-service networking works with UFW still enabled;
- TCP 6443 remains restricted and ports 10250/8472 are not externally exposed;
- MariaDB and Redis remain healthy and retain their data/container lifecycle;
- the second apply is idempotent and does not restart a healthy unchanged k3s;
- final check mode is clean and non-mutating;
- an explicitly approved reboot proves k3s and host data services recover;
- the bootstrap kubeconfig is ignored, mode `0600`, usable, and absent from evidence;
- negative safety tests fail before mutation;
- the progress document records selected values, commands, recaps, smoke-test results,
  reboot result, deferred controls, and residual risks; and
- no secret or unrelated worktree content is staged or committed.

Do not label the result production-ready. Label it a complete disposable single-node
Phase 4 development cluster that is ready for Phase 5 platform-core implementation.
```
