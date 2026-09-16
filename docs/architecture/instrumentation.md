# Instrumentation and Observability

See [Platform Decisions](decisions.md) for Layer 4 ownership. This document covers observability only; it does not define application, image, or k3s architecture.

## Goal

Provide useful failure, capacity, and security visibility without collecting credentials, tokens, request bodies, or unnecessary personal data.

## Phased Rollout

### Phase 1: Infrastructure Metrics and Central Logs

Deploy independently under `infra/addons/observability`:

- Prometheus and Grafana
- Loki with Grafana Alloy or Promtail
- Node Exporter and cAdvisor
- MariaDB and Redis exporters

Dashboards must cover host capacity, container restarts, DMOJ HTTP status/latency, MariaDB/Redis health, disk/log growth, and Keycloak availability when enabled.

### Phase 2: Focused DMOJ Metrics

Instrument only measurable operational paths:

- HTTP response status and latency
- local and OIDC login outcomes by failure class
- judge queue depth and execution duration
- Celery task failures and durations
- database latency

Do not use usernames, emails, submission IDs, tokens, or arbitrary URLs as metric labels.

### Phase 3: Distributed Tracing

Add OpenTelemetry only after logs and metrics expose a genuine cross-service debugging gap. Send traces through an OpenTelemetry Collector before Tempo; apply sampling and retention centrally.

## Data and Capacity Rules

- Never log passwords, OIDC secrets, access/refresh tokens, private keys, or full request bodies.
- Keep debug logs short-lived; define longer retention only for audited security events.
- Start with 15-30 second metric scrape intervals and short log retention.
- Measure growth before adding Tempo. Logs and traces, not metrics, drive most storage cost.
- Set explicit resource limits and alert on memory pressure, restarts, disk growth, judge backlog, and database saturation.

## Validation

1. Confirm each collector/exporter has a health endpoint and target is up.
2. Generate a harmless DMOJ request and locate its access/application logs.
3. Confirm no sensitive headers, tokens, or credentials appear.
4. Trigger a controlled failed login and verify a bounded failure metric/log event.
5. Test alert delivery before treating monitoring as operational.
