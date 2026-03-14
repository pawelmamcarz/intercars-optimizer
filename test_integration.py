"""
Comprehensive integration tests for INTERCARS Order Portfolio Optimizer.
Tests cross-module bridges, order lifecycle, supplier management, and KPIs.
"""
import sys
import traceback

# Ensure clean state for in-memory stores
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API = "/api/v1"
results = []


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed))
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def safe_test(name: str, fn):
    try:
        fn()
    except Exception as e:
        record(name, False, f"Exception: {e}")
        traceback.print_exc()


# =====================================================================
# 1. Tab 1 -> Tab 2 bridge: optimizer results -> buying order
# =====================================================================
def test_tab1_to_tab2_bridge():
    # First run demo optimization via Tab 1
    r = client.get(f"{API}/optimize/demo?domain=parts")
    assert r.status_code == 200, f"optimize/demo returned {r.status_code}"
    opt = r.json()
    assert opt.get("success"), "optimize/demo not successful"

    allocations = []
    for a in opt.get("allocations", []):
        allocations.append({
            "supplier_id": a["supplier_id"],
            "supplier_name": a["supplier_name"],
            "product_id": a["product_id"],
            "allocated_qty": a["allocated_qty"],
            "unit_cost": a["unit_cost"],
            "logistics_cost": a["logistics_cost"],
            "lead_time_days": a["lead_time_days"],
            "allocated_fraction": a["allocated_fraction"],
        })

    demand = [
        {"product_id": a["product_id"], "demand_qty": a["allocated_qty"], "destination_region": "PL-MA"}
        for a in allocations[:3]
    ]

    payload = {
        "domain": "parts",
        "allocations": allocations[:5],
        "demand": demand,
        "objective": opt.get("objective", {}),
        "solver_stats": opt.get("solver_stats", {}),
        "mpk": "TEST-MPK-01",
        "gl_account": "400-Test",
    }

    r2 = client.post(f"{API}/buying/order-from-optimizer", json=payload)
    assert r2.status_code == 200, f"order-from-optimizer returned {r2.status_code}"
    body = r2.json()
    assert body.get("success"), f"order-from-optimizer failed: {body}"
    assert body.get("order_id"), "No order_id returned"

    record("1. Tab1->Tab2 bridge: order-from-optimizer", True,
           f"order_id={body['order_id']}, status={body['order_status']}")
    return body["order_id"]


# =====================================================================
# 2. Tab 2 full flow: add items -> calculate -> optimize -> checkout
# =====================================================================
def test_tab2_full_flow():
    items = [
        {"id": "BRK-001", "quantity": 10},
        {"id": "FIL-001", "quantity": 20},
        {"id": "DSC-001", "quantity": 4},
    ]

    # 2a. Calculate cart
    r_calc = client.post(f"{API}/buying/calculate", json={"items": items})
    assert r_calc.status_code == 200
    calc = r_calc.json()
    assert "subtotal" in calc, "calculate missing subtotal"
    assert calc["subtotal"] > 0, "subtotal should be > 0"
    record("2a. Tab2: calculate cart", True,
           f"subtotal={calc['subtotal']}, items={calc['total_items']}")

    # 2b. Optimize (step 1)
    checkout_payload = {
        "items": items,
        "mpk": "IT-200",
        "gl_account": "400-Auto",
        "destination_region": "PL-MA",
    }
    r_opt = client.post(f"{API}/buying/optimize", json=checkout_payload)
    assert r_opt.status_code == 200
    opt = r_opt.json()
    assert opt.get("success"), f"optimize failed: {opt}"
    assert opt.get("optimization_id"), "No optimization_id"
    opt_id = opt["optimization_id"]
    record("2b. Tab2: optimize cart", True,
           f"opt_id={opt_id}, optimized_cost={opt.get('optimized_cost')}")

    # 2c. Checkout (step 2)
    r_checkout = client.post(f"{API}/buying/checkout", json={"optimization_id": opt_id})
    assert r_checkout.status_code == 200
    co = r_checkout.json()
    assert co.get("success"), f"checkout failed: {co}"
    assert co.get("order_id"), "No order_id from checkout"
    record("2c. Tab2: checkout (place order)", True,
           f"order_id={co['order_id']}, status={co['order_status']}")

    return co["order_id"]


