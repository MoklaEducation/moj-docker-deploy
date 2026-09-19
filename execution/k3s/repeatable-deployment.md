# Repeatable k3s Deployment Strategy

Status: proposed for agreement; no implementation is defined here.

## Purpose

Define how a supported clean VM is transformed into a validated, recoverable k3s
platform through one stable operator entry point. The process must be safe to repeat,
must not depend on undocumented changes made directly on the host, and must establish
the operational platform before application manifests are applied.

The target platform is defined in [k3s Cluster Blueprint](README.md). This document
describes deployment responsibilities, sequencing, and the contract between host
automation and Kubernetes configuration. It does not define application workloads.

Implementation discoveries and failure behavior are governed by
[Evolution and Failure Management](evolution-and-failure-management.md). Use that guide
to revise these plans without losing ownership boundaries, evidence, or repeatability.
See [Strategy Visualizations](strategy-visualizations.md) for diagrams connecting phases,
capabilities, maturity, failure routing, and evidence.

## Deployment Model

```text
clean supported VM
  -> bootstrap entry point
  -> host convergence
  -> k3s installation
  -> cluster core
  -> cluster add-ons
  -> platform validation
  -> clean-host recovery rehearsal
  -> application-ready handoff
```

Applications are deliberately deployed only after the platform is repeatably
provisioned and its certificate, observability, backup, and recovery capabilities have
passed the agreed acceptance checks. These capabilities can be implemented and released
independently, but all required baseline capabilities converge at the application-ready
gate.

## Responsibility-Based Layout

Directories describe ownership and intent rather than the tool currently used to
implement them:

```text
execution/k3s/
  README.md                         # target platform blueprint
  repeatable-deployment.md          # this deployment strategy
  bootstrap.sh                      # stable operator entry point

  environments/
    test/
    production/

  host/
    baseline/
    storage/
    data-services/
      mariadb/
      redis/
    k3s/

  cluster/
    core/
      namespaces/
      access/
      policies/
      quotas/
    addons/
      certificates/
      observability/
      backups/

  operations/
    validate/
    backup/
    restore/
    upgrade/
    rebuild/
```

The layout is a responsibility map, not a requirement to create every directory before
it contains an implementation. Add directories incrementally as their delivery phase
begins.

### `environments/`

Owns non-secret differences between installations, such as host addresses, DNS names,
storage locations, resource budgets, and enabled platform capabilities. Secrets are
referenced from environment configuration but stored only through the agreed encrypted
secret mechanism.

### `host/`

Owns everything configured directly on the VM:

- operating-system prerequisites and security baseline;
- users, time synchronization, firewall, kernel settings, and storage paths;
- MariaDB and Redis processes running outside Kubernetes;
- the pinned k3s installation and its host-level configuration.

Ansible is the preferred initial implementation tool inside this responsibility. The
directory remains named `host` because its purpose should survive a future tooling
change.

### `cluster/core/`

Owns the minimum declarative Kubernetes state required before workloads can be safely
onboarded, including namespaces, RBAC, quotas, limit defaults, network policies, storage
classes, and shared access boundaries.

Kustomize is the preferred tool for repository-owned Kubernetes resources and
environment overlays.

### `cluster/addons/`

Owns operational services deployed inside Kubernetes, initially certificate automation,
metrics, logs, dashboards, alerting, and Kubernetes-side backup components. Add-ons have
their own versions, validation, rollback, and release cadence even though their baseline
capabilities are required by the application-ready gate.

Pinned upstream Helm charts are preferred for maintained third-party systems. Custom
Helm charts should be introduced only when Kustomize and chart values cannot express the
required configuration cleanly.

### `operations/`

Owns explicit lifecycle workflows against the assembled platform. Validation, backup,
restore, upgrade, and rebuild are not hidden side effects of ordinary convergence.
Destructive workflows identify their target, run preflight checks, and require explicit
confirmation.

Host-level database backup implementation may live under `host/data-services/`, while
the end-to-end backup and restore workflow belongs under `operations/`.

## Stable Operator Entry Point

`bootstrap.sh` is the initial entry point from a clean VM. It must remain small and
auditable. Its responsibilities are limited to:

1. Verify that the operating system and architecture are supported.
2. Locate or install the pinned minimum automation prerequisites.
3. Select an environment definition.
4. Verify that required encrypted secret inputs are available.
5. Invoke the host convergence workflow.
6. Return a clear result and the next operator action.

It must not contain the actual host, database, k3s, or add-on configuration. Those rules
belong to their owning directories and must also be callable without duplicating logic in
the bootstrap script.

The eventual operator interface should expose a small set of stable actions. Exact
syntax is an implementation decision, but the conceptual interface is:

