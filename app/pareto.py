"""
Pareto front generator.

Sweeps λ from 0 to 1 and collects the objective breakdown at each step.
This allows the BI dashboard to render the trade-off curve between
cost and time (and other criteria).

v3.0: added generate_pareto_front_xy() for XY scatter (cost PLN vs quality).
"""
from __future__ import annotations

import logging

from app.schemas import (
    CriteriaWeights,
    DemandItem,
    ParetoPoint,
    ParetoPointXY,
    SolverMode,
    SupplierInput,
)
from app.optimizer import run_optimization

logger = logging.getLogger(__name__)


def generate_pareto_front(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    base_weights: CriteriaWeights,
    mode: SolverMode,
    steps: int = 11,
    max_vendor_share: float = 1.0,
) -> list[ParetoPoint]:
    """
    Generate a Pareto front by sweeping λ from 0.0 to 1.0.

    At each step, the optimisation is re-run with the updated λ while
    keeping w_cost, w_time, w_compliance, w_esg fixed.

    Returns a list of ParetoPoint ordered by ascending λ.
    """
    points: list[ParetoPoint] = []
    lambdas = [i / (steps - 1) for i in range(steps)]

    for lam in lambdas:
        w = CriteriaWeights(
            lambda_param=lam,
            w_cost=base_weights.w_cost,
            w_time=base_weights.w_time,
            w_compliance=base_weights.w_compliance,
            w_esg=base_weights.w_esg,
        )
        resp, _ = run_optimization(
            suppliers, demand, w, mode,
            max_vendor_share=max_vendor_share,
        )
        if resp.success:
            points.append(ParetoPoint(
                lambda_param=round(lam, 4),
                objective_total=resp.objective.total,
                cost_component=resp.objective.cost_component,
                time_component=resp.objective.time_component,
                compliance_component=resp.objective.compliance_component,
                esg_component=resp.objective.esg_component,
            ))
        else:
            logger.warning("Pareto sweep: infeasible at λ=%.4f — skipping", lam)

    return points


def generate_pareto_front_xy(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    base_weights: CriteriaWeights,
    mode: SolverMode,
    steps: int = 11,
    max_vendor_share: float = 1.0,
) -> list[ParetoPointXY]:
    """
    Generate XY Pareto front: X = total_cost_pln, Y = weighted_quality.

    Quality = (compliance + esg) / 2 averaged over allocations, weighted by qty.
    Returns ParetoPointXY list for scatter chart rendering.
    """
    points: list[ParetoPointXY] = []
    lambdas = [i / (steps - 1) for i in range(steps)]

    for lam in lambdas:
        w = CriteriaWeights(
            lambda_param=lam,
            w_cost=base_weights.w_cost,
            w_time=base_weights.w_time,
            w_compliance=base_weights.w_compliance,
            w_esg=base_weights.w_esg,
        )
        resp, _ = run_optimization(
            suppliers, demand, w, mode,
            max_vendor_share=max_vendor_share,
        )
        if not resp.success:
            logger.warning("Pareto XY: infeasible at λ=%.4f — skipping", lam)
            continue

        # Compute total cost PLN and weighted quality from allocations
        total_cost = 0.0
        quality_numerator = 0.0
        total_qty = 0.0
        active_suppliers: set[str] = set()

        for a in resp.allocations:
            qty = a.allocated_qty
            total_cost += (a.unit_cost + a.logistics_cost) * qty
            quality_numerator += ((a.compliance_score + a.esg_score) / 2.0) * qty
            total_qty += qty
            if a.allocated_fraction > 0.01:
                active_suppliers.add(a.supplier_id)

        weighted_quality = quality_numerator / total_qty if total_qty > 0 else 0.0

        points.append(ParetoPointXY(
            lambda_param=round(lam, 4),
            total_cost_pln=round(total_cost, 2),
            weighted_quality=round(weighted_quality, 4),
            objective_total=resp.objective.total,
            cost_component=resp.objective.cost_component,
            time_component=resp.objective.time_component,
            compliance_component=resp.objective.compliance_component,
            esg_component=resp.objective.esg_component,
            suppliers_used=len(active_suppliers),
        ))

    return points
