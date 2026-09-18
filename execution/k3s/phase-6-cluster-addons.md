# Phase 6 Implementation Plan: Cluster Add-ons

Status: ready for implementation after Phase 5 passes.

## Mission

Install the minimum production-readiness add-ons required before applications: automated
certificates, metrics and alerting, centralized logs and dashboards, and Kubernetes-side
backup integration. Deploy each capability as an independently versioned, reversible,
resource-bounded release while preserving the cluster-core ownership boundary.

## Context and Preconditions

Read the blueprint, deployment strategy, and Phase 1-5 plans. Require current passing
Phase 5 evidence, restricted add-on automation credentials, resolved resource/storage
budgets, DNS/challenge decisions, alert destination, retention values, and off-host backup
destination.

The initial stack is:

- cert-manager;
- Prometheus, Alertmanager, Grafana, and required Kubernetes/node exporters;
- Grafana Alloy and Loki;
- a Kubernetes backup mechanism selected during implementation for manifests and required
  local-path persistent data, using the existing off-host object/repository service;
- no Tempo, tracing, service mesh, distributed storage, GitOps, or application-specific
  instrumentation.

## Goals

1. Pin every chart, CRD, image, and configuration input.
2. Install add-ons in dependency order without coupling their releases.
3. Keep operational endpoints private and credentials encrypted.
4. Bound CPU, memory, storage, log volume, and retention.
5. Produce platform health signals and one tested external alert route.
6. Back up required Kubernetes state and integrate backup freshness with monitoring.
7. Prove each add-on can be re-applied and rolled back independently.

## Required Configuration

The shared schema must define:

- Helm repository URL, chart name/version, expected chart digest or vendored package
  checksum, and allowed image digests for every release;
- namespace, release name, resource requests/limits, PVC sizes, storage classes, and
  retention for each add-on;
- ACME directory, challenge type, staging/production issuer names, contact reference,
  DNS solver details when applicable, and disposable certificate hostname;
- private access method and hostnames for Grafana/Prometheus/Alertmanager/Loki;
- Prometheus scrape interval/evaluation interval and metrics retention;
- Loki retention and ingestion/storage limits;
- Alloy collection selectors and explicit redaction/drop rules;
- alert destination type and encrypted credential reference;
- Kubernetes backup scope, schedule, retention, destination, encryption, and excluded
  transient resources;
- capacity reserved for future applications after all add-ons are running.

No mutable chart versions, image tags, generated administrator passwords, or plaintext
credentials may be committed.

## Intended File Ownership

```text
execution/k3s/cluster/addons/
  releases.yaml                    # release inventory and exact versions
  certificates/
    values/
    resources/
    scripts/
  observability/
    metrics/
    logs/
    dashboards/
    alerts/
  backups/
    values/
    resources/
    scripts/
  scripts/
    render.sh
    validate.sh
    apply.sh
    smoke.sh
    rollback.sh
```

