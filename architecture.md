# Architecture

This document describes the full Failure Playground architecture, including the API control plane, worker execution path, Redis event bus, dashboard analysis layer, tracing, metrics, and CI/CD validation.

                                  +-------------------+
                                  | WebSocket         |
                                  | Dashboard         |
                                  |                   |
                                  | - live events     |
                                  | - event details   |
                                  | - Open Trace      |
                                  +---------+---------+
                                            |
                                            | derives replay-safe operator metrics
                                            v
            +---------------------------------------------------------------+
            | Dashboard Analysis                                            |
            | - Failure Rate Metrics                                        |
            | - Queue Latency Metrics                                       |
            | - Processing Latency Metrics                                  |
            | - Per-worker Throughput                                       |
            | - System Health Analysis                                      |
            | - Incident Workflow                                           |
            +---------------------------------------------------------------+
                                            ^
                                            |
                         replay + live      |      WebSocket /ws/operations
                         events             |
                                            |
+------------+     HTTP      +--------------+---------------+
| Operators  +-------------->| FastAPI API                  |
| / clients  |               | - REST control plane         |
+------------+               | - WebSocket bridge           |
                             | - Prometheus endpoint        |
                             +------+-----------+-----------+
                                    |           |
                  task state/logs   |           | enqueue task IDs
                                    v           v
                         +----------+--+     +--+----------------+
                         | PostgreSQL |     | Redis Queue        |
                         | - tasks    |     | - task IDs         |
                         | - logs     |     +--+----------------+
                         | - workers  |        |
                         | - state    |        | dequeue task IDs
                         +----------+-+        v
                                    |     +----+----------------+
                                    |     | Workers             |
                                    |     | - claim tasks       |
                                    |     | - process/retry     |
                                    |     | - heartbeat         |
                                    |     +----+----------------+
                                    |          |
                                    |          | operational events
                                    |          v
                                    |     +----+----------------+
                                    |     | Redis Pub/Sub       |
                                    |     | Event Bus           |
                                    |     +----+----------------+
                                    |          |
                                    |          | persisted recent events
                                    |          v
                                    |     +----+----------------+
                                    |     | Redis Replay        |
                                    |     | History             |
                                    |     | latest 100 events   |
                                    |     +----+----------------+
                                    |          |
                                    +----------+-------> FastAPI WebSocket bridge

        +--------------------+                 +------------------+
        | OpenTelemetry      | spans/traces    | Jaeger           |
        | API + Workers      +---------------->| trace UI         |
        +--------------------+                 +------------------+
                                                        ^
                                                        |
                    Dashboard Event -> Trace ID --------+

        +--------------------+   scrape /prometheus   +------------------+
        | Prometheus         |<----------------------- | FastAPI API      |
        +---------+----------+                         +------------------+
                  |
                  v
        +--------------------+
        | Grafana            |
        | system dashboards  |
        +--------------------+