# Keycloak Authentication for DMOJ: Test-First Delivery Plan

## Purpose

Add Keycloak-based OpenID Connect (OIDC) login to the public DMOJ service, while first proving the complete flow in the isolated local DMOJ test stack.

Platform repository, layering, and runtime boundaries are defined in [Platform Decisions](../architecture/decisions.md).

Headscale is explicitly outside this plan. It may later use a separate Keycloak OIDC client in the same realm.

## Decisions and Boundaries

- DMOJ remains publicly reachable; Keycloak authenticates browser users.
- Keycloak uses a dedicated MariaDB database and database user. It does not share the DMOJ database or credentials.
- The local test deployment is isolated under the existing `dmoj-test` Compose project.
- Local Keycloak accounts are manually provisioned. No SMTP, email-password login, email verification, or email-based DMOJ account linking is introduced by this plan.
- DMOJ uses the OIDC `iss` + `sub` claims as the stable external identity. Email, if requested at all, is only profile data and must not decide account linkage.
- Keep DMOJ local username/password login enabled during the test rollout and initial production rollout.
- Pin Keycloak and MariaDB image versions. Do not use `latest` or mutable tags.

## Target Test Architecture

```text
Browser
  |
  +-- https://code.test.local  -> DMOJ nginx -> DMOJ Django
  |
  +-- https://auth.test.local  -> test nginx -> Keycloak
                                      |
                                      +-> keycloak-db (dedicated MariaDB)
```

DMOJ callback URL:

```text
https://code.test.local/complete/openidconnect/
```

The final public deployment will use separate public names for DMOJ and Keycloak. Do not add its production hostname, TLS certificates, or credentials in any test phase.

## Proposed File Layout

```text
dmoj/
  docker-compose.keycloak.test.yml
  environment/
    keycloak.test.env.example
  keycloak/
    test/
      realm-dmoj-test.json
      nginx.conf
      README.md
  scripts/teststack/
    dct/
    keycloak/
      keycloak-main.sh
      keycloak-doctor.sh
```

The `keycloak/` directory contains test-only identity-provider configuration. Runtime data, local override environment files, and TLS private keys remain ignored.

## Secret Policy

Commit only values that are safe to disclose and disposable, such as test hostnames, database names, realm metadata, and a realm export with the client secret omitted or replaced by a documented placeholder.

Do not commit any of the following, even for the local test stack:

- Keycloak admin password
- OIDC client secret
- MariaDB password
- DMOJ `SECRET_KEY`
- TLS private key

Use ignored files such as `environment/keycloak.test.env` and `keycloak/test/realm-dmoj-test.local.json`. Commit matching `.example` files. This preserves one-command setup without storing credentials permanently in Git history.

## dct Command Design

Extend the existing `dct` interface rather than adding another top-level command:

```bash
dct keycloak doctor
dct keycloak bootstrap --yes
dct keycloak up -d
dct keycloak down
dct keycloak down -v --yes
dct keycloak status
dct keycloak logs -f
dct keycloak verify
```

Expected behavior:

- `doctor` checks test hosts, certificates, the local Keycloak env file, required Compose files, and Docker/Compose availability.
- `bootstrap` creates a local env file from its example when absent, starts MariaDB and Keycloak, and imports the disposable test realm once.
- `up`, `down`, `status`, and `logs` operate only on Keycloak services plus their dedicated database.
- `down -v` follows the existing `dct` confirmation/`--yes` convention and removes only Keycloak test volumes.
- `verify` checks OIDC discovery, Keycloak readiness, and that the configured issuer exactly matches the external test URL.
- DMOJ lifecycle commands stay usable without Keycloak until the DMOJ integration phase. After integration, `dct bootstrap` and `dct verify` should report an actionable warning when OIDC test configuration is enabled but Keycloak is unavailable.

## Delivery Phases

Each phase is an independent commit. Do not combine a phase with opportunistic refactors.

### Phase 0: Planning and Repository Guardrails

Commit scope:

- This document.
- `.gitignore` entries for local Keycloak test runtime state, env overrides, realm exports containing secrets, and TLS private keys.
- `keycloak/test/README.md` describing the local-only boundary and required host entries.

