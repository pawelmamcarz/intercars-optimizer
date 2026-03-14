"""
Super-admin API routes — tenant onboarding & management.

Only accessible by users with role='super_admin'.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, require_role, _list_users, _create_user, hash_password

logger = logging.getLogger(__name__)

superadmin_router = APIRouter(prefix="/api/v1/superadmin", tags=["superadmin"])


# ── Models ───────────────────────────────────────────────────────────────

class CreateTenantRequest(BaseModel):
    tenant_id: str
    name: str
    plan: str = "starter"
    max_users: int = 10
    max_catalog_items: int = 500
    contact_email: str = ""
    admin_username: str = ""     # auto-create tenant admin
    admin_password: str = ""
    admin_email: str = ""


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    max_users: Optional[int] = None
    max_catalog_items: Optional[int] = None
    contact_email: Optional[str] = None
    features: Optional[str] = None


# ── Tenant CRUD ──────────────────────────────────────────────────────────

@superadmin_router.get("/tenants", summary="List all tenants")
async def list_tenants(user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_list_tenants, db_get_tenant_user_count
    tenants = db_list_tenants()
    # Enrich with user counts
    for t in tenants:
        t["user_count"] = db_get_tenant_user_count(t["tenant_id"])
    return {"tenants": tenants, "total": len(tenants)}


@superadmin_router.get("/tenants/{tenant_id}", summary="Get tenant details")
async def get_tenant(tenant_id: str, user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_get_tenant, db_get_tenant_user_count
    tenant = db_get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    tenant["user_count"] = db_get_tenant_user_count(tenant_id)
    tenant["users"] = _list_users(tenant_id=tenant_id)
    return tenant


@superadmin_router.post("/tenants", summary="Create new tenant (onboard client)")
async def create_tenant(req: CreateTenantRequest,
                        user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_get_tenant, db_create_tenant

    if db_get_tenant(req.tenant_id):
        raise HTTPException(status_code=409, detail=f"Tenant '{req.tenant_id}' already exists")

    valid_plans = ("demo", "starter", "professional", "enterprise")
    if req.plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Allowed: {', '.join(valid_plans)}")

    db_create_tenant(
        tenant_id=req.tenant_id,
        name=req.name,
        plan=req.plan,
        max_users=req.max_users,
        max_catalog_items=req.max_catalog_items,
        contact_email=req.contact_email,
    )

    result = {"success": True, "tenant_id": req.tenant_id, "name": req.name, "plan": req.plan}

    # Auto-create tenant admin if requested
    if req.admin_username and req.admin_password:
        from app.auth import _get_user_by_username
        if _get_user_by_username(req.admin_username):
            result["admin_warning"] = f"Username '{req.admin_username}' already exists, skipped"
        else:
            admin_id = _create_user(
                req.admin_username,
                hash_password(req.admin_password),
                req.admin_email or req.contact_email,
                "admin",
                None,
                tenant_id=req.tenant_id,
            )
            result["admin_user_id"] = admin_id
            result["admin_username"] = req.admin_username

    logger.info("Tenant created: %s by super_admin %s", req.tenant_id, user["username"])
    return result


@superadmin_router.put("/tenants/{tenant_id}", summary="Update tenant")
async def update_tenant(tenant_id: str, req: UpdateTenantRequest,
                        user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_get_tenant, db_update_tenant

    if not db_get_tenant(tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = db_update_tenant(tenant_id, **fields)
    return {"success": updated, "tenant_id": tenant_id, "updated_fields": list(fields.keys())}


@superadmin_router.delete("/tenants/{tenant_id}", summary="Disable tenant")
async def disable_tenant(tenant_id: str, user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_delete_tenant

    if tenant_id == "demo":
        raise HTTPException(status_code=400, detail="Cannot disable the demo tenant")

    deleted = db_delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    logger.info("Tenant disabled: %s by super_admin %s", tenant_id, user["username"])
    return {"success": True, "tenant_id": tenant_id, "status": "disabled"}


# ── Tenant users ─────────────────────────────────────────────────────────

@superadmin_router.get("/tenants/{tenant_id}/users", summary="List users for a tenant")
async def list_tenant_users(tenant_id: str, user: dict = Depends(require_role("super_admin"))):
    users = _list_users(tenant_id=tenant_id)
    return {"tenant_id": tenant_id, "users": users, "total": len(users)}


# ── Platform stats ───────────────────────────────────────────────────────

@superadmin_router.get("/stats", summary="Platform-wide statistics")
async def platform_stats(user: dict = Depends(require_role("super_admin"))):
    from app.tenant import db_list_tenants, db_get_tenant_user_count
    from app.database import _get_client

    tenants = db_list_tenants()
    client = _get_client()

    # Count totals
    total_users = 0
    for t in tenants:
        t["user_count"] = db_get_tenant_user_count(t["tenant_id"])
        total_users += t["user_count"]

    # Orders count
    try:
        rs = client.execute("SELECT COUNT(*) FROM orders")
        total_orders = rs.rows[0][0] if rs.rows else 0
    except Exception:
        total_orders = 0

    return {
        "total_tenants": len(tenants),
        "active_tenants": sum(1 for t in tenants if t["is_active"]),
        "total_users": total_users,
        "total_orders": total_orders,
        "tenants": tenants,
        "plans": {
            plan: sum(1 for t in tenants if t["plan"] == plan)
            for plan in ("demo", "starter", "professional", "enterprise")
        },
    }