# =====================================================================
# 3. Tab 2 -> Tab 1 bridge: open-in-optimizer
# =====================================================================
def test_tab2_to_tab1_bridge():
    items = [
        {"id": "BRK-001", "quantity": 5},
        {"id": "DSC-001", "quantity": 3},
    ]
    r = client.post(f"{API}/buying/open-in-optimizer", json={"items": items})
    assert r.status_code == 200
    body = r.json()
    assert body.get("success"), f"open-in-optimizer failed: {body}"
    assert body.get("domains"), "No domains returned"
    assert len(body["domains"]) > 0, "Empty domains list"

    # Verify demand mapping
    total_demand = sum(
        len(d["demand"]) for d in body["domains"]
    )
    record("3. Tab2->Tab1 bridge: open-in-optimizer", True,
           f"domains={len(body['domains'])}, demand_items={total_demand}")


# =====================================================================
# 4. Tab 2 KPI
# =====================================================================
def test_tab2_kpi():
    r = client.get(f"{API}/buying/kpi")
    assert r.status_code == 200
    kpi = r.json()
    assert kpi.get("success"), f"KPI failed: {kpi}"
    assert "orders_total" in kpi, "Missing orders_total"
    assert "total_spend" in kpi, "Missing total_spend"
    assert "orders_by_status" in kpi, "Missing orders_by_status"
    record("4. Tab2 KPI", True,
           f"orders={kpi['orders_total']}, spend={kpi['total_spend']}, savings={kpi['total_savings']}")


# =====================================================================
# 5. Supplier module CRUD + certificates + assessment
# =====================================================================
def test_supplier_module():
    # 5a. Create supplier
    r_create = client.post(f"{API}/suppliers/", json={
        "nip": "5260250995",
        "name_override": "Test Supplier Sp. z o.o.",
        "domains": ["parts", "oils"],
    })
    assert r_create.status_code == 200, f"create supplier: {r_create.status_code} {r_create.text}"
    sup = r_create.json()
    sid = sup["supplier_id"]
    record("5a. Supplier: create", True, f"id={sid}, name={sup['name']}")

    # 5b. Get supplier
    r_get = client.get(f"{API}/suppliers/{sid}")
    assert r_get.status_code == 200
    assert r_get.json()["supplier_id"] == sid
    record("5b. Supplier: get by ID", True, f"id={sid}")

    # 5c. List suppliers
    r_list = client.get(f"{API}/suppliers/")
    assert r_list.status_code == 200
    slist = r_list.json()
    assert slist["total"] > 0
    record("5c. Supplier: list", True, f"total={slist['total']}")

    # 5d. Add certificate
    cert_payload = {
        "cert_type": "ISO 9001",
        "issuer": "TUV Rheinland",
        "issue_date": "2024-01-15",
        "expiry_date": "2027-01-15",
        "notes": "Integration test cert",
    }
    r_cert = client.post(f"{API}/suppliers/{sid}/certificates", json=cert_payload)
    assert r_cert.status_code == 200
    sup_after = r_cert.json()
    assert len(sup_after["certificates"]) > 0
    record("5d. Supplier: add certificate", True,
           f"certs={len(sup_after['certificates'])}")

    # 5e. Submit assessment
    # Get questions first
    r_q = client.get(f"{API}/suppliers/assessment/questions")
    assert r_q.status_code == 200
    questions = r_q.json()["questions"]

    answers = [{"question_id": q["question_id"], "score": 4, "comment": "Good"} for q in questions[:5]]
    r_assess = client.post(f"{API}/suppliers/{sid}/assessment", json=answers)
    assert r_assess.status_code == 200
    assess = r_assess.json()
    assert "overall_score" in assess
    record("5e. Supplier: submit assessment", True,
           f"score={assess['overall_score']}")

    # 5f. Delete supplier
    r_del = client.delete(f"{API}/suppliers/{sid}")
    assert r_del.status_code == 200
    assert r_del.json().get("success")
    record("5f. Supplier: delete", True, f"id={sid}")

    # Confirm deleted
    r_gone = client.get(f"{API}/suppliers/{sid}")
    assert r_gone.status_code == 404
    record("5g. Supplier: confirm deleted (404)", True, "")


