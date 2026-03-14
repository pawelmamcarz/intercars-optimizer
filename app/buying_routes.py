"""
Optimized Buying — API routes.

GET  /buying/catalog              → product catalog (optionally filtered)
GET  /buying/categories           → category list
POST /buying/calculate            → apply cart rules, return full state
POST /buying/optimize             → step 1: run optimizer (no order created)
POST /buying/checkout             → step 2: place order from optimization result
POST /buying/order-from-optimizer → create order from Tab 1 optimizer results
GET  /buying/orders               → list orders (optional status filter)
GET  /buying/orders/{order_id}    → order details
POST /buying/orders/{id}/approve  → manager approval
POST /buying/orders/{id}/generate-po → generate purchase orders
POST /buying/orders/{id}/confirm  → supplier confirms POs
POST /buying/orders/{id}/ship     → mark as in-delivery
POST /buying/orders/{id}/deliver  → goods receipt
POST /buying/orders/{id}/cancel   → cancel order
GET  /buying/orders/{id}/timeline → order timeline / audit log
GET  /buying/kpi                  → aggregate order statistics
POST /buying/open-in-optimizer    → bridge cart items to Tab 1 optimizer
"""

from __future__ import annotations

import csv
import io
import logging

from pathlib import Path

from fastapi import APIRouter, Body, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.buying_engine import (
    get_catalog,
    get_categories,
    calculate_cart_state,
    map_cart_to_demand,
    create_order,
    get_order,
    list_orders,
    approve_order,
    generate_purchase_orders,
    confirm_order,
    ship_order,
    deliver_order,
    cancel_order,
    STATUS_LABELS,
    ORDER_STATUSES,
)
from app.data_layer import get_domain_data, DOMAIN_WEIGHTS
from app.optimizer import run_optimization
from app.schemas import CriteriaWeights, DemandItem

buying_router = APIRouter(tags=["Optimized Buying"])


# ── Schemas ────────────────────────────────────────────────────────────────

class CartItemIn(BaseModel):
    id: str
    quantity: int = 1


class CartRequest(BaseModel):
    items: list[CartItemIn]


class CheckoutRequest(BaseModel):
    items: list[CartItemIn]
    mpk: str = "IT-100"
    gl_account: str = "400-Auto-Parts"
    destination_region: str = "PL-MA"


# ── Endpoints ──────────────────────────────────────────────────────────────

# ── UNSPSC segment → catalog category mapping ────────────────────────────
_UNSPSC_TO_CATEGORIES: dict[str, list[str]] = {
    "10": ["horticulture"],
    "11": ["raw_materials"],
    "12": ["chemicals"],
    "13": ["rubber_plastics"],
    "14": ["paper"],
    "15": ["oils", "fuels"],
    "20": ["mining_equip"],
    "21": ["agri_equip"],
    "22": ["construction_eq"],
    "23": ["industrial_mach"],
    "24": ["logistics", "packaging"],
    "25": ["parts", "oe_components", "tires", "bodywork", "batteries", "vehicles"],
    "26": ["electrical"],
    "27": ["mro"],
    "30": ["construction", "steel"],
    "31": ["bearings"],
    "32": ["semiconductors"],
    "39": ["lighting"],
    "40": ["hvac"],
    "41": ["lab_equipment"],
    "42": ["medical"],
    "43": ["it_services", "electronics"],
    "44": ["office"],
    "45": ["printing_equip"],
    "46": ["safety"],
    "47": ["cleaning"],
    "48": ["sports"],
    "49": ["furniture"],
    "50": ["food"],
    "51": ["pharma"],
    "52": ["appliances"],
    "53": ["clothing"],
    "55": ["publications"],
    "56": ["decorations"],
    "60": ["prefab"],
    "70": ["agri_services"],
    "71": ["mining_services"],
    "72": ["construction_svc"],
    "73": ["production_svc"],
    "76": ["industrial_clean"],
    "77": ["environmental"],
    "78": ["transport_svc", "logistics"],
    "80": ["consulting", "fleet_svc"],
    "81": ["engineering_svc"],
    "82": ["printing"],
    "83": ["utilities"],
    "84": ["financial_svc"],
    "85": ["healthcare_svc"],
    "86": ["consulting"],
    "90": ["travel"],
    "95": ["real_estate"],
}

# Deeper UNSPSC → specific category (4-6 digit overrides)
_UNSPSC_DEEP_MAP: dict[str, str] = {
    "2510": "vehicles",        # Pojazdy silnikowe → vehicles, nie parts
    "251010": "vehicles",      # Samochody osobowe
    "251012": "vehicles",      # Samochody dostawcze
    "251030": "vehicles",      # Pojazdy ciężarowe
    "251040": "vehicles",      # Autobusy
    "2511": "vehicles",        # Pojazdy morskie
    "2512": "vehicles",        # Pojazdy kolejowe
    "2513": "vehicles",        # Pojazdy lotnicze
    "2514": "sports",          # Rowery
    "2517": "parts",           # Akcesoria pojazdowe → parts
    "251715": "tires",         # Opony
    "251720": "batteries",     # Akumulatory pojazdów
    "251725": "bodywork",      # Oświetlenie pojazdów
    "2518": "vehicles",        # Przyczepy, naczepy
    "2519": "transport_svc",   # Osprzęt transportowy
    "25101500": "parts",       # Hamulce → parts
    "25101600": "parts",       # Zawieszenie
    "25101700": "parts",       # Kierownica
    "25102000": "oe_components",  # Elektryka silnikowa
    "1512": "oils",            # Oleje i smary
    "1511": "fuels",           # Paliwa stałe
    "1513": "fuels",           # Paliwa gazowe
    "4321": "electronics",     # Komputery
    "4322": "electronics",     # Urządzenia peryferyjne
    "4323": "it_services",     # Oprogramowanie
    "4324": "electronics",     # Telefonia
    "2611": "batteries",       # Akumulatory przemysłowe
    "2612": "electrical",      # Przewody i kable
    "2613": "electrical",      # Aparatura
    "3010": "steel",           # Profile stalowe
    "3011": "steel",           # Blachy
    "3015": "steel",           # Elementy złączne
    "8010": "consulting",      # Usługi doradcze
    "8015": "fleet_svc",       # Fleet management
    "8610": "consulting",      # Szkolenia
}


def _find_catalog_by_unspsc(code: str) -> list[dict]:
    """Smart UNSPSC-based catalog search.

    Strategy:
    1. Try deep map (most specific match first: 6→4→2 digit)
    2. Find all categories for the segment
    3. Return items from matching categories
    4. If nothing, expand to neighboring segments
    """
    from app.buying_engine import CATALOG

    # 1. Try deep map (most specific first)
    target_cat = None
    for length in (8, 6, 4):
        prefix = code[:length]
        if prefix in _UNSPSC_DEEP_MAP:
            target_cat = _UNSPSC_DEEP_MAP[prefix]
            break

    if target_cat:
        items = [p for p in CATALOG if p["category"] == target_cat]
        if items:
            # Also add items from sibling categories in same segment
            seg = code[:2]
            sibling_cats = _UNSPSC_TO_CATEGORIES.get(seg, [])
            siblings = [p for p in CATALOG if p["category"] in sibling_cats
                        and p["category"] != target_cat]
            # Return target items first, then siblings
            return items + siblings[:10]

    # 2. Segment-level match
    seg = code[:2]
    cats = _UNSPSC_TO_CATEGORIES.get(seg, [])
    if cats:
        items = [p for p in CATALOG if p["category"] in cats]
        if items:
            return items

    # 3. Neighboring segments (±1, ±2)
    try:
        seg_num = int(seg)
        for delta in [1, -1, 2, -2, 5, -5]:
            neighbor = str(seg_num + delta).zfill(2)
            n_cats = _UNSPSC_TO_CATEGORIES.get(neighbor, [])
            if n_cats:
                items = [p for p in CATALOG if p["category"] in n_cats]
                if items:
                    return items
    except ValueError:
        pass

    # 4. Return everything as fallback
    return [p for p in CATALOG if not p.get("_is_bundle_source")]


@buying_router.get("/buying/catalog")
def catalog(category: str | None = Query(None),
            unspsc: str | None = Query(None)):
    """Return product catalog, filtered by category or UNSPSC code.

    When `unspsc` is provided, uses smart matching:
    - Deep UNSPSC code → specific category
    - Segment level → all categories for that segment
    - Fallback to neighboring segments
    """
    if unspsc:
        products = _find_catalog_by_unspsc(unspsc)
        return {"products": products, "categories": get_categories(),
                "unspsc_match": unspsc, "count": len(products)}
    return {"products": get_catalog(category), "categories": get_categories()}


@buying_router.get("/buying/categories")
def categories():
    """Return category list with metadata."""
    return {"categories": get_categories()}


@buying_router.post("/buying/calculate")
def calculate_cart(req: CartRequest):
    """Apply all business rules to cart and return computed state."""
    raw = [{"id": i.id, "quantity": i.quantity} for i in req.items]
    return calculate_cart_state(raw)


