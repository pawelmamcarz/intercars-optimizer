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
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

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

@buying_router.get("/buying/catalog")
def catalog(category: str | None = Query(None)):
    """Return product catalog, optionally filtered by category."""
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
def order_approve(order_id: str, approver: str = Query("manager@intercars.eu")):
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