# =====================================================================
# 6. Tab 6 -> Tab 1: run optimization from supplier profile
# =====================================================================
def test_tab6_to_tab1():
    # Create a supplier first
    r_create = client.post(f"{API}/suppliers/", json={
        "nip": "1234567890",
        "name_override": "Optimizer Test Supplier",
        "domains": ["parts"],
    })
    assert r_create.status_code == 200
    sid = r_create.json()["supplier_id"]

    r_opt = client.post(f"{API}/suppliers/{sid}/run-optimization?domain=parts")
    assert r_opt.status_code == 200
    body = r_opt.json()
    assert body.get("success"), f"run-optimization failed: {body}"
    assert "allocations" in body
    record("6. Tab6->Tab1: run-optimization from supplier", True,
           f"allocations={len(body['allocations'])}, objective={body.get('objective', {}).get('total', 'N/A')}")

    # Cleanup
    client.delete(f"{API}/suppliers/{sid}")


# =====================================================================
# 7. Full order lifecycle
# =====================================================================
def test_order_lifecycle():
    # Create order via Tab 2 flow
    # Use high-value items to trigger manager approval (>15000 PLN) but stay under 100 items
    items = [
        {"id": "ALT-001", "quantity": 10},   # 890 * 10 = 8900
        {"id": "ROZ-001", "quantity": 10},   # 780 * 10 = 7800  => total ~16700 > 15000
    ]
    r_opt = client.post(f"{API}/buying/optimize", json={
        "items": items, "mpk": "LIFECYCLE-01", "gl_account": "400-Lifecycle",
        "destination_region": "PL-MA",
    })
    assert r_opt.status_code == 200
    opt = r_opt.json()
    assert opt.get("success"), f"lifecycle optimize failed: {opt}"
    opt_id = opt["optimization_id"]
    needs_approval = opt.get("cart_summary", {}).get("requires_manager_approval", False)

    r_co = client.post(f"{API}/buying/checkout", json={"optimization_id": opt_id})
    assert r_co.status_code == 200
    co = r_co.json()
    assert co.get("success")
    oid = co["order_id"]
    initial_status = co["order_status"]
    record("7a. Lifecycle: create order", True,
           f"id={oid}, status={initial_status}, needs_approval={needs_approval}")

    # 7b. Approve — only if order requires approval (pending_approval status)
    if initial_status == "pending_approval":
        r_approve = client.post(f"{API}/buying/orders/{oid}/approve?approver=test-manager@intercars.eu")
        assert r_approve.status_code == 200
        ap = r_approve.json()
        assert ap.get("success"), f"approve failed: {ap}"
        record("7b. Lifecycle: approve", True, f"status={ap['order']['status']}")
    else:
        # Already approved (auto-approved because no manager approval needed)
        record("7b. Lifecycle: approve (auto-approved)", True, f"status={initial_status}")

    # 7c. Generate POs
    r_po = client.post(f"{API}/buying/orders/{oid}/generate-po")
    assert r_po.status_code == 200
    po = r_po.json()
    assert po.get("success"), f"generate-po failed: {po}"
    po_count = len(po.get("purchase_orders", []))
    record("7c. Lifecycle: generate PO", True,
           f"POs={po_count}, status={po['order']['status']}")

    # 7d. Confirm
    r_confirm = client.post(f"{API}/buying/orders/{oid}/confirm")
    assert r_confirm.status_code == 200
    conf = r_confirm.json()
    assert conf.get("success"), f"confirm failed: {conf}"
    record("7d. Lifecycle: confirm", True, f"status={conf['order']['status']}")

    # 7e. Ship
    r_ship = client.post(f"{API}/buying/orders/{oid}/ship")
    assert r_ship.status_code == 200
    ship = r_ship.json()
    assert ship.get("success"), f"ship failed: {ship}"
    record("7e. Lifecycle: ship", True, f"status={ship['order']['status']}")

    # 7f. Deliver
    r_deliver = client.post(f"{API}/buying/orders/{oid}/deliver")
    assert r_deliver.status_code == 200
    dlv = r_deliver.json()
    assert dlv.get("success"), f"deliver failed: {dlv}"
    record("7f. Lifecycle: deliver", True, f"status={dlv['order']['status']}")

    return oid


