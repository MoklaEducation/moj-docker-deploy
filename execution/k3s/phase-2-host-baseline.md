# Phase 2 Implementation Plan: Host Baseline

Status: ready for implementation after Phase 1 passes.

## Mission

Converge one Phase 1-approved Ubuntu VM into the documented host baseline required by
same-host data services and a later single-server k3s installation. The result must be
secure, version-aware, idempotent, and recoverable from version-controlled configuration.

This phase changes the host. It must provide check mode, an explicit apply path, and
evidence that a second apply produces no unintended changes.

## Architectural Context

The target platform uses one VM as one failure domain. MariaDB and Redis will run in
digest-pinned containers on the host outside Kubernetes. k3s will use its own bundled
containerd; host data-service containers will use Docker Engine and Docker Compose. The
two runtimes must have separate storage roots and must not share sockets or state.

Kubernetes applications are not deployed in this phase. Read, in order:

1. [k3s Cluster Blueprint](README.md)
2. [Repeatable k3s Deployment Strategy](repeatable-deployment.md)
3. [Phase 1 Preflight](phase-1-preflight.md)
4. [Phase 3 Host Data Services](phase-3-host-data-services.md)

If a conflict exists, the blueprint wins, followed by the deployment strategy, followed
by this plan.

## Preconditions

- Phase 1 completed with overall `pass` for the selected environment.
- The target is Ubuntu Server 24.04 LTS on `x86_64` with `systemd`.
- The configured non-root automation user can connect over SSH and use non-interactive
  `sudo`.
- The operator has reviewed the rendered changes.
- A console or provider recovery path exists before SSH or firewall settings change.
- The target contains no existing k3s or conflicting Kubernetes installation.
- Environment secrets remain encrypted and are not needed for ordinary baseline tasks.

If the Phase 1 evidence is missing or its environment/host identity differs from the
current target, stop and require Phase 1 to run again.

## Goals

1. Establish a predictable operating-system package and repository baseline.
2. Harden and verify administrative access without locking out the operator.
3. Configure time, kernel, swap, firewall, logging, and resource prerequisites.
4. Establish stable host storage and configuration roots.
5. Install the pinned Docker Engine and Compose plugin required by Phase 3.
6. Reserve capacity and prevent unbounded host log/container growth.
7. Produce a redacted report and prove convergence on a second run.

## Non-Goals

- Installing MariaDB, Redis, k3s, Helm, Kustomize, or cluster add-ons.
- Creating application databases, users, schemas, or credentials.
- Managing DNS records, cloud firewalls, hypervisor settings, or VM creation.
- Replacing the existing automation SSH key.
- Enabling unattended k3s, Docker, database, or kernel upgrades.
- Supporting distributions or architectures outside the Phase 1 baseline.

## Configuration Contract

Consume the Phase 1 `platform.yml` schema. Its required `host` and `docker` values are:

```yaml
host:
  timezone: Etc/UTC
  automation_user: ubuntu
  ssh_port: 22
  storage_root: /srv/mokla
  config_root: /etc/mokla
  state_root: /var/lib/mokla
  evidence_root: /var/log/mokla
  disable_swap: true
  allow_automatic_security_updates: true
  allow_automatic_reboot: false
  journald_max_use: 1G
  minimum_free_disk_percent: 20

docker:
  apt_repository: <approved official repository URL>
  repository_key_fingerprint: <reviewed fingerprint>
  engine_version: <exact available package version>
  compose_plugin_version: <exact available package version>
  data_root: /srv/mokla/docker
  log_max_size: 20m
  log_max_files: 5
```

Values shown in angle brackets are decision inputs, not literal defaults. Commit selected
non-secret versions in each environment before Phase 1 is accepted. Validate that
configured package versions exist before changing repositories or packages. Phase 2 must
not define a second source for these values.

Administrative and public CIDRs/ports, NTP policy, and minimum resources come from the
Phase 1 contract and must not be restated elsewhere.

## Intended File Ownership

Extend the Phase 1 structure as follows:

