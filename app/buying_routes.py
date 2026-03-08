"""
Optimized Buying — API routes.

GET  /buying/catalog              → product catalog (optionally filtered)
GET  /buying/categories           → category list
POST /buying/calculate            → apply cart rules, return full state
POST /buying/checkout             → run optimizer + create order
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
from app.data_layer import get_domain_data
from app.optimizer import run_optimization
from app.schemas import CriteriaWeights, DemandItem

buying_router = APIRouter(tags=["Optimized Buying"])

# Domain → default weights
_DOMAIN_WEIGHTS = {
    "parts":         (0.40, 0.30, 0.15, 0.15),
    "oe_components": (0.35, 0.25, 0.25, 0.15),
    "oils":          (0.45, 0.25, 0.15, 0.15),
    "batteries":     (0.40, 0.25, 0.20, 0.15),
    "tires":         (0.40, 0.30, 0.15, 0.15),
    "bodywork":      (0.35, 0.30, 0.15, 0.20),
    "it_services":   (0.30, 0.20, 0.30, 0.20),
    "logistics":     (0.30, 0.40, 0.15, 0.15),
    "mro":           (0.45, 0.25, 0.15, 0.15),
    "packaging":     (0.45, 0.20, 0.10, 0.25),
}


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


@buying_router.post("/buying/checkout")
def checkout(req: CheckoutRequest):
    """
    Run the optimizer for each domain in the cart.

    Returns per-domain allocation results + summary.
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

        # Pick a valid region from the domain's suppliers
        all_regions: set[str] = set()
        for s in suppliers:
            all_regions.update(s.served_regions)
        dest_region = req.destination_region if req.destination_region in all_regions else next(iter(all_regions), "PL-MA")

        # Convert cart demand dicts → DemandItem objects
        demand_items = [
            DemandItem(
                product_id=di["product_id"],
                demand_qty=di["demand_qty"],
                destination_region=dest_region,
            )
            for di in demand_items_raw
        ]

        # Build weights
        wt = _DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
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

            # Compute allocated cost per allocation
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

    optimization_result = {
        "optimized_cost": round(total_optimized_cost, 2),
        "savings_pln": round(cart_state["subtotal"] - total_optimized_cost, 2),
        "domain_results": domain_results,
    }

    # Create order
    order = create_order(
        cart_state=cart_state,
        optimization_result=optimization_result,
        mpk=req.mpk,
        gl_account=req.gl_account,
    )

    return {
        "success": True,
        "message": "Zamówienie zoptymalizowane i utworzone pomyślnie.",
        "order_id": order["order_id"],
        "order_status": order["status"],
        "order_status_label": order["status_label"],
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
        "optimized_cost": round(total_optimized_cost, 2),
        "savings_pln": round(cart_state["subtotal"] - total_optimized_cost, 2),
        "domain_results": domain_results,
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
