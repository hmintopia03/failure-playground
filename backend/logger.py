import json
import logging
from datetime import datetime, UTC
from uuid import uuid4
from opentelemetry import trace
from redis_client import redis_client

logger = logging.getLogger("failure_playground")
logger.setLevel(logging.INFO)

OPERATIONS_CHANNEL = "operations"
OPERATIONS_HISTORY_KEY = "operations:history"
OPERATIONS_HISTORY_LIMIT = 100
NON_PERSISTED_EVENTS = {"worker_heartbeat"}

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

if not logger.handlers:
    logger.addHandler(handler)


def current_trace_fields():
    span = trace.get_current_span()
    span_context = span.get_span_context()

    if not span_context.is_valid:
        return {}

    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


def log_event(event, **fields):
    payload = {
        "event_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **current_trace_fields(),
        **fields,
    }


    message = json.dumps(payload, default=str)

    logger.info(message)

    if event not in NON_PERSISTED_EVENTS:
        redis_client.lpush(OPERATIONS_HISTORY_KEY, message)
        redis_client.ltrim(OPERATIONS_HISTORY_KEY, 0, OPERATIONS_HISTORY_LIMIT - 1)

    redis_client.publish(OPERATIONS_CHANNEL, message)