Manual test:

```bash
git check-ignore dmoj/environment/keycloak.test.env
git check-ignore dmoj/keycloak/test/realm-dmoj-test.local.json
git status --short
```

Expected result: local secret/runtime files are ignored; no real secret appears in `git status`.

### Phase 1: Dedicated Keycloak MariaDB

Commit scope:

- `docker-compose.keycloak.test.yml` with a `keycloak-db` service and named volume.
- A MariaDB initialization mechanism that creates only a dedicated Keycloak database and database user.
- `environment/keycloak.test.env.example` containing non-secret names and placeholder passwords.
- Database health check and explicit resource limits.

Manual test:

```bash
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test config >/tmp/dmoj-keycloak-rendered.yml
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test up -d keycloak-db
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test exec -T keycloak-db mariadb-admin ping -u root -p"$KEYCLOAK_DB_ROOT_PASSWORD"
```

Expected result: `keycloak-db` is healthy; DMOJ's `db` service and its database remain untouched.

### Phase 2: Keycloak Service and Local HTTPS Routing

Commit scope:

- Pinned Keycloak service, network attachment, health check, and resource limits.
- Test Nginx route for `auth.test.local` to Keycloak.
- Test certificate generation/documentation covering both `code.test.local` and `auth.test.local`.
- No DMOJ authentication changes.

Manual test:

```bash
sudo sh -c 'printf "127.0.0.1 code.test.local auth.test.local\n" >> /etc/hosts'
docker compose --env-file environment/keycloak.test.env \
  -f docker-compose.yml -f docker-compose.test.yml -f docker-compose.keycloak.test.yml \
  -p dmoj-test up -d keycloak-db keycloak nginx
curl --fail --cacert nginx/certs/test/code.test.local.crt \
  https://auth.test.local/realms/master/.well-known/openid-configuration
```

Expected result: discovery returns JSON with an issuer beginning `https://auth.test.local/`. Validate the Keycloak admin console separately in a browser.

Note: `auth.test.local` must be included in the certificate SAN. The test Nginx configuration must route by `Host`, not replace the DMOJ virtual host.

### Phase 3: Reproducible Realm and Manual Test Users

Commit scope:

- Sanitized `realm-dmoj-test.json` defining the `dmoj-test` realm.
- A confidential `dmoj-web` OIDC client with exact local redirect URI.
- Manual test user definitions or a documented admin-console procedure.
- Realm import automation that never overwrites a real/previously configured realm unintentionally.

Manual test:

```bash
dct keycloak bootstrap --yes
dct keycloak verify
```

Browser test:

1. Open the Keycloak admin console at `auth.test.local`.
2. Confirm the `dmoj-test` realm and `dmoj-web` client exist.
3. Sign in with the manually provisioned test user.
4. Confirm the client permits only `https://code.test.local/complete/openidconnect/` as its callback.

Expected result: realm import is repeatable; no public domain or production credentials are present.

### Phase 4: dct Keycloak Lifecycle Commands

Commit scope:

- `scripts/teststack/keycloak/` helpers.
- `dct keycloak` subcommand dispatch.
- `doctor`, `bootstrap`, `up`, `down`, `status`, `logs`, and `verify` behavior.
- Focused command documentation.

Manual test:

```bash
dct keycloak doctor
dct keycloak up -d
dct keycloak status
dct keycloak verify
dct keycloak down
dct keycloak up -d
dct keycloak down -v --yes
dct keycloak bootstrap --yes
```

Expected result: ordinary stop/start preserves Keycloak state; `down -v --yes` resets only Keycloak state; DMOJ containers and volumes are not removed.

### Phase 5: DMOJ OIDC Configuration and Identity Model

Commit scope:

- Test-only DMOJ OIDC settings loaded from ignored local env configuration.
- Add `social_core.backends.open_id_connect.OpenIdConnectAuth` to DMOJ authentication backends.
- Configure issuer, client ID, client secret, and scopes (`openid profile`).
- Replace automatic `associate_by_email` for this provider with an explicit `iss` + `sub` association policy.
- Define first-login behavior: either deny unless an administrator pre-links the subject, or create a restricted DMOJ profile pending staff approval. Choose and document one; do not silently auto-link accounts by email.

