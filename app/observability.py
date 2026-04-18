"""
observability.py — request tracing, JSON logs, in-process metrics.

Sentry-ready: `sentry_sdk.init(...)` slots in without touching anything else.
Metrics stay in-memory for now because the platform runs one Railway
replica; when we scale horizontally, swap `_metrics` for a Prometheus
client or push to a hosted service — the middleware surface stays the
same.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


log = logging.getLogger("flow.request")


class _RollingMetrics:
    """Tiny in-memory sink. Per (method, route_bucket):
      - total count
      - error count (status >= 500)
      - rolling window of the last 500 latencies_ms for percentiles
    Memory bound: O(routes × 500).
    """
    def __init__(self, window: int = 500):
        self.window = window
        self.counts: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.latencies: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=window))

    def record(self, route_key: str, latency_ms: float, status: int) -> None:
        self.counts[route_key] += 1
        if status >= 500:
            self.errors[route_key] += 1
        self.latencies[route_key].append(latency_ms)

    def summary(self) -> dict:
        out: list[dict] = []
        for key in sorted(self.counts.keys()):
            lats = sorted(self.latencies.get(key, []))
            n = len(lats)
            if n == 0:
                p50 = p95 = p99 = 0.0
            else:
                p50 = lats[min(n - 1, n // 2)]
                p95 = lats[min(n - 1, int(n * 0.95))]
                p99 = lats[min(n - 1, int(n * 0.99))]
            out.append({
                "route": key,
                "count": self.counts[key],
                "errors": self.errors.get(key, 0),
                "error_rate": round(self.errors.get(key, 0) / self.counts[key], 4),
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
            })
        totals = {
            "routes_tracked": len(out),
            "total_requests": sum(self.counts.values()),
            "total_errors": sum(self.errors.values()),
        }
        return {"totals": totals, "routes": out}


metrics = _RollingMetrics()


def _route_bucket(path: str) -> str:
    """Collapse dynamic segments so /orders/abc-123 and /orders/def-456
    share a bucket. Cheap rules — swap for the real routing table once
    we want per-handler granularity."""
    parts = path.rstrip("/").split("/")
    return "/".join(
        p if not p or not (p.isdigit() or len(p) > 16 or "-" in p) else "{id}"
        for p in parts
    ) or "/"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Attaches an X-Request-ID, logs each request as structured JSON,
    records latency + status in the rolling metrics store.

    Designed so downstream integrations (Sentry / Datadog / Axiom) can
    just read the structured log lines — no extra wiring inside handlers.
    """
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        start = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            # Surface the request ID on the response so clients can correlate
            # errors with server-side logs/metrics.
            response.headers["X-Request-ID"] = rid
            return response
        except Exception as exc:
            log.exception("unhandled error rid=%s path=%s: %s", rid, request.url.path, exc)
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            route = f"{request.method} {_route_bucket(request.url.path)}"
            metrics.record(route, latency_ms, status)
            payload = {
                "ts": time.time(),
                "rid": rid,
                "method": request.method,
                "path": request.url.path,
                "route": route,
                "status": status,
                "latency_ms": latency_ms,
                "client": request.client.host if request.client else "",
                "user_agent": request.headers.get("user-agent", "")[:120],
            }
            # Single-line JSON so log shippers (Axiom, Grafana Loki) parse
            # without a regex. stdout is flushed line-by-line by default
            # in Docker so nothing extra needed.
            print(json.dumps(payload, ensure_ascii=False), flush=True)


def get_metrics_summary() -> dict:
    """Exposed via /metrics endpoint."""
    return metrics.summary()
