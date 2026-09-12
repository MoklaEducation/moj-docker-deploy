# Scripts Layout

This folder contains the modular test-stack command groups and lower-level repo utilities.

## dct Commands
- teststack/dct/dct
- teststack/dct/dct-bootstrap
- teststack/dct/dct-init

Primary interface:
- Use `dct` for daily operations (`up`, `down`, `stop`, `start`, `ps`, `logs`, `exec`).
- Use `dct doctor` to check tooling and bootstrap prerequisites.
- Use `dct bootstrap` for first-run or reseed/reset workflows.
- `dct down -v` is destructive and prompts for confirmation unless `--yes` is passed.

## Shared dct Module
- teststack/common.sh
- teststack/dct-main.sh
- teststack/bootstrap-main.sh

These are implementation files used by the `teststack/dct/*` commands.

## Lifecycle Commands
- teststack/lifecycle/test-up
- teststack/lifecycle/test-down
- teststack/lifecycle/test-verify
- teststack/lifecycle/test-bootstrap

## Seed Commands
- teststack/seed/test-seed-import
- teststack/seed/test-seed-export

Lifecycle and seed commands support debugging, but normal operator workflow should prefer `dct`.

## Maintenance Commands
- teststack/maintenance/enter_site
- teststack/maintenance/initialize

## Django/Repo Utility Scripts
- copy_static
- enter_site
- initialize
- manage.py
- migrate

These scripts support lower-level maintenance tasks.
