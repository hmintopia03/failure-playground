from services.task_service import create_task

import json


def test_create_task_creates_queued_task(db_session):
    task = create_task(
        db=db_session,
        priority=1,
        is_poison=False,
    )

    assert task.id is not None
    assert task.status == "queued"
    assert task.priority == 1
    assert task.is_poison is False
    assert task.retry_count == 0
    assert task.created_at is not None
    assert task.updated_at is not None


def test_create_poison_task(db_session):
    task = create_task(
        db=db_session,
        priority=5,
        is_poison=True,
    )

    assert task.id is not None
    assert task.status == "queued"
    assert task.priority == 5
    assert task.is_poison is True
    assert task.retry_count == 0


def test_create_task_logs_structured_event(db_session, caplog):
    with caplog.at_level("INFO", logger="failure_playground"):
        task = create_task(
            db=db_session,
            priority=2,
            is_poison=False,
        )

    messages = [
        json.loads(record.message)
        for record in caplog.records
    ]

    task_created_logs = [
        message
        for message in messages
        if message["event"] == "task_created"
    ]

    assert len(task_created_logs) == 1

    log = task_created_logs[0]

    assert log["task_id"] == task.id
    assert log["status"] == "queued"
    assert log["priority"] == 2
    assert log["is_poison"] is False
    assert "timestamp" in log