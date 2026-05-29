# Dashboard Internals

Failure Playground's browser dashboard is the local operations console for realtime events, replay-safe metrics, system health, incidents, and trace correlation.

## Realtime Operational Signals

Operational events are emitted by the API and workers as structured JSON payloads. They are published to Redis pub/sub, persisted in a bounded Redis replay list, and bridged to the browser via `/ws/operations`.

Examples include:

- `task_created`
- `task_enqueued`
- `task_claimed`
- `task_started`
- `task_succeeded`
- `task_failed`
- `task_retried`
- `task_poisoned`
- `worker_heartbeat`
- `worker_processed_count_updated`

Each persisted event includes:

- `event_id`
- `timestamp`
- `event`
- event-specific task/worker fields
- trace fields when available

### Event Replay

The API stores the latest 100 non-heartbeat operational events in Redis. When a dashboard connects, the API sends that replay history first, then streams new live events.

This means a page refresh or WebSocket reconnect does not wipe out the operator's short-term incident context.

### Reconnect Recovery

The dashboard tracks WebSocket connection state:

- Connected
- Disconnected
- Reconnecting
- Reconnected

Unexpected disconnects trigger automatic reconnect with simple exponential backoff. When the socket reconnects, Redis replay restores recent events before live streaming continues.

### Replay-Safe Metrics

Each event has a stable `event_id`. The dashboard keeps a bounded set of received IDs and ignores duplicates. This prevents replayed events from inflating:

- failure-rate calculations
- delivery metrics
- retry counts
- worker throughput
- queue latency
- processing latency
- live event counters
- system health interpretation
- incident workflow transitions

### Operational Interpretation

The realtime dashboard does not only render event rows. It derives short-window operational signals from the event stream:

- Is the system failing recently?
- Are tasks succeeding, retrying, or becoming poison at concerning rates?
- Are workers keeping up?
- Are tasks waiting too long in the queue?
- Are workers spending too long processing tasks?
- Is the current state healthy or degraded?
- Has a degraded state opened, updated, or resolved a local incident?

That operator-facing interpretation is what makes the dashboard more than a WebSocket log viewer.

---

## Operational Dashboard

The browser dashboard is the primary local operations console. It ships from the FastAPI app and uses vanilla JavaScript; there is no separate frontend service.

### Live Event Console

- Realtime event stream over WebSocket
- Redis replay after refresh/reconnect
- Historical replay tagging
- Event severity styling
- Event filtering by task/failure/retry/worker
- Event search
- Pause/resume live stream display
- Event detail drawer with full JSON payload

### Connection Resilience

- Visible connection status badge
- Automatic reconnect with exponential backoff
- Reconnected state before returning to Connected
- WebSocket cleanup on page lifecycle events
- Replay-safe recovery after reconnect

### Failure Rate

- Rolling failure percentage over recent windows
- Retry count display
- Terminal event count display
- Recalculation from replayed history
- Live updates as task outcomes arrive

### Delivery Metrics

- Success rate over the selected recent window
- Retry rate over the selected recent window
- Poison rate over the selected recent window
- Event count used in the calculation
- Rebuilt from Redis replay and updated live after `event_id` deduplication

The panel uses the existing operational event stream:

- `task_succeeded` contributes to success rate
- `task_retried` contributes to retry rate
- `task_poisoned` contributes to poison rate

### Worker Throughput

- Per-worker processing rate
- Rolling 10s / 60s window selector
- Idle workers remain visible as `0/sec`
- Rebuilt from replayed worker events
- Updated live as workers process tasks

### Queue Latency

Queue latency answers:

> How long did this task wait before a worker started it?

Calculation:

```
task_started.timestamp - task_started.queued_at
```

The dashboard prefers replay-resilient fields on `task_started`:

- `queued_at`
- `created_at`

If those are missing, it falls back to matching `task_created` and `task_started` by `task_id`.

Displayed values:

- latest wait
- average wait
- max wait
- recent task count

### Processing Latency

Processing latency answers:

> How long did a worker spend actively processing the task?

Calculation:

```
terminal_event.timestamp - terminal_event.processing_started_at
```

Terminal events:

- `task_succeeded`
- `task_failed`
- `task_poisoned`

The dashboard prefers replay-resilient terminal event fields:

- `started_at`
- `processing_started_at`

If those are missing, it falls back to matching `task_started` by `task_id`.

Displayed values:

- latest processing duration
- average processing duration
- max processing duration
- recent task count

### System Health

The System Health panel provides operator-facing interpretation derived from existing metrics and events.

Possible states:

- **Healthy:** no active pressure or spike detected
- **Queue Pressure:** queue depth or queue wait time indicates workers are falling behind
- **Processing Bottleneck:** workers are spending too long actively processing tasks
- **Failure Spike:** recent terminal outcomes are failing at a high rate

The panel includes the reason for the selected state, such as queue depth, recent failure percentage, average queue wait, or average processing duration.

The logic is intentionally simple and explainable. It is derived from:

- `/metrics` queue depth and task counts
- replay-safe failure-rate events
- worker heartbeat freshness
- queue latency samples
- processing latency samples

### Incident Workflow

The Incident Workflow panel turns System Health into a small local operator workflow.

When System Health enters a non-Healthy state, the dashboard creates or updates one active incident for the continuous degraded period. The incident record includes:

- incident id
- incident type / health state
- status
- created timestamp
- acknowledged timestamp
- resolved timestamp
- summary

Supported incident states:

- **active:** System Health is currently degraded and the incident has not been acknowledged
- **acknowledged:** an operator clicked Acknowledge in the dashboard
- **resolved:** System Health returned to Healthy

Acknowledgement is frontend-only and does not call the backend. Resolved incidents remain visible in Incident History, and the current workflow state is stored in browser-local state so a refresh can reconstruct the most recent incident context as far as the replayed health signals allow.

### Trace Correlation

Task lifecycle events include OpenTelemetry trace fields when a span is active:

- `trace_id`
- `span_id`

The event detail drawer displays those fields and shows an **Open Trace** action when `trace_id` is present.

Flow:

```
dashboard event
      |
      v
trace_id / span_id
      |
      v
Open Trace
      |
      v
Jaeger: http://localhost:16686/trace/{trace_id}
```

This makes a live failure, retry, or poison event directly actionable: the operator can jump from a realtime dashboard event to the distributed trace for that task.
