from datetime import datetime, UTC

from models import Task


def test_metrics_endpoint_returns_task_counts(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    db.add_all([
        Task(status="queued", retry_count=0, priority=1, is_poison=False, created_at=now, updated_at=now),
        Task(status="queued", retry_count=0, priority=1, is_poison=False, created_at=now, updated_at=now),
        Task(status="processing", retry_count=0, priority=1, is_poison=False, created_at=now, updated_at=now),
        Task(status="success", retry_count=0, priority=1, is_poison=False, created_at=now, updated_at=now),
        Task(status="failed", retry_count=0, priority=1, is_poison=False, created_at=now, updated_at=now),
    ])

    db.commit()

    response = api_client.get("/metrics")

    assert response.status_code == 200

    data = response.json()

    assert data["queued"] == 2
    assert data["processing"] == 1
    assert data["success"] == 1
    assert data["failed"] == 1