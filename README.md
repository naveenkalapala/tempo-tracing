# Distributed Tracing with Grafana Tempo, Alloy & OpenTelemetry

A complete observability stack for Kubernetes that generates synthetic traces and logs, collected via Grafana Alloy and stored in Tempo and Loki.

## Architecture

```
┌──────────────────┐
│  Log Generator   │  (Python + OpenTelemetry SDK)
│  Structured JSON  │
└────────┬─────────┘
         │
    stdout (logs) + OTLP gRPC (traces)
         │
         ▼
┌──────────────────┐
│  Grafana Alloy   │  (DaemonSet - OTel Collector)
└───────┬──┬───────┘
        │  │
   Loki │  │ OTLP
        ▼  ▼
┌────────┐ ┌───────┐
│  Loki  │ │ Tempo │
└────┬───┘ └───┬───┘
     │         │
     ▼         ▼
┌──────────────────┐
│     Grafana      │  (Logs + Traces + Drilldown)
└──────────────────┘
```

## Components

| Component | Chart | Purpose |
|---|---|---|
| **Log Generator** | Custom Docker image | Emits JSON logs to stdout + OTel traces via OTLP |
| **Grafana Alloy** | `grafana/alloy` v1.7.0 | Collects logs (Kubernetes source) and traces (OTLP receiver) |
| **Grafana Tempo** | `grafana/tempo` v1.24.4 | Distributed tracing backend with metrics generator |
| **Grafana Loki** | `grafana/loki` v6.55.0 | Log aggregation (SingleBinary mode) |
| **Grafana** | Existing deployment | Visualization with Logs/Traces Drilldown |

## Features

- **Correlated logs and traces** - Same `trace_id` in both Loki logs and Tempo traces
- **Parent-child spans** - HTTP request spans with child DB query spans
- **10 simulated microservices** with realistic endpoints, status codes, and error patterns
- **Metrics from traces** - Tempo metrics generator produces span metrics, service graphs
- **Structured metadata** - `trace_id`, `user_id`, `http_path` as Loki structured metadata

## Quick Start

```bash
# Add Helm repos
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create namespace
kubectl create namespace logging

# Install Loki
helm install loki grafana/loki -n logging -f loki/loki-values.yaml

# Install Tempo
helm install tempo grafana/tempo -n logging -f tempo/tempo-values.yaml

# Deploy Alloy ConfigMap and install Alloy
kubectl apply -f alloy/configmap.yaml
helm install alloy grafana/alloy -n logging -f alloy/alloy-values.yaml

# Deploy log generator
kubectl apply -f k8s/deployment.yaml

# Verify all pods are running
kubectl get pods -n logging
```

## Grafana Data Sources

Add these data sources in Grafana:

| Data Source | Type | URL |
|---|---|---|
| Loki | Loki | `http://loki-gateway.logging.svc.cluster.local` |
| Tempo | Tempo | `http://tempo.logging.svc.cluster.local:3200` |

**Tempo settings:** Use HTTP protocol (not gRPC). Disable streaming queries.

## Configuration

### Environment Variables (Log Generator)

| Variable | Default | Description |
|---|---|---|
| `LOGS_PER_SECOND` | `10` | Log emission rate |
| `ERROR_RATE` | `0.05` | Fraction of ERROR logs |
| `WARN_RATE` | `0.10` | Fraction of WARN logs |
| `DEBUG_RATE` | `0.10` | Fraction of DEBUG logs |
| `OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint for traces |
| `TRACING_ENABLED` | `true` | Enable/disable OTel tracing |
| `ENVIRONMENT` | `dev` | Environment label |
| `REGION` | `us-east-1` | Region label |
| `CLUSTER` | `eks-dev-cluster` | Cluster name |

## Useful Queries

### Loki (LogQL)
```logql
# All errors from payment-service
{service_name="payment-service", level="ERROR"}

# 5xx responses
{http_status_code=~"5.."}

# Rate of logs per service
sum by (service_name) (rate({app="log-generator"} [5m]))
```

### Tempo (TraceQL)
```traceql
# Traces with errors
{status = error}

# Slow HTTP requests
{span.http.response_time_ms > 1000}

# DB queries on users table
{span.db.sql.table = "users"}
```

## Docker Image

```bash
docker build -t nkalapala24/log-generator:v2 .
docker push nkalapala24/log-generator:v2
```

Image: `nkalapala24/log-generator:v2` (Python 3.12-slim + OpenTelemetry SDK)
