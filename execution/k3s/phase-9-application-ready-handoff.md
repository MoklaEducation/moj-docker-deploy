# Phase 9 Implementation Plan: Application-Ready Handoff

Status: ready for implementation after Phase 8 passes.

## Mission

Publish and verify the stable interfaces through which application delivery consumes the
qualified platform. Convert platform assumptions into a versioned machine-readable
contract, operator documentation, scoped credentials, and a non-application conformance
test. Formally open the application deployment gate only when that contract is complete
and backed by current Phase 7 and Phase 8 evidence.

Phase 9 does not deploy DMOJ or any other application.

## Preconditions

- Phase 7 passes for the target platform revision with no blocking exception.
- Phase 8 recovery qualification passes against the same compatible desired state.
- DNS zones, ingress hostnames, certificate issuer, registry, image-pull mechanism,
  application owners, alert contacts, resource budgets, and data-service access policy
  are approved.
- Application namespaces and baseline guardrails exist from Phase 5 but contain no
  application workload.
- All contract values are available without exposing secret material.

Any later platform change that invalidates these evidence relationships closes the gate
until affected checks and the contract are republished.

## Goals

1. Define every supported platform interface and its owner.
2. Issue namespace-scoped application deployment identities with deny tests.
3. Publish endpoint/secret/storage/resource/observability/backup expectations.
4. Provide offline and live conformance checks for application manifests and access.
5. Version the contract and define compatible change/deprecation rules.
6. Record a signed or digest-verifiable application-ready decision.

## Intended File Ownership

```text
execution/k3s/environments/<environment>/
  application-platform-contract.yaml
  application-platform-contract.schema.json
  application-platform-contract.md
execution/k3s/operations/handoff/
  render-contract.sh
  validate-contract.sh
  verify-application-access.sh
  qualify-handoff.sh
```

The YAML contract is authoritative. Generate the Markdown view from it so machine and
human guidance cannot drift. Secret values, kubeconfigs, registry credentials, and
database passwords remain external encrypted inputs.

## Operator Interface

```bash
./execution/k3s/bootstrap.sh handoff check --environment test
./execution/k3s/bootstrap.sh handoff publish --environment test
```

`check` validates schema, evidence, live interfaces, RBAC boundaries, and generated
documentation without modifying the platform. `publish` writes the versioned contract,
records its digest/evidence relationship, and changes the application gate to open only
after all checks pass.

Provide a separate application pipeline command conceptually equivalent to:

```text
validate-application --environment <name> --manifest <rendered-manifest>
```

It performs offline schema/policy/contract checks and optional server-side dry-run using
the application deployment identity. It must not apply resources.

## Contract Contents

### Identity and compatibility

- contract semantic version, environment, cluster identity, generation time, repository
  revision, configuration hash, and required Phase 7/8 evidence IDs;
- supported Kubernetes API versions and k3s version range;
- owner and support/escalation procedure for platform and application responsibilities;
- compatibility and deprecation policy.

### Namespaces and deployment access

- exact namespace per application/environment and required/managed labels;
- deployment service-account/group identity, credential delivery method, lifetime,
  rotation, revocation, and break-glass procedure;
- allowed resource kinds/actions and explicit forbidden cluster-scoped/platform actions;
- ownership labels/annotations required on application resources;
- approved apply method: rendered Kustomize/plain manifests through scoped server-side
  apply initially, with the future GitOps transfer noted but disabled;
- pruning selector/allowlist that cannot delete platform or unrelated application state.

### Ingress, DNS, and certificates

- hostname allocation rules, DNS owner/change procedure, Traefik ingress class, supported
  annotations, ports/protocols, trusted proxy behavior, body/time-out limits, and source
  exposure expectations;
- production ClusterIssuer name and certificate resource/interface to consume;
- TLS policy, redirect behavior, health endpoint expectations, and certificate ownership;
- prohibition on application-owned ingress controllers or ACME account credentials.

### Secrets and image pulls

- SOPS-encrypted source format, approved age recipients, stable Secret naming, key schema,
  decryption/apply owner, rotation process, and forbidden plaintext locations;
- registry endpoint, repository naming, immutable digest requirement, image scanning/signing
  policy when adopted, pull-secret name, namespace delivery owner, and rotation method;
- prohibition on credentials in images, manifests, ConfigMaps, logs, annotations, or
  command arguments.

### MariaDB and Redis

- stable DNS/IP endpoint, port, TLS mode, CA reference, database/keyspace naming, secret
  reference and keys, connection limits, timeout/retry expectations, and maintenance
  behavior;
- per-environment least-privilege account provisioning/rotation/revocation procedure;
- Redis persistence policy and resulting data-loss expectation;
- backup/restore ownership and application-level data-integrity responsibilities;
- explicit same-host failure-domain warning: these endpoints are outside Kubernetes but
  fail with the same VM.

Do not publish administrator usernames, passwords, live connection strings, or private
CA keys in the contract.

### Storage and resources

- supported storage class, access modes, reclaim behavior, expansion support, backup
  coverage, maximum PVC size/count, and local single-host durability limits;
- namespace ResourceQuota and LimitRange values, minimum/maximum workload requests and
  limits, replica expectations, ephemeral-storage constraints, and measured remaining
  platform capacity;
- scheduling constraints and unavailable capabilities such as multi-node anti-affinity,
  ReadWriteMany, and distributed persistence.

### Network, health, and observability

