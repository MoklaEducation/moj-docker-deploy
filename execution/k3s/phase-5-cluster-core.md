# Phase 5 Implementation Plan: Cluster Core

Status: ready for implementation after Phase 4 passes.

## Mission

Establish the minimum repository-owned Kubernetes configuration needed to onboard shared
add-ons and later application namespaces safely. Create stable namespace, RBAC, resource,
network, storage, and secret-delivery contracts using Kustomize. Replace routine use of
the Phase 4 bootstrap administrator kubeconfig with restricted operator and automation
identities.

This phase defines cluster guardrails. It does not install certificate, observability,
backup, GitOps, or application workloads.

## Context and Preconditions

Read the blueprint, deployment strategy, and Phase 1-4 plans. Require current passing
Phase 4 evidence for the same environment and cluster identity.

Before apply:

- k3s and bundled components are healthy after reboot;
- bootstrap administrator kubeconfig is available only to the authorized operator;
- the environment names future platform and application namespaces;
- resource budgets and administrative subjects are resolved;
- the SOPS/age secret-delivery decision is accepted;
- no unmanaged objects conflict with intended names.

## Goals

1. Create stable platform and future application namespace contracts.
2. Apply least-privilege RBAC for human operations and deployment automation.
3. Apply quotas, limit defaults, pod-security labels, and default network isolation.
4. Preserve bundled local-path storage while constraining its use.
5. Establish encrypted secret-rendering conventions without committing plaintext.
6. Provide render, policy, server-side validation, apply, prune, and smoke-test workflows.
7. Keep all resources compatible with a later explicit transfer to Flux or Argo CD.

## Required Configuration

The Phase 1-owned schema must include:

- namespace names for `platform-system`, `observability`, `backup-system`, `dmoj-test`,
  and `dmoj-prod` or accepted equivalents;
- environment-specific namespace quotas and default CPU/memory requests and limits;
- pod-security level and documented exemptions;
- administrative user/group identities from the authentication mechanism available to
  k3s;
- deployment automation identity names and namespace scope;
- DNS, API, ingress-controller, certificate, observability, backup, and external
  MariaDB/Redis network flows required by later phases;
- local-path storage class policy and which namespaces may claim it;
- SOPS age recipients and decryption location on the controller.

Do not embed private keys, tokens, passwords, kubeconfigs, or decrypted Secret manifests
in the environment files.

## Intended File Ownership

```text
execution/k3s/cluster/core/
  base/
    kustomization.yaml
    namespaces/
    access/
    policies/
    quotas/
    storage/
  overlays/
    test/
      kustomization.yaml
    production/
      kustomization.yaml
  scripts/
    render.sh
    validate.sh
    apply.sh
    smoke.sh
```

