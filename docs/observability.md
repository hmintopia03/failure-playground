# Observability Details

Failure Playground connects structured logs, Prometheus metrics, Grafana dashboards, OpenTelemetry traces, Jaeger, and realtime operational signals into one local investigation loop.

## Observability Layers

Failure Playground uses four observability layers, each answering a different question:

| Layer | Tooling | Question |
|-------|---------|----------|
| Logs | Structured JSON logs | What happened? |
| Metrics | Prometheus + Grafana | How much, how often, and how saturated? |
| Traces | OpenTelemetry + Jaeger | How did one task move through the system? |
| Realtime signals | Redis pub/sub + WebSocket dashboard | What is happening right now, and what should an operator notice? |

### Structured Logs

The backend emits structured JSON logs for task lifecycle events, worker behavior, retries, failures, and health updates. These logs are designed to be machine-parseable and useful during debugging.

### Prometheus and Grafana

`/prometheus` exposes metrics such as:

- `failure_playground_tasks_queued`
- `failure_playground_tasks_processing`
- `failure_playground_tasks_success`
- `failure_playground_tasks_failed`
- `failure_playground_tasks_poison`
- `failure_playground_tasks_poison_failed`
- `failure_playground_redis_queue_length`
- `failure_playground_workers_alive`
- `failure_playground_workers_stale`

Grafana is provisioned through Docker Compose with a Prometheus datasource and dashboard panels for queue pressure, task state, worker health, retry/failure behavior, and throughput.

### Grafana Dashboard

Prometheus metrics are visualized through Grafana dashboards
covering queue pressure, latency, throughput, and worker health.

![Grafana Dashboard](../backend/images/grafana.png)

### OpenTelemetry and Jaeger

Traced services:

- `failure-playground-api`
- `failure-playground-worker`

Worker spans include:

```
worker.process_task
worker.claim_task
worker.retry_task
worker.fail_task
worker.complete_task
worker.recover_stuck_task
```

Worker polling is intentionally not heavily traced. Empty queue polls would dominate Jaeger and obscure the task-processing spans that matter.

---

## Trace Examples

### Distributed Trace Example

The dashboard can jump directly from a realtime event
to the matching Jaeger trace.

![Jaeger Trace](../backend/images/jaeger-trace.png)
