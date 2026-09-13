# Keycloak test-only configuration

This directory is reserved for local, disposable Keycloak integration testing for the DMOJ test stack.

## Local-only boundary

- This configuration is for the isolated local test deployment only.
- Do not add production Keycloak hostnames, client secrets, realms, or certificates here.
- Keep all runtime secrets out of source control.
- Only commit sanitized example files or non-secret placeholders.

## Required hosts

Add the following entries to the local machine's hosts file so the test stack resolves the DMOJ and Keycloak endpoints correctly:

```text
127.0.0.1 code.test.local auth.test.local
```

## Files that must remain ignored

The following local runtime or secret files must never be committed:

- `environment/keycloak.test.env`
- `keycloak/test/*.local.json`
- `keycloak/test/*.key`
- `keycloak/test/*.crt`
- `keycloak/test/*.pem`
- any exported realm JSON containing real secrets or credentials

## Safety rules

- Keep `auth.test.local` separate from the public production hostname.
- Do not commit the admin password, client secret, MariaDB password, or TLS private key.
- Treat the realm and database as disposable and rebuildable for local testing.
- When a local secret file is needed, create it from a committed example and keep it outside Git history.

## Test realm and client

`realm-dmoj-test.json` is a sanitized Keycloak import for the local `dmoj-test` realm. It defines the confidential `dmoj-web` client with this exact callback:

```text
https://code.test.local/complete/openidconnect/
```

The client secret is intentionally a placeholder. Replace it in the Keycloak admin console before using the client from DMOJ. Keycloak imports this realm at startup only when it does not already exist; it does not overwrite an existing realm.

## Create a disposable test user

After the Keycloak service is healthy:

1. Open `https://auth.test.local/admin/` and sign in with the local admin credentials.
2. Select the `dmoj-test` realm from the realm menu.
3. Open **Users**, choose **Add user**, and create a disposable username.
4. Open the user's **Credentials** tab, set a password, and turn off **Temporary** if the user should log in without changing it.
5. Use that user only for local integration tests; do not export its password into Git.
