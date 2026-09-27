# Cluster Administration 101

## Purpose

Use this runbook when administering the platform built by `execution/k3s`. It is organized
by operator intent: find the task you need, run the supported command, and inspect the
named evidence or logs if it fails.

This document describes commands that exist now. Proposed Mise and `platformctl`
equivalents are listed separately so the current and future interfaces are not confused.

## Platform At a Glance

The current `test` platform is one Ubuntu host containing:

```text
Host
├── Docker
│   ├── MariaDB
│   ├── Redis
│   ├── MinIO-compatible test storage
│   └── disposable alert receiver
└── single-node k3s
    ├── CoreDNS, Traefik, metrics-server, local-path storage
    ├── cluster namespaces, RBAC, quotas, limits, and network policies
    ├── cert-manager and private test certificates
    ├── Prometheus, Alertmanager, Grafana, and node exporter
    ├── Loki and Grafana Alloy
    └── judge-test application namespace
```

There is no high availability: host downtime means platform downtime. Kubernetes backup,
off-host recovery qualification, production certificate lifecycle, and production
environment configuration are not yet complete.

## Command Rules

1. Run commands from the repository root.
2. Use the platform operator kubeconfig for routine Kubernetes inspection.
3. Run `check` before `apply` unless installing a clean host through an approved plan.
4. Do not use `kubectl edit`, direct `helm upgrade`, or manual container recreation to
   repair declared state. Use the owning workflow.
5. Never print decrypted secrets, private keys, tokens, or Secret manifests.
6. Treat backup, restore, restart, reboot, access renewal, and certificate rotation as
   explicit operations rather than routine diagnostics.

## Prepare an Admin Shell

Run this once in each new shell:

```bash
ENVIRONMENT="test"
K3S_DIR="$PWD/execution/k3s"

export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

OPERATOR_KUBECONFIG="$K3S_DIR/environments/$ENVIRONMENT/.generated/platform-operator.kubeconfig"
ADDONS_KUBECONFIG="$K3S_DIR/environments/$ENVIRONMENT/.generated/cluster-addons.kubeconfig"
OPERATOR_NAMESPACES=(platform-system observability backup-system judge-test)
PHASE4_REPORT="$K3S_DIR/.evidence/$ENVIRONMENT/phase-4-k3s-installation.json"

test -r "$SOPS_AGE_KEY_FILE"
./execution/k3s/operations/setup/controller.sh check
sops --decrypt "$K3S_DIR/environments/$ENVIRONMENT/secrets.sops.yml" >/dev/null
```

If controller prerequisites are missing, install the repository-pinned toolchain:

```bash
./execution/k3s/operations/setup/controller.sh install
./execution/k3s/operations/setup/controller.sh check
```

Do not regenerate the age identity to fix a missing export. A new identity cannot decrypt
secrets encrypted for the current recipient.

## Scenario Index

| Administrator intent | Current facility | Future facade |
| --- | --- | --- |
| Get a quick health snapshot | systemd, Docker, and Kubernetes status commands | `mise run status` |
| Validate the complete platform | cumulative bootstrap check | `mise run check` |
| Install or reconcile the platform | cumulative bootstrap apply | `mise run apply` |
| Work at one phase boundary | bootstrap `--through` | `mise run phase:check` / `phase:apply` |
| Diagnose a failed workload | events, describe, logs, rollout status | `mise run doctor`, `logs`, `inspect` |
| Check or provision external data services | `data-services check|setup` | `mise run data:check|apply` |
| Create and verify a data-service backup | wrapper exists; disabled in `test` | `mise run backup`, `backup:verify` |
| Test an isolated data-service restore | wrapper exists; disabled in `test` | `mise run restore:verify` |
| Inspect certificates | cluster check and `kubectl get certificate` | `mise run cert:status` |
| Rotate test data-service TLS | certificate generator plus Phase 3 apply | `mise run cert:rotate-data` |
| Renew cluster access certificates | cluster-core access operation | `mise run access:renew` |
| Inspect dashboards and observability APIs | private port-forward | `mise run ui:grafana`, `ui:prometheus` |
| Perform a controlled k3s restart | lifecycle validator | `mise run restart:k3s` |
| Prove reboot recovery | prepare, reboot, verify, cumulative check | `mise run reboot:prepare|verify` |
| Review current evidence | JSON reports under `.evidence` | `mise run history`, `inspect` |
| Run platform qualification | not implemented | `mise run validate` |
| Roll back an add-on | not implemented | future explicit rollback task |
| Recover a destroyed host | not implemented/qualified | future recovery workflow |

