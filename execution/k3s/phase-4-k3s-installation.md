# Phase 4 Implementation Plan: k3s Installation

Status: ready for implementation after Phase 3 passes.

## Mission

Install one exact k3s release on the prepared host and prove that the Kubernetes control
plane and bundled core components are healthy and repeatably configured. This phase owns
the host-level k3s process and bootstrap administrator access only. It does not create
platform namespaces, policies, add-ons, or application workloads.

## Context and Authority

Read [k3s Cluster Blueprint](README.md),
[Repeatable k3s Deployment Strategy](repeatable-deployment.md), and the Phase 1-3 plans
before implementation. Earlier evidence must identify the same environment and host.

The fixed initial topology is one k3s server using:

- the default SQLite datastore;
- bundled containerd, Flannel, CoreDNS, Traefik, ServiceLB, local-path provisioner, and
  network-policy controller;
- `/srv/mokla/k3s`-owned persistent paths, separate from Docker and host data services;
- no agents, embedded etcd, external k3s datastore, custom CNI, or GitOps controller.

The MariaDB and Redis created in Phase 3 are application services. They must never be
configured as the k3s control-plane datastore.

## Preconditions

- Phases 1-3 have passing, current evidence and Phase 2 reports no pending reboot.
- Host MariaDB/Redis are healthy and their latest off-host backup is fresh.
- Pod/service CIDRs passed overlap checks and are frozen for this cluster identity.
- TCP 6443 is restricted to configured administrative CIDRs.
- Exact `k3s_version`, release checksum/source, node name, TLS SANs, bind address, and
  storage paths are present in the Phase 1-owned schema.
- The operator has console access and a verified pre-change host backup.

## Required Configuration

The shared schema must provide:

```yaml
k3s:
  version: <exact-vX.Y.Z+k3sN>
  checksum: <approved-release-checksum>
  node_name: <stable-name>
  node_ip: <stable-private-address>
  api_bind_address: <stable-private-address>
  tls_sans: [<admin-visible DNS name or address>]
  cluster_cidr: 10.42.0.0/16
  service_cidr: 10.43.0.0/16
  cluster_dns: 10.43.0.10
  data_dir: /srv/mokla/k3s/server
  local_storage_path: /srv/mokla/k3s/storage
  kubeconfig_output: <ignored controller-side path>
  secrets_encryption: true
```

Angle-bracket values must be resolved before apply. Pin the
`k3s-io/k3s-ansible` collection by release or commit and record its checksum through
Ansible dependency metadata. Review upstream defaults; local values must explicitly
override any behavior that conflicts with the blueprint.

## Intended Ownership

```text
execution/k3s/host/
  requirements.yml
  playbooks/
    k3s-installation.yml
  roles/
    k3s/
      defaults/main.yml
      tasks/main.yml
      tasks/validate.yml
      tasks/install.yml
      tasks/kubeconfig.yml
      tasks/verify.yml
      templates/config.yaml.j2
      templates/k3s-installation-report.json.j2
```

