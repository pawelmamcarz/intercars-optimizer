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
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8h
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Models ────────────────────────────────────────────────────────────────

class Role(str, Enum):
    admin = "admin"
    buyer = "buyer"
    supplier = "supplier"


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    supplier_id: Optional[str] = None
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


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ── Password helpers ──────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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

def _get_user_by_username(username: str) -> dict | None:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return None
    client = _get_client()
    rows = client.execute("SELECT id, username, email, password_hash, role, supplier_id, is_active FROM users WHERE username = ?", [username])
    if not rows:
        return None
    r = rows[0]
    return {"id": r[0], "username": r[1], "email": r[2], "password_hash": r[3],
            "role": r[4], "supplier_id": r[5], "is_active": bool(r[6])}


def _get_user_by_id(user_id: int) -> dict | None:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return None
    client = _get_client()
    rows = client.execute("SELECT id, username, email, password_hash, role, supplier_id, is_active FROM users WHERE id = ?", [user_id])
    if not rows:
        return None
    r = rows[0]
    return {"id": r[0], "username": r[1], "email": r[2], "password_hash": r[3],
            "role": r[4], "supplier_id": r[5], "is_active": bool(r[6])}


def _create_user(username: str, password_hash: str, email: str | None, role: str, supplier_id: str | None) -> int:
    from app.database import _get_client
    client = _get_client()
    now = datetime.utcnow().isoformat()
    client.execute(
        "INSERT INTO users (username, email, password_hash, role, supplier_id, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        [username, email, password_hash, role, supplier_id, now],
    )
    rows = client.execute("SELECT id FROM users WHERE username = ?", [username])
    return rows[0][0] if rows else 0


def _update_password(user_id: int, new_hash: str):
    from app.database import _get_client
    client = _get_client()
    client.execute("UPDATE users SET password_hash = ? WHERE id = ?", [new_hash, user_id])


def _update_last_login(user_id: int):
    from app.database import _get_client
    client = _get_client()
    now = datetime.utcnow().isoformat()
    client.execute("UPDATE users SET last_login = ? WHERE id = ?", [now, user_id])


def _list_users() -> list[dict]:
    from app.database import DB_AVAILABLE, _get_client
    if not DB_AVAILABLE:
        return []
    client = _get_client()
    rows = client.execute("SELECT id, username, email, role, supplier_id, is_active, created_at, last_login FROM users ORDER BY id")
    return [{"id": r[0], "username": r[1], "email": r[2], "role": r[3],
             "supplier_id": r[4], "is_active": bool(r[5]), "created_at": r[6], "last_login": r[7]} for r in rows]


# ── FastAPI dependencies ──────────────────────────────────────────────────

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Extract and validate JWT token → return user dict."""
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
    """Create default admin user if none exists. Called from init_db()."""
    from app.database import DB_AVAILABLE
    if not DB_AVAILABLE:
        return
    existing = _get_user_by_username("admin")
    if existing:
        return
    _create_user("admin", hash_password("admin123"), "admin@intercars.eu", "admin", None)
    logger.info("Seeded default admin user (admin/admin123)")


# ── Endpoints ─────────────────────────────────────────────────────────────

@auth_router.post("/login", summary="Login → JWT tokens")
def login(req: LoginRequest):
    user = _get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account disabled")

    _update_last_login(user["id"])
    token_data = {"sub": str(user["id"]), "role": user["role"], "username": user["username"]}
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
async def register(req: RegisterRequest, admin: dict = Depends(require_role("admin"))):
    if _get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail=f"Username '{req.username}' already exists")
    if req.role not in ("admin", "buyer", "supplier"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user_id = _create_user(req.username, hash_password(req.password), req.email, req.role, req.supplier_id)
    return {"success": True, "user_id": user_id, "username": req.username, "role": req.role}
