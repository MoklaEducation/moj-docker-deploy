# Phase 4 k3s Installation Progress

Status: implementation in progress; host installation not yet applied

Last updated: 2026-09-20

## Selected Development Values

- k3s `v1.36.3+k3s1`, linux/amd64 SHA-256 `2f98a9f8fe5782479ee2d54e70a1b10a7f6fd4cae8d38ed3098452dc6eed76b5`.
- Upstream `k3s.orchestration` collection `1.2.2`, installed from its immutable SCM tag.
- Node `bastion151` at `192.168.1.151`; API kubeconfig endpoint uses the private IP.
- Pod CIDR `10.42.0.0/16`, service CIDR `10.43.0.0/16`, and cluster DNS `10.43.0.10`.
- k3s state `/srv/mokla/k3s/server`, local-path storage `/srv/mokla/k3s/storage`.
- Ignored bootstrap administrator kubeconfig under the test environment `.generated` directory.

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