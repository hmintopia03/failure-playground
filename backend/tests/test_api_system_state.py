def test_system_state_defaults_to_not_paused(api_client):
    response = api_client.get("/system-state")

    assert response.status_code == 200
    assert response.json() == {"paused": False}


def test_pause_system(api_client):
    response = api_client.post("/pause")

    assert response.status_code == 200
    assert response.json() == {"paused": True}


def test_resume_system(api_client):
    api_client.post("/pause")

    response = api_client.post("/resume")

    assert response.status_code == 200
    assert response.json() == {"paused": False}