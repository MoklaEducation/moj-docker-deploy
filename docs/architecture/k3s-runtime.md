# k3s Runtime Initiative

See [Platform Decisions](decisions.md) for the repository layout, layer contract, and initial k3s boundary. See [Image Build and Release](image-build.md) for image publication requirements.

## Goal

Deliver DMOJ and Keycloak as Layer 3 Kubernetes workloads on k3s, consuming immutable Layer 2 images. The initiative is independent from source import and image-pipeline changes.

## Initial Runtime Scope

- One k3s server node using default SQLite datastore and local-path storage.
- Built-in Traefik ingress for public DMOJ and Keycloak HTTPS endpoints.
- DMOJ site, celery, bridged, wsevent, texoid, pdfoid, and mathoid as workloads.
- DMOJ MariaDB, Keycloak MariaDB, and Redis remain outside the cluster initially.
- `bridged` retains a stable externally reachable port for remote judges.
- Observability, backup, TLS automation, and Headscale are separate Layer 4 add-ons.

## Single-Machine Implementation Now

Implement and validate these items on one k3s server before planning additional machines:

1. Install a single k3s server with its default SQLite datastore, bundled Traefik, and local-path provisioner.
2. Create the `dmoj-test` namespace and deploy only test manifests using immutable image digests.
3. Connect pods to the external DMOJ MariaDB, Keycloak MariaDB, and Redis through explicit Services/Endpoints; do not move stateful data into k3s yet.
4. Add public DMOJ ingress, Keycloak ingress when enabled, and the stable bridged service port.
5. Test backup and restore for every external stateful service before a production cutover.
6. Document the exact k3s version, image digests, external service addresses, and ingress/TLS configuration needed to rebuild the node.

This baseline favors simplicity over node resilience. A failed server causes application downtime, but the external databases and image artifacts make recovery onto replacement hardware straightforward.

## Three-Machine Strategy (Deferred)

Do not add another server node to the SQLite-based cluster. Agent nodes may be added to the single-server cluster for capacity, but they do not provide control-plane resilience.

When three-machine resilience is required, create a new three-server k3s cluster using embedded etcd before any production workloads are moved. This avoids an in-place SQLite-to-etcd control-plane conversion.

Implement later, as separate commits:

1. `infra/k3s/cluster/three-server/`: version-pinned server bootstrap configuration for three fixed server addresses.
2. Node/bootstrap automation: installs k3s, joins each server, configures time sync, and records the cluster token outside Git.
3. Multi-node ingress/load-balancer design: stable virtual IP, external load balancer, or DNS strategy for API and public ingress traffic.
4. Storage strategy: keep the databases external initially; replace local-path only when a workload requires shared persistent volumes.
5. Pod disruption budgets, replica counts, resource requests/limits, and anti-affinity for stateless DMOJ/Keycloak workloads.
6. A documented restore/rebuild exercise for a failed server and an explicit upgrade procedure.

## Acceptable-Downtime Cluster Migration

Use a planned cutover rather than attempting live conversion:

1. Build and validate the new three-server cluster with `dmoj-test` manifests and disposable data.
2. Confirm all external database, Redis, TLS, and image-registry connections from the new cluster.
3. Freeze production writes: put DMOJ into maintenance mode and stop workers/ingress after active submissions finish or are recorded for retry.
4. Back up DMOJ MariaDB, Keycloak MariaDB, Redis configuration/state if applicable, and current Kubernetes/Compose deployment metadata.
5. Deploy the exact production image digests and manifests to `dmoj-prod` on the new cluster.
6. Run DMOJ anonymous browsing, authenticated login, submission, remote judge, and Keycloak OIDC smoke tests.
7. Switch public DNS/load-balancer traffic only after the checks pass; retain the original single-node stack unchanged for rollback.
8. If validation fails, switch traffic back and restore the external stateful services only if they were modified during the attempt.

This produces a bounded maintenance window. Plan 1-3 hours for the first migration rehearsal and publish a user-facing maintenance window; actual cutover should be shorter once rehearsed.

## Directory Ownership

```text
infra/k3s/
  base/          # DMOJ and Keycloak workload manifests
  overlays/
    test/        # disposable k3s test namespace
    prod/        # production-only values and references
```

Use namespaces `dmoj-test` and `dmoj-prod`. Treat `dmoj-test` as disposable.

## Observability Add-On Plan

