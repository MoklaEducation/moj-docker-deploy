# Strategy Visualizations

Status: visual companion to the deployment and evolution strategies.

## How to Read the Strategy

The strategy is not one staircase and not one maturity score for the whole platform. It
has five related dimensions:

```mermaid
flowchart TB
    P[Phase<br/>Where in delivery?]
    C[Capability<br/>What are we building?]
    M[Maturity<br/>How thoroughly is it proven?]
    O[Ownership<br/>Who may change it?]
    E[Evidence<br/>For which state, target, and time?]
    Q[Qualified platform capability]

    P --> Q
    C --> Q
    M --> Q
    O --> Q
    E --> Q
```

- **Phase** provides dependency order and a completion gate.
- **Capability** is the small unit that is implemented and tested.
- **Maturity** records the depth of proof for that capability.
- **Ownership** prevents two tools or teams from controlling the same state.
- **Evidence** makes a result valid only for exact inputs, versions, target, and time.

A statement such as “Phase 6 is complete” therefore means that every required Phase 6
capability reached its required maturity, stayed within its ownership boundary, and has
current evidence. It does not mean every platform capability has the same maturity.

## Phase Flow with Feedback

The main delivery direction is left to right. Dashed arrows show expected learning loops,
not exceptional project failure.

```mermaid
flowchart LR
    P1[1 Preflight] --> P2[2 Host baseline]
    P2 --> P3[3 Data services]
    P3 --> P4[4 k3s]
    P4 --> P5[5 Cluster core]
    P5 --> P6[6 Add-ons]
    P6 --> P7[7 Validation]
    P7 --> P8[8 Recovery]
    P8 --> P9[9 App handoff]

    P7 -. host or schema finding .-> P1
    P7 -. policy finding .-> P5
    P8 -. data recovery finding .-> P3
    P8 -. cluster recovery finding .-> P4
    P9 -. interface gap .-> P5
    P9 -. operational gap .-> P6
```

When a later phase exposes an earlier defect, reopen the owning phase, update its
automation and tests, invalidate affected evidence, and rerun only the dependent gates.
Do not continue forward with a known false assumption.

## Capability Maturity Spiral

Each capability repeatedly travels around the same learning loop. The loop becomes a
spiral because each pass should retain more automation, evidence, and operational
knowledge than the previous pass.

```mermaid
flowchart LR
    H[State a testable hypothesis] --> I[Implement smallest path]
    I --> V[Validate behavior]
    V --> F[Exercise a failure]
    F --> C[Classify the result]
    C --> U[Update code, plan, and tests]
    U --> R[Rebuild or reapply cleanly]
    R --> V

    V -. first success .-> L1[Level 1 Demonstrated]
    R -. stable second run .-> L2[Level 2 Repeatable]
    F -. bounded failures .-> L3[Level 3 Failure-aware]
    C -. recovery proven .-> L4[Level 4 Recoverable]
    U -. monitoring and runbook .-> L5[Level 5 Operable]
    R -. independent rehearsal .-> L6[Level 6 Reproducible]
```

Maturity levels are evidence labels, not time estimates. A backup job may be repeatable
at Level 2 while its restore capability remains only demonstrated at Level 1. Track the
lower defensible level until the missing behavior is proven.

## Capability Board

Use this matrix as the main implementation dashboard. One row represents one capability,
not an entire phase.

| Capability | Owner | Introduced | Current maturity | Required at next gate | Evidence | Main blocker |
| --- | --- | --- | --- | --- | --- | --- |
| Host firewall | Ansible host baseline | Phase 2 | Record during implementation | Phase 2 acceptance | Evidence ID | Finding ID or none |
| MariaDB restore | Host data-service operations | Phase 3 | Record during implementation | Phase 3 isolated restore | Evidence ID | Finding ID or none |
| k3s state recovery | Host/k3s recovery | Phase 4 | Record during implementation | Phase 8 clean restore | Evidence ID | Finding ID or none |
| Default-deny policy | Kustomize cluster core | Phase 5 | Record during implementation | Phase 5 enforcement | Evidence ID | Finding ID or none |
| Certificate renewal | Helm add-on plus owned resources | Phase 6 | Record during implementation | Phase 6 or bounded exception | Evidence ID | Finding ID or none |
| Alert delivery | Helm add-on plus owned rules | Phase 6 | Record during implementation | Phase 6 end-to-end test | Evidence ID | Finding ID or none |

Extend the board as capabilities are introduced. Keep evidence references and findings in
the board, but keep credentials and verbose logs in their approved external locations.

## Failure Routing

This decision path keeps “try it again” from becoming the default response to every
failure.

