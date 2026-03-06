"""
Core optimisation engine — three-layer pipeline, optimisation layer.

Supports two mathematical modes:
  1. Continuous  — scipy.optimize.linprog(method='highs')
  2. MIP/Binary  — PuLP with HiGHS backend  (x ∈ {0, 1})

Mathematical formulation
========================
Sets
----
  S : suppliers   (indexed i)
  P : products    (indexed j)

Decision variables
------------------
  Continuous:  x[i,j] ∈ [0, 1]   fraction of demand_j fulfilled by supplier i
  MIP:         x[i,j] ∈ {0, 1}   binary selection

Parameters (normalised min-max → [0, 1])
-----------------------------------------
  ĉ[i,j]  — normalised total unit cost   (lower = better → minimise directly)
  t̂[i,j]  — normalised lead-time         (lower = better → minimise directly)
  r̂[i]    — compliance / SLA score       (higher = better → minimise (1 - r̂))
  ê[i]    — ESG / reliability score      (higher = better → minimise (1 - ê))

Objective (minimisation)
------------------------
  min  Σ_{i,j} [ λ·w_c·ĉ[i,j] + (1-λ)·w_t·t̂[i,j]
                  + w_r·(1 - r̂[i]) + w_e·(1 - ê[i]) ] · x[i,j]

Constraints
-----------
  C1  demand coverage :  Σ_i x[i,j] = 1              ∀ j ∈ P
  C2  capacity        :  Σ_j x[i,j]·D_j ≤ Cap_i      ∀ i ∈ S
  C3  min order (cont):  x[i,j]·D_j ≥ MinOrd_ij  OR  x[i,j] = 0
  C4  regional block  :  x[i,j] = 0  if region(j) ∉ served_regions(i)
  C5  diversification :  Σ_j x[i,j]·D_j ≤ α·Q_total  ∀ i ∈ S   (α = max_vendor_share)
"""
from __future__ import annotations

import io
import logging
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import linprog

try:
    import pulp
    HAS_PULP = True
except ImportError:
    HAS_PULP = False