Deploy observability as a separate Layer 4 namespace and release path. See [Instrumentation and Observability](instrumentation.md) for telemetry data, retention, and privacy policy.

```text
infra/addons/observability/
  base/                 # namespace, RBAC, dashboards, alert rules
  overlays/
    test/               # short retention and low resource limits
    prod/               # reviewed retention, storage, and alert routing
```

Use a namespace such as `observability`. It observes `dmoj-test` and `dmoj-prod` but is not deployed as part of either application overlay.

### Components and Roles

| Component | Role | Initial deployment choice |
| --- | --- | --- |
| Grafana Alloy | Collect pod, node, and Kubernetes logs; forward them to Loki; optionally forward traces | DaemonSet on every k3s node |
| Loki | Store and query logs | Single replica with persistent storage; short retention first |
| Prometheus | Scrape Kubernetes, node, application, and exporter metrics | Single replica with persistent storage |
| Grafana | Dashboards and alert visualization | Single replica, backed up configuration |
| Tempo | Store distributed traces | Defer until a real cross-service debugging need exists |
| Alertmanager | Route alerts to the chosen notification target | Add with Prometheus when alerts are enabled |

### Independent Delivery Sequence

1. **Observability base:** namespace, network/RBAC policy, pinned Helm chart or image versions, resource requests/limits, and a render command. No data collectors yet.
2. **Metrics:** Prometheus, kube-state-metrics, node exporter, and cAdvisor/kubelet metrics. Add DMOJ MariaDB and Redis exporters when their external endpoints can be safely reached.
3. **Logs:** Grafana Alloy DaemonSet and Loki. Collect Kubernetes events plus container stdout/stderr from DMOJ, Keycloak, Traefik, and system workloads.
4. **Dashboards and alerts:** Grafana dashboards for node capacity, pod restarts, ingress status, DMOJ/Keycloak availability, database health, and judge queue behavior. Add one tested alert route before adding more alerts.
5. **Tracing:** OpenTelemetry Collector and Tempo only after application instrumentation exists and the capacity/retention plan is approved.

Each item is a separate commit and can be rolled back without changing DMOJ or Keycloak manifests.

### Single-Machine and Three-Machine Behavior

On the initial single server, keep all observability components single-replica with modest persistent storage and short retention. Reserve node capacity for DMOJ and judge workloads; Tempo is deferred.

For the later three-server cluster, run Alloy on every server/agent node. Continue with single-replica Loki, Prometheus, Grafana, and Tempo until uptime requirements justify their own high-availability storage and topology. Observability high availability is not a prerequisite for the application-cluster migration.

### Manual Validation

```bash
kubectl kustomize infra/addons/observability/overlays/test
kubectl apply --dry-run=server -k infra/addons/observability/overlays/test
kubectl get pods -n observability
kubectl get servicemonitors,podmonitors -A
```

Then generate a harmless request to DMOJ and confirm that its Nginx/Django logs appear in Loki and its health/HTTP metrics appear in Prometheus. Before enabling Tempo, confirm a test trace is visible from ingress through the DMOJ application without exposing credentials or tokens.

## Delivery Sequence

1. Create `infra/k3s/base` manifest structure and a render/validation command. No workload cutover.
2. Add external-service connection objects for MariaDB and Redis. Test DNS and network reachability from a disposable pod.
3. Deploy DMOJ workloads using already-published image digests.
4. Add ingress, certificates, and the bridged external port. Validate anonymous browsing and remote-judge connectivity.
5. Add Keycloak using the separately tested OIDC configuration from [the Keycloak plan](../keycloak/keycloak_dmoj_test_plan.md).
6. Add Layer 4 add-ons independently: observability, backups, TLS automation, and later Headscale.
7. Perform a deliberate cutover only after restore and rollback tests pass.

Each numbered item is separately committable and must include a manual test procedure.

## Validation

```bash
kubectl kustomize infra/k3s/overlays/test
kubectl apply --dry-run=server -k infra/k3s/overlays/test
kubectl get pods -n dmoj-test
```

For connectivity, use a short-lived test pod in the target namespace rather than assuming host-level reachability proves pod reachability.

## Operational Rules

- Reference image digests in manifests.
- Do not use `hostPath` or source bind mounts for application code.
- Do not put production credentials in manifests; use the selected secret-management mechanism.
- Back up external MariaDB and Redis before cutovers.
- Add agent nodes before server nodes. Make an explicit embedded-etcd/external-datastore decision before introducing HA control-plane nodes.
