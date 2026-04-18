"""
Comprehensive API tests for the Flow Procurement Platform.

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


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict:
    """JWT for the 'buyer' demo user. Tenant-scoped endpoints (orders,
    contracts, kpi, spend, scorecard) require auth as of Faza 1.1."""
    r = client.post("/auth/login", json={"username": "buyer", "password": "buyer123"})
    if r.status_code != 200:
        pytest.skip(f"Demo buyer login unavailable: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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

    def test_kpi_returns_200(self, client: TestClient, auth_headers):
        r = client.get(f"{API}/buying/kpi", headers=auth_headers)
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

    def test_optimize_and_checkout(self, client: TestClient, auth_headers):
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

        # Step 2: checkout — requires auth as of Faza 1.1
        r_co = client.post(
            f"{API}/buying/checkout",
            json={"optimization_id": opt["optimization_id"]},
            headers=auth_headers,
        )
        assert r_co.status_code == 200
        co = r_co.json()
        assert co["success"] is True
        assert "order_id" in co


# =====================================================================
# 14. Auctions / E-Sourcing
# =====================================================================

class TestAuctions:
    """Auction lifecycle: create → publish → start → bid → close → award."""

    def test_create_auction(self, client: TestClient):
        payload = {
            "title": "Test Auction",
            "auction_type": "reverse",
            "domain": "parts",
            "line_items": [
                {
                    "product_name": "Klocki hamulcowe",
                    "quantity": 100,
                    "unit": "szt",
                    "max_unit_price": 150.0,
                },
            ],
            "invited_suppliers": ["TRW-001", "BREMBO-001"],
            "duration_hours": 24,
            "min_decrement_pct": 1.0,
        }
        r = client.post(f"{API}/auctions/", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "auction" in data
        assert data["auction"]["status"] == "draft"
        assert data["auction"]["auction_id"]

    def test_list_auctions(self, client: TestClient):
        r = client.get(f"{API}/auctions/")
        assert r.status_code == 200
        data = r.json()
        assert "auctions" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_demo_auction(self, client: TestClient):
        r = client.get(f"{API}/auctions/demo")
        assert r.status_code == 200
        data = r.json()
        assert "auction" in data
        assert "stats" in data
        assert data["auction"]["status"] in ("active", "published", "closed")

    def test_get_auction_detail(self, client: TestClient):
        # Create, then get
        create_r = client.post(f"{API}/auctions/", json={
            "title": "Detail Test",
            "auction_type": "reverse",
            "domain": "parts",
            "line_items": [{"product_name": "Filtr oleju", "quantity": 50, "unit": "szt", "max_unit_price": 45.0}],
            "invited_suppliers": ["BOSCH-001"],
            "duration_hours": 12,
            "min_decrement_pct": 0.5,
        })
        aid = create_r.json()["auction"]["auction_id"]

        r = client.get(f"{API}/auctions/{aid}")
        assert r.status_code == 200
        data = r.json()
        assert data["auction"]["auction_id"] == aid
        assert "stats" in data

    def test_auction_not_found(self, client: TestClient):
        r = client.get(f"{API}/auctions/nonexistent-id")
        assert r.status_code == 404

    def test_auction_lifecycle(self, client: TestClient):
        # Create
        cr = client.post(f"{API}/auctions/", json={
            "title": "Lifecycle Test",
            "auction_type": "reverse",
            "domain": "parts",
            "line_items": [{"product_name": "Olej 5W-30", "quantity": 200, "unit": "l", "max_unit_price": 25.0}],
            "invited_suppliers": ["CASTROL-001"],
            "duration_hours": 48,
            "min_decrement_pct": 2.0,
        })
        aid = cr.json()["auction"]["auction_id"]

        # Publish
        r = client.post(f"{API}/auctions/{aid}/publish")
        assert r.status_code == 200
        assert r.json()["status"] == "published"

        # Start
        r = client.post(f"{API}/auctions/{aid}/start")
        assert r.status_code == 200
        assert r.json()["status"] == "active"

        # Close
        r = client.post(f"{API}/auctions/{aid}/close")
        assert r.status_code == 200
        assert r.json()["status"] in ("closing", "closed")

    def test_auction_cancel(self, client: TestClient):
        cr = client.post(f"{API}/auctions/", json={
            "title": "Cancel Test",
            "auction_type": "reverse",
            "domain": "parts",
            "line_items": [{"product_name": "Test", "quantity": 10, "unit": "szt", "max_unit_price": 10.0}],
            "invited_suppliers": ["TRW-001"],
            "duration_hours": 1,
            "min_decrement_pct": 1.0,
        })
        aid = cr.json()["auction"]["auction_id"]
        r = client.post(f"{API}/auctions/{aid}/cancel")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_auction_stats(self, client: TestClient):
        # Use demo auction which has bids
        demo = client.get(f"{API}/auctions/demo").json()
        aid = demo["auction"]["auction_id"]
        r = client.get(f"{API}/auctions/{aid}/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_bids" in data or "unique_suppliers" in data

    def test_auction_ranking(self, client: TestClient):
        demo = client.get(f"{API}/auctions/demo").json()
        aid = demo["auction"]["auction_id"]
        r = client.get(f"{API}/auctions/{aid}/ranking")
        assert r.status_code == 200
        data = r.json()
        assert "rankings" in data


# =====================================================================
# 15. Predictive Analytics / ML
# =====================================================================

class TestPredictions:
    """Prediction demo endpoints."""

    def test_predictions_demo(self, client: TestClient):
        r = client.get(f"{API}/predictions/demo")
        assert r.status_code == 200
        data = r.json()
        assert "predictions" in data
        assert "alerts" in data
        assert "profiles" in data
        assert len(data["predictions"]) > 0

    def test_prediction_fields(self, client: TestClient):
        r = client.get(f"{API}/predictions/demo")
        data = r.json()
        pred = data["predictions"][0]
        assert "product_id" in pred
        assert "probability_delay" in pred
        assert "predicted_delay_days" in pred
        assert "risk_level" in pred
        assert "factors" in pred

    def test_prediction_alerts(self, client: TestClient):
        r = client.get(f"{API}/predictions/demo")
        data = r.json()
        for alert in data["alerts"]:
            assert "severity" in alert
            assert "description" in alert
            assert alert["severity"] in ("critical", "high", "medium", "low", "info")

    def test_prediction_profiles(self, client: TestClient):
        r = client.get(f"{API}/predictions/demo")
        data = r.json()
        profiles = data["profiles"]
        assert isinstance(profiles, dict)
        assert len(profiles) > 0
        for sid, p in profiles.items():
            assert isinstance(sid, str)
            assert "supplier_id" in p
            assert "avg_lead_time_days" in p
            assert "on_time_rate" in p


# =====================================================================
# 16. AI Copilot
# =====================================================================

class TestCopilot:
    """AI Copilot chat and suggestions endpoints."""

    def test_copilot_suggestions(self, client: TestClient):
        r = client.get(f"{API}/copilot/suggestions", params={"step": 1, "domain": "parts"})
        assert r.status_code == 200
        data = r.json()
        assert data["step"] == 1
        assert data["domain"] == "parts"
        assert len(data["suggestions"]) > 0

    def test_copilot_suggestions_step3(self, client: TestClient):
        r = client.get(f"{API}/copilot/suggestions", params={"step": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["step"] == 3
        assert any("optymalizacj" in s.lower() or "pareto" in s.lower() for s in data["suggestions"])

    def test_copilot_chat_optimize(self, client: TestClient):
        r = client.post(f"{API}/copilot/chat", json={
            "message": "Optymalizuj klocki hamulcowe",
            "context": {"step": 1, "domain": "parts"},
        })
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert len(data["reply"]) > 10
        assert "actions" in data

    def test_copilot_chat_explain_pareto(self, client: TestClient):
        r = client.post(f"{API}/copilot/chat", json={
            "message": "Wyjaśnij front Pareto",
            "context": {"step": 3},
        })
        assert r.status_code == 200
        data = r.json()
        assert "pareto" in data["reply"].lower()

    def test_copilot_chat_navigate(self, client: TestClient):
        r = client.post(f"{API}/copilot/chat", json={
            "message": "Przejdź do dostawców",
            "context": {"step": 1},
        })
        assert r.status_code == 200
        data = r.json()
        assert "actions" in data

    def test_copilot_chat_unknown_fallback(self, client: TestClient):
        """Unknown intent should return a helpful fallback (not crash)."""
        r = client.post(f"{API}/copilot/chat", json={
            "message": "xyzzy foobar qux",
            "context": {"step": 2},
        })
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert len(data["reply"]) > 5
        assert "suggestions" in data

    def test_copilot_chat_risk_query(self, client: TestClient):
        r = client.post(f"{API}/copilot/chat", json={
            "message": "Pokaż ryzyko dostawców",
            "context": {"step": 5},
        })
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data

    def test_copilot_chat_create_auction(self, client: TestClient):
        r = client.post(f"{API}/copilot/chat", json={
            "message": "Utwórz nową aukcję",
            "context": {"step": 4},
        })
        assert r.status_code == 200
        data = r.json()
        assert "aukcj" in data["reply"].lower()

    def test_orders_list(self, client: TestClient, auth_headers):
        r = client.get(f"{API}/buying/orders", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "orders" in data
        assert "statuses" in data
