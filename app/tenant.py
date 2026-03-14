"""
Multi-tenant support — Iteration 1.

Provides:
- Tenant dataclass with metadata
- FastAPI dependency: get_tenant_context() — resolves tenant from JWT
- DB helpers: create_tenant, get_tenant, list_tenants, update_tenant
- Seed function for "demo" tenant
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

DEMO_TENANT_ID = "demo"


# ── Tenant context (injected into routes) ────────────────────────────────

@dataclass
class TenantContext:
    """Resolved tenant for the current request."""
    tenant_id: str
    tenant_name: str
    plan: str = "demo"           # demo | starter | professional | enterprise
    is_active: bool = True
    max_users: int = 10
    max_catalog_items: int = 500
    features: str = "{}"         # JSON string with feature flags


# ── DB helpers ───────────────────────────────────────────────────────────

def db_create_tenant(tenant_id: str, name: str, plan: str = "demo",
                     max_users: int = 10, max_catalog_items: int = 500,
                     contact_email: str = "", features: str = "{}") -> str:
    """Insert a new tenant. Returns tenant_id."""
    from app.database import _get_client
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()
    client.execute(
        """INSERT INTO tenants (tenant_id, name, plan, is_active, max_users,
           max_catalog_items, contact_email, features, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
        [tenant_id, name, plan, max_users, max_catalog_items,
         contact_email, features, now, now],
    )
    logger.info("Created tenant: %s (%s) plan=%s", tenant_id, name, plan)
    return tenant_id


def db_get_tenant(tenant_id: str) -> Optional[dict]:
    """Fetch a single tenant by ID."""
    from app.database import _get_client
    client = _get_client()
    rs = client.execute(
        "SELECT tenant_id, name, plan, is_active, max_users, max_catalog_items, "
        "contact_email, features, created_at, updated_at "
        "FROM tenants WHERE tenant_id = ?",
        [tenant_id],
    )
    if not rs.rows:
        return None
    r = rs.rows[0]
    return {
        "tenant_id": r[0], "name": r[1], "plan": r[2],
        "is_active": bool(r[3]), "max_users": r[4],
        "max_catalog_items": r[5], "contact_email": r[6],
        "features": r[7], "created_at": r[8], "updated_at": r[9],
    }


def db_list_tenants(active_only: bool = False) -> list[dict]:
    """List all tenants."""
    from app.database import _get_client
    client = _get_client()
    sql = ("SELECT tenant_id, name, plan, is_active, max_users, max_catalog_items, "
           "contact_email, features, created_at, updated_at FROM tenants")
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY created_at"
    rs = client.execute(sql)
    return [{
        "tenant_id": r[0], "name": r[1], "plan": r[2],
        "is_active": bool(r[3]), "max_users": r[4],
        "max_catalog_items": r[5], "contact_email": r[6],
        "features": r[7], "created_at": r[8], "updated_at": r[9],
    } for r in rs.rows]


def db_update_tenant(tenant_id: str, **fields) -> bool:
    """Update tenant fields. Returns True if updated."""
    from app.database import _get_client
    client = _get_client()
    allowed = {"name", "plan", "is_active", "max_users", "max_catalog_items",
               "contact_email", "features"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [tenant_id]
    rs = client.execute(f"UPDATE tenants SET {set_clause} WHERE tenant_id = ?", vals)
    return rs.rows_affected > 0


def db_delete_tenant(tenant_id: str) -> bool:
    """Soft-delete tenant (set is_active=0). Never deletes demo."""
    if tenant_id == DEMO_TENANT_ID:
        return False
    return db_update_tenant(tenant_id, is_active=0)


def db_get_tenant_user_count(tenant_id: str) -> int:
    """Count users for a tenant."""
    from app.database import _get_client
    client = _get_client()
    rs = client.execute(
        "SELECT COUNT(*) FROM users WHERE tenant_id = ? AND is_active = 1",
        [tenant_id],
    )
    return rs.rows[0][0] if rs.rows else 0


# ── Seed demo tenant ────────────────────────────────────────────────────

def seed_demo_tenant():
    """Create the demo tenant if it doesn't exist. Called at startup."""
    existing = db_get_tenant(DEMO_TENANT_ID)
    if existing:
        return
    db_create_tenant(
        tenant_id=DEMO_TENANT_ID,
        name="Flow Procurement Demo",
        plan="demo",
        max_users=50,
        max_catalog_items=1000,
        contact_email="demo@flowproc.eu",
        features='{"all": true}',
    )
    logger.info("Seeded demo tenant")


# ── FastAPI dependency ───────────────────────────────────────────────────

async def get_tenant_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TenantContext:
    """
    Resolve tenant from JWT token.

    Backward-compatible: if token has no tenant_id claim → defaults to "demo".
    If no token at all → defaults to "demo" (public/anonymous access).
    """
    tenant_id = DEMO_TENANT_ID  # default

    if credentials is not None:
        try:
            from jose import jwt as _jwt
            payload = _jwt.decode(
                credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
            )
            tenant_id = payload.get("tenant_id", DEMO_TENANT_ID)
        except Exception:
            # Invalid token → still allow demo access
            pass

    tenant = db_get_tenant(tenant_id)
    if not tenant:
        # Fallback to demo if tenant doesn't exist
        if tenant_id != DEMO_TENANT_ID:
            logger.warning("Tenant %s not found, falling back to demo", tenant_id)
            tenant = db_get_tenant(DEMO_TENANT_ID)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Demo tenant not configured",
            )

    if not tenant["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant '{tenant_id}' is disabled",
        )

    return TenantContext(
        tenant_id=tenant["tenant_id"],
        tenant_name=tenant["name"],
        plan=tenant["plan"],
        is_active=tenant["is_active"],
        max_users=tenant["max_users"],
        max_catalog_items=tenant["max_catalog_items"],
        features=tenant["features"],
    )
