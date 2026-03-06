"""
Pareto front generator.

Sweeps λ from 0 to 1 and collects the objective breakdown at each step.
This allows the BI dashboard to render the trade-off curve between
cost and time (and other criteria).
"""
from __future__ import annotations

import logging

from app.schemas import (
    CriteriaWeights,
    DemandItem,
    ParetoPoint,
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
        resp, _ = run_optimization(suppliers, demand, w, mode)
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
