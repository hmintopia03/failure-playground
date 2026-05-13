# Failure Playground

A simulated distributed job-processing system for learning backend/platform engineering concepts.

## What it does

- Creates background tasks
- Queues jobs with Redis
- Processes jobs with multiple workers
- Stores state in Postgres
- Retries failed jobs with backoff
- Detects stale workers
- Tracks metrics, logs, alerts, and task state
- Provides an operational dashboard

## Stack

- FastAPI
- SQLAlchemy
- Postgres
- Redis
- Docker Compose
- Vanilla JavaScript dashboard
- Chart.js

## Run

```bash
docker compose up --build