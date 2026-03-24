"""
JWT Authentication & Authorization module.

Provides:
- Password hashing (bcrypt via passlib)
- JWT token generation / validation (python-jose)
- FastAPI dependencies: get_current_user, require_role
- Auth endpoints: login, register, me, change-password
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8h
REFRESH_TOKEN_EXPIRE_DAYS = 30
security = HTTPBearer(auto_error=False)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Models ────────────────────────────────────────────────────────────────

class Role(str, Enum):
    super_admin = "super_admin"  # platform-level admin (manages tenants)
    admin = "admin"              # tenant-level admin
    buyer = "buyer"
    supplier = "supplier"


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    supplier_id: Optional[str] = None
    tenant_id: str = "demo"
    is_active: bool = True


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "buyer"
    supplier_id: Optional[str] = None
    tenant_id: Optional[str] = None  # None → inherit from admin's tenant


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ── Password helpers ──────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Token helpers ─────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


# ── DB helpers (use Turso via database.py) ────────────────────────────────

def _get_user_by_username(username: str, tenant_id: str | None = None) -> dict | None:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return None
    client = _get_client()
    if tenant_id:
        rs = client.execute(
            "SELECT id, username, email, password_hash, role, supplier_id, is_active, tenant_id "
            "FROM users WHERE username = ? AND tenant_id = ?", [username, tenant_id])
    else:
        rs = client.execute(
            "SELECT id, username, email, password_hash, role, supplier_id, is_active, tenant_id "
            "FROM users WHERE username = ?", [username])
    if not rs.rows:
        return None
    r = rs.rows[0]
    return {"id": r[0], "username": r[1], "email": r[2], "password_hash": r[3],
            "role": r[4], "supplier_id": r[5], "is_active": bool(r[6]),
            "tenant_id": r[7] if len(r) > 7 else "demo"}


def _get_user_by_id(user_id: int) -> dict | None:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return None
    client = _get_client()
    rs = client.execute(
        "SELECT id, username, email, password_hash, role, supplier_id, is_active, tenant_id "
        "FROM users WHERE id = ?", [user_id])
    if not rs.rows:
        return None
    r = rs.rows[0]
    return {"id": r[0], "username": r[1], "email": r[2], "password_hash": r[3],
            "role": r[4], "supplier_id": r[5], "is_active": bool(r[6]),
            "tenant_id": r[7] if len(r) > 7 else "demo"}


def _create_user(username: str, password_hash: str, email: str | None,
                  role: str, supplier_id: str | None,
                  tenant_id: str = "demo") -> int:
    from app.database import _get_client
    client = _get_client()
    now = datetime.utcnow().isoformat()
    client.execute(
        "INSERT INTO users (username, email, password_hash, role, supplier_id, is_active, tenant_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        [username, email, password_hash, role, supplier_id, tenant_id, now],
    )
    rs = client.execute("SELECT id FROM users WHERE username = ?", [username])
    return rs.rows[0][0] if rs.rows else 0


def _update_password(user_id: int, new_hash: str):
    from app.database import _get_client
    client = _get_client()
    client.execute("UPDATE users SET password_hash = ? WHERE id = ?", [new_hash, user_id])


def _update_last_login(user_id: int):
    from app.database import _get_client
    client = _get_client()
    now = datetime.utcnow().isoformat()
    client.execute("UPDATE users SET last_login = ? WHERE id = ?", [now, user_id])


def _list_users(tenant_id: str | None = None) -> list[dict]:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return []
    client = _get_client()
    if tenant_id:
        rs = client.execute(
            "SELECT id, username, email, role, supplier_id, is_active, created_at, last_login, tenant_id "
            "FROM users WHERE tenant_id = ? ORDER BY id", [tenant_id])
    else:
        rs = client.execute(
            "SELECT id, username, email, role, supplier_id, is_active, created_at, last_login, tenant_id "
            "FROM users ORDER BY id")
    return [{"id": r[0], "username": r[1], "email": r[2], "role": r[3],
             "supplier_id": r[4], "is_active": bool(r[5]), "created_at": r[6],
             "last_login": r[7], "tenant_id": r[8] if len(r) > 8 else "demo"} for r in rs.rows]


# ── FastAPI dependencies ──────────────────────────────────────────────────

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Extract and validate JWT token → return user dict (includes tenant_id)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = _get_user_by_id(int(user_id))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Ensure tenant_id from token is in user dict (backward compat)
    if "tenant_id" not in user or not user["tenant_id"]:
        user["tenant_id"] = payload.get("tenant_id", "demo")
    return user


def require_role(*roles: str):
    """Dependency factory — checks that current user has one of the given roles."""
    async def _check(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{user['role']}' not allowed. Required: {', '.join(roles)}")
        return user
    return _check


# ── Seed default admin ────────────────────────────────────────────────────

def seed_admin():
    """Create default users if none exist. Called from lifespan startup."""
    from app.database import DB_AVAILABLE
    if not DB_AVAILABLE:
        return

    # Seed demo tenant first
    from app.tenant import seed_demo_tenant
    seed_demo_tenant()

    # Super-admin (platform-level, not tied to any specific tenant)
    if not _get_user_by_username("superadmin"):
        _create_user("superadmin", hash_password("super123!"), "superadmin@flowproc.eu",
                      "super_admin", None, tenant_id="demo")
        logger.info("Seeded super_admin user (superadmin/super123!)")

    # Demo tenant admin
    if not _get_user_by_username("admin"):
        _create_user("admin", hash_password("admin123"), "admin@flowproc.eu",
                      "admin", None, tenant_id="demo")
        logger.info("Seeded default admin user (admin/admin123)")
    # Buyer
    if not _get_user_by_username("buyer"):
        _create_user("buyer", hash_password("buyer123"), "buyer@flowproc.eu",
                      "buyer", None, tenant_id="demo")
        logger.info("Seeded default buyer user (buyer/buyer123)")
    # Suppliers
    demo_suppliers = [
        ("trw", "trw123", "trw@trw.com", "TRW-001"),
        ("brembo", "brembo123", "brembo@brembo.com", "BREMBO-001"),
        ("bosch", "bosch123", "bosch@bosch.com", "BOSCH-001"),
        ("kraft", "kraft123", "kraft@kraftpol.pl", "KRAFT-001"),
    ]
    for uname, pwd, email, sid in demo_suppliers:
        if not _get_user_by_username(uname):
            _create_user(uname, hash_password(pwd), email, "supplier", sid, tenant_id="demo")
            logger.info("Seeded supplier user (%s/%s → %s)", uname, pwd, sid)


# ── Rate limiting ─────────────────────────────────────────────────────────

_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_RATE_LIMIT = 10  # max attempts per window
_LOGIN_RATE_WINDOW = 300  # 5 minutes


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if too many login attempts from this IP."""
    now = time.time()
    attempts = _login_attempts[client_ip]
    # Prune old attempts
    _login_attempts[client_ip] = [t for t in attempts if now - t < _LOGIN_RATE_WINDOW]
    if len(_login_attempts[client_ip]) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {_LOGIN_RATE_WINDOW // 60} minutes.",
        )
    _login_attempts[client_ip].append(now)
    # Bound cache size — evict stale IPs
    if len(_login_attempts) > 10000:
        cutoff = now - _LOGIN_RATE_WINDOW
        stale = [ip for ip, ts in _login_attempts.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del _login_attempts[ip]


# ── Endpoints ─────────────────────────────────────────────────────────────

@auth_router.post("/login", summary="Login → JWT tokens")
def login(req: LoginRequest, request: Request):
    _check_rate_limit(request.client.host if request.client else "unknown")
    user = _get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account disabled")

    _update_last_login(user["id"])
    token_data = {
        "sub": str(user["id"]),
        "role": user["role"],
        "username": user["username"],
        "tenant_id": user.get("tenant_id", "demo"),
    }
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "user": {k: v for k, v in user.items() if k != "password_hash"},
    }


