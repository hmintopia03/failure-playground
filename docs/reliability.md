# Reliability Mechanics

Failure Playground models backend reliability behaviors that appear in distributed task processing systems: retries, poison tasks, stuck work, duplicate delivery, reconnect recovery, bounded replay, and replay-safe metric reconstruction.

## Backend Systems

### Task Queue

The API creates task records in PostgreSQL and enqueues task IDs in Redis. Workers pull IDs from Redis, claim queued tasks, and update PostgreSQL as the task moves through processing, success, retry, failure, or poison states.

This separation is deliberate: the queue and database can disagree, and the worker logic has to handle duplicate claims, stuck tasks, retry cooldowns, and missing task IDs.

### Worker Lifecycle

Workers are independent processes responsible for:

- Pulling task IDs from Redis
- Claiming queued tasks (`queued -> processing`)
- Simulating success or failure
- Retrying failed work with exponential backoff
- Marking poison tasks as terminal failures
- Recording processing duration
- Updating heartbeat records
- Publishing realtime operational events
- Creating OpenTelemetry spans for task lifecycle operations

### Reliability Behaviors

- **Heartbeats:** workers update heartbeat rows; stale workers are visible in the dashboard.
- **Stuck task recovery:** long-running `processing` tasks are recovered and re-queued or failed.
- **Retry cooldowns:** retries are scheduled instead of immediate to avoid tight loops.
- **Poison handling:** poison tasks eventually become terminal failures.
- **Duplicate prevention:** workers skip tasks that are no longer queued.
- **Rate limiting:** workers can throttle processing when they exceed configured limits.
- **System pause/resume:** operators can pause and resume task processing.

---

## Operational Resilience Features

### WebSocket Reconnect Recovery

The dashboard reconnects automatically when `/ws/operations` closes unexpectedly. It uses a simple backoff sequence up to a maximum delay and exposes state through the UI so operators can see whether the live stream is connected, disconnected, reconnecting, or recently reconnected.

### Redis Replay Persistence

The API keeps a bounded Redis history of the latest 100 non-heartbeat operational events. New dashboard clients receive replay first, then live events.

This keeps recent context available across:

- page refresh
- browser reconnect
- API/WebSocket restart
- short network interruption

### Event Deduplication

Every persisted event has an `event_id`. The dashboard deduplicates by that ID before updating live event counters or derived metrics.

This protects the dashboard from double-counting when the same event is replayed and then received live.

### Replay-Safe Metric Reconstruction

The dashboard rebuilds derived metrics from replayed events:

- failure rate
- delivery metrics
- retries
- per-worker throughput
- queue latency
- processing latency
- system health
- incident workflow state

Latency events carry enough timestamp context to survive replay trimming:

- `task_started.created_at`
- `task_started.queued_at`
- terminal event `started_at`
- terminal event `processing_started_at`

When those fields are available, metrics do not require both sides of an event pair to still exist in the 100-event replay window.

---

## Failure Scenarios Supported

- Random task failure
- Retry with exponential backoff
- Permanent failure after max retries
- Poison tasks
- Queue pressure and backlog
- Slow processing / processing bottlenecks
- Stale workers
- Duplicate task prevention
- Stuck task recovery
- System pause/resume
- Redis queue clearing
- Degraded dependency health
- WebSocket disconnect and reconnect

---

## Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Operational dashboard |
| GET | `/docs` | FastAPI documentation |
| GET | `/health` | API, PostgreSQL, and Redis health |
| GET | `/metrics` | Human-readable metrics |
| GET | `/prometheus` | Prometheus scrape endpoint |
| WS | `/ws/operations` | Realtime operational event stream |
| POST | `/tasks` | Create a normal or poison task |
| POST | `/tasks/bulk` | Create multiple tasks |
| POST | `/tasks/{task_id}/retry` | Manually retry a task |
| POST | `/tasks/{task_id}/duplicate` | Duplicate a task |
| GET | `/tasks` | Paginated and filterable task list |
| GET | `/tasks/{task_id}` | Task detail |
| GET | `/logs` | Paginated task logs |
| GET | `/workers` | Worker heartbeat and processed counts |
| POST | `/workers/reset-counts` | Reset worker processed counts |
| GET | `/alerts` | Operational alerts |
| DELETE | `/alerts` | Clear alerts |
| GET | `/system-state` | Pause/resume state |
| POST | `/pause` | Pause task processing |
| POST | `/resume` | Resume task processing |
| DELETE | `/queue` | Clear Redis queue |
| DELETE | `/reset` | Reset system state |
| GET | `/report` | HTML system report |
| GET | `/dead-letter` | Dead-letter task view |

---

## Tests

From the `backend` directory:

```bash
cd backend
pytest -v
```

The test suite covers:

- task creation and API behavior
- Redis queue enqueue/dequeue behavior
- queue length and clear behavior
- system pause/resume
- pagination, filtering, and validation
- structured event logging
- Redis event persistence and replay
- trace context propagation in event payloads
- worker success, retry, final failure, poison, and recovery paths
- queue-latency and processing-latency event payload fields

Tests use pytest, FastAPI TestClient, temporary SQLite databases, and fake Redis implementations where appropriate.

---

## Version History

### v5.0 - GitHub Actions CI/CD

- Added GitHub Actions workflow for push and pull request checks on `main`
- Set up Python 3.13 and backend dependency installation in CI
- Runs backend tests with `pytest`
- Keeps lint and format validation ready for existing project tooling without introducing new heavy dependencies
- Builds API and worker Docker images from the existing backend Dockerfile
- Validates Docker Compose configuration
- Validates Kubernetes manifests against a kind cluster with `kubectl apply --dry-run=server`
- Existing application architecture and runtime behavior preserved

### v4.0-d - README Production Polish

- Reframed the project as a platform engineering and observability portfolio system
- Clarified architecture across API, workers, Redis, PostgreSQL, WebSocket dashboard, OpenTelemetry, Jaeger, Prometheus, Grafana, and Kubernetes
- Added release progression from v1 through v4
- Improved Kubernetes deployment, verification, observability access, limitations, and roadmap documentation
- Existing Docker Compose workflow preserved

### v4.0-c ??Kubernetes Worker Autoscaling

- Worker Deployment now has CPU and memory requests and limits
- Added `worker-hpa` HorizontalPodAutoscaler
- Worker autoscaling keeps 2 to 5 replicas
- HPA targets 70% average CPU utilization
- Documented `metrics-server` requirement for local Kubernetes clusters
- Existing Docker Compose workflow preserved

### v4.0-b ??Kubernetes Observability Stack Migration

- Kubernetes manifests for Jaeger, Prometheus, and Grafana
- Jaeger exposed through `jaeger-service` on UI, OTLP gRPC, and OTLP HTTP ports
- API and workers export OpenTelemetry traces to `http://jaeger-service:4317`
- Prometheus config migrated to a Kubernetes ConfigMap
- Prometheus scrapes the API through `api-service:8000`
- Prometheus exposed through `prometheus-service`
- Grafana exposed through `grafana-service`
- Grafana dashboard provisioning may remain Docker Compose-first for now
- Existing Docker Compose workflow preserved

### v4.0-a ??Kubernetes Core Stack Migration

- Kubernetes manifests for the core API, workers, Redis, and PostgreSQL stack
- API exposed through `api-service`
- PostgreSQL exposed through `postgres-service`
- Redis exposed through `redis-service`
- Worker deployment replaces `worker-a` and `worker-b` with 2 replicas
- Worker pod names are used as worker names through the Kubernetes Downward API
- Shared ConfigMap for local Kubernetes runtime configuration
- PostgreSQL PersistentVolumeClaim for local database persistence
- Observability stack migration explicitly deferred to v4.0-b
- Existing Docker Compose workflow preserved

### v3.7 ??Incident Workflow

