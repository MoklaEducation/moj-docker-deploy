# Cluster Add-ons

This directory owns Phase 6 release inputs and repository-managed add-on resources.
Upstream chart output is rendered from a checksum-verified archive and is not committed.

## Operator Workflow

Install or verify controller dependencies explicitly:

```bash
./execution/k3s/operations/setup/controller.sh check
./execution/k3s/operations/setup/controller.sh install
```

Run the public cumulative workflow with the environment's SOPS identity configured:

```bash
./execution/k3s/bootstrap.sh check --environment test --through cluster-addons
./execution/k3s/bootstrap.sh apply --environment test --through cluster-addons
```

`check` downloads the pinned charts to temporary paths, verifies their checksums, renders them
twice, runs offline policy checks, checks live drift, and performs read-only certificate
HTTPS, Prometheus, node metrics, Grafana, and Alertmanager health checks. `apply`
bootstraps the fixed test identity when necessary, reconciles only detected chart or
owned-resource drift, and sends one disposable end-to-end alert probe.

The internal scripts under `scripts/` are narrow implementation entry points used by
bootstrap. They require current passing Phase 5 evidence and are not a replacement for
the cumulative public workflow.

## Current Capabilities

`certificates` installs cert-manager `v1.18.2`, a private test CA, a
seven-day leaf certificate, and a disposable Traefik HTTPS endpoint. The smoke client
uses `curl --resolve`; no public DNS or public ingress automation is required.

`metrics` installs kube-prometheus-stack `91.7.0` in the restricted `observability`
namespace and prometheus-node-exporter `4.58.0` in `observability-agents`. Prometheus
retains 48 hours in an 8 GiB PVC; Alertmanager and Grafana use 1 GiB and 2 GiB PVCs.
Grafana is private, anonymous Viewer-only, and has no initial admin account. Built-in
Kubernetes rules, dashboards, and the Prometheus data source are declarative chart
resources. Alertmanager routes to the Phase 3 disposable receiver.

The node-agent namespace is explicitly labeled for privileged Pod Security because node
exporter requires host networking, host PID, and read-only `/proc`, `/sys`, and `/`
mounts. Offline policy rejects those privileges everywhere else and rejects additional
host paths even in that namespace.

The test add-on identity temporarily receives `cluster-admin` through the explicitly
labeled `mokla:cluster-addons:test-admin` binding because the Helm release owns CRDs,
webhook configuration, and cluster RBAC. Replace this with split bootstrap and routine
permissions before production qualification.

Logs and backups remain disabled. Add Alloy/Loki as separate pinned releases while
preserving the existing acquire, render, policy, drift, apply, smoke, and evidence
boundaries. Backup remains a deferred, non-qualified capability.