from config import TASK_QUEUE_NAME
from redis_client import redis_client


TASK_QUEUE_NAME = "task_queue"


def enqueue_task(task_id: int):
    redis_client.lpush(TASK_QUEUE_NAME, task_id)


def dequeue_task():
    task_id = redis_client.rpop(TASK_QUEUE_NAME)

    if task_id is None:
        return None

    return int(task_id)


def clear_queue():
    return redis_client.delete(TASK_QUEUE_NAME)


def get_queue_length():
    return redis_client.llen(TASK_QUEUE_NAME)