"""
supplier_scorecard.py — MVP-5

Composite supplier scoring that pulls together every signal we've built:
- ESG + compliance from the catalog
- Contract status from contract_engine (14-day to 1-year expiry buckets)
- Spend attribution + concentration from buying_engine orders
- Single-source product risk from catalog depth
- YoY drift from the BI warehouse mock

Each dimension lands on a 0–100 sub-score (higher = healthier supplier).
The composite is a weighted average; ranks let the UI show top-5 / bottom-3
plus a per-supplier breakdown so the buyer understands why a name scored
the way it did.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)

# Weights sum to 1.0 — tweak here when we get feedback on which dimension
# matters most for a particular buyer persona.
_DIMENSION_WEIGHTS = {
    "esg": 0.20,
    "compliance": 0.20,
    "contract": 0.20,
    "concentration": 0.20,
    "single_source_risk": 0.20,
}


def _score_esg(esg: float) -> float:
    """0–100 from raw 0–1 ESG score."""
    return round(max(0.0, min(1.0, esg)) * 100, 1)


def _score_compliance(compliance: float) -> float:
    return round(max(0.0, min(1.0, compliance)) * 100, 1)


def _score_contract(contract) -> tuple[float, dict]:
    """Contract dimension: active with room-to-expiry = top score; expiring
    soon or no contract at all = low."""
    if contract is None:
        return 55.0, {"status": "no_contract", "days_to_expiry": None}
    days = contract.days_to_expiry()
    if days < 0:
        return 20.0, {"status": "expired", "days_to_expiry": days, "contract_id": contract.id}
    if days <= 30:
        return 40.0, {"status": "expiring_30d", "days_to_expiry": days, "contract_id": contract.id}
    if days <= 90:
        return 65.0, {"status": "expiring_90d", "days_to_expiry": days, "contract_id": contract.id}
    if days <= 365:
        return 90.0, {"status": "active", "days_to_expiry": days, "contract_id": contract.id}
    return 85.0, {"status": "long_term", "days_to_expiry": days, "contract_id": contract.id}


def _score_concentration(share: float) -> tuple[float, dict]:
    """High share of buyer's spend = risky dependency. Range 0–1."""
    if share is None:
        return 70.0, {"share": None}
    if share >= 0.85:
        return 20.0, {"share": share, "level": "critical"}
    if share >= 0.70:
        return 45.0, {"share": share, "level": "high"}
    if share >= 0.50:
        return 70.0, {"share": share, "level": "moderate"}
    return 90.0, {"share": share, "level": "low"}


def _score_single_source(num_single: int, total_products: int) -> tuple[float, dict]:
    """How many of the supplier's products have no alternative in our
    catalog. More single-source = more leverage for the supplier."""
    if total_products == 0:
        return 60.0, {"single_source_count": 0, "total_products": 0}
    ratio = num_single / total_products
    score = round(100.0 - ratio * 80.0, 1)  # 100% single-source → 20
    return max(0.0, score), {
        "single_source_count": num_single,
        "total_products": total_products,
        "ratio": round(ratio, 3),
    }


def _find_contract(supplier_id: str, contracts: list) -> Optional[object]:
    for c in contracts:
        if c.supplier_id == supplier_id and c.is_active(date.today()):
            return c
    return None


def _build_spend_map(tenant_id: str | None = None) -> tuple[dict[str, float], float]:
    """Aggregate PLN spend per supplier across orders (PO-first, allocation
    fallback). Identical logic to _rule_supplier_concentration. Scoped to
    the active tenant when available."""
    from app.buying_engine import _load_orders
    if tenant_id is None:
        try:
            from app.tenant_context import current_tenant
            tenant_id = current_tenant()
        except Exception:
            tenant_id = "demo"
    per_sup: dict[str, float] = {}
    total = 0.0
    for o in _load_orders():
        if (o.get("tenant_id") or "demo") != tenant_id:
            continue
        pos = o.get("purchase_orders") or []
        if pos:
            for po in pos:
                sid = po.get("supplier_id") or po.get("supplier_name")
                if not sid:
                    continue
                per_sup[sid] = per_sup.get(sid, 0.0) + float(po.get("po_total_pln") or 0)
                total += float(po.get("po_total_pln") or 0)
            continue
        for dr in o.get("domain_results") or []:
            for alloc in dr.get("allocations") or []:
                sid = alloc.get("supplier_id")
                if not sid:
                    continue
                amount = float(alloc.get("allocated_cost_pln") or 0)
                per_sup[sid] = per_sup.get(sid, 0.0) + amount
                total += amount
    return per_sup, total


def _supplier_single_source_stats(supplier_id: str) -> tuple[int, int]:
    """Count how many of this supplier's products are single-source."""
    from app.buying_engine import get_catalog
    total = 0
    single = 0
    for p in get_catalog(None):
        sups = p.get("suppliers") or []
        if any(s.get("id") == supplier_id or s.get("name") == supplier_id for s in sups):
            total += 1
            if len(sups) == 1:
                single += 1
    return single, total


