"""
Optimized Buying Engine — guided buying catalog + cart rules + order lifecycle.

Inspired by SAP Ariba Guided Buying, adapted for INTERCARS procurement.
Catalog items map to optimizer domains → checkout runs multi-domain optimization.
Order lifecycle: draft → pending_approval → approved → po_generated → confirmed → delivered.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# ── Catalog ────────────────────────────────────────────────────────────────

CATEGORIES = [
    {"id": "parts",         "label": "Części zamienne",     "icon": "🔧", "group": "direct"},
    {"id": "oe_components", "label": "Komponenty OE",       "icon": "⚙️", "group": "direct"},
    {"id": "oils",          "label": "Oleje i płyny",       "icon": "🛢️", "group": "direct"},
    {"id": "batteries",     "label": "Akumulatory",         "icon": "🔋", "group": "direct"},
    {"id": "tires",         "label": "Opony",               "icon": "🚗", "group": "direct"},
    {"id": "bodywork",      "label": "Nadwozia i oświetl.", "icon": "💡", "group": "direct"},
    {"id": "it_services",   "label": "IT / Licencje",       "icon": "💻", "group": "indirect"},
    {"id": "logistics",     "label": "Logistyka",           "icon": "📦", "group": "indirect"},
    {"id": "mro",           "label": "MRO / Narzędzia",     "icon": "🛠️", "group": "indirect"},
    {"id": "packaging",     "label": "Opakowania",          "icon": "📋", "group": "indirect"},
]

CATALOG: list[dict] = [
    # ── Części zamienne ─────────────────────────────────────────────────
    {
        "id": "BRK-001", "name": "Klocki hamulcowe TRW GDB1550",
        "description": "Klocki hamulcowe przód, ceramiczne. Homologacja ECE R90.",
        "price": 185.0, "category": "parts", "delivery_days": 2,
        "weight_kg": 0.8, "unit": "kpl", "requires_approval": False,
        "image": "brake-pads",
    },
    {
        "id": "FIL-001", "name": "Filtr oleju MANN W712/73",
        "description": "Filtr oleju silnikowego. Pasuje do VW/Audi/Skoda.",
        "price": 32.0, "category": "parts", "delivery_days": 1,
        "weight_kg": 0.3, "unit": "szt", "requires_approval": False,
        "image": "oil-filter",
    },
    {
        "id": "DSC-001", "name": "Tarcza hamulcowa Brembo 09.5802",
        "description": "Tarcza wentylowana 280mm przód. Powłoka UV.",
        "price": 245.0, "category": "parts", "delivery_days": 3,
        "weight_kg": 4.5, "unit": "szt", "requires_approval": False,
        "image": "brake-disc",
    },
    {
        "id": "AMO-001", "name": "Amortyzator Sachs 313 478",
        "description": "Amortyzator przód gazowy. Oryginalna jakość ZF.",
        "price": 320.0, "category": "parts", "delivery_days": 3,
        "weight_kg": 3.2, "unit": "szt", "requires_approval": False,
        "image": "shock-absorber",
    },
    {
        "id": "PAS-001", "name": "Pasek wieloklinowy Gates 6PK1070",
        "description": "Pasek napędu osprzętu silnika. EPDM micro-V.",
        "price": 58.0, "category": "parts", "delivery_days": 1,
        "weight_kg": 0.2, "unit": "szt", "requires_approval": False,
        "image": "belt",
    },

    # ── Komponenty OE ───────────────────────────────────────────────────
    {
        "id": "ALT-001", "name": "Alternator Bosch 0 124 525 014",
        "description": "Alternator 14V 120A. Jakość OE, regulator napięcia.",
        "price": 890.0, "category": "oe_components", "delivery_days": 5,
        "weight_kg": 5.8, "unit": "szt", "requires_approval": False,
        "image": "alternator",
    },
    {
        "id": "PMP-001", "name": "Pompa wody SKF VKPC 86416",
        "description": "Pompa wody z uszczelką. Łożysko ceramiczne.",
        "price": 210.0, "category": "oe_components", "delivery_days": 4,
        "weight_kg": 1.5, "unit": "szt", "requires_approval": False,
        "image": "water-pump",
    },
    {
        "id": "ROZ-001", "name": "Rozrusznik Valeo 438170",
        "description": "Rozrusznik 12V 1.1kW. Regenerowany OE.",
        "price": 780.0, "category": "oe_components", "delivery_days": 5,
        "weight_kg": 4.2, "unit": "szt", "requires_approval": True,
        "image": "starter",
    },

    # ── Oleje i płyny ───────────────────────────────────────────────────
    {
        "id": "OIL-001", "name": "Castrol EDGE 5W-30 LL 5L",
        "description": "Olej syntetyczny Titanium FST. VW 504/507.",
        "price": 189.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 4.6, "unit": "szt", "requires_approval": False,
        "image": "engine-oil",
    },
    {
        "id": "OIL-002", "name": "Shell Helix Ultra ECT 5W-30 4L",
        "description": "Olej syntetyczny PurePlus. MB 229.51, BMW LL-04.",
        "price": 165.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 3.8, "unit": "szt", "requires_approval": False,
        "image": "engine-oil-2",
    },
    {
        "id": "BRF-001", "name": "Płyn hamulcowy ATE SL.6 DOT4 1L",
        "description": "Płyn hamulcowy klasy DOT4. T. wrzenia 265°C.",
        "price": 45.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 1.1, "unit": "szt", "requires_approval": False,
        "image": "brake-fluid",
    },
    {
        "id": "CLN-001", "name": "Płyn do spryskiwaczy zimowy -22°C 5L",
        "description": "Koncentrat z alkoholem izopropylowym. Nie pozostawia smug.",
        "price": 25.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 5.2, "unit": "szt", "requires_approval": False,
        "image": "washer-fluid",
    },

    # ── Akumulatory ─────────────────────────────────────────────────────
    {
        "id": "BAT-001", "name": "Varta Blue Dynamic E11 74Ah",
        "description": "Akumulator 12V 74Ah 680A(EN). Wymiary 278x175x190.",
        "price": 420.0, "category": "batteries", "delivery_days": 2,
        "weight_kg": 18.5, "unit": "szt", "requires_approval": False,
        "image": "battery",
    },
    {
        "id": "BAT-002", "name": "Exide Premium EA770 77Ah",
        "description": "Akumulator 12V 77Ah 760A(EN). Carbon Boost 2.0.",
        "price": 385.0, "category": "batteries", "delivery_days": 2,
        "weight_kg": 19.2, "unit": "szt", "requires_approval": False,
        "image": "battery-2",
    },
    {   # Auto-bundle item (injected when batteries in cart)
        "id": "BUNDLE-CAB", "name": "Kable rozruchowe 600A 3m",
        "description": "Kable rozruchowe miedziane z zaciskami izolowanymi.",
        "price": 89.0, "category": "batteries", "delivery_days": 1,
        "weight_kg": 1.5, "unit": "kpl", "requires_approval": False,
        "image": "jumper-cables", "_is_bundle_source": True,
    },

    # ── Opony ───────────────────────────────────────────────────────────
    {
        "id": "TIR-001", "name": "Continental PremiumContact 6 205/55R16",
        "description": "Opona letnia. EU label: A/A/71dB. Run-flat.",
        "price": 480.0, "category": "tires", "delivery_days": 3,
        "weight_kg": 8.5, "unit": "szt", "requires_approval": False,
        "image": "tire-continental",
    },
    {
        "id": "TIR-002", "name": "Michelin Pilot Sport 5 225/45R17",
        "description": "Opona letnia premium. EU label: A/A/70dB.",
        "price": 620.0, "category": "tires", "delivery_days": 4,
        "weight_kg": 9.2, "unit": "szt", "requires_approval": False,
        "image": "tire-michelin",
    },
    {
        "id": "TIR-003", "name": "Hankook Ventus Prime 4 195/65R15",
        "description": "Opona letnia ekonomiczna. EU label: A/B/69dB.",
        "price": 340.0, "category": "tires", "delivery_days": 2,
        "weight_kg": 7.8, "unit": "szt", "requires_approval": False,
        "image": "tire-hankook",
    },

    # ── Nadwozia / Oświetlenie ──────────────────────────────────────────
    {
        "id": "REF-001", "name": "Reflektor przedni LED (lewy)",
        "description": "Lampa przód LED z DRL. Homologacja E4. Hella OE.",
        "price": 1250.0, "category": "bodywork", "delivery_days": 7,
        "weight_kg": 2.8, "unit": "szt", "requires_approval": True,
        "image": "headlight",
    },
    {
        "id": "ZDR-001", "name": "Zderzak przedni surowy do lakierowania",
        "description": "Zderzak PP z otworami na czujniki PDC.",
        "price": 890.0, "category": "bodywork", "delivery_days": 7,
        "weight_kg": 4.5, "unit": "szt", "requires_approval": False,
        "image": "bumper",
    },

    # ── IT / Licencje ───────────────────────────────────────────────────
    {
        "id": "SAP-001", "name": "Licencja SAP moduł MM (roczna)",
        "description": "Named-user license SAP Materials Management.",
        "price": 12000.0, "category": "it_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "lic", "requires_approval": True,
        "image": "sap-license",
    },
    {
        "id": "ERP-001", "name": "Serwis ERP — aktualizacja kwartalna",
        "description": "Usługa aktualizacji i optymalizacji modułów ERP.",
        "price": 4500.0, "category": "it_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "usł", "requires_approval": False,
        "image": "erp-service",
    },

    # ── Logistyka ───────────────────────────────────────────────────────
    {
        "id": "PAL-001", "name": "Paleta EUR EPAL 1200x800",
        "description": "Paleta drewniana certyfikowana EPAL. Nowa.",
        "price": 42.0, "category": "logistics", "delivery_days": 2,
        "weight_kg": 25.0, "unit": "szt", "requires_approval": False,
        "image": "pallet",
    },

    # ── MRO / Narzędzia ─────────────────────────────────────────────────
    {
        "id": "NRZ-001", "name": "Zestaw kluczy Wera Kraftform 12szt",
        "description": "Zestaw wkrętaków Kraftform Plus z Lasertip.",
        "price": 380.0, "category": "mro", "delivery_days": 3,
        "weight_kg": 2.5, "unit": "kpl", "requires_approval": False,
        "image": "tools-wera",
    },
    {
        "id": "BHP-001", "name": "Rękawice robocze nitrylowe 100 par",
        "description": "Rękawice jednorazowe, pudrowane. Rozmiar L.",
        "price": 220.0, "category": "mro", "delivery_days": 2,
        "weight_kg": 5.0, "unit": "op", "requires_approval": False,
        "image": "gloves",
    },

    # ── Opakowania ──────────────────────────────────────────────────────
    {
        "id": "FOL-001", "name": "Folia stretch 23μm 500mm 2.4kg",
        "description": "Folia do owijania palet. Rozciągliwość 300%.",
        "price": 18.0, "category": "packaging", "delivery_days": 1,
        "weight_kg": 2.4, "unit": "rol", "requires_approval": False,
        "image": "stretch-film",
    },
    {
        "id": "KRT-001", "name": "Karton klapowy 600x400x400 3W",
        "description": "Karton trójwarstwowy fala B. Brązowy.",
        "price": 4.50, "category": "packaging", "delivery_days": 1,
        "weight_kg": 0.6, "unit": "szt", "requires_approval": False,
        "image": "cardboard-box",
    },
]

# Pre-index
_CATALOG_BY_ID = {p["id"]: p for p in CATALOG}

BUNDLE_CABLE_ID = "BUNDLE-CAB"


def get_catalog(category: str | None = None) -> list[dict]:
    """Return catalog items, optionally filtered by category."""
    items = [p for p in CATALOG if not p.get("_is_bundle_source")]
    if category:
        items = [p for p in items if p["category"] == category]
    return items


def get_categories() -> list[dict]:
    return CATEGORIES


# ── Cart Rules Engine ──────────────────────────────────────────────────────

def calculate_cart_state(raw_items: list[dict]) -> dict:
    """
    Apply 10 business rules to a raw cart.

    Input: [{"id": "BRK-001", "quantity": 4}, ...]
    Output: full cart state with items, totals, errors, warnings, bundles.
    """
    # Resolve items from catalog
    items: list[dict] = []
    for raw in raw_items:
        product = _CATALOG_BY_ID.get(raw["id"])
        if not product:
            continue
        items.append({
            **product,
            "quantity": max(1, int(raw.get("quantity", 1))),
            "_is_forced_bundle": False,
        })

    errors: list[str] = []
    warnings: list[str] = []
    discount = 0.0

    # ── RULE 1: Zestaw akumulatorowy (battery → auto-inject cables) ────
    has_battery = any(i["category"] == "batteries" and i["id"] != BUNDLE_CABLE_ID for i in items)
    cable_in_cart = any(i["id"] == BUNDLE_CABLE_ID for i in items)
    if has_battery and not cable_in_cart:
        cable = _CATALOG_BY_ID.get(BUNDLE_CABLE_ID)
        if cable:
            items.append({**cable, "quantity": 1, "_is_forced_bundle": True})
            warnings.append("Zestaw akumulatorowy: automatycznie dodano kable rozruchowe 600A.")
    elif not has_battery and cable_in_cart:
        items = [i for i in items if i["id"] != BUNDLE_CABLE_ID]

    # ── Calculate subtotal ─────────────────────────────────────────────
    subtotal = sum(i["price"] * i["quantity"] for i in items)

    # ── RULE 2: Minimum logistyczne (500 PLN) ──────────────────────────
    if 0 < subtotal < 500:
        errors.append(f"Minimalna wartość zamówienia to 500 PLN (brakuje {500 - subtotal:.0f} PLN).")

    # ── RULE 3: Oleje w opakowaniach (multiples of 4) ──────────────────
    for i in items:
        if i["category"] == "oils" and i["id"].startswith("OIL-") and i["quantity"] % 4 != 0:
            errors.append(f'{i["name"]}: oleje silnikowe należy zamawiać w wielokrotnościach 4 szt.')

    # ── RULE 4: Promocja oponowa (4+ szt tego samego = 8% rabat) ──────
    for i in items:
        if i["category"] == "tires" and i["quantity"] >= 4:
            sets_of_4 = i["quantity"] // 4
            disc = sets_of_4 * 4 * i["price"] * 0.08
            discount += disc
            warnings.append(f'Promocja oponowa: {sets_of_4} komplet(y) {i["name"][:30]}… → -{disc:.0f} PLN (8%).')

    # ── RULE 5: Komplet opon (nie wielokrotność 4 → warning) ──────────
    for i in items:
        if i["category"] == "tires" and i["quantity"] % 4 != 0:
            warnings.append(f'{i["name"][:30]}…: zalecane zamawianie opon w kompletach po 4 szt.')

    # ── RULE 6: Rabat ilościowy na opakowania (10+ szt → 12%) ─────────
    for i in items:
        if i["category"] == "packaging" and i["quantity"] >= 10:
            disc = i["price"] * i["quantity"] * 0.12
            discount += disc
            warnings.append(f'Rabat ilościowy: {i["name"][:30]}… ({i["quantity"]} szt) → -{disc:.0f} PLN (12%).')

    # ── RULE 7: Manager Approval ───────────────────────────────────────
    requires_approval = any(i.get("requires_approval") for i in items)
    if subtotal > 15000:
        requires_approval = True
    if requires_approval:
        reasons = []
        if subtotal > 15000:
            reasons.append(f"wartość zamówienia {subtotal:,.0f} PLN > 15 000 PLN")
        approval_items = [i["name"][:25] for i in items if i.get("requires_approval")]
        if approval_items:
            reasons.append(f"pozycje wymagające zatwierdzenia: {', '.join(approval_items)}")
        warnings.append(f"Wymagane zatwierdzenie kierownika ({'; '.join(reasons)}).")

    # ── RULE 8: Limit budżetowy IT (max 25 000 PLN) ───────────────────
    it_total = sum(i["price"] * i["quantity"] for i in items if i["category"] == "it_services")
    if it_total > 25000:
        errors.append(f"Przekroczony limit budżetowy IT: {it_total:,.0f} PLN > 25 000 PLN.")

    # ── RULE 9: Koszty dostawy ─────────────────────────────────────────
    total_weight = sum(i["weight_kg"] * i["quantity"] for i in items)
    if total_weight > 100:
        shipping = 250.0
        warnings.append(f"Fracht ciężki ({total_weight:.0f} kg > 100 kg): koszt dostawy 250 PLN.")
    elif subtotal > 1000:
        shipping = 0.0
        warnings.append("Darmowa dostawa (zamówienie > 1 000 PLN).")
    else:
        shipping = 49.0

    # ── RULE 10: Limit wielkości zamówienia (max 100 szt) ──────────────
    total_qty = sum(i["quantity"] for i in items)
    if total_qty > 100:
        errors.append(f"Przekroczony limit zamówienia: {total_qty} szt > 100 szt.")

    # ── Czas dostawy ──────────────────────────────────────────────────
    delivery_days = max((i["delivery_days"] for i in items), default=0)

    # ── Total ─────────────────────────────────────────────────────────
    total = subtotal - discount + shipping

    # Build clean item list for response
    response_items = []
    for i in items:
        response_items.append({
            "id": i["id"],
            "name": i["name"],
            "price": i["price"],
            "quantity": i["quantity"],
            "category": i["category"],
            "unit": i.get("unit", "szt"),
            "weight_kg": i["weight_kg"],
            "line_total": i["price"] * i["quantity"],
            "is_forced_bundle": i.get("_is_forced_bundle", False),
            "requires_approval": i.get("requires_approval", False),
        })

    return {
        "items": response_items,
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "shipping_fee": round(shipping, 2) if items else 0.0,
        "total": round(total, 2) if items else 0.0,
        "total_weight_kg": round(total_weight, 1),
        "total_items": total_qty,
        "delivery_days": delivery_days,
        "requires_manager_approval": requires_approval,
        "errors": errors,
        "warnings": warnings,
        "can_checkout": len(errors) == 0 and len(items) > 0,
    }


def map_cart_to_demand(cart_state: dict) -> dict[str, list[dict]]:
    """
    Map cart items to optimizer demand per domain.

    Returns: {"parts": [DemandItem, ...], "oils": [...], ...}
    """
    demand_by_domain: dict[str, list[dict]] = {}
    for item in cart_state["items"]:
        domain = item["category"]
        if domain not in demand_by_domain:
            demand_by_domain[domain] = []
        demand_by_domain[domain].append({
            "product_id": item["id"],
            "demand_qty": item["quantity"],
            "destination_region": "PL-MA",  # default Kraków hub
        })
    return demand_by_domain


# ── Order Lifecycle ───────────────────────────────────────────────────────

ORDER_STATUSES = [
    "draft",
    "pending_approval",
    "approved",
    "po_generated",
    "confirmed",
    "in_delivery",
    "delivered",
    "cancelled",
]

STATUS_LABELS = {
    "draft": "Szkic",
    "pending_approval": "Oczekuje na zatwierdzenie",
    "approved": "Zatwierdzone",
    "po_generated": "PO wygenerowane",
    "confirmed": "Potwierdzone przez dostawców",
    "in_delivery": "W dostawie",
    "delivered": "Dostarczone",
    "cancelled": "Anulowane",
}

# Valid status transitions
_TRANSITIONS = {
    "draft":             ["pending_approval", "approved", "cancelled"],
    "pending_approval":  ["approved", "cancelled"],
    "approved":          ["po_generated", "cancelled"],
    "po_generated":      ["confirmed", "cancelled"],
    "confirmed":         ["in_delivery"],
    "in_delivery":       ["delivered"],
    "delivered":         [],
    "cancelled":         [],
}

# In-memory order store
_orders: dict[str, dict] = {}


def create_order(
    cart_state: dict,
    optimization_result: dict,
    mpk: str,
    gl_account: str,
    requester: str = "procurement.bot@intercars.eu",
) -> dict:
    """Create a new order from checkout results."""
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()

    requires_approval = cart_state.get("requires_manager_approval", False)
    initial_status = "pending_approval" if requires_approval else "approved"

    order = {
        "order_id": order_id,
        "status": initial_status,
        "status_label": STATUS_LABELS[initial_status],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "requester": requester,
        "mpk": mpk,
        "gl_account": gl_account,
        # Cart data
        "items": cart_state["items"],
        "subtotal": cart_state["subtotal"],
        "discount": cart_state["discount"],
        "shipping_fee": cart_state["shipping_fee"],
        "total": cart_state["total"],
        "total_items": cart_state["total_items"],
        "delivery_days": cart_state["delivery_days"],
        "requires_manager_approval": requires_approval,
        # Optimization
        "optimized_cost": optimization_result.get("optimized_cost", 0),
        "savings_pln": optimization_result.get("savings_pln", 0),
        "domain_results": optimization_result.get("domain_results", []),
        # PO tracking
        "purchase_orders": [],
        # History
        "history": [
            {
                "timestamp": now.isoformat(),
                "action": "order_created",
                "status": initial_status,
                "actor": requester,
                "note": f"Zamówienie utworzone. Wartość: {cart_state['total']:.2f} PLN.",
            }
        ],
    }

    _orders[order_id] = order
    return order


def get_order(order_id: str) -> dict | None:
    return _orders.get(order_id)


def list_orders(status: str | None = None) -> list[dict]:
    orders = list(_orders.values())
    if status:
        orders = [o for o in orders if o["status"] == status]
    return sorted(orders, key=lambda o: o["created_at"], reverse=True)


def transition_order(
    order_id: str,
    new_status: str,
    actor: str = "system",
    note: str = "",
) -> dict | None:
    """Move order to a new status if transition is valid."""
    order = _orders.get(order_id)
    if not order:
        return None

    current = order["status"]
    allowed = _TRANSITIONS.get(current, [])
    if new_status not in allowed:
        return {
            "error": True,
            "message": f"Niedozwolona zmiana statusu: {STATUS_LABELS.get(current, current)} → {STATUS_LABELS.get(new_status, new_status)}.",
            "allowed_transitions": [{"status": s, "label": STATUS_LABELS[s]} for s in allowed],
        }

    now = datetime.now()
    order["status"] = new_status
    order["status_label"] = STATUS_LABELS[new_status]
    order["updated_at"] = now.isoformat()
    order["history"].append({
        "timestamp": now.isoformat(),
        "action": f"status_changed_to_{new_status}",
        "status": new_status,
        "actor": actor,
        "note": note or f"Status zmieniony na: {STATUS_LABELS[new_status]}.",
    })

    return order


def approve_order(order_id: str, approver: str = "manager@intercars.eu") -> dict | None:
    """Approve an order (shortcut for pending_approval → approved)."""
    return transition_order(order_id, "approved", actor=approver, note=f"Zatwierdzone przez {approver}.")


def generate_purchase_orders(order_id: str) -> dict | None:
    """Generate POs from optimization allocations (approved → po_generated)."""
    order = _orders.get(order_id)
    if not order:
        return None
    if order["status"] != "approved":
        return {
            "error": True,
            "message": f"PO można generować tylko dla zamówień zatwierdzonych (aktualnie: {order['status_label']}).",
        }

    now = datetime.now()
    pos: list[dict] = []
    po_seq = 1

    for dr in order.get("domain_results", []):
        if not dr.get("success"):
            continue
        # Group allocations by supplier
        by_supplier: dict[str, list[dict]] = {}
        for alloc in dr.get("allocations", []):
            sid = alloc["supplier_id"]
            by_supplier.setdefault(sid, []).append(alloc)

        for supplier_id, allocs in by_supplier.items():
            po_id = f"PO-{order_id.split('-', 1)[1]}-{po_seq:02d}"
            po_total = sum(a.get("allocated_cost_pln", 0) for a in allocs)
            po = {
                "po_id": po_id,
                "supplier_id": supplier_id,
                "supplier_name": allocs[0].get("supplier_name", supplier_id),
                "domain": dr["domain"],
                "lines": [
                    {
                        "product_id": a["product_id"],
                        "quantity": a["allocated_qty"],
                        "unit_cost": a["unit_cost"],
                        "logistics_cost": a["logistics_cost"],
                        "line_total": a.get("allocated_cost_pln", 0),
                    }
                    for a in allocs
                ],
                "po_total_pln": round(po_total, 2),
                "status": "sent",
                "created_at": now.isoformat(),
                "expected_delivery": (now + timedelta(days=max(a.get("lead_time_days", 5) for a in allocs))).strftime("%Y-%m-%d"),
            }
            pos.append(po)
            po_seq += 1

    order["purchase_orders"] = pos
    transition_order(order_id, "po_generated", actor="system", note=f"Wygenerowano {len(pos)} zamówień zakupu (PO).")
    return order


def confirm_order(order_id: str) -> dict | None:
    """Mark POs as confirmed by suppliers (po_generated → confirmed)."""
    order = _orders.get(order_id)
    if not order:
        return None
    if order["status"] != "po_generated":
        return {"error": True, "message": f"PO można potwierdzić tylko w statusie 'PO wygenerowane' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "confirmed"
        po["confirmed_at"] = now.isoformat()
    return transition_order(order_id, "confirmed", actor="supplier.portal", note="Wszystkie PO potwierdzone przez dostawców.")


def ship_order(order_id: str) -> dict | None:
    """Mark order as in delivery (confirmed → in_delivery)."""
    return transition_order(order_id, "in_delivery", actor="logistics", note="Przesyłka odebrana przez przewoźnika.")


def deliver_order(order_id: str) -> dict | None:
    """Mark order as delivered (in_delivery → delivered) + GR."""
    order = _orders.get(order_id)
    if not order:
        return None
    if order["status"] != "in_delivery":
        return {"error": True, "message": f"Dostawę można potwierdzić tylko w statusie 'W dostawie' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "delivered"
        po["delivered_at"] = now.isoformat()
    result = transition_order(order_id, "delivered", actor="warehouse", note="Goods Receipt (GR) zaksięgowane.")
    return result


def cancel_order(order_id: str, reason: str = "") -> dict | None:
    """Cancel an order at any cancellable stage."""
    return transition_order(order_id, "cancelled", actor="user", note=reason or "Zamówienie anulowane.")
