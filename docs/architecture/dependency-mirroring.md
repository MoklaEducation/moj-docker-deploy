# Dependency Mirroring

See [Platform Decisions](decisions.md) for repository ownership, naming, source import, and release rules.

## Goal

Keep builds reproducible when upstream repositories or personal container namespaces disappear, while accepting upstream updates only through an explicit review and test gate.

## Mirrors

Fork these upstream repositories publicly in the `MoklaEducation` organization. Each
fork retains its GitHub upstream relationship and has a controlled `prod` branch for
reviewed deployment inputs.

| Fork | Fork URL | Upstream | Current use |
| --- | --- | --- | --- |
| `MoklaEducation/online-judge` | [online-judge](https://github.com/MoklaEducation/online-judge) | `DMOJ/online-judge` | DMOJ application source; later imported to `apps/dmoj` by subtree |
| `MoklaEducation/dmoj-wpadmin` | [dmoj-wpadmin](https://github.com/MoklaEducation/dmoj-wpadmin) | `DMOJ/dmoj-wpadmin` | Python dependency |
| `MoklaEducation/django-fernet-fields` | [django-fernet-fields](https://github.com/MoklaEducation/django-fernet-fields) | `DMOJ/django-fernet-fields` | Python dependency |
| `MoklaEducation/jsonfield` | [jsonfield](https://github.com/MoklaEducation/jsonfield) | `DMOJ/jsonfield` | Python dependency |
| `MoklaEducation/ansi2html` | [ansi2html](https://github.com/MoklaEducation/ansi2html) | `DMOJ/ansi2html` | Python dependency |
| `MoklaEducation/pdfoid` | [pdfoid](https://github.com/MoklaEducation/pdfoid) | `DMOJ/pdfoid` | Renderer image source |
| `MoklaEducation/texoid` | [texoid](https://github.com/MoklaEducation/texoid) | `DMOJ/texoid` | Renderer image source |

Also move ownership of the DMOJ base image away from the `ninjaclasher/*` namespace.

## Mirror Workflow

1. Fork the upstream repository into `MoklaEducation`.
2. Add `upstream` as a read-only remote in the fork.
3. Preserve an unmodified `upstream/<branch>` reference and promote reviewed commits to `prod`.
4. Test a proposed update in an `eval/upstream-<date>` branch before moving `prod`.
5. Reference exact commits in Python dependencies and Docker build inputs.
6. Run `git fsck --full` periodically and retain a second backup, such as a `git bundle`, outside the mirror host.

Example mirror creation:

```bash
gh repo fork DMOJ/online-judge --org MoklaEducation --clone=false
git clone https://github.com/MoklaEducation/online-judge.git online-judge
cd online-judge
git remote add upstream https://github.com/DMOJ/online-judge.git
git fetch upstream --tags
git switch -c prod
git push -u origin prod
```

## Subtree Import

After the fork's `prod` branch is reviewed, import it into the monorepo as `apps/dmoj`:

```bash
git remote add dmoj-app git@github.com:MoklaEducation/online-judge.git
git fetch dmoj-app
git subtree add --prefix=apps/dmoj dmoj-app prod --squash
```

Use `git subtree pull` for reviewed updates. Do not manually copy the source tree and do not recreate a submodule.

## Validation

Before advancing a mirrored dependency:

```bash
git fsck --full
git log --oneline prod..upstream/main
```

Then build the affected image and run its existing smoke tests. Record the promoted commit in the release metadata.

## Licensing

Retain upstream license and notice files. For modified network-facing AGPL DMOJ code, provide corresponding source to service users as required by AGPLv3 section 13.
