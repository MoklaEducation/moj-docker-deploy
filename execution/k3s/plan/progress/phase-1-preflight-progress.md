# Phase 1 Preflight Progress

Status: local gate passing; hardening and coverage still in progress

Last updated: 2026-09-19

This document is the working progress record for Phase 1. Update it as implementation
and validation advance. The normative requirements remain in
[phase-1-preflight.md](../phase-1-preflight.md).

## Status Snapshot

- Public command: `./execution/k3s/bootstrap.sh check --environment test`
- Latest result: exit `0`, 24 controller checks passed, remote checks passed, and
  Ansible reported `localhost: ok=16`.
- Supported local test hosts: Ubuntu 24.04 or 26.04 on `x86_64` with `systemd`.
- Connection mode: local Ansible connection to `localhost`.
- Mutation policy: Phase 1 preflight is read-only.
- Evidence: `execution/k3s/.evidence/test/phase-1-preflight.json`.
- Completion state: the local gate passes; schema depth, structured Ansible evidence,
  negative fixtures, and disposable-machine coverage remain incomplete.

The implementation now accepts Ubuntu 24.04 and 26.04 for the test environment. The
normative Phase 1 and later phase plans still describe Ubuntu 24.04 as the fixed baseline;
that documentation difference must be resolved before treating 26.04 as a production
support commitment.

## Operating Model

The initial implementation is local-first. The machine running the command is also the
single target machine. Remote SSH execution remains an extension point for later, after
the local workflow is mature and repeatable.

```text
operator command
  -> bootstrap.sh
  -> explicit validation scripts
  -> Ansible local connection
  -> localhost
```

The target remains one explicitly selected Ubuntu `x86_64` machine with `systemd`. The
current local environment supports Ubuntu 24.04 and 26.04; this compatibility list must
be revisited before deploying to a different target.
A single machine may eventually run Docker-managed MariaDB and Redis alongside a
single-server k3s installation.

## Operating Principles

### Local first, SSH later

- `local` is the only currently supported execution mode.
- The inventory uses one `platform_host` named `localhost` with
  `ansible_connection: local`.
- Phase roles and playbooks must remain connection-agnostic.
- SSH-specific inventory fields and checks belong behind a future `ssh` connection mode.
- Local execution still uses Ansible privilege escalation where host changes require it;
  the operator should not run the wrapper as root.
- Network checks are not discarded permanently. Checks needed by k3s, ingress, service
  binding, DNS, outbound downloads, and backups still apply. SSH reachability checks are
  mode-specific.

### Python is explicit infrastructure

- Python is used for structured controller work: YAML parsing, JSON Schema validation,
  check aggregation, and JSON evidence generation.
- Python 3 is also the expected interpreter for Ansible modules on the target machine.
- Python is not hidden inside shell command substitutions or large shell heredocs.
- Python dependencies must remain explicit and must not be installed automatically by a
  read-only preflight.

### Scripts are explicit and independently runnable

- `bootstrap.sh` is a small operator-facing dispatcher and argument parser.
- Validation logic belongs in named scripts under `operations/validate/`.
- Each operational script should have its own CLI, help output, exit status, and narrow
  responsibility so it can be run manually and tested without the wrapper.
- Ansible playbooks and roles own host inspection or convergence; they should not be
  reimplemented in the wrapper.
- Generated evidence is machine-readable, redacted, and stored under `.evidence/`.

### Repeatability and safety

- Phase 1 is read-only: it must not install packages, create users, write target files,
  open ports, or start services.
- Missing prerequisites fail clearly and do not trigger network downloads or implicit
  installation.
- Secrets must remain encrypted and must never appear in normal output or evidence.
- Later destructive operations such as restore, rebuild, and upgrade must remain
  explicit commands rather than side effects of ordinary convergence.

## Implementation Inventory

The current Phase 1 controller surface is:

```text
execution/k3s/
  bootstrap.sh                                  # small public dispatcher
  environments/test/
    inventory.yml                               # localhost Ansible inventory
    inventory.yml.example                       # sanitized inventory example
    platform.yml                                # local test platform definition
    platform.yml.example                        # sanitized platform example
    secrets.sops.yml.example                    # encrypted-secret shape only
  host/
    ansible.cfg                                 # deterministic Ansible settings
    requirements.yml                            # pinned collection metadata
    playbooks/preflight.yml                    # read-only host inspection
  operations/validate/
    preflight.py                                # controller validation and report creation
    test_preflight.py                           # missing-command regression tests
    update_report.py                            # report update after Ansible execution
    compare_reports.py                          # stable repeatability comparison
    schemas/platform.schema.json                # platform contract
  operations/setup/
    controller.sh                               # explicit controller check/install helper
    controller_validate.py                      # standalone pinned dependency checker
    test_controller_validate.py                 # dependency-selection regression tests
    controller-requirements.txt                 # pinned Python controller dependencies
```

