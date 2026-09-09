# Scripts Layout

This folder contains both public operator commands and internal helpers.

## Public Commands (Use These)
- dct
- dct-bootstrap
- dct-init

Primary interface:
- Use `dct` for daily operations (`up`, `down`, `stop`, `start`, `ps`, `logs`, `exec`).
- Use `dct bootstrap` for first-run or reseed/reset workflows.

## Internal Module
- teststack/common.sh
- teststack/dct-main.sh
- teststack/bootstrap-main.sh

These are implementation files used by `dct`/`dct-bootstrap` wrappers.

## Low-Level Legacy Helpers
- test-up
- test-down
- test-verify
- test-seed-import
- test-seed-export

These are still used internally and can be invoked directly for debugging,
but normal operator workflow should prefer `dct`.

## Django/Repo Utility Scripts
- copy_static
- enter_site
- initialize
- manage.py
- migrate

These scripts support lower-level maintenance tasks.
