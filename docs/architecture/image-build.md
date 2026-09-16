# Image Build and Release

See [Platform Decisions](decisions.md) for layer ownership and repository layout, and [Dependency Mirroring](dependency-mirroring.md) for upstream source controls.

## Goal

Build reproducible Layer 2 OCI images from `apps/` and publish immutable artifacts for the runtime layer. The k3s manifests never build application code.

## Inputs and Outputs

```text
apps/dmoj at a reviewed commit
  -> images/dmoj build definitions
  -> CI build, test, scan
  -> private OCI registry
  -> immutable image digest
  -> infra/k3s deployment reference
```

Build images include DMOJ base, site, celery, bridged, wsevent, mathoid, texoid, and pdfoid. Keycloak and MariaDB consume pinned upstream images unless a derivative image is justified.

## Policy

- Pin base images by digest and application/dependency inputs by commit.
- Tag candidate images with the Layer 1 commit SHA, for example `ghcr.io/mokla-platform/dmoj-site:sha-<commit>`.
- Deploy the resulting image digest, not `latest` or a mutable branch tag.
- Build outside production where possible. A managed private registry is preferred; direct controlled builds are an interim option.
- Retain the prior deployed digest for rollback.
- Never pass production secrets as Docker build arguments or bake them into images.

## Release Flow

1. Merge a reviewed source or image-definition commit.
2. CI builds the affected image set.
3. CI runs image smoke tests and vulnerability scanning; document accepted findings.
4. CI publishes commit-tagged images and records their digests.
5. A runtime change in `infra/k3s/` references those exact digests.
6. Back up stateful services, apply runtime change, and verify DMOJ plus Keycloak OIDC when enabled.
7. Tag the platform commit only after verification.

## Validation

For every image-release change:

```bash
docker buildx build --check <context>
docker compose config
```

Then run the applicable DMOJ bootstrap/verification or Kubernetes smoke check. Verify the deployed image ID/digest matches the release record.

## Deferred Work

Registry hosting, image signing, SBOM generation, and automated dependency update proposals are valuable additions but do not alter the Layer 1/2/3 contract.
