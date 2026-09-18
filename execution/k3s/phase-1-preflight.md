# Phase 1 Implementation Plan: Preflight

Status: ready for implementation planning; implementation must not provision or mutate
the target host.

## Mission

Implement the first phase of the [Repeatable k3s Deployment Strategy](repeatable-deployment.md):
given a clean candidate VM and a selected environment definition, determine whether the
host and all required external inputs are suitable for later platform deployment.

This phase produces a deterministic, machine-readable readiness report. It does not
install packages, alter files, open ports, create users, or start services.

## Architectural Context

The target is initially one Linux VM running:

- host-level MariaDB and Redis outside Kubernetes;
- one single-server k3s cluster using SQLite, bundled Traefik, CoreDNS, ServiceLB, and
  local-path storage;
- later, in-cluster certificate, observability, alerting, and backup add-ons;
- application workloads only after all platform and recovery gates pass.

The VM is one failure domain. Off-host backups are mandatory. Host automation owns the
VM and k3s installation; Kustomize and Helm will later own in-cluster resources.

Read these documents before implementation:

1. [k3s Cluster Blueprint](README.md)
2. [Repeatable k3s Deployment Strategy](repeatable-deployment.md)
3. [Phase 2 Host Baseline](phase-2-host-baseline.md)
4. [Phase 3 Host Data Services](phase-3-host-data-services.md)

If a conflict exists, the blueprint wins, followed by the deployment strategy, followed
by this phase plan.

## Fixed Initial Baseline

Implement and test the first version against these defaults:

| Concern | Baseline |
| --- | --- |
| Target OS | Ubuntu Server 24.04 LTS |
| Architecture | `x86_64` / `amd64` |
| Init system | `systemd` |
| Automation | `ansible-core`, pinned in dependency metadata |
| Connection | SSH with a non-root automation user and `sudo` |
| Python on target | Python 3 |
| Initial topology | One host, one future k3s server |
| Secret model | SOPS with age, unless replaced by an accepted decision |
| Configuration format | YAML inventory and environment variables files |

Other operating systems and architectures are out of scope for the first implementation.
Do not silently accept them. Report them as unsupported with an actionable message.

## Required Inputs

Create one environment directory per installation:

```text
execution/k3s/environments/<environment>/
  inventory.yml
  platform.yml
  secrets.sops.yml
```

Commit sanitized examples for `test`; do not commit usable secrets.

`inventory.yml` must identify exactly one host in a `platform_host` group and define:

- inventory hostname;
- SSH address and port;
- SSH automation user;
- Python interpreter path.

`platform.yml` must define, with no hidden defaults for network-sensitive values:

- `environment_name`;
- `host_fqdn` and expected static or reserved host address;
- administrative source CIDRs allowed to reach SSH and the future Kubernetes API;
- public ingress ports, initially TCP 80 and 443;
- pod and service CIDRs, with proposed defaults `10.42.0.0/16` and `10.43.0.0/16`;
- host storage root, proposed default `/srv/mokla`;
- minimum CPU, memory, root-disk free space, and storage-root free space;
- DNS names needed by the platform;
- off-host restic repository type and non-secret location;
- age recipient(s) used to encrypt environment secrets;
- MariaDB and Redis private bind address and intended ports;
- whether Redis data is `persistent` or `disposable`;
- NTP source policy;
- selected k3s version placeholder for Phase 4 compatibility.
- the complete Phase 2 `host` and `docker` configuration blocks, including paths,
  package versions, Docker repository identity, update policy, logging bounds, and reboot
  policy;
- the complete Phase 3 `data_services` configuration block, including bind address,
  allowed client CIDRs, TLS policy, digest-pinned MariaDB and Redis images, ports, paths,
  resource limits, and Redis persistence policy;
- the complete Phase 3 `backup` configuration block, including the non-secret restic
  repository location, staging path, schedule, retention, freshness threshold, and
  restore-test isolation settings.

The exact nested Phase 2 and Phase 3 fields are specified in their linked implementation
plans and are part of the Phase 1 schema. Phase 1 owns schema assembly and validation;
later phases consume the same schema version and must not introduce private replacement
variables.

`secrets.sops.yml` must define the secret keys expected by later phases, using placeholder
or encrypted values only:

- MariaDB root/bootstrap password;
- Redis authentication secret if authentication is enabled;
- restic repository password and repository credentials;
- MariaDB/Redis TLS server certificate, private key, and issuing CA certificate;
- future k3s token or a policy indicating that it is generated during Phase 4;
- age metadata produced by SOPS.

Preflight checks the presence and decryptability of required keys but must never print
their values. If SOPS/age is not yet accepted, implement the secret interface and fixture
tests, but fail real-environment preflight with `secret_provider_not_configured`.

## Intended File Ownership

The implementation should create only the minimum structure required by this phase:

```text
execution/k3s/
  bootstrap.sh
  environments/
    test/
      inventory.yml.example
      platform.yml.example
      secrets.sops.yml.example
  host/
    ansible.cfg
    requirements.yml
    playbooks/
      preflight.yml
    roles/
      preflight/
        defaults/main.yml
        tasks/main.yml
        templates/preflight-report.json.j2
  operations/
    validate/
      schemas/
        platform.schema.json
```

Equivalent internal Ansible filenames are acceptable only if the public interface and
responsibility boundaries remain unchanged. Do not create Phase 2 or Phase 3 resources.

## Operator Interface

The required command is:

```bash
./execution/k3s/bootstrap.sh check --environment test
```

The script must:

