# Dependency Mirroring Progress

## Purpose

Checkpoint log for preserving the public DMOJ source dependencies locally before
repointing builds to owned repositories. This document records what has been captured,
what remains to be pushed to GitHub, and the validation required before consuming newer
upstream code.

## 2026-09-16: Initial local mirrors

Status: completed locally and published as public GitHub forks.

All seven public upstream repositories were reachable and cloned as bare mirrors outside
the deployment repository at:

```text
/home/ubuntu/repo/test-medocker-moj-004/dependency-mirrors/
```

| Local mirror | Upstream | Captured HEAD |
| --- | --- | --- |
| `mirror-dmoj-online-judge.git` | `https://github.com/DMOJ/online-judge.git` | `6aaddea6aaeabf4927b83787714509ff9fff8897` |
| `mirror-dmoj-dmoj-wpadmin.git` | `https://github.com/DMOJ/dmoj-wpadmin.git` | `dfafe1b20d69e2e0f8cf625fecbb957414040b80` |
| `mirror-dmoj-django-fernet-fields.git` | `https://github.com/DMOJ/django-fernet-fields.git` | `eaea7e760472106c015f65535f4837a1189c4e7c` |
| `mirror-dmoj-jsonfield.git` | `https://github.com/DMOJ/jsonfield.git` | `560bdca857a69b4a5b2773a79d7511ebc628f339` |
| `mirror-dmoj-ansi2html.git` | `https://github.com/DMOJ/ansi2html.git` | `485b4ad02cca1c078c35c3982e9c345b23905445` |
| `mirror-dmoj-pdfoid.git` | `https://github.com/DMOJ/pdfoid.git` | `55ebc64794d6531fc2837db28869e1b7c6cc6894` |
| `mirror-dmoj-texoid.git` | `https://github.com/DMOJ/texoid.git` | `f482221061e0d5e33296e60c77a0ead2c985f649` |

The local bare mirrors retain the public upstream as `upstream` and the corresponding
MoklaEducation fork as `origin`. The GitHub repositories are official public forks, so
GitHub displays their upstream parent and supports fork-network synchronization.

Published forks:

- `https://github.com/MoklaEducation/online-judge`
- `https://github.com/MoklaEducation/dmoj-wpadmin`
- `https://github.com/MoklaEducation/django-fernet-fields`
- `https://github.com/MoklaEducation/jsonfield`
- `https://github.com/MoklaEducation/ansi2html`
- `https://github.com/MoklaEducation/pdfoid`
- `https://github.com/MoklaEducation/texoid`

Each fork has a controlled `prod` branch and an immutable `baseline-2026-09-16` tag at
the captured upstream commit. The fork default branches remain separate from `prod`;
use `prod` for reviewed deployment inputs.

## Completed checkpoint: publish public forks to GitHub

The repositories were created as public forks:

```text
MoklaEducation/online-judge
MoklaEducation/dmoj-wpadmin
MoklaEducation/django-fernet-fields
MoklaEducation/jsonfield
MoklaEducation/ansi2html
MoklaEducation/pdfoid
MoklaEducation/texoid
```

Example for one mirror:

```bash
cd /home/ubuntu/repo/test-medocker-moj-004/dependency-mirrors/mirror-dmoj-online-judge.git
git remote rename origin upstream
git remote add origin git@github.com:MoklaEducation/online-judge.git
git push --mirror origin
```

Repeat for the other six mirrors. Preserve the `upstream` remote as read-only and use
`origin` for the owned GitHub mirror.

## Sync and promotion rules

- Fetch upstream changes with `git fetch upstream --tags --ff-only`.
- Do not force-update the mirror after an upstream history rewrite without investigation.
- Keep upstream references unmodified.
- Evaluate updates in an `eval/upstream-<date>` branch or equivalent review ref.
- Run the image build and smoke tests before promoting a change to `stable`.
- Pin application dependencies and Docker build inputs by commit SHA, not branch head.
- Tag deployed image/source states for rollback.
- Run `git fsck --full` periodically.
- Store periodic `git bundle` snapshots outside GitHub, such as encrypted object storage.

## Before repointing the deployment

Do not change `requirements.txt` or Docker clone URLs until the corresponding GitHub
mirrors are published and tested. Then update these inputs deliberately:

- The four DMOJ Git dependencies in `requirements.txt`.
- The `pdfoid` and `texoid` Dockerfile clone URLs.
- The main DMOJ source location during the later submodule-to-`apps/dmoj` migration.
- The remaining `ninjaclasher/dmoj-base` image references in `bridged` and `celery`.

## Integrity and licensing

The public mirrors preserve upstream history, licenses, and notices. The DMOJ
application and related network-facing modified services remain subject to AGPLv3
source-offer requirements. Mirroring is source preservation; it is not a substitute for
providing corresponding source to users of the modified public service.
