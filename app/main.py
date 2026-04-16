"""
Flow Procurement Platform — FastAPI application.

Three-layer architecture:
  Layer 1 (Data)         : EWM integration   → app.data_layer
  Layer 2 (Optimisation) : HiGHS solver      → app.optimizer
  Layer 3 (Decision)     : REST JSON API     → app.routes

Start with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db
from app.db_routes import db_router
from app.integration_routes import integration_router
from app.mip_routes import mip_router
from app.process_digging_routes import digging_router
from app.risk_routes import risk_router
from app.routes import router
from app.auth import auth_router, seed_admin
from app.admin_routes import admin_router
from app.buying_routes import buying_router
from app.portal_routes import portal_router
from app.supplier_routes import supplier_router
from app.whatif_routes import whatif_router
from app.ewm_integration import ewm_router
from app.auction_routes import auction_router
from app.prediction_routes import prediction_router
from app.project_routes import project_router
from app.bi_routes import bi_router
from app.superadmin_routes import superadmin_router
from app.marketplace_routes import marketplace_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — initialise database schema + seed data
    try:
        init_db()
        from app.migrations import run_migrations
        from app.database import _get_client
        run_migrations(_get_client())
        seed_admin()
        from app.supplier_engine import seed_demo_suppliers
        seed_demo_suppliers()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Startup DB init failed: %s", e)
    yield
    # shutdown


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "REST API for multi-criteria order portfolio optimisation. "
        "Minimises a weighted combination of cost, lead-time, compliance "
        "risk, and ESG impact across pre-selected suppliers using HiGHS.\n\n"
        "**Modes:** continuous (LP) and binary (MIP).\n\n"
        "**Endpoints:**\n"
        "- `/api/v1/optimize` — core optimisation\n"
        "- `/api/v1/dashboard` — Pareto front + radar charts\n"
        "- `/api/v1/stealth` — raw solver diagnostics\n"
        "- `/api/v1/weights` — live weight tuning\n\n"
        "**Dashboard UI:** [`/ui`](/ui)"
    ),
    lifespan=lifespan,
)

# CORS — configurable via FLOW_CORS_ORIGINS env var
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


from app.observability import ObservabilityMiddleware, get_metrics_summary
from app.tenant_context import TenantContextMiddleware

app.add_middleware(ObservabilityMiddleware)
# Resolve tenant before every other middleware needs it — stacked LIFO so
# we add it *after* Observability which means it runs *before*.
app.add_middleware(TenantContextMiddleware)


# Request rate limiting (in-memory, per-IP sliding window). Disabled by
# default; enable with FLOW_RATE_LIMIT_PER_MINUTE=<N>. With N=0 this is
# a no-op. Single-replica MVP only — behind multiple replicas push to
# Redis before trusting it.
class _RateLimitStore:
    def __init__(self):
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        import time as _t
        now = _t.time()
        hits = [h for h in self.hits.get(key, []) if now - h < window_s]
        if len(hits) >= limit:
            self.hits[key] = hits
            return False
        hits.append(now)
        self.hits[key] = hits
        return True


_rate_store = _RateLimitStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429s when a single IP exceeds FLOW_RATE_LIMIT_PER_MINUTE.

    Only applies to /api/v1/* paths — static assets, /docs, health
    probes stay unlimited so monitoring/CDNs don't self-DoS."""
    async def dispatch(self, request: Request, call_next):
        import os
        limit = int(os.environ.get("FLOW_RATE_LIMIT_PER_MINUTE", "0") or 0)
        if limit > 0 and request.url.path.startswith("/api/v1/"):
            client_host = request.client.host if request.client else "unknown"
            key = f"{client_host}:{request.url.path.split('/')[3] or 'root'}"
            if not _rate_store.allow(key, limit, 60.0):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests",
                        "limit": limit,
                        "window_s": 60,
                    },
                )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)


