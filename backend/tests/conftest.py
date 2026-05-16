import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base


@pytest.fixture
def db_session():
    import models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client(monkeypatch):
    os.environ["ENVIRONMENT"] = "test"

    import models
    import main
    from dependencies import get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    enqueued_task_ids = []

    def fake_enqueue_task(task_id):
        enqueued_task_ids.append(task_id)

    def fake_get_queue_length():
        return len(enqueued_task_ids)

    def fake_clear_queue():
        enqueued_task_ids.clear()

    main.app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr(main, "enqueue_task", fake_enqueue_task)
    monkeypatch.setattr(main, "get_queue_length", fake_get_queue_length)
    monkeypatch.setattr(main, "clear_queue", fake_clear_queue)

    client = TestClient(main.app)

    client.enqueued_task_ids = enqueued_task_ids
    client.override_get_db = override_get_db

    try:
        yield client
    finally:
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)