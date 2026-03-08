"""
Optimized Buying — API routes.

GET  /buying/catalog          → product catalog (optionally filtered)
GET  /buying/categories       → category list
POST /buying/calculate        → apply cart rules, return full state
POST /buying/checkout         → run multi-domain optimizer on cart
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.buying_engine import (
    get_catalog,
    get_categories,
    calculate_cart_state,
    map_cart_to_demand,
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

    return {
        "success": True,
        "message": "Zamówienie zoptymalizowane pomyślnie.",
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
