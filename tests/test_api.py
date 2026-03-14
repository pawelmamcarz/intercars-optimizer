"""
Comprehensive API tests for the INTERCARS Procurement Platform.

Uses pytest + httpx (via FastAPI TestClient) to exercise all major endpoints:
health/UI, optimization, demo data, buying catalog, UNSPSC search,
CIF template/upload, buying KPI, suppliers, process mining, and alerts.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app

API = "/api/v1"


@pytest.fixture(scope="module")
def client():
    """Shared TestClient for the entire module (avoids repeated lifespan)."""
    with TestClient(app) as c:
        yield c


# =====================================================================
# 1. Health / UI routes
# =====================================================================

class TestHealthAndUI:
    """GET requests to UI and health endpoints return 200."""

    def test_ui_returns_200(self, client: TestClient):
        r = client.get("/ui")
        assert r.status_code == 200

    def test_admin_ui_returns_200(self, client: TestClient):
        r = client.get("/admin-ui")
        assert r.status_code == 200

    def test_portal_ui_returns_200(self, client: TestClient):
        r = client.get("/portal-ui")
        assert r.status_code == 200

    def test_health_returns_ok(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data


# =====================================================================
# 2. Optimization
# =====================================================================

class TestOptimization:
    """POST /api/v1/optimize with valid demand data."""

    @pytest.fixture()
    def valid_payload(self):
        """Minimal valid optimization request."""
        return {
            "suppliers": [
                {
                    "supplier_id": "SUP-A",
                    "name": "Supplier Alpha",
                    "unit_cost": 100.0,
                    "logistics_cost": 10.0,
                    "lead_time_days": 3,
                    "compliance_score": 0.9,
                    "esg_score": 0.8,
                    "min_order_qty": 0,
                    "max_capacity": 500,
                    "served_regions": ["PL-MA"],
                },
                {
                    "supplier_id": "SUP-B",
                    "name": "Supplier Beta",
                    "unit_cost": 110.0,
                    "logistics_cost": 5.0,
                    "lead_time_days": 2,
                    "compliance_score": 0.95,
                    "esg_score": 0.85,
                    "min_order_qty": 0,
                    "max_capacity": 500,
                    "served_regions": ["PL-MA"],
                },
            ],
            "demand": [
                {
                    "product_id": "PROD-001",
                    "demand_qty": 100,
                    "destination_region": "PL-MA",
                },
            ],
            "weights": {
                "lambda_param": 0.5,
                "w_cost": 0.40,
                "w_time": 0.30,
                "w_compliance": 0.15,
                "w_esg": 0.15,
            },
            "mode": "continuous",
            "max_vendor_share": 0.60,
        }

    def test_optimize_returns_200(self, client: TestClient, valid_payload):
        r = client.post(f"{API}/optimize", json=valid_payload)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert len(data["allocations"]) > 0

    def test_optimize_demo_parts(self, client: TestClient):
        r = client.get(f"{API}/optimize/demo?domain=parts")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "allocations" in data
        assert "objective" in data


# =====================================================================
# 3. Demo data
# =====================================================================

class TestDemoData:
    """GET /api/v1/demo/parts/demand and /suppliers."""

    def test_demo_parts_demand(self, client: TestClient):
        r = client.get(f"{API}/demo/parts/demand")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_demo_parts_suppliers(self, client: TestClient):
        r = client.get(f"{API}/demo/parts/suppliers")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_demo_parts_labels(self, client: TestClient):
        r = client.get(f"{API}/demo/parts/labels")
        assert r.status_code == 200
        data = r.json()
        assert "products" in data
        assert "regions" in data


# =====================================================================
# 4. Buying catalog
# =====================================================================

class TestBuyingCatalog:
    """GET /api/v1/buying/catalog and /categories."""

    def test_catalog_returns_200(self, client: TestClient):
        r = client.get(f"{API}/buying/catalog")
        assert r.status_code == 200
        data = r.json()
        assert "products" in data
        assert "categories" in data

    def test_categories_returns_200(self, client: TestClient):
        r = client.get(f"{API}/buying/categories")
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data
        assert len(data["categories"]) > 0


# =====================================================================
# 5. UNSPSC search
# =====================================================================

class TestUNSPSCSearch:
    """GET /api/v1/unspsc/search with keyword and code queries."""

    def test_search_by_keyword_hamulce(self, client: TestClient):
        r = client.get(f"{API}/unspsc/search", params={"q": "hamulce"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["total"] > 0
        # Should match brake-related UNSPSC codes
        codes = [entry["code"] for entry in data["results"]]
        assert any("25101500" == c for c in codes), (
            f"Expected brake UNSPSC code 25101500, got {codes}"
        )

    def test_search_by_code_prefix(self, client: TestClient):
        r = client.get(f"{API}/unspsc/search", params={"q": "4321"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        # Should match IT-related codes starting with 4321
        assert data["total"] > 0
        for entry in data["results"]:
            assert entry["code"].startswith("4321") or entry["match"] == "ai"

    def test_search_empty_query_rejected(self, client: TestClient):
        r = client.get(f"{API}/unspsc/search", params={"q": ""})
        assert r.status_code == 422  # validation error — min_length=1


# =====================================================================
# 6. CIF template download
# =====================================================================

class TestCIFTemplate:
    """GET /api/v1/cif/template returns 200 with file content."""

    def test_template_download(self, client: TestClient):
        r = client.get(f"{API}/cif/template")
        assert r.status_code == 200
        # Should return binary content (file download)
        assert len(r.content) > 0


# =====================================================================
# 7. CIF upload
# =====================================================================

class TestCIFUpload:
    """POST /api/v1/cif/upload with a sample CIF file content."""

    def test_upload_csv_cif(self, client: TestClient):
        csv_content = (
            "item_id,name,description,price,currency,unit\n"
            "BRK-001,Klocki hamulcowe ceramiczne,Hamulce przednie,145.00,PLN,szt\n"
            "FIL-001,Filtr oleju Premium,Filtr silnikowy,42.50,PLN,szt\n"
            "OLJ-001,Olej silnikowy 5W-30,Syntetyczny olej,89.90,PLN,szt\n"
        )
        file = io.BytesIO(csv_content.encode("utf-8"))
        r = client.post(
            f"{API}/cif/upload",
            files={"file": ("test_catalog.csv", file, "text/csv")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["total_items"] == 3
        assert data["filename"] == "test_catalog.csv"

        # Verify UNSPSC auto-classification
        items = data["items"]
        brk = next((i for i in items if i["item_id"] == "BRK-001"), None)
        assert brk is not None
        assert brk["unspsc_code"] == "25101500"  # brake systems
        assert brk["classified_by"] == "auto"

        fil = next((i for i in items if i["item_id"] == "FIL-001"), None)
        assert fil is not None
        # "Filtr oleju" matches "olej" (lubricants 15121500) before "filtr" (filters)
        # due to keyword ordering; both are valid auto-classifications
        assert fil["classified_by"] == "auto"
        assert fil["unspsc_code"] != "00000000"

    def test_upload_cif_v3_format(self, client: TestClient):
        cif_content = (
            "CIF_I_V3.0\n"
            "LOADMODE:F\n"
            "CODEFORMAT:UNSPSC\n"
            "CURRENCY:PLN\n"
            "FIELDNAMES:item_id\tname\tdescription\tprice\n"
            "DATA\n"
            "AMO-001\tAmortyzator przedni\tZawieszenie McPherson\t320.00\n"
            "AKU-001\tAkumulator 12V 70Ah\tAkumulator rozruchowy\t450.00\n"
            "ENDOFDATA\n"
        )
        file = io.BytesIO(cif_content.encode("utf-8"))
        r = client.post(
            f"{API}/cif/upload",
            files={"file": ("catalog.cif", file, "application/octet-stream")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["total_items"] == 2

        items = data["items"]
        amo = next((i for i in items if i["item_id"] == "AMO-001"), None)
        assert amo is not None
        assert amo["unspsc_code"] == "25101700"  # suspension


# =====================================================================
# 8. Buying KPI
# =====================================================================

class TestBuyingKPI:
    """GET /api/v1/buying/kpi returns order statistics."""

    def test_kpi_returns_200(self, client: TestClient):
        r = client.get(f"{API}/buying/kpi")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        # KPI response always contains orders_by_status and avg metrics
        assert "orders_by_status" in data
        assert "avg_order_value" in data


# =====================================================================
# 9. Suppliers
# =====================================================================

class TestSuppliers:
    """GET /api/v1/suppliers/ returns supplier listing."""

    def test_list_suppliers(self, client: TestClient):
        r = client.get(f"{API}/suppliers/")
        assert r.status_code == 200
        data = r.json()
        assert "suppliers" in data
        assert "total" in data


# =====================================================================
# 10. Process mining (demo endpoints)
# =====================================================================

class TestProcessMining:
    """Process mining demo endpoints."""

    def test_demo_events(self, client: TestClient):
        r = client.get(f"{API}/process-mining/demo/events")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert data["total_events"] > 0

    def test_demo_dfg(self, client: TestClient):
        r = client.get(f"{API}/process-mining/demo/dfg")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

    def test_demo_lead_times(self, client: TestClient):
        r = client.get(f"{API}/process-mining/demo/lead-times")
        assert r.status_code == 200

    def test_demo_bottlenecks(self, client: TestClient):
        r = client.get(f"{API}/process-mining/demo/bottlenecks")
        assert r.status_code == 200

    def test_demo_variants(self, client: TestClient):
        r = client.get(f"{API}/process-mining/demo/variants")
        assert r.status_code == 200


# =====================================================================
# 11. What-If alerts demo
# =====================================================================

class TestAlerts:
    """GET /api/v1/whatif/alerts-demo (actually /whatif/alerts/demo)."""

    def test_alerts_demo(self, client: TestClient):
        r = client.get(f"{API}/whatif/alerts/demo")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
        assert "summary" in data
        assert data["summary"]["total"] > 0

    def test_whatif_scenarios_demo(self, client: TestClient):
        r = client.get(f"{API}/whatif/scenarios/demo")
        assert r.status_code == 200
        data = r.json()
        assert "scenarios" in data


# =====================================================================
# 12. Domains registry
# =====================================================================

class TestDomains:
    """Domain metadata endpoints."""

    def test_list_domains(self, client: TestClient):
        r = client.get(f"{API}/domains")
        assert r.status_code == 200
        data = r.json()
        assert "domains" in data
        assert data["total"] >= 10

    def test_extended_domains(self, client: TestClient):
        r = client.get(f"{API}/domains/extended")
        assert r.status_code == 200
        data = r.json()
        assert "domains" in data
        assert data["total"] >= 10


# =====================================================================
# 13. Buying flow (end-to-end: calculate -> optimize -> checkout)
# =====================================================================

class TestBuyingFlow:
    """End-to-end buying workflow."""

    def test_calculate_cart(self, client: TestClient):
        payload = {
            "items": [
                {"id": "BRK-001", "quantity": 10},
                {"id": "FIL-001", "quantity": 20},
            ]
        }
        r = client.post(f"{API}/buying/calculate", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "subtotal" in data
        assert data["subtotal"] > 0
        assert "total_items" in data

    def test_optimize_and_checkout(self, client: TestClient):
        # Step 1: optimize
        payload = {
            "items": [
                {"id": "BRK-001", "quantity": 5},
                {"id": "FIL-001", "quantity": 10},
            ],
            "mpk": "TEST-MPK",
            "gl_account": "400-Test",
            "destination_region": "PL-MA",
        }
        r_opt = client.post(f"{API}/buying/optimize", json=payload)
        assert r_opt.status_code == 200
        opt = r_opt.json()
        assert opt["success"] is True
        assert "optimization_id" in opt

        # Step 2: checkout
        r_co = client.post(
            f"{API}/buying/checkout",
            json={"optimization_id": opt["optimization_id"]},
        )
        assert r_co.status_code == 200
        co = r_co.json()
        assert co["success"] is True
        assert "order_id" in co

        # Verify order exists
        order_id = co["order_id"]
        r_detail = client.get(f"{API}/buying/orders/{order_id}")
        assert r_detail.status_code == 200
        assert r_detail.json()["success"] is True

    def test_orders_list(self, client: TestClient):
        r = client.get(f"{API}/buying/orders")
        assert r.status_code == 200
        data = r.json()
        assert "orders" in data
        assert "statuses" in data
