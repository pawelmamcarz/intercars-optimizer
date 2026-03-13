"""
Database REST endpoints — CRUD for suppliers, demand, results, and P2P events.

All endpoints are under /api/v1/db/...
Gracefully disabled when Turso is not configured (returns 503).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import Optional

from app.database import (
    DB_AVAILABLE,
    db_delete_demand,
    db_delete_p2p_events,
    db_delete_suppliers,
    db_get_demand,
    db_get_p2p_datasets,
    db_get_p2p_events,
    db_get_result_detail,
    db_get_results,
    db_get_suppliers,
    db_insert_demand,
    db_insert_p2p_events,
    db_insert_suppliers,
    db_save_result,
    get_db,
    seed_domain_data,
    seed_p2p_demo,
)
from app.upload import parse_demand_file, parse_p2p_events_file, parse_suppliers_file

db_router = APIRouter(prefix="/db", tags=["database"])


def _require_db(db):
    """Raise 503 if DB not available."""
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Set INTERCARS_TURSO_DATABASE_URL and INTERCARS_TURSO_AUTH_TOKEN (or TURSO_DATABASE_URL and TURSO_AUTH_TOKEN) env vars.",
        )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@db_router.get("/status", summary="Check database availability")
def db_status():
    return {
        "db_available": DB_AVAILABLE,
        "message": "Turso/libsql connected" if DB_AVAILABLE else "No database — demo-only mode",
    }


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@db_router.get("/suppliers", summary="Get suppliers from DB")
def get_suppliers(domain: str = Query(..., description="Domain name"), db=Depends(get_db)):
    _require_db(db)
    suppliers = db_get_suppliers(db, domain)
    return {"domain": domain, "suppliers": suppliers, "count": len(suppliers)}


@db_router.post("/suppliers/upload", summary="Upload suppliers from CSV/XLSX")
async def upload_suppliers(
    domain: str = Query(..., description="Domain to assign suppliers to"),
    file: UploadFile = File(...),
    replace: bool = Query(False, description="Replace existing suppliers for this domain"),
    db=Depends(get_db),
):
    _require_db(db)
    suppliers = await parse_suppliers_file(file)
    if not suppliers:
        raise HTTPException(400, "No valid supplier rows found in file")

    if replace:
        db_delete_suppliers(db, domain)

    count = db_insert_suppliers(db, domain, suppliers)
    return {"domain": domain, "inserted": count, "replaced": replace, "filename": file.filename}


@db_router.delete("/suppliers", summary="Delete suppliers for a domain")
def delete_suppliers(domain: str = Query(...), db=Depends(get_db)):
    _require_db(db)
    count = db_delete_suppliers(db, domain)
    return {"domain": domain, "deleted": count}


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------

@db_router.get("/demand", summary="Get demand from DB")
def get_demand(domain: str = Query(...), db=Depends(get_db)):
    _require_db(db)
    items = db_get_demand(db, domain)
    return {"domain": domain, "demand": items, "count": len(items)}


@db_router.post("/demand/upload", summary="Upload demand from CSV/XLSX")
async def upload_demand(
    domain: str = Query(...),
    file: UploadFile = File(...),
    replace: bool = Query(False),
    db=Depends(get_db),
):
    _require_db(db)
    items = await parse_demand_file(file)
    if not items:
        raise HTTPException(400, "No valid demand rows found in file")

    if replace:
        db_delete_demand(db, domain)

    count = db_insert_demand(db, domain, items)
    return {"domain": domain, "inserted": count, "replaced": replace, "filename": file.filename}


@db_router.delete("/demand", summary="Delete demand for a domain")
def delete_demand(domain: str = Query(...), db=Depends(get_db)):
    _require_db(db)
    count = db_delete_demand(db, domain)
    return {"domain": domain, "deleted": count}


# ---------------------------------------------------------------------------
# Optimization Results (history)
# ---------------------------------------------------------------------------

@db_router.get("/results", summary="List optimization results")
def list_results(
    domain: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db=Depends(get_db),
):
    _require_db(db)
    results = db_get_results(db, domain=domain, limit=limit)
    return {"results": results, "count": len(results)}


@db_router.get("/results/{result_id}", summary="Get optimization result detail")
def get_result(result_id: int, db=Depends(get_db)):
    _require_db(db)
    detail = db_get_result_detail(db, result_id)
    if not detail:
        raise HTTPException(404, f"Result {result_id} not found")
    return detail


# ---------------------------------------------------------------------------
# P2P Events
# ---------------------------------------------------------------------------

@db_router.get("/p2p-events/datasets", summary="List P2P event datasets")
def list_p2p_datasets(db=Depends(get_db)):
    _require_db(db)
    datasets = db_get_p2p_datasets(db)
    return {"datasets": datasets, "count": len(datasets)}


@db_router.get("/p2p-events", summary="Get P2P events from DB")
def get_p2p_events(dataset_name: str = Query("default"), db=Depends(get_db)):
    _require_db(db)
    events = db_get_p2p_events(db, dataset_name)
    return {"dataset_name": dataset_name, "events": events, "count": len(events)}


@db_router.post("/p2p-events/upload", summary="Upload P2P events from CSV/XLSX")
async def upload_p2p_events(
    dataset_name: str = Query("default"),
    file: UploadFile = File(...),
    replace: bool = Query(False),
    db=Depends(get_db),
):
    _require_db(db)
    events = await parse_p2p_events_file(file)
    if not events:
        raise HTTPException(400, "No valid P2P event rows found in file")

    if replace:
        db_delete_p2p_events(db, dataset_name)

    count = db_insert_p2p_events(db, dataset_name, events)
    return {"dataset_name": dataset_name, "inserted": count, "replaced": replace, "filename": file.filename}


@db_router.delete("/p2p-events", summary="Delete P2P events for a dataset")
def delete_p2p_events(dataset_name: str = Query("default"), db=Depends(get_db)):
    _require_db(db)
    count = db_delete_p2p_events(db, dataset_name)
    return {"dataset_name": dataset_name, "deleted": count}


# ---------------------------------------------------------------------------
# Seed demo data
# ---------------------------------------------------------------------------

@db_router.post("/seed/{domain}", summary="Seed demo data into DB for a domain")
def seed_data(domain: str, db=Depends(get_db)):
    _require_db(db)
    try:
        result = seed_domain_data(db, domain)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@db_router.post("/seed-p2p", summary="Seed demo P2P event log into DB")
def seed_p2p(dataset_name: str = Query("demo"), db=Depends(get_db)):
    _require_db(db)
    result = seed_p2p_demo(db, dataset_name)
    return result