@auth_router.get("/me", summary="Current user profile")
async def me(user: dict = Depends(get_current_user)):
    return {k: v for k, v in user.items() if k != "password_hash"}


@auth_router.post("/change-password", summary="Change password")
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    if not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Old password incorrect")
    _update_password(user["id"], hash_password(req.new_password))
    return {"success": True, "message": "Password changed"}


@auth_router.post("/register", summary="Register new user (admin only)")
async def register(req: RegisterRequest, admin: dict = Depends(require_role("admin", "super_admin"))):
    # Determine tenant: super_admin can specify any, admin inherits own
    target_tenant = req.tenant_id or admin.get("tenant_id", "demo")
    if admin["role"] != "super_admin" and target_tenant != admin.get("tenant_id", "demo"):
        raise HTTPException(status_code=403, detail="Cannot create users in another tenant")

    if _get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail=f"Username '{req.username}' already exists")
    valid_roles = ("admin", "buyer", "supplier")
    if admin["role"] == "super_admin":
        valid_roles = ("super_admin", "admin", "buyer", "supplier")
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {', '.join(valid_roles)}")
    user_id = _create_user(req.username, hash_password(req.password), req.email,
                           req.role, req.supplier_id, tenant_id=target_tenant)
    return {"success": True, "user_id": user_id, "username": req.username,
            "role": req.role, "tenant_id": target_tenant}