The local role validates project policy and invokes the pinned upstream collection. Do
not copy upstream role code into this repository. Ansible owns `/etc/rancher/k3s`, k3s
systemd state, and host paths; it does not own arbitrary Kubernetes objects.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh check --environment test --through k3s-installation
./execution/k3s/bootstrap.sh apply --environment test --through k3s-installation
```

All prerequisite phases run first. Check mode renders configuration and validates inputs
without installing, upgrading, restarting, or uninstalling k3s.

## Implementation Requirements

1. Create k3s data/storage parents with restrictive ownership and reject unsafe,
   symlinked, non-empty unowned paths.
2. Download the exact release through the pinned collection and verify its checksum
   before installation. Never use a mutable channel such as `stable` during apply.
3. Render one explicit `/etc/rancher/k3s/config.yaml` with mode `0600`.
4. Configure the fixed node identity, addresses, CIDRs, TLS SANs, data directory, default
   local-storage path, and secrets encryption.
5. Keep bundled Traefik, CoreDNS, ServiceLB, local-path provisioner, Flannel, and the
   network-policy controller enabled. Do not silently replace bundled components.
6. Ensure k3s starts after network readiness. Do not make it depend on MariaDB or Redis.
7. Keep the server token in a root-only file and encrypted off-host backup; never commit
   or print it.
8. Retrieve the bootstrap administrator kubeconfig to an ignored controller path with
   mode `0600`, rewrite only its server endpoint, and verify the endpoint is a configured
   TLS SAN.
9. Do not merge this kubeconfig into a user's global kubeconfig automatically.
10. Label evidence clearly: bootstrap administrator access is temporary for platform
    establishment. Phase 5 creates restricted routine identities.

## Health and Behavior Checks

- `k3s` systemd unit is enabled and active.
- Node reports `Ready` with the exact configured Kubernetes/k3s version and node name.
- API is reachable only from an allowed administrative source.
- CoreDNS resolves a test service from a disposable pod.
- Traefik, ServiceLB, local-path provisioner, metrics-server if bundled, and network-policy
  controller components are healthy.
- A disposable PVC using the bundled local-path class binds under the configured storage
  root, survives pod recreation, and is deleted cleanly afterward.
- A disposable ClusterIP service is reachable inside the cluster.
- No workload can connect to host MariaDB/Redis unless Phase 3 firewall policy explicitly
  allows the pod CIDR; record the result without creating application credentials.
- Host Docker containers and k3s containerd remain healthy and use distinct data roots.
- Restarting k3s preserves cluster identity and does not disturb host data services.

Use a dedicated temporary namespace such as `platform-install-smoke`; remove it after
checks. Test fixtures are platform validation resources, not application workloads.

## Idempotence and Upgrade Safety

- A second apply with unchanged inputs reports no unintended changes or restart.
- Check mode after convergence is clean.
- Changing `k3s.version` is not an ordinary apply. Detect it and stop with an
  upgrade-required message until the Phase 4 upgrade workflow is implemented and invoked
  explicitly.
- Changing cluster/service CIDRs, data directory, node identity, or datastore mode after
  initialization is a rebuild/migration, not convergence; fail closed.
- Ordinary apply never uninstalls k3s, deletes SQLite, rotates the token, or resets the
  kubeconfig.

## Failure and Recovery Behavior

- A failed binary/checksum validation leaves the running installation unchanged.
- A failed first startup preserves logs and configuration and blocks later phases.
- Never run the k3s uninstall script automatically.
- If configuration validation fails, do not restart a healthy k3s service.
- Record the previous effective configuration hash before an accepted change.
- Back up the server token, config, and SQLite state after successful installation using
  the existing off-host backup mechanism; do not claim restore support until Phase 8.

## Implementation Sequence

1. Pin and install the upstream Ansible collection in controller dependencies.
2. Extend semantic validation for immutable k3s inputs and path/CIDR constraints.
3. Implement host path and explicit config rendering.
4. Invoke the upstream collection for a single server with exact version/checksum.
5. Securely retrieve and validate bootstrap kubeconfig.
6. Implement component, DNS, storage, network, restart, and runtime-separation checks.
7. Add configuration-change guards and redacted evidence.
8. Run first apply, restart validation, second apply, and final check mode on a disposable
   VM.

## Acceptance Tests

Run and record:

```bash
./execution/k3s/bootstrap.sh check --environment test --through k3s-installation
./execution/k3s/bootstrap.sh apply --environment test --through k3s-installation
./execution/k3s/bootstrap.sh apply --environment test --through k3s-installation
./execution/k3s/bootstrap.sh check --environment test --through k3s-installation
```

Prove all health checks above, then reboot the VM and prove host data services and k3s
recover automatically. Also prove that an incorrect checksum, unsupported version
change, CIDR change, and unapproved non-empty data path fail before mutation.

Run shell/YAML/Ansible lint, syntax/check mode, and a disposable-VM integration test.

## Evidence and Completion Gate

Write a redacted report to
`execution/k3s/.evidence/<environment>/phase-4-k3s-installation.json`. Include previous
phase evidence IDs, collection and k3s versions, binary checksum, non-secret config hash,
component versions/health, storage/DNS/network checks, reboot result, first/second-run
recaps, and overall status.

Phase 4 is complete only when the exact release is healthy after reboot, the second apply
is idempotent, final check mode is clean, bootstrap credentials are protected, host data
services remain healthy, and Phase 5 can use the cluster API without undocumented setup.

## Non-Goals

- HA, agents, embedded etcd, external k3s datastore, custom CNI, or load-balancer changes.
- Platform namespaces, RBAC, quotas, default policies, add-ons, GitOps, or applications.
- Routine deployment credentials; these belong to Phase 5.