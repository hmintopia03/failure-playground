from datetime import datetime, UTC

from models import WorkerHeartbeat


def test_workers_endpoint_returns_worker_heartbeats(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    db.add_all([
        WorkerHeartbeat(
            worker_name="worker-1",
            last_seen=now,
            processed_count=3,
        ),
        WorkerHeartbeat(
            worker_name="worker-2",
            last_seen=now,
            processed_count=7,
        ),
    ])

    db.commit()

    response = api_client.get("/workers")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    worker_names = [
        worker["worker_name"]
        for worker in data
    ]

    assert "worker-1" in worker_names
    assert "worker-2" in worker_names

    processed_counts = {
        worker["worker_name"]: worker["processed_count"]
        for worker in data
    }

    assert processed_counts["worker-1"] == 3
    assert processed_counts["worker-2"] == 7