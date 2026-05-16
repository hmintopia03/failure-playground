def test_health_check_returns_ok(api_client, monkeypatch):
    import main

    class FakeRedis:
        def ping(self):
            return True

    monkeypatch.setattr(main, "redis_client", FakeRedis())

    response = api_client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["redis"] == "ok"


def test_health_check_returns_degraded_when_redis_fails(api_client, monkeypatch):
    import main

    class BrokenRedis:
        def ping(self):
            raise Exception("Redis unavailable")

    monkeypatch.setattr(main, "redis_client", BrokenRedis())

    response = api_client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "degraded"
    assert data["database"] == "ok"
    assert data["redis"] == "error"