Required DMOJ integration changes:

1. [dmoj/repo/dmoj/settings.py](../../dmoj/repo/dmoj/settings.py): register the OIDC backend and provider-specific pipeline.
2. [dmoj/repo/dmoj/local_settings.py](../../dmoj/repo/dmoj/local_settings.py): read test OIDC variables; do not commit secrets.
3. [dmoj/repo/judge/social_auth.py](../../dmoj/repo/judge/social_auth.py): add provider-specific subject validation/linking logic.
4. [dmoj/repo/templates/registration/login.html](../../dmoj/repo/templates/registration/login.html): add a Keycloak login action, retaining local login.
5. DMOJ site image/dependencies: verify that the installed pinned `social-auth-core` exposes the generic OIDC backend. Add a pinned dependency only if verification proves it is absent.

Manual test:

```bash
dct keycloak up -d
dct up -d
dct verify
```

Browser test:

1. Open `https://code.test.local/accounts/login/`.
2. Select Keycloak login.
3. Authenticate with the manually provisioned user.
4. Confirm the callback succeeds and the expected DMOJ account policy is applied.
5. Confirm a different, unlinked Keycloak user is denied or held pending approval as documented.
6. Confirm local DMOJ username/password login still works.

Expected result: account identity is bound to issuer and subject, not an editable email address.

### Phase 6: Logout, Failure Handling, and Regression Checks

Commit scope:

- DMOJ local logout behavior documented and tested.
- Optional Keycloak single logout only if it behaves reliably with the pinned versions; otherwise retain local DMOJ logout and document the session boundary.
- Verification commands that report Keycloak discovery failures separately from DMOJ failures.
- Regression checklist/script for existing `dct up`, `dct down`, `dct bootstrap`, and `dct verify` flows without Keycloak.

Manual test:

```bash
dct keycloak verify
dct verify
dct stop
dct start
dct verify
dct keycloak down
dct verify
```

Browser test:

1. Test success, denied login, cancelled login, expired Keycloak session, and DMOJ logout.
2. Confirm unavailable Keycloak produces a clear DMOJ login failure without breaking anonymous DMOJ browsing.
3. Confirm original DMOJ test-stack lifecycle remains functional when Keycloak is down.

### Phase 7: Production Readiness Review (No Production Deployment)

Commit scope:

- A production checklist only; no production Compose changes.
- Version pin/update policy, backups/restores, TLS/reverse-proxy design, Keycloak resource limits, monitoring, and admin-recovery procedure.
- Separate production secret-management and realm-import procedure.

Manual review:

1. Restore the Keycloak MariaDB test database into a disposable environment.
2. Prove a realm export/import recovery.
3. Confirm exact public issuer and redirect URLs will be used before creating production credentials.
4. Require an explicit follow-up decision before any production deployment work.

## Additional Recommendations

- Use a separate `docker-compose.keycloak.test.yml` overlay rather than adding Keycloak to the ordinary test overlay. This keeps current DMOJ test bootstrap fast and unchanged when auth testing is not needed.
- Keep Keycloak on an internal Docker network; publish only the test Nginx HTTPS port. Do not publish Keycloak's management port publicly.
- Add health checks for MariaDB, Keycloak, OIDC discovery, and the DMOJ login callback independently. A running container is not proof of a usable OIDC flow.
- Configure explicit container memory limits and monitor them. Keycloak is resource-heavy compared with DMOJ helper services.
- Back up and test restore of the dedicated Keycloak database before treating it as authentication infrastructure.
- Record Keycloak image and database schema upgrade steps. Identity-provider upgrades should be planned, reversible operations.

## Handoff Checklist

Before starting any phase, verify:

```bash
git status --short
cd dmoj
source ./scripts/teststack/dct/dct-init
dct doctor
```

After each phase:

```bash
git diff --check
git status --short
git add <only-phase-files>
git commit -m "keycloak: <phase outcome>"
```

Do not mix DMOJ public-domain changes, Headscale setup, or production secrets into these commits.