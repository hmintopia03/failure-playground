from fastapi import FastAPI
from sqlalchemy.orm import Session

from db import Base, engine, SessionLocal
from models import Task, TaskLog, WorkerHeartbeat
from sqlalchemy import text

from fastapi.responses import HTMLResponse
from redis_client import redis_client

from models import Task, TaskLog, WorkerHeartbeat, Alert
from datetime import datetime
import os

from schemas import task_to_dict, worker_to_dict, alert_to_dict

from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from services.task_service import create_task
from config import TASK_QUEUE_NAME

from fastapi import Depends
from dependencies import get_db


from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import func
from fastapi import Depends


ALERT_COOLDOWN_SECONDS = 60
QUEUE_PRESSURE_THRESHOLD = 20
WORKER_ALIVE_THRESHOLD_SECONDS = 10

from services.queue_service import (
    enqueue_task,
    dequeue_task,
    clear_queue,
    get_queue_length,
)

Base.metadata.create_all(bind=engine)

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
SYSTEM_VERSION = "0.1.0"
SYSTEM_STARTED_AT = datetime.utcnow()

SYSTEM_PAUSED = False

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/tasks")
def create_task_endpoint(
    priority: int = 1,
    is_poison: bool = False
):
    db: Session = SessionLocal()

    task = create_task(
        db=db,
        priority=priority,
        is_poison=is_poison
    )

    enqueue_task(task.id)

    result = task_to_dict(task)

    db.close()

    return result

@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).all()

    return [
        task_to_dict(task)
        for task in tasks
    ]

@app.get("/logs")
def get_logs():
    db: Session = SessionLocal()

    logs = db.query(TaskLog).all()

    result = []

    for log in logs:
        result.append({
            "task_id": log.task_id,
            "message": log.message,
            "created_at": log.created_at
        })

    db.close()

    return result


@app.get("/dead-letter")
def get_dead_letter_tasks():
    db: Session = SessionLocal()

    tasks = (
        db.query(Task)
        .filter(Task.status == "failed")
        .all()
    )

    result = []

    for task in tasks:
        result.append({
            "id": task.id,
            "status": task.status,
            "retry_count": task.retry_count,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        })

    db.close()

    return result

@app.post("/tasks/{task_id}/retry")
def retry_task(task_id: int):
    db: Session = SessionLocal()

    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        db.close()
        return {"error": "Task not found"}

    task.status = "queued"
    task.retry_count = 0
    task.retry_at = None

    db.commit()

    retried_task_id = task.id

    log = TaskLog(
        task_id=retried_task_id,
        message="Task manually retried"
    )

    db.add(log)
    db.commit()

    db.close()

    return {
        "message": "Task retried",
        "task_id": retried_task_id
    }


@app.get("/tasks/{task_id}")
def get_task_detail(task_id: int):
    db: Session = SessionLocal()

    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        db.close()
        return {"error": "Task not found"}

    logs = (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task.id)
        .all()
    )

    result = {
        "id": task.id,
        "status": task.status,
        "retry_count": task.retry_count,
        "retry_at": task.retry_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "processing_started_at": task.processing_started_at,
        
        "logs": [
            {
                "message": log.message,
                "created_at": log.created_at
            }
            for log in logs
        ]
    }

    db.close()

    return result



def _maybe_create_queue_pressure_alert(db: Session, queue_length: int, now: datetime) -> None:

    if queue_length <= QUEUE_PRESSURE_THRESHOLD:
        return

    existing_alert = (
        db.query(Alert)
        .filter(Alert.message.contains("High queue pressure"))
        .order_by(Alert.id.desc())
        .first()
    )

    if existing_alert:
        seconds_since_last = (now - existing_alert.created_at).total_seconds()
        if seconds_since_last < ALERT_COOLDOWN_SECONDS:
            return

    db.add(Alert(message=f"High queue pressure: {queue_length} tasks waiting"))
    db.commit()


def _count_workers(db: Session, now: datetime) -> tuple[int, int]:
    """Alive / stale worker 수 반환."""
    workers = db.query(WorkerHeartbeat).all()
    alive = 0
    stale = 0
    for worker in workers:
        seconds_since_seen = (now - worker.last_seen).total_seconds()
        if seconds_since_seen <= WORKER_ALIVE_THRESHOLD_SECONDS:
            alive += 1
        else:
            stale += 1
    return alive, stale


