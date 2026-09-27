# Cluster 101: Learning and Operating This Platform

## Purpose

This guide describes what an operator should learn to administer this repository's
single-node k3s test platform safely. It is a learning path and daily operations
reference, not a replacement for the phase plans or the automated checks.

The platform consists of:

- one Ubuntu host running Docker and k3s;
- MariaDB, Redis, MinIO, and the alert receiver in Docker outside Kubernetes;
- Traefik, CoreDNS, metrics-server, and local-path storage supplied by k3s;
- cert-manager for certificates;
- Prometheus, Alertmanager, Grafana, and node exporter for metrics and alerting;
- Loki and Grafana Alloy for logs; and
- application namespaces such as `judge-test`, protected by quotas, Pod Security, RBAC,
  and NetworkPolicy.

## Safety Principles

Before learning individual commands, adopt these operating rules:

1. Prefer the repository's `bootstrap.sh check` workflow over manual diagnosis.
2. Use `check` before `apply`; understand the reported drift before changing anything.
3. Treat `kubectl edit`, `kubectl delete`, direct Helm changes, and manual host changes as
   exceptional. They can create drift from the repository's desired state.
4. Never print, copy into logs, or commit age identities, decrypted SOPS content,
   kubeconfigs, tokens, passwords, private keys, or Kubernetes Secret values.
5. Back up state before upgrades or destructive work.
6. Remember that this is one machine. A reboot causes downtime, and loss of the host can
   lose data until off-host recovery is qualified.

## Prepare an Operator Shell

Run these commands from the repository root in each new shell:

```bash
ENVIRONMENT="test"
K3S_DIR="$PWD/execution/k3s"

export PATH="$K3S_DIR/.controller-venv/bin:$PATH"
export ANSIBLE_CONFIG="$K3S_DIR/host/ansible.cfg"
export SOPS_AGE_KEY_FILE="$K3S_DIR/environments/$ENVIRONMENT/age-identity.txt"

test -r "$SOPS_AGE_KEY_FILE"
./execution/k3s/operations/setup/controller.sh check
```

Do not generate a replacement age identity when decryption fails. First confirm that the
existing identity path is exported correctly and that the file is readable.

## 1. Linux Administration

### Learn

- systemd units, service dependencies, startup behavior, and logs;
- filesystems, free space, mounts, permissions, ownership, and restrictive file modes;
- CPU, memory, process, and network inspection;
- DNS resolution, routes, listening ports, and UFW rules;
- package updates, kernel updates, pending-reboot state, and safe reboot procedures;
- the difference between a process, a systemd service, a container, and a Kubernetes
  workload.

### Practice safely

```bash
systemctl status k3s docker --no-pager
journalctl -u k3s --since "30 minutes ago" --no-pager
uptime
uname -r
free -h
df -h
ip address
ip route
ss -lntup
sudo ufw status verbose
```

Start with status and log commands. Do not restart services simply to test commands on a
working cluster.

### Know how to answer

- Is the host under CPU, memory, or disk pressure?
- Is Docker or k3s inactive, failed, or repeatedly restarting?
- Is a port bound publicly when it should be private?
- Is a failure caused by DNS, routing, firewall policy, permissions, or the service
  itself?
- Does the host require a reboot after package updates?

## 2. Containers

### Learn

- the relationship between OCI images, containers, registries, tags, and digests;
- why this platform pins deployed images by digest;
- Docker volumes, bind mounts, networks, health checks, and restart policies;
- the difference between Docker, containerd, and the k3s container runtime;
- why MariaDB and Redis run outside Kubernetes in the current architecture.

### Practice safely

```bash
docker ps
docker compose ls
docker inspect --format '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
  $(docker ps -q)
docker logs --tail 100 mokla-test-mariadb-1
docker logs --tail 100 mokla-test-redis-1
```

Avoid `docker compose down`, volume removal, image pruning, or direct container recreation
until you understand which phase owns the service and how its state is protected.

### Know how to answer

- Which external services are healthy?
- Which image and immutable digest should a service use?
- Where does persistent service data live?
- Will recreating a container preserve its data?
- Is a failed health check caused by the process, its dependency, or its credentials?

## 3. Kubernetes Fundamentals

### Learn

- Pods as disposable runtime instances;
- Deployments for stateless replicated workloads;
- StatefulSets for stable identities and persistent storage;
- DaemonSets for one workload instance per selected node;
- Services for stable internal addressing and Ingress for HTTP/TLS routing;
- ConfigMaps for non-secret configuration and Secrets for sensitive runtime values;
- namespaces, labels, selectors, annotations, requests, limits, probes, and quotas;
- PersistentVolumes, PersistentVolumeClaims, StorageClasses, and reclaim policies;
- desired state, reconciliation, rollout history, events, and readiness.