Generated local state is ignored by Git:

```text
execution/k3s/.controller-venv/                 # pinned local controller environment
execution/k3s/.evidence/                        # generated reports
execution/k3s/environments/*/age-identity*      # private age identities
execution/k3s/environments/*/secrets.sops.yml   # encrypted environment secrets
```

### Public wrapper

```bash
./execution/k3s/bootstrap.sh check --environment test
```

`bootstrap.sh` currently:

1. Parses the public command and environment name.
2. Rejects root execution.
3. Calls `operations/validate/preflight.py`.
4. Stops if controller validation fails.
5. Runs the read-only Ansible preflight playbook using the selected inventory.
6. Calls `operations/validate/update_report.py`.
7. Returns the Ansible exit status.

### Standalone validation scripts

Controller validation can be run without the wrapper:

```bash
./execution/k3s/operations/validate/preflight.py \
  --environment test \
  --environment-dir execution/k3s/environments/test \
  --schema execution/k3s/operations/validate/schemas/platform.schema.json \
  --report execution/k3s/.evidence/test-manual/phase-1-preflight.json \
  --repository .
```

The Ansible result updater can also be run directly when working with a manually
executed playbook:

```bash
./execution/k3s/operations/validate/update_report.py \
  --report execution/k3s/.evidence/test-manual/phase-1-preflight.json \
  --ansible-status 0
```

Compare two saved reports while ignoring timestamps, repository metadata, and
transient evidence:

```bash
./execution/k3s/operations/validate/compare_reports.py \
  --first execution/k3s/.evidence/test-first/phase-1-preflight.json \
  --second execution/k3s/.evidence/test-second/phase-1-preflight.json
```

## Clean-Machine Runbook

Run these commands as a non-root operator with `sudo` access from a fresh repository
checkout. The target and controller are the same machine in the current local workflow.

### 1. Enter the repository

```bash
cd /path/to/moj-docker-deploy
```

### 2. Install and verify controller prerequisites

```bash
./execution/k3s/operations/setup/controller.sh install
./execution/k3s/operations/setup/controller.sh check
```

The explicit `install` action:

- acquires a nonblocking lock so only one setup process runs;
- creates the ignored `.controller-venv` only when absent;
- invokes pip only when pinned Python packages do not match;
- installs `age` through apt only when absent;
- installs SOPS 3.9.4 only when a matching installation is unavailable, verifies its
  SHA-256 checksum, and atomically moves it into the local controller environment;
- installs only missing or mismatched pinned Ansible collections;
- cleans temporary files and validates the complete result before returning success.

### 3. Review environment inputs

```bash
cp -n execution/k3s/environments/test/inventory.yml.example \
  execution/k3s/environments/test/inventory.yml
cp -n execution/k3s/environments/test/platform.yml.example \
  execution/k3s/environments/test/platform.yml
```

Review `inventory.yml` and `platform.yml` before continuing. The committed test files may
already exist, in which case `cp -n` leaves them unchanged.

### 4. Create an age identity

```bash
umask 077
IDENTITY="$PWD/execution/k3s/environments/test/age-identity.txt"
age-keygen -o "$IDENTITY"
RECIPIENT="$(age-keygen -y "$IDENTITY")"
export SOPS_AGE_KEY_FILE="$IDENTITY"
```

The `age1...` recipient is public and encrypts data. The identity file contains the
private key and must remain private. A recipient cannot recreate its private identity.

### 5. Create and encrypt environment secrets

Create a temporary file outside the repository-managed environment directory:

```bash
PLAINTEXT="$(mktemp)"
chmod 0600 "$PLAINTEXT"
${EDITOR:-vi} "$PLAINTEXT"
```

Populate exactly these keys. Test placeholders satisfy Phase 1 presence checks, but real
TLS PEM material is required before Phase 3:

```yaml
mariadb_root_password: REPLACE_FOR_THIS_ENVIRONMENT
redis_password: REPLACE_FOR_THIS_ENVIRONMENT
restic_password: REPLACE_FOR_THIS_ENVIRONMENT
data_services_tls_certificate: TEST_ONLY_REPLACE_BEFORE_PHASE_3
data_services_tls_private_key: TEST_ONLY_REPLACE_BEFORE_PHASE_3
data_services_ca_certificate: TEST_ONLY_REPLACE_BEFORE_PHASE_3
k3s_token_policy: generate_during_phase_4
```

