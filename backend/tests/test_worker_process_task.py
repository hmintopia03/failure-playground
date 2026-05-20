from datetime import datetime, UTC

import worker
from models import Task


def test_process_task_marks_task_as_success(db_session, monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(worker.random, "random", lambda: 0.99)

    monkeypatch.setattr(worker, "WORKER_NAME", "test-worker")

    task = Task(
        status="processing",
        retry_count=0,
        priority=1,
        is_poison=False,
        processing_started_at=datetime.now(UTC),
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    worker.process_task(task, db_session)

    db_session.refresh(task)

    assert task.status == "success"
    assert task.failure_reason is None
    assert task.processing_duration_seconds is not None



def test_process_task_retries_failed_task(db_session, monkeypatch):
    enqueued_task_ids = []

    def fake_enqueue_task(task_id):
        enqueued_task_ids.append(task_id)

    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(worker.random, "random", lambda: 0.1)
    monkeypatch.setattr(worker.random, "choice", lambda reasons: "database_error")
    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setattr(worker, "WORKER_NAME", "test-worker")

    task = Task(
        status="processing",
        retry_count=0,
        priority=1,
        is_poison=False,
        processing_started_at=datetime.now(UTC),
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    worker.process_task(task, db_session)

    db_session.refresh(task)

    assert task.status == "queued"
    assert task.retry_count == 1
    assert task.failure_reason == "database_error"
    assert task.retry_at is not None
    assert task.id in enqueued_task_ids


def test_process_task_marks_task_as_failed_after_max_retries(
    db_session,
    monkeypatch,
):
    enqueued_task_ids = []

    def fake_enqueue_task(task_id):
        enqueued_task_ids.append(task_id)

    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(worker.random, "random", lambda: 0.1)
    monkeypatch.setattr(worker.random, "choice", lambda reasons: "database_error")
    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setattr(worker, "WORKER_NAME", "test-worker")

    task = Task(
        status="processing",
        retry_count=worker.MAX_RETRIES - 1,
        priority=1,
        is_poison=False,
        processing_started_at=datetime.now(UTC),
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    worker.process_task(task, db_session)

    db_session.refresh(task)

    assert task.status == "failed"
    assert task.retry_count == worker.MAX_RETRIES
    assert task.failure_reason == "database_error"
    assert task.updated_at is not None
    assert task.id not in enqueued_task_ids


def test_process_task_marks_poison_task_as_failed(
    db_session,
    monkeypatch,
):
    enqueued_task_ids = []

    def fake_enqueue_task(task_id):
        enqueued_task_ids.append(task_id)

    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(worker.random, "random", lambda: 0.99)
    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setattr(worker, "WORKER_NAME", "test-worker")

    task = Task(
        status="processing",
        retry_count=worker.MAX_RETRIES - 1,
        priority=1,
        is_poison=True,
        processing_started_at=datetime.now(UTC),
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    worker.process_task(task, db_session)

    db_session.refresh(task)

    assert task.status == "failed"
    assert task.retry_count == worker.MAX_RETRIES
    assert task.failure_reason == "poison_task"
    assert task.id not in enqueued_task_ids