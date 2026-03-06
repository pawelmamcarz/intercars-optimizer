"""
REST API endpoints — Decision / Integration layer.

Groups:
  1. /optimize          — core optimisation (continuous or MIP)
  2. /dashboard         — Pareto front + radar profiles
  3. /stealth           — raw solver diagnostics for analysts
  4. /demo/{domain}     — generic demo data for all 8 procurement domains
  5. /domains           — domain registry (metadata)
  6. /weights           — live weight management
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.data_layer import get_domain_data
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
# Domain default weights  (cost, time, compliance, esg)
# -----------------------------------------------------------------------

DOMAIN_WEIGHTS: dict[str, tuple[float, float, float, float]] = {
    # ── DIRECT ──────────────────────────────────────────
    "parts":         (0.40, 0.30, 0.15, 0.15),
    "oe_components": (0.35, 0.25, 0.25, 0.15),  # OE → compliance critical
    "oils":          (0.45, 0.25, 0.15, 0.15),   # oils → cost-driven commodity
    "batteries":     (0.35, 0.30, 0.15, 0.20),   # batteries → ESG recycling focus
    # ── INDIRECT ────────────────────────────────────────
    "it_services":   (0.35, 0.25, 0.20, 0.20),   # SLA + reliability
    "logistics":     (0.30, 0.40, 0.15, 0.15),   # logistics → time-critical
    "packaging":     (0.45, 0.20, 0.10, 0.25),   # packaging → ESG/sustainability
    "mro":           (0.40, 0.25, 0.20, 0.15),   # MRO → balanced + compliance
}


def _domain_weights(domain: str, lambda_param: float = 0.5) -> CriteriaWeights:
    """Build CriteriaWeights for a given domain from the registry."""
    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
    return CriteriaWeights(
        lambda_param=lambda_param,
        w_cost=wc, w_time=wt, w_compliance=wcomp, w_esg=wesg,
    )


def _load_domain(domain: str):
    """Load suppliers and demand for any domain."""
    try:
        d = get_domain_data(domain)
        return d["suppliers"], d["demand"]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain}")


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
    summary="Run optimisation with demo data (any domain)",
    tags=["optimization"],
)
async def optimize_demo(
    domain: DemoDomain = DemoDomain.parts,
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> OptimizationResponse:
    """Run optimisation on built-in demo dataset for any procurement domain."""
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)

    resp, _ = run_optimization(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=mode, max_vendor_share=max_vendor_share,
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
        suppliers=req.suppliers, demand=req.demand, weights=req.weights,
        mode=req.mode, max_vendor_share=req.max_vendor_share,
    )
    if not current_resp.success:
        raise HTTPException(status_code=422, detail=current_resp.message)

    pareto = generate_pareto_front(
        suppliers=req.suppliers, demand=req.demand, base_weights=req.weights,
        mode=req.mode, steps=req.pareto_steps, max_vendor_share=req.max_vendor_share,
    )

    profiles = get_supplier_profiles(
        suppliers=req.suppliers, demand=req.demand,
        weights=req.weights, x_sol_response=current_resp,
    )

    return DashboardResponse(
        pareto_front=pareto,
        supplier_profiles=profiles,
        current_allocation=current_resp,
    )


@router.get(
    "/dashboard/demo",
    response_model=DashboardResponse,
    summary="Dashboard with demo data (any domain)",
    tags=["dashboard"],
)
async def dashboard_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    mode: SolverMode = SolverMode.continuous,
    pareto_steps: int = 11,
    max_vendor_share: float = 0.60,
) -> DashboardResponse:
    """Convenience: dashboard with built-in demo data for any domain."""
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)

    req = DashboardRequest(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=mode, pareto_steps=pareto_steps, max_vendor_share=max_vendor_share,
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
        suppliers=req.suppliers, demand=req.demand, weights=req.weights,
        mode=req.mode, max_vendor_share=req.max_vendor_share,
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
    summary="Stealth mode with demo data (any domain)",
    tags=["stealth"],
)
async def stealth_demo(
    domain: DemoDomain = DemoDomain.parts,
    mode: SolverMode = SolverMode.continuous,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> StealthResponse:
    """Convenience: stealth diagnostics on built-in demo data for any domain."""
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)

    req = StealthRequest(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=mode, max_vendor_share=max_vendor_share,
    )
    return await stealth(req)


# -----------------------------------------------------------------------
# 4. Generic demo data endpoints — works for ALL 8 domains
# -----------------------------------------------------------------------

@router.get(
    "/demo/{domain}/suppliers",
    summary="Get demo suppliers for any domain",
    tags=["demo"],
)
async def demo_domain_suppliers(domain: DemoDomain):
    return _load_domain(domain.value)[0]


@router.get(
    "/demo/{domain}/demand",
    summary="Get demo demand for any domain",
    tags=["demo"],
)
async def demo_domain_demand(domain: DemoDomain):
    return _load_domain(domain.value)[1]


@router.get(
    "/demo/{domain}/labels",
    summary="Get product & region labels for any domain",
    tags=["demo"],
)
async def demo_domain_labels(domain: DemoDomain):
    d = get_domain_data(domain.value)
    return {"products": d["products"], "regions": d["regions"]}


# Legacy aliases (backward compat for v1 URLs)
@router.get("/demo/suppliers", include_in_schema=False)
async def demo_suppliers_legacy():
    return _load_domain("parts")[0]

@router.get("/demo/demand", include_in_schema=False)
async def demo_demand_legacy():
    return _load_domain("parts")[1]

@router.get("/demo/labels", include_in_schema=False)
async def demo_labels_legacy():
    d = get_domain_data("parts")
    return {"products": d["products"], "regions": d["regions"]}


# -----------------------------------------------------------------------
# 5. Domain registry — list all available domains with metadata
# -----------------------------------------------------------------------

@router.get(
    "/domains",
    summary="List all 8 procurement domains with metadata",
    tags=["domains"],
)
async def list_domains():
    """Return metadata for all available demo domains."""
    from app.data_layer import DOMAIN_DATA

    DOMAIN_META = {
        "parts":         {"label": "Części zamienne", "icon": "wrench", "category": "direct"},
        "oe_components": {"label": "Komponenty OE", "icon": "cog", "category": "direct"},
        "oils":          {"label": "Oleje i płyny", "icon": "droplet", "category": "direct"},
        "batteries":     {"label": "Akumulatory", "icon": "battery", "category": "direct"},
        "it_services":   {"label": "Usługi IT", "icon": "monitor", "category": "indirect"},
        "logistics":     {"label": "Logistyka", "icon": "truck", "category": "indirect"},
        "packaging":     {"label": "Opakowania", "icon": "package", "category": "indirect"},
        "mro":           {"label": "MRO", "icon": "tool", "category": "indirect"},
    }

    domains = []
    for key, data in DOMAIN_DATA.items():
        meta = DOMAIN_META.get(key, {})
        wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(key, (0.40, 0.30, 0.15, 0.15))
        domains.append({
            "domain": key,
            "label": meta.get("label", key),
            "icon": meta.get("icon", ""),
            "category": meta.get("category", ""),
            "suppliers_count": len(data["suppliers"]),
            "demand_items": len(data["demand"]),
            "regions": list(data["regions"].keys()),
            "default_weights": {"w_cost": wc, "w_time": wt, "w_compliance": wcomp, "w_esg": wesg},
        })
    return {"domains": domains, "total": len(domains)}


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
