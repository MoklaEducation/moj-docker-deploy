# Keycloak for DMOJ: Phase Progress Log

This document tracks implementation progress for the isolated local Keycloak test work described in [keycloak_dmoj_test_plan.md](keycloak_dmoj_test_plan.md).

## Current status

- Current phase: Phase 3
- Phase 0 status: committed
- Phase 1 status: completed
- Phase 2 status: completed
- Phase 3 status: in progress
- Working assumption: local Keycloak integration is being developed in a dedicated test-only overlay and isolated database, without affecting the main DMOJ database or production naming.

---

## Phase 0: Planning and Repository Guardrails

Status: committed

Scope:
- Add the Keycloak-specific .gitignore rules for local runtime files, secrets, and TLS assets.
- Add the local-only Keycloak test directory with documentation.
- Keep the local auth test stack isolated from committed repo contents.

Implementation notes:
- The repository now ignores local Keycloak env files such as `dmoj/environment/keycloak.test.env`.
- Local realm exports matching `keycloak/test/*.local.json` are ignored.
- Local TLS private keys and certificate artifacts used for local testing are kept out of version control.
- A README under `dmoj/keycloak/test/` documents the local-only boundary and the required hosts entry.

Verification checklist:
- Command: `git check-ignore dmoj/environment/keycloak.test.env`
- Command: `git check-ignore dmoj/keycloak/test/realm-dmoj-test.local.json`
- Command: `git status --short`
- Expected result: local secret/runtime files do not appear in tracked status output.
- Manual review: confirm no real password, secret, or private key is present in committed files.

Exit criteria for phase completion:
- Secret-bearing local files are ignored.
- Test-only docs are present and explicitly state the local-only boundary.
- No real credentials are stored in committed repository files.

---

## Phase 1: Dedicated Keycloak MariaDB

Status: completed

Scope:
- Add a dedicated `keycloak-db` MariaDB service in a dedicated Keycloak compose overlay.
- Keep the Keycloak database isolated from the existing DMOJ database.
- Add example env values for a dedicated database name, user, and passwords.
- Ensure a health check and resource limits are present for the dedicated database service.

Implementation notes:
- New overlay file: `dmoj/docker-compose.keycloak.test.yml`
- Example env file: `dmoj/environment/keycloak.test.env.example`
- The new database uses a dedicated volume and is separated from the main `db` service.
- The database is intentionally configured with placeholder values in the example file; real secrets remain local-only.
- Setup requirement: create a local file at `dmoj/environment/keycloak.test.env` from the example before running commands. The repo intentionally does not commit this file. The root password must match the value used when the container was created.

Verification checklist:

```bash
cd /home/ubuntu/repo/test-medocker-moj-004/moj-docker-deploy/dmoj
cp environment/keycloak.test.env.example environment/keycloak.test.env

# Render the merged stack to verify the overlay is valid
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test config

# Start only the dedicated Keycloak database
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test up -d keycloak-db

# Confirm the MariaDB service responds to admin ping
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test exec -T keycloak-db mariadb-admin ping -u root -p"$KEYCLOAK_DB_ROOT_PASSWORD"
```

Expected result: Compose render succeeds without schema or merge errors; the `keycloak-db` container starts and reaches a healthy state; MariaDB responds successfully.

Manual check: verify the DMOJ `db` service remains unrelated and unchanged.

Exit criteria for phase completion:
- `keycloak-db` runs in a dedicated Compose service and volume.
- The service is healthy and reachable with its own credentials.
- No DMOJ production or test DB data is shared with the Keycloak DB.
- Local env values are not committed.

Optional reset / rebuild commands:

```bash
cd /home/ubuntu/repo/test-medocker-moj-004/moj-docker-deploy/dmoj

# Stop and remove the Keycloak test stack, leaving the main DMOJ services intact
# (this only targets the Keycloak-specific project name and services)
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test down

# Remove the dedicated Keycloak DB volume to begin from an empty local state
docker volume rm dmoj-test_keycloak-db-data

# Recreate from scratch
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test up -d keycloak-db
```

Note: if the DB password was changed manually in the container or env file, the recreated environment must use matching values or the database will reject the root access check. The safest reset is to recreate the local env file from the example and then recreate the container stack.

---

## Phase 2: Keycloak Service and Local HTTPS Routing

Status: completed

Scope:
- Add the Keycloak service itself, pinned image version, health checks, and network configuration.
- Route `auth.test.local` through the local test Nginx setup.
- Generate or document test certificates covering both `code.test.local` and `auth.test.local`.
- Ensure no DMOJ auth logic changes yet.

