# Phase 4 k3s Installation Progress

Status: complete disposable single-node Phase 4 development cluster; ready for Phase 5

Last updated: 2026-09-20

## Selected Development Values

- k3s `v1.36.3+k3s1`, linux/amd64 SHA-256 `2f98a9f8fe5782479ee2d54e70a1b10a7f6fd4cae8d38ed3098452dc6eed76b5`.
- Upstream `k3s.orchestration` collection `1.2.2`, installed from its immutable SCM tag.
- Node `bastion151` at `192.168.1.151`; API kubeconfig endpoint uses the private IP.
- Pod CIDR `10.42.0.0/16`, service CIDR `10.43.0.0/16`, and cluster DNS `10.43.0.10`.
- k3s state `/srv/mokla/k3s/server`, local-path storage `/srv/mokla/k3s/storage`.
- Ignored mode-`0600` bootstrap administrator kubeconfig under the test environment `.generated` directory.
- Runtime smoke image `busybox:1.36.1` pinned to OCI index digest `sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662`.

## Implemented Contract

- Public orchestration supports explicit Phase 4 check and apply boundaries after Phases 1-3.
- Check mode performs read-only node and bundled-component observation. Disposable namespace, pod, service, and PVC operations run only during explicit apply.
- The exact binary checksum, exact parsed release, immutable cluster identity, protected paths, service state, secrets encryption, firewall policy, and Docker/k3s data-root separation are verified.
- Full apply smoke tests cover DNS, ClusterIP routing, pod egress, permitted MariaDB/Redis TCP reachability, and local-path persistence across pod recreation.
- The report preserves a bounded lifecycle history with mode, recap, runtime scope, and service start identity before and after each run.
- Dedicated controlled-restart and reboot prepare/verify validators record redacted lifecycle evidence without storing credentials.

## Lifecycle Evidence

- Initial k3s activation occurred at `2026-09-20 07:34:08 UTC`; the host boot predates installation at `2026-09-19 17:39:36 UTC`.
- A corrected public check completed with `changed=0`, retained the same service start identity, and left `platform-install-smoke` absent before and after execution.
- An unchanged apply completed with Phase 2 `changed=0`, Phase 3 `changed=0`, Phase 4 `changed=0`, full runtime smoke status `pass`, and no k3s restart.
- Controlled k3s restart status is `pass`: the service start identity changed, the Kubernetes node UID/version/readiness were preserved, and MariaDB/Redis container identities and health were unchanged.
- The post-restart public check completed with all phases at `changed=0`, read-only runtime status `pass`, and no additional k3s restart.
- The operator-approved reboot completed successfully. The boot ID changed; k3s and Docker recovered automatically; the Kubernetes node UID, exact version, and Ready state were preserved; and MariaDB/Redis container identities and health were unchanged.
- The final post-reboot public check completed in 88 seconds with Phase 4 `changed=0`, read-only runtime status `pass`, no k3s restart, and `platform-install-smoke` absent before and after execution.
- The original installation run predated lifecycle-history support. Its successful installation can be corroborated by the exact binary checksum and systemd activation timestamp, but its complete first-run recap was not retained in repository evidence.
- Durable evidence is written to `execution/k3s/.evidence/test/phase-4-k3s-installation.json`.

## Validation

The completion gate passed:

- 84 Python tests passed in the pinned controller virtual environment; one test was skipped.
- Python compilation passed for all operation modules.
- `bash -n execution/k3s/bootstrap.sh` passed.
- Phase 4 Ansible syntax validation passed.
- Staged and unstaged `git diff --check` passed.
- k3s is active and enabled at `v1.36.3+k3s1`.
- Controlled restart, operator-approved reboot recovery, and the final non-mutating public check passed.

## Reboot Procedure Used

Immediately before the operator-approved reboot, the pre-boot snapshot was recorded with:

```bash
python3 execution/k3s/operations/validate/k3s_reboot.py prepare \
	--platform execution/k3s/environments/test/platform.yml \
	--repository "$PWD" \
	--report execution/k3s/.evidence/test/phase-4-k3s-installation.json
```

After the host returned, recovery was verified before running any apply with:

```bash
python3 execution/k3s/operations/validate/k3s_reboot.py verify \
	--platform execution/k3s/environments/test/platform.yml \
	--repository "$PWD" \
	--report execution/k3s/.evidence/test/phase-4-k3s-installation.json
```

The final non-mutating public check then passed. No apply was required after reboot.

## Portability Note

The upstream collection's server role always invokes the install script, reports a
change, writes broader configuration permissions, and restarts the first server during
ordinary convergence. The local Phase 4 role therefore owns exact binary verification,
configuration, systemd lifecycle, and kubeconfig handling. It consumes only the pinned
upstream prerequisite role with upstream firewall management disabled. A replacement
installer must preserve the schema, immutable identity marker, service/config paths,
kubeconfig, runtime-validation, and evidence interfaces.

## Deferred Controls

Off-host token/SQLite/config backup, public DNS and PKI, restricted routine identities,
production firewall qualification, multi-node networking, and recovery rehearsal remain
assigned to later phases by the development-profile addendum.