Do not put the `age1...` recipient or age private identity inside this YAML document.
Encrypt it and immediately remove the plaintext file:

```bash
SOPS="$PWD/execution/k3s/.controller-venv/bin/sops"
"$SOPS" --encrypt \
  --age "$RECIPIENT" \
  --output execution/k3s/environments/test/secrets.sops.yml \
  "$PLAINTEXT"
rm -f "$PLAINTEXT"
"$SOPS" --decrypt execution/k3s/environments/test/secrets.sops.yml >/dev/null
```

### 6. Run the public preflight

```bash
export SOPS_AGE_KEY_FILE="$PWD/execution/k3s/environments/test/age-identity.txt"
./execution/k3s/bootstrap.sh check --environment test
```

Expected result:

```text
Phase 1 preflight: pass
localhost : ok=16
```

The exact Ansible recap spacing may differ. The command must exit `0`, and the evidence
report must show `overall_status: pass` and `remote_checks: pass`.

### 7. Prove repeatability

```bash
REPORT="execution/k3s/.evidence/test/phase-1-preflight.json"
cp "$REPORT" /tmp/phase-1-preflight-first.json
./execution/k3s/bootstrap.sh check --environment test
cp "$REPORT" /tmp/phase-1-preflight-second.json
./execution/k3s/operations/validate/compare_reports.py \
  --first /tmp/phase-1-preflight-first.json \
  --second /tmp/phase-1-preflight-second.json
rm -f /tmp/phase-1-preflight-first.json /tmp/phase-1-preflight-second.json
```

## Developer Validation

Check the wrapper interface:

```bash
./execution/k3s/bootstrap.sh --help
```

Validate the standalone scripts:

```bash
python3 -m py_compile \
  execution/k3s/operations/setup/controller_validate.py \
  execution/k3s/operations/validate/preflight.py \
  execution/k3s/operations/validate/update_report.py
python3 -m unittest \
  execution/k3s/operations/setup/test_controller_validate.py \
  execution/k3s/operations/validate/test_preflight.py
bash -n \
  execution/k3s/bootstrap.sh \
  execution/k3s/operations/setup/controller.sh
```

Validate the platform schema and localhost inventory:

```bash
python3 - <<'PY'
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator

root = Path("execution/k3s")
schema = json.loads((root / "operations/validate/schemas/platform.schema.json").read_text())
platform = yaml.safe_load((root / "environments/test/platform.yml").read_text())
errors = list(Draft202012Validator(schema).iter_errors(platform))
assert not errors, errors
assert platform["target_connection"]["mode"] == "local"
inventory = yaml.safe_load((root / "environments/test/inventory.yml").read_text())
host = inventory["all"]["children"]["platform_host"]["hosts"]["localhost"]
assert host["ansible_connection"] == "local"
print("local platform and inventory validation passed")
PY
```

Validate Ansible discovery and playbook syntax:

```bash
ANSIBLE_CONFIG=execution/k3s/host/ansible.cfg \
  ansible-inventory \
  -i execution/k3s/environments/test/inventory.yml \
  --graph

ANSIBLE_CONFIG=execution/k3s/host/ansible.cfg \
  ansible-playbook \
  -i execution/k3s/environments/test/inventory.yml \
  execution/k3s/host/playbooks/preflight.yml \
  --syntax-check \
  -e platform_file=execution/k3s/environments/test/platform.yml
```

The public preflight and repeatability commands are defined in the clean-machine runbook
and should be run after these focused checks.

## Evidence

Reports are written to:

```text
execution/k3s/.evidence/<environment>/phase-1-preflight.json
```

The report includes:

- phase and schema version;
- timestamps;
- repository commit and dirty-worktree state;
- environment and connection mode;
- structured local network facts;
- stable check IDs, statuses, evidence, and remediation hints;
- overall status;
- remote check result.

Evidence is ignored by Git. Secret values, decrypted files, age identities, and
kubeconfigs are also covered by ignore rules.

## Issues Encountered and Resolved