def compute_scorecards(category: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Return ranked supplier scorecards.

    Joins catalog (ESG + compliance + product count) with spend attribution
    (share of total spend) and contract state (active/expiring/none).
    Filters by catalog `category` when provided.
    """
    from app.buying_engine import get_catalog
    from app.contract_engine import list_contracts

    contracts = list_contracts()
    spend_map, total_spend = _build_spend_map()

    # Gather unique suppliers from the catalog — each carries ESG/compliance
    # implicitly through products but we need SupplierInput-level data from
    # data_layer.* for the per-supplier ESG score.
    seen: dict[str, dict] = {}
    for p in get_catalog(None):
        if category and p.get("category") != category:
            continue
        for s in p.get("suppliers") or []:
            sid = s.get("id") or s.get("name")
            if not sid or sid in seen:
                continue
            # Pull ESG/compliance from data_layer SupplierInput when present
            esg, comp = _supplier_esg_compliance(sid)
            seen[sid] = {
                "supplier_id": sid,
                "supplier_name": s.get("name") or sid,
                "category": p.get("category"),
                "esg_score": esg,
                "compliance_score": comp,
            }

    scorecards: list[dict] = []
    for sid, info in seen.items():
        esg_s = _score_esg(info["esg_score"])
        comp_s = _score_compliance(info["compliance_score"])
        contract_s, contract_meta = _score_contract(_find_contract(sid, contracts))
        share = (spend_map.get(sid, 0.0) / total_spend) if total_spend > 0 else 0.0
        conc_s, conc_meta = _score_concentration(share)
        single_n, total_n = _supplier_single_source_stats(sid)
        ss_s, ss_meta = _score_single_source(single_n, total_n)

        composite = round(
            esg_s * _DIMENSION_WEIGHTS["esg"]
            + comp_s * _DIMENSION_WEIGHTS["compliance"]
            + contract_s * _DIMENSION_WEIGHTS["contract"]
            + conc_s * _DIMENSION_WEIGHTS["concentration"]
            + ss_s * _DIMENSION_WEIGHTS["single_source_risk"],
            1,
        )

        # Verbal recommendations based on the lowest dimension
        dims = {
            "esg": esg_s, "compliance": comp_s, "contract": contract_s,
            "concentration": conc_s, "single_source_risk": ss_s,
        }
        weakest = min(dims, key=dims.get)
        recs = _recommendations_for(weakest, contract_meta, conc_meta, ss_meta)

        scorecards.append({
            "supplier_id": sid,
            "supplier_name": info["supplier_name"],
            "category": info["category"],
            "composite_score": composite,
            "dimensions": {
                "esg": {"score": esg_s, "raw": info["esg_score"]},
                "compliance": {"score": comp_s, "raw": info["compliance_score"]},
                "contract": {"score": contract_s, **contract_meta},
                "concentration": {"score": conc_s, **conc_meta},
                "single_source_risk": {"score": ss_s, **ss_meta},
            },
            "spend_pln": round(spend_map.get(sid, 0.0), 2),
            "spend_share": round(share, 4),
            "recommendations": recs,
            "weakest_dimension": weakest,
        })

    scorecards.sort(key=lambda s: s["composite_score"], reverse=True)
    return scorecards[:limit]


def _supplier_esg_compliance(sid: str) -> tuple[float, float]:
    """Best-effort lookup of ESG + compliance from the supplier lists
    across all domains. Falls back to modest defaults."""
    try:
        from app.data_layer import (
            DEMO_SUPPLIERS, OE_SUPPLIERS, OIL_SUPPLIERS, BAT_SUPPLIERS,
            TIRE_SUPPLIERS, BODY_SUPPLIERS, IT_DEMO_SUPPLIERS, LOG_SUPPLIERS,
            PKG_SUPPLIERS, MRO_SUPPLIERS,
        )
        pools = [
            DEMO_SUPPLIERS, OE_SUPPLIERS, OIL_SUPPLIERS, BAT_SUPPLIERS,
            TIRE_SUPPLIERS, BODY_SUPPLIERS, IT_DEMO_SUPPLIERS, LOG_SUPPLIERS,
            PKG_SUPPLIERS, MRO_SUPPLIERS,
        ]
        for pool in pools:
            for s in pool:
                if s.supplier_id == sid:
                    return float(s.esg_score), float(s.compliance_score)
    except Exception as exc:
        log.debug("esg_compliance lookup failed for %s: %s", sid, exc)
    return 0.80, 0.90  # conservative defaults


def _recommendations_for(weakest: str, contract_meta: dict,
                         conc_meta: dict, ss_meta: dict) -> list[str]:
    """Short actionable hints — one per problem surface we detect."""
    tips: list[str] = []
    if weakest == "contract":
        status = contract_meta.get("status")
        if status == "expiring_30d":
            tips.append("Kontrakt wygasa za 30 dni — uruchom RFQ albo renegocjuj teraz.")
        elif status == "expiring_90d":
            tips.append("Kontrakt wygasa w kwartale — zaplanuj odnowienie.")
        elif status == "expired":
            tips.append("Kontrakt wygasl — zawiez nowy albo rozwaz wyjscie.")
        elif status == "no_contract":
            tips.append("Brak aktywnego kontraktu — rozwaz ramowa umowe.")
    if weakest == "concentration":
        level = conc_meta.get("level")
        if level in ("critical", "high"):
            tips.append(f"Dostawca przejmuje {conc_meta.get('share', 0) * 100:.0f}% spendu — dywersyfikuj.")
    if weakest == "single_source_risk":
        if ss_meta.get("single_source_count", 0) > 0:
            tips.append(f"{ss_meta['single_source_count']} produktow bez alternatywy — znajdz drugiego dostawce.")
    if weakest == "esg":
        tips.append("Niski ESG — sprawdz certyfikaty, raporty zrownowazonego rozwoju.")
    if weakest == "compliance":
        tips.append("Niskie compliance — zwerfikuj dokumenty, SLA, historie dostaw.")
    return tips or ["Profil stabilny — bez dzialan awaryjnych."]
