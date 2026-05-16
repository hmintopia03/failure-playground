from datetime import datetime, UTC

from models import Task, WorkerHeartbeat


def test_prometheus_endpoint_returns_metrics(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    db.add_all([
        Task(
            status="queued",
            retry_count=0,
            priority=1,
            is_poison=False,
            created_at=now,
            updated_at=now,
        ),
        Task(
            status="success",
            retry_count=0,
            priority=1,
            is_poison=False,
            created_at=now,
            updated_at=now,
        ),
        Task(
            status="failed",
            retry_count=3,
            priority=1,
            is_poison=True,
            created_at=now,
            updated_at=now,
        ),
        WorkerHeartbeat(
            worker_name="worker-1",
            last_seen=now,
            processed_count=5,
        ),
    ])

    db.commit()

    response = api_client.get("/prometheus")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text

    assert "failure_playground_tasks_queued 1" in body
    assert "failure_playground_tasks_success 1" in body
    assert "failure_playground_tasks_failed 1" in body
    assert "failure_playground_tasks_poison 1" in body
    assert "failure_playground_tasks_poison_failed 1" in body
    assert "failure_playground_workers_alive 1" in body