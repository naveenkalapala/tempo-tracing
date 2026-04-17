import json
import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import StatusCode


# Configuration (all tuneable via environment variables)

LOGS_PER_SECOND = int(os.getenv("LOGS_PER_SECOND", "10"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.05"))        # 5 %
WARN_RATE = float(os.getenv("WARN_RATE", "0.10"))          # 10 %
DEBUG_RATE = float(os.getenv("DEBUG_RATE", "0.10"))         # 10 %
APP_NAME = os.getenv("APP_NAME", "log-generator")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
REGION = os.getenv("REGION", "us-east-1")
CLUSTER = os.getenv("CLUSTER", "eks-dev-cluster")
NAMESPACE = os.getenv("NAMESPACE", "logging")
POD_NAME = os.getenv("POD_NAME", f"log-generator-{uuid.uuid4().hex[:8]}")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
TRACING_ENABLED = os.getenv("TRACING_ENABLED", "true").lower() == "true"


# Realistic data pools

SERVICES = [
    "api-gateway", "auth-service", "user-service", "order-service",
    "payment-service", "inventory-service", "notification-service",
    "search-service", "recommendation-engine", "analytics-service",
]

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]

ENDPOINTS = [
    "/api/v1/users", "/api/v1/users/{id}", "/api/v1/users/{id}/profile",
    "/api/v1/orders", "/api/v1/orders/{id}", "/api/v1/orders/{id}/status",
    "/api/v1/payments", "/api/v1/payments/{id}/refund",
    "/api/v1/products", "/api/v1/products/{id}", "/api/v1/products/search",
    "/api/v1/inventory", "/api/v1/inventory/{id}/reserve",
    "/api/v1/notifications/send", "/api/v1/notifications/subscribe",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/refresh",
    "/api/v1/health", "/api/v1/ready",
    "/api/v2/recommendations", "/api/v2/analytics/events",
]

ERROR_MESSAGES = [
    "Connection refused to downstream service",
    "Request timeout after 30000ms",
    "Database connection pool exhausted",
    "Invalid authentication token",
    "Rate limit exceeded for client",
    "Upstream service returned 503",
    "Failed to serialize response payload",
    "Circuit breaker OPEN for dependency",
    "Out of memory while processing batch",
    "TLS handshake failed with upstream",
]

WARN_MESSAGES = [
    "Response time exceeded SLO threshold",
    "Retry attempt 2/3 for downstream call",
    "Cache miss ratio above 40%",
    "Connection pool utilisation above 80%",
    "Deprecated API version called",
    "Slow query detected (>500ms)",
    "JWT token expires in less than 5 minutes",
    "Disk usage above 75% on volume",
]

INFO_MESSAGES = [
    "Request processed successfully",
    "User authenticated",
    "Order created",
    "Payment processed",
    "Cache refreshed",
    "Health check passed",
    "Batch job completed",
    "Notification dispatched",
    "Search index updated",
    "Config reloaded from ConfigMap",
]

DEBUG_MESSAGES = [
    "Entering request handler",
    "Resolved user from token claims",
    "Query plan generated in 2ms",
    "Cache key computed",
    "Serialising response object",
    "Opening new DB connection",
    "Scheduling async task",
    "Reading feature flag state",
]

CALLER_MODULES = [
    "handler.go", "middleware.go", "repository.go", "service.go",
    "controller.go", "client.go", "worker.go", "scheduler.go",
]

DB_OPERATIONS = ["SELECT", "INSERT", "UPDATE", "DELETE"]
DB_TABLES = ["users", "orders", "payments", "products", "sessions", "events"]


# Helpers


def _pick_level() -> str:
    r = random.random()
    if r < ERROR_RATE:
        return "ERROR"
    if r < ERROR_RATE + WARN_RATE:
        return "WARN"
    if r < ERROR_RATE + WARN_RATE + DEBUG_RATE:
        return "DEBUG"
    return "INFO"


def _pick_status_code(level: str) -> int:
    if level == "ERROR":
        return random.choice([400, 401, 403, 404, 409, 422, 500, 502, 503, 504])
    if level == "WARN":
        return random.choice([200, 201, 204, 301, 408, 429])
    return random.choice([200, 200, 200, 201, 204])  # weighted towards 200


def _pick_response_time(level: str) -> int:
    """Return response time in ms, skewed higher for errors."""
    if level == "ERROR":
        return random.randint(500, 30000)
    if level == "WARN":
        return random.randint(200, 5000)
    if level == "DEBUG":
        return random.randint(1, 50)
    return random.randint(5, 500)


def _pick_message(level: str) -> str:
    if level == "ERROR":
        return random.choice(ERROR_MESSAGES)
    if level == "WARN":
        return random.choice(WARN_MESSAGES)
    if level == "DEBUG":
        return random.choice(DEBUG_MESSAGES)
    return random.choice(INFO_MESSAGES)


def _init_tracing():
    """Initialise OpenTelemetry tracing with OTLP gRPC exporter."""
    resource = Resource.create({
        "service.name": APP_NAME,
        "service.namespace": NAMESPACE,
        "deployment.environment": ENVIRONMENT,
        "k8s.pod.name": POD_NAME,
        "k8s.cluster.name": CLUSTER,
        "cloud.region": REGION,
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(APP_NAME)


def generate_log_entry(tracer) -> dict:
    """Build a single structured log entry with a matching OTel trace."""
    level = _pick_level()
    service = random.choice(SERVICES)
    method = random.choice(HTTP_METHODS)
    endpoint = random.choice(ENDPOINTS)
    status_code = _pick_status_code(level)
    response_time_ms = _pick_response_time(level)
    user_id = f"usr_{random.randint(1000, 99999)}"
    caller = f"{random.choice(CALLER_MODULES)}:{random.randint(10, 500)}"
    message = _pick_message(level)

    # Create a real OTel span so Tempo receives the trace
    with tracer.start_as_current_span(
        name=f"{method} {endpoint}",
        attributes={
            "http.method": method,
            "http.route": endpoint,
            "http.status_code": status_code,
            "http.response_time_ms": response_time_ms,
            "service.name": service,
            "user.id": user_id,
            "environment": ENVIRONMENT,
            "region": REGION,
            "cluster": CLUSTER,
        },
    ) as span:
        # Set span status based on log level
        if level == "ERROR":
            span.set_status(StatusCode.ERROR, message)
            span.record_exception(Exception(message))
        else:
            span.set_status(StatusCode.OK)

        # Extract the real trace_id and span_id from the active span
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")

        # Simulate a downstream DB call as a child span
        db_entry = None
        if random.random() < 0.3:
            with tracer.start_as_current_span(
                name=f"DB {random.choice(DB_OPERATIONS)}",
                attributes={
                    "db.system": "postgresql",
                    "db.operation": random.choice(DB_OPERATIONS),
                    "db.sql.table": random.choice(DB_TABLES),
                },
            ) as db_span:
                db_duration = random.randint(1, 800)
                db_entry = {
                    "operation": db_span.attributes.get("db.operation", ""),
                    "table": db_span.attributes.get("db.sql.table", ""),
                    "duration_ms": db_duration,
                    "rows_affected": random.randint(0, 1000),
                }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "logger": f"{service}.{random.choice(['http','grpc','worker','cron'])}",
        "message": message,
        "service": service,
        "environment": ENVIRONMENT,
        "region": REGION,
        "cluster": CLUSTER,
        "namespace": NAMESPACE,
        "pod": POD_NAME,
        "app": APP_NAME,
        "http": {
            "method": method,
            "path": endpoint,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
        },
        "trace_id": trace_id,
        "span_id": span_id,
        "user_id": user_id,
        "caller": caller,
        "request_id": str(uuid.uuid4()),
    }

    if db_entry:
        entry["db"] = db_entry

    # Occasionally add error stack trace
    if level == "ERROR" and random.random() < 0.4:
        entry["error"] = {
            "type": random.choice([
                "TimeoutError", "ConnectionError", "ValidationError",
                "AuthenticationError", "InternalServerError",
            ]),
            "stack": f"at {caller} -> {random.choice(CALLER_MODULES)}:{random.randint(10,500)}",
        }

    return entry


# Main loop

def main():
    # Unbuffered stdout for container log collection
    sys.stdout.reconfigure(line_buffering=True)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Initialise OTel tracing
    if TRACING_ENABLED:
        tracer = _init_tracing()
        logging.info("Tracing enabled | endpoint=%s", OTLP_ENDPOINT)
    else:
        tracer = trace.get_tracer(APP_NAME)
        logging.info("Tracing disabled (using noop tracer)")

    logging.info(
        "Starting log generator | rate=%d logs/s | error_rate=%.2f | env=%s | region=%s",
        LOGS_PER_SECOND, ERROR_RATE, ENVIRONMENT, REGION,
    )

    interval = 1.0 / LOGS_PER_SECOND if LOGS_PER_SECOND > 0 else 1.0
    counter = 0

    try:
        while True:
            start = time.monotonic()
            entry = generate_log_entry(tracer)
            print(json.dumps(entry, separators=(",", ":")))
            counter += 1

            if counter % (LOGS_PER_SECOND * 60) == 0:
                logging.info("Emitted %d log entries so far", counter)

            elapsed = time.monotonic() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logging.info("Shutting down after %d entries", counter)


if __name__ == "__main__":
    main()
