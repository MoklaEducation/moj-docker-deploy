# dct Usage

## Purpose
Provide a single command surface for the test stack, while preserving compose compatibility and test isolation.

## Scripts
- dmoj/scripts/dct
- dmoj/scripts/dct-bootstrap
- dmoj/scripts/dct-init

Run from dmoj:
```bash
cd /path/to/moj-docker-deploy/dmoj
```

## One-Time Per Shell: Enable From Anywhere
To run `dct` and `dct-bootstrap` from any directory, source the init script once per shell session:

```bash
source /path/to/moj-docker-deploy/dmoj/scripts/dct-init
```

Important:
- Source only `dct-init`.
- Do not source `dct`; run it as a normal command.

Verification:
```bash
command -v dct
command -v dct-bootstrap
```

Persist across future shells (optional):
```bash
echo 'source /path/to/moj-docker-deploy/dmoj/scripts/dct-init' >> ~/.bashrc
```

## Defaults
Both wrappers use these defaults unless overridden:
- PROJECT_NAME=dmoj-test
- ENV_FILE=.env.test
- Compose files: docker-compose.yml + docker-compose.test.yml

Override example:
```bash
PROJECT_NAME=my-test ENV_FILE=.env.test ./scripts/dct ps
```

## Primary Interface
Use `dct` as the primary operator command.

First-run/bootstrap:
```bash
dct bootstrap
```

Non-interactive/automation bootstrap:
```bash
dct bootstrap --yes
```

Verification:
```bash
dct verify
```

Seed operations:
```bash
dct seed-import
dct seed-export
```

## Compose Compatibility
`dct` forwards compose commands with test flags injected.

Examples:
```bash
./scripts/dct up -d
./scripts/dct down
./scripts/dct down -v
./scripts/dct stop
./scripts/dct start
./scripts/dct ps
./scripts/dct logs -f nginx
./scripts/dct exec site bash
```

Bootstrap detection behavior:
- For `up`, `start`, and `restart`, `dct` checks required bootstrap prerequisites.
- If required files are missing, it exits with a clear message and asks you to run `dct bootstrap`.

## dct-bootstrap Script
dct-bootstrap remains available as the underlying script, and `dct bootstrap` calls it.

## dct-bootstrap: First-Run / Reset Wrapper
Use `dct-bootstrap` on:
1. New machine
2. Fresh clone
3. After destructive reset
4. Any time you want a known seeded baseline

Important:
- Re-running `dct-bootstrap` resets and re-imports test database data from `SEED_DUMP`.
- Use it when you want a clean baseline, not for preserving in-progress DB changes.

Default run:
```bash
./scripts/dct-bootstrap
```

Confirmation bypass (for automation/non-interactive use):
```bash
./scripts/dct-bootstrap --yes
```

With explicit seed:
```bash
SEED_DUMP=seeds/latest.sql.gz ./scripts/dct-bootstrap
```

What it does:
1. Ensures `.env.test` exists (creates from `.env.test.example` when needed)
2. Initializes `dmoj/repo` submodule
3. Syncs runtime config files into submodule
4. Ensures test certs exist (mkcert if available, else openssl)
5. Runs preflight checks
6. Runs `test-bootstrap`
7. Runs `compilemessages`, `compilejsi18n`, `collectstatic`
8. Runs `test-verify`
9. Runs host-header probe

## Start/Stop Without Losing State
If you want to pause and resume from same state:
```bash
./scripts/dct stop
./scripts/dct start
```

Notes:
- `stop/start` preserves data and containers.
- `down` removes containers/network.
- `down -v` removes named volumes as well, so persisted DB/cache data is deleted.
- `start` only works when containers already exist in stopped state; after `down`, use `up -d`.

What `-v` means:
- In `docker compose down -v`, `-v` means "remove volumes".
- In this stack, that wipes persisted test data and you will need bootstrap/reseed again.

## Quick Flag Reference
Use these often with `dct`.

- `up -d`: start in detached/background mode.
- `down`: stop and remove containers + project network, keep volumes.
- `down -v`: stop/remove containers + network + named volumes (destructive data reset).
- `stop`: stop containers only, keep everything for fast resume.
- `start`: start previously stopped containers from same state.
- `logs -f <service>`: follow live logs for a service.
- `ps`: show container status.
- `exec <service> <cmd>`: run a command inside a running service container.

Important clarification:
- `-v` is the correct flag for volume removal on `down`.
- `-f` is commonly used for compose file selection (`docker compose -f ...`), not volume deletion.

## When To Use Which Command
1. First setup: `dct bootstrap`
2. Daily start: `./scripts/dct up -d` or `./scripts/dct start`
3. Daily stop: `./scripts/dct stop`
4. Full teardown: `./scripts/dct down`
5. Destructive teardown: `./scripts/dct down -v`

## Step-by-Step Refactor Testing
Run this after each refactor step.

Step A: command wiring
```bash
dct --help
dct bootstrap --help
dct verify
```

Step B: compose compatibility
```bash
dct ps
dct config >/tmp/dct_config.out && echo OK
dct compose ps
```

Step C: lifecycle without data loss
```bash
dct stop
dct start
dct ps
```
