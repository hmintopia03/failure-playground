from datetime import datetime, UTC

from models import Task
from logger import log_event

def create_task(db, priority=1, is_poison=False):
    now = datetime.now(UTC)

    
    task = Task(
        status="queued",
        priority=priority,
        is_poison=is_poison,        
        retry_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task)
    db.commit()
    db.refresh(task)
    
    log_event(
        "task_created",
        task_id=task.id,
        status=task.status,
        priority=task.priority,
        is_poison=task.is_poison,
    )

    return task