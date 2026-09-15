# Deployment Instrumentation Strategy

## Purpose

This document records the observability strategy for DMOJ, Keycloak, and future education, communication, home-automation, security, and AI services.

The goal is to start with low-effort operational visibility and add application instrumentation only where it provides meaningful value.

## Current Assessment

The current DMOJ stack already produces useful container and application logs:

- Nginx access and error logs
- DMOJ/uWSGI logs
- Django and judge Python logging
- Celery logs
- Keycloak logs
- MariaDB and Redis container logs

The repository does not currently provide a complete Prometheus metrics endpoint or OpenTelemetry tracing across the application and worker flows.

## Observability Components

### Prometheus

Prometheus collects numeric time-series metrics.

Infrastructure metrics can be added with little or no DMOJ code change:

- Node Exporter for VM CPU, memory, disk, and network
- cAdvisor for container CPU, memory, restarts, and limits
- MariaDB exporter for database connections, queries, and health
- Redis exporter for memory, commands, and latency
- Nginx exporter for request counts and response status

Application metrics require instrumentation. Useful DMOJ metrics include:

- HTTP request count and latency
- Login success and failure counts
- OIDC discovery and callback failures
- Submission queue length
- Submission execution duration
- Compile failures and judge results
- Celery task count, duration, and failures
- Database query latency
- Rate-limit and authentication failures

Possible tools:

- `django-prometheus`
- Prometheus Python client
- Celery instrumentation
- MariaDB exporter
- Redis exporter

### Loki

Loki is the easiest first addition because the stack already logs to container output.

Use Grafana Alloy or Promtail to collect Docker logs from:

- DMOJ site and uWSGI
- Celery
- Bridge and judge services
- Nginx
- Keycloak
- MariaDB
- Redis

Loki can provide value without significant application changes. Improve the logs gradually by using structured JSON fields such as service, environment, request ID, user ID where appropriate, severity, and event type.

Never log:

- Passwords
- OIDC client secrets
- Access tokens or refresh tokens
- Private keys
- Unnecessary personal profile data
- Unredacted AI prompts containing private information
- Camera or home-security data without an explicit retention policy

### Tempo

Tempo stores distributed traces. Unlike log collection, useful tracing requires instrumentation and trace-context propagation.

Potential trace path:

```text
Browser
  -> Nginx
  -> Django/uWSGI
  -> MariaDB or Redis
  -> Celery
  -> Judge worker
  -> Keycloak or external API
```

Possible tools:

- OpenTelemetry Python SDK
- Django OpenTelemetry instrumentation
- SQL instrumentation
- Redis instrumentation
- Requests or HTTPX instrumentation
- Celery instrumentation
- OpenTelemetry Collector
- Grafana Tempo

Tempo should be introduced after basic metrics and logs are working. It is most useful when a request crosses several services and logs alone cannot explain latency or failure.

## Recommended Rollout

### Stage 1: Infrastructure and logs

No application code changes required:

```text
Node Exporter
cAdvisor
MariaDB exporter
Redis exporter
Grafana Alloy or Promtail
Prometheus
Loki
Grafana
```

Initial dashboards should show:

- VM CPU, memory, disk, and network
- Container health and restart count
- Database health and connections
- Redis health and memory
- Nginx request rates and status codes
- Keycloak availability and recent errors
- Disk and log growth

### Stage 2: DMOJ application metrics

Add a small, focused metrics layer to DMOJ:

- Request latency and status codes
- Local-login and Keycloak-login outcomes
- OIDC discovery and callback errors
- Submission queue depth
- Judge execution time
- Compile and runtime result counts
- Celery task failures

Use labels carefully. Do not use unbounded labels such as username, email, submission ID, or arbitrary URL parameters.

### Stage 3: Distributed tracing

Add OpenTelemetry to the highest-value paths:

- Django request handling
- Database and Redis calls
- Celery task dispatch and execution
- Judge submission lifecycle
- Keycloak/OIDC requests
- Future AI API calls

Send traces through an OpenTelemetry Collector before Tempo so sampling, filtering, and export policy remain centralized.

## DMOJ-Specific Considerations