from app.schemas import (
    AllocationRow,
    ConstraintConfig,
    ConstraintLog,
    CriteriaWeights,
    DemandItem,
    IterationLog,
    ObjectiveBreakdown,
    OptimizationResponse,
    SolverMode,
    SolverStats,
    SupplierInput,
    VariableLog,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _minmax(values: np.ndarray) -> np.ndarray:
    """Min-max normalisation to [0, 1]. Returns zeros for constant arrays."""
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-12:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


# ---------------------------------------------------------------------------
# Problem builder — shared between both solvers
# ---------------------------------------------------------------------------

@dataclass
class _Problem:
    """Pre-processed, normalised optimisation problem."""

    n_sup: int
    n_prod: int
    sup: list[SupplierInput]
    dem: list[DemandItem]
    weights: CriteriaWeights
    max_vendor_share: float = 1.0  # 1.0 = disabled
    constraints: Optional[ConstraintConfig] = None

    # Cost matrix (n_sup × n_prod) — normalised
    cost_norm: np.ndarray = field(default_factory=lambda: np.empty(0))
    # Lead-time matrix — normalised
    time_norm: np.ndarray = field(default_factory=lambda: np.empty(0))
    # Per-supplier scores (already 0..1 but we still normalise across set)
    compliance_norm: np.ndarray = field(default_factory=lambda: np.empty(0))
    esg_norm: np.ndarray = field(default_factory=lambda: np.empty(0))

    # Raw matrices (for reporting)
    cost_raw: np.ndarray = field(default_factory=lambda: np.empty(0))
    time_raw: np.ndarray = field(default_factory=lambda: np.empty(0))

    # Feasibility mask (n_sup × n_prod) — True if supplier can serve product
    feasible: np.ndarray = field(default_factory=lambda: np.empty(0))

    # Demand vector
    demand_qty: np.ndarray = field(default_factory=lambda: np.empty(0))

    # Objective coefficient vector (flattened i*n_prod + j)
    c_obj: np.ndarray = field(default_factory=lambda: np.empty(0))

    def flat_idx(self, i: int, j: int) -> int:
        return i * self.n_prod + j


def _build_problem(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    weights: CriteriaWeights,
    max_vendor_share: float = 1.0,
    constraints: Optional[ConstraintConfig] = None,
) -> _Problem:
    n_s = len(suppliers)
    n_p = len(demand)
    p = _Problem(
        n_sup=n_s, n_prod=n_p, sup=suppliers, dem=demand,
        weights=weights, max_vendor_share=max_vendor_share,
        constraints=constraints,
    )

    # --- raw matrices (n_s × n_p) ---
    cost_raw = np.zeros((n_s, n_p))
    time_raw = np.zeros((n_s, n_p))
    for i, s in enumerate(suppliers):
        for j in range(n_p):
            cost_raw[i, j] = s.unit_cost + s.logistics_cost
            time_raw[i, j] = s.lead_time_days

    p.cost_raw = cost_raw
    p.time_raw = time_raw
    p.cost_norm = _minmax(cost_raw)
    p.time_norm = _minmax(time_raw)

    # compliance & ESG — normalise across supplier set
    comp_arr = np.array([s.compliance_score for s in suppliers])
    esg_arr = np.array([s.esg_score for s in suppliers])
    p.compliance_norm = _minmax(comp_arr)
    p.esg_norm = _minmax(esg_arr)

    # demand vector
    p.demand_qty = np.array([d.demand_qty for d in demand])

    # feasibility mask based on regional availability
    p.feasible = np.zeros((n_s, n_p), dtype=bool)
    for i, s in enumerate(suppliers):
        regions = set(s.served_regions)
        for j, d in enumerate(demand):
            if d.destination_region in regions:
                p.feasible[i, j] = True

    # objective vector
    lam = weights.lambda_param
    c_vec = np.zeros(n_s * n_p)
    for i in range(n_s):
        for j in range(n_p):
            cost_part = lam * weights.w_cost * p.cost_norm[i, j]
            time_part = (1 - lam) * weights.w_time * p.time_norm[i, j]
            # Higher compliance/ESG = better → minimise (1 - normalised)
            comp_part = weights.w_compliance * (1.0 - p.compliance_norm[i])
            esg_part = weights.w_esg * (1.0 - p.esg_norm[i])
            c_vec[p.flat_idx(i, j)] = cost_part + time_part + comp_part + esg_part
    p.c_obj = c_vec

    # C15: preferred supplier bonus — reduce objective for preferred suppliers
    if constraints and constraints.preferred_supplier_bonus > 0:
        bonus = constraints.preferred_supplier_bonus
        for i, s in enumerate(suppliers):
            if getattr(s, "is_preferred", False):
                for j in range(n_p):
                    idx = p.flat_idx(i, j)
                    p.c_obj[idx] *= (1.0 - bonus)

    return p


# ---------------------------------------------------------------------------
# Continuous solver  — scipy linprog (HiGHS)
# ---------------------------------------------------------------------------

@dataclass
class _SolverDiagnostics:
    """Captures raw solver output for Stealth mode."""
    raw_log: str = ""
    variables: list[VariableLog] = field(default_factory=list)
    constraints: list[ConstraintLog] = field(default_factory=list)
    iterations: list[IterationLog] = field(default_factory=list)
    objective_equation: str = ""


def _solve_continuous(
    prob: _Problem,
    *,
    capture_diagnostics: bool = False,
) -> tuple[Optional[np.ndarray], str, int, float, _SolverDiagnostics]:
    """
    Solve the LP relaxation using scipy.optimize.linprog(method='highs').

    Includes:
      C1: demand coverage (equality)
      C2: capacity (inequality)
      C4: regional block (bounds)
      C5: vendor diversification (inequality)

    Returns (x_solution, status_str, iterations, solve_time_ms, diagnostics).
    """
    n = prob.n_sup * prob.n_prod

    # --- bounds ---
    bounds: list[tuple[float, float]] = []
    for i in range(prob.n_sup):
        for j in range(prob.n_prod):
            if not prob.feasible[i, j]:
                # C4: regional block
                bounds.append((0.0, 0.0))
            else:
                bounds.append((0.0, 1.0))

    # --- equality constraints: C1 — Σ_i x[i,j] = 1 for each j ---
    A_eq = np.zeros((prob.n_prod, n))
    b_eq = np.ones(prob.n_prod)
    for j in range(prob.n_prod):
        for i in range(prob.n_sup):
            A_eq[j, prob.flat_idx(i, j)] = 1.0

    # --- inequality constraints ---
    ineq_rows = []
    ineq_rhs = []

    # C2: capacity — Σ_j x[i,j]·D_j ≤ Cap_i
    for i in range(prob.n_sup):
        row = np.zeros(n)
        for j in range(prob.n_prod):
            row[prob.flat_idx(i, j)] = prob.demand_qty[j]
        ineq_rows.append(row)
        ineq_rhs.append(prob.sup[i].max_capacity)

    # C5: vendor diversification — Σ_j x[i,j]·D_j ≤ α·Q_total
    diversification_active = prob.max_vendor_share < 1.0 - 1e-9
    q_total = float(prob.demand_qty.sum())
    if diversification_active:
        max_vol = prob.max_vendor_share * q_total
        for i in range(prob.n_sup):
            row = np.zeros(n)
            for j in range(prob.n_prod):
                row[prob.flat_idx(i, j)] = prob.demand_qty[j]
            ineq_rows.append(row)
            ineq_rhs.append(max_vol)

    # ── v3.0 Constraints C10–C14 ────────────────────────────────
    cc = prob.constraints  # Optional[ConstraintConfig]

    # C14: contract lock-in — set lower bound for suppliers with contract_min_allocation > 0
    if cc:
        for i, s in enumerate(prob.sup):
            cma = getattr(s, "contract_min_allocation", 0.0)
            if cma > 0:
                for j in range(prob.n_prod):
                    idx = prob.flat_idx(i, j)
                    lo, hi = bounds[idx]
                    if hi > 0:  # only if feasible
                        bounds[idx] = (max(lo, cma), hi)

    # C11: geographic diversity — Σ_{i in region(r)} Σ_j x[i,j] ≥ ε  for each required region
    if cc and cc.min_geographic_regions is not None:
        region_to_suppliers: dict[str, list[int]] = {}
        for i, s in enumerate(prob.sup):
            rc = getattr(s, "region_code", None)
            if rc:
                region_to_suppliers.setdefault(rc, []).append(i)
        # We require at least min_geographic_regions distinct regions to have allocation
        # Implemented as: for each region, add a ≥ ε constraint (soft via ≤ with negation)
        eps = 0.01  # minimum allocation fraction from region
        for _region, sup_indices in region_to_suppliers.items():
            # -Σ x[i,j] ≤ -ε  →  Σ x[i,j] ≥ ε
            row = np.zeros(n)
            for i in sup_indices:
                for j in range(prob.n_prod):
                    row[prob.flat_idx(i, j)] = -1.0
            ineq_rows.append(row)
            ineq_rhs.append(-eps)

    # C12: ESG floor — Σ_i (esg_i · Σ_j x[i,j]·D_j) ≥ min_esg · Q_total
    if cc and cc.min_esg_score is not None:
        # -Σ esg_i · D_j · x[i,j] ≤ -min_esg · Q_total
        row = np.zeros(n)
        for i in range(prob.n_sup):
            esg_i = prob.sup[i].esg_score
            for j in range(prob.n_prod):
                row[prob.flat_idx(i, j)] = -esg_i * prob.demand_qty[j]
        ineq_rows.append(row)
        ineq_rhs.append(-cc.min_esg_score * q_total)

    # C13: payment terms cap — Σ_i (pay_days_i · Σ_j x[i,j]·D_j) ≤ max_days · Q_total
    if cc and cc.max_payment_terms_days is not None:
        row = np.zeros(n)
        for i in range(prob.n_sup):
            pay_days = getattr(prob.sup[i], "payment_terms_days", 30.0)
            for j in range(prob.n_prod):
                row[prob.flat_idx(i, j)] = pay_days * prob.demand_qty[j]
        ineq_rows.append(row)
        ineq_rhs.append(cc.max_payment_terms_days * q_total)

    A_ub = np.array(ineq_rows) if ineq_rows else np.zeros((0, n))
    b_ub = np.array(ineq_rhs) if ineq_rhs else np.zeros(0)

    diag = _SolverDiagnostics()

    # build equation string
    if capture_diagnostics:
        terms = []
        for i in range(prob.n_sup):
            for j in range(prob.n_prod):
                k = prob.flat_idx(i, j)
                coeff = prob.c_obj[k]
                if coeff > 1e-12:
                    terms.append(
                        f"{coeff:.6f}·x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]"
                    )
        diag.objective_equation = "min  " + " + ".join(terms[:50])
        if len(terms) > 50:
            diag.objective_equation += f"  ... (+{len(terms)-50} more terms)"

    t0 = time.perf_counter()

    # Capture HiGHS output
    log_buffer = io.StringIO()
    options = {"disp": capture_diagnostics, "time_limit": 60.0, "presolve": True}

    with redirect_stdout(log_buffer):
        result = linprog(
            c=prob.c_obj,
            A_ub=A_ub if A_ub.size > 0 else None,
            b_ub=b_ub if b_ub.size > 0 else None,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
            options=options,
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    diag.raw_log = log_buffer.getvalue()

    if capture_diagnostics and result.x is not None:
        for i in range(prob.n_sup):
            for j in range(prob.n_prod):
                k = prob.flat_idx(i, j)
                diag.variables.append(VariableLog(
                    name=f"x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]",
                    value=float(result.x[k]),
                    reduced_cost=None,
                ))

        # Document demand coverage constraints
        for j in range(prob.n_prod):
            lhs = " + ".join(
                f"x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]"
                for i in range(prob.n_sup)
            )
            diag.constraints.append(ConstraintLog(
                name=f"C1_demand_{prob.dem[j].product_id}",
                expression=lhs,
                bound="= 1.0",
            ))
        # Document capacity constraints
        for i in range(prob.n_sup):
            lhs_parts = []
            for j in range(prob.n_prod):
                lhs_parts.append(
                    f"{prob.demand_qty[j]:.0f}·x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]"
                )
            diag.constraints.append(ConstraintLog(
                name=f"C2_capacity_{prob.sup[i].supplier_id}",
                expression=" + ".join(lhs_parts),
                bound=f"≤ {prob.sup[i].max_capacity:.0f}",
            ))
        # Document diversification constraints
        if diversification_active:
            q_total = float(prob.demand_qty.sum())
            for i in range(prob.n_sup):
                lhs_parts = []
                for j in range(prob.n_prod):
                    lhs_parts.append(
                        f"{prob.demand_qty[j]:.0f}·x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]"
                    )
                diag.constraints.append(ConstraintLog(
                    name=f"C5_diversification_{prob.sup[i].supplier_id}",
                    expression=" + ".join(lhs_parts),
                    bound=f"≤ {prob.max_vendor_share * q_total:.0f} ({prob.max_vendor_share*100:.0f}% of {q_total:.0f})",
                ))

        diag.iterations.append(IterationLog(
            iteration=result.nit,
            objective_value=float(result.fun) if result.fun is not None else 0.0,
        ))

    if result.success:
        # C10: min supplier count — advisory (log warning, don't fail)
        if prob.constraints and prob.constraints.min_supplier_count is not None:
            active_sups = set()
            for i in range(prob.n_sup):
                for j in range(prob.n_prod):
                    if result.x[prob.flat_idx(i, j)] > 1e-6:
                        active_sups.add(i)
            if len(active_sups) < prob.constraints.min_supplier_count:
                logger.warning(
                    "C10 advisory: only %d active suppliers (min requested: %d)",
                    len(active_sups), prob.constraints.min_supplier_count,
                )
        return result.x, "optimal", result.nit, elapsed_ms, diag
    return None, result.message, result.nit, elapsed_ms, diag


# ---------------------------------------------------------------------------
# MIP solver — PuLP + HiGHS
# ---------------------------------------------------------------------------

def _solve_mip(
    prob: _Problem,
    *,
    capture_diagnostics: bool = False,
) -> tuple[Optional[np.ndarray], str, int, float, _SolverDiagnostics]:
    """
    Solve the binary (MIP) formulation using PuLP backed by HiGHS.

    x[i,j] ∈ {0, 1} — supplier i is either selected or not for product j.
    C5 diversification also applies: total volume per supplier ≤ α·Q_total.

    Returns (x_solution, status_str, iterations, solve_time_ms, diagnostics).
    """
    if not HAS_PULP:
        raise RuntimeError(
            "PuLP is not installed. Install it with: pip install PuLP"
        )

    model = pulp.LpProblem("INTERCARS_MIP", pulp.LpMinimize)
    diag = _SolverDiagnostics()

    # Decision variables
    x = {}
    for i in range(prob.n_sup):
        for j in range(prob.n_prod):
            var_name = f"x_{prob.sup[i].supplier_id}_{prob.dem[j].product_id}"
            if not prob.feasible[i, j]:
                # C4: regional block — fix to zero
                x[i, j] = pulp.LpVariable(var_name, cat="Binary")
                model += x[i, j] == 0, f"C4_regional_block_{i}_{j}"
            else:
                x[i, j] = pulp.LpVariable(var_name, cat="Binary")

    # Objective
    obj_expr = pulp.lpSum(
        prob.c_obj[prob.flat_idx(i, j)] * x[i, j]
        for i in range(prob.n_sup)
        for j in range(prob.n_prod)
    )
    model += obj_expr, "total_weighted_objective"

    # C1: demand coverage — exactly one supplier per product
    for j in range(prob.n_prod):
        model += (
            pulp.lpSum(x[i, j] for i in range(prob.n_sup)) == 1,
            f"C1_demand_{prob.dem[j].product_id}",
        )

    # C2: capacity constraints
    for i in range(prob.n_sup):
        model += (
            pulp.lpSum(
                x[i, j] * prob.demand_qty[j] for j in range(prob.n_prod)
            ) <= prob.sup[i].max_capacity,
            f"C2_capacity_{prob.sup[i].supplier_id}",
        )

    # C3: min-order — if selected, demand must exceed min_order
    for i in range(prob.n_sup):
        for j in range(prob.n_prod):
            if prob.feasible[i, j] and prob.sup[i].min_order_qty > 0:
                if prob.dem[j].demand_qty < prob.sup[i].min_order_qty:
                    model += (
                        x[i, j] == 0,
                        f"C3_min_order_block_{i}_{j}",
                    )

    # C5: vendor diversification — Σ_j x[i,j]·D_j ≤ α·Q_total
    diversification_active = prob.max_vendor_share < 1.0 - 1e-9
    if diversification_active:
        q_total = float(prob.demand_qty.sum())
        max_vol = prob.max_vendor_share * q_total
        for i in range(prob.n_sup):
            model += (
                pulp.lpSum(
                    x[i, j] * prob.demand_qty[j] for j in range(prob.n_prod)
                ) <= max_vol,
                f"C5_diversification_{prob.sup[i].supplier_id}",
            )

    # Build equation string for stealth
    if capture_diagnostics:
        terms = []
        for i in range(prob.n_sup):
            for j in range(prob.n_prod):
                k = prob.flat_idx(i, j)
                coeff = prob.c_obj[k]
                if coeff > 1e-12:
                    terms.append(
                        f"{coeff:.6f}·x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]"
                    )
        diag.objective_equation = "min  " + " + ".join(terms[:50])
        if len(terms) > 50:
            diag.objective_equation += f"  ... (+{len(terms)-50} more terms)"

    # Solve
    t0 = time.perf_counter()
    try:
        solver = pulp.HiGHS_CMD(msg=True, timeLimit=60, gapRel=1e-4, logPath="")
        model.solve(solver)
    except Exception:
        # Fallback to default CBC if HiGHS CMD not available
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, gapRel=1e-4)
        model.solve(solver)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    status = pulp.LpStatus[model.status]

    # Extract solution
    x_sol = np.zeros(prob.n_sup * prob.n_prod)
    if model.status == pulp.constants.LpStatusOptimal:
        for i in range(prob.n_sup):
            for j in range(prob.n_prod):
                val = x[i, j].varValue or 0.0
                x_sol[prob.flat_idx(i, j)] = val
    else:
        x_sol = None  # type: ignore[assignment]

    if capture_diagnostics:
        if x_sol is not None:
            for i in range(prob.n_sup):
                for j in range(prob.n_prod):
                    val = x[i, j].varValue or 0.0
                    diag.variables.append(VariableLog(
                        name=f"x[{prob.sup[i].supplier_id},{prob.dem[j].product_id}]",
                        value=float(val),
                        reduced_cost=None,
                    ))

        for name, c in model.constraints.items():
            diag.constraints.append(ConstraintLog(
                name=name,
                expression=str(c),
                bound=f"{'=' if c.sense == 0 else '≤' if c.sense <= 0 else '≥'} {c.constant}",
                slack=float(c.slack) if c.slack is not None else None,
            ))

        obj_val = pulp.value(model.objective) if model.objective else 0.0
        diag.iterations.append(IterationLog(
            iteration=0,
            objective_value=float(obj_val),
        ))
        diag.raw_log = f"PuLP/HiGHS MIP — Status: {status}, Obj: {obj_val}"

    iterations = 0
    return x_sol, status, iterations, elapsed_ms, diag


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

def _build_response(
    prob: _Problem,
    x_sol: np.ndarray,
    status: str,
    iterations: int,
    solve_time_ms: float,
    mode: SolverMode,
) -> OptimizationResponse:
    allocations: list[AllocationRow] = []
    cost_comp = time_comp = comp_comp = esg_comp = 0.0

    for i in range(prob.n_sup):
        for j in range(prob.n_prod):
            frac = float(x_sol[prob.flat_idx(i, j)])
            if frac < 1e-9:
                continue
            qty = frac * prob.dem[j].demand_qty
            allocations.append(AllocationRow(
                supplier_id=prob.sup[i].supplier_id,
                supplier_name=prob.sup[i].name,
                product_id=prob.dem[j].product_id,
                allocated_qty=round(qty, 2),
                allocated_fraction=round(frac, 6),
                unit_cost=prob.sup[i].unit_cost,
                logistics_cost=prob.sup[i].logistics_cost,
                lead_time_days=prob.sup[i].lead_time_days,
                compliance_score=prob.sup[i].compliance_score,
                esg_score=prob.sup[i].esg_score,
            ))
            lam = prob.weights.lambda_param
            w = prob.weights
            cost_comp += lam * w.w_cost * prob.cost_norm[i, j] * frac
            time_comp += (1 - lam) * w.w_time * prob.time_norm[i, j] * frac
            comp_comp += w.w_compliance * (1.0 - prob.compliance_norm[i]) * frac
            esg_comp += w.w_esg * (1.0 - prob.esg_norm[i]) * frac

    total_obj = cost_comp + time_comp + comp_comp + esg_comp
    diversification_active = prob.max_vendor_share < 1.0 - 1e-9

    return OptimizationResponse(
        success=True,
        message=f"Optimisation completed — {mode.value} mode, status: {status}"
                + (f", diversification ≤{prob.max_vendor_share*100:.0f}%" if diversification_active else ""),
        solver_stats=SolverStats(
            status=status,
            iterations=iterations,
            solve_time_ms=round(solve_time_ms, 3),
            mode=mode,
            diversification_active=diversification_active,
            max_vendor_share=prob.max_vendor_share,
        ),
        objective=ObjectiveBreakdown(
            total=round(total_obj, 8),
            cost_component=round(cost_comp, 8),
            time_component=round(time_comp, 8),
            compliance_component=round(comp_comp, 8),
            esg_component=round(esg_comp, 8),
        ),
        allocations=allocations,
        weights_used=prob.weights,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_optimization(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    weights: CriteriaWeights,
    mode: SolverMode = SolverMode.continuous,
    *,
    max_vendor_share: float = 1.0,
    capture_diagnostics: bool = False,
    constraints: Optional[ConstraintConfig] = None,
) -> tuple[OptimizationResponse, _SolverDiagnostics]:
    """
    Main entry point for the optimisation layer.

    Args:
        max_vendor_share: Maximum fraction of total volume any single supplier
                          can receive. 0.6 = 60%. Set to 1.0 to disable.
        constraints: Optional v3.0 constraint config (C10-C15).

    Returns (response, diagnostics).
    """
    prob = _build_problem(suppliers, demand, weights, max_vendor_share=max_vendor_share,
                          constraints=constraints)

    if mode == SolverMode.continuous:
        x_sol, status, iters, elapsed, diag = _solve_continuous(
            prob, capture_diagnostics=capture_diagnostics,
        )
    else:
        x_sol, status, iters, elapsed, diag = _solve_mip(
            prob, capture_diagnostics=capture_diagnostics,
        )

    if x_sol is None:
        fail_resp = OptimizationResponse(
            success=False,
            message=f"Solver failed — {status}. Check feasibility: are all regions "
                    f"covered by at least one supplier? Do capacities meet demand? "
                    f"Is max_vendor_share={max_vendor_share} too restrictive?",
            solver_stats=SolverStats(
                status=status, iterations=iters,
                solve_time_ms=round(elapsed, 3), mode=mode,
                diversification_active=max_vendor_share < 1.0 - 1e-9,
                max_vendor_share=max_vendor_share,
            ),
            objective=ObjectiveBreakdown(
                total=0, cost_component=0, time_component=0,
                compliance_component=0, esg_component=0,
            ),
            allocations=[],
            weights_used=weights,
        )
        return fail_resp, diag

    resp = _build_response(prob, x_sol, status, iters, elapsed, mode)
    return resp, diag


def get_supplier_profiles(
    suppliers: list[SupplierInput],
    demand: list[DemandItem],
    weights: CriteriaWeights,
    x_sol_response: OptimizationResponse,
) -> list:
    """Build per-supplier radar-chart profiles from the solution."""
    from app.schemas import SupplierRadarProfile

    # Compute normalised values
    costs = np.array([s.unit_cost + s.logistics_cost for s in suppliers])
    times = np.array([s.lead_time_days for s in suppliers])
    cost_n = _minmax(costs)
    time_n = _minmax(times)
    comp_arr = np.array([s.compliance_score for s in suppliers])
    esg_arr = np.array([s.esg_score for s in suppliers])
    comp_n = _minmax(comp_arr)
    esg_n = _minmax(esg_arr)

    # Compute total allocation per supplier
    alloc_map: dict[str, float] = {}
    total_demand = sum(d.demand_qty for d in demand)
    for row in x_sol_response.allocations:
        alloc_map[row.supplier_id] = alloc_map.get(row.supplier_id, 0) + row.allocated_qty

    profiles = []
    for i, s in enumerate(suppliers):
        total_frac = alloc_map.get(s.supplier_id, 0) / total_demand if total_demand else 0
        profiles.append(SupplierRadarProfile(
            supplier_id=s.supplier_id,
            supplier_name=s.name,
            cost_norm=round(float(1.0 - cost_n[i]), 4),   # invert: higher = cheaper = better
            time_norm=round(float(1.0 - time_n[i]), 4),   # invert: higher = faster = better
            compliance_norm=round(float(comp_n[i]), 4),
            esg_norm=round(float(esg_n[i]), 4),
            total_allocated_fraction=round(total_frac, 6),
        ))
    return profiles
