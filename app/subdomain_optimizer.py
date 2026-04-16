"""
subdomain_optimizer.py — Phase B4

Runs the optimizer independently for every subdomain inside a domain
(e.g. parts → brake_systems, filters, suspension), then aggregates the
individual allocations back into domain-level totals.

Why:
- Each subdomain has its own supplier pool in app.data_layer.SUBDOMAIN_DATA
  — a disc-brake vendor is irrelevant for filters. Solving per-subdomain
  keeps the LP narrow, respects that structural separation, and exposes
  which slice drives total spend.
- Compared to solving the whole domain at once, per-subdomain solves
  usually produce tighter (or at least different) allocations because
  diversification / concentration caps are applied inside each bucket
  rather than globally.

The aggregate view powers a dashboard widget ('spend distribution across
subdomains'), plus it feeds future rules like 'subdomain A grew 40% vs
subdomain B this quarter'.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from app.data_layer import get_domain_subdomains, get_subdomain_data
from app.optimizer import run_optimization
from app.schemas import (
    ConstraintConfig,
    CriteriaWeights,
    SolverMode,
)

logger = logging.getLogger(__name__)


def _cost_of(resp) -> float:
    return sum(
        (a.unit_cost + a.logistics_cost) * a.allocated_qty
        for a in resp.allocations
        if a.allocated_fraction > 0.01
    )


def optimize_per_subdomain(
    domain: str,
    base_weights: Optional[CriteriaWeights] = None,
    mode: SolverMode = SolverMode.continuous,
    max_vendor_share: float = 1.0,
    constraints: Optional[ConstraintConfig] = None,
) -> dict:
    """Solve every subdomain in `domain` separately and return per-sub
    breakdown plus aggregated totals.

    Returns
    -------
    dict with keys:
      - domain
      - subdomain_count (successful runs)
      - subdomains: per-sub list of {subdomain, total_cost_pln,
          objective_total, suppliers_used, success, message}
      - aggregate: domain-level rollup {total_cost_pln, unique_suppliers,
          total_allocations, weighted_objective}
      - total_time_ms
    """
    weights = base_weights or CriteriaWeights()
    t0 = time.perf_counter()

    try:
        sub_keys = get_domain_subdomains(domain)
    except ValueError as exc:
        return {"error": True, "message": str(exc), "domain": domain}

    sub_results: list[dict] = []
    agg_cost = 0.0
    agg_allocations = 0
    agg_suppliers: set[str] = set()
    obj_weighted_num = 0.0    # Σ obj × cost
    obj_weighted_denom = 0.0  # Σ cost

    for sub in sub_keys:
        data = get_subdomain_data(domain, sub)
        resp, _ = run_optimization(
            suppliers=data["suppliers"],
            demand=data["demand"],
            weights=weights,
            mode=mode,
            max_vendor_share=max_vendor_share,
            constraints=constraints,
        )
        if not resp.success:
            sub_results.append({
                "subdomain": sub,
                "success": False,
                "message": resp.message,
                "total_cost_pln": 0.0,
                "objective_total": 0.0,
                "suppliers_used": 0,
                "allocations_count": 0,
            })
            continue

        sub_cost = _cost_of(resp)
        sub_sups = {a.supplier_id for a in resp.allocations if a.allocated_fraction > 0.01}
        agg_cost += sub_cost
        agg_allocations += len([a for a in resp.allocations if a.allocated_fraction > 0.01])
        agg_suppliers.update(sub_sups)
        if sub_cost > 0:
            obj_weighted_num += resp.objective.total * sub_cost
            obj_weighted_denom += sub_cost

        sub_results.append({
            "subdomain": sub,
            "success": True,
            "message": resp.message,
            "total_cost_pln": round(sub_cost, 2),
            "objective_total": round(resp.objective.total, 6),
            "cost_component": round(resp.objective.cost_component, 6),
            "time_component": round(resp.objective.time_component, 6),
            "compliance_component": round(resp.objective.compliance_component, 6),
            "esg_component": round(resp.objective.esg_component, 6),
            "suppliers_used": len(sub_sups),
            "allocations_count": len([a for a in resp.allocations if a.allocated_fraction > 0.01]),
            "top_suppliers": _top_supplier_breakdown(resp, limit=3),
        })

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    weighted_obj = (obj_weighted_num / obj_weighted_denom) if obj_weighted_denom else 0.0

    successful = [r for r in sub_results if r["success"]]
    return {
        "domain": domain,
        "subdomain_count": len(successful),
        "subdomain_total": len(sub_keys),
        "aggregate": {
            "total_cost_pln": round(agg_cost, 2),
            "unique_suppliers": len(agg_suppliers),
            "total_allocations": agg_allocations,
            "weighted_objective": round(weighted_obj, 6),
        },
        "subdomains": sub_results,
        "total_time_ms": elapsed_ms,
    }


def _top_supplier_breakdown(resp, limit: int = 3) -> list[dict]:
    """Aggregate allocations by supplier and return the top-N by cost
    contribution."""
    by_sup: dict[str, dict] = {}
    for a in resp.allocations:
        if a.allocated_fraction <= 0.01:
            continue
        entry = by_sup.setdefault(a.supplier_id, {
            "supplier_id": a.supplier_id,
            "supplier_name": a.supplier_name,
            "cost_pln": 0.0,
            "qty": 0.0,
        })
        entry["cost_pln"] += (a.unit_cost + a.logistics_cost) * a.allocated_qty
        entry["qty"] += a.allocated_qty
    rows = sorted(by_sup.values(), key=lambda r: r["cost_pln"], reverse=True)[:limit]
    for r in rows:
        r["cost_pln"] = round(r["cost_pln"], 2)
        r["qty"] = round(r["qty"], 2)
    return rows