Keep Kustomize resources in the relevant responsibility directory. Do not generate them
from Ansible templates. Ansible may invoke the scripts after Phase 4, but Kustomize owns
the Kubernetes objects.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh check --environment test --through cluster-core
./execution/k3s/bootstrap.sh apply --environment test --through cluster-core
```

Check mode renders the selected overlay, validates schemas and policies, performs
server-side dry-run when a cluster is available, and shows a diff without applying.
Apply requires current earlier-phase evidence, applies only declared core resources, and
runs smoke tests.

## Required Resources and Policies

### Namespaces and labels

- Create only agreed platform and placeholder application namespaces.
- Label namespaces with environment, ownership, managed-by, and pod-security admission
  labels.
- Use `restricted` pod-security defaults where supported. Any exemption must identify the
  resource, reason, owner, and expiry/review condition.
- Do not deploy an application merely to populate its namespace.

### RBAC and identities

- Retain the bootstrap administrator kubeconfig only for break-glass cluster bootstrap
  and recovery.
- Create a routine human operator identity with only documented platform operations.
- Create separate automation identities for `cluster-core` and, later, add-on and
  application reconciliation. Do not share credentials across responsibilities.
- Scope application deployment identities to their target namespaces; they must not
  administer nodes, CRDs, or shared platform namespaces.
- Generate short-lived credentials where the selected mechanism supports them. If
  long-lived service-account tokens are unavoidable initially, encrypt them, document
  rotation, and set a review date.
- Produce separate ignored kubeconfigs rather than merging into global user state.
- Verify denied actions as well as allowed actions with `kubectl auth can-i`.

### Resource governance

- Apply `ResourceQuota` and `LimitRange` per non-system namespace from measured budgets.
- Defaults must prevent unbounded workloads without making known Phase 6 charts
  unschedulable.
- Reserve host and k3s capacity outside namespace quotas.
- Do not modify `kube-system` resource policies unless a specific tested requirement
  exists.

### Network policies

- Establish default-deny ingress and egress in managed non-system namespaces.
- Add explicit egress for DNS.
- Add only the baseline flows needed for Phase 6 control-plane/API interaction,
  certificate challenges, monitoring scrapes, log delivery, backup destinations, and
  host data services.
- Do not pre-authorize arbitrary internet egress or cross-namespace communication.
- Policy selectors must rely on labels managed by this repository.
- Exercise allowed and denied traffic with disposable pods. Manifest rendering alone is
  not proof that the k3s policy controller enforces policy.

### Storage

- Keep the bundled local-path class and document its single-host failure behavior.
- Decide explicitly whether it remains default; prefer requiring explicit class names for
  persistent platform state.
- Constrain PVC use through quotas and namespace policy.
- Add no distributed storage, hostPath application volumes, snapshots, or database
  storage classes.
- Verify provisioning, persistence across pod recreation, reclaim behavior, and cleanup
  in a disposable core-validation namespace.

### Secret-delivery foundation

- Store only SOPS-encrypted secret source files in Git.
- Decrypt on the trusted operator/controller at apply time; never write plaintext into a
  repository path or evidence directory.
- Pipe decrypted manifests directly to validation/apply where practical and ensure
  process arguments and logs remain redacted.
- Commit an encrypted-secret template and schema, not usable production secrets.
- Do not install Flux, Argo CD, External Secrets, Vault, or another controller yet.
- Define how later GitOps ownership can replace controller-side decryption without
  changing consumer Secret names.

## Validation and Pruning

- Render output deterministically; two renders from identical inputs must match.
- Validate YAML, Kubernetes schemas, duplicate resource IDs, namespace references,
  immutable fields, and policy conventions before server interaction.
- Use server-side dry-run and a diff before apply.
- Label all managed objects and restrict pruning to an explicit allowlist and ownership
  selector. Never prune cluster/system or application resources by broad namespace.
- Apply CRDs only in the phase that owns the corresponding add-on.
- Remove disposable smoke resources even after a failed test, without deleting retained
  evidence.

## GitOps Compatibility Contract

- Resource files remain plain Kustomize-compatible desired state.
- Do not make reconciliation depend on local mutable files or Ansible facts.
- Keep environment overlays declarative and secret references stable.
- Record the complete inventory of objects owned by direct apply.
- A later GitOps adoption explicitly pauses direct apply, imports the same objects, proves
  no destructive diff, and transfers ownership. Concurrent ownership is prohibited.

## Implementation Sequence

1. Add schema values and define namespace/resource budgets.
2. Build deterministic base and environment overlays.
3. Add namespace labels, quotas, limits, and storage policy.
4. Add RBAC and generate restricted ignored kubeconfigs.
5. Add default-deny and explicit baseline network policies.
6. Add SOPS rendering/validation pipeline with redaction tests.
7. Add server dry-run, diff, scoped apply/prune, and smoke workflows.
8. Run first apply, authorization tests, network/storage smoke tests, second apply, and
   final check mode.

## Acceptance Tests

Prove:

1. Offline render is deterministic and schema-valid.
2. Server-side dry-run and diff pass before apply.
3. Expected namespaces, labels, quotas, limits, and policies exist.
4. Restricted identities can perform intended operations and cannot read unrelated
   secrets, modify nodes/CRDs, or access other application namespaces.
5. Default-deny blocks unapproved ingress/egress; DNS and specifically allowed paths work.
6. A local-path PVC behaves as documented and leaves no smoke resources afterward.
7. No decrypted secret persists in Git, temporary repository files, logs, or evidence.
8. The second apply and subsequent check show no unexplained drift.
9. Bootstrap administrator credentials are no longer used by routine check/apply paths.

Run Kustomize render, YAML/schema/policy lint, server-side dry-run, authorization tests,
and disposable workload smoke tests.

## Evidence and Completion Gate

Write `execution/k3s/.evidence/<environment>/phase-5-cluster-core.json` containing prior
evidence IDs, rendered content hash, managed object inventory, namespace/resource-policy
summary, RBAC allow/deny results, network/storage tests, first/second apply results, and
overall status. Redact subjects if their disclosure is sensitive; never include tokens or
kubeconfig client keys.

Phase 5 completes only when all core objects are deterministic, restricted credentials
replace routine bootstrap-admin use, enforcement tests pass, no secrets leak, and Phase 6
can install add-ons through documented identities and policies.

## Non-Goals

- cert-manager, observability, alerting, backup controllers, GitOps, or applications.
- Replacing bundled ingress, CNI, DNS, ServiceLB, or local-path storage.
- Application-specific RBAC, secrets, databases, or network policies.