This repository invokes Kubernetes through k3s. Use the scoped kubeconfig where possible:

```bash
KUBECONFIG="$K3S_DIR/environments/$ENVIRONMENT/.generated/cluster-addons.kubeconfig"

k3s kubectl --kubeconfig "$KUBECONFIG" get nodes
k3s kubectl --kubeconfig "$KUBECONFIG" get pods -A
k3s kubectl --kubeconfig "$KUBECONFIG" get deployments,statefulsets,daemonsets -A
k3s kubectl --kubeconfig "$KUBECONFIG" get services,ingress -A
k3s kubectl --kubeconfig "$KUBECONFIG" get pvc,pv -A
k3s kubectl --kubeconfig "$KUBECONFIG" get events -A --sort-by=.lastTimestamp
```

For a specific failure:

```bash
k3s kubectl --kubeconfig "$KUBECONFIG" describe pod POD_NAME -n NAMESPACE
k3s kubectl --kubeconfig "$KUBECONFIG" logs POD_NAME -n NAMESPACE --all-containers --tail=100
k3s kubectl --kubeconfig "$KUBECONFIG" rollout status deployment/DEPLOYMENT -n NAMESPACE
```

Do not retrieve Secret YAML or use `--show-managed-fields` unless a documented diagnostic
requires it. Terminal output can be retained in logs and evidence.

### Know how to answer

- Is a Pod Pending, starting, unready, crashing, or terminated?
- Did scheduling, image pulling, configuration, storage, or a health probe fail?
- Does a Service selector match the intended Pods?
- Is an Ingress routed through Traefik with the expected certificate?
- Is a PVC Bound, and what happens to its data if the claim is deleted?

## 4. Cluster Security

### Learn

- Kubernetes users, groups, service accounts, Roles, ClusterRoles, and bindings;
- authentication versus authorization;
- default-deny NetworkPolicy and explicit ingress/egress allowances;
- restricted Pod Security and why privileged containers, host mounts, and added Linux
  capabilities require review;
- SOPS encryption, age recipients, private age identities, and controller-side
  decryption;
- why application and platform automation must not share administrator credentials.

### Practice safely

Inspect policy without exposing secret data:

```bash
k3s kubectl --kubeconfig "$KUBECONFIG" get resourcequota,limitrange,networkpolicy -n judge-test
k3s kubectl --kubeconfig "$KUBECONFIG" get role,rolebinding,serviceaccount -n judge-test
k3s kubectl --kubeconfig "$KUBECONFIG" auth can-i get pods -n judge-test
sops --decrypt "$K3S_DIR/environments/$ENVIRONMENT/secrets.sops.yml" >/dev/null
```

Never display the decrypted SOPS document merely to test access. A zero exit status from
the final command is enough to prove that decryption works.

### Know how to answer

- Which identity is running a command, and what is it allowed to do?
- Why was a Pod rejected by restricted Pod Security?
- Which NetworkPolicy permits or denies a connection?
- Where is the authoritative encrypted source for a runtime Secret?
- Is a proposed exception limited, documented, test-only, and reversible?

## 5. This Platform's Tooling

### Helm

Helm renders and tracks third-party add-on releases. Learn chart archives, values,
releases, revisions, and rollback semantics. Do not run an ad hoc `helm upgrade`; the
Phase 6 workflow owns release reconciliation.

```bash
helm --kubeconfig "$KUBECONFIG" list --all-namespaces
helm --kubeconfig "$KUBECONFIG" status monitoring -n observability
helm --kubeconfig "$KUBECONFIG" history monitoring -n observability
```

### Kustomize

Kustomize composes repository-owned Kubernetes resources from bases and environment
overlays. Learn resources, patches, labels, and deterministic rendering. Render locally
before applying through the owning workflow.

### Bootstrap workflow

The supported cumulative interface is:

```bash
./execution/k3s/bootstrap.sh check --environment test --through cluster-addons
./execution/k3s/bootstrap.sh apply --environment test --through cluster-addons
```

Use `check` for routine validation. Use `apply` only when intentionally reconciling the
host or cluster to repository state. Each phase requires current passing evidence from
its predecessors.

Evidence is written beneath:

```text
execution/k3s/.evidence/test/
```

Evidence is generated local state and is intentionally ignored by Git. It must remain
redacted and must not contain credentials or private keys.

### Observability

Learn the role of each component:

- Prometheus scrapes and stores metrics.
- Alertmanager groups and routes alerts.
- Grafana displays metrics, logs, and dashboards.
- node exporter exposes host metrics.
- Loki stores bounded platform logs.
- Alloy discovers, filters, redacts, and sends logs and events to Loki.

