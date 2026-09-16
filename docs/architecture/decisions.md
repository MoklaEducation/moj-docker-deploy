# Platform Decisions

Status: accepted

This document is the single authority for platform decisions. Focused documents in this directory explain implementation and operational detail; they must not restate or override these decisions.

## 1. Private Organization and Naming

Create one private GitHub organization for all platform-owned code and artifacts. Recommended organization name: `mokla-platform`.

Use role-based repository names without project-specific prefixes where the repository may serve future applications:

| Repository | Purpose |
| --- | --- |
| `platform` | Monorepo for application source, image definitions, k3s infrastructure, and platform documentation. This repository evolves from `moj-docker-deploy`. |
| `vendor-dmoj-online-judge` | Private mirror of `DMOJ/online-judge`. |
| `vendor-dmoj-wpadmin` | Private mirror of `DMOJ/dmoj-wpadmin`. |
| `vendor-dmoj-fernet-fields` | Private mirror of `DMOJ/django-fernet-fields`. |
| `vendor-dmoj-jsonfield` | Private mirror of `DMOJ/jsonfield`. |
| `vendor-dmoj-ansi2html` | Private mirror of `DMOJ/ansi2html`. |
| `vendor-dmoj-pdfoid` | Private mirror of `DMOJ/pdfoid`. |
| `vendor-dmoj-texoid` | Private mirror of `DMOJ/texoid`. |

Use package/repository names with the same `vendor-<upstream-owner>-<project>` format for future mirrored dependencies. Keep mirrors private where upstream licensing permits, retain upstream license/notice files, and satisfy the AGPL source-offer duty for the public DMOJ service.

## 2. Monorepo Structure and Source Import

`platform` is the target monorepo. It uses generic layer folders so future applications can live beside DMOJ:

```text
apps/                 # Layer 1: deployable application source
  dmoj/               # imported DMOJ source and local changes
images/               # Layer 2: Dockerfiles, image build definitions, CI
infra/
  k3s/                # Layer 3: Kubernetes base manifests and app overlays
  addons/             # Layer 4: observability, backups, private networking, TLS
  compose/            # temporary local/test Compose tooling while it remains useful
docs/
```

Import `vendor-dmoj-online-judge` into `apps/dmoj` with `git subtree`. Do not use Git submodules or manually copy source trees.

The subtree is an owned snapshot in `platform`; update it only through reviewed, test-gated subtree pulls from the private vendor mirror. Local DMOJ changes are committed in `platform` and can be maintained as a patch series or pushed back through `git subtree push` when appropriate.

## 3. Layered Build and Runtime Contract

- Layer 1 (`apps/`) provides application source.
- Layer 2 (`images/`) builds immutable OCI images from Layer 1 and publishes them with commit-derived tags/digests.
- Layer 3 (`infra/k3s/`) deploys only pinned Layer 2 image digests; it never builds images or mounts application source.
- Layer 4 (`infra/addons/`) contains independently deployable operational services and must not be coupled to individual application manifests.

The current Compose stack remains a local/test transition tool. It is not the target runtime architecture.

## 4. k3s Initiative Boundary

k3s is an independent initiative under `infra/k3s/`. Start it after the `apps/` and `images/` contracts are usable; it must not require application source restructuring in the same commit.

Initial scope:

- Single-node k3s.
- DMOJ workloads as Kubernetes workloads.
- Dedicated MariaDB for DMOJ, dedicated MariaDB for Keycloak, and Redis remain external to the cluster initially.
- Public ingress for DMOJ and Keycloak; private access only for operational add-ons.
- k3s consumes Layer 2 artifacts by digest.

A later integration phase marries the layers by deploying DMOJ image digests from `images/` through `infra/k3s/` manifests. It does not merge their ownership or release cadence.

## 5. Identity Boundary

DMOJ is public. Keycloak is the initial identity provider for test-first OIDC integration, as described in `../keycloak/keycloak_dmoj_test_plan.md`.

DMOJ integration remains provider-agnostic at the code boundary: it uses generic OIDC and stores identity by issuer plus subject. Keycloak is deployment configuration, not an application-specific protocol dependency. Headscale integration is deferred.

## 6. Change and Release Rules

- Every phase is independently committable and manually verifiable.
- Vendor mirror updates, source subtree updates, image changes, and k3s runtime changes are separate commits and separate CI concerns.
- Pin source dependencies by commit and images by digest. Never deploy mutable `latest` tags.
- Production secrets, client secrets, passwords, and private keys are never committed.
- Update this document for decision changes; update the focused document only for its implementation details.