Use upstream Helm charts for maintained third-party resources. Use Kustomize/plain YAML
for project-owned issuers, policies, dashboards, rules, monitors, and backup schedules.
Do not copy rendered upstream chart output into source control.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh check --environment test --through cluster-addons
./execution/k3s/bootstrap.sh apply --environment test --through cluster-addons
```

Also provide scoped operations conceptually equivalent to:

```text
addons check <certificates|metrics|logs|backups>
addons apply <name>
addons validate <name>
addons rollback <name> --revision <known-good>
```

An add-on apply may touch only its owned release/resources. The full phase command invokes
them in dependency order and runs integrated checks.

## Supply-Chain and Release Rules

- Pin chart versions and verify downloaded chart provenance/digest or vendor the exact
  chart archive with checksum metadata.
- Pin images by digest through supported chart values. If a chart cannot support immutable
  image references, record and resolve that limitation before production readiness.
- Render every release offline with the exact values and scan rendered resources for
  privileged containers, host mounts, host networking, broad RBAC, missing limits, and
  mutable images.
- Scan images and record accepted findings with expiry/review dates.
- Install CRDs explicitly or through one documented chart policy; back up CRDs and custom
  resources before upgrades. Never let unrelated releases own the same CRD.
- Record previous known-good chart version, values hash, and image digests for rollback.

## Add-on Release 1: Certificates

- Install cert-manager CRDs and controller components in a dedicated namespace.
- Apply least-privilege RBAC, resource limits, pod-security-compatible settings, and
  network policies for API, DNS, and ACME access.
- Configure separate staging and production issuers; the first validation uses staging.
- Keep account credentials and DNS provider tokens SOPS-encrypted and absent from logs.
- Issue a certificate for a disposable hostname routed through Traefik and validate the
  chain, SAN, key type, readiness, and HTTPS response.
- Test automatic renewal with a safe forced/staging procedure where supported. If issuer
  timing makes this impractical, record the bounded exception required by the blueprint,
  prove renewal configuration and expiry alerting, and schedule the follow-up before
  relying on a production certificate.
- Back up issuer configuration/account references and identify whether certificates are
  restored or safely reissued after cluster rebuild.

## Add-on Release 2: Metrics and Alerting

- Install Prometheus Operator/Prometheus, Alertmanager, Grafana, kube-state-metrics, and
  node exporter from reviewed pinned charts; avoid duplicate collection already supplied
  by k3s.
- Use one single replica for each stateful component and explicit local-path PVCs.
- Apply 15-30 second scrape intervals initially and bounded retention/storage.
- Monitor node readiness, CPU/memory pressure, filesystem capacity, certificate expiry,
  pod crash loops, persistent volume usage, ingress availability, monitoring target
  absence, host MariaDB/Redis health, and backup freshness.
- Expose host data-service and backup status through bounded exporters/textfile metrics
  without database credentials or application identifiers.
- Keep UIs private through the accepted administrative access path; do not make them
  public merely to obtain certificates.
- Configure one external Alertmanager route and send a controlled test alert through the
  complete route. Inhibition/routing must prevent obvious duplicate storms.

## Add-on Release 3: Logs and Dashboards

- Install Grafana Alloy as a DaemonSet and Loki as a single-replica stateful service.
- Collect Kubernetes events and stdout/stderr for k3s system and platform namespaces.
- Collect required host service logs only through an explicitly approved host source;
  avoid broad host filesystem mounts.
- Apply short explicit retention, ingestion limits, query limits, and storage quotas.
- Drop authorization headers, cookies, tokens, query parameters known to carry secrets,
  request bodies, and high-cardinality personal identifiers before storage.
- Do not collect MariaDB general/slow query content or Redis command payloads by default.
- Provision Grafana data sources and baseline dashboards declaratively. Dashboards cover
  node capacity, k3s components, ingress, certificates, add-on health, logs, external data
  services, and backup status.
- Generate harmless events and verify they are queryable without sensitive values.

## Add-on Release 4: Kubernetes Backups

- Select and record the backup tool only after confirming support for k3s, local-path
  volumes, the chosen off-host destination, encryption, and restore into a clean cluster.
- Back up repository-owned Kubernetes objects, CRDs/custom resources required by add-ons,
  and explicitly selected persistent volumes. Exclude ephemeral objects, Secrets whose
  authoritative encrypted source is Git unless recovery requires them, and application
  namespaces not yet deployed.
- Treat k3s SQLite/token/config backup as host-level backup; do not assume a Kubernetes
  backup controller can replace it.
- Treat MariaDB/Redis backup as Phase 3 host operations; do not copy live database files
  into Kubernetes backup jobs.
- Run scheduled backups, verify destination objects/checksums, apply retention after
  success, and publish freshness/failure metrics.
- Perform a namespace-scoped restore into an isolated validation namespace in this phase.
  Full clean-host recovery belongs to Phase 8.

## Security and Capacity Requirements

- Use separate service accounts and least-privilege RBAC per add-on.
- Do not grant cluster-admin to Helm releases or automation unless a reviewed CRD
  installation step strictly requires temporary bootstrap access.
- Apply network policies matching only required API, DNS, scrape, notification, ACME,
  and backup flows.
- Run non-root/read-only filesystem/restricted seccomp settings where chart support
  permits; document bounded exceptions.
- Set requests, limits, PVC sizes, retention, and quotas for every component.
- After stabilization, measure actual use and prove configured application headroom
  remains. If not, reduce retention or increase capacity before Phase 7.
- Back up Grafana dashboards/configuration and alert rules as desired state; do not depend
  on manual UI changes.

## Idempotence and Failure Behavior

- Two renders from identical inputs are byte-stable except documented chart metadata.
- A second apply causes no rollout or resource mutation without an input change.
- A failed add-on apply stops that release and later releases but does not roll back or
  alter previously healthy independent releases automatically.
- Rollback targets an explicit known-good revision and runs that add-on's validation.
- Stateful rollback must consider storage/schema compatibility; never downgrade blindly.
- Ordinary apply never deletes PVCs, CRDs, certificate account keys, backup snapshots, or
  monitoring history.

## Implementation Sequence

1. Finalize release inventory, capacity budget, secrets, and private access.
2. Implement common chart acquisition, verification, render, lint, diff, apply, and
   evidence tooling.
3. Deliver and validate certificates.
4. Deliver and validate metrics, dashboards, and the external alert route.
5. Deliver and validate Alloy/Loki logs and redaction rules.
6. Select, deliver, and validate Kubernetes backup integration.
7. Run integrated resource/headroom, privacy, network-policy, restart, second-apply, and
   rollback tests.

## Acceptance Tests

Prove:

1. Every chart/image/CRD is pinned and rendered manifests pass policy checks.
2. A disposable staging certificate is issued and HTTPS works; renewal passes or has the
   approved bounded exception and tested expiry alert.
3. Prometheus targets are healthy, baseline alerts/rules load, dashboards load, and a
   controlled alert reaches the operator.
4. Harmless platform logs reach Loki and deliberate secret-shaped test values are dropped
   or redacted.
5. Backup completes off-host, freshness is monitored, and isolated namespace restore
   succeeds.
6. UIs are inaccessible publicly and available only through the approved admin path.
7. Network policies allow required flows and deny an unapproved probe.
8. Resource/PVC usage remains within budgets with documented application headroom.
9. Rebooting the host restores all add-ons to health without manual changes.
10. Second apply is stable and one chosen add-on rollback rehearsal succeeds.

Run Helm lint/template, Kustomize render, Kubernetes schema/policy lint, server-side
dry-run/diff, image scanning, and live smoke tests.

## Evidence and Completion Gate

Write one aggregate Phase 6 report plus one report per add-on under
`execution/k3s/.evidence/<environment>/`. Record prior evidence IDs, release/chart/image
versions, rendered hashes, RBAC/policy findings, health, resource/storage use, certificate,
alert, log-redaction, backup/restore, reboot, idempotence, and rollback outcomes. Do not
record credentials, notification secrets, private keys, or sensitive log content.

Phase 6 completes only when all four releases pass independently and together, capacity
headroom remains, backup and alert failures are visible, private access is enforced, and
no application workload was required to prove the platform.

## Non-Goals

- Tempo/tracing, service mesh, public operational UIs, distributed storage, HA add-ons,
  GitOps, or application-specific dashboards and backups.
- Replacing host/k3s backup or Phase 3 MariaDB/Redis backup procedures.