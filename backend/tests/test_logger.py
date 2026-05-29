import json

import logger
from opentelemetry import trace
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
)


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.published = []

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    def publish(self, channel, message):
        self.published.append((channel, message))


def test_log_event_outputs_json(caplog, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(logger, "redis_client", fake_redis)

    with caplog.at_level("INFO", logger="failure_playground"):
        logger.log_event(
            "task_created",
            task_id=123,
            status="queued",
        )

    assert len(caplog.records) == 1

    payload = json.loads(caplog.records[0].message)

    assert payload["event"] == "task_created"
    assert payload["task_id"] == 123
    assert payload["status"] == "queued"
    assert "event_id" in payload
    assert "timestamp" in payload

    assert fake_redis.published == [
        (logger.OPERATIONS_CHANNEL, caplog.records[0].message)
    ]
    assert fake_redis.lists[logger.OPERATIONS_HISTORY_KEY] == [
        caplog.records[0].message
    ]


def test_log_event_keeps_only_latest_100_events(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(logger, "redis_client", fake_redis)

    for task_id in range(105):
        logger.log_event("task_created", task_id=task_id)

    stored = fake_redis.lists[logger.OPERATIONS_HISTORY_KEY]

    assert len(stored) == logger.OPERATIONS_HISTORY_LIMIT
    assert json.loads(stored[0])["task_id"] == 104
    assert json.loads(stored[-1])["task_id"] == 5
    assert len(fake_redis.published) == 105


def test_worker_heartbeat_streams_live_without_displacing_event_history(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(logger, "redis_client", fake_redis)

    logger.log_event("task_created", task_id=1)
    logger.log_event("worker_heartbeat", worker_name="worker-a")

    stored = fake_redis.lists[logger.OPERATIONS_HISTORY_KEY]

    assert len(stored) == 1
    assert json.loads(stored[0])["event"] == "task_created"
    assert len(fake_redis.published) == 2


def test_log_event_includes_current_trace_context(monkeypatch, caplog):
    fake_redis = FakeRedis()
    monkeypatch.setattr(logger, "redis_client", fake_redis)
    span_context = SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )

    with trace.use_span(NonRecordingSpan(span_context), end_on_exit=False):
        with caplog.at_level("INFO", logger="failure_playground"):
            logger.log_event("task_succeeded", task_id=123)

    payload = json.loads(caplog.records[0].message)

    assert payload["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert payload["span_id"] == "1234567890abcdef"
    assert payload["event_id"]
