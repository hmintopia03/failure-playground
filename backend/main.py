import os
from collections import Counter
from datetime import datetime, UTC, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from config import TASK_QUEUE_NAME
from db import Base, SessionLocal, engine
from dependencies import get_db
from models import Alert, Task, TaskLog, WorkerHeartbeat
from redis_client import redis_client
from schemas import alert_to_dict, task_to_dict, worker_to_dict
from services.task_service import create_task

from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )

ALERT_COOLDOWN_SECONDS = 60
QUEUE_PRESSURE_THRESHOLD = 20
WORKER_ALIVE_THRESHOLD_SECONDS = 10

from services.queue_service import (
    enqueue_task,
    dequeue_task,
    clear_queue,
    get_queue_length,
)

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

if ENVIRONMENT != "test":
    Base.metadata.create_all(bind=engine)

SYSTEM_VERSION = "0.1.0"
SYSTEM_STARTED_AT = datetime.now(UTC)
SYSTEM_PAUSED = False


def ensure_utc(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value

@app.post("/tasks")
def create_task_endpoint(
    priority: int = 1,
    is_poison: bool = False,
    db: Session = Depends(get_db),
):
    task = create_task(
        db=db,
        priority=priority,
        is_poison=is_poison,
    )

    enqueue_task(task.id)

    return task_to_dict(task)

@app.get("/tasks")
def get_tasks(
    status: str | None = Query(
        default=None,
        pattern="^(queued|processing|success|failed)$",
    ),
    is_poison: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Task)

    if status is not None:
        query = query.filter(Task.status == status)

    if is_poison is not None:
        query = query.filter(Task.is_poison == is_poison)

    total = query.count()

    tasks = (
        query
        .order_by(Task.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "items": [
            task_to_dict(task)
            for task in tasks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@app.get("/logs")
def get_logs(
    task_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):

    query = db.query(TaskLog)

    if task_id is not None:
        query = query.filter(TaskLog.task_id == task_id)

    total = query.count()

    logs = (
        query
        .order_by(TaskLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "items": [
            {
                "id": log.id,
                "task_id": log.task_id,
                "message": log.message,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

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
def get_metrics(db: Session = Depends(get_db)):
    redis_queue_length = get_queue_length()

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

    now = datetime.now(UTC)

    for worker in workers:
        if not worker.last_seen:
            stale_workers += 1
            continue

        last_seen = ensure_utc(worker.last_seen)

        seconds_since_seen = (
            now - last_seen
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

        updated_at = ensure_utc(task.updated_at)

        seconds_since_update = (
            now - updated_at
        ).total_seconds()

        if seconds_since_update <= 60:
            throughput_last_minute += 1

    return {
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

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    database_status = "ok"
    redis_status = "ok"

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    try:
        redis_client.ping()
    except Exception:
        redis_status = "error"

    overall_status = "ok"

    if database_status != "ok" or redis_status != "ok":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "database": database_status,
        "redis": redis_status,
    }
    
@app.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request},
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
def get_workers(db: Session = Depends(get_db)):
    workers = db.query(WorkerHeartbeat).all()

    result = []

    for worker in workers:
        result.append({
            "worker_name": worker.worker_name,
            "last_seen": worker.last_seen,
            "processed_count": worker.processed_count,
        })

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
def get_alerts(db: Session = Depends(get_db)):
    alerts = db.query(Alert).all()

    result = []

    for alert in alerts:
        result.append({
            "id": alert.id,
            "message": alert.message,
            "created_at": alert.created_at,
        })

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

@app.get("/prometheus", response_class=PlainTextResponse)
def get_prometheus_metrics(db: Session = Depends(get_db)):
    queued_count = db.query(Task).filter(Task.status == "queued").count()
    processing_count = db.query(Task).filter(Task.status == "processing").count()
    success_count = db.query(Task).filter(Task.status == "success").count()
    failed_count = db.query(Task).filter(Task.status == "failed").count()

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

    redis_queue_length = get_queue_length()

    workers = db.query(WorkerHeartbeat).all()

    now = datetime.now(UTC)

    alive_workers = 0
    stale_workers = 0

    for worker in workers:
        if not worker.last_seen:
            stale_workers += 1
            continue

        last_seen = ensure_utc(worker.last_seen)

        seconds_since_seen = (
            now - last_seen
        ).total_seconds()

        if seconds_since_seen <= 10:
            alive_workers += 1
        else:
            stale_workers += 1

    metrics = [
        "# HELP failure_playground_tasks_queued Number of queued tasks",
        "# TYPE failure_playground_tasks_queued gauge",
        f"failure_playground_tasks_queued {queued_count}",
        "",
        "# HELP failure_playground_tasks_processing Number of processing tasks",
        "# TYPE failure_playground_tasks_processing gauge",
        f"failure_playground_tasks_processing {processing_count}",
        "",
        "# HELP failure_playground_tasks_success Number of successful tasks",
        "# TYPE failure_playground_tasks_success gauge",
        f"failure_playground_tasks_success {success_count}",
        "",
        "# HELP failure_playground_tasks_failed Number of failed tasks",
        "# TYPE failure_playground_tasks_failed gauge",
        f"failure_playground_tasks_failed {failed_count}",
        "",
        "# HELP failure_playground_tasks_poison Number of poison tasks",
        "# TYPE failure_playground_tasks_poison gauge",
        f"failure_playground_tasks_poison {poison_count}",
        "",
        "# HELP failure_playground_tasks_poison_failed Number of failed poison tasks",
        "# TYPE failure_playground_tasks_poison_failed gauge",
        f"failure_playground_tasks_poison_failed {failed_poison_count}",
        "",
        "# HELP failure_playground_redis_queue_length Redis queue length",
        "# TYPE failure_playground_redis_queue_length gauge",
        f"failure_playground_redis_queue_length {redis_queue_length}",
        "",
        "# HELP failure_playground_workers_alive Number of alive workers",
        "# TYPE failure_playground_workers_alive gauge",
        f"failure_playground_workers_alive {alive_workers}",
        "",
        "# HELP failure_playground_workers_stale Number of stale workers",
        "# TYPE failure_playground_workers_stale gauge",
        f"failure_playground_workers_stale {stale_workers}",
        "",
    ]

    return "\n".join(metrics)

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(str(BASE_DIR / "static" / "favicon.svg"))