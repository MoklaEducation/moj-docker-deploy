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

## Directory Ownership

```text
infra/k3s/
  base/          # DMOJ and Keycloak workload manifests
  overlays/
    test/        # disposable k3s test namespace
    prod/        # production-only values and references
```

Use namespaces `dmoj-test` and `dmoj-prod`. Treat `dmoj-test` as disposable.

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