- Incident Workflow panel driven by System Health state
- Active, acknowledged, and resolved incident states
- Frontend acknowledgement without backend API calls
- Automatic incident resolution when System Health returns to Healthy
- Incident records with id, type, status, timestamps, and summary
- Local reconstruction across refresh/reconnect using replay-safe health inputs and browser-local workflow state

### v3.6 ??Dashboard Delivery Metrics

- Delivery Metrics panel
- Success rate, retry rate, and poison rate over recent windows
- Replay-safe reconstruction from Redis event history
- Reconnect-safe and refresh-safe calculations through `event_id` deduplication

### v3.5 ??System Health and Bottleneck Detection

- System Health panel
- Healthy / Queue Pressure / Processing Bottleneck / Failure Spike states
- Operator-facing explanation for each selected state
- Health interpretation derived from existing metrics and replay-safe event samples

### v3.4 ??Processing Latency Visualization

- Processing latency panel
- Active processing duration from terminal event timestamp minus processing start timestamp
- Terminal events include `started_at` / `processing_started_at`
- Replay-resilient processing latency reconstruction
- Success, failed, and poison terminal outcomes included

### v3.3 ??Queue Latency Visualization

- Queue latency panel
- Queue wait time from `task_started.timestamp - queued_at/created_at`
- `task_started` includes `created_at` / `queued_at`
- Fallback matching by `task_id` when direct timestamps are unavailable
- Replay-resilient queue latency reconstruction

### v3.2 ??Jaeger Trace Links

- Event detail drawer includes an Open Trace action when `trace_id` exists
- Local Jaeger links use `http://localhost:16686/trace/{trace_id}`
- Events without trace context hide the trace action

### v3.1 ??Trace Correlation in Realtime Events

- Task lifecycle events include `trace_id` and `span_id` when tracing is active
- Replayed events preserve trace fields
- Dashboard event detail drawer displays trace fields

### v2.4 ??Per-Worker Throughput

- Worker Throughput panel
- Rolling 10s / 60s per-worker processing rates
- Idle workers remain visible as `0/sec`
- Rebuilt from replayed worker events

### v2.3 ??Rolling Failure Rate

- Rolling failure-rate visualization
- Retry count and terminal event count
- Recalculation from replayed event history
- Replay-safe failure/retry metrics

### v2.2 ??Event Persistence and Replay

- Redis-backed latest-100 operational event history
- Replay on dashboard connect/reconnect
- `event_id`-based deduplication
- Historical replay tagging in the live event stream

### v2.1 ??WebSocket Reconnect Handling

- Automatic reconnect after unexpected WebSocket close
- Exponential backoff
- Connection status badge
- Reconnected state without page refresh
- Cleanup of sockets and timers on page lifecycle events

### v2.0 ??Realtime Operations Dashboard

- Redis pub/sub operational event bus
- FastAPI `/ws/operations` WebSocket bridge
- Live event stream with filtering and search
- Worker heartbeat cards
- Stale worker detection and recovery tracking
- Failure spike alert banner
- Toast notifications
- Incident history
- Event detail drawer
- Severity-based event styling

### v1.5 ??Observability Foundation

- OpenTelemetry tracing across API and workers
- Custom worker spans
- Jaeger integration
- Prometheus metrics
- Grafana provisioning
- Structured JSON logging
- Alembic migrations
- Backend tests and GitHub Actions CI

### v1.0 ??Backend Foundation

- FastAPI control plane
- PostgreSQL persistence
- Redis-backed task queue
- Worker queue consumers
- Retry, backoff, and poison-task handling
- Stuck task recovery
- System pause/resume
- Polling-based dashboard

---

## Next Roadmap

- **v5.1:** Prometheus alert rules for queue pressure, worker health, failure spikes, and dependency degradation.
- **v5.2:** RBAC for dashboard operations, separating read-only visibility from destructive controls.
- **v6.0:** Kafka or another durable event-streaming layer for replay, consumer lag, partitioning, and event retention experiments.