def _run_optimization_for_cart(cart_state: dict, destination_region: str):
    """Shared helper: run optimizer for each domain in the cart."""
    demand_by_domain = map_cart_to_demand(cart_state)
    domain_results = []
    total_optimized_cost = 0.0

    for domain, demand_items_raw in demand_by_domain.items():
        try:
            domain_data = get_domain_data(domain)
            suppliers = domain_data["suppliers"]
        except Exception:
            domain_results.append({
                "domain": domain,
                "success": False,
                "message": f"Brak danych dostawców dla domeny '{domain}'.",
            })
            continue

        all_regions: set[str] = set()
        for s in suppliers:
            all_regions.update(s.served_regions)
        dest_region = destination_region if destination_region in all_regions else next(iter(all_regions), "PL-MA")

        demand_items = [
            DemandItem(
                product_id=di["product_id"],
                demand_qty=di["demand_qty"],
                destination_region=dest_region,
            )
            for di in demand_items_raw
        ]

        wt = DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
        weights = CriteriaWeights(
            w_cost=wt[0], w_time=wt[1], w_compliance=wt[2], w_esg=wt[3],
        )

        try:
            response, _diag = run_optimization(
                suppliers=suppliers,
                demand=demand_items,
                weights=weights,
            )
            result = response.model_dump()

            for a in result.get("allocations", []):
                a["allocated_cost_pln"] = round(
                    a["allocated_qty"] * (a["unit_cost"] + a["logistics_cost"]), 2
                )

            domain_cost = sum(
                a.get("allocated_cost_pln", 0)
                for a in result.get("allocations", [])
            )
            total_optimized_cost += domain_cost

            domain_results.append({
                "domain": domain,
                "success": result.get("success", False),
                "allocations": result.get("allocations", []),
                "objective": result.get("objective", {}),
                "solver_stats": result.get("solver_stats", {}),
                "domain_cost": round(domain_cost, 2),
            })
        except Exception as e:
            domain_results.append({
                "domain": domain,
                "success": False,
                "message": str(e),
            })

    return {
        "optimized_cost": round(total_optimized_cost, 2),
        "savings_pln": round(cart_state["subtotal"] - total_optimized_cost, 2),
        "domain_results": domain_results,
    }


# In-memory store for pending optimization results (before order placement)
_pending_optimizations: dict[str, dict] = {}


@buying_router.post("/buying/optimize")
def optimize_cart(req: CheckoutRequest):
    """
    Step 1: Run optimizer for each domain in the cart.

    Returns optimization results WITHOUT creating an order.
    Returns an optimization_id to use in /buying/checkout.
    """
    raw = [{"id": i.id, "quantity": i.quantity} for i in req.items]
    cart_state = calculate_cart_state(raw)

    if not cart_state["can_checkout"]:
        return {
            "success": False,
            "message": "Zamówienie zawiera błędy — popraw koszyk.",
            "errors": cart_state["errors"],
            "cart": cart_state,
        }

    optimization_result = _run_optimization_for_cart(cart_state, req.destination_region)

    # Store for later checkout (UUID-based to avoid race conditions)
    import uuid as _uuid
    opt_id = f"OPT-{_uuid.uuid4().hex[:8].upper()}"
    _pending_optimizations[opt_id] = {
        "cart_state": cart_state,
        "optimization_result": optimization_result,
        "mpk": req.mpk,
        "gl_account": req.gl_account,
    }

    return {
        "success": True,
        "optimization_id": opt_id,
        "message": "Optymalizacja zakończona — potwierdź złożenie zamówienia.",
        "mpk": req.mpk,
        "gl_account": req.gl_account,
        "cart_summary": {
            "subtotal": cart_state["subtotal"],
            "discount": cart_state["discount"],
            "shipping_fee": cart_state["shipping_fee"],
            "cart_total": cart_state["total"],
            "total_items": cart_state["total_items"],
            "delivery_days": cart_state["delivery_days"],
            "requires_manager_approval": cart_state["requires_manager_approval"],
        },
        "optimized_cost": optimization_result["optimized_cost"],
        "savings_pln": optimization_result["savings_pln"],
        "domain_results": optimization_result["domain_results"],
    }


class PlaceOrderRequest(BaseModel):
    optimization_id: str


@buying_router.post("/buying/checkout")
def checkout(req: PlaceOrderRequest):
    """
    Step 2: Create order from a pending optimization result.

    Requires optimization_id from /buying/optimize.
    """
    pending = _pending_optimizations.pop(req.optimization_id, None)
    if not pending:
        return {
            "success": False,
            "message": "Wynik optymalizacji wygasł lub nie istnieje. Uruchom optymalizację ponownie.",
        }

    cart_state = pending["cart_state"]
    optimization_result = pending["optimization_result"]

    order = create_order(
        cart_state=cart_state,
        optimization_result=optimization_result,
        mpk=pending["mpk"],
        gl_account=pending["gl_account"],
    )

    return {
        "success": True,
        "message": "Zamówienie utworzone pomyślnie.",
        "order_id": order["order_id"],
        "order_status": order["status"],
        "order_status_label": order["status_label"],
        "requires_manager_approval": cart_state["requires_manager_approval"],
        "mpk": pending["mpk"],
        "gl_account": pending["gl_account"],
        "cart_summary": {
            "subtotal": cart_state["subtotal"],
            "discount": cart_state["discount"],
            "shipping_fee": cart_state["shipping_fee"],
            "cart_total": cart_state["total"],
            "total_items": cart_state["total_items"],
            "delivery_days": cart_state["delivery_days"],
            "requires_manager_approval": cart_state["requires_manager_approval"],
        },
        "optimized_cost": optimization_result["optimized_cost"],
        "savings_pln": optimization_result["savings_pln"],
        "domain_results": optimization_result["domain_results"],
    }


# ── Cross-module: Tab 1 Optimizer → Buying Order ─────────────────────────

class OptimizerOrderRequest(BaseModel):
    """Create a Buying order directly from Tab 1 optimization results."""
    domain: str
    allocations: list[dict]
    demand: list[dict]          # [{product_id, demand_qty, destination_region}]
    objective: dict = {}
    solver_stats: dict = {}
    mpk: str = "INTER-ZAKUPY-01"
    gl_account: str = "400-Auto-Parts"


@buying_router.post("/buying/order-from-optimizer")
def order_from_optimizer(req: OptimizerOrderRequest):
    """
    Create a Buying order from Tab 1 optimization results.

    Bridges the analytical optimizer with the order lifecycle.
    Synthesizes a cart_state from domain demand data.
    """
    # Compute total cost from allocations
    total_cost = 0.0
    for a in req.allocations:
        cost = a.get("allocated_qty", 0) * (a.get("unit_cost", 0) + a.get("logistics_cost", 0))
        a["allocated_cost_pln"] = round(cost, 2)
        total_cost += cost

    # Synthesize cart_state from demand data
    items = []
    total_items = 0
    max_lead = 0
    for d in req.demand:
        qty = d.get("demand_qty", 0)
        # Find avg unit cost from allocations for this product
        prod_allocs = [a for a in req.allocations if a.get("product_id") == d["product_id"]]
        avg_price = 0.0
        if prod_allocs:
            avg_price = sum(a.get("unit_cost", 0) for a in prod_allocs) / len(prod_allocs)
            max_lead = max(max_lead, max(a.get("lead_time_days", 0) for a in prod_allocs))
        items.append({
            "id": d["product_id"],
            "name": d["product_id"],
            "quantity": qty,
            "price": round(avg_price, 2),
            "line_total": round(avg_price * qty, 2),
            "category": req.domain,
            "unit": "szt.",
        })
        total_items += qty

    subtotal = sum(i["line_total"] for i in items)
    requires_approval = subtotal > 15000

    cart_state = {
        "items": items,
        "subtotal": round(subtotal, 2),
        "discount": 0.0,
        "shipping_fee": 0.0,
        "total": round(subtotal, 2),
        "total_items": total_items,
        "delivery_days": max(max_lead, 1),
        "requires_manager_approval": requires_approval,
    }

    optimization_result = {
        "optimized_cost": round(total_cost, 2),
        "savings_pln": round(subtotal - total_cost, 2),
        "domain_results": [{
            "domain": req.domain,
            "success": True,
            "allocations": req.allocations,
            "objective": req.objective,
            "solver_stats": req.solver_stats,
            "domain_cost": round(total_cost, 2),
        }],
    }

    order = create_order(
        cart_state=cart_state,
        optimization_result=optimization_result,
        mpk=req.mpk,
        gl_account=req.gl_account,
    )

    return {
        "success": True,
        "message": "Zamówienie utworzone z optymalizatora.",
        "order_id": order["order_id"],
        "order_status": order["status"],
        "order_status_label": order["status_label"],
        "requires_manager_approval": requires_approval,
        "optimized_cost": round(total_cost, 2),
        "savings_pln": round(subtotal - total_cost, 2),
        "domain": req.domain,
    }


# ── Order Management ─────────────────────────────────────────────────────

@buying_router.get("/buying/orders")
def orders_list(status: str | None = Query(None)):
    """List all orders, optionally filtered by status."""
    return {
        "orders": list_orders(status),
        "statuses": [{"id": s, "label": STATUS_LABELS[s]} for s in ORDER_STATUSES],
    }


@buying_router.get("/buying/orders/{order_id}")
def order_detail(order_id: str):
    """Get full order details."""
    order = get_order(order_id)
    if not order:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    return {"success": True, "order": order}


@buying_router.post("/buying/orders/{order_id}/approve")
def order_approve(order_id: str, approver: str = Query("manager@flowproc.eu")):
    """Manager approves an order (pending_approval → approved)."""
    result = approve_order(order_id, approver)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, "message": "Zamówienie zatwierdzone.", "order": result}


@buying_router.post("/buying/orders/{order_id}/generate-po")
def order_generate_po(order_id: str):
    """Generate Purchase Orders from optimized allocations (approved → po_generated)."""
    result = generate_purchase_orders(order_id)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {
        "success": True,
        "message": f"Wygenerowano {len(result['purchase_orders'])} zamówień zakupu.",
        "purchase_orders": result["purchase_orders"],
        "order": result,
    }


@buying_router.post("/buying/orders/{order_id}/confirm")
def order_confirm(order_id: str):
    """Supplier confirms all POs (po_generated → confirmed)."""
    result = confirm_order(order_id)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, "message": "Zamówienia potwierdzone przez dostawców.", "order": result}


@buying_router.post("/buying/orders/{order_id}/ship")
def order_ship(order_id: str):
    """Mark order as in delivery (confirmed → in_delivery)."""
    result = ship_order(order_id)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, "message": "Przesyłka w drodze.", "order": result}


@buying_router.post("/buying/orders/{order_id}/deliver")
def order_deliver(order_id: str):
    """Mark order as delivered — Goods Receipt (confirmed/in_delivery → delivered)."""
    result = deliver_order(order_id)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, "message": "Towar dostarczony — GR zaksięgowane.", "order": result}


