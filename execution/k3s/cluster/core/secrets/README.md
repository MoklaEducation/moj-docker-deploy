# Cluster Secret Source Contract

`template.secret.sops.yaml` is an encrypted, deliberately unusable example. Copy its
decrypted structure outside the repository, replace the name, namespace, keys, and
values, then encrypt it to the environment's declared age recipient before placing the
encrypted source in the owning phase.

Controller-side workflows decrypt to stdout and pipe directly into validation or
`kubectl`; they must not write plaintext beneath the repository or evidence directory.
Consumer Secret names remain stable so a future GitOps SOPS integration can assume
ownership without changing workloads. Phase 5 installs no secret controller and applies
no Secret from this template.