@app.get("/metrics")
def get_metrics():
    db: Session = SessionLocal()

    redis_queue_length = redis_client.llen(TASK_QUEUE_NAME)

    queued_count = db.query(Task).filter(Task.status == "queued").count()
    processing_count = db.query(Task).filter(Task.status == "processing").count()
    success_count = db.query(Task).filter(Task.status == "success").count()
    failed_count = db.query(Task).filter(Task.status == "failed").count()

    failure_reasons = {}

    failed_tasks = (
        db.query(Task)
        .filter(Task.status == "failed")
        .all()
    )

    for task in failed_tasks:
        reason = task.failure_reason or "unknown"

        if reason not in failure_reasons:
            failure_reasons[reason] = 0

        failure_reasons[reason] += 1

    high_priority_queued = (
        db.query(Task)
        .filter(Task.status == "queued")
        .filter(Task.priority == 0)
        .count()
    )

    duplicate_prevented_count = (
        db.query(TaskLog)
        .filter(TaskLog.message.contains("Duplicate task prevented"))
        .count()
    )

    poison_count = (
        db.query(Task)
        .filter(Task.is_poison == True)
        .count()
    )

    failed_poison_count = (
        db.query(Task)
        .filter(Task.is_poison == True)
        .filter(Task.status == "failed")
        .count()
    )

    alive_workers = 0
    stale_workers = 0

    workers = db.query(WorkerHeartbeat).all()

    for worker in workers:
        if not worker.last_seen:
            stale_workers += 1
            continue

        seconds_since_seen = (
            datetime.utcnow() - worker.last_seen
        ).total_seconds()

        if seconds_since_seen <= 10:
            alive_workers += 1
        else:
            stale_workers += 1

    throughput_last_minute = 0

    recent_successes = (
        db.query(Task)
        .filter(Task.status == "success")
        .all()
    )

    for task in recent_successes:
        if not task.updated_at:
            continue

        seconds_since_update = (
            datetime.utcnow() - task.updated_at
        ).total_seconds()

        if seconds_since_update <= 60:
            throughput_last_minute += 1

    result = {
        "queued": queued_count,
        "processing": processing_count,
        "success": success_count,
        "failed": failed_count,
        "total": (
            queued_count
            + processing_count
            + success_count
            + failed_count
        ),
        "failure_reasons": failure_reasons,
        "high_priority_queued": high_priority_queued,
        "redis_queue_length": redis_queue_length,
        "alive_workers": alive_workers,
        "stale_workers": stale_workers,
        "duplicate_prevented_count": duplicate_prevented_count,
        "poison_tasks": poison_count,
        "failed_poison_tasks": failed_poison_count,
        "throughput_last_minute": throughput_last_minute,
    }

    db.close()

    return result
@app.get("/health")
def health_check():
    try:
        db: Session = SessionLocal()

        db.execute(text("SELECT 1"))

        db.close()

        uptime_seconds = int(
            (datetime.utcnow() - SYSTEM_STARTED_AT).total_seconds()
        )

        return {
            "status": "healthy",
            "database": "connected",
            "uptime_seconds": uptime_seconds
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
    
@app.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html"
    )

@app.post("/pause")
def pause_system():
    global SYSTEM_PAUSED
    SYSTEM_PAUSED = True
    return {"paused": SYSTEM_PAUSED}


@app.post("/resume")
def resume_system():
    global SYSTEM_PAUSED
    SYSTEM_PAUSED = False
    return {"paused": SYSTEM_PAUSED}


@app.get("/system-state")
def get_system_state():
    return {"paused": SYSTEM_PAUSED}

