"""
REST API endpoints — Decision / Integration layer.

Three groups:
  1. /optimize          — core optimisation (continuous or MIP)
  2. /dashboard         — Pareto front + radar profiles
  3. /stealth           — raw solver diagnostics for analysts
  4. /demo              — demo data helpers
  5. /weights           — live weight management
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.data_layer import get_demo_demand, get_demo_suppliers, get_product_labels, get_region_labels
from app.optimizer import get_supplier_profiles, run_optimization
from app.pareto import generate_pareto_front
from app.schemas import (
    CriteriaWeights,
    DashboardRequest,
    DashboardResponse,
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
      Allocations are fractional (0..1).
    - **mip** — Mixed-Integer (binary) via PuLP + HiGHS.
      Exactly one supplier selected per product.
    """
    resp, _ = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return resp


@router.get(
    "/optimize/demo",
    response_model=OptimizationResponse,
    summary="Run optimisation with built-in demo data",
    tags=["optimization"],
)
async def optimize_demo(
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
) -> OptimizationResponse:
    """Run optimisation on the built-in INTERCARS demo dataset."""
    weights = CriteriaWeights(
        lambda_param=lambda_param,
        w_cost=settings.default_w_cost,
        w_time=settings.default_w_time,
        w_compliance=settings.default_w_compliance,
        w_esg=settings.default_w_esg,
    )
    resp, _ = run_optimization(
        suppliers=get_demo_suppliers(),
        demand=get_demo_demand(),
        weights=weights,
        mode=mode,
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

    Designed to feed radar charts and Pareto plots in BI systems.
    """
    # Current allocation at the requested lambda
    current_resp, _ = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
    )
    if not current_resp.success:
        raise HTTPException(status_code=422, detail=current_resp.message)

    # Pareto front
    pareto = generate_pareto_front(
        suppliers=req.suppliers,
        demand=req.demand,
        base_weights=req.weights,
        mode=req.mode,
        steps=req.pareto_steps,
    )

    # Radar profiles
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
    summary="Dashboard with demo data",
    tags=["dashboard"],
)
async def dashboard_demo(
    lambda_param: float = 0.5,
    mode: SolverMode = SolverMode.continuous,
    pareto_steps: int = 11,
) -> DashboardResponse:
    """Convenience: dashboard with built-in demo data."""
    weights = CriteriaWeights(
        lambda_param=lambda_param,
        w_cost=settings.default_w_cost,
        w_time=settings.default_w_time,
        w_compliance=settings.default_w_compliance,
        w_esg=settings.default_w_esg,
    )
    req = DashboardRequest(
        suppliers=get_demo_suppliers(),
        demand=get_demo_demand(),
        weights=weights,
        mode=mode,
        pareto_steps=pareto_steps,
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

    Returns:
    - Raw HiGHS solver log output
    - All decision variable values and reduced costs
    - Constraint expressions, bounds, and slack
    - Objective function equation (human-readable)
    - Iteration-by-iteration objective values
    """
    resp, diag = run_optimization(
        suppliers=req.suppliers,
        demand=req.demand,
        weights=req.weights,
        mode=req.mode,
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
    summary="Stealth mode with demo data",
    tags=["stealth"],
)
async def stealth_demo(
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
) -> StealthResponse:
    """Convenience: stealth diagnostics on built-in demo data."""
    weights = CriteriaWeights(
        lambda_param=lambda_param,
        w_cost=settings.default_w_cost,
        w_time=settings.default_w_time,
        w_compliance=settings.default_w_compliance,
        w_esg=settings.default_w_esg,
    )
    req = StealthRequest(
        suppliers=get_demo_suppliers(),
        demand=get_demo_demand(),
        weights=weights,
        mode=mode,
    )
    return await stealth(req)


# -----------------------------------------------------------------------
# 4. Demo data
# -----------------------------------------------------------------------

@router.get(
    "/demo/suppliers",
    summary="Get demo supplier dataset",
    tags=["demo"],
)
async def demo_suppliers():
    return get_demo_suppliers()


@router.get(
    "/demo/demand",
    summary="Get demo demand dataset",
    tags=["demo"],
)
async def demo_demand():
    return get_demo_demand()


@router.get(
    "/demo/labels",
    summary="Get product and region labels",
    tags=["demo"],
)
async def demo_labels():
    return {
        "products": get_product_labels(),
        "regions": get_region_labels(),
    }


# -----------------------------------------------------------------------
# 5. Live weight management
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
    """
    Modify default weights **in-flight** without restarting the server.

    These become the new defaults when no weights are provided in requests.
    """
    settings.default_lambda = w.lambda_param
    settings.default_w_cost = w.w_cost
    settings.default_w_time = w.w_time
    settings.default_w_compliance = w.w_compliance
    settings.default_w_esg = w.w_esg
    return w
