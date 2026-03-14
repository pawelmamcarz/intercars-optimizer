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

from fastapi import APIRouter, Query, UploadFile, File
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
