# dct and dct-bootstrap Usage

## Purpose
Provide docker compose-like commands for the test stack without repeating long flags, while preserving test isolation.

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

## dct: Compose-Compatible Daily Wrapper
`dct` forwards all arguments to docker compose with test flags injected.

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
- If required files are missing, it exits with a clear message and asks you to run `./scripts/dct-bootstrap`.

## dct-bootstrap: First-Run / Reset Wrapper
Use `dct-bootstrap` on:
1. New machine
2. Fresh clone
3. After destructive reset
4. Any time you want a known seeded baseline

Default run:
```bash
./scripts/dct-bootstrap
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
- `down -v` also removes named volumes.

## When To Use Which Command
1. First setup: `./scripts/dct-bootstrap`
2. Daily start: `./scripts/dct up -d` or `./scripts/dct start`
3. Daily stop: `./scripts/dct stop`
4. Full teardown: `./scripts/dct down`
5. Destructive teardown: `./scripts/dct down -v`
