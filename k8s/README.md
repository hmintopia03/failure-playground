# Failure Playground Kubernetes Core Stack

These manifests run the core Failure Playground stack on a local Kubernetes cluster:

- FastAPI API
- Worker Deployment with 2 replicas
- Redis
- PostgreSQL with a PersistentVolumeClaim

Prometheus, Grafana, and Jaeger are intentionally not migrated here. The observability stack migration is deferred to v4.0-b.

## Build The Backend Image

Kubernetes uses the same backend Dockerfile as Docker Compose. Build the local image before applying the manifests:

```bash
docker build -t failure-playground-backend:latest ./backend
```

If you are using Minikube, build the image inside Minikube's Docker environment or load it into the cluster:

```bash
minikube image build -t failure-playground-backend:latest ./backend
```

## Start The Core Stack

From the project root:

```bash
kubectl apply -f k8s/
kubectl get pods
kubectl get svc
```

The API Deployment runs Alembic migrations before starting Uvicorn. Kubernetes does not support Docker Compose `depends_on` directly, so startup ordering is handled by normal pod restarts and readiness probes.

## Open The API Locally

Forward the API service to the same local port used by Docker Compose:

```bash
kubectl port-forward service/api-service 8001:8000
```

Then open:

- Dashboard: <http://localhost:8001>
- API docs: <http://localhost:8001/docs>
- Health: <http://localhost:8001/health>

## Service Names

The Kubernetes manifests use cluster service names for internal traffic:

- PostgreSQL: `postgres-service`
- Redis: `redis-service`
- API: `api-service`

The shared ConfigMap sets:

- `DATABASE_URL=postgresql+psycopg2://app:app@postgres-service:5432/failure_playground`
- `REDIS_HOST=redis-service`
- `API_BASE_URL=http://api-service:8000`

Workers use the Kubernetes Downward API for `WORKER_NAME`, so worker heartbeat names match their pod names.

## Docker Compose Still Works

`docker-compose.yml` is unchanged. The existing Docker Compose workflow remains:

```bash
docker compose up --build
```
