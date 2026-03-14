"""
INTERCARS Order Portfolio Optimizer — FastAPI application.

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.db_routes import db_router
from app.integration_routes import integration_router
from app.mip_routes import mip_router
from app.process_digging_routes import digging_router
from app.risk_routes import risk_router
from app.routes import router
from app.auth import auth_router, seed_default_admin
from app.admin_routes import admin_router
from app.buying_routes import buying_router
from app.portal_routes import portal_router
from app.supplier_routes import supplier_router
from app.whatif_routes import whatif_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — initialise database schema (if Turso is configured)
    init_db()
    seed_default_admin()
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

# CORS — allow BI dashboards from any origin (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ──
app.include_router(router, prefix="/api/v1")
app.include_router(db_router, prefix="/api/v1")
app.include_router(digging_router, prefix="/api/v1")
app.include_router(mip_router, prefix="/api/v1")
app.include_router(whatif_router, prefix="/api/v1")
app.include_router(integration_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(buying_router, prefix="/api/v1")
app.include_router(supplier_router, prefix="/api/v1")
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(portal_router)

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


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": settings.app_version}
