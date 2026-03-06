"""
What-If Scenario Engine — run multiple optimisation scenarios and compare results.

Accepts 2-10 scenario specifications, runs each through LP or MIP solver,
and returns a structured comparison matrix for decision-makers.
"""
from __future__ import annotations

import time
from typing import Optional

from app.optimizer import run_optimization
from app.schemas import (
    CriteriaWeights,
    DemandItem,
    SolverMode,
    SupplierInput,
)

try:
    from app.solver_mip import MipOptimizationEngine
    HAS_MIP = True
except Exception:
    HAS_MIP = False


# ---------------------------------------------------------------------------
# Data classes for scenario results
# ---------------------------------------------------------------------------

class ScenarioResult:
    """Result of a single scenario run."""

    __slots__ = (
        "label", "mode", "success", "message", "objective_total",
        "cost_component", "time_component", "compliance_component",
        "esg_component", "total_cost_pln", "suppliers_used",
        "products_covered", "solve_time_ms", "allocations",
    )

    def __init__(self, label: str, mode: str):
        self.label = label
        self.mode = mode
        self.success = False
        self.message = ""
        self.objective_total = 0.0
        self.cost_component = 0.0
        self.time_component = 0.0
        self.compliance_component = 0.0
        self.esg_component = 0.0
        self.total_cost_pln = 0.0
        self.suppliers_used = 0
        self.products_covered = 0
        self.solve_time_ms = 0.0
        self.allocations: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "mode": self.mode,
            "success": self.success,
            "message": self.message,
            "objective_total": self.objective_total,
            "cost_component": self.cost_component,
            "time_component": self.time_component,
            "compliance_component": self.compliance_component,
            "esg_component": self.esg_component,
            "total_cost_pln": self.total_cost_pln,
            "suppliers_used": self.suppliers_used,
            "products_covered": self.products_covered,
            "solve_time_ms": self.solve_time_ms,
            "allocations_count": len(self.allocations),
        }


# ---------------------------------------------------------------------------
# What-If Engine
# ---------------------------------------------------------------------------

