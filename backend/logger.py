import json
import logging
from datetime import datetime, UTC
from redis_client import redis_client

logger = logging.getLogger("failure_playground")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

if not logger.handlers:
    logger.addHandler(handler)


def log_event(event, **fields):
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **fields,
    }


    message = json.dumps(payload, default=str)

    logger.info(message)
    redis_client.publish("operations", message)