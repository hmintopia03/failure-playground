# Failure Playground Kubernetes Runbook

This directory contains simple local Kubernetes manifests for the Failure Playground application, observability stack, and worker autoscaling. The manifests are intended for learning and local validation, not production deployment.

## Prerequisites

- A local Kubernetes cluster, such as Docker Desktop Kubernetes, Minikube, kind, or another single-node dev cluster.
- `kubectl` configured for that cluster.
- Docker or a cluster-specific image build path.
- `metrics-server` installed if you want the worker HPA to report CPU metrics and make scaling decisions.

Docker Compose remains supported separately through `docker-compose.yml`.

## Local Image

The API and worker use the existing backend Dockerfile. Build the image before applying the manifests:

```bash
docker build -t failure-playground-backend:latest ./backend
```

If your cluster cannot see local Docker images directly, build or load the image into the cluster. For Minikube:

```bash
minikube image build -t failure-playground-backend:latest ./backend
```

## Apply

From the project root:

```bash
kubectl apply -f k8s/
```

This creates the core app stack, observability stack, PostgreSQL PVC, shared ConfigMap, and worker HPA.

## Verification

Check pods, services, autoscaling, and key logs:

```bash
kubectl get pods
kubectl get svc
kubectl get hpa
kubectl describe hpa worker-hpa
kubectl logs deployment/api
kubectl logs deployment/worker
kubectl logs deployment/jaeger
kubectl logs deployment/prometheus
kubectl logs deployment/grafana
```

If the HPA shows unknown CPU metrics, confirm `metrics-server` is installed and ready in your local cluster.

## Port Forwarding

Open the API and dashboard:

```bash
kubectl port-forward service/api-service 8001:8000
```

Open observability tools:

```bash
kubectl port-forward service/jaeger-service 16686:16686
kubectl port-forward service/prometheus-service 9091:9090
kubectl port-forward service/grafana-service 3000:3000
```

URLs:

- Dashboard: <http://localhost:8001>
- API docs: <http://localhost:8001/docs>
- Jaeger: <http://localhost:16686>
- Prometheus: <http://localhost:9091>
- Grafana: <http://localhost:3000>

Default Grafana login:

```text
Username: admin
Password: admin
```

Grafana runs in Kubernetes, but dashboard provisioning may still be Docker Compose-first unless migrated separately.

## Kubernetes Mapping

- `api`: Deployment plus `api-service`
- `worker`: replica-based Deployment plus `worker-hpa`
- `redis`: Deployment plus `redis-service`
- `postgres`: Deployment plus `postgres-service` and `postgres-pvc`
- `failure-playground-config`: shared application ConfigMap
- `jaeger`: Deployment plus `jaeger-service`
- `prometheus`: ConfigMap, Deployment, and `prometheus-service`
- `grafana`: Deployment plus `grafana-service`

Prometheus scrapes the API through Kubernetes DNS at `api-service:8000`.

The API and worker export traces to Jaeger through:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-service:4317
```

## Cleanup

Remove the Kubernetes stack:

```bash
kubectl delete -f k8s/
```