class WhatIfEngine:
    """
    Run multiple optimisation scenarios and produce comparison matrix.

    Each scenario can vary: lambda, weights, mode (LP/MIP), budget,
    SLA floor, max_vendor_share, max_products_per_supplier.
    """

    def __init__(
        self,
        suppliers: list[SupplierInput],
        demand: list[DemandItem],
    ):
        self.suppliers = suppliers
        self.demand = demand

    def run_scenario(
        self,
        label: str,
        *,
        weights: Optional[CriteriaWeights] = None,
        mode: str = "continuous",
        max_vendor_share: float = 1.0,
        sla_floor: Optional[float] = None,
        total_budget: Optional[float] = None,
        max_products_per_supplier: Optional[int] = None,
    ) -> ScenarioResult:
        """Run a single scenario and return structured result."""
        w = weights or CriteriaWeights()
        result = ScenarioResult(label=label, mode=mode)

        if mode == "mip" and HAS_MIP:
            return self._run_mip(result, w, max_vendor_share, sla_floor, total_budget, max_products_per_supplier)
        else:
            return self._run_lp(result, w, max_vendor_share)

    def _run_lp(self, result: ScenarioResult, w: CriteriaWeights, max_vendor_share: float) -> ScenarioResult:
        try:
            resp, _ = run_optimization(
                suppliers=self.suppliers,
                demand=self.demand,
                weights=w,
                mode=SolverMode.continuous,
                max_vendor_share=max_vendor_share,
            )
            result.success = resp.success
            result.message = resp.message
            result.objective_total = round(resp.objective.total, 6)
            result.cost_component = round(resp.objective.cost_component, 6)
            result.time_component = round(resp.objective.time_component, 6)
            result.compliance_component = round(resp.objective.compliance_component, 6)
            result.esg_component = round(resp.objective.esg_component, 6)
            result.solve_time_ms = resp.solver_stats.solve_time_ms
            result.suppliers_used = len(set(a.supplier_id for a in resp.allocations if a.allocated_fraction > 0.001))
            result.products_covered = len(set(a.product_id for a in resp.allocations if a.allocated_fraction > 0.001))
            result.total_cost_pln = round(sum(
                (a.unit_cost + a.logistics_cost) * a.allocated_qty for a in resp.allocations
            ), 2)
            result.allocations = [a.model_dump() for a in resp.allocations]
        except Exception as e:
            result.message = f"LP failed: {e}"
        return result

    def _run_mip(
        self, result: ScenarioResult, w: CriteriaWeights,
        max_vendor_share: float,
        sla_floor: Optional[float],
        total_budget: Optional[float],
        max_products_per_supplier: Optional[int],
    ) -> ScenarioResult:
        try:
            engine = MipOptimizationEngine(
                suppliers=self.suppliers,
                demand=self.demand,
                weights=w,
                max_vendor_share=max_vendor_share,
                sla_floor=sla_floor,
                total_budget=total_budget,
                max_products_per_supplier=max_products_per_supplier,
            )
            mip_res = engine.solve()
            result.success = mip_res.success
            result.message = mip_res.message
            result.objective_total = round(mip_res.objective_total, 6)
            result.cost_component = round(mip_res.cost_component, 6)
            result.time_component = round(mip_res.time_component, 6)
            result.compliance_component = round(mip_res.compliance_component, 6)
            result.esg_component = round(mip_res.esg_component, 6)
            result.total_cost_pln = mip_res.total_cost_pln
            result.suppliers_used = mip_res.suppliers_selected
            result.products_covered = mip_res.products_covered
            result.solve_time_ms = mip_res.solve_time_ms
            result.allocations = mip_res.allocations
        except Exception as e:
            result.message = f"MIP failed: {e}"
        return result

    def run_all(self, scenarios: list[dict]) -> dict:
        """
        Run multiple scenarios and produce comparison matrix.

        Each scenario dict keys:
            label, lambda_param, w_cost, w_time, w_compliance, w_esg,
            mode, max_vendor_share, sla_floor, total_budget, max_products_per_supplier
        """
        t0 = time.perf_counter()
        results: list[ScenarioResult] = []

        for spec in scenarios:
            label = spec.get("label", f"Scenario {len(results) + 1}")
            mode = spec.get("mode", "continuous")

            # Build weights
            w = CriteriaWeights(
                lambda_param=spec.get("lambda_param", 0.5),
                w_cost=spec.get("w_cost", 0.40),
                w_time=spec.get("w_time", 0.30),
                w_compliance=spec.get("w_compliance", 0.15),
                w_esg=spec.get("w_esg", 0.15),
            )

            sr = self.run_scenario(
                label=label,
                weights=w,
                mode=mode,
                max_vendor_share=spec.get("max_vendor_share", 1.0),
                sla_floor=spec.get("sla_floor"),
                total_budget=spec.get("total_budget"),
                max_products_per_supplier=spec.get("max_products_per_supplier"),
            )
            results.append(sr)

        total_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Build comparison matrix
        metrics = [
            "objective_total", "cost_component", "time_component",
            "compliance_component", "esg_component", "total_cost_pln",
            "suppliers_used", "products_covered", "solve_time_ms",
        ]
        comparison = []
        for m in metrics:
            values = [getattr(r, m) for r in results]
            comparison.append({
                "metric": m,
                "values": {r.label: getattr(r, m) for r in results},
                "best": results[values.index(min(values))].label if m != "products_covered" else results[values.index(max(values))].label,
            })

        # Find best scenario (lowest objective among successful)
        successful = [r for r in results if r.success]
        best_label = min(successful, key=lambda r: r.objective_total).label if successful else None

        return {
            "scenarios": [r.to_dict() for r in results],
            "comparison": comparison,
            "best_scenario": best_label,
            "total_scenarios": len(results),
            "total_time_ms": total_ms,
        }