@buying_router.post("/buying/orders/{order_id}/cancel")
def order_cancel(order_id: str, reason: str = Query("")):
    """Cancel order at any cancellable stage."""
    result = cancel_order(order_id, reason)
    if not result:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, "message": "Zamówienie anulowane.", "order": result}


@buying_router.get("/buying/orders/{order_id}/timeline")
def order_timeline(order_id: str):
    """Get order audit log / timeline."""
    order = get_order(order_id)
    if not order:
        return {"success": False, "message": f"Zamówienie {order_id} nie istnieje."}
    return {
        "success": True,
        "order_id": order_id,
        "current_status": order["status"],
        "current_status_label": order["status_label"],
        "timeline": order["history"],
        "purchase_orders": order.get("purchase_orders", []),
    }


# ── KPI & Cross-module Bridge ────────────────────────────────────────────

@buying_router.get("/buying/kpi")
def buying_kpi():
    """Aggregate order statistics for dashboard KPI cards."""
    # Try DB first
    try:
        from app.database import DB_AVAILABLE, _get_client, db_get_order_kpi
        if DB_AVAILABLE:
            client = _get_client()
            return {"success": True, **db_get_order_kpi(client)}
    except Exception:
        pass

    # Fallback: compute from in-memory orders
    all_orders = list_orders()
    by_status: dict[str, int] = {}
    total_spend = 0.0
    total_savings = 0.0
    total_items_ordered = 0
    for o in all_orders:
        st = o.get("status", "draft")
        by_status[st] = by_status.get(st, 0) + 1
        total_spend += o.get("total", 0)
        total_savings += o.get("savings_pln", 0) if o.get("savings_pln") else 0
        total_items_ordered += o.get("total_items", 0)

    total = len(all_orders)
    return {
        "success": True,
        "orders_total": total,
        "orders_by_status": {
            s: {"count": by_status.get(s, 0), "label": STATUS_LABELS[s]}
            for s in ORDER_STATUSES
        },
        "total_spend": round(total_spend, 2),
        "total_savings": round(total_savings, 2),
        "avg_order_value": round(total_spend / total, 2) if total else 0,
        "avg_savings_pct": round(total_savings / total_spend * 100, 2) if total_spend else 0,
        "total_items_ordered": total_items_ordered,
    }


@buying_router.post("/buying/open-in-optimizer")
def open_in_optimizer(req: CartRequest):
    """
    Bridge: map cart items to optimizer demand payload.

    Returns a ready-to-use payload for /api/v1/optimize (Tab 1).
    """
    raw = [{"id": i.id, "quantity": i.quantity} for i in req.items]
    cart_state = calculate_cart_state(raw)
    demand_by_domain = map_cart_to_demand(cart_state)

    domains = []
    for domain, demand_items in demand_by_domain.items():
        domains.append({
            "domain": domain,
            "demand": demand_items,
        })

    return {
        "success": True,
        "message": "Dane gotowe do optymalizacji w Tab 1.",
        "domains": domains,
        "cart_summary": {
            "subtotal": cart_state["subtotal"],
            "total_items": cart_state["total_items"],
        },
    }


# ── Approval Workflow API ──────────────────────────────────────────────────

from app.buying_engine import get_approval_policies, update_approval_policies, evaluate_approval


@buying_router.get(
    "/buying/approval-policies",
    summary="Get current approval workflow configuration",
    tags=["buying", "approval"],
)
def get_policies():
    """Return approval thresholds, category rules, item policies, and workflow mode."""
    return get_approval_policies()


@buying_router.put(
    "/buying/approval-policies",
    summary="Update approval workflow configuration",
    tags=["buying", "approval"],
)
def put_policies(body: dict = Body(...)):
    """
    Update approval workflow settings.

    Fields: workflow_mode, thresholds, category_rules, item_policies.
    Only provided fields are updated.
    """
    return update_approval_policies(body)


@buying_router.post(
    "/buying/evaluate-approval",
    summary="Evaluate approval requirements for a cart",
    tags=["buying", "approval"],
)
def post_evaluate_approval(req: CartRequest):
    """
    Given a cart, evaluate which approval rules apply.
    Returns approval level, required approvers, reasons, and chain.
    """
    cart_state = calculate_cart_state([item.model_dump() for item in req.items])
    return {
        "cart_summary": {
            "subtotal": cart_state["subtotal"],
            "total_items": cart_state["total_items"],
            "total": cart_state["total"],
        },
        "approval": cart_state.get("approval", {}),
    }


# ── CIF Upload + UNSPSC Classification ──────────────────────────────────

# UNSPSC keyword-to-code mapping for auto-classification
_UNSPSC_KEYWORDS: dict[str, tuple[str, str]] = {
    "hamulc": ("25101500", "Brake systems and components"),
    "brake": ("25101500", "Brake systems and components"),
    "klock": ("25101500", "Brake systems and components"),
    "tarcz": ("25101500", "Brake systems and components"),
    "zawieszeni": ("25101700", "Suspension system components"),
    "amortyz": ("25101700", "Suspension system components"),
    "suspension": ("25101700", "Suspension system components"),
    "wydech": ("25101900", "Exhaust system and emission controls"),
    "exhaust": ("25101900", "Exhaust system and emission controls"),
    "katalizator": ("25101900", "Exhaust system and emission controls"),
    "alternator": ("25102000", "Engine electrical system"),
    "rozrusznik": ("25102000", "Engine electrical system"),
    "starter": ("25102000", "Engine electrical system"),
    "cewk": ("25102000", "Engine electrical system"),
    "paliwow": ("25102100", "Fuel system and components"),
    "wtrysk": ("25102100", "Fuel system and components"),
    "injector": ("25102100", "Fuel system and components"),
    "fuel": ("25102100", "Fuel system and components"),
    "pomp": ("25102100", "Fuel system and components"),
    "chlodnic": ("25102200", "Cooling system and components"),
    "radiator": ("25102200", "Cooling system and components"),
    "termostat": ("25102200", "Cooling system and components"),
    "coolant": ("25102200", "Cooling system and components"),
    "sprzeg": ("25102500", "Transmission components"),
    "clutch": ("25102500", "Transmission components"),
    "skrzyni": ("25102500", "Transmission components"),
    "opon": ("25171500", "Tires"),
    "tire": ("25171500", "Tires"),
    "tyre": ("25171500", "Tires"),
    "felg": ("25171700", "Wheels and rims"),
    "wheel": ("25171700", "Wheels and rims"),
    "akumulat": ("25172000", "Batteries for vehicles"),
    "batter": ("25172000", "Batteries for vehicles"),
    "olej": ("15121500", "Lubricants and oils"),
    "oil": ("15121500", "Lubricants and oils"),
    "smar": ("15121900", "Greases"),
    "grease": ("15121900", "Greases"),
    "filtr": ("31162800", "Filters"),
    "filter": ("31162800", "Filters"),
    "uszczelk": ("31163100", "Gaskets and seals"),
    "gasket": ("31163100", "Gaskets and seals"),
    "seal": ("31163100", "Gaskets and seals"),
    "lozysk": ("31211500", "Bearings"),
    "bearing": ("31211500", "Bearings"),
    "kierownic": ("25101600", "Steering components"),
    "steering": ("25101600", "Steering components"),
    "swieca": ("25102000", "Engine electrical system"),
    "spark": ("25102000", "Engine electrical system"),
    "nadwozi": ("26101100", "Lighting fixtures / Bodywork"),
    "blotnik": ("26101100", "Lighting fixtures / Bodywork"),
    "zderzak": ("26101100", "Lighting fixtures / Bodywork"),
    "bumper": ("26101100", "Lighting fixtures / Bodywork"),
    "lampa": ("26101100", "Lighting fixtures / Bodywork"),
    "headlight": ("26101100", "Lighting fixtures / Bodywork"),
    "komputer": ("43211500", "Computers and servers"),
    "laptop": ("43211500", "Computers and servers"),
    "server": ("43211500", "Computers and servers"),
    "software": ("43211600", "Software licenses"),
    "licencj": ("43211600", "Software licenses"),
    "transport": ("78101800", "Freight services"),
    "freight": ("78101800", "Freight services"),
    "dostaw": ("78101800", "Freight services"),
    "opakow": ("24112400", "Packaging materials"),
    "packaging": ("24112400", "Packaging materials"),
    "karton": ("24112400", "Packaging materials"),
    "narzedz": ("27111700", "Hand tools"),
    "tool": ("27111700", "Hand tools"),
    "klucz": ("27111700", "Hand tools"),
}


def _classify_unspsc(name: str, description: str = "") -> tuple[str, str]:
    """Auto-classify product to UNSPSC code based on keywords in name/description."""
    text = (name + " " + description).lower()
    for keyword, (code, label) in _UNSPSC_KEYWORDS.items():
        if keyword in text:
            return code, label
    return "00000000", "Nieklasyfikowane"


