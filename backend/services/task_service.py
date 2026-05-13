from datetime import datetime

from models import Task


def create_task(
    db,
    priority=1,
    is_poison=False
):
    task = Task(
        status="queued",
        priority=priority,
        is_poison=is_poison,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task