## Check Platform Health Quickly

Use this sequence for routine inspection:

```bash
systemctl is-active docker k3s
docker ps --format 'table {{.Names}}\t{{.Status}}'
k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" get nodes
for namespace in "${OPERATOR_NAMESPACES[@]}"; do
  k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" get pods,pvc -n "$namespace"
done
```

Check for a pending host reboot:

```bash
if [[ -e /var/run/reboot-required ]]; then
  echo "reboot required"
  cat /var/run/reboot-required.pkgs
else
  echo "no reboot required"
fi
```

This is a health snapshot, not a complete drift or policy validation.

## Validate the Complete Platform

Run the current authoritative read-only workflow through Phase 6:

```bash
./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

A successful exit proves current Phase 1-6 checks passed. It does not qualify deferred
Kubernetes backup, off-host recovery, production certificates, or Phase 7 scenarios.

## Install or Reconcile the Complete Platform

For an approved initial installation or desired-state reconciliation:

```bash
./execution/k3s/bootstrap.sh apply \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

Then run the complete check:

```bash
./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

`apply` never reboots the host automatically. Stop if an earlier phase reports a pending
reboot, repair requirement, or failed prerequisite.

## Stop at a Phase Boundary

Use `--through` to limit cumulative execution:

```bash
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT"
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-baseline
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through host-data-services
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through k3s-installation
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through cluster-core
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through cluster-addons
```

Apply requires an explicit boundary:

```bash
./execution/k3s/bootstrap.sh apply --environment "$ENVIRONMENT" --through PHASE
```

Valid `PHASE` values are `host-baseline`, `host-data-services`, `k3s-installation`,
`cluster-core`, and `cluster-addons`. Earlier phases still run because the current
orchestrator is cumulative.

## Diagnose Kubernetes Workloads

Start with recent events and workload state:

```bash
for namespace in "${OPERATOR_NAMESPACES[@]}"; do
  k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" \
    get events -n "$namespace" --sort-by=.lastTimestamp
  k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" \
    get deployments,statefulsets,daemonsets -n "$namespace"
done
```

Inspect one failing Pod:

```bash
NAMESPACE="observability"
POD="REPLACE_WITH_POD_NAME"

k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" describe pod "$POD" -n "$NAMESPACE"
k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" \
  logs "$POD" -n "$NAMESPACE" --all-containers --tail=200
```

Check a rollout without changing it:

```bash
k3s kubectl --kubeconfig "$OPERATOR_KUBECONFIG" \
  rollout status deployment/DEPLOYMENT -n NAMESPACE --timeout=120s
```

Do not delete a failing Pod until its events and logs have been inspected. Deletion may
remove useful evidence and does not repair incorrect desired state.

## Diagnose Host and k3s Services

```bash
systemctl status docker k3s --no-pager
journalctl -u docker --since "30 minutes ago" --no-pager
journalctl -u k3s --since "30 minutes ago" --no-pager
free -h
df -h / /srv
ss -lntup
```

Use the first failing cumulative phase to decide whether the problem belongs to the host,
external services, k3s, cluster core, or add-ons.

## Check External Data Services

Run the scoped read-only workflow:

```bash
./execution/k3s/operations/data-services/data-services \
  check --environment "$ENVIRONMENT"
```

Inspect container state and bounded logs:

```bash
docker ps --filter 'name=mokla-test-'
docker logs --tail 200 "mokla-$ENVIRONMENT-mariadb-1"
docker logs --tail 200 "mokla-$ENVIRONMENT-redis-1"
docker logs --tail 200 "mokla-$ENVIRONMENT-minio-1"
docker logs --tail 200 "mokla-$ENVIRONMENT-alert-receiver-1"
```

Provision or reconcile helper-managed services only when intended:

```bash
./execution/k3s/operations/data-services/data-services \
  setup --environment "$ENVIRONMENT" --provision-host-services
```

## Encrypt or Replace Environment Secrets

Prepare a mode-`0600` plaintext YAML file outside the repository, then run:

```bash
./execution/k3s/operations/data-services/data-services encrypt-secrets \
  --environment "$ENVIRONMENT" \
  --from /secure/temporary/secrets.yml \
  --remove-source
```

The command validates the encrypted result before replacing the environment SOPS file.
Never pass secret values directly as command-line arguments.

## Back Up External Data Services (Disabled)

The repository contains the command interface below, but the current `test` profile sets
`backup.enabled: false`. Its required host helper is consequently not installed, so this
command is not currently operational:

```bash
./execution/k3s/operations/backup/backup \
  data-services --environment "$ENVIRONMENT"
