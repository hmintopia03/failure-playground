from datetime import datetime, UTC

from models import Alert


def test_alerts_endpoint_returns_alerts(api_client):
    db = next(api_client.override_get_db())

    now = datetime.now(UTC)

    db.add_all([
        Alert(
            message="High queue pressure: 25 tasks waiting",
            created_at=now,
        ),
        Alert(
            message="Worker stale: worker-1",
            created_at=now,
        ),
    ])

    db.commit()

    response = api_client.get("/alerts")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    messages = [
        alert["message"]
        for alert in data
    ]

    assert "High queue pressure: 25 tasks waiting" in messages
    assert "Worker stale: worker-1" in messages