```text
bootstrap     prepare a clean VM and invoke initial convergence
check         inspect prerequisites and render intended changes
apply         converge host, cluster core, and selected add-ons
validate      run platform acceptance checks
backup        create and verify an off-host backup
restore       restore into an explicitly selected target
upgrade       perform a versioned platform change
rebuild       reconstruct a clean host and validate the result
```

Ordinary `apply` must be safe to rerun. Restore, upgrade, and rebuild remain separate,
explicit operations.

## Deployment Phases

Each phase is independently reviewable and produces validation evidence before the next
phase begins.

### Phase 1: Preflight

Inspect the VM without changing it. Validate the supported OS, CPU, memory, disks,
network ranges, DNS, time, required ports, outbound access, environment configuration,
and secret availability.

Detailed implementation handoff: [Phase 1 Preflight](phase-1-preflight.md).

Exit condition: the host is suitable for the selected environment and the intended
changes can be rendered without unresolved inputs.

### Phase 2: Host Baseline

Converge users, package prerequisites, time synchronization, firewall rules, kernel
settings, storage directories, permissions, and resource limits.

Detailed implementation handoff: [Phase 2 Host Baseline](phase-2-host-baseline.md).

Exit condition: rerunning the host automation reports no unexplained changes and host
checks pass.

### Phase 3: Host Data Services

Install pinned MariaDB and Redis versions outside Kubernetes on the same VM. Bind them
only to the required interfaces, establish stable storage paths, configure health checks,
and integrate their data with encrypted off-host backups.

Detailed implementation handoff:
[Phase 3 Host Data Services](phase-3-host-data-services.md).

This arrangement is intentionally simple but is not a separate failure domain. Loss of
the VM can affect k3s and application data simultaneously. Application plans remain
responsible for schemas, users, migrations, credentials, and data-level validation.

Exit condition: services are healthy, inaccessible from unintended networks, included in
the backup inventory, and recoverable without depending on Kubernetes.

### Phase 4: k3s Installation

Install a checksum-verified, pinned k3s release using explicit configuration. Establish
controlled bootstrap-administrator access. Phase 5 replaces routine use of that access
with separate least-privilege identities and RBAC.

Detailed implementation handoff: [Phase 4 k3s Installation](phase-4-k3s-installation.md).

Exit condition: the node, API, CoreDNS, Traefik, and local-path provisioner are healthy;
the effective version and configuration are recorded; a second run is idempotent.

### Phase 5: Cluster Core

Apply repository-owned namespaces, RBAC, quotas, default limits, network policies,
storage configuration, and secret-delivery foundations.

Detailed implementation handoff: [Phase 5 Cluster Core](phase-5-cluster-core.md).

Exit condition: manifests render, server-side validation passes, access boundaries work,
and allowed and denied network flows are exercised.

### Phase 6: Cluster Add-ons

Install independently pinned and reversible add-ons in dependency order:

1. Certificate management and issuer configuration.
2. Metrics collection and alert routing.
3. Log collection, storage, and dashboards.
4. Kubernetes-side backup integration.

Detailed implementation handoff: [Phase 6 Cluster Add-ons](phase-6-cluster-addons.md).

Exit condition: a staging certificate is issued, platform metrics and logs are visible,
a controlled alert reaches the operator, retention and resource limits are active, and
backup freshness is monitored. Certificate renewal is tested when practical; otherwise
the bounded exception and follow-up required by the blueprint are recorded.

### Phase 7: Platform Validation

Run one acceptance workflow covering host health, data services, Kubernetes API, DNS,
storage, ingress, certificates, network policy, observability, alerting, backups, secret
exposure, resource headroom, and version records.

Exit condition: one report identifies the environment, versions, checks, results, and any
approved bounded exceptions without exposing secrets.

Detailed implementation handoff:
[Phase 7 Platform Validation](phase-7-platform-validation.md).

### Phase 8: Recovery Qualification

Provision a clean test VM from the repository and documented secret inputs. Restore k3s
state, required persistent data, and same-host MariaDB and Redis data from off-host
backups. Run the complete platform validation workflow against the restored environment.

Detailed implementation handoff:
[Phase 8 Recovery Qualification](phase-8-recovery-qualification.md).

Exit condition: the rehearsal meets the agreed RTO and RPO and requires no undocumented
manual host changes.

### Phase 9: Application-Ready Handoff

Publish the validated platform contract: ingress and DNS expectations, secret-delivery
interface, external data-service endpoints, storage classes, namespaces, resource
budgets, image-pull mechanism, supported deployment method, and operational contacts or
procedures.

Detailed implementation handoff:
[Phase 9 Application-Ready Handoff](phase-9-application-ready-handoff.md).

Only after this gate passes may application manifests be applied. Application delivery
then consumes the platform contract without taking ownership of host provisioning,
cluster bootstrap, or shared add-ons.

## Idempotence and Repeatability Contract

A deployment is repeatable only when all of the following are true:

- A clean supported VM can reach the same declared state from version-controlled inputs
  and externally held secrets.
- A second ordinary apply makes no unintended changes.
- Exact k3s, package, chart, and image versions are pinned and recorded.
- No required configuration exists only as an interactive or undocumented host change.
- Generated runtime state and plaintext secrets are absent from Git.
- Validation produces an environment-specific result that can be compared across runs.
- Off-host backups are fresh, integrity-checked, and proven by a clean-host restore.
- Failed changes have an explicit rollback or rebuild path.

Byte-for-byte equality is not required for generated identities, timestamps, certificates,
or runtime databases. Repeatability means equivalent declared configuration, security
boundaries, interfaces, behavior, and recovery capability.

## Recommended Implementation Strategy

Build a project-specific integration layer from maintained upstream components rather
than creating a new k3s installer or copying an entire homelab distribution.

### Reuse directly

- Use the official [`k3s-io/k3s-ansible`](https://github.com/k3s-io/k3s-ansible)
  collection for pinned k3s installation, configuration, upgrade, reset, and kubeconfig
  retrieval. Pin a reviewed collection release or commit in the Ansible dependency file.
- Use supported upstream Helm charts for `cert-manager`, Prometheus and Alertmanager,
  Grafana, Loki, and Grafana Alloy. Pin chart versions and resulting container images;
  keep environment values and release definitions in `cluster/addons/`.
- Use Kustomize for repository-owned namespaces, RBAC, quotas, policies, storage
  configuration, and environment overlays under `cluster/core/`.
- Use established MariaDB, Redis, and off-host backup utilities rather than custom data
  formats. Their invocation, retention, encryption, integrity checks, and restore
  qualification remain owned by this repository.

The `k3s-ansible` use of an "external database" refers to an optional k3s control-plane
datastore. It is unrelated to the application MariaDB and Redis services that this plan
runs on the host outside Kubernetes.

### Retain project ownership

This repository must provide the parts that generic installers and charts cannot know:

- the thin bootstrap and stable operator interface;
- supported-host preflight and security baseline, including firewall policy;
- same-host MariaDB and Redis placement and isolation;
- encrypted secret delivery and environment configuration;
- dependency ordering across host convergence, cluster core, and add-ons;
- platform-wide validation and evidence collection;
- off-host backup integration and clean-host recovery rehearsal;
- the application-ready gate and the contract presented to application deployments.

Do not inherit an upstream recommendation that conflicts with this blueprint merely to
reduce local configuration. For example, host firewall ownership remains local even if a
cluster installer recommends disabling it.

### Use as references only

Larger projects such as
[`ricsanfre/pi-cluster`](https://github.com/ricsanfre/pi-cluster) and
[`onedr0p/cluster-template`](https://github.com/onedr0p/cluster-template) demonstrate
useful Ansible, GitOps, certificate, observability, backup, and repository patterns. They
also make different assumptions about hardware, Talos, immediate GitOps, networking,
distributed storage, and the number of platform services. Study individual patterns but
do not fork either project as the platform base.

`k3sup`, HA-focused k3s playbooks, and Kubespray solve adjacent problems but are not the
preferred foundation here. `k3sup` is primarily a fast imperative bootstrap tool;
HA-focused playbooks introduce topology not needed by the initial single server; and
Kubespray targets a fuller upstream Kubernetes deployment rather than this k3s model.

### Initial composition

```text
bootstrap.sh
  -> project-owned host baseline and data-service roles
  -> pinned k3s-io/k3s-ansible collection
  -> project-owned cluster/core Kustomize resources
  -> pinned upstream Helm charts under cluster/addons
  -> project-owned validation and recovery workflows
  -> application-ready handoff
```

Review upstream releases before each version change and test the exact pinned composition
as one platform. Reusing maintained components reduces installation code; it does not
delegate responsibility for their combined behavior or recovery.

## Tool Ownership Rule

Use each tool within one clear boundary:

- Ansible converges the host and installs k3s.
- Kustomize manages repository-owned Kubernetes resources and environment overlays.
- Helm installs pinned third-party add-ons.
- Shell provides thin operator entry points and focused validation glue.

Two tools must not manage the same resource. In particular, Ansible may invoke the
cluster deployment workflow, but it must not duplicate Kubernetes resource definitions
that are owned by Kustomize or Helm.

## Deferred Evolution

GitOps can replace direct cluster reconciliation after this process is proven. At that
point, host automation continues to own the VM and k3s bootstrap, while the GitOps
controller assumes ownership of agreed `cluster/` resources. Ownership transfers must be
explicit so Ansible and GitOps never reconcile the same object.

Moving MariaDB and Redis to separate infrastructure is also deferred. That migration
must preserve their application-facing connection contract and establish its own backup,
restore, cutover, and rollback plan.