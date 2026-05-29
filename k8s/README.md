# Failure Playground Kubernetes Stack

These manifests run Failure Playground on a local Kubernetes cluster:

- FastAPI API
- Worker Deployment with 2 replicas
- Redis
- PostgreSQL with a PersistentVolumeClaim
- Jaeger
- Prometheus
- Grafana

Grafana runs on Kubernetes in v4.0-b, but dashboard provisioning may remain Docker Compose-first until that setup is worth migrating cleanly.

## Build The Backend Image

Kubernetes uses the same backend Dockerfile as Docker Compose. Build the local image before applying the manifests:

```bash
docker build -t failure-playground-backend:latest ./backend
```

If you are using Minikube, build the image inside Minikube's Docker environment or load it into the cluster:

```bash
minikube image build -t failure-playground-backend:latest ./backend
```

## Start The Stack

From the project root:

```bash
kubectl apply -f k8s/
kubectl get pods
kubectl get svc
```

The API Deployment runs Alembic migrations before starting Uvicorn. Kubernetes does not support Docker Compose `depends_on` directly, so startup ordering is handled by normal pod restarts and readiness probes.

## Open The Services Locally

Forward the API service to the same local port used by Docker Compose:

```bash
kubectl port-forward service/api-service 8001:8000
kubectl port-forward service/jaeger-service 16686:16686
kubectl port-forward service/prometheus-service 9091:9090
kubectl port-forward service/grafana-service 3000:3000
```

Then open:

- Dashboard: <http://localhost:8001>
- API docs: <http://localhost:8001/docs>
- Health: <http://localhost:8001/health>
- Jaeger: <http://localhost:16686>
- Prometheus: <http://localhost:9091>
- Grafana: <http://localhost:3000>

Default Grafana login:

```text
Username: admin
Password: admin
```

## Service Names

The Kubernetes manifests use cluster service names for internal traffic:

- PostgreSQL: `postgres-service`
- Redis: `redis-service`
- API: `api-service`
- Jaeger: `jaeger-service`
- Prometheus: `prometheus-service`
- Grafana: `grafana-service`

The shared ConfigMap sets:

- `DATABASE_URL=postgresql+psycopg2://app:app@postgres-service:5432/failure_playground`
- `REDIS_HOST=redis-service`
- `API_BASE_URL=http://api-service:8000`
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-service:4317`

Workers use the Kubernetes Downward API for `WORKER_NAME`, so worker heartbeat names match their pod names.

Prometheus uses a Kubernetes ConfigMap and scrapes the API through `api-service:8000` at `/prometheus`.

## Verification

Useful checks after applying the manifests:

```bash
kubectl apply -f k8s/
kubectl get pods
kubectl get svc
kubectl logs deployment/jaeger
kubectl logs deployment/prometheus
kubectl logs deployment/grafana
```

## Docker Compose Still Works

`docker-compose.yml` is unchanged. The existing Docker Compose workflow remains:

```bash
docker compose up --build
```