Things to verify:
- Command: `docker compose --env-file environment/keycloak.test.env -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml -p dmoj-test up -d keycloak-db keycloak nginx`
- Command: `curl --fail --cacert nginx/certs/test/code.test.local.crt https://auth.test.local/realms/master/.well-known/openid-configuration`
- Expected result: JSON discovery document is returned and contains an issuer beginning with `https://auth.test.local/`.
- Manual check: open the Keycloak admin console via the browser and confirm it loads correctly.
- Manual check: confirm `auth.test.local` is included in the certificate SAN and not just the DMOJ host.

Exit criteria for phase completion:
- Local HTTPS routing to Keycloak works from the browser.
- The OIDC discovery endpoint is reachable and issuer matches the test URL exactly.
- DMOJ remains unchanged and unaffected by the Keycloak-only service.

Troubleshooting note:
- Initial failure: the discovery request returned `502` and the browser/curl seen `SSL: no alternative certificate subject name matches target host name` before the route was corrected.
- Root cause 1: the test certificate only covered `code.test.local`; `auth.test.local` was missing from the certificate SAN, so TLS validation failed before nginx could route the request.
- Root cause 2: the original Keycloak startup command used the unsupported `--proxy` flag for Keycloak 26. The container exited during startup with `Unknown option: '--proxy'`.
- Root cause 3: the container health check used `wget`, which is not installed in the Keycloak image, causing the service to look unhealthy even after the process had started successfully.
- Fix applied: regenerate the local TLS cert with SAN entries for both `code.test.local` and `auth.test.local`, replace the invalid `--proxy` flag with the supported `--proxy-headers` and `--proxy-trusted-addresses` settings, and replace the health probe with a bash socket check using `/dev/tcp` inside the container.
- Validation result: `curl --fail --silent --show-error --cacert nginx/certs/test/code.test.local.crt --resolve auth.test.local:443:127.0.0.1 https://auth.test.local/realms/master/.well-known/openid-configuration` now returns the Keycloak discovery JSON, including the issuer `https://auth.test.local/realms/master`.

---

## Phase 3: Reproducible Realm and Manual Test Users

Status: completed

Scope:
- Add a sanitized `realm-dmoj-test.json` file.
- Define a confidential OIDC client for DMOJ.
- Add manual test users or clear admin-console instructions.
- Ensure realm import automation won't overwrite a real or previously configured realm accidentally.

Implementation notes:
- `dmoj/keycloak/test/realm-dmoj-test.json` defines the local `dmoj-test` realm and `dmoj-web` confidential client.
- The client permits only `https://code.test.local/complete/openidconnect/` as its redirect URI.
- The Keycloak overlay mounts the sanitized realm file read-only and starts with `--import-realm`.
- Existing realms are not overwritten by the import; disposable users are created manually in the admin console so passwords remain local-only.
- The client secret remains a placeholder until it is replaced in the local Keycloak console or a future ignored local override is added.

Things to verify:
- Command: `docker compose ... up -d keycloak`
- Manual check: open the admin console and confirm the `dmoj-test` realm is present.
- Manual check: confirm the `dmoj-web` client exists and the redirect URI matches the local DMOJ callback.
- Manual check: confirm a sample local user can log in to Keycloak directly and is recognized as a valid OIDC user.

Exit criteria for phase completion:
- Test realm and client are reproducible and not dependent on a manual hidden state.
- Test users are known, disposable, and documented.
- Importing the realm is safe and does not overwrite real data.

Manual test-user procedure and console distinction:
- The Keycloak administrator console is `https://auth.test.local/admin/`. Sign in here with the `master` realm admin account (`KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD`). The `dmoj-test` user is not an administrator and cannot sign in to this console.
- In the admin console, select the `dmoj-test` realm, open **Users**, and create the disposable test user.
- Under the new user's **Credentials** tab, set a password and disable **Temporary** if the user should log in without being forced to change it. Creating the user and setting this password are required before testing authentication.
- The `dmoj-test` user's account console is `https://auth.test.local/realms/dmoj-test/account/`. Use the test user's username and password there, or through the DMOJ OIDC login once Phase 4 is implemented.
- The DMOJ application login is separate and is not expected to work until the Phase 4 OIDC integration is complete.
- Keep the test user's password and any generated client secret out of Git.

---

## Phase 4: Keycloak Lifecycle Commands

Status: in progress

Scope:
- Add the `dct keycloak` lifecycle command family.
- Keep Keycloak database and service operations separate from ordinary DMOJ lifecycle commands.
- Provide diagnostics, bootstrap, status, logs, and OIDC discovery verification.