```text
execution/k3s/host/
  playbooks/
    host-baseline.yml
  roles/
    baseline/
      defaults/main.yml
      handlers/main.yml
      tasks/
        main.yml
        packages.yml
        access.yml
        time.yml
        kernel.yml
        swap.yml
        firewall.yml
        logging.yml
        docker.yml
        storage.yml
        verify.yml
      templates/
        docker-daemon.json.j2
        host-baseline-report.json.j2
```

Keep task files cohesive; do not create wrapper roles for individual package commands.
All handlers must be named and should restart a service only when its managed
configuration changes.

## Operator Interface

Required commands:

```bash
./execution/k3s/bootstrap.sh check --environment test --through host-baseline
./execution/k3s/bootstrap.sh apply --environment test --through host-baseline
```

`check` runs Phase 1 plus Ansible check/diff mode for Phase 2 and writes no target state.
`apply` reruns Phase 1, stops on failure, then applies Phase 2. `--through` means all
prerequisite phases run in order; it must not permit Phase 2 to bypass Phase 1.

If a reboot is required, apply must report it and exit successfully with a distinct
machine-readable `reboot_required` result. It must not reboot automatically. After the
operator reboots, the same apply command resumes convergence and validation.

## Required Host State

### Package and repository policy

- Refresh package metadata only through Ansible modules.
- Install a minimal explicit package list needed for automation, diagnostics, time sync,
  firewalling, encrypted backups, Docker repository verification, and future k3s checks.
- Do not perform an unrestricted distribution upgrade.
- Use Ubuntu repositories for ordinary OS packages.
- Add Docker's official Ubuntu repository using a keyring file and `signed-by`; do not use
  deprecated global `apt-key` trust.
- Verify the configured repository-key fingerprint before trusting it.
- Install exact Docker Engine and Compose plugin package versions and hold them against
  unattended version changes. Version changes are later explicit platform upgrades.
- Record installed and candidate versions in evidence.

### Administrative access

- Preserve the working automation user's authorized key and non-interactive sudo access.
- Lock password authentication and direct root SSH login only after proving public-key
  access in a second connection.
- Validate `sshd` configuration before reload. Reload rather than restart when supported.
- Do not edit provider-managed network configuration unless explicitly owned by the
  environment.
- Treat the automation account as privileged and root-equivalent; restrict its key and
  source networks accordingly.

### Time and host identity

- Set the configured timezone and establish one time-synchronization implementation.
- Enable it at boot and verify synchronized state.
- Set the configured stable hostname only when the environment explicitly authorizes the
  change; preserve provider-required `/etc/hosts` behavior.
- Record but do not silently repair forward/reverse DNS mismatches.

### Kernel and swap

- Load and persist only modules required by k3s and container networking, initially
  `overlay` and `br_netfilter` where supported.
- Persist required forwarding and bridge netfilter sysctls using one managed file.
- Apply values through `sysctl` and verify the effective values.
- Disable swap when configured, both immediately and persistently. Preserve a backup or
  report of the prior `/etc/fstab` entry. Do not alter unrelated mounts.
- Report whether a reboot is required because of kernel/package changes.

### Firewall

- Use one host-firewall owner, initially UFW on Ubuntu.
- Set default incoming deny, routed deny, and outgoing allow unless the accepted network
  policy says otherwise.
- Add SSH allowance from configured administrative CIDRs before enabling or reloading the
  firewall.
- Allow TCP 6443 only from configured administrative CIDRs for the future Kubernetes API.
- Allow TCP 80 and 443 from configured public source CIDRs for future ingress.
- Do not open MariaDB or Redis ports publicly. Phase 3 may add narrowly scoped rules for
  the selected private host and future pod CIDR contract.
- Do not add broad rules for Docker bridge interfaces. Account for Docker's interaction
  with netfilter and validate exposure from an external test source in Phase 3.
- Preserve an explicit emergency console recovery procedure in operator documentation.

### Storage and filesystem ownership

- Create the configured roots with root ownership and restrictive modes:
  `/srv/mokla`, `/etc/mokla`, `/var/lib/mokla`, and `/var/log/mokla` by default.
- Create a dedicated Docker data root under the storage root.
- Do not create MariaDB or Redis service data directories until Phase 3.
- Refuse symlinked roots, world-writable parent paths, unsupported network filesystems, or
  paths on filesystems below the configured free-space threshold.
