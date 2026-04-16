"""
recommendation_engine.py — MVP-4

Turns the raw signal sources (contracts, orders, spend analytics, supplier
concentration) into the ActionCard list consumed by the copilot dashboard.

Each rule is a pure function that returns `list[ActionCard]`. The public
`generate_recommendations()` runs every rule, concatenates the output,
sorts by urgency (urgent first) then by some rule-specific key, and caps
the result so the dashboard stays readable.

Rules:
  R1 contracts_expiring        — contracts ending within 90 days
  R2 supplier_concentration    — one supplier over 70% of total spend
  R3 direct_indirect_drift     — dominant kind > 80% (consolidation hint)
  R4 single_source_risk        — product with only one active supplier
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular import at module load; only needed for type hints.
    from app.copilot_engine import ActionCard

log = logging.getLogger(__name__)


# ─── Rule 1: expiring contracts ─────────────────────────────────────

def _rule_contracts_expiring() -> list["ActionCard"]:
    from app.contract_engine import expiring_within
    from app.copilot_engine import ActionCard, CopilotAction

    cards: list[ActionCard] = []
    for c in expiring_within(90):
        days = c.days_to_expiry()
        urgency = "urgent" if days <= 30 else "info"
        when = f"za {days} dni" if days > 0 else "dzisiaj"
        vol = f"{c.committed_volume_pln / 1000:.0f} tys. PLN/rok" if c.committed_volume_pln else ""
        cards.append(ActionCard(
            id=f"contract_expiry_{c.id}",
            icon="📅",
            urgency=urgency,
            title=f"Kontrakt z {c.supplier_name} wygasa {when}",
            desc=(f"Kategoria: {c.category}"
                  + (f" · wolumen {vol}" if vol else "")
                  + (f" · {c.notes}" if c.notes else "")
                  + ". Zaplanuj renegocjacje albo RFQ, zeby miec alternatywy."),
            cta="Zaplanuj renegocjacje",
            action=CopilotAction(action_type="navigate", params={"step": 2}, confidence=0.85),
        ))
    return cards


# ─── Rule 2: supplier concentration ─────────────────────────────────

def _rule_supplier_concentration() -> list["ActionCard"]:
    """Aggregate spend per supplier across orders. Reads purchase_orders
    when filled (post-PO-generation) and falls back to solver allocations
    (domain_results[].allocations) so the rule fires even on approved
    orders whose POs haven't been generated yet."""
    from app.buying_engine import _load_orders
    from app.copilot_engine import ActionCard, CopilotAction

    # Scope to active tenant so cross-tenant spend doesn't trip alerts.
    try:
        from app.tenant_context import current_tenant
        _tenant = current_tenant()
    except Exception:
        _tenant = "demo"

    per_sup: dict[str, tuple[str, float]] = {}
    total = 0.0
    for o in _load_orders():
        if (o.get("tenant_id") or "demo") != _tenant:
            continue
        order_total = float(o.get("total") or 0)
        total += order_total

        pos = o.get("purchase_orders") or []
        if pos:
            for po in pos:
                sid = po.get("supplier_id") or po.get("supplier_name")
                if not sid:
                    continue
                amount = float(po.get("po_total_pln") or po.get("total") or 0)
                sname = po.get("supplier_name") or sid
                prev_name, prev_amt = per_sup.get(sid, (sname, 0.0))
                per_sup[sid] = (prev_name, prev_amt + amount)
            continue

        # Fallback: attribute spend via solver allocations
        for dr in o.get("domain_results") or []:
            for alloc in dr.get("allocations") or []:
                sid = alloc.get("supplier_id")
                if not sid:
                    continue
                amount = float(alloc.get("allocated_cost_pln") or 0)
                sname = alloc.get("supplier_name") or sid
                prev_name, prev_amt = per_sup.get(sid, (sname, 0.0))
                per_sup[sid] = (prev_name, prev_amt + amount)

    if not total or not per_sup:
        return []
    top_sid, (top_name, top_spend) = max(per_sup.items(), key=lambda kv: kv[1][1])
    attributed = sum(v[1] for v in per_sup.values())
    # Concentration is computed over attributed spend (what we can map),
    # not over the raw order total which may include unmatched charges.
    denom = attributed if attributed > 0 else total
    share = top_spend / denom
    if share < 0.70:
        return []
    return [ActionCard(
        id=f"concentration_{top_sid}",
        icon="⚠️",
        urgency="urgent" if share >= 0.85 else "info",
        title=f"Ryzyko koncentracji: {top_name} ma {share * 100:.0f}% spendu",
        desc=(f"Jeden dostawca obsluguje {top_spend / 1000:.0f} tys. PLN z "
              f"{denom / 1000:.0f} tys. PLN atrybuowanego spendu. "
              "Rozwazasz dywersyfikacje zanim cokolwiek się sparzy."),
        cta="Znajdz alternatywnych dostawcow",
        action=CopilotAction(action_type="navigate", params={"step": 2}, confidence=0.8),
    )]


# ─── Rule 3: direct / indirect drift ────────────────────────────────

