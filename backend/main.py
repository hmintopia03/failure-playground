import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from dependencies import get_db
from logger import OPERATIONS_CHANNEL, OPERATIONS_HISTORY_KEY, OPERATIONS_HISTORY_LIMIT
from models import Alert, Task, TaskLog, WorkerHeartbeat
from redis_client import redis_client
from schemas import task_to_dict
from services.queue_service import clear_queue, enqueue_task, get_queue_length
from services.task_service import create_task


ALERT_COOLDOWN_SECONDS = 60
QUEUE_PRESSURE_THRESHOLD = 20
WORKER_ALIVE_THRESHOLD_SECONDS = 10

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
SYSTEM_VERSION = "0.1.0"
SYSTEM_STARTED_AT = datetime.now(UTC)
SYSTEM_PAUSED_KEY = "system_paused"


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI()
logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI) -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not endpoint:
        return

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "failure-playground-api")
    })

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing(app)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

def ensure_utc(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value


def _is_system_paused() -> bool:
    value = redis_client.get(SYSTEM_PAUSED_KEY)

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    return value == "1"


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    admin_token = os.getenv("ADMIN_TOKEN")

    if admin_token and x_admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")

def _count_workers(db: Session, now: datetime) -> tuple[int, int]:
    """Alive / stale worker 수 반환."""
    workers = db.query(WorkerHeartbeat).all()
    alive = 0
    stale = 0
    for worker in workers:
        if not worker.last_seen:
            stale += 1
            continue

        seconds_since_seen = (now - ensure_utc(worker.last_seen)).total_seconds()
        if seconds_since_seen <= WORKER_ALIVE_THRESHOLD_SECONDS:
            alive += 1
        else:
            stale += 1
    return alive, stale

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
        seconds_since_last = (now - ensure_utc(existing_alert.created_at)).total_seconds()
        if seconds_since_last < ALERT_COOLDOWN_SECONDS:
            return

    db.add(Alert(message=f"High queue pressure: {queue_length} tasks waiting"))
    db.commit()


def _tasks_response(
    db: Session,
    status: str | None = None,
    is_poison: bool | None = None,
    limit: int = 50,
    offset: int = 0,
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


def _task_detail_response(db: Session, task_id: int):
    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        return None

    logs = (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task.id)
        .all()
    )

    return {
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


def _retry_task(db: Session, task_id: int):
    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        return None

    task.status = "queued"
    task.retry_count = 0
    task.retry_at = None

    db.commit()

    log = TaskLog(
        task_id=task.id,
        message="Task manually retried"
    )

    db.add(log)
    db.commit()

    return {
        "message": "Task retried",
        "task_id": task.id
    }


def _delete_tasks_by_status(db: Session, status: str, message: str):
    tasks = (
        db.query(Task)
        .filter(Task.status == status)
        .all()
    )

    count = len(tasks)
    task_ids = [task.id for task in tasks]

    if task_ids:
        (
            db.query(TaskLog)
            .filter(TaskLog.task_id.in_(task_ids))
            .delete(synchronize_session=False)
        )

    for task in tasks:
        db.delete(task)

    db.commit()

    return {
        "message": message,
        "deleted_count": count
    }


def _logs_response(
    db: Session,
    task_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
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


def _workers_response(db: Session):
    workers = db.query(WorkerHeartbeat).all()

    result = []

    for worker in workers:
        result.append({
            "worker_name": worker.worker_name,
            "last_seen": worker.last_seen,
            "processed_count": worker.processed_count,
        })

    return result


def _reset_worker_counts(db: Session) -> None:
    workers = db.query(WorkerHeartbeat).all()

    for worker in workers:
        worker.processed_count = 0

    db.commit()


def _alerts_response(db: Session):
    alerts = db.query(Alert).all()

    result = []

    for alert in alerts:
        result.append({
            "id": alert.id,
            "message": alert.message,
            "created_at": alert.created_at,
        })

    return result


def _clear_alerts(db: Session):
    count = db.query(Alert).delete(synchronize_session=False)

    db.commit()

    return {
        "message": "Alerts cleared",
        "deleted_count": count
    }


def _metrics_response(db: Session):
    redis_queue_length = get_queue_length()

    queued_count = db.query(Task).filter(Task.status == "queued").count()
    processing_count = db.query(Task).filter(Task.status == "processing").count()
    success_count = db.query(Task).filter(Task.status == "success").count()
    failed_count = db.query(Task).filter(Task.status == "failed").count()

    failure_reasons = {
        reason or "unknown": count
        for reason, count in (
            db.query(Task.failure_reason, func.count(Task.id))
            .filter(Task.status == "failed")
            .group_by(Task.failure_reason)
            .all()
        )
    }

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
        .filter(Task.is_poison.is_(True))
        .count()
    )

    failed_poison_count = (
        db.query(Task)
        .filter(Task.is_poison.is_(True))
        .filter(Task.status == "failed")
        .count()
    )

    now = datetime.now(UTC)
    alive_workers, stale_workers = _count_workers(db, now)

    recent_successes = (
        db.query(Task)
        .filter(Task.status == "success")
        .order_by(Task.id.desc())
        .limit(1000)
        .all()
    )

    throughput_last_minute = 0

    for task in recent_successes:
        if not task.updated_at:
            continue

        updated_at = ensure_utc(task.updated_at)
        seconds_since_update = (now - updated_at).total_seconds()

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


def _report_response(db: Session):
    return {
        "metrics": _metrics_response(db),
        "workers": _workers_response(db),
        "alerts": _alerts_response(db),
        "recent_logs": _logs_response(db, limit=20)["items"],
        "tasks": _tasks_response(db),
    }



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

@app.post("/tasks/bulk")
def create_bulk_tasks(
    count: int = Query(default=10, ge=1, le=1000),
    priority: int = 1,
    db: Session = Depends(get_db),
):
    created_task_ids = []

    for _ in range(count):
        task = create_task(db=db, priority=priority)
        enqueue_task(task.id)
        created_task_ids.append(task.id)

    return {
        "message": "Bulk tasks created",
        "count": count,
        "task_ids": created_task_ids
    }

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
    return _tasks_response(db, status, is_poison, limit, offset)

@app.get("/tasks/{task_id}")
def get_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
):
    result = _task_detail_response(db, task_id)

    if result is None:
        return {"error": "Task not found"}

    return result

@app.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    result = _retry_task(db, task_id)

    if result is None:
        return {"error": "Task not found"}

    return result


@app.post("/tasks/{task_id}/duplicate")
def duplicate_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = (
        db.query(Task)
        .filter(Task.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    enqueue_task(task.id)

    return {
        "message": "Duplicate task pushed into Redis",
        "task_id": task_id
    }

@app.delete("/tasks/completed")
def delete_completed_tasks(db: Session = Depends(get_db)):
    return _delete_tasks_by_status(db, "success", "Completed tasks deleted")

@app.delete("/tasks/failed")
def delete_failed_tasks(db: Session = Depends(get_db)):
    return _delete_tasks_by_status(db, "failed", "Failed tasks deleted")

@app.get("/logs")
def get_logs(
    task_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return _logs_response(db, task_id, limit, offset)

@app.get("/workers")
def get_workers(db: Session = Depends(get_db)):
    return _workers_response(db)


@app.post("/workers/reset-counts")
def reset_worker_counts(db: Session = Depends(get_db)):
    _reset_worker_counts(db)
    return {"message": "Worker counts reset"}


@app.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    return _alerts_response(db)

@app.delete("/alerts")
def clear_alerts(db: Session = Depends(get_db)):
    return _clear_alerts(db)

@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    return _metrics_response(db)

@app.get("/prometheus", response_class=PlainTextResponse)
def get_prometheus_metrics(db: Session = Depends(get_db)):
    queued_count = db.query(Task).filter(Task.status == "queued").count()
    processing_count = db.query(Task).filter(Task.status == "processing").count()
    success_count = db.query(Task).filter(Task.status == "success").count()
    failed_count = db.query(Task).filter(Task.status == "failed").count()

    poison_count = (
        db.query(Task)
        .filter(Task.is_poison.is_(True))
        .count()
    )

    failed_poison_count = (
        db.query(Task)
        .filter(Task.is_poison.is_(True))
        .filter(Task.status == "failed")
        .count()
    )

    redis_queue_length = get_queue_length()

    now = datetime.now(UTC)
    alive_workers, stale_workers = _count_workers(db, now)

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

@app.get("/config")
def get_config():
    return {
        "environment": ENVIRONMENT,
        "version": SYSTEM_VERSION
    }

@app.get("/system-state")
def get_system_state():
    return {"paused": _is_system_paused()}

@app.post("/pause")
def pause_system(_: None = Depends(require_admin_token)):
    try:
        redis_client.set(SYSTEM_PAUSED_KEY, "1")
        paused = _is_system_paused()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc

    return {"paused": paused}


@app.post("/resume")
def resume_system(_: None = Depends(require_admin_token)):
    try:
        redis_client.set(SYSTEM_PAUSED_KEY, "0")
        paused = _is_system_paused()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc

    return {"paused": paused}


@app.delete("/queue")
def clear_task_queue():
    deleted_count = clear_queue()

    return {
        "message": "Queue cleared",
        "deleted": deleted_count
    }

@app.delete("/reset")
def reset_system(
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
):
    clear_queue()

    db.query(TaskLog).delete()
    db.query(Alert).delete()
    db.query(Task).delete()

    workers = db.query(WorkerHeartbeat).all()

    for worker in workers:
        worker.processed_count = 0

    db.commit()

    return {
        "message": "System reset complete"
    }


@app.get("/report")
def get_report(db: Session = Depends(get_db)):
    return _report_response(db)

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(str(BASE_DIR / "static" / "favicon.svg"))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


@app.websocket("/ws/operations")
async def operations_websocket(websocket: WebSocket):
    await websocket.accept()

    pubsub = redis_client.pubsub()
    pubsub.subscribe(OPERATIONS_CHANNEL)

    try:
        stored_events = redis_client.lrange(
            OPERATIONS_HISTORY_KEY,
            0,
            OPERATIONS_HISTORY_LIMIT - 1,
        )

        for stored_event in reversed(stored_events):
            data = json.loads(stored_event)
            data["replayed"] = True
            await websocket.send_text(json.dumps(data, default=str))

        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)

            if message:
                data = message["data"]

                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                await websocket.send_text(data)

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info("operations websocket disconnected")

    except Exception:
        logger.exception("unexpected operations websocket error")

    finally:
        pubsub.close()
