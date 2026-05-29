# Failure Playground

## Overview

Failure Playground is a platform engineering project designed to explore reliability, observability, and operational behavior in distributed systems.

The project began as a simple task queue and evolved into a Kubernetes-based platform with tracing, metrics, autoscaling, and CI/CD validation.

## Problem

Modern backend systems fail in many ways:

* workers crash
* tasks fail
* queues grow unexpectedly
* latency increases
* deployments introduce regressions

I wanted to understand how operators detect and investigate these situations.

## Solution

I built a distributed task-processing platform using FastAPI, PostgreSQL, Docker, Kubernetes, OpenTelemetry, Prometheus, Grafana, and GitHub Actions.

The system supports:

* asynchronous task processing
* retries and failure handling
* operational dashboards
* distributed tracing
* autoscaling
* automated validation pipelines

## Key Engineering Decisions

### PostgreSQL Instead of Redis

I intentionally used PostgreSQL to better understand transactional queue patterns and worker coordination.

### Failure-First Design

The project was built around failure scenarios rather than happy-path processing.

### Observability as a Core Feature

Metrics, traces, and operational visibility were treated as primary requirements rather than later additions.

### Kubernetes Validation

The project includes Kubernetes manifests and CI validation to ensure infrastructure definitions remain deployable.

## Outcomes

* Built and operated a multi-worker task platform
* Implemented observability tooling
* Learned Kubernetes deployment patterns
* Implemented GitHub Actions CI/CD
* Gained practical platform engineering experience

## Future Work

* Alertmanager integration
* SLO and error-budget tracking
* Canary deployments
* Service-to-service communication patterns