- The DMOJ stack contains synchronous web requests, Celery work, bridge/judge processes, Redis, MariaDB, and auxiliary rendering services.
- Submission execution should be measured separately from web request latency.
- Judge workers need queue, execution, timeout, and failure metrics.
- OIDC login should expose failure categories without recording credentials or tokens.
- Existing Python loggers provide a useful starting point for Loki.
- Nginx and uWSGI access information can help correlate requests before full tracing is added.

## Future Services

For course, chat, quiz, testing, AI, home-automation, family-communication, and home-security services:

- Standardize log fields across services.
- Use a shared request or correlation ID.
- Expose a `/metrics` endpoint where practical.
- Propagate W3C trace context for service-to-service calls.
- Define data-retention rules before collecting personal or security-sensitive data.
- Keep AI, locks, alarms, and camera systems subject to explicit quotas and access controls.
- Do not allow observability tooling to become an unrestricted path into production data.

## Cost and Privacy Controls

Observability can become expensive through log and trace volume rather than CPU alone.

Control cost with:

- Log rotation
- Short retention for debug logs
- Longer retention only for audit/security events
- Trace sampling
- Metrics label limits
- Filtering noisy health checks
- Separate retention policies for education and home-security data
- Local aggregation before sending data to a hosted service

Keep personal information out of labels and avoid storing complete request bodies by default.

## Resource Planning

For a small DMOJ deployment, observability can be lightweight if retention, labels, and trace sampling are controlled.

Approximate additional resource use:

| Component | CPU | RAM | Main cost driver |
| --- | ---: | ---: | --- |
| Node Exporter | Very low | 20-50 MB | Host metrics |
| cAdvisor | Low | 50-150 MB | Container metrics |
| MariaDB exporter | Very low | 20-50 MB | Database metrics |
| Redis exporter | Very low | 10-30 MB | Redis metrics |
| Grafana Alloy or Promtail | Low | 50-200 MB | Log volume |
| Prometheus | Low to moderate | 200-600 MB | Scrape count and retention |
| Grafana | Moderate | 200-500 MB | Dashboard queries |
| Loki | Moderate | 300 MB-1 GB | Log volume and retention |
| OpenTelemetry Collector | Low | 100-300 MB | Telemetry volume |
| Tempo | Low to moderate | 200 MB-1 GB | Trace volume and retention |

For the current low-volume deployment, plan approximately:

```text
Prometheus, Grafana, Loki, exporters, and log collection:
  0.5-1 vCPU
  1.5-2 GB RAM
  20-40 GB disk initially
```

Adding Tempo and distributed tracing may increase the observability allocation to:

```text
  1-2 vCPU during activity
  2-4 GB RAM
  20-100+ GB disk depending on retention
```

On a single burstable VM with approximately 2 vCPU and 8 GB RAM, the core DMOJ services, Keycloak, MariaDB, Redis, Nginx, and the Stage 1 observability stack can coexist. Keep at least 1-2 GB RAM and CPU headroom for judge workers, builds, and traffic bursts.

Judge compilation and execution is the unpredictable workload. Set explicit container limits and monitor CPU credits on burstable VMs. Delay Tempo until metrics and logs show a concrete cross-service debugging need.

Network use is usually small for exporters and metrics. Logs and traces are the larger variables. Use 15-30 second scrape intervals, log filtering, rotation, trace sampling, short retention, and no request-body collection by default.

Track these capacity signals:

- VM CPU percentage and burst-credit balance
- Available memory and swap activity
- MariaDB slow queries and connections
- Redis memory and latency
- Judge queue length and execution time
- Container restarts
- Disk and log growth
- Prometheus, Loki, and Tempo storage growth

## Recommended Initial Stack

For the current small deployment:

```text
Prometheus + Grafana
Loki + Grafana Alloy or Promtail
Node Exporter
cAdvisor
MariaDB exporter
Redis exporter
```

Add Tempo and OpenTelemetry after the first metrics and log dashboards identify a concrete cross-service debugging need.

## Completion Checklist

```text
[ ] Container logs are collected centrally.
[ ] Log rotation and retention are configured.
[ ] VM and container metrics are available.
[ ] MariaDB and Redis metrics are available.
[ ] Keycloak health and login failures are visible.
[ ] DMOJ submission queue and judge health are measurable.
[ ] Sensitive values are excluded from logs, labels, and traces.
[ ] Backup and retention policies cover observability data.
[ ] Trace instrumentation is added only for high-value workflows.
```
