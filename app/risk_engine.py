"""
v3.0 — Risk Engine: Heatmap, Monte Carlo Simulation, Negotiation Assistant.

All computations are pure Python + scipy LP — no extra dependencies.
"""
from __future__ import annotations

import logging
import math
import random
from collections import defaultdict
from typing import Optional

from app.schemas import (
    AllocationRow,
    CriteriaWeights,
    DemandItem,
    MonteCarloResponse,
    NegotiationResponse,
    NegotiationTargetSchema,
    RiskCellSchema,
    RiskHeatmapResponse,
    SolverMode,
    SupplierInput,
    SupplierStability,
)

logger = logging.getLogger(__name__)


# ── Risk Heatmap ──────────────────────────────────────────────────────

class RiskHeatmapEngine:
    """
    Compute a risk heatmap from supplier allocations.

    Risk composite = 0.4×single_source + 0.3×capacity_util + 0.3×esg_risk.
    Labels: low (<0.25), medium (<0.50), high (<0.75), critical (≥0.75).
    """

    @staticmethod
    def compute(
        suppliers: list[SupplierInput],
        demand: list[DemandItem],
        allocations: list[AllocationRow],
    ) -> RiskHeatmapResponse:
        sup_map = {s.supplier_id: s for s in suppliers}
        demand_map = {d.product_id: d for d in demand}

        # Aggregate allocations per product to find single-source risk
        product_supplier_count: dict[str, set[str]] = defaultdict(set)
        product_allocations: dict[str, list[AllocationRow]] = defaultdict(list)
        for a in allocations:
            if a.allocated_fraction > 0.01:
                product_supplier_count[a.product_id].add(a.supplier_id)
                product_allocations[a.product_id].append(a)

        cells: list[RiskCellSchema] = []
        supplier_ids_seen: set[str] = set()
        product_ids_seen: set[str] = set()

        for a in allocations:
            if a.allocated_fraction < 0.01:
                continue
            sup = sup_map.get(a.supplier_id)
            dem = demand_map.get(a.product_id)

            # Single-source risk: 1.0 if only one supplier for this product
            n_sources = len(product_supplier_count.get(a.product_id, set()))
            single_source = 1.0 if n_sources <= 1 else 1.0 / n_sources

            # Capacity utilization: higher = riskier
            cap = sup.max_capacity if sup else 1.0
            total_alloc_qty = sum(
                aa.allocated_qty for aa in allocations
                if aa.supplier_id == a.supplier_id and aa.allocated_fraction > 0.01
            )
            cap_util = min(total_alloc_qty / cap, 1.0) if cap > 0 else 1.0

            # ESG risk: inverse of ESG score
            esg_risk = 1.0 - a.esg_score

            # Composite
            risk = 0.4 * single_source + 0.3 * cap_util + 0.3 * esg_risk
            label = (
                "low" if risk < 0.25
                else "medium" if risk < 0.50
                else "high" if risk < 0.75
                else "critical"
            )

            cells.append(RiskCellSchema(
                supplier_id=a.supplier_id,
                supplier_name=a.supplier_name,
                product_id=a.product_id,
                risk_score=round(risk, 4),
                single_source_risk=round(single_source, 4),
                capacity_utilization=round(cap_util, 4),
                esg_risk=round(esg_risk, 4),
                risk_label=label,
            ))
            supplier_ids_seen.add(a.supplier_id)
            product_ids_seen.add(a.product_id)

        critical = sum(1 for c in cells if c.risk_label == "critical")
        high = sum(1 for c in cells if c.risk_label == "high")
        overall = sum(c.risk_score for c in cells) / len(cells) if cells else 0.0

        return RiskHeatmapResponse(
            cells=cells,
            suppliers=sorted(supplier_ids_seen),
            products=sorted(product_ids_seen),
            critical_count=critical,
            high_count=high,
            overall_risk_score=round(overall, 4),
        )


# ── Monte Carlo Simulation ───────────────────────────────────────────