Implementation notes:
- New wrapper: `dmoj/scripts/teststack/keycloak-main.sh`.
- Keycloak commands use `environment/keycloak.test.env` by default and can be pointed at another test env with `KEYCLOAK_ENV_FILE`.
- `dct keycloak down` removes only the Keycloak containers; it does not stop or remove DMOJ services.
- `dct keycloak down -v --yes` removes only the dedicated `${PROJECT_NAME}_keycloak-db-data` volume.
- `dct keycloak bootstrap --yes` creates the ignored local env file from the example when absent, starts Keycloak, verifies the external issuer, and creates or updates the disposable test user from local env values.
- `KEYCLOAK_TEST_USER` and `KEYCLOAK_TEST_USER_PASSWORD` belong only in the ignored `environment/keycloak.test.env`; the user password is not stored in the realm export.
- `KEYCLOAK_TEST_USER_EMAIL`, `KEYCLOAK_TEST_USER_FIRST_NAME`, and `KEYCLOAK_TEST_USER_LAST_NAME` are also read from the ignored env file and applied during bootstrap, so first login does not require profile completion.
- Existing local env files created before this automation must be updated with the five test-user variables before running `dct keycloak bootstrap --yes`.

Things to verify:

```bash
cd /home/ubuntu/repo/test-medocker-moj-004/moj-docker-deploy/dmoj
source ./scripts/teststack/dct/dct-init
dct keycloak doctor
dct keycloak up -d
dct keycloak status
dct keycloak verify
dct keycloak logs
dct keycloak down
dct keycloak up -d
dct keycloak down -v --yes
dct keycloak bootstrap --yes
```

Expected result: ordinary stop/start preserves Keycloak state; `down -v --yes` resets only Keycloak state; DMOJ containers and volumes remain present; `verify` confirms the issuer `https://auth.test.local/realms/master`.

Manual check: run `dct status` before and after Keycloak teardown and confirm the DMOJ services remain available.

Manual test-user password reset:

```bash
cd /home/ubuntu/repo/test-medocker-moj-004/moj-docker-deploy/dmoj
set -a
source environment/keycloak.test.env
set +a

docker compose \
  --env-file environment/keycloak.test.env \
  -f docker-compose.yml \
  -f docker-compose.test.yml \
  -f docker-compose.keycloak.test.yml \
  -p dmoj-test exec -T keycloak \
  /opt/keycloak/bin/kcadm.sh set-password \
  -r dmoj-test \
  --username "$KEYCLOAK_TEST_USER" \
  --new-password "$KEYCLOAK_TEST_USER_PASSWORD"
```

Caveat: run this only after `dct keycloak status` shows `keycloak` as healthy. The Keycloak database credentials in `environment/keycloak.test.env` must match the credentials used when the `dmoj-test_keycloak-db-data` volume was initialized. If they do not match, reset the disposable Keycloak stack first with `dct keycloak down -v --yes`, then run `dct keycloak bootstrap --yes`.

Exit criteria for phase completion:
- Keycloak lifecycle commands are available through `dct`.
- Keycloak reset operations cannot remove DMOJ services or volumes.
- Discovery verification reports a usable Keycloak endpoint and exact issuer.

## Phase 5: DMOJ OIDC Integration

Status: pending

Scope:
- Add the OIDC login action to the DMOJ login flow.
- Retain local username/password login.
- Confirm that Keycloak users can log in without breaking the existing local auth flow.

Things to verify:
- Manual browser test: local DMOJ login page exposes the Keycloak login option.
- Manual browser test: successful Keycloak login completes the DMOJ callback.
- Manual browser test: denied or unlinked user flows fail gracefully.
- Manual browser test: logout behavior is still acceptable and clearly documented.

Exit criteria for phase completion:
- OIDC login works end-to-end in the test stack.
- Existing DMOJ login remains functional.
- Keycloak is not required for anonymous browsing or existing local login flows.

---

## Phase 5: Hardened Verification and Regression Coverage

Status: pending

Scope:
- Add final verification commands for Keycloak availability and DMOJ behavior.
- Ensure faulty Keycloak configuration reports actionable errors without breaking ordinary DMOJ usage.
- Run regression checks for standard DMOJ lifecycle commands.

Things to verify:
- Command: `dct keycloak verify`
- Command: `dct keycloak doctor`
- Command: `dct keycloak status`
- Command: `dct bootstrap` / `dct verify` when Keycloak is unavailable
- Manual check: DMOJ test-stack baseline still works when Keycloak is down.

Exit criteria for phase completion:
- Keycloak health checks are explicit and actionable.
- DMOJ baseline usability remains intact.
- End-to-end test and regression confidence is documented.

---

## Notes for future work

- Keep all runtime env files, realm exports, and local secrets out of Git.
- Prefer committed `.example` files and explicit local copy steps.
- Keep phase boundaries separate and avoid combining unrelated fixes into the same commit.
- Use this document as the official checkpoint log, updating it as each phase progresses or completes.
