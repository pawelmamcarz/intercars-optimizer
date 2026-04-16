"""
tenant_context.py — request-scoped tenant resolution.

Every DB table already carries `tenant_id`. What was missing was a
uniform way to pull the current tenant out of the JWT (or an
`X-Tenant-ID` header for service-to-service calls) and make it
available to engines like `contract_engine.list_contracts` without
threading the parameter through every function signature.

Usage in a route handler:
    from app.tenant_context import current_tenant
    items = list_contracts()   # already tenant-scoped

Usage in an engine call that needs the value explicitly:
    tenant = current_tenant()   # returns 'demo' in the default path

The default tenant is 'demo' so existing unauthenticated endpoints
keep working — nothing silently breaks.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Optional

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

log = logging.getLogger(__name__)

_DEFAULT_TENANT = "demo"

# Stored on a ContextVar so that each request sees its own value even
# when FastAPI fans out to multiple workers / tasks.
_current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar(
    "flow_current_tenant", default=_DEFAULT_TENANT,
)


def current_tenant() -> str:
    """Return the tenant_id resolved for the active request. Safe to call
    from any sync or async code running inside the request scope."""
    return _current_tenant.get()


def set_tenant(tenant_id: str) -> contextvars.Token:
    """Explicitly override the tenant — returns a Token you can pass to
    reset() if you need to revert (e.g. in tests)."""
    return _current_tenant.set(tenant_id or _DEFAULT_TENANT)


def reset_tenant(token: contextvars.Token) -> None:
    _current_tenant.reset(token)


def _decode_tenant_from_bearer(auth_header: str) -> Optional[str]:
    """Extract tenant_id from an 'Authorization: Bearer <jwt>' header.
    Swallows any decode errors — the request will fall back to the
    header or the default tenant."""
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(None, 1)[1].strip()
    if not token:
        return None
    try:
        secret = settings.jwt_secret
        if not secret:
            return None
        payload = jwt.decode(token, secret, algorithms=["HS256"],
                             options={"verify_exp": False})
        tenant = payload.get("tenant_id") or payload.get("tenant")
        return tenant or None
    except JWTError as exc:
        log.debug("tenant decode failed: %s", exc)
        return None


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Resolve tenant_id per request and stash it in a ContextVar.

    Resolution order:
      1. Explicit X-Tenant-ID header (service-to-service calls)
      2. tenant_id claim inside the JWT bearer token
      3. Fallback: '_DEFAULT_TENANT' ('demo')
    """
    async def dispatch(self, request: Request, call_next):
        tenant = (
            request.headers.get("x-tenant-id")
            or _decode_tenant_from_bearer(request.headers.get("authorization", ""))
            or _DEFAULT_TENANT
        )
        token = _current_tenant.set(tenant)
        # Also surface on request.state for handlers that prefer explicit
        # access over the ContextVar.
        request.state.tenant_id = tenant
        try:
            return await call_next(request)
        finally:
            _current_tenant.reset(token)
