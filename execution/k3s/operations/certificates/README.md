# Test Data-Service Certificates

Generate a controller-owned test CA and a shared server certificate covering the
configured private service IP and host name:

```bash
./execution/k3s/operations/certificates/generate-test-data-services \
  --environment test --initialize-sops
```

Artifacts are written with restrictive permissions beneath the ignored directory
`execution/k3s/environments/test/.generated/data-services-tls`. The server certificate,
server key, and CA certificate are imported into the existing SOPS file only when
`--update-sops` is supplied. For first-time test setup, `--initialize-sops` creates a
new encrypted document with generated service passwords and refuses to overwrite a
non-empty file. The CA private key is never copied to the managed host.

Rotate before expiry with `--force --update-sops`, then run the Phase 3 check and apply.
The certificate is used by MariaDB and Redis. The local restic repository is a filesystem
path and therefore has no TLS endpoint; moving restic to an HTTPS/S3 endpoint requires
independent verification of that endpoint's certificate.

These certificates are test-only. Production environments must use an externally owned
certificate lifecycle and off-host backup storage.