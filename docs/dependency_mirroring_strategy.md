# Dependency Mirroring Strategy

## Purpose

Record which external source repositories and container images this deployment depends
on that are not under our control, and the strategy for mirroring them and safely
absorbing upstream changes without introducing regressions or corruption.

This is separate from `deployment_image_strategy.md` (which covers *our own* image
build/publish pipeline) and `deployment_k3s_strategy.md` (runtime/layering strategy).
This document is about *third-party* source we depend on but do not own.

## Repositories to Mirror

All of the following are small, low-traffic repositories under a single GitHub
organization or personal account — exactly the kind of dependency that can disappear
(org renamed, repo archived/deleted, maintainer account issue) with little warning.
Mirror all of them now, while still available.

| Repository | Where it is used | Risk if unavailable |
| --- | --- | --- |
| `DMOJ/online-judge` | Main application (currently `dmoj/repo` submodule; becomes `app/` after restructuring) | Build fails entirely |
| `DMOJ/dmoj-wpadmin` | `requirements.txt` | `pip install` fails |
| `DMOJ/django-fernet-fields` | `requirements.txt` | `pip install` fails |
| `DMOJ/jsonfield` | `requirements.txt` | `pip install` fails |
| `DMOJ/ansi2html` | `requirements.txt` | `pip install` fails |
| `DMOJ/pdfoid` | `pdfoid/Dockerfile` — cloned fresh at every image build | Image build fails immediately |
| `DMOJ/texoid` | `texoid/Dockerfile` — cloned fresh at every image build | Image build fails immediately |

Mirror command:

```bash
for repo in online-judge dmoj-wpadmin django-fernet-fields jsonfield ansi2html pdfoid texoid; do
  git clone --mirror "https://github.com/DMOJ/${repo}.git" "${repo}.git"
done
```

Push each mirror to your own Git host (GitHub or self-hosted), then re-point:

- The four `git+https://github.com/DMOJ/...` lines in `requirements.txt` to the mirrors.
- The `git clone` lines in `pdfoid/Dockerfile` and `texoid/Dockerfile` to the mirrors.

## Naming Scheme

Isolate this initiative from other, future initiatives (course platform, chat, home
automation), and isolate risky in-progress work (the k3s migration) from the currently
working Compose deployment, using two axes: an initiative prefix and a lifecycle stage.

### Initiative prefix

```text
dmoj-*      <- this initiative (DMOJ + Keycloak + k3s)
course-*    <- future course platform
chat-*      <- future chat service
home-*      <- future home automation
```

### Repository names within the initiative

| Repository | Role |
| --- | --- |
| `dmoj-deploy` | Layer 3+4: k3s manifests, overlays, docs (this repository, eventually renamed from `moj-docker-deploy`) |
| `dmoj-app` | Layer 1: mirror of `DMOJ/online-judge` plus local changes (replaces the `dmoj/repo` submodule) |
| `dmoj-images` | Layer 2: Dockerfiles + CI, only if split into its own repository; otherwise a folder in `dmoj-deploy` |
| `dmoj-vendor-wpadmin`, `dmoj-vendor-fernet-fields`, `dmoj-vendor-jsonfield`, `dmoj-vendor-ansi2html`, `dmoj-vendor-pdfoid`, `dmoj-vendor-texoid` | The six small dependency mirrors listed above |

### Branches, not new repositories, isolate risky work

Since a single repository with folders is preferred, isolate the k3s
repo-restructuring effort with a branch rather than a separate repository, so
abandoning it is a branch deletion, not a repository teardown:

```text
main                        <- current working Compose-based deployment, untouched
experiment/k3s-migration    <- all repo-restructuring and k3s work happens here
experiment/keycloak-oidc    <- prior Keycloak integration work
```

Escalate to a genuinely separate, throwaway repository only for a spike that is never
merged and never depended on by anything else:

```text
dmoj-k3s-spike-2026-09
```

### Cluster namespace naming (k3s)

Matches the existing `dmoj-test` Compose project-name convention:

```text
dmoj-test    <- k3s namespace for the experiment, deletable with one command
dmoj-prod    <- created only once the migration is proven
```

```bash
kubectl delete namespace dmoj-test
```

### Registry and image tags

```text
registry.example/dmoj/dmoj-site:sha-<commit>
registry.example/dmoj/dmoj-base:sha-<commit>
```

Same `dmoj/` prefix as the repository naming, so the initiative is identifiable
consistently across Git, the registry, and the cluster namespace.

## Docker Images to Re-Point