- Do not recursively change ownership of a pre-existing non-empty root without explicit
  migration approval.

### Docker Engine

- Install and enable Docker Engine and the Compose plugin, but deploy no containers.
- Configure Docker's data root and bounded `json-file` logging.
- Keep Docker's socket root-owned. Do not add the automation user to the `docker` group;
  use `sudo` because Docker socket access is root-equivalent.
- Disable Docker Swarm and verify the node is not part of a swarm.
- Verify Docker and the future k3s containerd paths are distinct.
- Do not configure application registry credentials in this phase.

### Logging and updates

- Bound persistent journald disk usage using the configured limit.
- Retain logs across reboot and verify journal health.
- Permit automatic security updates only according to configuration, without automatic
  reboot. Exclude held platform packages from unattended replacement.
- Configure no cron job or timer that performs an unreviewed platform upgrade.

## Idempotence Requirements

- Use Ansible modules instead of shell commands whenever a suitable module exists.
- Every template and managed file has explicit owner, group, mode, and validation where
  available.
- Package installation, repository setup, sysctls, mounts, firewall rules, and service
  enablement must be declarative.
- A second apply after any required reboot reports `changed=0` except for evidence files
  written on the controller.
- Check mode after convergence reports no pending changes.
- Do not use timestamps or random values in managed host files.

## Failure and Rollback Behavior

- Validate SSH and firewall changes before activation and preserve the current session.
- If Docker fails after a configuration change, restore the prior validated daemon
  configuration and report failure; do not remove Docker data.
- Never remove packages, users, firewall rules, storage, or data during ordinary apply.
- A failed task stops the phase. Do not continue into data-service or k3s installation.
- Record changed resources and remediation in the redacted evidence report.

## Implementation Sequence

1. Add Phase 2 semantic validation for the existing environment JSON schema.
2. Add pinned Ansible collection dependencies and lint configuration.
3. Implement package/repository and storage-root tasks.
4. Implement access changes with connection-safety checks.
5. Implement time, kernel, swap, firewall, and journald tasks.
6. Install and configure Docker without deploying containers.
7. Add post-apply host assertions and report generation.
8. Exercise check mode, first apply, reboot continuation if needed, second apply, and
   final check mode on a disposable VM.
9. Exercise one rollback path for invalid Docker and SSH configuration fixtures.

## Acceptance Tests

Run and record at minimum:

```bash
./execution/k3s/bootstrap.sh check --environment test --through host-baseline
./execution/k3s/bootstrap.sh apply --environment test --through host-baseline
./execution/k3s/bootstrap.sh apply --environment test --through host-baseline
./execution/k3s/bootstrap.sh check --environment test --through host-baseline
```

The acceptance evidence must prove:

1. Phase 1 passes immediately before mutation.
2. The supported package and Docker versions are installed and pinned.
3. SSH key access still works from an allowed source; password and root login policy match
   configuration.
4. Allowed ports are reachable from allowed sources and denied from a test disallowed
   source where the test environment permits that check.
5. Time synchronization, modules, sysctls, swap policy, journald bounds, and services
   match configuration after reboot.
6. Storage roots have expected filesystems, ownership, modes, and free capacity.
7. Docker runs with the configured data root and logging limits, with no deployed
   containers and no active Swarm.
8. The second apply reports no unintended changes.
9. No plaintext secret, generated runtime state, kubeconfig, or host evidence is staged in
   Git.

Run shell lint, YAML lint, `ansible-lint`, `ansible-playbook --syntax-check`, and Molecule
or an equivalent disposable-VM integration test selected by the implementation.

## Evidence Contract

Write a redacted controller-side report under:

```text
execution/k3s/.evidence/<environment>/phase-2-host-baseline.json
```

Include Phase 1 report identity, configuration schema version, applied role/version,
package versions, service states, firewall policy summary, storage facts, reboot state,
first/second-run Ansible recap, acceptance checks, and overall status. Do not include SSH
keys, sudo credentials, repository credentials, or decrypted secrets.

## Completion Gate

Phase 2 is complete only when the first apply succeeds, any required reboot is completed,
the second apply is idempotent, final check mode is clean, all acceptance tests pass, and
Phase 3 can consume the same host and environment contract without manual preparation.