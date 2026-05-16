import json
import logging
from datetime import datetime, UTC


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

    logger.info(json.dumps(payload, default=str))