"""
REST API endpoints — Decision / Integration layer.

Groups:
  1. /optimize          — core optimisation (continuous or MIP)
  2. /dashboard         — Pareto front + radar profiles
  3. /stealth           — raw solver diagnostics for analysts
  4. /demo/parts        — auto-parts demo data helpers
  5. /demo/it           — IT services demo data helpers
  6. /weights           — live weight management
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.data_layer import (
    get_demo_demand, get_demo_suppliers,
    get_it_demo_demand, get_it_demo_suppliers,
    get_it_product_labels, get_it_region_labels,
    get_product_labels, get_region_labels,
)
from app.optimizer import get_supplier_profiles, run_optimization
from app.pareto import generate_pareto_front
from app.schemas import (
    CriteriaWeights,
    DashboardRequest,
    DashboardResponse,
    DemoDomain,
    OptimizationRequest,
    OptimizationResponse,
    SolverMode,
    StealthRequest,
    StealthResponse,
)

router = APIRouter()


# -----------------------------------------------------------------------
# 1. Core optimisation
# -----------------------------------------------------------------------

@router.post(
    "/optimize",
    response_model=OptimizationResponse,
    summary="Run order portfolio optimisation",
    tags=["optimization"],
)
async def optimize(req: OptimizationRequest) -> OptimizationResponse:
    """
    Solve the multi-criteria supplier allocation problem.

    Modes:
    - **continuous** — LP relaxation via `scipy.optimize.linprog(method='highs')`.
      Allocations are fractional (0..1). Vendor diversification enforced.
    - **mip** — Mixed-Integer (binary) via PuLP + HiGHS.
      Exactly one supplier selected per product. Diversification as volume cap.
    """
    resp, _ = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
        max_vendor_share=req.max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return resp


@router.get(
    "/optimize/demo",
    response_model=OptimizationResponse,
    summary="Run optimisation with demo data (parts or IT)",
    tags=["optimization"],
)
async def optimize_demo(
    domain: DemoDomain = DemoDomain.parts,
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> OptimizationResponse:
    """Run optimisation on built-in demo dataset (auto-parts or IT services)."""
    if domain == DemoDomain.parts:
        suppliers = get_demo_suppliers()
        demand = get_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_w_cost,
            w_time=settings.default_w_time,
            w_compliance=settings.default_w_compliance,
            w_esg=settings.default_w_esg,
        )
    else:
        suppliers = get_it_demo_suppliers()
        demand = get_it_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_it_w_cost,
            w_time=settings.default_it_w_time,
            w_compliance=settings.default_it_w_compliance,
            w_esg=settings.default_it_w_esg,
        )

    resp, _ = run_optimization(
        suppliers=suppliers,
        demand=demand,
        weights=weights,
        mode=mode,
        max_vendor_share=max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return resp


# -----------------------------------------------------------------------
# 2. Dashboard — Pareto front + radar
# -----------------------------------------------------------------------

@router.post(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Generate Pareto front and supplier radar profiles",
    tags=["dashboard"],
)
async def dashboard(req: DashboardRequest) -> DashboardResponse:
    """
    **Dashboard endpoint** — generates:
    1. Pareto front by sweeping λ ∈ [0, 1].
    2. Supplier radar profiles (normalised cost/time/compliance/ESG).
    3. Current allocation at the requested λ.
    """
    current_resp, _ = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
        max_vendor_share=req.max_vendor_share,
    )
    if not current_resp.success:
        raise HTTPException(status_code=422, detail=current_resp.message)

    pareto = generate_pareto_front(
        suppliers=req.suppliers,
        demand=req.demand,
        base_weights=req.weights,
        mode=req.mode,
        steps=req.pareto_steps,
        max_vendor_share=req.max_vendor_share,
    )

    profiles = get_supplier_profiles(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        x_sol_response=current_resp,
    )

    return DashboardResponse(
        pareto_front=pareto,
        supplier_profiles=profiles,
        current_allocation=current_resp,
    )


@router.get(
    "/dashboard/demo",
    response_model=DashboardResponse,
    summary="Dashboard with demo data (parts or IT)",
    tags=["dashboard"],
)
async def dashboard_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    mode: SolverMode = SolverMode.continuous,
    pareto_steps: int = 11,
    max_vendor_share: float = 0.60,
) -> DashboardResponse:
    """Convenience: dashboard with built-in demo data."""
    if domain == DemoDomain.parts:
        suppliers = get_demo_suppliers()
        demand = get_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_w_cost,
            w_time=settings.default_w_time,
            w_compliance=settings.default_w_compliance,
            w_esg=settings.default_w_esg,
        )
    else:
        suppliers = get_it_demo_suppliers()
        demand = get_it_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_it_w_cost,
            w_time=settings.default_it_w_time,
            w_compliance=settings.default_it_w_compliance,
            w_esg=settings.default_it_w_esg,
        )

    req = DashboardRequest(
        suppliers=suppliers,
        demand=demand,
        weights=weights,
        mode=mode,
        pareto_steps=pareto_steps,
        max_vendor_share=max_vendor_share,
    )
    return await dashboard(req)


# -----------------------------------------------------------------------
# 3. Stealth mode — raw solver diagnostics
# -----------------------------------------------------------------------

@router.post(
    "/stealth",
    response_model=StealthResponse,
    summary="Stealth mode — raw solver diagnostics",
    tags=["stealth"],
)
async def stealth(req: StealthRequest) -> StealthResponse:
    """
    **Stealth Mode** — for analysts.

    Returns raw HiGHS solver log, decision variables, constraints
    (including C5 diversification), objective equation, and iterations.
    """
    resp, diag = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
        max_vendor_share=req.max_vendor_share,
        capture_diagnostics=True,
    )

    solver_name = "scipy.linprog/HiGHS" if req.mode == SolverMode.continuous else "PuLP/HiGHS-MIP"
    obj_val = resp.objective.total if resp.success else 0.0

    return StealthResponse(
        success=resp.success,
        solver_name=solver_name,
        solver_status=resp.solver_stats.status,
        solve_time_ms=resp.solver_stats.solve_time_ms,
        objective_value=obj_val,
        objective_equation=diag.objective_equation,
        variables=diag.variables,
        constraints=diag.constraints,
        iterations=diag.iterations,
        raw_log=diag.raw_log,
        allocation_result=resp,
    )


@router.get(
    "/stealth/demo",
    response_model=StealthResponse,
    summary="Stealth mode with demo data (parts or IT)",
    tags=["stealth"],
)
async def stealth_demo(
    domain: DemoDomain = DemoDomain.parts,
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> StealthResponse:
    """Convenience: stealth diagnostics on built-in demo data."""
    if domain == DemoDomain.parts:
        suppliers = get_demo_suppliers()
        demand = get_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_w_cost,
            w_time=settings.default_w_time,
            w_compliance=settings.default_w_compliance,
            w_esg=settings.default_w_esg,
        )
    else:
        suppliers = get_it_demo_suppliers()
        demand = get_it_demo_demand()
        weights = CriteriaWeights(
            lambda_param=lambda_param,
            w_cost=settings.default_it_w_cost,
            w_time=settings.default_it_w_time,
            w_compliance=settings.default_it_w_compliance,
            w_esg=settings.default_it_w_esg,
        )

    req = StealthRequest(
        suppliers=suppliers,
        demand=demand,
        weights=weights,
        mode=mode,
        max_vendor_share=max_vendor_share,
    )
    return await stealth(req)


# -----------------------------------------------------------------------
# 4. Demo data — Auto-parts
# -----------------------------------------------------------------------

@router.get("/demo/parts/suppliers", summary="Get parts demo suppliers", tags=["demo"])
async def demo_parts_suppliers():
    return get_demo_suppliers()


@router.get("/demo/parts/demand", summary="Get parts demo demand", tags=["demo"])
async def demo_parts_demand():
    return get_demo_demand()


@router.get("/demo/parts/labels", summary="Get parts product & region labels", tags=["demo"])
async def demo_parts_labels():
    return {"products": get_product_labels(), "regions": get_region_labels()}


# Legacy aliases (backward compat)
@router.get("/demo/suppliers", include_in_schema=False)
async def demo_suppliers():
    return get_demo_suppliers()

@router.get("/demo/demand", include_in_schema=False)
async def demo_demand():
    return get_demo_demand()

@router.get("/demo/labels", include_in_schema=False)
async def demo_labels():
    return {"products": get_product_labels(), "regions": get_region_labels()}


# -----------------------------------------------------------------------
# 5. Demo data — IT Services
# -----------------------------------------------------------------------

@router.get("/demo/it/suppliers", summary="Get IT services demo suppliers", tags=["demo"])
async def demo_it_suppliers():
    return get_it_demo_suppliers()


@router.get("/demo/it/demand", summary="Get IT services demo demand", tags=["demo"])
async def demo_it_demand():
    return get_it_demo_demand()


@router.get("/demo/it/labels", summary="Get IT product & competency labels", tags=["demo"])
async def demo_it_labels():
    return {"products": get_it_product_labels(), "regions": get_it_region_labels()}


# -----------------------------------------------------------------------
# 6. Live weight management
# -----------------------------------------------------------------------

@router.get(
    "/weights/defaults",
    response_model=CriteriaWeights,
    summary="Get current default weights",
    tags=["weights"],
)
async def get_default_weights() -> CriteriaWeights:
    """Return the server-side default weights (modifiable via env vars)."""
    return CriteriaWeights(
        lambda_param=settings.default_lambda,
        w_cost=settings.default_w_cost,
        w_time=settings.default_w_time,
        w_compliance=settings.default_w_compliance,
        w_esg=settings.default_w_esg,
    )


@router.put(
    "/weights/defaults",
    response_model=CriteriaWeights,
    summary="Update default weights at runtime",
    tags=["weights"],
)
async def set_default_weights(w: CriteriaWeights) -> CriteriaWeights:
    """Modify default weights in-flight without restarting the server."""
    settings.default_lambda = w.lambda_param
    settings.default_w_cost = w.w_cost
    settings.default_w_time = w.w_time
    settings.default_w_compliance = w.w_compliance
    settings.default_w_esg = w.w_esg
    return w