Learn to distinguish these failure classes:

- the source stopped producing data;
- discovery or collection failed;
- storage rejected or expired data;
- a query or dashboard is wrong;
- an alert rule did not evaluate;
- Alertmanager received an alert but delivery failed.

## Daily Diagnostic Sequence

Begin with the least invasive checks:

```bash
systemctl status k3s docker --no-pager
docker ps
k3s kubectl --kubeconfig "$KUBECONFIG" get nodes
k3s kubectl --kubeconfig "$KUBECONFIG" get pods -A
k3s kubectl --kubeconfig "$KUBECONFIG" get events -A --sort-by=.lastTimestamp
```

Then run the repository's complete read-only validation:

```bash
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through cluster-addons
```

Investigate the first failing phase. A later symptom is often caused by an earlier host,
secret, network, or service dependency.

## Reboot Survival

The cluster is configured to recover from an ordinary host reboot:

- systemd starts Docker and k3s;
- Docker restart policies recover MariaDB, Redis, MinIO, and the alert receiver;
- Kubernetes reconciles platform Deployments, StatefulSets, and DaemonSets;
- local-path volumes remain on the host and are reattached to their claims; and
- readiness checks prevent an unready workload from being treated as healthy.

The test host completed this recovery successfully on 2026-09-27. Docker and k3s became
active, all external service containers became healthy, all Kubernetes workloads became
Ready, persistent claims remained Bound, and the cumulative Phase 1-6 check passed.

This does not provide high availability. During every reboot:

- the Kubernetes API, ingress, applications, and external data services are unavailable;
- alerts and dashboards on the same host are also unavailable; and
- recovery depends on the host disk and configuration remaining intact.

An ordinary reboot is not equivalent to recovery from disk corruption, accidental
deletion, failed upgrades, credential loss, or destruction of the VM. Until off-host
backup and clean-host restore qualification pass, loss of this machine can lose cluster
and application data.

## Safe Reboot Procedure

Before rebooting:

1. Confirm no deployment, migration, backup, or long-running administrative operation is
   active.
2. Confirm console or provider access is available in case SSH does not return.
3. Record current service and workload health.
4. Schedule the reboot with a short cancellation window.

```bash
systemctl is-active k3s docker
docker ps
k3s kubectl --kubeconfig "$KUBECONFIG" get nodes
k3s kubectl --kubeconfig "$KUBECONFIG" get pods -A
sudo shutdown -r +1 "Applying approved host updates"
```

Cancel during the waiting period if necessary:

```bash
sudo shutdown -c
```

After reconnecting, prepare the operator shell again and verify:

```bash
uptime -s
uname -r
systemctl is-active k3s docker
docker ps
k3s kubectl --kubeconfig "$KUBECONFIG" get nodes
k3s kubectl --kubeconfig "$KUBECONFIG" get pods -A
./execution/k3s/bootstrap.sh check --environment "$ENVIRONMENT" --through cluster-addons
```

Do not treat the reboot as successful until the cumulative check exits with status zero.

## Suggested Learning Exercises

Perform these exercises on the disposable test environment and keep them read-only:

1. Trace one request from Traefik Ingress to a Service and its selected Pod.
2. Choose one Pod and identify its owning Deployment or StatefulSet, images, resource
   limits, probes, service account, and mounted configuration.
3. Choose one PVC and trace it to its PV, StorageClass, consuming Pod, and host storage.
4. Follow one metric from node exporter through Prometheus to a Grafana panel.
5. Follow one harmless log line from a Pod through Alloy into Loki and Grafana.
6. Select one alert rule and identify its expression, labels, Alertmanager route, and
   external receiver.
7. Inspect `judge-test` and explain its quota, default limits, restricted Pod Security,
   and default-deny network policy.
8. Read one phase evidence report and map each result to the command or resource that
   produced it.

After those are comfortable, practice bounded failure and recovery scenarios only
through the Phase 7 workflow when it is implemented.

## Read Next

- [k3s Cluster Blueprint](README.md)
- [Repeatable k3s Deployment Strategy](repeatable-deployment.md)
- [Phase 6 Cluster Add-ons](plan/phase-6-cluster-addons.md)
- [Phase 6 Progress](plan/progress/phase-6-cluster-addons-progress.md)
- [Phase 7 Platform Validation](plan/phase-7-platform-validation.md)
- [Phase 8 Recovery Qualification](plan/phase-8-recovery-qualification.md)
- [Phase 9 Application-Ready Handoff](plan/phase-9-application-ready-handoff.md)