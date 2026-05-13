import random
import time
from sqlalchemy.orm import Session

from db import SessionLocal, Base, engine
from models import Task
from models import Task, TaskLog
from datetime import datetime, timedelta
import requests
from models import WorkerHeartbeat
import os
from redis_client import redis_client
from config import TASK_QUEUE_NAME
from logger import logger


from services.queue_service import (
    enqueue_task,
    dequeue_task,
)
from config import MAX_RETRIES

Base.metadata.create_all(bind=engine)

MAX_TASKS_PER_WINDOW = 3
WINDOW_SECONDS = 10

processed_timestamps = []



WORKER_NAME = os.getenv("WORKER_NAME", "worker-default")

TASK_TIMEOUT_SECONDS = 15

FAILURE_REASONS = [
    "timeout",
    "external_api_error",
    "database_error",
    "validation_error",
]

def process_task(task: Task, db: Session):

    add_log(db, task.id, f"{WORKER_NAME}: Task started processing")

    time.sleep(2)

    did_fail = (
        task.is_poison
        or
        random.random() < 0.5
    )

    if did_fail:

        failure_reason = random.choice(FAILURE_REASONS)
        task.failure_reason = failure_reason
        task.retry_count += 1

        if task.retry_count >= MAX_RETRIES:
            task.status = "failed"
            add_log(db, task.id, f"Task failed because of {failure_reason}")
        else:
            backoff_seconds = 2 ** task.retry_count

            task.retry_at = datetime.utcnow() + timedelta(
                seconds=backoff_seconds
            )

            task.status = "queued"
            task.updated_at = datetime.utcnow()

            db.commit()

            add_log(
                db,
                task.id,
                f"Retry scheduled in {backoff_seconds} seconds"
            )

            add_log(db, task.id, "Retrying task")

            enqueue_task(task.id)
    else:
        task.status = "success"
        task.failure_reason = None
        task.updated_at = datetime.utcnow()
        db.commit()

        add_log(db, task.id, "Task succeeded")

def run_worker():
    logger.info("Worker started.")

    while True:
        db: Session = SessionLocal()
        update_heartbeat(db)
        if is_system_paused():
            logger.info(f"[{WORKER_NAME}] System paused")
            time.sleep(1)
            db.close()
            continue

        current_time = time.time()

        processed_timestamps[:] = [
            ts
            for ts in processed_timestamps
            if current_time - ts < WINDOW_SECONDS
        ]

        if len(processed_timestamps) >= MAX_TASKS_PER_WINDOW:
            logger.info(
                f"[{WORKER_NAME}] Rate limit reached"
            )

            time.sleep(1)
            db.close()
            continue

        stuck_tasks = (
            db.query(Task)
            .filter(Task.status == "processing")
            .all()
        )

        for stuck_task in stuck_tasks:
            if (
                stuck_task.processing_started_at
                and
                (
                    datetime.utcnow()
                    - stuck_task.processing_started_at
                ).total_seconds() > TASK_TIMEOUT_SECONDS
            ):
                stuck_task.status = "queued"
                stuck_task.processing_started_at = None
                stuck_task.updated_at = datetime.utcnow()

                db.commit()
                logger.info(f"[{WORKER_NAME}] heartbeat updated")

                add_log(
                    db,
                    stuck_task.id,
                    "Task recovered after timeout"
                )

                redis_client.lpush(TASK_QUEUE_NAME, stuck_task.id)

                logger.info(
                    f"[{WORKER_NAME}] Recovered stuck task {stuck_task.id}"
                )

        task_id = dequeue_task()

        if not task_id:
            time.sleep(1)
            db.close()
            continue

        task = (
            db.query(Task)
            .filter(Task.id == int(task_id))
            .first()
        )

        if not task:
            db.close()
            continue

        if task.status != "queued":

            add_log(
                db,
                task.id,
                "Duplicate task prevented"
            )

            db.close()
            continue

        if task.retry_at and task.retry_at > datetime.utcnow():
            enqueue_task(task.id)
            time.sleep(1)
            db.close()
            continue

        task.status = "processing"
        task.updated_at = datetime.utcnow()
        task.processing_started_at = datetime.utcnow()
        db.commit()

        logger.info(f"[{WORKER_NAME}] Claimed task {task.id}")
        processed_timestamps.append(time.time())

        process_task(task, db)

        worker = (
            db.query(WorkerHeartbeat)
            .filter(
                WorkerHeartbeat.worker_name == WORKER_NAME
            )
            .first()
        )

        if worker:
            worker.processed_count += 1
            db.commit()

        db.close()

def add_log(db: Session, task_id: int, message: str):
    log = TaskLog(
        task_id=task_id,
        message=message
    )

    db.add(log)
    db.commit()

def is_system_paused():
    try:
        response = requests.get("http://api:8000/system-state")
        data = response.json()
        return data["paused"]
    except Exception:
        return False

def update_heartbeat(db):
    worker = (
        db.query(WorkerHeartbeat)
        .filter(
            WorkerHeartbeat.worker_name == WORKER_NAME
        )
        .first()
    )

    if not worker:
        worker = WorkerHeartbeat(
            worker_name=WORKER_NAME
        )

        db.add(worker)

    worker.last_seen = datetime.utcnow()

    db.commit()


if __name__ == "__main__":
    run_worker()