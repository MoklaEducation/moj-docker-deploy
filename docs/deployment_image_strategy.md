# Deployment and Docker Image Strategy

## Purpose

This document records repository ownership, Docker image build and publishing options, and practical tooling for a small DMOJ deployment with optional Keycloak integration.

The immediate goal is a reliable test-to-production path without requiring a large platform team or a registry running on the production server.

## Recommended Repository Boundaries

### 1. Deployment repository

Keep the current deployment repository as the source of truth for:

- Docker Compose files
- Nginx configuration
- TLS setup instructions
- Keycloak test overlay and sanitized realm definition
- `dct` lifecycle scripts
- Environment examples
- Deployment and recovery documentation

This repository should not contain production secrets, private keys, or local runtime env files.

### 2. Private DMOJ application repository

The application under `dmoj/repo` is currently a Git submodule pointing to the upstream DMOJ repository. Because the Keycloak OIDC changes modify DMOJ application code, maintain a private repository or private fork for the deployable application version.

The private application repository should contain:

- DMOJ settings and authentication code
- Keycloak OIDC backend and pipeline changes
- Login template changes
- Application dependency changes
- Application tests

Use a real branch rather than leaving the submodule at detached HEAD. The deployment repository should record a pushed, reviewable submodule commit.

### 3. Optional infrastructure repository

A separate infrastructure repository is useful only when deployment configuration becomes large or is shared across multiple environments. It can contain:

- Production-only Compose overrides
- Backup jobs
- Monitoring configuration
- Secret-management integration
- Server bootstrap scripts

For the current small deployment, keeping this with the deployment repository is reasonable. Do not split repositories merely to create more boundaries.

### 4. Container image registry

Treat the registry as a distribution system, not as a source repository. It should contain built images such as:

```text
dmoj-base
dmoj-site
dmoj-celery
dmoj-bridged
```

Keycloak and MariaDB should continue to use pinned upstream image versions unless there is a specific reason to build private derivative images.

## Image Build and Publish Options

### Option A: Managed registry and CI build

Recommended when available:

```text
Private DMOJ repository
        |
        v
CI build and test
        |
        v
Managed private registry
        |
        v
Production server pulls an immutable image
```

Possible services:

- GitHub Actions plus GitHub Container Registry
- GitLab CI plus GitLab Container Registry
- Docker Hub private repositories
- Azure Container Registry
- Another managed OCI registry already used by the organization

Benefits:

- Builds do not consume production CPU and memory.
- Images are available for rollback.
- Build logs and test results are retained.
- Production pulls a known artifact rather than compiling at deploy time.

Use immutable tags or digests:

```text
registry.example/dmoj-base:sha-<commit>
registry.example/dmoj-site:sha-<commit>
```

Prefer deploying by digest when practical:

```text
registry.example/dmoj-site@sha256:<digest>
```

Do not use `latest` as the production deployment reference.

### Option B: Build directly on the production server

This is acceptable for a small single-server deployment when a registry is not yet practical.

Basic workflow:

```bash
git fetch origin
git checkout <approved-deployment-commit>
# Also initialize/update the DMOJ application submodule at the recorded commit.
docker compose build base site
docker compose up -d
```

Safeguards:

- Build only from an approved commit or tag.
- Keep the previous image available for rollback.
- Record the Git commit, image IDs, Dockerfile versions, and build time.
- Run Compose rendering, Django checks, and smoke tests before declaring success.
- Do not put production secrets in Docker build arguments or image layers.
- Do not run `down -v` during an ordinary deployment.
- Back up application and Keycloak databases before risky changes.

The main weakness is reproducibility: upstream base images and package indexes can change between builds. Pin base images and dependency versions as much as possible.

### Option C: Build on a separate machine, transfer images

A workstation, home server, or small build VM can build images and transfer them to production:

```bash
docker save registry.example/dmoj-site:<tag> | gzip > dmoj-site.tar.gz
scp dmoj-site.tar.gz production:/tmp/
ssh production 'gunzip -c /tmp/dmoj-site.tar.gz | docker load'
```

