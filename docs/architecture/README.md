# Platform Architecture

This directory is the authoritative record for platform-level decisions. It is designed for handoff: read `decisions.md` first, then the focused strategy document for the work being planned.

## Documents

- `decisions.md`: frozen repository, dependency, layering, and k3s boundaries.
- `dependency-mirroring.md`: private mirrors, pinned dependencies, and upstream promotion.
- `image-build.md`: Layer 2 image build, registry, and release policy.
- `instrumentation.md`: observability scope and rollout.
- `k3s-runtime.md`: Layer 3 k3s initiative and Layer 4 operational add-ons.

## Scope Boundaries

- The `apps/` folder owns deployable application source as normal Git-tracked directories.
- The `images/` folder owns image definitions and build automation.
- The `infra/k3s/` folder owns Kubernetes runtime configuration.
- `docs/keycloak/` owns Keycloak-specific, test-first authentication delivery plans.

Do not duplicate decisions across documents. Update `decisions.md` when a platform decision changes; link to it from focused plans.