@buying_router.post(
    "/cif/upload",
    summary="Upload CIF file — parse, classify UNSPSC, return items",
    tags=["buying"],
)
async def upload_cif(file: UploadFile = File(...)):
    """
    Upload a CIF (Catalogue Interchange Format) or CSV file.
    Parses rows, auto-classifies each item to UNSPSC code,
    and returns structured items with classification.
    No auth required (demo mode).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    # Strip CIF header lines (CIF_V3.0 format)
    lines = text.splitlines()
    data_start = 0
    data_end = len(lines)
    fieldnames_line = None
    cif_metadata: dict[str, str] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        upper = stripped.upper()

        # Parse CIF header key: value pairs
        if ":" in stripped and not upper.startswith("FIELDNAMES") and data_start == 0:
            key, _, val = stripped.partition(":")
            cif_metadata[key.strip().upper()] = val.strip()
            continue

        # FIELDNAMES line — strip prefix "FIELDNAMES:" or "FIELDNAMES\t"
        if upper.startswith("FIELDNAMES"):
            raw = stripped
            # Remove "FIELDNAMES" prefix (may have :, tab, or space separator)
            for sep in (":", "\t", " "):
                if "FIELDNAMES" + sep in raw or "FIELDNAMES" + sep.lower() in raw.upper():
                    raw = raw.split(sep, 1)[-1] if sep != " " else raw[len("FIELDNAMES"):].lstrip(": \t")
                    break
            else:
                raw = raw[len("FIELDNAMES"):].lstrip(": \t")

            # Detect delimiter in fieldnames (tab > semicolon > comma)
            if "\t" in raw:
                fieldnames_line = [f.strip() for f in raw.split("\t")]
            elif ";" in raw:
                fieldnames_line = [f.strip() for f in raw.split(";")]
            else:
                fieldnames_line = [f.strip() for f in raw.split(",")]
            fieldnames_line = [f for f in fieldnames_line if f and f.upper() != "FIELDNAMES"]
            continue

        if upper == "DATA":
            data_start = i + 1
            continue
        if upper in ("ENDOFDATA", "EOF"):
            data_end = i
            break

    # Extract data lines only (between DATA and ENDOFDATA)
    data_lines = [l for l in lines[data_start:data_end] if l.strip()]
    csv_text = "\n".join(data_lines)
    if not csv_text.strip():
        csv_text = text  # fallback to full text

    # Detect delimiter in data rows
    # Count delimiters in first data line (outside quotes)
    first_line = data_lines[0] if data_lines else ""
    tab_count = first_line.count("\t")
    semi_count = first_line.count(";")
    # For comma, we need to be smarter — count commas outside quotes
    comma_count = 0
    in_quote = False
    for ch in first_line:
        if ch == '"':
            in_quote = not in_quote
        elif ch == ',' and not in_quote:
            comma_count += 1

    if tab_count >= semi_count and tab_count >= comma_count and tab_count > 0:
        delimiter = "\t"
    elif semi_count >= comma_count and semi_count > 0:
        delimiter = ";"
    else:
        delimiter = ","

    if fieldnames_line:
        reader = csv.DictReader(io.StringIO(csv_text), fieldnames=fieldnames_line, delimiter=delimiter)
    else:
        reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

    items = []
    unspsc_stats: dict[str, int] = {}
    for i, row in enumerate(reader, 1):
        if not row:
            continue
        try:
            r = {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in row.items() if k}
            name = (r.get("name") or r.get("nazwa") or r.get("product_name")
                    or r.get("short_name") or r.get("item_description") or "")
            desc = (r.get("description") or r.get("opis") or r.get("long_name")
                    or r.get("item_description") or "")
            existing_unspsc = (r.get("unspsc_code") or r.get("unspsc")
                               or r.get("spsc_code") or r.get("classification_code") or "")

            if existing_unspsc and len(existing_unspsc) >= 8:
                unspsc_code = existing_unspsc
                unspsc_name = r.get("unspsc_name") or r.get("spsc_name") or ""
                classified_by = "cif"
            else:
                unspsc_code, unspsc_name = _classify_unspsc(name, desc)
                classified_by = "auto" if unspsc_code != "00000000" else "none"

            price_str = r.get("price") or r.get("cena") or r.get("unit_price") or r.get("unitprice") or "0"
            try:
                price = float(price_str.replace(",", ".").replace(" ", ""))
            except ValueError:
                price = 0.0

            item = {
                "row": i,
                "item_id": (r.get("item_id") or r.get("id") or r.get("sku")
                            or r.get("supplier_part_id") or r.get("manufacturer_part_id")
                            or r.get("supplier_id_aux") or f"CIF-{i:04d}"),
                "name": name,
                "description": desc,
                "price": price,
                "currency": r.get("currency") or r.get("waluta") or "PLN",
                "unit": (r.get("unit") or r.get("jm") or r.get("uom")
                         or r.get("unit_of_measure") or "szt"),
                "unspsc_code": unspsc_code,
                "unspsc_name": unspsc_name,
                "classified_by": classified_by,
                "manufacturer": r.get("manufacturer") or r.get("manufacturer_name") or r.get("producent") or "",
                "ean": r.get("ean") or r.get("gtin") or r.get("barcode") or "",
            }
            items.append(item)
            unspsc_stats[unspsc_code] = unspsc_stats.get(unspsc_code, 0) + 1
        except Exception as e:
            logger.warning("CIF row %d parse error: %s", i, e)
            continue

    # Build classification summary
    classification_summary = []
    for code, count in sorted(unspsc_stats.items(), key=lambda x: -x[1]):
        label = next((it["unspsc_name"] for it in items if it["unspsc_code"] == code), "")
        classification_summary.append({"unspsc_code": code, "unspsc_name": label, "count": count})

    auto_count = sum(1 for it in items if it["classified_by"] == "auto")
    cif_count = sum(1 for it in items if it["classified_by"] == "cif")
    none_count = sum(1 for it in items if it["classified_by"] == "none")

    return {
        "success": True,
        "filename": file.filename,
        "total_items": len(items),
        "classification": {
            "auto_classified": auto_count,
            "from_cif": cif_count,
            "unclassified": none_count,
            "categories": len(unspsc_stats),
        },
        "classification_summary": classification_summary,
        "items": items,
    }


# ── CIF Template Download ─────────────────────────────────────────────────

@buying_router.get(
    "/cif/template",
    summary="Download sample CIF template file",
    tags=["buying"],
)
def download_cif_template():
    """Serve the sample CIF V3.0 template file for download."""
    template_path = Path(__file__).resolve().parent.parent / "10 pozycji.cif"
    if not template_path.exists():
        return {"success": False, "message": "Plik szablonu CIF nie znaleziony."}
    return FileResponse(
        path=str(template_path),
        filename="szablon_cif.cif",
        media_type="application/octet-stream",
    )


# ── UNSPSC Search / AI Suggestion ─────────────────────────────────────────

# Extended UNSPSC catalog for search (code → label)
# Structure: Segment (2-digit) → Family (4-digit) → Class (6-digit) → Commodity (8-digit)
_UNSPSC_CATALOG: dict[str, str] = {}
for _kw, (_code, _label) in _UNSPSC_KEYWORDS.items():
    _UNSPSC_CATALOG[_code] = _label

# ── UNSPSC Level 1: Segments (2-digit) ──────────────────────────────────
_UNSPSC_SEGMENTS: dict[str, str] = {
    "10": "Rośliny i zwierzęta / Live plant and animal material",
    "11": "Surowce mineralne / Mineral and textile and inedible plant and animal materials",
    "12": "Chemikalia / Chemicals including bio chemicals and gas materials",
    "13": "Żywica i kalafonia / Resin and rosin and rubber and foam and film",
    "14": "Papier i tektura / Paper materials and products",
    "15": "Paliwa, smary i oleje / Fuels and fuel additives and lubricants",
    "20": "Sprzęt górniczy / Mining and well drilling machinery and accessories",
    "21": "Maszyny rolnicze / Farming and fishing and forestry and wildlife machinery",
    "22": "Maszyny budowlane / Building and construction machinery and accessories",
    "23": "Maszyny przemysłowe / Industrial and manufacturing machinery",
    "24": "Maszyny do transportu / Material handling and conditioning machinery",
    "25": "Pojazdy i akcesoria / Commercial and military and private vehicles",
    "26": "Sprzęt elektryczny / Power generation and distribution machinery",
    "27": "Narzędzia i osprzęt / Tools and general machinery",
    "30": "Elementy konstrukcyjne / Structural components and basic shapes",
    "31": "Elementy złączne i uszczelki / Bearings and bushings and wheels and gears",
    "32": "Komponenty elektroniczne / Electronic components and supplies",
    "39": "Lampy i oświetlenie / Lamps and lightbulbs and lamp components",
    "40": "Systemy dystrybucji i HVAC / Distribution and conditioning systems",
    "41": "Sprzęt laboratoryjny / Laboratory and measuring and testing equipment",
    "42": "Sprzęt medyczny / Medical equipment and accessories and supplies",
    "43": "Technologia IT / Information technology broadcasting and telecommunications",
    "44": "Materiały biurowe / Office equipment and accessories and supplies",
    "45": "Urządzenia drukujące / Printing and photographic and audio and visual equipment",
    "46": "Sprzęt obronny / Defense and law enforcement and security equipment",
    "47": "Środki czystości / Cleaning equipment and supplies",
    "48": "Sprzęt sportowy / Sport and recreational equipment and supplies",
    "49": "Meble / Furniture and furnishings",
    "50": "Żywność i napoje / Food beverage and tobacco products",
    "51": "Leki i farmaceutyki / Drugs and pharmaceutical products",
    "52": "Artykuły gospodarstwa dom. / Domestic appliances and supplies",
    "53": "Odzież i obuwie / Apparel and luggage and personal care products",
    "54": "Zegary i biżuteria / Timepieces and jewelry and gemstone products",
    "55": "Wydawnictwa / Published products",
    "56": "Zabawki i dekoracje / Toys and games and arts and crafts",
    "60": "Budynki i konstrukcje / Building and facility construction",
    "70": "Usługi rolnicze / Farming and fishing and forestry and wildlife services",
    "71": "Usługi górnicze / Mining and oil and gas services",
    "72": "Usługi budowlane / Building and facility construction and maintenance services",
    "73": "Usługi produkcyjne / Industrial production and manufacturing services",
    "76": "Usługi środowiskowe / Industrial cleaning services",
    "77": "Usługi środowiskowe / Environmental services",
    "78": "Usługi transportowe / Transportation and storage and mail services",
    "80": "Usługi zarządzania / Management and business professionals services",
    "81": "Usługi inżynieryjne / Engineering and research and technology services",
    "82": "Usługi redakcyjne / Editorial and design and graphic services",
    "83": "Usługi komunalne / Public utilities and public sector related services",
    "84": "Usługi finansowe / Financial and insurance services",
    "85": "Usługi zdrowotne / Healthcare services",
    "86": "Usługi edukacyjne / Education and training services",
    "90": "Usługi turystyczne / Travel and food and lodging and entertainment services",
    "91": "Usługi osobiste / Personal and domestic services",
    "92": "Usługi obronne / National defense and public order services",
    "93": "Usługi polityczne / Politics and civic affairs services",
    "94": "Organizacje i kluby / Organizations and clubs",
    "95": "Tereny i budynki / Land and buildings and structures and thoroughfares",
}

# ── UNSPSC Level 2: Families (4-digit) — kluczowe dla procurement ────────
_UNSPSC_FAMILIES: dict[str, str] = {
    # 15 — Paliwa, smary, oleje
    "1511": "Paliwa stałe / Solid fuels",
    "1512": "Paliwa ciekłe, oleje, smary / Fuels and lubricants and anti corrosive materials",
    "1513": "Paliwa gazowe / Fuel for nuclear reactors",
    # 23 — Maszyny przemysłowe
    "2310": "Maszyny produkcyjne / Industrial process machinery",
    "2311": "Maszyny obróbcze / Machining and turning and boring",
    "2312": "Maszyny pakujące / Packaging machinery",
    "2314": "Maszyny do obr. metalu / Metal cutting machinery",
    "2315": "Maszyny CNC / Turning and milling machinery",
    "2316": "Zgrzewarki i spawarki / Welding and soldering and brazing machinery",
    # 24 — Transport materiałów
    "2410": "Dźwigi i przenośniki / Cranes and fixed lifting equipment",
    "2411": "Kontenery i opakowania / Containers and storage",
    "2412": "Wózki widłowe / Industrial trucks",
    "2413": "Dźwignice / Lifting equipment",
    # 25 — Pojazdy
    "2510": "Pojazdy silnikowe / Motor vehicles",
    "2511": "Pojazdy morskie / Marine transport",
    "2512": "Pojazdy kolejowe / Railway and tramway machinery",
    "2513": "Pojazdy lotnicze / Aircraft",
    "2514": "Rowery / Non motorized cycles",
    "2517": "Akcesoria pojazdowe / Vehicle components and accessories",
    "2518": "Części pojazdu / Vehicle bodies and trailers",
    "2519": "Osprzęt transportowy / Transportation services equipment",
    # 26 — Elektryka i energetyka
    "2610": "Generatory i silniki / Power sources",
    "2611": "Akumulatory przemysłowe / Batteries and generators and kinetic power",
    "2612": "Przewody i kable / Electrical wire and cable and harness",
    "2613": "Aparatura łączeniowa / Electrical switchgear and accessories",
    "2614": "Transformatory / Power conversion equipment",
    # 27 — Narzędzia
    "2711": "Narzędzia ręczne / Hand tools",
    "2712": "Narzędzia elektryczne / Power tools",
    "2713": "Sprzęt spawalniczy / Welding and soldering equipment",
    # 30 — Elementy konstrukcyjne
    "3010": "Profile stalowe / Structural components",
    "3011": "Blachy / Plates and sheets",
    "3012": "Rury i kształtki / Pipe and tube",
    "3013": "Pręty i druty / Bars and rods and wire",
    "3014": "Odlewy / Castings and forgings",
    "3015": "Elementy złączne / Nuts and bolts and screws and studs",
    # 31 — Łożyska, uszczelki
    "3116": "Filtry i uszczelki / Filters",
    "3121": "Łożyska / Bearings and bushings and gears",
    "3122": "Koła zębate / Gears",
    "3123": "Łańcuchy / Chains",
    "3124": "Sprężyny / Springs",
    "3125": "Tuleje / Bushings",
    "3126": "Zasuwy i zawory / Valves",
    "3127": "Pierścienie / Rings and seals",
    "3128": "Kliny / Wedges and cams",
    "3129": "Paski napędowe / Belts and drives",
    "3131": "Wały i osie / Shafts and axles",
    "3132": "Sprzęgła / Clutches",
    "3133": "Koła / Wheels and casters",
    # 32 — Elektronika
    "3210": "Półprzewodniki / Printed circuits and integrated circuits",
    "3211": "Diody i tranzystory / Discrete semiconductor devices",
    "3212": "Wyroby pasywne / Passive discrete components",
    "3213": "Przewody elektroniczne / Electronic hardware and component parts",
    # 39 — Oświetlenie
    "3910": "Lampy / Lamps and lightbulbs",
    "3911": "Oprawy oświetleniowe / Lighting fixtures",
    "3912": "Oświetlenie zewnętrzne / Exterior lighting fixtures and accessories",
    # 40 — Systemy HVAC i instalacje
    "4010": "Ogrzewanie / Heating equipment",
    "4011": "Klimatyzacja / Cooling equipment",
    "4012": "Wentylacja / Ventilation equipment",
    "4013": "Dystryb. ciepła / Fluid and gas distribution",
    "4014": "Pompy / Pumps and compressors",
    "4015": "Instalacje wod-kan / Plumbing fixtures",
    # 41 — Sprzęt pomiarowy
    "4110": "Aparatura pomiarowa / Laboratory instruments",
    "4111": "Przyrządy pomiarowe / Measuring and observing instruments",
    "4112": "Sprzęt testowy / Analyzers and testers",
    # 43 — IT i telekomunikacja
    "4320": "Sprzęt sieciowy / Components for information technology",
    "4321": "Komputery / Computer equipment and accessories",
    "4322": "Urządzenia peryferyjne / Data input and output and storage devices",
    "4323": "Oprogramowanie / Software",
    "4324": "Telefonia / Telephone equipment",
    "4325": "Systemy telekomunikacyjne / Communications devices and accessories",
    "4326": "Sieć / Network infrastructure",
    "4331": "Okablowanie sieciowe / Network cabling",
    "4332": "Multimedia / Multimedia equipment",
    "4333": "Sprzęt nadawczy / Broadcasting equipment",
    # 44 — Biuro
    "4410": "Materiały eksploatacyjne / Office machines and accessories",
    "4411": "Artykuły biurowe / Office supplies",
    "4412": "Papier i piśmiennictwo / Office and desk accessories",
    "4413": "Kalendarze / Mail and desk supplies",
    # 45 — Druk i foto
    "4510": "Sprzęt drukujący / Printing and publishing equipment",
    "4511": "Sprzęt audio-video / Audio and visual equipment",
    "4512": "Sprzęt fotograficzny / Photographic equipment",
    # 46 — Ochrona i BHP
    "4610": "Broń / Weapons",
    "4611": "Amunicja / Ammunition",
    "4617": "Odzież ochronna / Safety apparel",
    "4618": "Sprzęt BHP / Personal safety and protection",
    "4619": "Systemy gaśnicze / Fire protection equipment",
    "4620": "Systemy zabezpieczeń / Locks and security hardware",
    "4621": "Monitoring / Surveillance and detection equipment",
    # 47 — Środki czystości
    "4713": "Środki czystości / Cleaning and janitorial supplies",
    "4714": "Urządzenia czyszczące / Floor care machines",
    # 48 — Sport
    "4810": "Sprzęt sportowy / Sports equipment",
    "4811": "Sprzęt fitness / Fitness equipment",
    # 49 — Meble
    "4910": "Meble biurowe / Accommodation furniture",
    "4911": "Siedziska / Seating",
    "4912": "Krzesła i stoliki / Furniture and furnishings",
    # 50 — Żywność
    "5010": "Warzywa i owoce / Fresh vegetables",
    "5011": "Mięso / Meat and poultry products",
    "5013": "Napoje / Beverages",
    "5020": "Pieczywo / Baked goods",
    # 52 — AGD
    "5210": "Sprzęt AGD / Floor care appliances",
    "5211": "Sprzęt kuchenny / Kitchen appliances",
    # 53 — Odzież
    "5310": "Odzież / Clothing",
    "5311": "Obuwie / Footwear",
    "5312": "Bagaż / Luggage and handbags",
    # 55 — Wydawnictwa
    "5510": "Druki / Printed media",
    "5511": "Publikacje elektroniczne / Electronic reference material",
    # 60 — Budowa
    "6010": "Budynki prefabrykowane / Prefabricated buildings and structures",
    "6011": "Materiały betonowe / Concrete and cement and plaster",
    "6012": "Drewno budowlane / Building timber and lumber",
    "6013": "Materiały dachowe / Roofing materials",
    "6014": "Szkło budowlane / Glass",
    "6015": "Drzwi i okna / Doors and windows",
    "6016": "Materiały izolacyjne / Insulation",
    # 72 — Usługi budowlane
    "7210": "Budowa budynków / Building construction services",
    "7211": "Budowa dróg / Heavy construction services",
    "7212": "Instalacje / Building installation services",
    "7213": "Wykończenie / Building completion services",
    "7214": "Utrzymanie budynków / Building maintenance services",
    "7215": "Zarządzanie nieruchomościami / Facility management services",
    # 73 — Usługi produkcyjne
    "7310": "Obróbka metali / Metal treatment services",
    "7311": "Galwanizacja / Coating and plating services",
    "7312": "Usługi obróbki cieplnej / Heat treatment services",
    # 76 — Sprzątanie przemysłowe
    "7610": "Sprzątanie / Decontamination services",
    "7611": "Utylizacja / Refuse disposal and treatment",
    "7612": "Czyszczenie przemysłowe / Industrial cleaning services",
    # 77 — Środowisko
    "7710": "Ochrona środowiska / Environmental management",
    "7711": "Oczyszczanie / Pollution tracking and clean up services",
    "7712": "Rekultywacja / Environmental remediation",
    # 78 — Transport i logistyka
    "7810": "Transport drogowy / Mail and cargo transport",
    "7811": "Transport morski / Passenger transport",
    "7812": "Magazynowanie / Material packing and handling",
    "7813": "Przechowywanie / Storage",
    "7814": "Transport lotniczy / Air cargo transport",
    # 80 — Zarządzanie i konsulting
    "8010": "Usługi doradcze / Management advisory services",
    "8011": "Usługi HR / Human resources services",
    "8012": "Usługi prawne / Legal services",
    "8013": "Usługi marketingowe / Marketing and distribution",
    "8014": "Usługi handlowe / Trade policy and services",
    "8015": "Usługi logistyczne / Fleet management and maintenance",
    "8016": "Zarządzanie operacyjne / Management services",
    # 81 — Inżynieria i R&D
    "8110": "Usługi inżynierskie / Professional engineering services",
    "8111": "Usługi IT / Computer services",
    "8112": "Usługi badawcze / Economic analysis",
    "8114": "Usługi testowe / Quality control",
    "8115": "Kontrola jakości / Earth science services",
    "8116": "Usługi techniczne / Technical services",
    # 82 — Usługi graficzne i drukarskie
    "8210": "Reklama / Advertising",
    "8211": "Druk / Writing and translations",
    "8212": "Usługi fotograficzne / Photographic services",
    "8213": "Grafika / Graphic design",
    # 83 — Media i komunalne
    "8310": "Elektryczność / Water and sewer utilities",
    "8311": "Gaz / Gas utilities",
    "8312": "Telekomunikacja / Telecommunications media services",
    # 84 — Finanse i ubezpieczenia
    "8410": "Bankowość / Banking and investment",
    "8411": "Ubezpieczenia / Insurance and retirement services",
    "8412": "Księgowość / Accounting and auditing",
    "8413": "Podatki / Tax services",
    # 85 — Usługi zdrowotne
    "8510": "Usługi medyczne / Healthcare provider services",
    "8511": "Stomatologia / Dental services",
    # 86 — Edukacja
    "8610": "Szkolenia / Vocational training",
    "8611": "Edukacja alternatywna / Alternative educational systems",
    "8612": "Szkolnictwo wyższe / Educational institutions",
    # 90 — Turystyka
    "9010": "Hotele / Hotels and lodging",
    "9011": "Restauracje / Restaurants and catering",
    "9012": "Podróże / Travel agencies",
    "9013": "Eventy / Performing arts",
    "9014": "Rozrywka / Recreational services",
    "9015": "Atrakcje / Amusement parks",
}

_UNSPSC_CATALOG.update(_UNSPSC_SEGMENTS)
_UNSPSC_CATALOG.update(_UNSPSC_FAMILIES)

# ── UNSPSC Level 3: Classes (6-digit) ────────────────────────────────────
_UNSPSC_CLASSES: dict[str, str] = {
    # 15 — Paliwa, smary, oleje
    "151115": "Paliwa stałe / Coal and fuel wood",
    "151210": "Paliwa płynne / Petroleum and distillates",
    "151215": "Oleje smarowe / Lubricating oils and greases",
    "151219": "Smary specjalne / Specialty lubricants",
    "151220": "Płyny chłodnicze / Anti freeze and de icing materials",
    "151225": "Paliwa gazowe / Gaseous fuels",
    # 23 — Maszyny przemysłowe
    "231010": "Piece przemysłowe / Industrial ovens and furnaces",
    "231015": "Suszarki / Drying equipment",
    "231110": "Tokarki / Lathes",
    "231115": "Frezarki / Milling equipment",
    "231120": "Wiertarki / Drilling machines",
    "231210": "Maszyny pakujące / Packaging machinery",
    "231410": "Prasy / Presses",
    "231415": "Walcarki / Rolling machines",
    "231510": "Obrabiarki CNC / CNC machining centers",
    "231610": "Spawarki łukowe / Arc welding equipment",
    "231615": "Spawarki MIG/TIG / Gas welding equipment",
    "231620": "Lutownice / Soldering equipment",
    # 24 — Transport materiałów i opakowania
    "241010": "Suwnice / Overhead traveling cranes",
    "241015": "Żurawie / Boom cranes",
    "241110": "Kontenery / Freight containers",
    "241115": "Zbiorniki / Tanks and cylinders",
    "241120": "Kosze i pojemniki / Bins and baskets",
    "241124": "Opakowania kartonowe / Corrugated boxes and containers",
    "241125": "Opakowania foliowe / Bags and sacks",
    "241210": "Wózki paletowe / Pallet trucks",
    "241215": "Wózki widłowe elektryczne / Powered lift trucks",
    "241220": "Wózki ręczne / Hand trucks and dollies",
    # 25 — Pojazdy i akcesoria
    "251010": "Samochody osobowe / Passenger motor vehicles",
    "251012": "Samochody dostawcze / Light trucks and vans",
    "251015": "Układy hamulcowe / Brake systems and components",
    "251016": "Układy kierownicze / Steering systems",
    "251017": "Układy zawieszenia / Suspension systems",
    "251018": "Układy przeniesienia napędu / Power train systems",
    "251019": "Układy wydechowe / Exhaust systems and components",
    "251020": "Elektryka silnikowa / Engine electrical systems",
    "251021": "Układy paliwowe / Fuel systems",
    "251022": "Układy chłodzenia / Cooling systems",
    "251025": "Przekładnie i sprzęgła / Transmission components",
    "251030": "Pojazdy ciężarowe / Heavy trucks",
    "251040": "Autobusy / Buses",
    "251110": "Łodzie / Motorboats",
    "251115": "Statki / Ships",
    "251210": "Lokomotywy / Locomotives",
    "251215": "Wagony / Railway wagons",
    "251310": "Samoloty / Fixed wing aircraft",
    "251315": "Helikoptery / Rotary wing aircraft",
    "251410": "Rowery / Bicycles",
    "251710": "Części nadwoziowe / Vehicle body components",
    "251715": "Opony / Tires",
    "251717": "Felgi / Wheels and rims",
    "251720": "Akumulatory / Vehicle batteries",
    "251725": "Oświetlenie pojazdów / Vehicle lighting",
    "251730": "Szyby samochodowe / Vehicle windows",
    "251735": "Wyposażenie wnętrza / Interior trim parts",
    "251740": "Filtry pojazdowe / Vehicle filters",
    "251745": "Paski i łańcuchy napędowe / Vehicle belts and chains",
    "251810": "Przyczepy / Trailers",
    "251815": "Naczepy / Semi-trailers",
    "251910": "Sygnalizacja i BRD / Traffic control equipment",
    # 26 — Elektryka i energetyka
    "261010": "Silniki elektryczne / Electric motors",
    "261011": "Oprawy oświetleniowe / Lighting fixtures",
    "261015": "Generatory / Generators",
    "261020": "Turbiny / Turbines",
    "261110": "Akumulatory kwasowe / Lead acid batteries",
    "261115": "Akumulatory litowe / Lithium batteries",
    "261120": "Ogniwa paliwowe / Fuel cells",
    "261210": "Przewody miedziane / Copper wire",
    "261215": "Kable siłowe / Power cables",
    "261220": "Wiązki kablowe / Wire harnesses",
    "261310": "Wyłączniki / Circuit breakers",
    "261315": "Bezpieczniki / Fuses",
    "261320": "Rozdzielnice / Switchboards and panelboards",
    "261325": "Gniazda i wtyczki / Electrical receptacles and plugs",
    "261410": "Transformatory mocy / Power transformers",
    "261415": "Prostowniki / Rectifiers and inverters",
    "261420": "UPS / Uninterruptible power supplies",
    # 27 — Narzędzia
    "271110": "Klucze / Wrenches and spanners",
    "271115": "Śrubokręty / Screwdrivers",
    "271120": "Szczypce i obcęgi / Pliers and wire cutters",
    "271125": "Młotki / Hammers",
    "271130": "Piły ręczne / Hand saws",
    "271135": "Narzędzia pomiarowe / Measuring tools",
    "271140": "Nożyce / Scissors and shears",
    "271210": "Wiertarki elektryczne / Power drills",
    "271215": "Szlifierki / Grinders and polishers",
    "271220": "Piły mechaniczne / Power saws",
    "271225": "Wkrętarki / Power screwdrivers",
    "271230": "Frezarki ręczne / Routers",
    "271310": "Palniki / Blowtorches",
    "271315": "Reduktory gazowe / Gas regulators",
    # 30 — Elementy konstrukcyjne
    "301010": "Kątowniki i ceowniki / Angles and channels",
    "301015": "Dwuteowniki / I-beams and H-beams",
    "301020": "Profile zamknięte / Hollow sections",
    "301110": "Blachy stalowe / Steel plates and sheets",
    "301115": "Blachy aluminiowe / Aluminum sheets",
    "301120": "Blachy nierdzewne / Stainless steel sheets",
    "301210": "Rury stalowe / Steel pipes",
    "301215": "Rury miedziane / Copper pipes",
    "301220": "Rury PVC / PVC pipes",
    "301225": "Złączki rurowe / Pipe fittings",
    "301310": "Pręty stalowe / Steel bars and rods",
    "301315": "Druty / Wire",
    "301410": "Odlewy żeliwne / Cast iron castings",
    "301415": "Odlewy aluminiowe / Aluminum castings",
    "301420": "Odkuwki / Forgings",
    "301510": "Śruby / Bolts",
    "301515": "Nakrętki / Nuts",
    "301520": "Podkładki / Washers",
    "301525": "Wkręty / Screws",
    "301530": "Nity / Rivets",
    "301535": "Kołki / Pins and dowels",
    # 31 — Łożyska, uszczelki, filtry
    "311610": "Filtry powietrza / Air filters",
    "311615": "Filtry oleju / Oil filters",
    "311620": "Filtry paliwa / Fuel filters",
    "311625": "Filtry hydrauliczne / Hydraulic filters",
    "311628": "Filtry kabinowe / Cabin air filters",
    "311630": "Filtry wodne / Water filters",
    "311631": "Uszczelki płaskie / Flat gaskets",
    "311635": "O-ringi / O-rings",
    "312110": "Łożyska kulkowe / Ball bearings",
    "312115": "Łożyska wałeczkowe / Roller bearings",
    "312120": "Łożyska igiełkowe / Needle bearings",
    "312125": "Łożyska oporowe / Thrust bearings",
    "312210": "Koła zębate walcowe / Spur gears",
    "312215": "Koła zębate stożkowe / Bevel gears",
    "312220": "Przekładnie ślimakowe / Worm gears",
    "312310": "Łańcuchy rolkowe / Roller chains",
    "312315": "Łańcuchy dźwigowe / Lifting chains",
    "312410": "Sprężyny naciskowe / Compression springs",
    "312415": "Sprężyny rozciągane / Extension springs",
    "312420": "Sprężyny piórowe / Leaf springs",
    "312510": "Tuleje ślizgowe / Sliding bushings",
    "312515": "Tuleje gumowo-metalowe / Rubber-metal bushings",
    "312610": "Zawory kulowe / Ball valves",
    "312615": "Zawory zwrotne / Check valves",
    "312620": "Zawory regulacyjne / Control valves",
    "312625": "Zawory bezpieczeństwa / Safety valves",
    "312710": "Pierścienie tłokowe / Piston rings",
    "312715": "Pierścienie uszczelniające / Sealing rings",
    "312810": "Kliny napędowe / Drive wedges",
    "312910": "Paski klinowe / V-belts",
    "312915": "Paski wieloklinowe / Poly-V belts",
    "312920": "Paski zębate / Timing belts",
    "313110": "Wały napędowe / Drive shafts",
    "313115": "Wały korbowe / Crankshafts",
    "313120": "Wały rozrządu / Camshafts",
    "313210": "Sprzęgła cierne / Friction clutches",
    "313215": "Sprzęgła hydrauliczne / Hydraulic clutches",
    "313310": "Koła jezdne / Running wheels",
    "313315": "Rolki / Rollers and casters",
    # 32 — Elektronika
    "321010": "Płytki PCB / Printed circuit boards",
    "321015": "Układy scalone / Integrated circuits",
    "321020": "Mikroprocesory / Microprocessors",
    "321110": "Diody / Diodes",
    "321115": "Tranzystory / Transistors",
    "321120": "Tyrystory / Thyristors",
    "321210": "Rezystory / Resistors",
    "321215": "Kondensatory / Capacitors",
    "321220": "Cewki indukcyjne / Inductors",
    "321310": "Złącza elektroniczne / Electronic connectors",
    "321315": "Radiatory / Heat sinks",
    # 39 — Oświetlenie
    "391010": "Żarówki / Incandescent lamps",
    "391015": "Świetlówki / Fluorescent lamps",
    "391020": "LED / Light emitting diodes",
    "391025": "Żarówki halogenowe / Halogen lamps",
    "391110": "Oprawy wewnętrzne / Interior fixtures",
    "391115": "Oprawy przemysłowe / Industrial fixtures",
    "391210": "Lampy uliczne / Street lights",
    "391215": "Lampy ogrodowe / Garden lights",
    # 40 — Instalacje HVAC
    "401010": "Kotły grzewcze / Heating boilers",
    "401015": "Grzejniki / Radiators and convectors",
    "401020": "Pompy ciepła / Heat pumps",
    "401110": "Klimatyzatory / Air conditioners",
    "401115": "Chillery / Chillers",
    "401210": "Wentylatory / Fans and blowers",
    "401215": "Centrale wentylacyjne / Air handling units",
    "401310": "Rury grzewcze / Heating pipes",
    "401315": "Armatura / Pipe fittings and valves",
    "401410": "Pompy wodne / Water pumps",
    "401415": "Sprężarki / Compressors",
    "401510": "Baterie łazienkowe / Bathroom faucets",
    "401515": "Toalety / Toilets and urinals",
    "401520": "Umywalki / Sinks and basins",
    # 41 — Sprzęt pomiarowy i laboratoryjny
    "411010": "Mikroskopy / Microscopes",
    "411015": "Pipety / Pipettes",
    "411020": "Inkubatory / Incubators",
    "411110": "Termometry / Thermometers",
    "411115": "Manometry / Pressure gauges",
    "411120": "Przepływomierze / Flow meters",
    "411125": "Wagi / Scales and balances",
    "411130": "Mierniki elektryczne / Electrical meters",
    "411210": "Analizatory chemiczne / Chemical analyzers",
    "411215": "Spektrometry / Spectrometers",
    "411220": "Chromatografy / Chromatographs",
    # 43 — IT i telekomunikacja
    "432010": "Pamięci RAM / Computer memory",
    "432015": "Procesory / Computer processors",
    "432020": "Płyty główne / Motherboards",
    "432025": "Karty graficzne / Graphics cards",
    "432110": "Komputery stacjonarne / Desktop computers",
    "432115": "Laptopy / Notebook computers",
    "432116": "Stacje dokujące / Docking stations",
    "432117": "Tablety / Tablet computers",
    "432120": "Serwery / Computer servers",
    "432125": "Stacje robocze / Workstations",
    "432210": "Drukarki / Printers",
    "432215": "Skanery / Scanners",
    "432220": "Dyski twarde / Hard disk drives",
    "432225": "Dyski SSD / Solid state drives",
    "432226": "Pamięci USB / USB flash drives",
    "432230": "Napędy optyczne / Optical drives",
    "432235": "Taśmy archiwizacyjne / Backup tapes",
    "432240": "Macierze dyskowe / Disk arrays",
    "432310": "Systemy operacyjne / Operating system software",
    "432315": "Oprogramowanie biurowe / Office suite software",
    "432320": "Oprogramowanie bazodanowe / Database software",
    "432325": "Oprogramowanie ERP / ERP software",
    "432330": "Oprogramowanie bezpieczeństwa / Security software",
    "432335": "Oprogramowanie programistyczne / Development tools",
    "432340": "Oprogramowanie graficzne / Graphics software",
    "432345": "Oprogramowanie CAD/CAM / CAD CAM software",
    "432410": "Telefony stacjonarne / Corded telephones",
    "432415": "Telefony VoIP / VoIP phones",
    "432420": "Centrale telefoniczne / PBX systems",
    "432510": "Smartfony / Smartphones",
    "432515": "Radiotelefony / Two way radios",
    "432610": "Routery / Routers",
    "432615": "Switche / Network switches",
    "432620": "Firewalle / Firewalls",
    "432625": "Access pointy / Wireless access points",
    "432630": "Modemy / Modems",
    "433110": "Kable sieciowe / Network cables",
    "433115": "Kable światłowodowe / Fiber optic cables",
    "433120": "Panele krosowe / Patch panels",
    "433210": "Projektory / Projectors",
    "433215": "Ekrany projekcyjne / Projection screens",
    "433220": "Kamery internetowe / Web cameras",
    "433225": "Zestawy wideokonferencyjne / Video conferencing equipment",
    "433310": "Mikrofony / Microphones",
    "433315": "Głośniki / Speakers",
    "433320": "Słuchawki / Headsets",
    # 44 — Materiały biurowe
    "441010": "Kopiarki / Copiers",
    "441015": "Niszczarki / Paper shredders",
    "441020": "Laminatory / Laminators",
    "441025": "Bindownice / Binding machines",
    "441030": "Tonery i tusze / Toner and ink cartridges",
    "441110": "Organizery biurkowe / Desk organizers",
    "441115": "Pojemniki na dokumenty / File folders and sorters",
    "441120": "Tablice / Boards and easels",
    "441125": "Kalkulatory / Calculators",
    "441210": "Papier ksero / Copy paper",
    "441215": "Papier do drukarek / Printer paper",
    "441220": "Koperty / Envelopes",
    "441225": "Etykiety / Labels and stickers",
    "441230": "Długopisy / Pens",
    "441235": "Ołówki / Pencils",
    "441240": "Markery / Markers and highlighters",
    "441245": "Korektory / Correction supplies",
    "441250": "Zszywacze / Staplers",
    "441255": "Dziurkacze / Hole punches",
    "441260": "Spinacze / Paper clips and binder clips",
    "441265": "Taśmy klejące / Adhesive tapes",
    "441310": "Kalendarze / Calendars",
    "441315": "Notesy i zeszyty / Notebooks and notepads",
    # 46 — BHP i ochrona
    "461710": "Kaski ochronne / Safety helmets",
    "461715": "Okulary ochronne / Safety glasses",
    "461720": "Rękawice ochronne / Protective gloves",
    "461725": "Obuwie ochronne / Safety footwear",
    "461730": "Odzież odblaskowa / High visibility clothing",
    "461735": "Kombinezony / Coveralls",
    "461810": "Szelki bezpieczeństwa / Safety harnesses",
    "461815": "Ochronniki słuchu / Ear protection",
    "461820": "Maski ochronne / Respiratory protection",
    "461825": "Apteczki / First aid kits",
    "461910": "Gaśnice / Fire extinguishers",
    "461915": "Czujniki dymu / Smoke detectors",
    "461920": "Hydranty / Fire hydrants",
    "461925": "Systemy tryskaczowe / Sprinkler systems",
    "462010": "Kłódki / Padlocks",
    "462015": "Zamki / Door locks",
    "462020": "Sejfy / Safes",
    "462110": "Kamery CCTV / CCTV cameras",
    "462115": "Systemy alarmowe / Alarm systems",
    "462120": "Kontrola dostępu / Access control systems",
    "462125": "Domofony / Intercom systems",
    # 47 — Środki czystości
    "471310": "Detergenty / Cleaning detergents",
    "471315": "Środki dezynfekujące / Disinfectants",
    "471320": "Ręczniki papierowe / Paper towels",
    "471325": "Papier toaletowy / Toilet paper",
    "471330": "Worki na śmieci / Trash bags",
    "471335": "Mopy i wiadra / Mops and buckets",
    "471340": "Szczotki / Brooms and brushes",
    "471410": "Odkurzacze / Vacuum cleaners",
    "471415": "Szorowarki / Floor scrubbers",
    "471420": "Myjki ciśnieniowe / Pressure washers",
    # 49 — Meble
    "491010": "Biurka / Desks",
    "491015": "Szafy biurowe / Office cabinets",
    "491020": "Regały / Shelving and storage",
    "491025": "Stoły konferencyjne / Conference tables",
    "491110": "Krzesła biurowe / Office chairs",
    "491115": "Fotele / Armchairs",
    "491120": "Sofy / Sofas",
    "491210": "Meble kuchenne / Kitchen furniture",
    "491215": "Meble socjalne / Break room furniture",
    # 60 — Materiały budowlane
    "601010": "Budynki modułowe / Modular buildings",
    "601110": "Beton / Concrete",
    "601115": "Cement / Cement",
    "601120": "Gips / Plaster and gypsum",
    "601210": "Drewno konstrukcyjne / Structural timber",
    "601215": "Sklejka / Plywood",
    "601220": "Płyty OSB / OSB panels",
    "601310": "Dachówki / Roof tiles",
    "601315": "Blachodachówka / Metal roofing",
    "601320": "Papa / Roofing felt",
    "601410": "Szkło płaskie / Flat glass",
    "601415": "Szyby zespolone / Insulated glass",
    "601510": "Drzwi wewnętrzne / Interior doors",
    "601515": "Drzwi zewnętrzne / Exterior doors",
    "601520": "Okna PVC / PVC windows",
    "601525": "Okna aluminiowe / Aluminum windows",
    "601610": "Styropian / Polystyrene insulation",
    "601615": "Wełna mineralna / Mineral wool insulation",
    "601620": "Pianka PUR / Polyurethane foam insulation",
    # 72 — Usługi budowlane i facility
    "721010": "Budowa obiektów / Building construction",
    "721015": "Remonty / Renovation services",
    "721110": "Budowa dróg / Road construction",
    "721115": "Budowa mostów / Bridge construction",
    "721210": "Instalacje elektryczne / Electrical installation",
    "721215": "Instalacje wod-kan / Plumbing installation",
    "721220": "Instalacje HVAC / HVAC installation",
    "721225": "Instalacje gazowe / Gas installation",
    "721310": "Malowanie / Painting services",
    "721315": "Posadzki / Flooring services",
    "721320": "Tynkowanie / Plastering services",
    "721410": "Konserwacja budynków / Building maintenance",
    "721415": "Sprzątanie budynków / Building cleaning services",
    "721510": "Zarządzanie nieruchomościami / Property management",
    "721515": "Ochrona obiektów / Building security services",
    # 78 — Transport i logistyka
    "781010": "Transport drogowy / Road freight transport",
    "781015": "Transport ekspresowy / Express delivery services",
    "781018": "Spedycja / Freight forwarding services",
    "781020": "Transport międzynarodowy / International freight",
    "781110": "Transport pasażerski / Passenger transport",
    "781115": "Wynajem pojazdów / Vehicle rental",
    "781210": "Pakowanie / Packing services",
    "781215": "Paletyzacja / Palletizing services",
    "781310": "Magazynowanie / Warehousing services",
    "781315": "Magazyny chłodnicze / Cold storage",
    "781410": "Fracht lotniczy / Air freight",
    "781415": "Fracht morski / Ocean freight",
    # 80 — Zarządzanie i konsulting
    "801010": "Doradztwo strategiczne / Strategic planning consultancy",
    "801015": "Doradztwo organizacyjne / Business process consultancy",
    "801020": "Doradztwo finansowe / Financial advisory",
    "801110": "Rekrutacja / Recruitment services",
    "801115": "Szkolenia pracownicze / Staff training services",
    "801120": "Outsourcing HR / HR outsourcing",
    "801125": "Wynagrodzenia / Payroll services",
    "801210": "Usługi prawne korporacyjne / Corporate legal services",
    "801215": "Usługi prawne compliance / Compliance advisory",
    "801310": "Badania rynku / Market research",
    "801315": "Reklama / Advertising services",
    "801320": "PR / Public relations",
    "801325": "Marketing cyfrowy / Digital marketing",
    "801510": "Zarządzanie flotą / Fleet management",
    "801515": "Leasing pojazdów / Vehicle leasing",
    "801610": "Zarządzanie projektami / Project management",
    "801615": "Zarządzanie zmianą / Change management",
    # 81 — Inżynieria i IT
    "811010": "Projektowanie mechaniczne / Mechanical engineering",
    "811015": "Projektowanie elektryczne / Electrical engineering",
    "811020": "Projektowanie budowlane / Civil engineering",
    "811110": "Usługi programistyczne / Software development",
    "811115": "Administracja IT / IT administration",
    "811120": "Wsparcie techniczne / IT support",
    "811125": "Hosting i chmura / Hosting and cloud services",
    "811130": "Cyberbezpieczeństwo / Cybersecurity services",
    "811135": "Wdrożenia ERP / ERP implementation",
    "811140": "Analiza danych / Data analytics services",
    "811210": "Badania ekonomiczne / Economic research",
    "811215": "Badania technologiczne / Technology research",
    "811410": "Audyt jakości / Quality auditing",
    "811415": "Certyfikacja / Certification services",
    "811510": "Badania geologiczne / Geological services",
    "811610": "Testowanie materiałów / Material testing",
    "811615": "Kalibracja / Calibration services",
    # 84 — Finanse i ubezpieczenia
    "841010": "Usługi bankowe / Banking services",
    "841015": "Kredyty / Lending services",
    "841020": "Faktoring / Factoring services",
    "841025": "Usługi płatnicze / Payment services",
    "841110": "Ubezpieczenia majątkowe / Property insurance",
    "841115": "Ubezpieczenia komunikacyjne / Vehicle insurance",
    "841120": "Ubezpieczenia grupowe / Group insurance",
    "841125": "Ubezpieczenia OC / Liability insurance",
    "841210": "Księgowość / Accounting services",
    "841215": "Audyt finansowy / Financial auditing",
    "841310": "Doradztwo podatkowe / Tax advisory",
    "841315": "Rozliczenia podatkowe / Tax filing services",
}

_UNSPSC_CATALOG.update(_UNSPSC_CLASSES)

# Add extra commodity-level codes not in keyword dict
_UNSPSC_CATALOG.update({
    "25101500": "Hamulce / Brake systems and components",
    "25101600": "Układ kierowniczy / Steering components",
    "25101700": "Zawieszenie / Suspension system components",
    "25101900": "Układ wydechowy / Exhaust system and emission controls",
    "25102000": "Elektryka silnika / Engine electrical system",
    "25102100": "Układ paliwowy / Fuel system and components",
    "25102200": "Układ chłodzenia / Cooling system and components",
    "25102500": "Układ napędowy / Transmission components",
    "25171500": "Opony / Tires",
    "25171700": "Felgi / Wheels and rims",
    "25172000": "Akumulatory / Batteries for vehicles",
    "15121500": "Oleje i smary / Lubricants and oils",
    "15121900": "Smary / Greases",
    "31162800": "Filtry / Filters",
    "31163100": "Uszczelki / Gaskets and seals",
    "31211500": "Łożyska / Bearings",
    "26101100": "Nadwozie i oświetlenie / Bodywork and lighting",
    "43211500": "Komputery i serwery / Computers and servers",
    "43211600": "Oprogramowanie / Software licenses",
    "43211602": "Stacje dokujące / Docking stations",
    "43211708": "Urządzenia wskazujące / Pointing devices",
    "43211711": "Klawiatury / Keyboards",
    "43211908": "Monitory / Monitors and displays",
    "43222609": "Huby USB / USB hubs",
    "44103103": "Tonery / Toner cartridges",
    "44111509": "Organizery biurowe / Desk organizers",
    "44121618": "Papier biurowy / Copy paper",
    "44121706": "Ołówki / Pencils",
    "44121708": "Długopisy / Pens",
    "78101800": "Transport / Freight services",
    "24112400": "Opakowania / Packaging materials",
    "27111700": "Narzędzia ręczne / Hand tools",
})


@buying_router.get(
    "/unspsc/search",
    summary="Search UNSPSC codes by keyword or code",
    tags=["buying"],
)
def search_unspsc(q: str = Query("", min_length=1)):
    """
    Search UNSPSC catalog by keyword (Polish or English) or code prefix.

    Returns matching UNSPSC entries sorted by relevance.
    Results include hierarchy level (segment/family/class/commodity).
    Also runs keyword-based AI suggestion from the query text.
    """
    query = q.strip().lower()
    seen_codes: set[str] = set()
    results = []

    # Normalize Polish diacritics for fuzzy matching
    _PL_NORM = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

    def _normalize(text: str) -> str:
        return text.lower().translate(_PL_NORM)

    query_norm = _normalize(query)

    def _level(code: str) -> str:
        n = len(code)
        if n <= 2:
            return "segment"
        elif n <= 4:
            return "family"
        elif n <= 6:
            return "class"
        return "commodity"

    def _add(code: str, label: str, match: str):
        if code not in seen_codes:
            seen_codes.add(code)
            results.append({"code": code, "label": label, "match": match, "level": _level(code)})

    # 1. Direct code prefix match — sorted by hierarchy (segment → family → ... → commodity)
    code_matches = []
    for code, label in _UNSPSC_CATALOG.items():
        if code.startswith(query):
            code_matches.append((code, label))
    code_matches.sort(key=lambda x: (len(x[0]), x[0]))
    for code, label in code_matches:
        _add(code, label, "code")

    # 2. Label / keyword search (Polish + English) with diacritics normalization
    query_words = query_norm.split()
    for code, label in _UNSPSC_CATALOG.items():
        lab_norm = _normalize(label)
        if all(w in lab_norm for w in query_words):
            _add(code, label, "label")

    # 3. Keyword-based AI suggestion (use _classify_unspsc logic)
    ai_code, ai_label = _classify_unspsc(query)
    if ai_code != "00000000":
        ai_entry_label = _UNSPSC_CATALOG.get(ai_code, ai_label)
        if ai_code not in seen_codes:
            results.insert(0, {"code": ai_code, "label": ai_entry_label, "match": "ai", "level": _level(ai_code)})
            seen_codes.add(ai_code)

    return {
        "success": True,
        "query": q.strip(),
        "results": results[:30],
        "total": len(results),
    }
