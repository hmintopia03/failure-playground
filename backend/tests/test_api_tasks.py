def test_create_task_endpoint_creates_and_enqueues_task(api_client):
    response = api_client.post(
        "/tasks",
        params={
            "priority": 3,
            "is_poison": False,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] is not None
    assert data["status"] == "queued"
    assert data["priority"] == 3
    assert data["is_poison"] is False
    assert data["retry_count"] == 0

    assert api_client.enqueued_task_ids == [data["id"]]


def test_create_poison_task_endpoint(api_client):
    response = api_client.post(
        "/tasks",
        params={
            "priority": 5,
            "is_poison": True,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] is not None
    assert data["status"] == "queued"
    assert data["priority"] == 5
    assert data["is_poison"] is True
    assert data["retry_count"] == 0


    assert api_client.enqueued_task_ids == [data["id"]]
