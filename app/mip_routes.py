"""
MIP Dedicated Router — binary optimisation with IT-specific constraints.

Endpoints:
  POST /mip/optimize           — run MIP with custom data + IT constraints
  GET  /mip/optimize/demo      — run MIP on demo data for any domain
  POST /mip/compare            — compare LP vs MIP results side-by-side
  GET  /mip/compare/demo       — compare on demo data
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.data_layer import get_domain_data, DOMAIN_WEIGHTS
from app.optimizer import run_optimization
from app.schemas import (
    CriteriaWeights,
    DemoDomain,
    MipAllocationRow,
    MipDiagnostics,
    MipObjectiveBreakdown,
    MipOptimizationRequest,
    MipOptimizationResponse,
    OptimizationResponse,
    SolverMode,
)
from app.solver_mip import MipOptimizationEngine

mip_router = APIRouter()



def _domain_weights(domain: str, lambda_param: float = 0.5) -> CriteriaWeights:
    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
    return CriteriaWeights(lambda_param=lambda_param, w_cost=wc, w_time=wt, w_compliance=wcomp, w_esg=wesg)


def _build_mip_response(result) -> MipOptimizationResponse:
    """Convert MipResult dataclass to Pydantic response."""
    allocations = [MipAllocationRow(**a) for a in result.allocations]
    return MipOptimizationResponse(
        success=result.success,
        message=result.message,
        status=result.status,
        solve_time_ms=result.solve_time_ms,
        objective=MipObjectiveBreakdown(
            total=result.objective_total,
            cost_component=result.cost_component,
            time_component=result.time_component,
            compliance_component=result.compliance_component,
            esg_component=result.esg_component,
        ),
        allocations=allocations,
        diagnostics=MipDiagnostics(
            total_cost_pln=result.total_cost_pln,
            budget_used_pct=result.budget_used_pct,
            suppliers_selected=result.suppliers_selected,
            products_covered=result.products_covered,
            infeasible_products=result.infeasible_products,
            sla_floor_active=result.sla_floor_active,
            budget_ceiling_active=result.budget_ceiling_active,
            max_products_per_supplier_active=result.max_products_per_supplier_active,
        ),
        weights_used=CriteriaWeights(),  # placeholder, overridden below
    )


# -----------------------------------------------------------------------
# 1. Core MIP optimization
# -----------------------------------------------------------------------

@mip_router.post(
    "/mip/optimize",
    response_model=MipOptimizationResponse,
    summary="Run dedicated MIP optimisation with IT-specific constraints",
    tags=["mip"],
)
async def mip_optimize(req: MipOptimizationRequest) -> MipOptimizationResponse:
    """
    **Dedicated MIP Solver** — binary (0/1) supplier selection.

    IT-specific constraints beyond standard MIP:
    - **sla_floor** — minimum compliance/SLA score for eligibility (e.g., 0.8)
    - **total_budget** — budget ceiling in PLN
    - **max_products_per_supplier** — limits workload concentration

    All standard constraints (demand, capacity, regional, diversification) also apply.
    """
    try:
        engine = MipOptimizationEngine(
            suppliers=req.suppliers,
            demand=req.demand,
            weights=req.weights,
            max_vendor_share=req.max_vendor_share,
            sla_floor=req.sla_floor,
            total_budget=req.total_budget,
            max_products_per_supplier=req.max_products_per_supplier,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = engine.solve()
    resp = _build_mip_response(result)
    resp.weights_used = req.weights

    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)
    return resp


@mip_router.get(
    "/mip/optimize/demo",
    response_model=MipOptimizationResponse,
    summary="MIP optimisation with demo data (any domain)",
    tags=["mip"],
)
async def mip_optimize_demo(
    domain: DemoDomain = DemoDomain.it_services,
    lambda_param: float = 0.5,
    max_vendor_share: float = 1.0,
    sla_floor: Optional[float] = None,
    total_budget: Optional[float] = None,
    max_products_per_supplier: Optional[int] = None,
) -> MipOptimizationResponse:
    """Run MIP on built-in demo dataset. Defaults to IT services domain."""
    try:
        data = get_domain_data(domain.value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain.value}")

    suppliers = data["suppliers"]
    demand = data["demand"]
    weights = _domain_weights(domain.value, lambda_param)

    try:
        engine = MipOptimizationEngine(
            suppliers=suppliers,
            demand=demand,
            weights=weights,
            max_vendor_share=max_vendor_share,
            sla_floor=sla_floor,
            total_budget=total_budget,
            max_products_per_supplier=max_products_per_supplier,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = engine.solve()
    resp = _build_mip_response(result)
    resp.weights_used = weights

    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)
    return resp


# -----------------------------------------------------------------------
# 2. LP vs MIP comparison
# -----------------------------------------------------------------------

class CompareResponse(MipOptimizationResponse):
    """Side-by-side LP vs MIP comparison."""

    # Keep MIP result as base, add LP for comparison
    pass


@mip_router.post(
    "/mip/compare",
    summary="Compare LP (continuous) vs MIP (binary) results",
    tags=["mip"],
)
async def mip_compare(req: MipOptimizationRequest):
    """
    Run both LP (continuous) and MIP (binary) on the same data.

    Returns both results for side-by-side comparison:
    - LP: fractional allocations, lower bound on objective
    - MIP: binary selections, real-world actionable assignments
    """
    # LP result (via standard optimizer)
    lp_resp, _ = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=SolverMode.continuous,
        max_vendor_share=req.max_vendor_share,
    )

    # MIP result (via dedicated engine)
    try:
        engine = MipOptimizationEngine(
            suppliers=req.suppliers,
            demand=req.demand,
            weights=req.weights,
            max_vendor_share=req.max_vendor_share,
            sla_floor=req.sla_floor,
            total_budget=req.total_budget,
            max_products_per_supplier=req.max_products_per_supplier,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    mip_result = engine.solve()
    mip_resp = _build_mip_response(mip_result)
    mip_resp.weights_used = req.weights

    # Compute LP total cost
    lp_total_cost = sum(
        (a.unit_cost + a.logistics_cost) * a.allocated_qty
        for a in lp_resp.allocations
    )

    return {
        "lp_result": {
            "success": lp_resp.success,
            "message": lp_resp.message,
            "objective_total": lp_resp.objective.total,
            "cost_component": lp_resp.objective.cost_component,
            "time_component": lp_resp.objective.time_component,
            "compliance_component": lp_resp.objective.compliance_component,
            "esg_component": lp_resp.objective.esg_component,
            "total_cost_pln": round(lp_total_cost, 2),
            "allocations_count": len(lp_resp.allocations),
            "unique_suppliers": len(set(a.supplier_id for a in lp_resp.allocations)),
            "solve_time_ms": lp_resp.solver_stats.solve_time_ms,
            "allocations": [a.model_dump() for a in lp_resp.allocations],
        },
        "mip_result": mip_resp.model_dump(),
        "comparison": {
            "objective_gap_pct": round(
                (mip_result.objective_total - lp_resp.objective.total)
                / max(lp_resp.objective.total, 1e-12) * 100, 2
            ) if lp_resp.success and mip_result.success else None,
            "cost_gap_pln": round(
                mip_result.total_cost_pln - lp_total_cost, 2
            ) if lp_resp.success and mip_result.success else None,
            "lp_suppliers": len(set(a.supplier_id for a in lp_resp.allocations)),
            "mip_suppliers": mip_result.suppliers_selected,
            "note": (
                "LP provides a lower bound (fractional). "
                "MIP provides actionable binary assignments. "
                "Gap shows the 'price of integrality'."
            ),
        },
    }


@mip_router.get(
    "/mip/compare/demo",
    summary="LP vs MIP comparison with demo data",
    tags=["mip"],
)
async def mip_compare_demo(
    domain: DemoDomain = DemoDomain.it_services,
    lambda_param: float = 0.5,
    max_vendor_share: float = 1.0,
    sla_floor: Optional[float] = None,
    total_budget: Optional[float] = None,
    max_products_per_supplier: Optional[int] = None,
):
    """Convenience: LP vs MIP comparison on built-in demo data."""
    try:
        data = get_domain_data(domain.value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain.value}")

    req = MipOptimizationRequest(
        suppliers=data["suppliers"],
        demand=data["demand"],
        weights=_domain_weights(domain.value, lambda_param),
        max_vendor_share=max_vendor_share,
        sla_floor=sla_floor,
        total_budget=total_budget,
        max_products_per_supplier=max_products_per_supplier,
    )
    return await mip_compare(req)
