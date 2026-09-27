# Phase 5 Cluster Core Progress

Status: test environment complete; ready for Phase 6 implementation

Last updated: 2026-09-27

This document records verified Phase 5 implementation progress and accepted planning
decisions. The normative requirements remain in
[phase-5-cluster-core.md](../phase-5-cluster-core.md), while platform-wide decisions
remain authoritative in [Platform Decisions](../../../../docs/architecture/decisions.md).

## Verified Prerequisite State

- Phase 4 is complete for the disposable single-node test cluster and its latest public
  check evidence passes.
- The cluster has 6 allocatable CPUs, approximately 16 GiB allocatable memory, and ample
  storage for the initial core-policy work.
- The bundled `local-path` storage class is currently the default, uses `Delete` reclaim
  policy, and uses `WaitForFirstConsumer` binding.
- Current Phase 4 evidence passes for the same cluster identity and configuration hash.

## Accepted Namespace Vocabulary

The Kubernetes application namespace vocabulary transitions from implementation-specific
`dmoj-*` names to environment instances under the `judge-platform` umbrella:

| Environment | Namespace | Phase 5 treatment |
| --- | --- | --- |
| Test | `judge-test` | Created by the test overlay and treated as disposable |
| Production | `judge-prod` | Defined by the contract and created only by the production overlay |
| Staging | `judge-staging` | Reserved convention only; not created until staging is approved |

Application resources use `app.kubernetes.io/part-of: judge-platform`. DMOJ remains the
initial implementation and may retain DMOJ-specific component, image, and source names.
The umbrella name avoids coupling the stable Kubernetes environment boundary to one
judge implementation.

This transition is limited to Kubernetes namespaces and their platform contract. It does
not rename the existing `dmoj-test` Compose project, Keycloak realm, database names,
repositories, or historical documentation. Changing those identifiers would require a
separate compatibility and migration decision.

## Implemented Overlay Behavior

- The test overlay creates `platform-system`, `observability`, `backup-system`, and
  `judge-test`.
- The test overlay does not create `judge-prod` or `judge-staging`.
- A future production overlay creates `judge-prod`; a staging overlay is added only when
  staging has concrete configuration and ownership.
- Shared platform namespaces remain outside the `judge-platform` application umbrella
  and retain independent ownership.
- Namespace selectors and policies must use repository-managed labels rather than infer
  ownership from namespace-name prefixes.

## Implemented Contract

- Kustomize owns Phase 5 Kubernetes objects; Ansible may invoke the workflow but does not
  template or duplicate those objects.
- Phase 5 owns default-deny policies and explicit DNS access. Add-on-specific flows are
  added with their Phase 6 releases rather than pre-authorized speculatively.
- The bundled local-path class remains available for the test profile with explicit PVC
  quotas and documented single-host and `Delete` reclaim behavior.
- Routine human and cluster-core automation credentials are separate from the Phase 4
  bootstrap administrator credential. Generated kubeconfigs remain ignored and mode
  `0600`.
- Apply and prune operate only on an explicit managed-object inventory and allowlisted
  namespaced kinds carrying the Phase 5 ownership label.
- The public bootstrap interface supports `check` and `apply` through `cluster-core`
  after the existing Phase 1-4 gates.
- The Phase 1-owned schema now validates namespace, Pod Security, identity, quota,
  default-limit, network, storage, secret-delivery, and pinned smoke-image inputs.
- The test Kustomize overlay renders 36 uniquely identified objects. It creates four
  namespaces, four quotas, four limit ranges, nine network policies, four cluster roles,
  two cluster role bindings, and nine role bindings.
- All managed namespaces enforce, audit, and warn at the restricted Pod Security level.
  Each has default-deny ingress/egress and explicit DNS access. `judge-test` additionally
  permits labeled clients to reach only the declared host MariaDB and Redis ports.
