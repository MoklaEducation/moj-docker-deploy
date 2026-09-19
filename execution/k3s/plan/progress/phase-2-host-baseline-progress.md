# Phase 2 Host Baseline Progress

Status: locally converged and idempotent on the Ubuntu 24.04 test VM

Last updated: 2026-09-19

This document records actual Phase 2 implementation and validation results. The
normative requirements remain in [phase-2-host-baseline.md](../phase-2-host-baseline.md).

## Status Snapshot

- Check command: `./execution/k3s/bootstrap.sh check --environment test --through host-baseline`
- Apply command: `./execution/k3s/bootstrap.sh apply --environment test --through host-baseline`
- Final Phase 1 result: exit `0`; 24 controller checks passed; remote checks passed;
  Ansible reported `ok=16 changed=0 failed=0`.
- Successful convergence result: exit `0`; Ansible reported
  `ok=76 changed=3 failed=0`; the changes corrected SSH drop-in precedence.
- Idempotence result: exit `0`; Ansible reported `ok=75 changed=0 failed=0`.
- Strengthened-evidence idempotence result: exit `0`; Ansible reported
  `ok=80 changed=0 failed=0`.
- Two final check-mode runs each exited `0` and reported
  `ok=76 changed=0 failed=0`; their 15 stable check outcomes matched.
- Reboot result: `reboot_required=false`; no reboot was performed.
- Evidence: `execution/k3s/.evidence/test/phase-2-host-baseline.json`.
- Phase 3 state: no containers, k3s units, MariaDB, Redis, or application workloads
  were deployed.

## Operating Model

The current test environment uses a local Ansible connection to the Ubuntu 24.04 VM.
Every Phase 2 command reruns Phase 1 before entering the baseline role.

```text
bootstrap.sh
  -> Phase 1 controller validation
  -> Phase 1 read-only Ansible preflight
  -> Phase 2 safety checks
  -> Phase 2 check or apply
  -> redacted controller evidence
```

Check mode uses Ansible `--check --diff`, performs read-only safety and verification
probes, and writes only ignored controller evidence. Apply refuses to continue unless a
second public-key SSH connection with non-interactive sudo succeeds, the inspected and
scanned host keys match, a non-loopback administrative CIDR is configured, storage
parents are safe, and no implicit Docker data migration is required.

The operator confirmed console/provider recovery access before apply. The reviewed
administrative CIDR is `192.168.1.0/24`.

## Implementation Inventory

```text
execution/k3s/
  bootstrap.sh
  environments/test/
    platform.yml
    platform.yml.example
  host/
    ansible.cfg
    playbooks/host-baseline.yml
    roles/baseline/
      defaults/main.yml
      handlers/main.yml
      tasks/
        main.yml
        safety.yml
        packages.yml
        storage.yml
        access.yml
        time.yml
        kernel.yml
        swap.yml
        firewall.yml
        logging.yml
        docker.yml
        verify.yml
      templates/
        apt-periodic.j2
        sshd-baseline.conf.j2
        journald-baseline.conf.j2
        docker.list.j2
        docker-daemon.json.j2
  operations/validate/
    host_baseline_report.py
    test_host_baseline_report.py
    test_platform_schema.py
    schemas/platform.schema.json
```

The role manages only Phase 2 state: explicit host packages, SSH safeguards, chrony,
kernel modules and sysctls, swap policy, UFW, journald bounds, platform roots, and
pinned Docker Engine/Compose. It does not create Phase 3 directories or containers.

## Clean-Machine Runbook

Run as the configured non-root automation user with working `sudo -n`, a matching age
identity, a second SSH path, and verified recovery access.

```bash
cd /path/to/moj-docker-deploy
export SOPS_AGE_KEY_FILE="$PWD/execution/k3s/environments/test/age-identity.txt"

./execution/k3s/operations/setup/controller.sh check
./execution/k3s/bootstrap.sh check --environment test
./execution/k3s/bootstrap.sh check --environment test --through host-baseline
```

Review the check-mode diff. Confirm that the configured administrative CIDRs include
the operator source, no existing Docker containers require migration, and console
recovery remains available. Then apply twice and finish with check mode:

```bash
./execution/k3s/bootstrap.sh apply --environment test --through host-baseline
./execution/k3s/bootstrap.sh apply --environment test --through host-baseline
./execution/k3s/bootstrap.sh check --environment test --through host-baseline
```

If evidence reports `reboot_required=true`, reboot explicitly through the provider or
console, reconnect, rerun Phase 1, and repeat the same apply command. Automation never
reboots the host.

## Developer Validation

The following validations passed:

```bash
python3 -m unittest -v \
  execution/k3s/operations/setup/test_controller_validate.py \
  execution/k3s/operations/validate/test_preflight.py \
  execution/k3s/operations/validate/test_platform_schema.py \
  execution/k3s/operations/validate/test_host_baseline_report.py

python3 -m py_compile \
  execution/k3s/operations/setup/controller_validate.py \
  execution/k3s/operations/validate/preflight.py \
  execution/k3s/operations/validate/update_report.py \
  execution/k3s/operations/validate/compare_reports.py \
  execution/k3s/operations/validate/host_baseline_report.py

bash -n execution/k3s/bootstrap.sh execution/k3s/operations/setup/controller.sh

ANSIBLE_CONFIG=execution/k3s/host/ansible.cfg \
  ansible-inventory -i execution/k3s/environments/test/inventory.yml --graph

ANSIBLE_CONFIG=execution/k3s/host/ansible.cfg \
  ansible-playbook -i execution/k3s/environments/test/inventory.yml \
  execution/k3s/host/playbooks/preflight.yml --syntax-check \
  -e platform_file=execution/k3s/environments/test/platform.yml

ANSIBLE_CONFIG=execution/k3s/host/ansible.cfg \
  ansible-playbook -i execution/k3s/environments/test/inventory.yml \
  execution/k3s/host/playbooks/host-baseline.yml --syntax-check \
  -e platform_file=execution/k3s/environments/test/platform.yml \
  -e phase2_facts_path=/tmp/phase-2-facts.json
```