This avoids a registry but creates manual artifact-transfer and cleanup work. It is useful as a temporary bridge, not an ideal long-term release process.

### Option D: Self-hosted registry at home over Headscale

A private registry can run on a home server and be reachable from production over a Headscale network:

```text
Production server -- Headscale network -- Home registry
```

This can work for low-frequency deployments, but it introduces availability dependencies:

- Home server uptime
- Home internet upload bandwidth
- Headscale control-plane availability
- Registry storage and backups
- TLS and authentication management

If using this option:

- Keep the registry private and do not expose its port publicly.
- Give it a stable Headscale IP or private DNS name.
- Use TLS; do not use Docker's insecure-registry setting in production.
- Create a read-only pull credential for production.
- Back up the registry storage.
- Keep previously deployed images on the production server for rollback.

A managed registry is usually simpler. A Headscale-connected home registry is reasonable when cost and control matter more than registry availability.

## Recommended Path for This Deployment

For the current small deployment:

1. Create a private DMOJ application repository or private fork.
2. Commit the OIDC changes on a branch in that repository.
3. Push the application commit and update the deployment repository's submodule pointer.
4. Initially build images directly on the production server or on a separate build machine.
5. Tag locally built images with the application/deployment commit.
6. Move to GHCR, GitLab Container Registry, or another managed registry when rollback and repeatability become important.
7. Keep the Keycloak test overlay separate from production Compose files.

Do not merge the branch into production until the normal production image build has been tested. In particular, verify the shared `site/Dockerfile` base-image choice and confirm that test-only files are not loaded by the production deployment.

## Useful Tools

### Build and packaging

- Docker Buildx for repeatable builds and multi-platform support.
- Docker Compose for the current single-server deployment.
- `docker build --check` or Compose config rendering for early configuration errors.
- `make` or a small checked-in shell wrapper for standard build commands.

### Security and supply chain

- Trivy for image and dependency vulnerability scanning.
- Cosign for signing images and verifying signatures before deployment.
- Syft for generating SBOMs.
- Dependabot or Renovate for dependency and image update proposals.

### CI and release automation

- GitHub Actions if the private application repository is hosted on GitHub.
- GitLab CI if the repositories are hosted on GitLab.
- A release workflow that builds, scans, tests, tags, and publishes images in that order.
- `act` can run some GitHub Actions locally, but it should not replace CI validation.

### Deployment and operations

- Ansible for repeatable server setup if more than one server is involved.
- `systemd` or a simple deployment script to serialize production updates.
- Uptime monitoring for DMOJ, Keycloak discovery, and the database.
- Restic, Borg, or the hosting provider's backup service for encrypted backups.
- Headscale only for private administration or private registry connectivity, not as a substitute for image versioning.

## Minimum Release Checklist

Before a production deployment:

```text
[ ] DMOJ application commit is pushed and reviewable.
[ ] Deployment repository records the exact application commit.
[ ] Image build uses the intended repository and Dockerfile.
[ ] Image tag or digest is immutable and recorded.
[ ] Production Compose config renders successfully.
[ ] Test-only Compose files and hostnames are excluded.
[ ] Images pass vulnerability scanning or the exceptions are documented.
[ ] DMOJ and Keycloak database backups are current.
[ ] Rollback image and rollback procedure are available.
[ ] DMOJ anonymous browsing and local login are tested.
[ ] Keycloak OIDC discovery and login are tested when enabled.
```

## Final Recommendation

For a small installation, begin with direct builds on a controlled server or a separate build machine. Keep releases tied to explicit commits and retain old images. Adopt a managed private registry when the need for repeatable builds, easy rollback, or multiple deployment targets outweighs the cost of setting it up.

Do not run a registry on the production server unless there is a clear operational reason. A registry is lightweight in CPU terms, but it still needs storage, TLS, authentication, cleanup, backup, and recovery procedures.