class MonteCarloEngine:
    """
    Perturbation-based Monte Carlo: varies costs/times by log-normal noise,
    re-solves LP N times, and collects cost/objective distributions.
    """

    def __init__(
        self,
        suppliers: list[SupplierInput],
        demand: list[DemandItem],
        weights: CriteriaWeights,
        n_iterations: int = 500,
        cost_std_pct: float = 0.10,
        time_std_pct: float = 0.15,
        max_vendor_share: float = 1.0,
        seed: Optional[int] = 42,
    ):
        self.suppliers = suppliers
        self.demand = demand
        self.weights = weights
        self.n = n_iterations
        self.cost_std = cost_std_pct
        self.time_std = time_std_pct
        self.max_share = max_vendor_share
        self.rng = random.Random(seed)

    def _perturb_suppliers(self) -> list[SupplierInput]:
        """Return a copy of suppliers with perturbed cost/time."""
        perturbed = []
        for s in self.suppliers:
            cost_factor = math.exp(self.rng.gauss(0, self.cost_std))
            time_factor = math.exp(self.rng.gauss(0, self.time_std))
            perturbed.append(SupplierInput(
                supplier_id=s.supplier_id,
                name=s.name,
                unit_cost=s.unit_cost * cost_factor,
                logistics_cost=s.logistics_cost * cost_factor,
                lead_time_days=max(1.0, s.lead_time_days * time_factor),
                compliance_score=s.compliance_score,
                esg_score=s.esg_score,
                min_order_qty=s.min_order_qty,
                max_capacity=s.max_capacity,
                served_regions=s.served_regions,
                payment_terms_days=s.payment_terms_days,
                contract_min_allocation=s.contract_min_allocation,
                is_preferred=s.is_preferred,
                region_code=s.region_code,
            ))
        return perturbed

    def run(self) -> MonteCarloResponse:
        from app.optimizer import run_optimization

        costs: list[float] = []
        objectives: list[float] = []
        supplier_selections: dict[str, int] = defaultdict(int)
        feasible = 0

        for _ in range(self.n):
            psup = self._perturb_suppliers()
            resp, _ = run_optimization(
                psup, self.demand, self.weights,
                mode=SolverMode.continuous,
                max_vendor_share=self.max_share,
            )
            if not resp.success:
                continue
            feasible += 1

            total_cost = sum(
                (a.unit_cost + a.logistics_cost) * a.allocated_qty
                for a in resp.allocations if a.allocated_fraction > 0.01
            )
            costs.append(total_cost)
            objectives.append(resp.objective.total)

            for a in resp.allocations:
                if a.allocated_fraction > 0.01:
                    supplier_selections[a.supplier_id] += 1

        if not costs:
            return MonteCarloResponse(
                n_iterations=self.n, feasible_rate=0.0,
                cost_mean_pln=0, cost_std_pln=0,
                cost_p5_pln=0, cost_p95_pln=0,
                objective_mean=0, objective_std=0,
                robustness_score=0, supplier_stability=[],
                cost_histogram=[],
            )

        costs_sorted = sorted(costs)
        obj_sorted = sorted(objectives)
        n_f = len(costs)
        cost_mean = sum(costs) / n_f
        obj_mean = sum(objectives) / n_f
        cost_std = math.sqrt(sum((c - cost_mean) ** 2 for c in costs) / n_f)
        obj_std = math.sqrt(sum((o - obj_mean) ** 2 for o in objectives) / n_f)
        p5 = costs_sorted[max(0, int(n_f * 0.05))]
        p95 = costs_sorted[min(n_f - 1, int(n_f * 0.95))]

        # Robustness: 1 - (std/mean), clamped to [0, 1]
        robustness = max(0.0, min(1.0, 1.0 - (cost_std / cost_mean))) if cost_mean > 0 else 0.0

        # Supplier stability
        sup_map = {s.supplier_id: s.name for s in self.suppliers}
        stability = [
            SupplierStability(
                supplier_id=sid,
                supplier_name=sup_map.get(sid, sid),
                selection_rate=round(cnt / feasible, 4),
            )
            for sid, cnt in sorted(supplier_selections.items(), key=lambda x: -x[1])
        ]

        # Histogram: 20 bins
        n_bins = 20
        bin_width = (p95 - p5) / n_bins if p95 > p5 else 1.0
        histogram = [0.0] * n_bins
        for c in costs:
            idx = min(n_bins - 1, max(0, int((c - p5) / bin_width)))
            histogram[idx] += 1
        histogram = [h / n_f for h in histogram]  # normalize to fractions

        return MonteCarloResponse(
            n_iterations=self.n,
            feasible_rate=round(feasible / self.n, 4),
            cost_mean_pln=round(cost_mean, 2),
            cost_std_pln=round(cost_std, 2),
            cost_p5_pln=round(p5, 2),
            cost_p95_pln=round(p95, 2),
            objective_mean=round(obj_mean, 6),
            objective_std=round(obj_std, 6),
            robustness_score=round(robustness, 4),
            supplier_stability=stability,
            cost_histogram=histogram,
        )


