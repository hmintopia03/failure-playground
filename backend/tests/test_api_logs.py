from datetime import datetime, UTC

from models import Task, TaskLog


def test_logs_endpoint_returns_task_logs(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    task = Task(
        status="queued",
        retry_count=0,
        priority=1,
        is_poison=False,
        created_at=now,
        updated_at=now,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    log = TaskLog(
        task_id=task.id,
        message="Task created",
        created_at=now,
    )

    db.add(log)
    db.commit()

    response = api_client.get("/logs")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert data["limit"] == 50
    assert data["offset"] == 0

    items = data["items"]

    assert len(items) == 1
    assert items[0]["task_id"] == task.id
    assert items[0]["message"] == "Task created"

def test_logs_rejects_invalid_task_id(api_client):
    response = api_client.get(
        "/logs",
        params={
            "task_id": 0,
        },
    )

    assert response.status_code == 422


def test_logs_rejects_invalid_limit(api_client):
    response = api_client.get(
        "/logs",
        params={
            "limit": 999,
        },
    )

    assert response.status_code == 422


def test_logs_rejects_negative_offset(api_client):
    response = api_client.get(
        "/logs",
        params={
            "offset": -1,
        },
    )

    assert response.status_code == 422