| Image | Where it is used | Note |
| --- | --- | --- |
| `ninjaclasher/dmoj-base:latest` | `bridged/Dockerfile`, `celery/Dockerfile` | Personal Docker Hub namespace; `site/Dockerfile` already switched to `moj/dmoj-base:latest` — `bridged`/`celery` still need the same change for consistency. |

Lower priority, official/verified images (Docker Official Images, low disappearance
risk, but still worth caching in your own registry eventually per
`deployment_image_strategy.md`): `python:3.11-slim-bookworm`, `node:18`, `node:alpine`,
`nginx:alpine`, `mariadb`, `redis:alpine`, `mariadb:11.4.5`,
`quay.io/keycloak/keycloak:26.0.5`.

## Licensing Note

`DMOJ/online-judge` (and likely its satellite render services `pdfoid`/`texoid`) are
licensed under **GNU AGPLv3**. Mirroring the source itself is unrestricted under any of
these licenses provided attribution/license files are preserved. Separately, AGPL §13
requires that users interacting with the **running, modified, network-facing service**
be offered access to the corresponding source — this obligation attaches to the live
DMOJ instance, independent of whether the mirror or development repository is private.
Keep a visible source-code link or a documented offer-on-request process on the public
site.

## Sync Strategy: Minimizing Regressions and Corruption

The guiding principle: **a mirror is a buffer, not a pass-through.** Nothing upstream
reaches the build until it has been explicitly fetched, tested, and promoted.

### 1. Two branches per mirrored repository

```text
upstream/main   <- exact mirror, fast-forward-only, never edited directly
stable          <- what builds/deploys actually reference, advanced manually
```

### 2. Fetch fast-forward-only

```bash
git remote add upstream https://github.com/DMOJ/online-judge.git
git fetch upstream --tags --ff-only
```

`--ff-only` is the actual corruption/regression guard: if upstream force-pushed or
rewrote history, the fetch fails loudly instead of silently rewriting the mirror.
Investigate before ever re-fetching with `--force`.

### 3. Gate every upstream advance through CI before merging

```bash
git checkout -b eval/upstream-<date> upstream/main
# push and let the existing build + smoke-test pipeline run against it
```

Only merge `upstream/main` into `stable` after the throwaway branch passes the same
build/smoke checks already used in CI (image build, migrate, collectstatic, fixture
load). This is the manual equivalent of what Dependabot/Renovate do automatically for
registry-based dependencies, applied here to git-mirrored source.

### 4. Pin by commit SHA everywhere, never by branch name

- `requirements.txt`: `dmoj-wpadmin @ git+https://your-git/dmoj-wpadmin.git@<pinned-sha>`
- Dockerfiles: clone, then `git checkout <pinned-sha>` instead of cloning a branch head.
- `app/` (post-restructuring) references `stable` only after it has been advanced
  deliberately per step 3.

A bad or regressed commit on `stable` is then always one
`git reset --hard <last-known-good-sha>` away from recovery, because every deployed
state is a tagged, known commit.

### 5. Tag every commit actually deployed

```bash
git tag deployed-2026-09-15
```

Gives an instant rollback target independent of wherever `stable` currently points.

### 6. Periodic integrity checks and a second backup location

```bash
git fsck --full
```

on each mirror, on a schedule. Since the goal is resilience against a source
disappearing, do not let the mirror host be the only copy either — export periodic
`git bundle` snapshots to separate object storage (see the backup guidance in
`deployment_image_strategy.md`), so a mirror-host-side problem does not take out both
the original and the safety copy at once.

### 7. Same pattern for the Docker base image

Pin by digest, not tag, once `bridged`/`celery` are re-pointed to the owned base image:

```dockerfile
FROM moj/dmoj-base@sha256:<digest>
```

Re-verify and re-pull deliberately rather than always tracking a mutable tag.

## Action Checklist

```text
[ ] Mirror all seven DMOJ/* repositories to an owned Git host.
[ ] Re-point requirements.txt git+https entries to the mirrors.
[ ] Re-point pdfoid/Dockerfile and texoid/Dockerfile clone URLs to the mirrors.
[ ] Re-point bridged/Dockerfile and celery/Dockerfile to the owned base image.
[ ] Pin all of the above by commit SHA or image digest, not branch/tag.
[ ] Set up upstream/stable branch split with fast-forward-only fetch.
[ ] Add a CI evaluation step before promoting upstream changes to stable.
[ ] Tag every deployed commit.
[ ] Schedule git fsck and a secondary bundle backup for each mirror.
[ ] Confirm the public DMOJ instance offers a source-code link per AGPL §13.
```