| Issue | Cause | Resolution |
| --- | --- | --- |
| Missing `ansible-galaxy` produced a Python traceback | Preflight recorded command absence but invoked the executable unconditionally afterward. | Command discovery now returns resolved paths; dependent collection, SOPS, and network checks fail as named report checks without raising. |
| A fresh machine lacked pinned Python, Ansible, age, SOPS, and collections | The setup helper originally assumed parts of its own toolchain already existed. | Setup now creates an ignored local virtual environment and installs each prerequisite independently only when needed. |
| Repeated SOPS setup attempts exhausted disk space | Concurrent or interrupted setup runs created many complete temporary downloads with no single-instance guard. | A nonblocking lock rejects concurrent runs; SOPS uses one cleaned staging file, verifies its pinned checksum, and moves atomically. |
| SOPS decryption failed after encryption | `SOPS_AGE_KEY_FILE` was unset, pointed at the wrong repository-relative path, or did not match the encryption recipient. | The runbook derives the recipient from the private identity and exports the absolute identity path before encryption and preflight. |
| Secret YAML failed to parse | Age recipient or identity text was appended to the YAML secret document. | The runbook separates plaintext secret keys, public recipient, private identity, and encrypted output. |
| Preflight could not find `secrets.sops.yml` | Only the sanitized example existed. | The runbook now creates the ignored encrypted environment file explicitly and verifies decryption before preflight. |
| Ubuntu 24.04 failed an exact Ubuntu 26.04 assertion | The test environment declared only one exact version despite the current host using 24.04. | The environment contract now explicitly supports 24.04 and 26.04 while continuing to reject unknown distributions and releases. |
| Public ingress port checks failed while Docker workloads were running | Existing containers occupied ports 80 or 443. | Stop or reconfigure only the conflicting workload before preflight; Phase 1 does not stop services automatically. |
| Generated Python caches appeared as untracked files | Repository ignore rules did not cover Python bytecode. | Repository-wide `__pycache__/` and `*.py[cod]` ignore rules were added. |

## Current Gaps

Phase 1 is not complete yet. The current implementation still needs:

- complete Phase 1 schema coverage for the full Phase 2 and Phase 3 contracts;
- structured Ansible facts and individual host check results in the final report rather
  than only the initial Ansible success/failure status;
- negative fixtures for invalid schema, overlapping CIDRs, low disk/memory, unsupported
  OS/architecture, and secret redaction;
- disposable-machine validation; repeated local runs are the current acceptance path.

These gaps should be addressed before starting Phase 2 host mutation.

## Next Implementation Sequence

1. Add structured Ansible facts and individual host check results to the JSON report.
2. Add focused fixture tests and stable report assertions.
3. Only after Phase 1 is complete locally, implement Phase 2 check/apply behavior.
4. Add SSH as a separate connection mode without changing phase role ownership.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-18 | Established local-first execution, standalone Python validation scripts, explicit report updater, and localhost inventory. | Shell syntax, Python compilation, schema validation, Ansible inventory discovery, playbook syntax, and fail-closed wrapper run passed. |
| 2026-09-18 | Added explicit Ubuntu 26.04 policy, verified age/SOPS tooling, encrypted local test secrets, required-key/decryptability checks, pinned collection verification, and expanded read-only host checks. | Controller validation passed with redacted evidence; public local preflight passed with 16 Ansible tasks and zero changes. |
| 2026-09-18 | Re-ran the public local preflight and compared stable check outcomes. | Two consecutive runs produced 14 identical controller check outcomes, overall pass, zero Ansible changes, and no warnings. |
| 2026-09-18 | Added a bounded retry for system time synchronization to tolerate chrony startup convergence. | The local preflight passed after the transient `NTPSynchronized=no` condition, with 16 tasks and zero changes. |
| 2026-09-18 | Added local DNS, HTTPS, address-assignment, and CIDR-overlap checks plus structured local network facts. | Controller and public local preflight passed with all network checks passing and zero target changes. |
| 2026-09-18 | Added explicit controller setup/check scripts and pinned Python controller requirements. | Standalone dependency validation and `controller.sh check` both passed. |
| 2026-09-18 | Added route/hostname evidence and a standalone stable-report comparison tool. | Public local preflight passed; repeatability can be checked without comparing timestamps or transient evidence. |
| 2026-09-18 | Ran the public local preflight twice and compared both saved reports. | 23 stable check outcomes matched; both runs passed with zero Ansible changes. |
| 2026-09-19 | Hardened missing-command handling, added focused regression tests, made controller setup locked and independently idempotent, and allowed Ubuntu 24.04 or 26.04 explicitly. | Unit tests, compilation, schema validation, playbook syntax, and the public preflight passed; the report contains 24 passing checks and remote checks passed. |

Add one row for each meaningful implementation or validation milestone.