The unit run completed 12 tests. `git diff --check` passed. `shellcheck`, `yamllint`,
`ansible-lint`, and Molecule were unavailable on this host and were not installed as an
implicit side effect of validation.

## Evidence

The final report contains 15 unique passing check IDs and `overall_status: pass`. It
records:

- Phase 1 report identity and pass state;
- Ansible recap and apply history;
- installed, configured, and candidate Docker Engine and Compose versions;
- Docker and chrony service state;
- UFW policy summary and reviewed source/port contract;
- root ownership and modes for all managed roots;
- reboot state and stable acceptance checks.

The configured and installed versions are Docker Engine
`5:29.6.1-1~ubuntu.24.04~noble` and Compose plugin
`5.3.0-1~ubuntu.24.04~noble`. Both are held, along with `docker-ce-cli` and
`containerd.io`. Docker uses `/srv/mokla/docker`, bounded `json-file` logging, zero
containers, and inactive Swarm.

A redaction scan rejected private-key, age-secret, SOPS ciphertext, and AWS access-key
markers. It found none. Two final reports had identical stable check IDs and statuses.

## Issues Encountered and Resolved

| Issue | Cause | Resolution |
| --- | --- | --- |
| Phase 2 initially blocked before mutation | The environment allowed only loopback administration, persistent host-key trust was absent, and Docker had 12 stopped containers under `/var/lib/docker`. | Recovery was confirmed, the admin CIDR was reviewed as `192.168.1.0/24`, SSH proof now uses a verified ephemeral known-hosts file, and the operator authorized removal of the 12 stopped containers. Images and volumes were not removed. |
| Read-only probes were skipped in check mode | Ansible command and URI actions defaulted to check-mode skip behavior. | Safety, Docker-key, and verification probes explicitly use `check_mode: false` with `changed_when: false`. |
| First mutation run stopped after `ok=74 changed=21 failed=1` | A colon-bearing UFW assertion was parsed as a non-string conditional. | The expression was quoted; the immediate repair run reached `ok=73 changed=1 failed=0`. |
| Evidence still failed after host convergence | Ubuntu cloud-init set `PasswordAuthentication yes` in an earlier SSH drop-in; OpenSSH retained the first value. | The managed policy moved to `00-mokla-baseline.conf`, the obsolete file was removed, the complete config is validated with `sshd -t`, and SSH is reloaded only after validation. The corrective apply passed with `ok=76 changed=3 failed=0`. |
| A stricter idempotence audit stopped at `ok=78 changed=0 failed=1` | The evidence assertion expected inactive UFW wording for the routed default. | The assertion now matches active UFW's `deny (routed)` policy. The rerun passed with `ok=80 changed=0 failed=0`. |
| A later check-mode run reported `changed=1` on a converged host | The Docker repository metadata refresh reported transient APT cache activity as managed-state drift. | The refresh remains enabled but no longer contributes to Ansible change accounting. The full validation suite and Phase 2 check passed with `ok=76 changed=0 failed=0`. |
| Probing the dormant `lxc` launcher installed the LXD snap | The host command was an on-demand wrapper rather than an already installed VM runtime. | No LXD instances existed; the newly installed LXD snap was removed and its absence was verified. |

## Current Gaps

- The single-host environment proved allowed SSH access through a second connection but
  cannot originate a meaningful disallowed-source firewall probe. UFW policy and rule
  state were verified locally; an external denied-source test remains for an environment
  with a second network vantage point.
- No reboot path was exercised because the host never reported one was required.
- `ansible-lint`, YAML lint, shellcheck, and Molecule remain unavailable locally.
- The authorized container cleanup left the old `/var/lib/docker` image/volume data
  untouched. Docker now uses the configured empty `/srv/mokla/docker` root.
- The pre-existing `dmoj/repo` nested-repository modification was not touched, staged, or
  reverted.

## Next Steps

Phase 2 is complete for this local VM. Stop here. Before Phase 3 begins, review this
evidence, independently test denied-source firewall behavior from another host when one
is available, and confirm the Phase 3 preconditions. Do not deploy MariaDB, Redis, k3s,
or application workloads as part of this phase.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-19 | Added the complete Phase 2 schema, reviewed Docker pins, and focused schema/report tests. | Schema validation passed for both platform files; all focused tests passed. |
| 2026-09-19 | Added safety-first check/apply dispatch, the baseline role, validated templates, rollback behavior, and redacted evidence. | Python/shell compilation, inventory discovery, and both playbook syntax checks passed. |
| 2026-09-19 | Resolved access, Docker migration, check-mode probe, SSH precedence, and evidence assertion failures encountered on the VM. | Successful convergence reached `ok=76 changed=3`; no reboot was required. |
| 2026-09-19 | Proved idempotence and final clean check mode with strengthened acceptance evidence. | Apply reached `ok=80 changed=0`; two final checks each reached `ok=76 changed=0`; Phase 1 independently remained `ok=16 changed=0`. |
| 2026-09-19 | Excluded transient Docker repository metadata refreshes from managed-state change accounting. | All 12 tests and documented static checks passed; Phase 2 check reached `ok=76 changed=0 failed=0`. |