def _rule_direct_indirect_drift() -> list["ActionCard"]:
    from app.buying_engine import spend_analytics
    from app.copilot_engine import ActionCard, CopilotAction

    r = spend_analytics(period_days=90)
    total = r.get("total_spend", 0)
    if total < 1000:  # not enough signal
        return []
    direct_pct = r.get("direct_pct", 0)
    indirect_pct = r.get("indirect_pct", 0)
    cards = []
    if direct_pct >= 95 and total > 10000:
        cards.append(ActionCard(
            id="drift_direct",
            icon="📊",
            urgency="info",
            title="Spend Indirect prawie zero",
            desc=(f"100% spendu (ostatnie 90 dni, {total / 1000:.0f} tys. PLN) idzie "
                  "na Direct. Sprawdz czy OPEX (IT, logistyka, FM) nie jest "
                  "puszczany obok systemu — to typowy maverick spend."),
            cta="Sprawdz wydatki Indirect",
            action=CopilotAction(action_type="navigate", params={"step": 5}, confidence=0.7),
        ))
    elif indirect_pct >= 80:
        cards.append(ActionCard(
            id="drift_indirect",
            icon="📊",
            urgency="info",
            title=f"Indirect dominuje: {indirect_pct:.0f}% spendu",
            desc=("Wiekszosc wydatkow idzie na OPEX. "
                  "Warto skonsolidowac umowy ramowe, zeby zbic koszty jednostkowe."),
            cta="Analizuj spend Indirect",
            action=CopilotAction(action_type="navigate", params={"step": 5}, confidence=0.7),
        ))
    return cards


# ─── Rule 4: YoY spend anomaly (from BI warehouse mock) ─────────────

def _rule_yoy_anomaly() -> list["ActionCard"]:
    from app.bi_mock import get_connector
    from app.copilot_engine import ActionCard, CopilotAction

    bi = get_connector("bi")
    if not bi:
        return []
    anomalies = bi.yoy_anomalies(threshold_pct=20.0)
    if not anomalies:
        return []
    # Surface the top single anomaly — more than one gets noisy on the card row
    top = anomalies[0]
    arrow = "▲" if top["direction"] == "up" else "▼"
    urgency = "urgent" if abs(top["delta_pct"]) >= 40 else "info"
    return [ActionCard(
        id=f"yoy_anomaly_{top['category']}",
        icon="📈" if top["direction"] == "up" else "📉",
        urgency=urgency,
        title=f"{top['category']}: spend {arrow} {abs(top['delta_pct']):.0f}% YoY",
        desc=(f"W {top['current_quarter']} wydatki w kategorii {top['category']} "
              f"siegnely {top['current_spend'] / 1000:.0f} tys. PLN "
              f"(vs {top['reference_spend'] / 1000:.0f} tys. w {top['reference_quarter']}). "
              "Sprawdz czy to sezon, czy driftują warunki umów."),
        cta="Zobacz trend i dostawcow",
        action=CopilotAction(action_type="navigate", params={"step": 5}, confidence=0.75),
    )]


# ─── Rule 5: single-source product risk ─────────────────────────────

def _rule_single_source_risk() -> list["ActionCard"]:
    from app.buying_engine import get_catalog
    from app.copilot_engine import ActionCard, CopilotAction

    single = [p for p in get_catalog(None) if len(p.get("suppliers") or []) == 1]
    if len(single) < 3:
        return []
    # Count of OE components in the single-source list — they're highest-risk
    oe_single = [p for p in single if p.get("category") == "oe_components"]
    focus = oe_single or single
    label = "OE produktow" if oe_single else "produktow"
    sample = ", ".join(p["name"][:40] for p in focus[:3])
    return [ActionCard(
        id="single_source",
        icon="⚠️",
        urgency="urgent",
        title=f"Ryzyko single-source: {len(focus)} {label}",
        desc=(f"Tyle pozycji ma w katalogu tylko jednego dostawce "
              f"({sample}...). Brak alternatywy = ryzyko dla ciaglosci zakupow. "
              f"Calkowita liczba single-source: {len(single)}."),
        cta="Pokaz ryzykowne pozycje",
        action=CopilotAction(action_type="navigate", params={"step": 5}, confidence=0.8),
    )]


# ─── Orchestrator ───────────────────────────────────────────────────

_RULES = (
    _rule_contracts_expiring,
    _rule_supplier_concentration,
    _rule_direct_indirect_drift,
    _rule_yoy_anomaly,
    _rule_single_source_risk,
)

_URGENCY_RANK = {"urgent": 0, "info": 1}


def generate_recommendations(context: dict | None = None, limit: int = 6) -> list[dict]:
    """Run every rule, merge and sort by urgency, cap at `limit`."""
    from app.copilot_engine import ActionCard  # noqa — ensure module present

    out: list = []
    for rule in _RULES:
        try:
            out.extend(rule())
        except Exception as exc:
            log.warning("recommendation rule %s failed: %s", rule.__name__, exc)

    out.sort(key=lambda c: (_URGENCY_RANK.get(getattr(c, "urgency", "info"), 1), getattr(c, "id", "")))
    return [c.model_dump() for c in out[:limit]]