# ── Negotiation Assistant ─────────────────────────────────────────────

class NegotiationAssistant:
    """
    Analyse allocations and identify negotiation targets.

    High priority: share >30% AND cost > median.
    Medium: share >15% OR cost in top quartile.
    """

    @staticmethod
    def analyze(
        suppliers: list[SupplierInput],
        allocations: list[AllocationRow],
    ) -> NegotiationResponse:
        sup_map = {s.supplier_id: s for s in suppliers}

        # Aggregate per supplier
        sup_data: dict[str, dict] = {}
        total_cost_all = 0.0
        for a in allocations:
            if a.allocated_fraction < 0.01:
                continue
            cost = (a.unit_cost + a.logistics_cost) * a.allocated_qty
            total_cost_all += cost
            entry = sup_data.setdefault(a.supplier_id, {
                "supplier_id": a.supplier_id,
                "supplier_name": a.supplier_name,
                "total_cost": 0.0,
                "total_qty": 0.0,
                "unit_costs": [],
            })
            entry["total_cost"] += cost
            entry["total_qty"] += a.allocated_qty
            entry["unit_costs"].append(a.unit_cost)

        if not sup_data or total_cost_all == 0:
            return NegotiationResponse(targets=[], total_estimated_savings_pln=0, analyzed_suppliers=0)

        # Compute shares and median cost
        for entry in sup_data.values():
            entry["share"] = entry["total_cost"] / total_cost_all
            entry["avg_unit_cost"] = sum(entry["unit_costs"]) / len(entry["unit_costs"])

        all_costs = [e["avg_unit_cost"] for e in sup_data.values()]
        all_costs.sort()
        median_cost = all_costs[len(all_costs) // 2]
        q75_cost = all_costs[int(len(all_costs) * 0.75)] if len(all_costs) > 1 else median_cost

        targets: list[NegotiationTargetSchema] = []
        total_savings = 0.0

        for entry in sorted(sup_data.values(), key=lambda x: -x["total_cost"]):
            share = entry["share"]
            avg_cost = entry["avg_unit_cost"]

            if share > 0.30 and avg_cost > median_cost:
                priority = "high"
                reduction = 0.08
                rationale = f"Dominant share ({share:.0%}) with above-median unit cost"
            elif share > 0.15 or avg_cost >= q75_cost:
                priority = "medium"
                reduction = 0.05
                rationale = (
                    f"Significant share ({share:.0%})"
                    if share > 0.15
                    else f"Top-quartile unit cost ({avg_cost:.1f} PLN)"
                )
            else:
                priority = "low"
                reduction = 0.02
                rationale = f"Minor share ({share:.0%}), limited savings potential"

            saving = entry["total_cost"] * reduction
            total_savings += saving

            targets.append(NegotiationTargetSchema(
                supplier_id=entry["supplier_id"],
                supplier_name=entry["supplier_name"],
                current_share_pct=round(share * 100, 2),
                current_total_cost_pln=round(entry["total_cost"], 2),
                estimated_saving_pln=round(saving, 2),
                target_reduction_pct=round(reduction * 100, 2),
                negotiation_priority=priority,
                rationale=rationale,
            ))

        return NegotiationResponse(
            targets=targets,
            total_estimated_savings_pln=round(total_savings, 2),
            analyzed_suppliers=len(targets),
        )
