# Phase 1 Preflight Progress

Status: in progress

Last updated: 2026-09-18

This document is the working progress record for Phase 1. Update it as implementation
and validation advance. The normative requirements remain in
[phase-1-preflight.md](../phase-1-preflight.md).

## Current Direction

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

The target remains one supported Ubuntu 24.04 `x86_64` machine with `systemd`. The
single machine may eventually run Docker-managed MariaDB and Redis alongside a
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

## Implemented Files

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
    update_report.py                            # report update after Ansible execution
    schemas/platform.schema.json                # platform contract
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

## Current Validation Commands

Check the wrapper interface:

```bash
./execution/k3s/bootstrap.sh --help
```

Validate the standalone scripts:

```bash
python3 -m py_compile \
  execution/k3s/operations/validate/preflight.py \
  execution/k3s/operations/validate/update_report.py
bash -n execution/k3s/bootstrap.sh
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
assert platform["connection"]["mode"] == "local"
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

Run the local preflight:

```bash
./execution/k3s/bootstrap.sh check --environment test
```

The current test run is expected to fail closed until SOPS, age, and an operator-created
`secrets.sops.yml` are available. The command must still write a report.

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
- stable check IDs, statuses, evidence, and remediation hints;
- overall status;
- remote check result.

Evidence is ignored by Git. Secret values, decrypted files, age identities, and
kubeconfigs are also covered by ignore rules.

## Current Gaps

Phase 1 is not complete yet. The current implementation still needs:

- real SOPS/age decryptability and required-key validation;
- pinned Ansible collection installation/verification;
- complete Phase 1 schema coverage for the full Phase 2 and Phase 3 contracts;
- remote host facts for CPU, memory, disks, storage-root suitability, time, DNS, routes,
  CIDR overlap, ports, conflicting services, and outbound HTTPS;
- structured remote facts and check results in the final report rather than only the
  initial Ansible success/failure status;
- negative fixtures for invalid schema, overlapping CIDRs, low disk/memory, unsupported
  OS/architecture, and secret redaction;
- disposable-machine validation and a second-run repeatability check.

These gaps should be addressed before starting Phase 2 host mutation.

## Next Implementation Sequence

1. Complete local Phase 1 controller checks and secret handling.
2. Expand the local Ansible preflight checks and evidence collection.
3. Add focused fixture tests and stable report assertions.
4. Prove two consecutive local checks produce equivalent check outcomes.
5. Only after Phase 1 passes locally, implement Phase 2 check/apply behavior.
6. Add SSH as a separate connection mode without changing phase role ownership.

## Update Log

| Date | Change | Validation |
| --- | --- | --- |
| 2026-09-18 | Established local-first execution, standalone Python validation scripts, explicit report updater, and localhost inventory. | Shell syntax, Python compilation, schema validation, Ansible inventory discovery, playbook syntax, and fail-closed wrapper run passed. |

Add one row for each meaningful implementation or validation milestone.
