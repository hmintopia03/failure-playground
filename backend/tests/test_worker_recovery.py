from datetime import datetime, timedelta, UTC

import worker
from models import Task


def test_recover_stuck_tasks_requeues_timed_out_processing_task(
    db_session,
    monkeypatch,
):
    enqueued_task_ids = []

    def fake_enqueue_task(task_id):
        enqueued_task_ids.append(task_id)

    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)

    old_time = datetime.now(UTC) - timedelta(seconds=999)

    task = Task(
        status="processing",
        retry_count=0,
        priority=1,
        is_poison=False,
        created_at=old_time,
        updated_at=old_time,
        processing_started_at=old_time,
    )

    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    worker.recover_stuck_tasks(db_session)

    db_session.refresh(task)

    assert task.status == "queued"
    assert task.processing_started_at is None
    assert task.id in enqueued_task_ids