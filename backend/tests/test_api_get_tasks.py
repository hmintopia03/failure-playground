from datetime import datetime, UTC

from models import Task, TaskLog


def test_get_tasks_endpoint_returns_tasks(api_client):
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
            status="failed",
            retry_count=3,
            priority=5,
            is_poison=True,
            failure_reason="Poison task failed",
            created_at=now,
            updated_at=now,
        ),
    ])

    db.commit()

    response = api_client.get("/tasks")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["limit"] == 50
    assert data["offset"] == 0

    items = data["items"]

    assert len(items) == 2

    statuses = [
        task["status"]
        for task in items
    ]

    assert "queued" in statuses
    assert "failed" in statuses

    poison_tasks = [
        task
        for task in items
        if task["is_poison"] is True
    ]

    assert len(poison_tasks) == 1
    assert poison_tasks[0]["failure_reason"] == "Poison task failed"


def test_get_tasks_endpoint_filters_by_status(api_client):
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
            status="failed",
            retry_count=3,
            priority=1,
            is_poison=True,
            created_at=now,
            updated_at=now,
        ),
    ])

    db.commit()

    response = api_client.get(
        "/tasks",
        params={
            "status": "failed",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "failed"

    items = data["items"]


def test_get_tasks_endpoint_supports_pagination(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    for _ in range(5):
        db.add(
            Task(
                status="queued",
                retry_count=0,
                priority=1,
                is_poison=False,
                created_at=now,
                updated_at=now,
            )
        )

    db.commit()

    response = api_client.get(
        "/tasks",
        params={
            "limit": 2,
            "offset": 0,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2

    items = data["items"]


def test_logs_endpoint_filters_by_task_id(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    task_1 = Task(
        status="queued",
        retry_count=0,
        priority=1,
        is_poison=False,
        created_at=now,
        updated_at=now,
    )

    task_2 = Task(
        status="queued",
        retry_count=0,
        priority=1,
        is_poison=False,
        created_at=now,
        updated_at=now,
    )

    db.add_all([task_1, task_2])
    db.commit()
    db.refresh(task_1)
    db.refresh(task_2)

    db.add_all([
        TaskLog(
            task_id=task_1.id,
            message="Task 1 log",
            created_at=now,
        ),
        TaskLog(
            task_id=task_2.id,
            message="Task 2 log",
            created_at=now,
        ),
    ])

    db.commit()

    response = api_client.get(
        "/logs",
        params={
            "task_id": task_1.id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["task_id"] == task_1.id
    assert data["items"][0]["message"] == "Task 1 log"


def test_logs_endpoint_supports_pagination(api_client):
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

    for index in range(5):
        db.add(
            TaskLog(
                task_id=task.id,
                message=f"Log {index}",
                created_at=now,
            )
        )

    db.commit()

    response = api_client.get(
        "/logs",
        params={
            "limit": 2,
            "offset": 0,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2

def test_get_tasks_rejects_invalid_status(api_client):
    response = api_client.get(
        "/tasks",
        params={
            "status": "banana",
        },
    )

    assert response.status_code == 422


def test_get_tasks_rejects_invalid_limit(api_client):
    response = api_client.get(
        "/tasks",
        params={
            "limit": 999,
        },
    )

    assert response.status_code == 422


def test_get_tasks_rejects_negative_offset(api_client):
    response = api_client.get(
        "/tasks",
        params={
            "offset": -1,
        },
    )

    assert response.status_code == 422