1. resolve its own repository-relative paths;
2. reject execution as root;
3. reject an unknown environment or missing input file;
4. verify local controller dependencies without making network downloads;
5. invoke the preflight playbook with the selected inventory and variables;
6. preserve the Ansible exit status;
7. print the report path and a concise pass/fail summary.

Support `--help`. Unknown options and missing option values return exit code `2`.
Preflight failure returns non-zero. Do not add an implicit default environment.

## Required Checks

### Controller checks

- Required local commands exist at supported versions: Bash, Python, Ansible,
  `ansible-galaxy`, SOPS, age, SSH, and a JSON-schema validator selected by the
  implementation.
- Required Ansible collections are installed at versions pinned in `requirements.yml`.
- Environment YAML parses and conforms to `platform.schema.json`.
- The encrypted secret file is present, is not plaintext, and can be decrypted using the
  operator-provided age identity.
- No secret value is included in normal or verbose output.

Phase 1 must not automatically install controller dependencies. A later bootstrap apply
path may do so only after an explicit design decision.

### Remote host checks

- SSH connectivity and `sudo -n true` succeed for the automation user.
- `/etc/os-release` identifies Ubuntu 24.04.
- Machine architecture is `x86_64`.
- PID 1 is `systemd`; Python 3 and required basic shell utilities are available.
- Configured hostname and host address match the target or report the exact mismatch.
- CPU count, available memory, and free space meet configured minimums.
- The storage-root parent filesystem exists, is writable only where expected, and has
  enough capacity. Preflight must not create the storage root.
- Time is synchronized and the configured NTP policy can be satisfied.
- Forward and reverse DNS results are recorded; reverse DNS may be a warning when the
  environment explicitly allows its absence.
- Pod and service CIDRs do not overlap each other or any detected host route. Any
  configured VPN/home/cloud CIDRs must be included in the overlap test.
- Required public and administrative ports are not occupied by conflicting processes.
  SSH on its declared port is expected and is not a conflict.
- No existing k3s, kubelet, Docker Swarm, MicroK8s, or conflicting Kubernetes state is
  present. Existing Docker alone may be reported but is not automatically rejected.
- Required outbound HTTPS endpoints resolve and are reachable. Keep the endpoint list in
  configuration and include Ubuntu repositories, GitHub release assets, required OCI
  registries, and the selected backup destination.
- Virtualization and filesystem type are recorded for support evidence.

Checks must distinguish `pass`, `fail`, `warning`, and `not_applicable`. Warnings do not
change the exit status unless the environment declares them fatal.

## Report Contract

Write a redacted JSON report under an ignored evidence directory such as:

```text
execution/k3s/.evidence/<environment>/phase-1-preflight.json
```

The report must contain:

- schema version and phase identifier;
- UTC start/end timestamps;
- repository commit when available and dirty-worktree boolean;
- environment and inventory hostname;
- detected OS, architecture, resources, routes, DNS, and filesystem information;
- each check ID, severity, status, concise evidence, and remediation hint;
- overall status;
- no passwords, tokens, decrypted values, private keys, or complete secret-bearing URLs.

Use stable check IDs such as `host.os.supported`, `network.cidr.no_overlap`, and
`secrets.decryptable` so later automation can consume results.

## Security Requirements

- Mark all secret-handling Ansible tasks `no_log: true`.
- Never pass secrets on a command line where process listings can expose them.
- Never copy decrypted secret files to the target host.
- Do not weaken SSH host-key checking in production configuration.
- Do not use `curl | sh`, add repositories, call `apt`, or mutate firewall rules.
- Add `.gitignore` coverage for `.evidence/`, decrypted secret files, local age keys,
  generated inventory, and kubeconfigs before generating those artifacts.

## Implementation Sequence

1. Add ignored-artifact rules and sanitized environment examples.
2. Define and test the platform configuration schema.
3. Pin controller-side Ansible dependencies.
4. Implement argument parsing and dependency checks in `bootstrap.sh`.
5. Implement controller configuration and secret checks.
6. Implement remote host facts and readiness checks.
7. Generate the stable redacted report.
8. Add automated tests for argument parsing, schema rejection, secret redaction, and
   report aggregation.
9. Run preflight against a disposable supported VM and at least one intentionally invalid
   fixture.

## Acceptance Tests

At minimum, demonstrate and record:

```bash
./execution/k3s/bootstrap.sh --help
./execution/k3s/bootstrap.sh check --environment test
./execution/k3s/bootstrap.sh check --environment does-not-exist
```

Also run the repository's selected shell lint, YAML lint, Ansible lint/syntax check, and
JSON-schema tests. The implementation must prove:

1. A conforming Ubuntu 24.04 VM produces overall `pass` without mutation.
2. A second run produces the same check outcomes apart from timestamps and transient
   measurements.
3. An overlapping CIDR causes a named failure.
4. Insufficient disk or memory causes a named failure.
5. Missing or undecryptable secrets cause a named failure without leaking content.
6. Unsupported OS and architecture fail clearly.
7. Check mode does not change the remote filesystem, packages, users, services, firewall,
   or kernel settings.

## Completion Gate

Phase 1 is complete only when:

- all required inputs are represented by schema-validated examples;
- the supported VM passes every required check;
- negative fixtures fail for the intended reason;
- the report is stable, redacted, and machine-readable;
- controller and target mutation checks show no changes;
- Phase 2 can consume the same inventory and environment contract without redefining it.

## Non-Goals

- Installing Ansible or other controller tools automatically.
- Changing the target host.
- Installing Docker, MariaDB, Redis, k3s, Helm, or Kustomize.
- Creating DNS records, firewall rules, users, directories, databases, or secrets.
- Selecting application schemas, database users, or Kubernetes workloads.
- Supporting multiple hosts, operating systems, or architectures in the first version.