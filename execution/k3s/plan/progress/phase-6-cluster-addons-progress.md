# Phase 6 Cluster Add-ons Progress

Status: certificate capability complete; metrics and logs not started

Last updated: 2026-09-27

This document records accepted planning decisions for the first Phase 6 implementation
iteration. The normative requirements and profile-specific gates remain in
[phase-6-cluster-addons.md](../phase-6-cluster-addons.md).

## Accepted Test-Profile Scope

The first iteration is intended to make the private single-node test cluster usable and
observable without claiming production security or recovery qualification. It will
deliver:

- cert-manager using a private test issuer and disposable private hostname;
- Prometheus, Alertmanager, Grafana, and required Kubernetes/node metrics;
- Grafana Alloy and Loki for bounded platform log collection;
- declarative alerts, data sources, dashboards, resource controls, and private access;
- end-to-end alert delivery through the Phase 3 disposable webhook receiver.

Kubernetes backup tooling, off-host upload, freshness monitoring, and restore acceptance
are deferred. Their absence does not block the initial test-profile Phase 6 gate, but it
must remain visible as `deferred` and `not_qualified`, and it blocks the corresponding
Phase 7 and Phase 8 recovery claims.

## Accepted Security Exceptions

- Phase 5 `restricted` Pod Security remains the default. Node-level collectors may use a
  dedicated Phase 6-owned namespace with only the host mounts, namespaces, capabilities,
  and Pod Security labels required by the selected reviewed charts.
- A fixed set of test operator and automation identities is acceptable. Break-glass
  access may create and repair add-on identities and cluster-scoped RBAC. Fine-grained
  role separation, self-service restrictions beyond the basic no-escalation boundary,
  and short-lived credential rotation are deferred hardening work.
- SOPS secrets may be decrypted on the trusted controller and applied directly through
  the Phase 6 workflow. A cluster secret controller is deferred unless implementation
  proves it is required. Plaintext persistence and secret-bearing evidence remain
  prohibited.
- The existing private HTTP MinIO endpoint and frozen legacy test image may be used only
  for exploratory backup mechanics. They are not an accepted production or off-host
  backup destination.

Every exception must be represented in configuration or owned manifests, validated by
allow/deny tests where practical, and recorded in evidence with a reason and follow-up
condition. Exceptions must not silently weaken `judge-test` or unrelated namespaces.

## Certificate Decision

Public ingress, public DNS automation, and ACME are outside this iteration. Cert-manager
will use a private test issuer and a disposable hostname resolved through the approved
private/manual path. Acceptance covers controller health, issuance, chain and SAN,
private Traefik HTTPS, short-lived renewal behavior, and expiry alerting. A production
issuer, public DNS solver, and external routing remain later environment inputs.

## Release And Capability Decision

Track certificates, metrics/alerting, and logs/dashboards as capabilities. Each
capability may contain multiple independently pinned Helm releases plus repository-owned
resources. Rollback and evidence operate at the actual release/resource-set boundary;
the plan does not assume exactly one Helm release per capability.

## Implementation Entry Conditions

Before the first add-on apply, select exact charts and images, render them against the
current quotas, identify node-agent Pod Security requirements, define private UI access,
and confirm the Phase 3 webhook endpoint. The implementation should then proceed in this
order: common release tooling, certificates, metrics and alerting, logs and dashboards,
and integrated test-profile validation.

## Implemented Foundation

- The public bootstrap accepts `check|apply --through cluster-addons` and gates Phase 6
  behind current passing Phase 5 evidence.
- Controller setup installs and validates Helm `v3.18.6` from its checksum-pinned upstream
  archive.
- `cluster/addons/releases.yaml` records cert-manager chart `v1.18.2`, chart SHA-256, and
  immutable digests for controller, webhook, cainjector, startup API check, and ACME
  solver images.
- Shared scripts acquire the chart into temporary storage, verify its checksum, render
  twice, enforce offline image/resource/security policy, detect live drift, apply only
  changed portions, and write redacted evidence.
- The test environment schema now controls capability switches, fixed identity,
  namespaces, private access mode, issuer, hostname, certificate lifetime, renewal
  window, and ingress class.

## Implemented Certificate Capability

- A `cert-manager` namespace enforces restricted Pod Security, default-deny networking,
  explicit DNS/API/internal/Traefik flows, a ResourceQuota, and a LimitRange.
- Cert-manager runs as three single-replica bounded deployments. The rendered release and
  smoke workload contain five workload images, all pinned by digest.
- A namespaced self-signed bootstrap issuer creates a private CA. The CA issuer creates a
  seven-day ECDSA leaf certificate for `phase6.test.mokla.local` with a 24-hour renewal
  window.
- A restricted BusyBox HTTP deployment, Service, and Traefik Ingress provide the
  disposable HTTPS target. Validation checks certificate readiness, chain, SAN, minimum
  remaining lifetime, and the HTTPS response using the generated CA and `curl --resolve`.
- The add-on client certificate is stored only in the ignored `.generated` directory with
  mode `0600`. For this test iteration its group has an explicitly labeled temporary
  `cluster-admin` binding. Splitting bootstrap CRD/RBAC work from routine reconciliation
  remains required before production qualification.

## Verified State

- Deterministic rendering passes with 66 objects and SHA-256
  `6ddaebb9f88691fcaa35e762151ba301c443703419c90cd85b25b0ccae699884`.
- Cert-manager controller, cainjector, webhook, and the certificate smoke deployment are
  Available. Both the private CA and leaf Certificate report Ready.
- Private HTTPS, certificate chain, SAN, and expiry checks pass.
- A repeat apply reports `drift_before: false`; the Helm revision count remained 2 before
  and after, proving the unchanged operation did not create a release revision.
- The cumulative public check through Phase 6 passes and writes redacted evidence to
  `execution/k3s/.evidence/test/phase-6-cluster-addons.json`.

## Remaining Work

- Implement metrics and alerting, including the Phase 3 webhook route.
- Implement Alloy/Loki and the dedicated node-agent Pod Security exception.
- Exercise short-lifetime certificate renewal and add expiry alerting after metrics is
  available.
- Replace the temporary add-on `cluster-admin` binding with split least-privilege roles.
- Implement Kubernetes backup and off-host recovery qualification in the deferred
  iteration.