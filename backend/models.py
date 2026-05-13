from sqlalchemy import Column, Integer, String, ForeignKey
from db import Base
from sqlalchemy import DateTime
from datetime import datetime
from sqlalchemy import Boolean
from sqlalchemy import Integer

class Task(Base):
    __tablename__ = "tasks"


    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="queued")
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    retry_at = Column(DateTime, nullable=True)

    processing_started_at = Column(DateTime, nullable=True)
    priority = Column(Integer, default=1)
    failure_reason = Column(String, nullable=True)

    is_poison = Column(Boolean, default=False)

    processing_duration_seconds = Column(Integer, nullable=True)

class TaskLog(Base):
    __tablename__ = "task_logs"
    created_at = Column(DateTime, default=datetime.utcnow)
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    message = Column(String)

class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id = Column(Integer, primary_key=True)
    worker_name = Column(String, unique=True)
    last_seen = Column(DateTime, default=datetime.utcnow)
    processed_count = Column(Integer, default=0)

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)