# ── API routes ──
app.include_router(router, prefix="/api/v1")
app.include_router(db_router, prefix="/api/v1")
app.include_router(digging_router, prefix="/api/v1")
app.include_router(mip_router, prefix="/api/v1")
app.include_router(whatif_router, prefix="/api/v1")
app.include_router(integration_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(buying_router, prefix="/api/v1")
app.include_router(marketplace_router, prefix="/api/v1")
app.include_router(supplier_router, prefix="/api/v1")
app.include_router(ewm_router, prefix="/api/v1")
app.include_router(auction_router, prefix="/api/v1")
app.include_router(prediction_router, prefix="/api/v1")
app.include_router(project_router, prefix="/api/v1")
app.include_router(bi_router, prefix="/api/v1")
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(portal_router)
app.include_router(superadmin_router)

# ── Static files (dashboard UI, admin panel, supplier portal) ──
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static-assets")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to the graphical dashboard."""
    return RedirectResponse(url="/ui")


@app.get("/ui", include_in_schema=False)
@app.get("/ui/{path:path}", include_in_schema=False)
async def serve_ui(path: str = ""):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin-ui", include_in_schema=False)
@app.get("/admin-ui/{path:path}", include_in_schema=False)
async def serve_admin_ui(path: str = ""):
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/portal-ui", include_in_schema=False)
@app.get("/portal-ui/{path:path}", include_in_schema=False)
async def serve_portal_ui(path: str = ""):
    return FileResponse(STATIC_DIR / "portal.html")


@app.get("/requester", include_in_schema=False)
@app.get("/requester/{path:path}", include_in_schema=False)
async def serve_requester_ui(path: str = ""):
    return FileResponse(STATIC_DIR / "requester.html")


@app.get("/superadmin-ui", include_in_schema=False)
@app.get("/superadmin-ui/{path:path}", include_in_schema=False)
async def serve_superadmin_ui(path: str = ""):
    return FileResponse(STATIC_DIR / "superadmin.html")


@app.get("/health", tags=["system"])
async def health():
    """Liveness probe — just proves the process is up."""
    return {"status": "ok", "version": settings.app_version}


@app.get("/metrics", tags=["system"])
async def metrics_endpoint():
    """Rolling in-process metrics: request counts, error counts, p50/p95/p99
    latency per (method, route). Useful for ops dashboards without standing
    up Prometheus + Grafana. Reset on every process restart."""
    return get_metrics_summary()


@app.get("/health/ready", tags=["system"])
async def readiness():
    """Readiness probe — checks every subsystem the app actually depends on.

    Returns 200 with a per-subsystem verdict so Railway (or any LB) can
    keep routing even when optional pieces are degraded. Each check is
    isolated so one slow check can't cascade.
    """
    import time as _time

    checks: dict[str, dict] = {}

    # Database
    t = _time.perf_counter()
    try:
        from app.database import DB_AVAILABLE, _get_client
        if DB_AVAILABLE:
            client = _get_client()
            client.execute("SELECT 1")
            checks["database"] = {"status": "ok", "latency_ms": round((_time.perf_counter() - t) * 1000, 1)}
        else:
            checks["database"] = {"status": "disabled", "note": "in-memory mode"}
    except Exception as exc:
        checks["database"] = {"status": "degraded", "error": str(exc)[:200]}

    # LLM backend
    checks["llm"] = {
        "status": "ok" if settings.llm_api_key else "missing_key",
        "model": settings.llm_model,
        "heavy_model": settings.llm_heavy_model,
    }

    # BI mock layer
    try:
        from app.bi_mock import list_connectors
        connectors = list_connectors()
        checks["bi_adapters"] = {
            "status": "ok",
            "count": len(connectors),
            "modes": list({c.get("source", "mock") for c in connectors}),
        }
    except Exception as exc:
        checks["bi_adapters"] = {"status": "degraded", "error": str(exc)[:200]}

    # Solver
    try:
        from scipy.optimize import linprog  # noqa — import probe
        checks["solver"] = {"status": "ok", "engine": "HiGHS"}
    except Exception as exc:
        checks["solver"] = {"status": "degraded", "error": str(exc)[:200]}

    # OCR — optional
    try:
        import pytesseract  # noqa
        checks["ocr"] = {"status": "ok" if settings.pdf_ocr_enabled else "disabled"}
    except Exception:
        checks["ocr"] = {"status": "not_installed"}

    # Overall verdict — 'ok' when no hard degradation
    hard_failed = [k for k, v in checks.items() if v.get("status") == "degraded"]
    overall = "degraded" if hard_failed else "ok"

    return {
        "status": overall,
        "version": settings.app_version,
        "checks": checks,
        "degraded": hard_failed,
    }
