import os
import random
import time
from datetime import datetime, timedelta, UTC

import requests
from sqlalchemy.orm import Session

from config import (
    MAX_RETRIES,
    TASK_TIMEOUT_SECONDS,
    MAX_TASKS_PER_WINDOW,
    WINDOW_SECONDS,
)
from db import SessionLocal, Base, engine
from logger import logger, log_event
from models import Task, TaskLog, WorkerHeartbeat
from redis_client import redis_client
from services.queue_service import (
    enqueue_task,
    dequeue_task,
)

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

processed_timestamps = []

WORKER_NAME = os.getenv("WORKER_NAME", "worker-default")

FAILURE_REASONS = [
    "timeout",
    "external_api_error",
    "database_error",
    "validation_error",
]

def setup_tracing():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not endpoint:
        return

    resource = Resource.create({
        "service.name": os.getenv(
            "OTEL_SERVICE_NAME",
            "failure-playground-worker",
        )
    })

    provider = TracerProvider(resource=resource)

    processor = BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True,
        )
    )

    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

setup_tracing()
tracer = trace.get_tracer(__name__)


def now_utc():
    return datetime.now(UTC)


def ensure_utc(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value


def process_task(task: Task, db: Session):
    add_log(db, task.id, f"{WORKER_NAME}: Task started processing")

    log_event(
            "task_started",
            task_id=task.id,
            worker_name=WORKER_NAME,
            retry_count=task.retry_count,
            priority=task.priority,
            is_poison=task.is_poison,
        )

    time.sleep(2)

    did_fail = (
        task.is_poison
        or random.random() < 0.5
    )

    if did_fail:
        failure_reason = (
            "poison_task"
            if task.is_poison
            else random.choice(FAILURE_REASONS)
        )

        task.failure_reason = failure_reason
        task.retry_count += 1

        if task.retry_count >= MAX_RETRIES:
            with tracer.start_as_current_span("worker.fail_task") as fail_span:
                fail_span.set_attribute("task.id", task.id)
                fail_span.set_attribute("worker.name", WORKER_NAME)
                fail_span.set_attribute("task.status", "failed")
                task.status = "failed"
                task.updated_at = now_utc()

                db.commit()

                add_log(db, task.id, f"Task failed because of {failure_reason}")

                event_name = (
                    "task_poisoned"
                    if task.is_poison
                    else "task_failed"
                )

                log_event(
                    event_name,
                    task_id=task.id,
                    worker_name=WORKER_NAME,
                    retry_count=task.retry_count,
                    failure_reason=task.failure_reason,
                )

        else:
            with tracer.start_as_current_span("worker.retry_task") as retry_span:
                retry_span.set_attribute("task.id", task.id)
                retry_span.set_attribute("task.retry_count", task.retry_count)
                retry_span.set_attribute("worker.name", WORKER_NAME)

                backoff_seconds = 2 ** task.retry_count

                task.retry_at = now_utc() + timedelta(
                    seconds=backoff_seconds
                )

                task.status = "queued"
                task.updated_at = now_utc()

                db.commit()

                add_log(
                    db,
                    task.id,
                    f"Retry scheduled in {backoff_seconds} seconds",
                )

                add_log(db, task.id, "Retrying task")

                enqueue_task(task.id)

                log_event(
                    "task_retried",
                    task_id=task.id,
                    worker_name=WORKER_NAME,
                    retry_count=task.retry_count,
                    retry_at=task.retry_at,
                    backoff_seconds=backoff_seconds,
                    failure_reason=task.failure_reason,
                )

    else:
        with tracer.start_as_current_span("worker.complete_task") as success_span:
            success_span.set_attribute("task.id", task.id)
            success_span.set_attribute("worker.name", WORKER_NAME)
            success_span.set_attribute("task.status", "success")
            task.status = "success"
            task.failure_reason = None
            task.updated_at = now_utc()

            if task.processing_started_at:
                started_at = ensure_utc(task.processing_started_at)
                task.processing_duration_seconds = (
                    now_utc() - started_at
                ).total_seconds()

            db.commit()

            add_log(db, task.id, "Task succeeded")

            log_event(
                "task_succeeded",
                task_id=task.id,
                worker_name=WORKER_NAME,
                retry_count=task.retry_count,
                processing_duration_seconds=task.processing_duration_seconds,
            )


def run_worker():
    logger.info("Worker started.")

    while True:
        db: Session = SessionLocal()

        update_heartbeat(db)

        if is_system_paused():
            log_event(
                "system_paused",
                worker_name=WORKER_NAME,
            )

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
            log_event(
                "worker_rate_limited",
                worker_name=WORKER_NAME,
                processed_in_window=len(processed_timestamps),
                max_tasks_per_window=MAX_TASKS_PER_WINDOW,
                window_seconds=WINDOW_SECONDS,
            )

            time.sleep(1)
            db.close()
            continue

        recover_stuck_tasks(db)

        task_id = dequeue_task()

        if not task_id:
            time.sleep(1)
            db.close()
            continue

        with tracer.start_as_current_span("worker.process_task") as span:
            span.set_attribute("task.id", int(task_id))
            span.set_attribute("worker.name", WORKER_NAME)
            span.set_attribute("queue.name", "task_queue")

            task = (
                db.query(Task)
                .filter(Task.id == int(task_id))
                .first()
            )

            if not task:
                log_event(
                    "task_missing",
                    worker_name=WORKER_NAME,
                    task_id=task_id,
                )

                db.close()
                continue

            if task.status != "queued":
                add_log(
                    db,
                    task.id,
                    "Duplicate task prevented",
                )

                log_event(
                    "duplicate_task_prevented",
                    worker_name=WORKER_NAME,
                    task_id=task.id,
                    current_status=task.status,
                )

                db.close()
                continue

            retry_at = ensure_utc(task.retry_at)

            if retry_at and retry_at > now_utc():
                enqueue_task(task.id)

                log_event(
                    "task_not_ready_for_retry",
                    worker_name=WORKER_NAME,
                    task_id=task.id,
                    retry_at=retry_at,
                )

                time.sleep(1)
                db.close()
                continue

            with tracer.start_as_current_span("worker.claim_task") as claim_span:
                claim_span.set_attribute("task.id", task.id)
                claim_span.set_attribute("worker.name", WORKER_NAME)
                claim_span.set_attribute("task.previous_status", task.status)

                task.status = "processing"
                task.updated_at = now_utc()
                task.processing_started_at = now_utc()

                db.commit()

                claim_span.set_attribute("task.new_status", task.status)

            log_event(
                "task_claimed",
                worker_name=WORKER_NAME,
                task_id=task.id,
                retry_count=task.retry_count,
                priority=task.priority,
                is_poison=task.is_poison,
            )

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

                log_event(
                    "worker_processed_count_updated",
                    worker_name=WORKER_NAME,
                    processed_count=worker.processed_count,
                )

        db.close()

def recover_stuck_tasks(db: Session):
    with tracer.start_as_current_span("worker.recover_stuck_task") as span:
        span.set_attribute("worker.action", "recover_stuck_tasks")

        stuck_tasks = (
            db.query(Task)
            .filter(Task.status == "processing")
            .all()
        )

        span.set_attribute("worker.stuck_task_candidates", len(stuck_tasks))

        for stuck_task in stuck_tasks:
            if not stuck_task.processing_started_at:
                continue

            processing_started_at = ensure_utc(
                stuck_task.processing_started_at
            )

            seconds_processing = (
                now_utc() - processing_started_at
            ).total_seconds()

            if seconds_processing <= TASK_TIMEOUT_SECONDS:
                continue

            stuck_task.status = "queued"
            stuck_task.processing_started_at = None
            stuck_task.updated_at = now_utc()

            db.commit()

            add_log(
                db,
                stuck_task.id,
                "Task recovered after timeout",
            )

            enqueue_task(stuck_task.id)

            span.set_attribute("worker.recovered_task_id", stuck_task.id)

            log_event(
                "task_recovered_after_timeout",
                worker_name=WORKER_NAME,
                task_id=stuck_task.id,
                seconds_processing=seconds_processing,
                task_timeout_seconds=TASK_TIMEOUT_SECONDS,
            )


def add_log(db: Session, task_id: int, message: str):
    log = TaskLog(
        task_id=task_id,
        message=message,
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


def update_heartbeat(db: Session):
    worker = (
        db.query(WorkerHeartbeat)
        .filter(
            WorkerHeartbeat.worker_name == WORKER_NAME
        )
        .first()
    )

    if not worker:
        worker = WorkerHeartbeat(
            worker_name=WORKER_NAME,
        )

        db.add(worker)

    worker.last_seen = now_utc()

    db.commit()

    log_event(
        "worker_heartbeat",
        worker_name=WORKER_NAME,
        last_seen=worker.last_seen,
        processed_count=worker.processed_count,
    )


if __name__ == "__main__":
    run_worker()