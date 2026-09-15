# k3s-First Deployment Strategy: Requirements, Decisions, Actions

## Purpose

Capture the requirements and decisions from the k3s-vs-Compose discussion so the layered
build/deploy model (Layer 1 app, Layer 2 image build, Layer 3 runtime, Layer 4 orthogonal
add-ons) can be implemented directly on k3s, skipping a Docker Compose runtime layer.

## Requirements

### Functional

- DMOJ (site, celery, bridged, wsevent, texoid, pdfoid, mathoid) and Keycloak run as
  container workloads.
- MariaDB (DMOJ), MariaDB (Keycloak), and Redis run **outside** the cluster (host-level
  Docker or systemd), not as cluster-managed stateful workloads.
- Public HTTPS ingress for DMOJ and Keycloak; private access for internal tooling.
- Judge/`bridged` remains reachable on a stable external port for remote judges.
- DMOJ users accumulated before Keycloak adoption must be migratable to Keycloak-backed
  login without losing their existing account/history.

### Non-functional / operational

- Start with a single k3s node. Must be able to add nodes later without redesigning the
  application layer.
- Downtime is acceptable for cutovers and migrations; zero-downtime blue/green is not a
  requirement.
- Image build (Layer 2) must be independent of the runtime layer (Layer 3), so the same
  tagged image can be deployed identically regardless of node count.
- Application source (Layer 1) must not depend on a Git submodule checked out inside the
  deployment repo — this was the direct cause of the earlier detached-HEAD/dirty-submodule
  problem.
- Prefer a single repository, organized by folder, over multiple repositories. Multiple
  repositories remain acceptable if a boundary genuinely needs separate access control or
  release cadence, but add cognitive load and are not the default.
- Registry references must point to a private/owned namespace, not the upstream
  `ninjaclasher/*` Docker Hub namespace currently referenced in CI.

## Decisions

1. Build directly on k3s; do not build out a Docker Compose runtime layer first.
2. Keep MariaDB (x2) and Redis outside the cluster for the foreseeable future.
3. Single k3s node initially, default SQLite datastore, default `local-path` storage,
   built-in Traefik ingress.
4. Prefer one repository split into layer-scoped folders; CI path filters keep the
   build/deploy pipelines independent within that single repository.
5. Application source moves from a Git submodule to a plain folder in the same
   repository (or, if split out, a real branch in its own repository) — no detached HEAD.
6. Images are tagged by commit SHA (and optionally semantic version), never `:latest`, and
   pushed to a private registry namespace.
7. DMOJ users are migrated to Keycloak by directly inserting
   `social_auth_usersocialauth` rows (provider `openidconnect`, uid `issuer|sub`) rather
   than relying on the web login flow; a forced password reset on first Keycloak login is
   acceptable.
8. Scaling from 1 to 3 nodes will add agent (worker) nodes first; a highly-available
   control plane (embedded etcd or external DB datastore) is a separate, deliberate
   decision made only if control-plane resilience is actually needed.

## Decision → Action Mapping

| Decision | Suggested Action |
| --- | --- |
| Build directly on k3s | Author Layer 3 as plain k8s manifests or a Helm chart from the start; no `docker-compose.yml` for app services. |
| DBs stay outside the cluster | Keep MariaDB/Redis as host Docker/systemd services; expose to pods via `ExternalName` Services or manually-managed `Endpoints`. |
| Single node, default datastore | Use k3s defaults (SQLite, `local-path-provisioner`, Traefik); no HA config yet. |
| Single repo, folder-scoped layers | Create top-level folders `app/`, `images/`, `cluster/`, `docs/`; use CI `paths:` filters so each folder's pipeline runs independently. |
| No submodule for app source | Move DMOJ source into `app/` as a normal tracked folder (or a real branch in a dedicated repo, never a detached checkout). |
| Commit-based image tags, private registry | `images/` CI builds from `app/` at a pinned ref, tags `registry.example/dmoj-site:sha-<commit>`, pushes to your own namespace. |
| Code baked into images, not bind-mounted | Dockerfiles `COPY` source at build time; no `hostPath`/bind-mount of source into any pod. |
| Bulk-migrate DMOJ users to Keycloak | One-time Django management command: create Keycloak users via Admin API/`kcadm`, insert matching `social_auth_usersocialauth` rows, force password reset. |
| Downtime acceptable | No blue/green needed for the migration cutover or for any future HA control-plane bootstrap. |
| Future 1→3 node growth | Add agent nodes freely at any time; decide the HA datastore (embedded etcd vs external DB) before adding server nodes, not after. |
| Public TLS | Use k3s's built-in Traefik plus `cert-manager` for automatic Let's Encrypt certificates on public hostnames. |
| Private/internal TLS | Use a private CA (e.g., `step-ca`) or DNS-01 challenges for internal-only hostnames; do not expose internal services publicly to get a certificate. |
| Observability | Deploy Prometheus/Grafana/Loki and exporters as an independent Layer 4 namespace/overlay, not coupled to app manifests. |
| Private networking | Deploy Headscale as its own Layer 4 component for admin/private access; not used for intra-cluster traffic. |

## Suggested Repository Layout (single-repo, folder-scoped)

```text
repo-root/
  app/                 # Layer 1: DMOJ application source (real folder or branch, no submodule)
  images/              # Layer 2: Dockerfiles + CI to build, tag (by commit), and push
  cluster/
    base/              # Layer 3: k8s manifests/Helm chart for DMOJ + Keycloak workloads
    overlays/
      observability/   # Layer 4: Prometheus/Grafana/Loki/exporters
      backups/         # Layer 4: backup jobs/cron
      headscale/       # Layer 4: private networking
      cert-manager/    # Layer 4: TLS automation
  docs/                # Strategy docs, runbooks, migration plans
```