- `mokla-platform-operator` and `mokla-cluster-core` use separate 30-day client
  certificates and ignored mode-`0600` kubeconfigs. Routine Phase 5 check/apply succeeds
  with the bootstrap administrator kubeconfig unavailable.
- RBAC and certificate issuance remain an explicit break-glass operation through
  `cluster/core/scripts/access.sh`; routine automation detects RBAC drift and cannot
  escalate its own permissions.
- Phase 4 prerequisite checks may validate the bootstrap administrator credential that
  Phase 4 owns. Phase 5 reconciliation itself has been proven to pass with that file
  unavailable and uses only the restricted cluster-core credential.
- Phase 6 owns creation of its add-on automation identity and exact add-on NetworkPolicies
  after concrete charts, CRDs, endpoints, and ports are selected. Phase 5 intentionally
  avoids dormant credentials and speculative egress.
- The SOPS foundation includes a valid encrypted, deliberately unusable Secret template,
  a source schema, recipient matching, controller-side decryption validation, and no
  applied Secret or secret controller.

## Acceptance Evidence

- Two offline renders from identical inputs match. The accepted 36-object render SHA-256
  is `98aa6ac4e95d5e2c96e5652e4ca36aed5bc8ee239f74e68a04a0271de5561200`.
- Server-side dry-run and diff pass. The unchanged repeat apply and final check both
  report `drift_before: false` and use `credential_mode: restricted`.
- Human and automation allow tests pass. Both identities are denied Secret reads and
  node mutation; automation is additionally denied CRD creation and pod creation in
  `observability` while retaining its intended policy and smoke permissions in
  `judge-test`.
- Live network enforcement proves DNS and labeled host data-service access work, while
  arbitrary Internet egress and unapproved pod ingress are denied.
- A disposable local-path claim provisions, preserves a marker across pod recreation,
  uses the documented `Delete` reclaim behavior, and leaves no pod, Service, PVC, or PV
  smoke resource afterward.
- Live pruning safety passes: an allowlisted stale NetworkPolicy carrying the Phase 5
  ownership label is deleted; an equivalent unowned NetworkPolicy is refused and remains
  present until explicit smoke cleanup; both reserved test objects are absent afterward.
- The local-path class remains the default with `WaitForFirstConsumer` binding. Namespace
  quotas constrain claim count and storage requests.
- The complete validation suite passes 95 tests. Python compilation, shell syntax,
  documentation diagnostics, and `git diff --check` pass.
- Durable redacted evidence is written to
  `execution/k3s/.evidence/test/phase-5-cluster-core.json` and records the object
  inventory, render hash, authorization results, network/storage smoke results, storage
  behavior, and apply/check history.

## First-Run Findings

The first implementation apply exposed two local defects and stopped without leaving
smoke resources:

1. Kubernetes returned the approved client certificate as PEM, while the initial
   validator requested DER parsing. Validation now explicitly checks PEM and has a
   generated-certificate regression test.
2. `kubectl auth can-i` returns exit status 1 for an expected `no`. The authorization
   helper now accepts only the exact `yes`/0 and `no`/1 pairs and still rejects transport
   or API errors.

After those repairs, the unchanged public apply and final public check passed. Earlier
failed attempts remain in bounded lifecycle evidence rather than being hidden.

## Remaining Deferred Work

- Add production configuration and the `judge-prod` overlay only when production
  budgets, subjects, recipients, and endpoints are approved.
- Add `judge-staging` only if a staging environment is adopted.
- Phase 6 owns add-on-specific identities and concrete certificate, observability, and
  backup network permissions; Phase 5 does not pre-authorize them.
- Certificate renewal is required before the configured 30-day validity window expires.

## Completion State

Phase 5 is complete for the disposable test environment. All declared core objects are
deterministic, restricted routine credentials replace bootstrap-admin use in the Phase 5
workflow, enforcement and cleanup tests pass, no plaintext secret is persisted, and the
cluster is ready for Phase 6 add-on implementation.