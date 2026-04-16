"""
Pareto front generator.

Sweeps λ from 0 to 1 and collects the objective breakdown at each step.
This allows the BI dashboard to render the trade-off curve between
cost and time (and other criteria).

v3.0: added generate_pareto_front_xy() for XY scatter (cost PLN vs quality).
"""
from __future__ import annotations

import logging

import math
import random

from app.schemas import (
    CriteriaWeights,
    DemandItem,
    ParetoPoint,
    ParetoPointMC,
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


def _perturb(suppliers, rng, cost_std, time_std):
    """In-place copy of suppliers with log-normal noise on cost & lead time."""
    out = []
    for s in suppliers:
        cost_factor = math.exp(rng.gauss(0, cost_std))
        time_factor = math.exp(rng.gauss(0, time_std))
        copy = s.model_copy(update={
            "unit_cost": s.unit_cost * cost_factor,
            "logistics_cost": s.logistics_cost * cost_factor,
            "lead_time_days": max(1.0, s.lead_time_days * time_factor),
        })
        out.append(copy)
    return out


def generate_pareto_with_mc(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    base_weights: CriteriaWeights,
    mode: SolverMode,
    steps: int = 11,
    max_vendor_share: float = 1.0,
    mc_iterations: int = 50,
    cost_std_pct: float = 0.10,
    time_std_pct: float = 0.15,
    seed: int = 42,
) -> list[ParetoPointMC]:
    """Phase B2 — generate the Pareto front *with* Monte Carlo cost dispersion.

    For each λ step we solve the LP once (baseline), then re-solve
    `mc_iterations` times with log-normally perturbed cost + lead-time
    factors. The P5/mean/P95 of the realised total_cost_pln distribution
    are stored on the point so the UI can shade a confidence band around
    the deterministic curve. Feasibility rate lets us flag λ points where
    the allocation becomes brittle under noise.

    Default 50 iterations × 11 λ points ≈ 550 LP solves — on HiGHS that
    runs in a few seconds, well below the user-perceived boundary. Bump
    `mc_iterations` to 200 for tighter bands when you can afford it.
    """
    rng = random.Random(seed)
    out: list[ParetoPointMC] = []
    lambdas = [i / (steps - 1) for i in range(steps)]

    for lam in lambdas:
        w = CriteriaWeights(
            lambda_param=lam,
            w_cost=base_weights.w_cost,
            w_time=base_weights.w_time,
            w_compliance=base_weights.w_compliance,
            w_esg=base_weights.w_esg,
        )
        # Baseline (deterministic) solve — same as vanilla XY front
        baseline, _ = run_optimization(
            suppliers, demand, w, mode, max_vendor_share=max_vendor_share,
        )
        if not baseline.success:
            logger.warning("Pareto+MC: baseline infeasible at λ=%.4f — skipping", lam)
            continue

        base_cost = sum(
            (a.unit_cost + a.logistics_cost) * a.allocated_qty
            for a in baseline.allocations if a.allocated_fraction > 0.01
        )
        quality_num = 0.0
        total_qty = 0.0
        active: set[str] = set()
        for a in baseline.allocations:
            quality_num += ((a.compliance_score + a.esg_score) / 2.0) * a.allocated_qty
            total_qty += a.allocated_qty
            if a.allocated_fraction > 0.01:
                active.add(a.supplier_id)
        quality = quality_num / total_qty if total_qty else 0.0

        # Monte Carlo ring around the baseline
        realised: list[float] = []
        feasible = 0
        for _ in range(mc_iterations):
            psup = _perturb(suppliers, rng, cost_std_pct, time_std_pct)
            resp, _ = run_optimization(
                psup, demand, w, mode, max_vendor_share=max_vendor_share,
            )
            if not resp.success:
                continue
            feasible += 1
            realised.append(sum(
                (a.unit_cost + a.logistics_cost) * a.allocated_qty
                for a in resp.allocations if a.allocated_fraction > 0.01
            ))

        if realised:
            realised.sort()
            n = len(realised)
            mean = sum(realised) / n
            p5 = realised[max(0, int(n * 0.05))]
            p95 = realised[min(n - 1, int(n * 0.95))]
        else:
            mean = base_cost
            p5 = p95 = base_cost

        out.append(ParetoPointMC(
            lambda_param=round(lam, 4),
            total_cost_pln=round(base_cost, 2),
            weighted_quality=round(quality, 4),
            objective_total=baseline.objective.total,
            cost_component=baseline.objective.cost_component,
            time_component=baseline.objective.time_component,
            compliance_component=baseline.objective.compliance_component,
            esg_component=baseline.objective.esg_component,
            suppliers_used=len(active),
            cost_mean_pln=round(mean, 2),
            cost_p5_pln=round(p5, 2),
            cost_p95_pln=round(p95, 2),
            feasible_rate=round(feasible / mc_iterations if mc_iterations else 0, 4),
            mc_iterations=mc_iterations,
        ))

    return out