```mermaid
flowchart TD
    X[Operation failed] --> K{State and cause known?}
    K -- No --> STOP[Fail closed and investigate]
    K -- Yes --> T{Transient and idempotent?}
    T -- Yes --> RETRY[Bounded retry with backoff]
    T -- No --> SAFE{Target identity and integrity safe?}
    SAFE -- No --> STOP
    SAFE -- Yes --> PART{Checkpoint postconditions pass?}
    PART -- Yes --> RESUME[Resume from named checkpoint]
    PART -- No --> DECL{Declarative state understood?}
    DECL -- Yes --> FORWARD[Correct input and roll forward]
    DECL -- No --> GOOD{Compatible known-good state exists?}
    GOOD -- Yes --> BACK[Explicit rollback]
    GOOD -- No --> RECOVER[Guarded rebuild or restore]

    RETRY --> VERIFY[Revalidate and capture evidence]
    RESUME --> VERIFY
    FORWARD --> VERIFY
    BACK --> VERIFY
    RECOVER --> VERIFY
    VERIFY --> LEARN[Update finding, automation, test, and plan]
```

Authentication, authorization, integrity, policy, identity, destructive-operation, and
unknown-state failures bypass retry and go to investigation or guarded recovery.

## Ownership Boundaries

```mermaid
flowchart TB
    ENV[Environment inputs<br/>non-secret references]
    SEC[Encrypted external secrets]
    ANS[Ansible<br/>host, Docker, k3s install]
    KUS[Kustomize<br/>owned cluster resources]
    HELM[Helm<br/>third-party add-ons]
    OPS[Operations<br/>validate, backup, restore]
    APP[Application delivery<br/>namespaced workloads only]

    ENV --> ANS
    ENV --> KUS
    ENV --> HELM
    SEC --> ANS
    SEC --> KUS
    SEC --> HELM
    ANS --> KUS
    KUS --> HELM
    ANS --> OPS
    KUS --> OPS
    HELM --> OPS
    OPS --> APP
```

Arrows show dependency or consumption, not shared ownership. Ansible may invoke a
Kustomize or Helm workflow, but it does not become owner of the resulting Kubernetes
objects. Future GitOps adoption replaces the direct Kustomize/Helm reconciliation owner;
it does not run concurrently as a second owner.

## Evidence Dependency and Invalidation

Evidence is a dependency graph, not a permanent certificate.

```mermaid
flowchart LR
    E1[Phase 1 evidence] --> E2[Phase 2 evidence]
    E2 --> E3[Phase 3 evidence]
    E3 --> E4[Phase 4 evidence]
    E4 --> E5[Phase 5 evidence]
    E5 --> E6[Phase 6 evidence]
    E6 --> E7[Phase 7 report]
    E7 --> E8[Phase 8 recovery report]
    E8 --> E9[Phase 9 open gate]

    CHANGE[Input, version, ownership,<br/>identity, or recovery change]
    CHANGE --> OWNER[Reopen owning phase]
    OWNER --> IMPACT[Mark dependent evidence stale]
    IMPACT --> TEST[Revalidate affected path]
    TEST --> E9
```

A change does not always require rerunning every phase. Start at the phase that owns the
changed assumption, identify consumers of its contract, and rerun that dependency path.
A cluster identity or recovery-authority change usually has broad impact; a dashboard
wording change usually does not.

## Three Operating Loops

The overall strategy can be remembered as three nested loops:

```mermaid
flowchart TB
    subgraph Daily[Capability loop: minutes to days]
        D1[Implement] --> D2[Test]
        D2 --> D3[Learn]
        D3 --> D1
    end

    subgraph Phase[Phase loop: days to weeks]
        P1[Integrate capabilities] --> P2[Run phase gate]
        P2 --> P3[Resolve findings]
        P3 --> P1
    end

    subgraph Platform[Platform loop: releases]
        R1[Clean deployment] --> R2[Platform validation]
        R2 --> R3[Recovery rehearsal]
        R3 --> R4[Publish contract]
        R4 --> R1
    end

    Daily --> Phase
    Phase --> Platform
```

- The **capability loop** improves one behavior quickly.
- The **phase loop** proves that related capabilities work together.
- The **platform loop** proves clean deployment, operations, recovery, and consumer
  contracts as one system.

The loops continue after initial application readiness for upgrades, capacity changes,
security improvements, and eventual GitOps adoption.

## Practical Reading Order

When planning work, read the diagrams in this order:

1. Use the phase flow to choose the current delivery boundary.
2. Use the capability board to choose one small owned behavior.
3. Use the maturity spiral to choose the next missing proof.
4. Use failure routing when a check fails.
5. Use the evidence graph to determine what must be revalidated.
6. Use the ownership diagram before changing tools or responsibility.

This keeps iteration deliberate: move forward when evidence supports it, loop locally
when learning is contained, and reopen earlier phases when a foundational assumption
changes.