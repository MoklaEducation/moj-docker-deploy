# Dependency Mirroring

See [Platform Decisions](decisions.md) for repository ownership, naming, source import, and release rules.

## Goal

Keep builds reproducible when upstream repositories or personal container namespaces disappear, while accepting upstream updates only through an explicit review and test gate.

## Mirrors

Mirror these upstream repositories in the private `mokla-platform` organization:

| Mirror | Upstream | Current use |
| --- | --- | --- |
| `mirror-dmoj-online-judge` | `DMOJ/online-judge` | DMOJ application source; later imported to `apps/dmoj` by subtree |
| `mirror-dmoj-wpadmin` | `DMOJ/dmoj-wpadmin` | Python dependency |
| `mirror-dmoj-fernet-fields` | `DMOJ/django-fernet-fields` | Python dependency |
| `mirror-dmoj-jsonfield` | `DMOJ/jsonfield` | Python dependency |
| `mirror-dmoj-ansi2html` | `DMOJ/ansi2html` | Python dependency |
| `mirror-dmoj-pdfoid` | `DMOJ/pdfoid` | Renderer image source |
| `mirror-dmoj-texoid` | `DMOJ/texoid` | Renderer image source |

Also move ownership of the DMOJ base image away from the `ninjaclasher/*` namespace.

## Mirror Workflow

1. Create a bare mirror from the upstream repository and push it to the private organization.
2. Add `upstream` as a read-only remote in the private mirror.
3. Preserve an unmodified `upstream/<branch>` reference and promote reviewed commits to `stable`.
4. Test a proposed update in an `eval/upstream-<date>` branch before moving `stable`.
5. Reference exact commits in Python dependencies and Docker build inputs.
6. Run `git fsck --full` periodically and retain a second backup, such as a `git bundle`, outside the mirror host.

Example mirror creation:

```bash
git clone --mirror https://github.com/DMOJ/online-judge.git mirror-dmoj-online-judge.git
git -C mirror-dmoj-online-judge.git remote add private git@github.com:mokla-platform/mirror-dmoj-online-judge.git
git -C mirror-dmoj-online-judge.git push --mirror private
```

## Subtree Import

After the mirror is stable, import it into the monorepo as `apps/dmoj`:

```bash
git remote add mirror-dmoj git@github.com:mokla-platform/mirror-dmoj-online-judge.git
git fetch mirror-dmoj
git subtree add --prefix=apps/dmoj mirror-dmoj stable --squash
```

Use `git subtree pull` for reviewed updates. Do not manually copy the source tree and do not recreate a submodule.

## Validation

Before advancing a mirrored dependency:

```bash
git fsck --full
git log --oneline stable..upstream/main
```

Then build the affected image and run its existing smoke tests. Record the promoted commit in the release metadata.

## Licensing

Retain upstream license and notice files. For modified network-facing AGPL DMOJ code, provide corresponding source to service users as required by AGPLv3 section 13.