```

Read the resulting snapshot ID without exposing credentials:

```bash
python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_id"])' \
  "$K3S_DIR/.evidence/$ENVIRONMENT/phase-3-backup.json"
```

Verify that exact snapshot:

```bash
SNAPSHOT="REPLACE_WITH_SNAPSHOT_ID"

./execution/k3s/operations/backup/backup verify \
  --environment "$ENVIRONMENT" \
  --snapshot "$SNAPSHOT"
```

Do not enable this solely to claim recoverability. The configured test repository is
same-host local storage; it does not provide off-host resilience. Enabling backup requires
an approved platform configuration change, Phase 3 apply, successful backup verification,
and documented retention and monitoring ownership.

## Test an Isolated Data-Service Restore (Disabled)

The restore wrapper is also present but unavailable while backup is disabled and the host
restore helper is not installed. After an approved backup enablement, restore only into a
dedicated child of the configured restore root:

```bash
SNAPSHOT="REPLACE_WITH_SNAPSHOT_ID"
TARGET="/srv/mokla/restore-tests/admin-check-$(date +%Y%m%d%H%M%S)"

./execution/k3s/operations/restore/restore data-services \
  --environment "$ENVIRONMENT" \
  --snapshot "$SNAPSHOT" \
  --target "$TARGET"
```

This is an isolated validation restore. It does not replace live MariaDB or Redis and is
not a full host or Kubernetes recovery operation.

## Inspect Certificates

Run the complete Phase 6 check for the supported certificate validation:

```bash
./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" \
  --through cluster-addons
```

Cert-manager resources are outside the platform operator's namespace grants. Use the
test-only elevated add-on identity for this inspection, without reading private-key
Secrets:

```bash
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" get issuer,certificate -A
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" \
  describe certificate phase6-test-tls -n cert-manager
```

Current limitation: automatic renewal configuration exists, but there is no supported
operator command for a forced cert-manager renewal rehearsal or expiry-alert test.

## Rotate Test Data-Service Certificates

This operation is test-only. It replaces the data-service TLS material in SOPS:

```bash
./execution/k3s/operations/certificates/generate-test-data-services \
  --environment "$ENVIRONMENT" --force --update-sops

./execution/k3s/bootstrap.sh apply \
  --environment "$ENVIRONMENT" --through host-data-services

./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" --through host-data-services
```

Production requires an externally owned certificate lifecycle; this generator must not
be treated as a production certificate authority.

## Renew Cluster-Core Access Certificates

Routine checks use restricted client-certificate identities. When Phase 5 credentials
approach expiry, review the RBAC and run the explicit break-glass operation:

```bash
./execution/k3s/cluster/core/scripts/access.sh check "$ENVIRONMENT"
./execution/k3s/cluster/core/scripts/access.sh apply "$ENVIRONMENT"
./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" --through cluster-core
```

Current limitation: the Phase 6 add-on identity still uses a documented temporary
test-only `cluster-admin` binding and lacks an equally clear standalone renewal command.

## Open Private Observability UIs

The platform operator identity cannot create port-forwards. The current test-only add-on
identity can, but it temporarily has `cluster-admin`; use it only for this operation and
bind only to loopback. Run one command per terminal:

```bash
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" -n observability \
  port-forward --address 127.0.0.1 service/monitoring-grafana 3000:80
```

Open `http://127.0.0.1:3000` for Grafana.

Prometheus:

```bash
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" -n observability \
  port-forward --address 127.0.0.1 \
  service/monitoring-kube-prometheus-prometheus 9090:9090
```

Alertmanager:

```bash
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" -n observability \
  port-forward --address 127.0.0.1 \
  service/monitoring-kube-prometheus-alertmanager 9093:9093
```

Loki API:

```bash
k3s kubectl --kubeconfig "$ADDONS_KUBECONFIG" -n observability \
  port-forward --address 127.0.0.1 service/loki 3100:3100
```

Stop a port-forward with `Ctrl+C`. Do not bind these administrative endpoints to
`0.0.0.0`.

## Perform a Controlled k3s Restart

This is disruptive and requires current passing Phase 4 evidence:

```bash
python3 execution/k3s/operations/validate/k3s_restart.py \
  --platform "$K3S_DIR/environments/$ENVIRONMENT/platform.yml" \
  --repository "$PWD" \
  --report "$PHASE4_REPORT"
```

The command restarts k3s, waits for the node, verifies identity and version preservation,
checks MariaDB/Redis health, and records the result in Phase 4 evidence.