CI triggers scoped by path (for example, GitHub Actions `paths:` filters) keep the
build (`images/`) and deploy (`cluster/`) pipelines decoupled even though they live in one
repository, which was the original goal of separating build from deploy without taking on
the cognitive overhead of multiple repositories.

## Suggested Phased Implementation

1. **Repo restructuring** — introduce `app/`, `images/`, `cluster/` folders; move DMOJ
   source out of the submodule into `app/`; no functional/runtime change yet.
2. **Layer 2: image build pipeline** — CI builds from `app/` at a pinned ref, tags by
   commit, pushes to a private registry namespace (replacing `ninjaclasher/*`).
3. **Layer 3: base k3s manifests** — DMOJ workloads (site, celery, bridged, wsevent),
   external-DB Services, Traefik ingress, referencing the tagged images from step 2.
4. **Keycloak on k3s** — port the existing Compose Keycloak setup and OIDC wiring
   (application code is unchanged) into `cluster/base` or its own overlay.
5. **Observability overlay** — Prometheus/Grafana/Loki as an independent namespace/overlay.
6. **Operational overlays** — backups, cert-manager/TLS automation, Headscale, as needed.
7. **DMOJ → Keycloak user migration** — bulk-link script plus forced password reset,
   executed as a planned, downtime-acceptable cutover.
8. **Future node-count decision point** — evaluate whether growth needs only agent nodes
   (no migration) or an HA control plane (datastore decision made explicitly beforehand).

## Orthogonal Bootstrap Services

Beyond the DMOJ/Keycloak workload stack, a hybrid cloud+home deployment connected over
Headscale needs a foundation layer of shared infrastructure services. These are
orthogonal to DMOJ itself and, once built, support every future service (education,
chat, home automation, etc.), not just DMOJ.

### A. Network and identity foundation (depend on nothing else)

- **Private DNS** — CoreDNS, AdGuard Home, or Unbound; split-horizon so
  `*.internal.example.com` resolves only over Headscale.
- **Private CA / certificate automation** — `step-ca` for internal TLS, `cert-manager`
  plus Let's Encrypt for public TLS.
- **Time sync (NTP)** — `chrony` on every node. Clock drift silently breaks certificate
  validation, token expiry, and log correlation.
- **Keycloak, extended role** — beyond DMOJ, use it as SSO for Grafana, the registry UI,
  Git hosting, and any other internal tool with a login.

### B. Source and artifact management

- **Private Git** — Gitea or Forgejo (lightweight) vs. self-hosted GitLab CE (heavier,
  more built-in CI). Needed for the Layer 1 application repository.
- **Docker/OCI registry** — `registry:2` (minimal) or Harbor (registry plus
  vulnerability scanning, RBAC, UI). Needed for Layer 2 image publishing.
- **CI runner** — a self-hosted runner (Gitea Actions, Drone/Woodpecker) so Layer 2
  builds do not depend solely on a third-party CI quota.
- **Dependency/package mirror** *(optional, later)* — pull-through cache for Docker Hub,
  or Verdaccio/devpi, to cut egress cost and build time once builds are frequent.

### C. Storage and secrets

- **Object storage** — MinIO (S3-compatible) for backups, media, submission artifacts,
  and registry blob storage.
- **Simple file share** *(optional)* — Samba/NFS for less structured data.
- **Backup orchestration** — Restic or Borg repository, separate from the object storage
  it writes to; needs its own retention policy and restore-test schedule.
- **Secrets vault** — Vault, or the lighter SOPS + age (encrypted secrets committed to
  Git), or Vaultwarden for human-facing credentials.

### D. Observability and operations

- **Alerting/notification gateway** — Alertmanager routed into `ntfy`, Matrix, or a
  Discord/Slack webhook; otherwise metrics/logs accumulate without anyone being notified.
- **Uptime/status page** — Uptime Kuma or Gatus, for a simple "is it up" view for
  family/education users without requiring Grafana access.

### E. Provisioning and lifecycle

- **Node bootstrap automation** — an Ansible playbook or checked-in shell script that
  reproducibly installs the Headscale client, Docker/k3s agent, node exporter, and
  chrony, and joins DNS/Headscale on any new node. This matters as soon as a second
  physical or virtual node is added, to avoid a hand-configured, drifting snowflake node.
- **Config/secret distribution** — how encrypted secrets from section C actually reach a
  freshly-bootstrapped node; normally paired with the bootstrap automation above.

### Suggested priority order

1. Private DNS and private CA — unlocks clean internal hostnames/TLS for everything else.
2. Object storage (MinIO) — backups and Layer 2 build artifacts need a destination.
3. Private Git and registry — directly required by the Layer 1/Layer 2 split.
4. Node bootstrap automation — do this before adding a second node, not after.

Vault, Harbor's scanner, package mirrors, and status pages are real value but not
blocking for the current single-node k3s plan.

## Open Questions

- Registry choice (managed vs. self-hosted over Headscale) — see
  `deployment_image_strategy.md` for the tradeoffs already recorded.
- Whether `app/` stays in this repository or becomes its own repository once the OIDC
  work stabilizes — either is compatible with this plan; only the CI wiring changes.
- Exact ingress/cert boundary between public DMOJ/Keycloak hostnames and private
  Layer 4 service hostnames — see `deployment_instrumentation_strategy.md` for the
  related observability-specific guidance.
