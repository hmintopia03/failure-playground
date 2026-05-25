import asyncio
import json

import main


class FakePubSub:
    def __init__(self):
        self.channel = None
        self.closed = False

    def subscribe(self, channel):
        self.channel = channel

    def get_message(self, ignore_subscribe_messages=True):
        raise RuntimeError("end test stream")

    def close(self):
        self.closed = True


class FakeRedis:
    def __init__(self, stored_events):
        self.stored_events = stored_events
        self.subscription = FakePubSub()
        self.history_request = None

    def pubsub(self):
        return self.subscription

    def lrange(self, key, start, end):
        self.history_request = (key, start, end)
        return self.stored_events


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, data):
        self.sent.append(data)


def test_operations_websocket_replays_stored_events_oldest_first(monkeypatch):
    stored_events = [
        json.dumps({"event_id": "new", "event": "task_succeeded"}),
        json.dumps({"event_id": "old", "event": "task_created"}),
    ]
    fake_redis = FakeRedis(stored_events)
    websocket = FakeWebSocket()

    monkeypatch.setattr(main, "redis_client", fake_redis)

    asyncio.run(main.operations_websocket(websocket))

    sent = [json.loads(message) for message in websocket.sent]

    assert websocket.accepted is True
    assert fake_redis.history_request == (
        main.OPERATIONS_HISTORY_KEY,
        0,
        main.OPERATIONS_HISTORY_LIMIT - 1,
    )
    assert fake_redis.subscription.channel == main.OPERATIONS_CHANNEL
    assert fake_redis.subscription.closed is True
    assert [message["event_id"] for message in sent] == ["old", "new"]
    assert all(message["replayed"] is True for message in sent)
