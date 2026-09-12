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
