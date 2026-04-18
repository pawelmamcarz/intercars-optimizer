"""
Tenant isolation regression tests.

Confirm that:
1. Anonymous requests to tenant-scoped endpoints get 401.
2. Authenticated requests succeed and only see the caller's tenant.
3. Two different tenants don't see each other's orders.

The fixtures rely on `seed_admin()` running in the FastAPI lifespan
(which creates the demo users buyer / admin / trw etc.).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

API = "/api/v1"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        pytest.skip(f"Login {username} unavailable: {r.status_code} {r.text[:120]}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def buyer_headers(client: TestClient) -> dict:
    token = _login(client, "buyer", "buyer123")
    return {"Authorization": f"Bearer {token}"}


# ────────────────────────────────────────────────────────────────────
# 1. Anonymous access is denied for tenant-scoped endpoints
# ────────────────────────────────────────────────────────────────────

class TestAnonymousDenied:
    """Endpoints touching per-tenant data must reject missing token with 401."""

    @pytest.mark.parametrize("path", [
        "/buying/orders",
        "/buying/kpi",
        "/buying/contracts",
        "/buying/spend-analytics",
        "/buying/suppliers/scorecard",
    ])
    def test_get_requires_auth(self, client: TestClient, path: str):
        r = client.get(f"{API}{path}")
        assert r.status_code == 401, f"{path} should be 401 without token, got {r.status_code}"
        body = r.json()
        # Faza 1.4: error responses include a request_id for debugging
        assert "request_id" in body


# ────────────────────────────────────────────────────────────────────
# 2. Authenticated request returns 200 and JSON body
# ────────────────────────────────────────────────────────────────────

class TestAuthenticatedAccess:
    def test_orders_with_token_200(self, client: TestClient, buyer_headers):
        r = client.get(f"{API}/buying/orders", headers=buyer_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "orders" in data

    def test_kpi_with_token_200(self, client: TestClient, buyer_headers):
        r = client.get(f"{API}/buying/kpi", headers=buyer_headers)
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True

    def test_contracts_with_token_200(self, client: TestClient, buyer_headers):
        r = client.get(f"{API}/buying/contracts", headers=buyer_headers)
        assert r.status_code == 200
        assert "contracts" in r.json()


# ────────────────────────────────────────────────────────────────────
# 3. X-Tenant-ID header isolates traffic
# ────────────────────────────────────────────────────────────────────

class TestTenantHeaderIsolation:
    """Send the same authenticated request with a different X-Tenant-ID
    override and confirm the orders list does NOT include data from the
    default 'demo' tenant. We can't fully simulate two real tenants without
    bootstrapping a second tenant + user, so this checks the middleware
    actually scopes the SQL filter (tenant 'isolation_test_xyz' is brand-new
    and has zero orders)."""

    def test_other_tenant_sees_no_demo_orders(self, client: TestClient, buyer_headers):
        headers = {**buyer_headers, "X-Tenant-ID": "isolation_test_xyz"}
        r = client.get(f"{API}/buying/orders", headers=headers)
        assert r.status_code == 200
        # Brand-new tenant has empty orders list — proves the filter works.
        assert r.json()["orders"] == []


# ────────────────────────────────────────────────────────────────────
# 4. Admin users list is tenant-scoped too
# ────────────────────────────────────────────────────────────────────

class TestAdminUsersTenantScope:
    """B2 regression: /admin/users and POST /admin/users used to ignore
    tenant_id — admin in tenant A could see (and create) users in tenant B.
    Now both read current_tenant() from the request context."""

    @pytest.fixture(scope="class")
    def admin_headers(self, client: TestClient) -> dict:
        r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        if r.status_code != 200:
            pytest.skip(f"Demo admin login unavailable: {r.status_code}")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_admin_users_list_scoped_by_x_tenant_header(self, client: TestClient, admin_headers):
        headers = {**admin_headers, "X-Tenant-ID": "isolation_admin_users_xyz"}
        r = client.get("/admin/users", headers=headers)
        assert r.status_code == 200, r.text
        # Fresh tenant has no users — if isolation is broken we'd see the
        # seeded demo users here.
        assert r.json()["users"] == []
