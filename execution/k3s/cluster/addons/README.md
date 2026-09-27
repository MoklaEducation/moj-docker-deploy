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

`check` downloads the pinned chart to a temporary path, verifies its checksum, renders it
twice, runs offline policy checks, checks live drift, and performs read-only certificate
and HTTPS health checks. `apply` bootstraps the fixed test identity when necessary and
reconciles only detected chart or owned-resource drift.

The internal scripts under `scripts/` are narrow implementation entry points used by
bootstrap. They require current passing Phase 5 evidence and are not a replacement for
the cumulative public workflow.

## Current Capability

Only `certificates` is enabled. It installs cert-manager `v1.18.2`, a private test CA, a
seven-day leaf certificate, and a disposable Traefik HTTPS endpoint. The smoke client
uses `curl --resolve`; no public DNS or public ingress automation is required.

The test add-on identity temporarily receives `cluster-admin` through the explicitly
labeled `mokla:cluster-addons:test-admin` binding because the Helm release owns CRDs,
webhook configuration, and cluster RBAC. Replace this with split bootstrap and routine
permissions before production qualification.

Metrics, logs, and backups remain disabled in `platform.yml`. Add each as a separate
pinned release and preserve the existing acquire, render, policy, drift, apply, smoke,
and evidence boundaries.