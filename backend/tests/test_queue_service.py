import pytest
import services.queue_service as queue_service
import json

class FakeRedis:
    def __init__(self):
        self.queues = {}

    def lpush(self, queue_name, value):
        self.queues.setdefault(queue_name, [])
        self.queues[queue_name].insert(0, value)

    def rpop(self, queue_name):
        queue = self.queues.get(queue_name, [])

        if not queue:
            return None

        return queue.pop()

    def delete(self, queue_name):
        existed = queue_name in self.queues
        self.queues.pop(queue_name, None)
        return 1 if existed else 0

    def llen(self, queue_name):
        return len(self.queues.get(queue_name, []))


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()

    monkeypatch.setattr(
        queue_service,
        "redis_client",
        fake,
    )

    return fake


def test_enqueue_and_dequeue_task(fake_redis):
    queue_service.enqueue_task(123)

    task_id = queue_service.dequeue_task()

    assert task_id == 123


def test_dequeue_empty_queue_returns_none(fake_redis):
    task_id = queue_service.dequeue_task()

    assert task_id is None


def test_get_queue_length(fake_redis):
    queue_service.enqueue_task(1)
    queue_service.enqueue_task(2)

    length = queue_service.get_queue_length()

    assert length == 2


def test_clear_queue(fake_redis):
    queue_service.enqueue_task(1)
    queue_service.enqueue_task(2)

    queue_service.clear_queue()

    assert queue_service.get_queue_length() == 0


def test_enqueue_task_logs_structured_event(fake_redis, caplog):
    with caplog.at_level("INFO", logger="failure_playground"):
        queue_service.enqueue_task(123)

    messages = [
        json.loads(record.message)
        for record in caplog.records
    ]

    task_enqueued_logs = [
        message
        for message in messages
        if message["event"] == "task_enqueued"
    ]

    assert len(task_enqueued_logs) == 1

    log = task_enqueued_logs[0]

    assert log["task_id"] == 123
    assert log["queue_name"] == queue_service.TASK_QUEUE_NAME
    assert "timestamp" in log