# =====================================================================
# 8. Tab 2 order management: list, detail, timeline
# =====================================================================
def test_order_management(order_id: str):
    # 8a. List orders
    r_list = client.get(f"{API}/buying/orders")
    assert r_list.status_code == 200
    ol = r_list.json()
    assert len(ol["orders"]) > 0
    record("8a. Order mgmt: list orders", True, f"count={len(ol['orders'])}")

    # 8b. Get order detail
    r_detail = client.get(f"{API}/buying/orders/{order_id}")
    assert r_detail.status_code == 200
    det = r_detail.json()
    assert det.get("success")
    assert det["order"]["order_id"] == order_id
    record("8b. Order mgmt: get detail", True, f"id={order_id}, status={det['order']['status']}")

    # 8c. Get timeline
    r_tl = client.get(f"{API}/buying/orders/{order_id}/timeline")
    assert r_tl.status_code == 200
    tl = r_tl.json()
    assert tl.get("success")
    assert len(tl["timeline"]) > 0
    record("8c. Order mgmt: get timeline", True,
           f"events={len(tl['timeline'])}, status={tl['current_status']}")


# =====================================================================
# Run all tests
# =====================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("INTERCARS Optimizer — Integration Test Suite")
    print("=" * 70)

    # Test 1
    print("\n--- Test 1: Tab1 -> Tab2 Bridge ---")
    bridge_order_id = None
    safe_test("1. Tab1->Tab2 bridge", lambda: None)
    try:
        bridge_order_id = test_tab1_to_tab2_bridge()
    except Exception as e:
        record("1. Tab1->Tab2 bridge: order-from-optimizer", False, str(e))
        traceback.print_exc()

    # Test 2
    print("\n--- Test 2: Tab2 Full Flow ---")
    tab2_order_id = None
    try:
        tab2_order_id = test_tab2_full_flow()
    except Exception as e:
        record("2. Tab2 full flow", False, str(e))
        traceback.print_exc()

    # Test 3
    print("\n--- Test 3: Tab2 -> Tab1 Bridge ---")
    safe_test("3. Tab2->Tab1 bridge", test_tab2_to_tab1_bridge)

    # Test 4
    print("\n--- Test 4: Tab2 KPI ---")
    safe_test("4. Tab2 KPI", test_tab2_kpi)

    # Test 5
    print("\n--- Test 5: Supplier Module ---")
    safe_test("5. Supplier module", test_supplier_module)

    # Test 6
    print("\n--- Test 6: Tab6 -> Tab1 ---")
    safe_test("6. Tab6->Tab1", test_tab6_to_tab1)

    # Test 7
    print("\n--- Test 7: Order Lifecycle ---")
    lifecycle_order_id = None
    try:
        lifecycle_order_id = test_order_lifecycle()
    except Exception as e:
        record("7. Order lifecycle", False, str(e))
        traceback.print_exc()

    # Test 8
    print("\n--- Test 8: Order Management ---")
    target_oid = lifecycle_order_id or tab2_order_id or bridge_order_id
    if target_oid:
        safe_test("8. Order management", lambda: test_order_management(target_oid))
    else:
        record("8a. Order mgmt: list orders", False, "No order_id available")
        record("8b. Order mgmt: get detail", False, "No order_id available")
        record("8c. Order mgmt: get timeline", False, "No order_id available")

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for _, p in results if p)
    failed = sum(1 for _, p in results if not p)
    total = len(results)
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    print("=" * 70)

    if failed > 0:
        print("\nFailed tests:")
        for name, p in results:
            if not p:
                print(f"  FAIL: {name}")
        sys.exit(1)
    else:
        print("\nAll integration tests passed!")
        sys.exit(0)
