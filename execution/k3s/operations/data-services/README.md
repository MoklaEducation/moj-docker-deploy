# Data-Service Operator Helper

Phase 3 separates service provisioning from service validation. MariaDB and Redis always
remain outside Kubernetes.

## Test Host: Optional Provisioning

Set `data_services.provisioning_mode: helper-managed` in the environment platform file.
Preview configuration and host changes without creating services:

```bash
./execution/k3s/operations/data-services/data-services check --environment test
```

Provision only after reviewing recovery access, current containers, target directories,
firewall rules, image scans, and the Ansible check output:

```bash
./execution/k3s/operations/data-services/data-services setup \
  --environment test --provision-host-services
```

The explicit flag is mandatory. Setup delegates to the existing ordered Ansible path,
including Phase 1 and Phase 2 prerequisites. It does not install services inside k3s.

## Production: Externally Managed Services

Set `data_services.provisioning_mode: external`, configure the private endpoint and
dedicated probe identities, and run only `check`. The local Compose, systemd, filesystem,
UFW, and backup role is skipped. Runtime validation still requires:

- a certificate chain trusted by the configured CA and valid for the endpoint IP;
- successful MariaDB authentication and `SELECT 1`;
- successful Redis authentication and `PING`; and
- no secret material in evidence or command output.

Use least-privilege external probe users through `probe_username` and
`probe_password_secret_key`. The corresponding values belong in SOPS.

## Temporary Secret Input

Create plaintext only as a restrictive temporary file outside Git:

```bash
TEMPORARY_SECRETS="$(mktemp --suffix=.yaml)"
chmod 0600 "$TEMPORARY_SECRETS"
${EDITOR:-vi} "$TEMPORARY_SECRETS"

./execution/k3s/operations/data-services/data-services encrypt-secrets \
  --environment test --from "$TEMPORARY_SECRETS" --remove-source
```

The helper encrypts to the ignored environment `secrets.sops.yml`, validates required
keys and TLS material, and only then replaces the existing encrypted file. It removes
the plaintext source only when `--remove-source` is explicit and validation succeeds.

The test-PKI helper can initialize or rotate generated test credentials and certificates:

```bash
./execution/k3s/operations/certificates/generate-test-data-services \
  --environment test --force --update-sops
```

## Acceptance Boundary

The protocol checks run from the controller. They prove endpoint reachability, TLS,
authentication, and basic command execution from that vantage point. Later acceptance
must still test from an allowed k3s pod/client network and from a denied external source.