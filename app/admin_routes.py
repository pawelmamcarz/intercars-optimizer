"""
Backoffice Admin endpoints — catalog management, business rules, workflow config, users.

All endpoints require 'admin' role via JWT auth.
Prefix: /admin
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.auth import require_role, _list_users, _create_user, hash_password, _get_user_by_username
from app.tenant_context import current_tenant
from app.database import (
    DB_AVAILABLE, _get_client,
    db_list_catalog, db_save_catalog_item, db_delete_catalog_item,
    db_list_rules, db_save_rule, db_delete_rule,
    db_list_workflow_steps, db_save_workflow_step, db_delete_workflow_step,
)

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["backoffice"])


def _require_db():
    if not DB_AVAILABLE:
        raise HTTPException(503, "Database not configured")


# ── Models ────────────────────────────────────────────────────────────────

class CatalogItemIn(BaseModel):
    item_id: str
    name: str
    description: Optional[str] = None
    price: float
    category: str = "parts"
    delivery_days: int = 3
    weight_kg: Optional[float] = None
    unit: str = "szt"
    requires_approval: bool = False
    unspsc_code: Optional[str] = None
    unspsc_name: Optional[str] = None
    manufacturer: Optional[str] = None
    ean: Optional[str] = None


class RuleIn(BaseModel):
    id: Optional[int] = None
    rule_type: str
    rule_key: str
    config: dict
    is_active: bool = True
    description: Optional[str] = None


class WorkflowStepIn(BaseModel):
    id: Optional[int] = None
    workflow_name: str = "order_approval"
    step_order: int
    condition_type: str
    condition_value: Optional[dict] = None
    approver_role: str
    sla_hours: int = 24


class UserCreateIn(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "buyer"
    supplier_id: Optional[str] = None


# ── UNSPSC Lookup ─────────────────────────────────────────────────────────

# Common UNSPSC codes for automotive/procurement
UNSPSC_CODES = {
    "25101500": "Brake systems and components",
    "25101700": "Suspension system components",
    "25101900": "Exhaust system and emission controls",
    "25102000": "Engine electrical system",
    "25102100": "Fuel system and components",
    "25102200": "Cooling system and components",
    "25102500": "Transmission components",
    "25171500": "Tires",
    "25171700": "Wheels and rims",
    "25172000": "Batteries for vehicles",
    "15121500": "Lubricants and oils",
    "15121900": "Greases",
    "26111700": "Batteries",
    "31161500": "Nuts and bolts",
    "31161700": "Screws",
    "31162800": "Filters",
    "31163100": "Gaskets and seals",
    "40141600": "Pumps",
    "40151500": "Valves",
    "43211500": "Computers and servers",
    "43211600": "Software licenses",
    "78101800": "Freight services",
    "78102200": "Warehousing",
    "24112400": "Packaging materials",
    "27111700": "Hand tools",
    "27112000": "Power tools",
    "31211500": "Bearings",
    "26101100": "Lighting fixtures",
    "25101600": "Steering components",
}


@admin_router.get("/unspsc/search", summary="Search UNSPSC codes")
async def search_unspsc(
    q: str = Query("", description="Search text"),
    _admin: dict = Depends(require_role("admin")),
):
    results = []
    q_lower = q.lower()
    for code, name in UNSPSC_CODES.items():
        if q_lower in code or q_lower in name.lower():
            results.append({"code": code, "name": name})
    return {"results": results, "count": len(results)}


# ── DUNS / D&B Integration ────────────────────────────────────────────────

@admin_router.get("/duns/lookup", summary="Lookup DUNS number by NIP")
async def duns_lookup(
    nip: str = Query(..., description="Polish NIP (10 digits)"),
    _admin: dict = Depends(require_role("admin", "buyer")),
):
    """
    Lookup DUNS number from Dun & Bradstreet by NIP.
    In production, this would call D&B Direct+ API.
    Currently returns a simulated response for demo.
    """
    nip_clean = nip.replace("-", "").replace(" ", "").strip()
    if len(nip_clean) != 10 or not nip_clean.isdigit():
        raise HTTPException(400, "NIP must be 10 digits")

    # Demo mode — simulate D&B response
    # In production: call https://plus.dnb.com/v1/match/cleanseMatch
    # with Authorization: Bearer {D&B_API_KEY}
    import hashlib
    duns_hash = int(hashlib.md5(nip_clean.encode()).hexdigest()[:9], 16) % 999999999
    duns_number = f"{duns_hash:09d}"

    return {
        "success": True,
        "nip": nip_clean,
        "duns_number": duns_number,
        "company_name": f"Firma NIP-{nip_clean[:4]}...{nip_clean[-2:]}",
        "country": "PL",
        "confidence_score": 0.92,
        "source": "demo",
        "note": "Production: integrate with D&B Direct+ API (https://directplus.documentation.dnb.com/)"
    }


# ── Catalog CRUD ──────────────────────────────────────────────────────────

@admin_router.get("/catalog", summary="List catalog items")
async def list_catalog(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    items = db_list_catalog(client, category, search, active_only=not include_inactive,
                             tenant_id=current_tenant())
    return {"items": items, "count": len(items)}


@admin_router.post("/catalog", summary="Create/update catalog item")
async def save_catalog_item(
    item: CatalogItemIn,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    item_id = db_save_catalog_item(client, item.model_dump(), tenant_id=current_tenant())
    return {"success": True, "item_id": item_id}


@admin_router.delete("/catalog/{item_id}", summary="Soft-delete catalog item")
async def delete_catalog_item(
    item_id: str,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    count = db_delete_catalog_item(client, item_id, tenant_id=current_tenant())
    if count == 0:
        raise HTTPException(404, f"Item '{item_id}' not found")
    return {"success": True, "item_id": item_id}


@admin_router.post("/catalog/import", summary="Import catalog from CSV (CIF format)")
async def import_catalog_cif(
    file: UploadFile = File(...),
    _admin: dict = Depends(require_role("admin")),
):
    """
    Import catalog items from CSV file in CIF-like format.
    Expected columns: item_id, name, description, price, category,
    delivery_days, unit, unspsc_code, manufacturer, ean
    """
    _require_db()
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames:
        # Try comma
        reader = csv.DictReader(io.StringIO(text), delimiter=",")

    client = _get_client()
    imported = 0
    errors = []
    for i, row in enumerate(reader, 1):
        try:
            # Normalize field names (case-insensitive, strip)
            r = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}
            item = {
                "item_id": r.get("item_id") or r.get("id") or r.get("sku") or f"IMP-{i:04d}",
                "name": r.get("name") or r.get("nazwa") or r.get("product_name") or "",
                "description": r.get("description") or r.get("opis") or "",
                "price": float(r.get("price") or r.get("cena") or r.get("unit_price") or 0),
                "category": r.get("category") or r.get("kategoria") or "parts",
                "delivery_days": int(r.get("delivery_days") or r.get("lead_time") or 3),
                "unit": r.get("unit") or r.get("jm") or "szt",
                "weight_kg": float(r.get("weight_kg") or r.get("waga") or 0) or None,
                "requires_approval": r.get("requires_approval", "").lower() in ("1", "true", "tak"),
                "unspsc_code": r.get("unspsc_code") or r.get("unspsc") or "",
                "unspsc_name": r.get("unspsc_name") or UNSPSC_CODES.get(r.get("unspsc_code", ""), ""),
                "manufacturer": r.get("manufacturer") or r.get("producent") or "",
                "ean": r.get("ean") or r.get("gtin") or r.get("barcode") or "",
                "is_active": True,
            }
            if not item["name"]:
                errors.append(f"Row {i}: missing name")
                continue
            db_save_catalog_item(client, item, tenant_id=current_tenant())
            imported += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return {
        "success": True,
        "imported": imported,
        "errors": errors[:20],
        "filename": file.filename,
    }


# ── Business Rules CRUD ──────────────────────────────────────────────────

@admin_router.get("/rules", summary="List business rules")
async def list_rules(
    rule_type: Optional[str] = Query(None),
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    rules = db_list_rules(client, rule_type, tenant_id=current_tenant())
    return {"rules": rules, "count": len(rules)}


@admin_router.post("/rules", summary="Create/update business rule")
async def save_rule(
    rule: RuleIn,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    rule_id = db_save_rule(client, rule.model_dump(), tenant_id=current_tenant())
    return {"success": True, "rule_id": rule_id}


@admin_router.delete("/rules/{rule_id}", summary="Deactivate business rule")
async def delete_rule(
    rule_id: int,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    count = db_delete_rule(client, rule_id, tenant_id=current_tenant())
    if count == 0:
        raise HTTPException(404, f"Rule {rule_id} not found")
    return {"success": True, "rule_id": rule_id}


# ── Workflow Steps CRUD ───────────────────────────────────────────────────

@admin_router.get("/workflows", summary="List workflow steps")
async def list_workflows(
    workflow_name: str = Query("order_approval"),
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    steps = db_list_workflow_steps(client, workflow_name, tenant_id=current_tenant())
    return {"steps": steps, "count": len(steps)}


@admin_router.post("/workflows", summary="Create/update workflow step")
async def save_workflow_step(
    step: WorkflowStepIn,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    step_id = db_save_workflow_step(client, step.model_dump(), tenant_id=current_tenant())
    return {"success": True, "step_id": step_id}


@admin_router.delete("/workflows/{step_id}", summary="Remove workflow step")
async def delete_workflow_step(
    step_id: int,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    client = _get_client()
    count = db_delete_workflow_step(client, step_id, tenant_id=current_tenant())
    if count == 0:
        raise HTTPException(404, f"Step {step_id} not found")
    return {"success": True, "step_id": step_id}


# ── User Management ──────────────────────────────────────────────────────

@admin_router.get("/users", summary="List users")
async def list_users(_admin: dict = Depends(require_role("admin"))):
    _require_db()
    users = _list_users(tenant_id=current_tenant())
    return {"users": users, "count": len(users)}


@admin_router.post("/users", summary="Create user")
async def create_user(
    req: UserCreateIn,
    _admin: dict = Depends(require_role("admin")),
):
    _require_db()
    if _get_user_by_username(req.username):
        raise HTTPException(409, f"Username '{req.username}' already exists")
    if req.role not in ("admin", "buyer", "supplier"):
        raise HTTPException(400, "Invalid role. Must be: admin, buyer, supplier")
    user_id = _create_user(req.username, hash_password(req.password), req.email,
                             req.role, req.supplier_id, tenant_id=current_tenant())
    return {"success": True, "user_id": user_id, "username": req.username, "role": req.role}


# ── Admin Dashboard KPI ──────────────────────────────────────────────────

@admin_router.get("/dashboard", summary="Admin dashboard KPI")
async def admin_dashboard(_admin: dict = Depends(require_role("admin"))):
    _require_db()
    client = _get_client()

    tenant = current_tenant()
    users = _list_users(tenant_id=tenant)
    catalog = db_list_catalog(client, tenant_id=tenant)
    rules = db_list_rules(client, tenant_id=tenant)
    steps = db_list_workflow_steps(client, tenant_id=tenant)

    return {
        "users_total": len(users),
        "users_by_role": _count_by(users, "role"),
        "catalog_items": len(catalog),
        "catalog_by_category": _count_by(catalog, "category"),
        "active_rules": len(rules),
        "rules_by_type": _count_by(rules, "rule_type"),
        "workflow_steps": len(steps),
    }


def _count_by(items: list[dict], key: str) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        val = str(item.get(key, "unknown"))
        counts[val] = counts.get(val, 0) + 1
    return counts
