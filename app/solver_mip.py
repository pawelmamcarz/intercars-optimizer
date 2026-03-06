"""
Dedicated MIP Optimization Engine — binary supplier selection with IT-specific constraints.

Goes beyond the generic MIP in optimizer.py by adding:
  C6  Single-vendor-per-competency  — exactly one supplier per product (already binary)
  C7  Hard SLA floor                — supplier.compliance_score ≥ sla_floor to be eligible
  C8  Budget ceiling                — Σ (unit_cost + logistics) · demand · x ≤ total_budget
  C9  Max products per supplier     — limit number of products assigned to one vendor

Uses PuLP with HiGHS backend. Falls back to CBC if HiGHS is unavailable.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import pulp
    HAS_PULP = True
except ImportError:
    HAS_PULP = False

from app.schemas import (
    AllocationRow,
    CriteriaWeights,
    DemandItem,
    ObjectiveBreakdown,
    SolverMode,
    SolverStats,
    SupplierInput,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------

def _minmax(values: np.ndarray) -> np.ndarray:
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-12:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class MipResult:
    """Result from the dedicated MIP engine."""

    success: bool
    message: str = ""
    status: str = "unknown"
    solve_time_ms: float = 0.0
    objective_total: float = 0.0

    # Breakdown
    cost_component: float = 0.0
    time_component: float = 0.0
    compliance_component: float = 0.0
    esg_component: float = 0.0

    # Allocations
    allocations: list[dict] = field(default_factory=list)

    # Diagnostics
    total_cost_pln: float = 0.0
    budget_used_pct: float = 0.0
    suppliers_selected: int = 0
    products_covered: int = 0
    infeasible_products: list[str] = field(default_factory=list)

    # Constraint activity
    sla_floor_active: bool = False
    budget_ceiling_active: bool = False
    max_products_per_supplier_active: bool = False


# ---------------------------------------------------------------------------
# Dedicated MIP Engine
# ---------------------------------------------------------------------------

class MipOptimizationEngine:
    """
    Binary MIP solver with IT-services-specific constraints.

    Beyond the standard constraints (demand, capacity, regional, diversification),
    adds:
      - Hard SLA floor: suppliers below threshold are excluded
      - Budget ceiling: total spend must not exceed budget
      - Max products per supplier: limits workload concentration
    """

    def __init__(
        self,
        suppliers: list[SupplierInput],
        demand: list[DemandItem],
        weights: CriteriaWeights,
        *,
        max_vendor_share: float = 1.0,
        sla_floor: Optional[float] = None,
        total_budget: Optional[float] = None,
        max_products_per_supplier: Optional[int] = None,
    ):
        if not HAS_PULP:
            raise RuntimeError("PuLP is not installed — cannot run MIP optimization")

        self.suppliers = suppliers
        self.demand = demand
        self.weights = weights
        self.max_vendor_share = max_vendor_share
        self.sla_floor = sla_floor
        self.total_budget = total_budget
        self.max_products_per_supplier = max_products_per_supplier

        self.n_sup = len(suppliers)
        self.n_prod = len(demand)

        # Pre-compute matrices
        self._build_matrices()

    def _build_matrices(self) -> None:
        """Build normalised cost/time matrices and feasibility mask."""
        n_s, n_p = self.n_sup, self.n_prod

        # Raw cost/time matrices
        cost_raw = np.zeros((n_s, n_p))
        time_raw = np.zeros((n_s, n_p))
        for i, s in enumerate(self.suppliers):
            for j in range(n_p):
                cost_raw[i, j] = s.unit_cost + s.logistics_cost
                time_raw[i, j] = s.lead_time_days

        self.cost_raw = cost_raw
        self.time_raw = time_raw
        self.cost_norm = _minmax(cost_raw)
        self.time_norm = _minmax(time_raw)

        # Per-supplier scores
        comp_arr = np.array([s.compliance_score for s in self.suppliers])
        esg_arr = np.array([s.esg_score for s in self.suppliers])
        self.compliance_norm = _minmax(comp_arr)
        self.esg_norm = _minmax(esg_arr)

        # Demand vector
        self.demand_qty = np.array([d.demand_qty for d in self.demand])

        # Feasibility mask — regional + SLA
        self.feasible = np.zeros((n_s, n_p), dtype=bool)
        for i, s in enumerate(self.suppliers):
            regions = set(s.served_regions)
            for j, d in enumerate(self.demand):
                if d.destination_region in regions:
                    # C7: SLA floor check
                    if self.sla_floor is not None and s.compliance_score < self.sla_floor:
                        continue
                    self.feasible[i, j] = True

        # Objective coefficients
        lam = self.weights.lambda_param
        w = self.weights
        self.c_obj = np.zeros((n_s, n_p))
        for i in range(n_s):
            for j in range(n_p):
                self.c_obj[i, j] = (
                    lam * w.w_cost * self.cost_norm[i, j]
                    + (1 - lam) * w.w_time * self.time_norm[i, j]
                    + w.w_compliance * (1.0 - self.compliance_norm[i])
                    + w.w_esg * (1.0 - self.esg_norm[i])
                )

    def solve(self) -> MipResult:
        """Run the MIP solver and return structured result."""
        result = MipResult(success=False)
        result.sla_floor_active = self.sla_floor is not None
        result.budget_ceiling_active = self.total_budget is not None
        result.max_products_per_supplier_active = self.max_products_per_supplier is not None

        # Check feasibility — each product must have at least one eligible supplier
        for j in range(self.n_prod):
            if not any(self.feasible[i, j] for i in range(self.n_sup)):
                result.infeasible_products.append(self.demand[j].product_id)

        if result.infeasible_products:
            result.message = (
                f"Infeasible: products {result.infeasible_products} have no eligible supplier. "
                f"Check regional coverage"
                + (f" and SLA floor ≥ {self.sla_floor}" if self.sla_floor else "")
                + "."
            )
            return result

        # Build PuLP model
        model = pulp.LpProblem("INTERCARS_MIP_IT", pulp.LpMinimize)

        # Decision variables: x[i,j] ∈ {0, 1}
        x = {}
        for i in range(self.n_sup):
            for j in range(self.n_prod):
                var_name = f"x_{self.suppliers[i].supplier_id}_{self.demand[j].product_id}"
                x[i, j] = pulp.LpVariable(var_name, cat="Binary")
                # Fix infeasible pairs to zero
                if not self.feasible[i, j]:
                    model += x[i, j] == 0, f"C4_block_{i}_{j}"

        # Objective
        model += (
            pulp.lpSum(
                self.c_obj[i, j] * x[i, j]
                for i in range(self.n_sup)
                for j in range(self.n_prod)
            ),
            "objective",
        )

        # C1: demand coverage — exactly one supplier per product
        for j in range(self.n_prod):
            model += (
                pulp.lpSum(x[i, j] for i in range(self.n_sup)) == 1,
                f"C1_demand_{self.demand[j].product_id}",
            )

        # C2: capacity — Σ_j x[i,j] · D_j ≤ Cap_i
        for i in range(self.n_sup):
            model += (
                pulp.lpSum(
                    x[i, j] * self.demand_qty[j] for j in range(self.n_prod)
                ) <= self.suppliers[i].max_capacity,
                f"C2_cap_{self.suppliers[i].supplier_id}",
            )

        # C3: min order — block if demand < min_order
        for i in range(self.n_sup):
            for j in range(self.n_prod):
                if self.feasible[i, j] and self.suppliers[i].min_order_qty > 0:
                    if self.demand[j].demand_qty < self.suppliers[i].min_order_qty:
                        model += x[i, j] == 0, f"C3_minord_{i}_{j}"

        # C5: vendor diversification
        diversification_active = self.max_vendor_share < 1.0 - 1e-9
        if diversification_active:
            q_total = float(self.demand_qty.sum())
            max_vol = self.max_vendor_share * q_total
            for i in range(self.n_sup):
                model += (
                    pulp.lpSum(
                        x[i, j] * self.demand_qty[j] for j in range(self.n_prod)
                    ) <= max_vol,
                    f"C5_div_{self.suppliers[i].supplier_id}",
                )

        # C8: budget ceiling — Σ (cost_raw · demand · x) ≤ budget
        if self.total_budget is not None:
            model += (
                pulp.lpSum(
                    self.cost_raw[i, j] * self.demand_qty[j] * x[i, j]
                    for i in range(self.n_sup)
                    for j in range(self.n_prod)
                ) <= self.total_budget,
                "C8_budget_ceiling",
            )

        # C9: max products per supplier
        if self.max_products_per_supplier is not None:
            for i in range(self.n_sup):
                model += (
                    pulp.lpSum(x[i, j] for j in range(self.n_prod))
                    <= self.max_products_per_supplier,
                    f"C9_max_products_{self.suppliers[i].supplier_id}",
                )

        # Solve
        t0 = time.perf_counter()
        try:
            solver = pulp.HiGHS_CMD(msg=False, timeLimit=60, gapRel=1e-4, logPath="")
            model.solve(solver)
        except Exception:
            solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, gapRel=1e-4)
            model.solve(solver)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        result.solve_time_ms = round(elapsed_ms, 3)
        result.status = pulp.LpStatus[model.status]

        if model.status != pulp.constants.LpStatusOptimal:
            result.message = (
                f"Solver failed — status: {result.status}. "
                f"Check feasibility: capacity, budget ceiling"
                + (f" ({self.total_budget} PLN)" if self.total_budget else "")
                + f", max_vendor_share={self.max_vendor_share}"
                + (f", max_products_per_supplier={self.max_products_per_supplier}"
                   if self.max_products_per_supplier else "")
                + "."
            )
            return result

        # Extract solution
        result.success = True
        total_cost = 0.0
        suppliers_used = set()
        products_assigned = set()

        cost_comp = time_comp = comp_comp = esg_comp = 0.0

        for i in range(self.n_sup):
            for j in range(self.n_prod):
                val = x[i, j].varValue or 0.0
                if val < 0.5:
                    continue

                s = self.suppliers[i]
                d = self.demand[j]
                qty = d.demand_qty
                line_cost = self.cost_raw[i, j] * qty

                suppliers_used.add(s.supplier_id)
                products_assigned.add(d.product_id)
                total_cost += line_cost

                result.allocations.append({
                    "supplier_id": s.supplier_id,
                    "supplier_name": s.name,
                    "product_id": d.product_id,
                    "allocated_qty": round(qty, 2),
                    "allocated_fraction": 1.0,
                    "unit_cost": s.unit_cost,
                    "logistics_cost": s.logistics_cost,
                    "lead_time_days": s.lead_time_days,
                    "compliance_score": s.compliance_score,
                    "esg_score": s.esg_score,
                    "total_line_cost": round(line_cost, 2),
                })

                # Objective breakdown
                lam = self.weights.lambda_param
                w = self.weights
                cost_comp += lam * w.w_cost * self.cost_norm[i, j]
                time_comp += (1 - lam) * w.w_time * self.time_norm[i, j]
                comp_comp += w.w_compliance * (1.0 - self.compliance_norm[i])
                esg_comp += w.w_esg * (1.0 - self.esg_norm[i])

        result.objective_total = round(cost_comp + time_comp + comp_comp + esg_comp, 8)
        result.cost_component = round(cost_comp, 8)
        result.time_component = round(time_comp, 8)
        result.compliance_component = round(comp_comp, 8)
        result.esg_component = round(esg_comp, 8)

        result.total_cost_pln = round(total_cost, 2)
        result.suppliers_selected = len(suppliers_used)
        result.products_covered = len(products_assigned)
        if self.total_budget and self.total_budget > 0:
            result.budget_used_pct = round(total_cost / self.total_budget * 100, 1)

        result.message = (
            f"MIP solved — {result.suppliers_selected} suppliers selected "
            f"for {result.products_covered} products, "
            f"total cost {result.total_cost_pln} PLN"
            + (f" ({result.budget_used_pct}% of budget)" if self.total_budget else "")
        )
        return result
