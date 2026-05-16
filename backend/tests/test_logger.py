import json

from logger import log_event


def test_log_event_outputs_json(caplog):
    with caplog.at_level("INFO", logger="failure_playground"):
        log_event(
            "task_created",
            task_id=123,
            status="queued",
        )

    assert len(caplog.records) == 1

    payload = json.loads(caplog.records[0].message)

    assert payload["event"] == "task_created"
    assert payload["task_id"] == 123
    assert payload["status"] == "queued"
    assert "timestamp" in payload