## Reboot the Host With Recovery Evidence

Formal reboot qualification requires a passing controlled restart first.

Before rebooting:

```bash
python3 execution/k3s/operations/validate/k3s_reboot.py prepare \
  --platform "$K3S_DIR/environments/$ENVIRONMENT/platform.yml" \
  --repository "$PWD" \
  --report "$PHASE4_REPORT"

sudo shutdown -r +1 "Approved platform reboot"
```

Cancel during the waiting period if needed:

```bash
sudo shutdown -c
```

After reconnecting, prepare the admin shell again and run:

```bash
python3 execution/k3s/operations/validate/k3s_reboot.py verify \
  --platform "$K3S_DIR/environments/$ENVIRONMENT/platform.yml" \
  --repository "$PWD" \
  --report "$PHASE4_REPORT"

./execution/k3s/bootstrap.sh check \
  --environment "$ENVIRONMENT" --through cluster-addons
```

## Review Evidence

List available reports:

```bash
find "$K3S_DIR/.evidence/$ENVIRONMENT" -maxdepth 1 -type f -name '*.json' -print
```

Show phase status without displaying complete report content:

```bash
python3 - "$K3S_DIR/.evidence/$ENVIRONMENT" <<'PY'
import json
import pathlib
import sys

for path in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    report = json.loads(path.read_text(encoding="utf-8"))
    status = report.get("overall_status", report.get("status", "unknown"))
    print(f"{path.name}: {status}")
PY
```

Evidence is ignored local state. Do not copy reports externally until their redaction has
been reviewed.

## Respond to a Failed Cumulative Check

1. Stop at the first failing phase; do not compensate by manually changing a later
   layer.
2. Read the failing phase's report under `.evidence/$ENVIRONMENT/`.
3. Use host logs, container logs, or Kubernetes events according to the owning phase.
4. Correct desired state or the missing prerequisite.
5. Run the same `check` again.
6. Run `apply` only when a declared-state change is intended.
7. Finish with the complete cumulative check.

Do not delete evidence, PVCs, namespaces, Helm releases, or data directories merely to
make a check pass.

## Current Administrative Gaps

These workflows do not yet have a complete supported command:

- fast consolidated `status` and guided `doctor` output;
- Phase 7 platform validation and scenario selection;
- Kubernetes/add-on backup, freshness monitoring, and namespace restore;
- qualified off-host backup and clean-host recovery;
- forced cert-manager renewal rehearsal and certificate-expiry alert testing;
- production certificate issuance and rotation;
- least-privilege Phase 6 access renewal;
- explicit add-on rollback and validation;
- platform upgrade orchestration and rollback;
- evidence history, run IDs, and safe resume;
- application deployment and application-specific backup; and
- a production environment configuration.

Do not replace these gaps with undocumented manual procedures. Add an owned operation,
validation, and evidence contract before treating one as routine.

## Future Mise and platformctl Translation

The planned facade should map current capabilities without changing their owners:

```text
mise run status              -> platformctl status
mise run check               -> platformctl check
mise run apply               -> platformctl apply
mise run phase:check         -> platformctl phase check
mise run phase:apply         -> platformctl phase apply
mise run doctor              -> platformctl doctor
mise run logs                -> platformctl logs
mise run backup              -> platformctl backup data-services
mise run backup:verify       -> platformctl backup verify
mise run restore:verify      -> platformctl restore verify
mise run cert:status         -> platformctl certificate status
mise run cert:rotate-data    -> platformctl certificate rotate-data-services
mise run access:renew        -> platformctl access renew
mise run restart:k3s         -> platformctl restart k3s
mise run reboot:prepare      -> platformctl reboot prepare
mise run reboot:verify       -> platformctl reboot verify
mise run history             -> platformctl history
mise run validate            -> platformctl validate
```

Until those commands are implemented and tested, use the current commands in this
runbook. Do not assume a listed future command exists merely because its mapping is
documented.

## Related Guides

- [Cluster 101](learn_cluster101.md) explains the concepts an administrator should learn.
- [Deployment Automation Strategy](plan/deployment-automation-strategy.md) explains the
  proposed Mise and runner architecture.
- [Repeatable Deployment Strategy](repeatable-deployment.md) defines phase ownership and
  sequencing.
- [Phase 6 Progress](plan/progress/phase-6-cluster-addons-progress.md) records the current
  add-on state.
- [Phase 7 Platform Validation](plan/phase-7-platform-validation.md) defines the next
  qualification workflow.