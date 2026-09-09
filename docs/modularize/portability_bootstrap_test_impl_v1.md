# Portability Bootstrap Test Implementation v1

## Goal
Provide one consistent process to seed and start the isolated test stack on any new machine, based on issues encountered during first execution.

Reference:
- portability_bootstrap_v1.md

## What We Hit and What Fixed It
1. .env.test missing
- Symptom: test scripts failed immediately.
- Fix: create dmoj/.env.test from .env.test.example.

2. Test TLS certs missing in expected path
- Symptom: test-bootstrap failed with "Missing test TLS certificate files in nginx/certs/test".
- Fix: generate cert/key under dmoj/nginx/certs/test.

3. dmoj/repo submodule not initialized
- Symptom: Docker build failed at COPY repo/requirements.txt.
- Fix: initialize submodule with git submodule update --init --recursive dmoj/repo.
- Note: do not run unscoped git submodule update --init --recursive in this repo state, because it fails on nginx/mokla-site not being declared in .gitmodules.

4. Runtime config files missing in submodule
- Symptom: service startup risk due to missing project config files.
- Fix: copy local_settings.py, config.js, uwsgi.ini into dmoj/repo.

5. test-verify originally showed HTTP 400 on raw IP probe (resolved)
- Symptom: endpoint probe in test-verify returned HTTP/1.1 400 Bad Request.
- Cause: probe used 127.0.0.1 without expected host header; Django host policy rejected it.
- Fix: test-verify now probes HTTPS with configured host header (DMOJ_TEST_HOST).

6. Host-header probe exposed missing static i18n artifact
- Symptom: Host-header probe returned HTTP 500; site log showed missing /assets/static/jsi18n/en/djangojs.js.
- Fix: run compilemessages, compilejsi18n, then collectstatic.

## Tooling for New Machines
Required:
1. Docker Engine
2. Docker Compose plugin
3. Git
4. OpenSSL
5. curl

Recommended:
1. mkcert
2. libnss3-tools

Ubuntu install:
```bash
sudo apt-get update
sudo apt-get install -y git openssl curl ca-certificates libnss3-tools mkcert
```

Verify:
```bash
docker --version
docker compose version
git --version
openssl version
curl --version
mkcert --version
```

## New Machine Procedure
Run all commands from moj-docker-deploy/dmoj unless a step says otherwise.

### Step 1: Enter working directory
```bash
cd /path/to/moj-docker-deploy/dmoj
```
Expectation:
- pwd ends with /moj-docker-deploy/dmoj.

### Step 2: Initialize mkcert trust (recommended)
```bash
mkcert -install
```
Expectation:
- local CA install completes without error.

### Step 3: Generate test TLS certs
```bash
cd nginx/certs/test
mkcert -cert-file code.test.local.crt -key-file code.test.local.key code.test.local
cd ../..
ls -l nginx/certs/test/code.test.local.crt nginx/certs/test/code.test.local.key
```
Expectation:
- both files exist in nginx/certs/test.

### Step 4: Create env file
```bash
cp .env.test.example .env.test
```
Expectation:
- dmoj/.env.test exists.

### Step 5: Validate compose render
```bash
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test config >/tmp/dmoj_test_rendered.yml && echo VALID
```
Expectation:
- command prints VALID.

### Step 6: Initialize online-judge submodule
Run from moj-docker-deploy/dmoj using a root-scoped git command.
```bash
git -C .. submodule update --init --recursive dmoj/repo
```
Expectation:
- dmoj/repo populated, including dmoj/repo/resources/libs.

### Step 7: Copy required runtime config files
```bash
cp ../local_settings.py repo/dmoj/local_settings.py
cp ../config.js repo/websocket/config.js
cp ../uwsgi.ini repo/uwsgi.ini
```
Expectation:
- all copy commands succeed.

### Step 8: Preflight required files
```bash
for f in repo/requirements.txt repo/dmoj/local_settings.py repo/websocket/config.js repo/uwsgi.ini; do
  if [ -f "$f" ]; then
    echo "OK $f"
  else
    echo "MISSING $f"
  fi
done
```
Expectation:
- all lines print OK.

### Step 9: Start and seed
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test SEED_DUMP=seeds/latest.sql.gz ./scripts/test-bootstrap
```
Expectation:
- exits with code 0.

Important:
- Re-running bootstrap re-imports seed data and resets test DB state.
- Use bootstrap for first-run/reset scenarios, not for day-to-day resume.

What this command does:
- PROJECT_NAME=dmoj-test: isolates containers/networks/volumes under a test-only compose project name.
- ENV_FILE=.env.test: forces test ports/host settings from the test env file.
- SEED_DUMP=seeds/latest.sql.gz: tells seed import which SQL dump to load.
- ./scripts/test-bootstrap: orchestrates startup + DB import + migrate + style/static build + verify.

### Step 9a: Do I always need this exact command?
Short answer:
- On a new machine or after destructive cleanup: yes, use test-bootstrap.
- For normal restarts of an already-seeded stack: no, you can use test-up or docker compose up.

Use test-bootstrap when:
1. First run on a machine.
2. You ran test-down with REMOVE_VOLUMES=1.
3. You changed or replaced the seed dump.
4. You want a known reset from seed state.

Use test-up (or docker compose up) when:
1. Data volumes already exist and you just want services running.
2. You are iterating on app/container behavior without reseeding DB.

Preferred restart command in this repo (keeps test overlay and checks):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/test-up
```

Direct compose equivalent:
```bash
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test up -d
```

Important:
- Plain docker compose up without test flags can start the wrong project/ports and bypass test isolation.

### Step 10: Verify stack
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/test-verify
```
Expectation:
- script exits with code 0.
- endpoint probe should return HTTP 200 or 302 when stack is healthy.

### Step 11: Verify with host header (real app check)
```bash
HTTPS_PORT="$(grep '^DMOJ_TEST_HTTPS_PORT=' .env.test | cut -d= -f2)"
HTTPS_PORT="${HTTPS_PORT:-8443}"
curl -kI -H 'Host: code.test.local' "https://127.0.0.1:${HTTPS_PORT}/"
```
Expectation:
- preferred: HTTP 200 or HTTP 302.
- if HTTP 500, run Step 12.

### Step 12: Fix missing i18n/static artifacts (only if Step 11 is 500)
```bash
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test exec -T site python3 manage.py compilemessages
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test exec -T site python3 manage.py compilejsi18n
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test exec -T site python3 manage.py collectstatic --noinput
```
Re-check Step 11.

## Teardown
Stop and remove containers/network:
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/test-down
```

Also remove volumes (destructive, test-only):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test REMOVE_VOLUMES=1 ./scripts/test-down
```

`-v` meaning in direct compose usage:
- `docker compose ... down -v` removes named volumes.
- Removing volumes deletes persisted DB/cache data and usually requires bootstrap/reseed next start.

## First-Machine Validation Snapshot (2026-09-08)
1. Tooling installed and verified.
2. Step 9 (test-bootstrap) completed with exit code 0 after prerequisite fixes.
3. Step 10 (test-verify) completed with exit code 0.
4. Raw-IP probe showed HTTP 400 as expected under current host policy.
5. Host-header probe is the authoritative app-health check.
6. After compilemessages + compilejsi18n + collectstatic, host-header probe returned HTTP/1.1 200 OK.
