# Portability Bootstrap v1

## Goal
Safely run and test the DMOJ stack on a different machine using this repository branch, with seed data, while keeping production untouched.

## Scope
- Use test-only compose overlay and scripts from dmoj/.
- Use isolated compose project name and non-production ports.
- Bootstrap database using committed seed dump.

## Preconditions (New Machine)
1. Docker Engine and Docker Compose plugin installed.
2. Git installed.
3. This branch available on the machine:
   - portability_impl_v1
4. Host has enough disk for images + data.

## Safety Principles
1. Never run these commands in the production compose project path.
2. Always set a dedicated project name (default in scripts: dmoj-test).
3. Do not reuse production ports on shared hosts.
4. Keep test certificates separate from /etc/letsencrypt production paths.

## Files Used
- dmoj/docker-compose.yml
- dmoj/docker-compose.test.yml
- dmoj/.env.test.example
- dmoj/scripts/teststack/dct/dct
- dmoj/scripts/teststack/lifecycle/test-up
- dmoj/scripts/teststack/lifecycle/test-down
- dmoj/scripts/teststack/lifecycle/test-verify
- dmoj/scripts/teststack/seed/test-seed-import
- dmoj/scripts/teststack/lifecycle/test-bootstrap
- dmoj/seeds/latest.sql.gz
- dmoj/nginx/conf.d/nginx.test.conf
- dmoj/nginx/certs/test/README.md

## Step 1: Clone and checkout branch
```bash
git clone <your-repo-url>
cd moj-docker-deploy
git checkout portability_impl_v1
cd dmoj
```

## Step 2: Prepare test environment file
```bash
cp .env.test.example .env.test
```

Edit .env.test if needed:
- DMOJ_TEST_HOST (default: code.test.local)
- DMOJ_TEST_HTTPS_PORT (default: 8443)
- DMOJ_TEST_HTTP_PORT (default: 18081)
- DMOJ_TEST_BRIDGED_PORT (default: 19999)
- SEED_DUMP (default: seeds/latest.sql.gz)

## Step 3: Provision test TLS certificate
Preferred local-dev method (mkcert):
```bash
cd nginx/certs/test
mkcert -cert-file code.test.local.crt -key-file code.test.local.key code.test.local
cd ../..
```

Fallback (OpenSSL self-signed):
```bash
cd nginx/certs/test
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout code.test.local.key \
  -out code.test.local.crt \
  -subj "/CN=code.test.local" \
  -addext "subjectAltName=DNS:code.test.local"
cd ../..
```

Optional host mapping for browser access:
- Add code.test.local to hosts/DNS pointing to this test machine.

## Step 4: Validate rendered test stack config
```bash
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test config >/tmp/dmoj_test_rendered.yml && echo VALID
```

## Step 5: Bring up isolated test stack
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/teststack/lifecycle/test-up
```

## Step 6: Seed the test database
Option A (recommended one-command bootstrap):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test SEED_DUMP=seeds/latest.sql.gz ./scripts/teststack/lifecycle/test-bootstrap
```

Option B (manual seed import after stack is up):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test SEED_DUMP=seeds/latest.sql.gz RESET_DB_ON_IMPORT=1 ./scripts/teststack/seed/test-seed-import
```

## Step 7: Verify services
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/teststack/lifecycle/test-verify
```

Checkpoints:
1. docker compose ps shows services up.
2. HTTPS endpoint responds on configured test port (default 8443).
3. Seeded login/users/content are present.

## Step 8: Stop or teardown test stack
Stop and remove containers/network (keep volumes):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test ./scripts/teststack/lifecycle/test-down
```

Destructive teardown including volumes (test-only):
```bash
PROJECT_NAME=dmoj-test ENV_FILE=.env.test REMOVE_VOLUMES=1 ./scripts/teststack/lifecycle/test-down
```

## Troubleshooting
1. Missing cert error from test-up:
- Ensure both files exist:
  - nginx/certs/test/code.test.local.crt
  - nginx/certs/test/code.test.local.key

2. Port conflicts:
- Change DMOJ_TEST_HTTPS_PORT / DMOJ_TEST_HTTP_PORT / DMOJ_TEST_BRIDGED_PORT in .env.test.

3. Seed import failure:
- Confirm seed file exists at SEED_DUMP path.
- Run:
  - docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml -p dmoj-test logs db

## Non-Disruption Assurance
This workflow is isolated because:
1. It uses docker-compose.test.yml overrides.
2. It uses a separate compose project name (dmoj-test).
3. It uses non-production host ports by default.
4. It does not require editing production compose files or cert mount paths.