@app.get("/workers")
def get_workers():
    db: Session = SessionLocal()

    workers = db.query(WorkerHeartbeat).all()

    result = []

    for worker in workers:
        seconds_since_seen = (
            datetime.utcnow() - worker.last_seen
        ).total_seconds()

        if seconds_since_seen > 10:
            existing_alert = (
                db.query(Alert)
                .filter(Alert.message.contains(f"Worker stale: {worker.worker_name}"))
                .order_by(Alert.id.desc())
                .first()
            )

            should_create_alert = True

            if existing_alert:
                seconds_since_last_alert = (
                    datetime.utcnow() - existing_alert.created_at
                ).total_seconds()

                if seconds_since_last_alert < 60:
                    should_create_alert = False

            if should_create_alert:
                alert = Alert(
                    message=f"Worker stale: {worker.worker_name}"
                )
                db.add(alert)
                db.commit()
        result.append({
            "worker_name": worker.worker_name,
            "last_seen": worker.last_seen,
            "processed_count": worker.processed_count,
        })

    db.close()

    return result

@app.post("/tasks/{task_id}/duplicate")
def duplicate_task(task_id: int):
    redis_client.lpush(TASK_QUEUE_NAME, task_id)

    return {
        "message": "Duplicate task pushed into Redis",
        "task_id": task_id
    }

@app.delete("/tasks/completed")
def delete_completed_tasks():
    db: Session = SessionLocal()

    completed_tasks = (
        db.query(Task)
        .filter(Task.status == "success")
        .all()
    )

    count = len(completed_tasks)

    for task in completed_tasks:
        db.delete(task)

    db.commit()
    db.close()

    return {
        "message": "Completed tasks deleted",
        "deleted_count": count
    }

@app.delete("/tasks/failed")
def delete_failed_tasks():
    db: Session = SessionLocal()

    failed_tasks = (
        db.query(Task)
        .filter(Task.status == "failed")
        .all()
    )

    count = len(failed_tasks)

    for task in failed_tasks:
        db.delete(task)

    db.commit()
    db.close()

    return {
        "message": "Failed tasks deleted",
        "deleted_count": count
    }

@app.post("/workers/reset-counts")
def reset_worker_counts():
    db: Session = SessionLocal()

    workers = db.query(WorkerHeartbeat).all()

    for worker in workers:
        worker.processed_count = 0

    db.commit()
    db.close()

    return {"message": "Worker counts reset"}

@app.post("/tasks/bulk")
def create_bulk_tasks(count: int = 10, priority: int = 1):
    db: Session = SessionLocal()

    created_task_ids = []

    for _ in range(count):
        task = Task(
            status="queued",
            retry_count=0,
            priority=priority
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        enqueue_task(task.id)
        created_task_ids.append(task.id)

    db.close()

    return {
        "message": "Bulk tasks created",
        "count": count,
        "task_ids": created_task_ids
    }

@app.get("/alerts")
def get_alerts():
    db: Session = SessionLocal()

    alerts = db.query(Alert).all()

    result = []

    for alert in alerts:
        result.append({
            "id": alert.id,
            "message": alert.message,
            "created_at": alert.created_at
        })

    db.close()

    return result

@app.delete("/alerts")
def clear_alerts():
    db: Session = SessionLocal()

    alerts = db.query(Alert).all()

    count = len(alerts)

    for alert in alerts:
        db.delete(alert)

    db.commit()
    db.close()

    return {
        "message": "Alerts cleared",
        "deleted_count": count
    }

@app.get("/report")
def get_report():
    db: Session = SessionLocal()

    report = {
        "metrics": get_metrics(),
        "workers": get_workers(),
        "alerts": get_alerts(),
        "recent_logs": get_logs()[-20:],
        "tasks": get_tasks()
    }

    db.close()

    return report

@app.get("/config")
def get_config():
    return {
        "environment": ENVIRONMENT,
        "version": SYSTEM_VERSION
    }

@app.delete("/queue")
def clear_queue():
    deleted_count = redis_client.delete(TASK_QUEUE_NAME)

    return {
        "message": "Queue cleared",
        "deleted": deleted_count
    }

@app.delete("/reset")
def reset_system():
    db: Session = SessionLocal()

    redis_client.delete(TASK_QUEUE_NAME)

    db.query(TaskLog).delete()
    db.query(Alert).delete()
    db.query(Task).delete()

    workers = db.query(WorkerHeartbeat).all()

    for worker in workers:
        worker.processed_count = 0

    db.commit()
    db.close()

    return {
        "message": "System reset complete"
    }