- default-deny behavior and request process for approved ingress/egress destinations;
- allowed DNS, ingress, data-service, registry, monitoring, and backup-related flows;
- required readiness/liveness/startup probe behavior and graceful termination budget;
- metrics endpoint/labels, log stream format, correlation fields, prohibited sensitive
  content, retention, dashboard ownership, and alert-routing responsibilities;
- application SLO/runbook/contact references required before production onboarding.

### Backup and recovery responsibilities

- which Kubernetes objects/PVCs the platform backs up and which application data is
  protected by MariaDB/Redis procedures;
- RPO/RTO offered by the platform and any stricter application-owned requirement;
- what is explicitly disposable or excluded;
- restore request, approval, validation, and application data-consistency procedure;
- requirement that application changes preserve the Phase 8 recovery workflow.

## Responsibility Matrix

At minimum assign one accountable owner for:

| Concern | Platform responsibility | Application responsibility |
| --- | --- | --- |
| Host/k3s/add-ons | Provision, secure, observe, recover | Do not modify |
| Namespace guardrails | Create and enforce | Operate within limits |
| Images | Provide registry access/policy | Build, scan, pin digest |
| Secrets | Provide encrypted delivery mechanism | Own values and rotation request |
| MariaDB/Redis | Operate service, backup, restore | Schema/migration and data validation |
| Ingress/certificates | Provide controller, issuer, DNS process | Declare host/routes within contract |
| Observability | Collect/store/route shared signals | Emit safe metrics/logs and own app alerts |
| Persistent data | Provide documented storage/backup scope | Declare data and test restored behavior |
| Deployment | Provide scoped identity and validation | Own manifests and release rollback |

Resolve every `shared` or ambiguous item into a named procedure and final decision owner.

## Application Manifest Conformance Policy

Reject manifests that:

- target an undeclared namespace or create cluster-scoped resources;
- request privileged mode, host networking/PID/IPC, hostPath, unsafe capabilities, or
  unapproved service-account token access;
- omit required requests/limits/probes/ownership labels;
- use mutable image tags or an unapproved registry;
- create LoadBalancer/NodePort services, ingress classes, storage classes, CRDs, issuers,
  operators, or platform add-ons;
- bypass declared Secret/image-pull mechanisms;
- request unsupported storage/access modes or exceed quotas;
- define unapproved network flows;
- contain likely plaintext credentials or sensitive ConfigMap data.

Document a review path for justified exceptions with owner, expiry, compensating control,
and requalification scope.

## Non-Application Conformance Probe

Use disposable resources bearing a reserved `platform-contract-probe` label, not a sample
application. With the real scoped deployment identity, prove:

1. allowed namespaced dry-run/create/read/update/delete operations;
2. denied cross-namespace, Secret-read, node, CRD, RBAC-escalation, and add-on operations;
3. registry authentication and immutable image pull using a harmless pinned probe image;
4. DNS and explicitly allowed network paths plus one denied path;
5. PVC provisioning only where allowed and documented cleanup/reclaim behavior;
6. ingress, staging TLS, probes, metrics scrape, and safe log collection;
7. Secret mount/reference without revealing its value;
8. quota violation rejection and alert/visibility of a controlled failed workload.

Always remove probe resources and revoke temporary probe credentials. Cleanup failure
blocks handoff.

## Versioning and Change Control

- Use semantic contract versions. Breaking interface/ownership changes increment major;
  backward-compatible additions increment minor; clarifications increment patch.
- Record supported contract versions in application repositories/pipelines.
- Every change identifies affected consumers, migration steps, deprecation date, rollback,
  and which phases require revalidation.
- Changes to cluster identity, data endpoints, secret names, storage behavior, deployment
  identity, ingress class, issuer, or RPO/RTO close the gate until requalified.
- Future GitOps adoption is a major ownership event: pause direct application apply,
  import desired state, prove no destructive diff, transfer ownership, then revoke old
  automation credentials.

## Evidence and Gate State

Write `execution/k3s/.evidence/<environment>/phase-9-application-ready.json` with contract
version/digest, source revision/config hash, Phase 7/8 evidence IDs, all interface checks,
RBAC allow/deny outcomes, probe cleanup, exceptions, owner approvals, and gate state.

Represent the gate as generated evidence/status, not a mutable hand-edited boolean in
desired-state configuration. Gate state is `open` only while its evidence and referenced
platform state remain current.

## Acceptance Tests

Prove:

1. YAML validates against schema and generated Markdown exactly reflects it.
2. All required interfaces have values, owner, security mode, validation, and change
   procedure without embedding secrets.
3. Phase 7/8 evidence matches current cluster and contract inputs.
4. The scoped identity passes every expected allow and deny check.
5. A compliant fixture passes offline and server-side validation; fixtures for every
   prohibited category fail with actionable messages.
6. The disposable conformance probe passes and cleans up fully.
7. Published endpoints are reachable only from intended sources and no admin credential
   is required by application delivery.
8. Contract/report digests verify and the application gate opens only after all required
   checks and approvals pass.

## Completion Gate

Phase 9 completes when the versioned contract is published, current Phase 7/8 evidence
supports it, scoped deployment access and all interfaces pass conformance, ownership is
unambiguous, no secret is disclosed, probe cleanup succeeds, and the generated gate state
is `open`. Only then may a separate application implementation plan apply workloads.

## Non-Goals

- Deploying applications, defining DMOJ architecture, running application migrations,
  adopting GitOps, changing the platform topology, or granting application teams platform
  administrator access.