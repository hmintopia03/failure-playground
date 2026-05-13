def task_to_dict(task):
    return {
        "id": task.id,
        "status": task.status,
        "retry_count": task.retry_count,
        "priority": task.priority,
        "failure_reason": task.failure_reason,
        "is_poison": task.is_poison,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "processing_duration_seconds": task.processing_duration_seconds,
    }


def worker_to_dict(worker):
    return {
        "worker_name": worker.worker_name,
        "last_seen": worker.last_seen,
        "processed_count": worker.processed_count,
    }


def alert_to_dict(alert):
    return {
        "id": alert.id,
        "message": alert.message,
        "created_at": alert.created_at,
    }