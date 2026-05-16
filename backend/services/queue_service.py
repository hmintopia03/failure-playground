from config import TASK_QUEUE_NAME
from redis_client import redis_client
from logger import log_event


def enqueue_task(task_id: int):
    redis_client.lpush(TASK_QUEUE_NAME, task_id)
    
    log_event(
        "task_enqueued",
        task_id=task_id,
        queue_name=TASK_QUEUE_NAME,
    )


def dequeue_task():
    task_id = redis_client.rpop(TASK_QUEUE_NAME)

    if task_id is None:
        return None

    return int(task_id)


def clear_queue():
    return redis_client.delete(TASK_QUEUE_NAME)


def get_queue_length():
    return redis_client.llen(TASK_QUEUE_NAME)