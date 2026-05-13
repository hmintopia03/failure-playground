import os


ENVIRONMENT = os.getenv(
    "ENVIRONMENT",
    "local"
)

SYSTEM_VERSION = "0.1.0"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://app:app@postgres:5432/failure_playground"
)

TASK_QUEUE_NAME = "task_queue"

MAX_RETRIES = 3

TASK_TIMEOUT_SECONDS = 30

MAX_TASKS_PER_WINDOW = 5

WINDOW_SECONDS = 10

WORKER_STALE_SECONDS = 10