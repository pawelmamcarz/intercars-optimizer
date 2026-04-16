"""
REST API endpoints — Decision / Integration layer.

Groups:
  1. /optimize            — core optimisation (continuous or MIP)
  2. /dashboard           — Pareto front + radar profiles + XY scatter
  3. /stealth             — raw solver diagnostics for analysts
  4. /demo/{domain}       — generic demo data for all 10 procurement domains
  5. /demo/{domain}/{sub} — subdomain-level demo data (v3.0)
  6. /domains             — domain registry (metadata)
  7. /domains/extended    — domains + subdomains (v3.0)
  8. /weights             — live weight management
  9. /process-mining      — P2P process mining (DFG, lead times, bottlenecks, variants)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.data_layer import (
    get_domain_data,
    get_p2p_demo_events,
    get_subdomain_data,
    get_domain_subdomains,
    SUBDOMAIN_DATA,
    DOMAIN_WEIGHTS,
)
from app.optimizer import get_supplier_profiles, run_optimization
from app.pareto import generate_pareto_front, generate_pareto_front_xy, generate_pareto_with_mc
from app.process_miner import (
    analyze_variants,
    compute_lead_times,
    detect_bottlenecks,
    discover_dfg,
)
from app.schemas import (
    BottleneckResponse,
    ConstraintConfig,
    CriteriaWeights,
    DashboardRequest,
    DashboardResponse,
    DemoDomain,
    DFGResponse,
    LeadTimeResponse,
    OptimizationRequest,
    OptimizationResponse,
    ProcessMiningRequest,
    SolverMode,
    StealthRequest,
    StealthResponse,
    SubDomain,
    VariantResponse,
    # v3.0 dashboard
    ParetoPointXY,
    SankeyNode,
    SankeyLink,
    SankeyResponse,
    DonutSegment,
    DonutResponse,
    DomainTrendPoint,
    DomainTrendResponse,
)

router = APIRouter()



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
        constraints=req.constraints,
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
# 4. Generic demo data endpoints — works for ALL 10 domains
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
# 4b. Subdomain demo data endpoints (v3.0)
# -----------------------------------------------------------------------

@router.get(
    "/demo/{domain}/{subdomain}/suppliers",
    summary="Get demo suppliers for a subdomain",
    tags=["demo"],
)
async def demo_subdomain_suppliers(domain: DemoDomain, subdomain: SubDomain):
    try:
        sd = get_subdomain_data(domain.value, subdomain.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sd["suppliers"]


@router.get(
    "/demo/{domain}/{subdomain}/demand",
    summary="Get demo demand for a subdomain",
    tags=["demo"],
)
async def demo_subdomain_demand(domain: DemoDomain, subdomain: SubDomain):
    try:
        sd = get_subdomain_data(domain.value, subdomain.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sd["demand"]


@router.get(
    "/demo/{domain}/{subdomain}/labels",
    summary="Get product & region labels for a subdomain",
    tags=["demo"],
)
async def demo_subdomain_labels(domain: DemoDomain, subdomain: SubDomain):
    try:
        sd = get_subdomain_data(domain.value, subdomain.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"products": sd["products"], "regions": sd["regions"]}


# -----------------------------------------------------------------------
# 5. Domain registry — list all available domains with metadata
# -----------------------------------------------------------------------

DOMAIN_META = {
    "parts":               {"label": "Części zamienne", "icon": "wrench", "category": "direct"},
    "oe_components":       {"label": "Komponenty OE", "icon": "cog", "category": "direct"},
    "oils":                {"label": "Oleje i płyny", "icon": "droplet", "category": "direct"},
    "batteries":           {"label": "Akumulatory", "icon": "battery", "category": "direct"},
    "tires":               {"label": "Opony", "icon": "circle", "category": "direct"},
    "bodywork":            {"label": "Nadwozia i oświetlenie", "icon": "car", "category": "direct"},
    "it_services":         {"label": "Usługi IT", "icon": "monitor", "category": "indirect"},
    "logistics":           {"label": "Logistyka", "icon": "truck", "category": "indirect"},
    "packaging":           {"label": "Opakowania", "icon": "package", "category": "indirect"},
    "facility_management": {"label": "Zarządzanie obiektem", "icon": "building", "category": "indirect"},
    "mro":                 {"label": "MRO (alias)", "icon": "tool", "category": "indirect"},
}

@router.get(
    "/domains",
    summary="List all 10 procurement domains with metadata",
    tags=["domains"],
)
async def list_domains():
    """Return metadata for all available demo domains."""
    from app.data_layer import DOMAIN_DATA

    domains = []
    for key, data in DOMAIN_DATA.items():
        if key == "mro":
            continue  # skip alias in listing — show facility_management only
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


@router.get(
    "/domains/extended",
    summary="List 10 domains with subdomains (v3.0)",
    tags=["domains"],
)
async def list_domains_extended():
    """Return domains + their subdomains, weights, and supplier counts."""
    from app.data_layer import DOMAIN_DATA

    result = []
    for key, data in DOMAIN_DATA.items():
        if key == "mro":
            continue
        meta = DOMAIN_META.get(key, {})
        wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(key, (0.40, 0.30, 0.15, 0.15))

        subs = []
        for sub_key, sub_data in SUBDOMAIN_DATA.get(key, {}).items():
            subs.append({
                "subdomain": sub_key,
                "suppliers_count": len(sub_data["suppliers"]),
                "demand_items": len(sub_data["demand"]),
                "products": sub_data["products"],
            })

        result.append({
            "domain": key,
            "label": meta.get("label", key),
            "icon": meta.get("icon", ""),
            "category": meta.get("category", ""),
            "suppliers_count": len(data["suppliers"]),
            "demand_items": len(data["demand"]),
            "regions": list(data["regions"].keys()),
            "default_weights": {"w_cost": wc, "w_time": wt, "w_compliance": wcomp, "w_esg": wesg},
            "subdomains": subs,
        })
    # Pre-computed rollups so the UI widget can render Direct/Indirect
    # summary chips without re-walking the tree.
    direct = [d for d in result if d["category"] == "direct"]
    indirect = [d for d in result if d["category"] == "indirect"]
    subdomains_total = sum(len(d["subdomains"]) for d in result)
    return {
        "domains": result,
        "total": len(result),
        "summary": {
            "domains_total": len(result),
            "direct_domains": len(direct),
            "indirect_domains": len(indirect),
            "subdomains_total": subdomains_total,
            "direct_subdomains": sum(len(d["subdomains"]) for d in direct),
            "indirect_subdomains": sum(len(d["subdomains"]) for d in indirect),
        },
    }


@router.get(
    "/domains/{domain}/subdomains",
    summary="List subdomains for a specific domain",
    tags=["domains"],
)
async def list_subdomains(domain: DemoDomain):
    """Return available subdomains and their stats for a domain."""
    try:
        sub_names = get_domain_subdomains(domain.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = []
    for sub_key in sub_names:
        sub_data = get_subdomain_data(domain.value, sub_key)
        result.append({
            "subdomain": sub_key,
            "suppliers_count": len(sub_data["suppliers"]),
            "demand_items": len(sub_data["demand"]),
            "products": sub_data["products"],
            "regions": sub_data["regions"],
        })
    return {"domain": domain.value, "subdomains": result, "total": len(result)}


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


# -----------------------------------------------------------------------
# 7. Process Mining — P2P (Procure-to-Pay) analysis
# -----------------------------------------------------------------------

def _events_to_dicts(req: ProcessMiningRequest) -> list[dict]:
    """Convert Pydantic EventLogEntry list to plain dicts for the engine."""
    return [e.model_dump() for e in req.events]


@router.post(
    "/process-mining/dfg",
    response_model=DFGResponse,
    summary="Discover Directly-Follows Graph from event log",
    tags=["process-mining"],
)
async def pm_dfg(req: ProcessMiningRequest) -> DFGResponse:
    """
    Build a **Directly-Follows Graph** (DFG) from P2P event logs.

    Returns nodes, edges (with frequency), start/end activities.
    Ready for BI visualisation (Power BI, Tableau, Qlik).
    """
    try:
        result = discover_dfg(_events_to_dicts(req))
        return DFGResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post(
    "/process-mining/lead-times",
    response_model=LeadTimeResponse,
    summary="Compute lead times between activities",
    tags=["process-mining"],
)
async def pm_lead_times(req: ProcessMiningRequest) -> LeadTimeResponse:
    """
    Calculate **lead time statistics** for each transition (activity → activity).

    Returns avg/median/p95/min/max hours per transition + case duration stats.
    """
    result = compute_lead_times(_events_to_dicts(req))
    return LeadTimeResponse(**result)


@router.post(
    "/process-mining/bottlenecks",
    response_model=BottleneckResponse,
    summary="Detect process bottlenecks",
    tags=["process-mining"],
)
async def pm_bottlenecks(req: ProcessMiningRequest) -> BottleneckResponse:
    """
    Identify **top-N bottleneck** transitions and activities.

    Returns slowest transitions, activity-level bottlenecks, and slowest cases.
    """
    result = detect_bottlenecks(_events_to_dicts(req), top_n=req.top_n)
    return BottleneckResponse(**result)


@router.post(
    "/process-mining/variants",
    response_model=VariantResponse,
    summary="Analyse process variants",
    tags=["process-mining"],
)
async def pm_variants(req: ProcessMiningRequest) -> VariantResponse:
    """
    Identify unique **process variants** (traces) with frequency and duration.
    """
    result = analyze_variants(_events_to_dicts(req))
    return VariantResponse(**result)


# ── Demo endpoint — uses built-in P2P event log ──────────────────────

@router.get(
    "/process-mining/demo/events",
    summary="Get demo P2P event log (10 cases)",
    tags=["process-mining"],
)
async def pm_demo_events():
    """Return the built-in demo P2P event log for testing."""
    return {"events": get_p2p_demo_events(), "total_events": len(get_p2p_demo_events())}


@router.get(
    "/process-mining/demo/dfg",
    response_model=DFGResponse,
    summary="DFG from demo P2P data",
    tags=["process-mining"],
)
async def pm_demo_dfg() -> DFGResponse:
    """Convenience: DFG discovery on built-in demo P2P event log."""
    try:
        result = discover_dfg(get_p2p_demo_events())
        return DFGResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get(
    "/process-mining/demo/lead-times",
    response_model=LeadTimeResponse,
    summary="Lead times from demo P2P data",
    tags=["process-mining"],
)
async def pm_demo_lead_times() -> LeadTimeResponse:
    """Convenience: lead time analysis on built-in demo P2P event log."""
    result = compute_lead_times(get_p2p_demo_events())
    return LeadTimeResponse(**result)


@router.get(
    "/process-mining/demo/bottlenecks",
    response_model=BottleneckResponse,
    summary="Bottlenecks from demo P2P data",
    tags=["process-mining"],
)
async def pm_demo_bottlenecks(top_n: int = 5) -> BottleneckResponse:
    """Convenience: bottleneck detection on built-in demo P2P event log."""
    result = detect_bottlenecks(get_p2p_demo_events(), top_n=top_n)
    return BottleneckResponse(**result)


@router.get(
    "/process-mining/demo/variants",
    response_model=VariantResponse,
    summary="Variants from demo P2P data",
    tags=["process-mining"],
)
async def pm_demo_variants() -> VariantResponse:
    """Convenience: variant analysis on built-in demo P2P event log."""
    result = analyze_variants(get_p2p_demo_events())
    return VariantResponse(**result)


# -----------------------------------------------------------------------
# 10. Dashboard v3.0 — XY Pareto, Sankey, Donut, Cross-domain Trend
# -----------------------------------------------------------------------

@router.post(
    "/dashboard/pareto-xy",
    summary="Generate XY Pareto scatter (cost PLN vs quality)",
    tags=["dashboard"],
)
async def dashboard_pareto_xy(
    req: DashboardRequest,
) -> dict:
    """XY Pareto front: X = total cost PLN, Y = weighted quality."""
    pts = generate_pareto_front_xy(
        suppliers=req.suppliers, demand=req.demand,
        base_weights=req.weights, mode=req.mode,
        steps=req.pareto_steps, max_vendor_share=req.max_vendor_share,
    )
    return {"points": [p.model_dump() for p in pts], "total": len(pts)}


@router.get(
    "/dashboard/pareto-xy/demo",
    summary="XY Pareto scatter with demo data",
    tags=["dashboard"],
)
async def dashboard_pareto_xy_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    mode: SolverMode = SolverMode.continuous,
    steps: int = 11,
    max_vendor_share: float = 0.60,
) -> dict:
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    pts = generate_pareto_front_xy(
        suppliers=suppliers, demand=demand, base_weights=weights,
        mode=mode, steps=steps, max_vendor_share=max_vendor_share,
    )
    return {"points": [p.model_dump() for p in pts], "total": len(pts)}


@router.post(
    "/dashboard/pareto-xy-mc",
    summary="XY Pareto scatter + Monte Carlo cost dispersion (B2)",
    tags=["dashboard"],
)
async def dashboard_pareto_xy_mc(
    req: DashboardRequest,
    mc_iterations: int = 50,
) -> dict:
    """Phase B2 — Pareto front with an MC confidence fan on cost.

    Each λ point carries baseline cost plus MC-derived P5/mean/P95 over
    `mc_iterations` perturbed re-solves. Default 50 is a pragmatic trade-off;
    bump to 200 for tighter bands when latency is acceptable.
    """
    pts = generate_pareto_with_mc(
        suppliers=req.suppliers, demand=req.demand,
        base_weights=req.weights, mode=req.mode,
        steps=req.pareto_steps, max_vendor_share=req.max_vendor_share,
        mc_iterations=max(5, min(500, mc_iterations)),
    )
    return {"points": [p.model_dump() for p in pts], "total": len(pts)}


@router.get(
    "/dashboard/pareto-xy-mc/demo",
    summary="XY Pareto + MC with demo data",
    tags=["dashboard"],
)
async def dashboard_pareto_xy_mc_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    mode: SolverMode = SolverMode.continuous,
    steps: int = 11,
    max_vendor_share: float = 0.60,
    mc_iterations: int = 50,
) -> dict:
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    pts = generate_pareto_with_mc(
        suppliers=suppliers, demand=demand, base_weights=weights,
        mode=mode, steps=steps, max_vendor_share=max_vendor_share,
        mc_iterations=max(5, min(500, mc_iterations)),
    )
    return {"points": [p.model_dump() for p in pts], "total": len(pts)}


@router.get(
    "/dashboard/sankey/demo",
    response_model=SankeyResponse,
    summary="Sankey allocation flow diagram (demo data)",
    tags=["dashboard"],
)
async def dashboard_sankey_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> SankeyResponse:
    """Supplier → Product allocation flows for Sankey visualisation."""
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    resp, _ = run_optimization(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=SolverMode.continuous, max_vendor_share=max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)

    nodes: list[SankeyNode] = []
    node_ids: set[str] = set()
    links: list[SankeyLink] = []
    total_flow = 0.0

    for a in resp.allocations:
        if a.allocated_fraction < 0.01:
            continue
        sid = f"sup_{a.supplier_id}"
        pid = f"prod_{a.product_id}"
        if sid not in node_ids:
            nodes.append(SankeyNode(id=sid, label=a.supplier_name, type="supplier"))
            node_ids.add(sid)
        if pid not in node_ids:
            nodes.append(SankeyNode(id=pid, label=a.product_id, type="product"))
            node_ids.add(pid)
        val = a.allocated_qty
        links.append(SankeyLink(
            source=sid, target=pid, value=val,
            label=f"{a.allocated_fraction:.0%}",
        ))
        total_flow += val

    return SankeyResponse(nodes=nodes, links=links, total_flow=total_flow)


@router.get(
    "/dashboard/donut/demo",
    response_model=DonutResponse,
    summary="Cost breakdown donut chart (demo data)",
    tags=["dashboard"],
)
async def dashboard_donut_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> DonutResponse:
    """Cost share per supplier as donut segments."""
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    resp, _ = run_optimization(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=SolverMode.continuous, max_vendor_share=max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)

    supplier_costs: dict[str, dict] = {}
    for a in resp.allocations:
        if a.allocated_fraction < 0.01:
            continue
        cost = (a.unit_cost + a.logistics_cost) * a.allocated_qty
        entry = supplier_costs.setdefault(a.supplier_id, {
            "supplier_id": a.supplier_id,
            "supplier_name": a.supplier_name,
            "total_cost_pln": 0.0,
        })
        entry["total_cost_pln"] += cost

    total = sum(e["total_cost_pln"] for e in supplier_costs.values())
    segments = [
        DonutSegment(
            supplier_id=e["supplier_id"],
            supplier_name=e["supplier_name"],
            total_cost_pln=round(e["total_cost_pln"], 2),
            fraction=round(e["total_cost_pln"] / total, 4) if total > 0 else 0,
        )
        for e in sorted(supplier_costs.values(), key=lambda x: -x["total_cost_pln"])
    ]
    return DonutResponse(segments=segments, total_cost_pln=round(total, 2))


@router.get(
    "/dashboard/trend/demo",
    response_model=DomainTrendResponse,
    summary="Cross-domain comparison trend (demo data)",
    tags=["dashboard"],
)
async def dashboard_trend_demo(
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> DomainTrendResponse:
    """Compare optimisation results across all 10 domains."""
    from app.data_layer import DOMAIN_DATA

    pts: list[DomainTrendPoint] = []
    for key in DOMAIN_DATA:
        if key == "mro":
            continue
        try:
            suppliers, demand = _load_domain(key)
        except HTTPException:
            continue
        weights = _domain_weights(key, lambda_param)
        resp, _ = run_optimization(
            suppliers=suppliers, demand=demand, weights=weights,
            mode=SolverMode.continuous, max_vendor_share=max_vendor_share,
        )
        if not resp.success:
            continue

        total_cost = sum(
            (a.unit_cost + a.logistics_cost) * a.allocated_qty
            for a in resp.allocations if a.allocated_fraction > 0.01
        )
        active = len({a.supplier_id for a in resp.allocations if a.allocated_fraction > 0.01})
        meta = DOMAIN_META.get(key, {})

        pts.append(DomainTrendPoint(
            domain=key,
            label=meta.get("label", key),
            objective_total=resp.objective.total,
            cost_component=resp.objective.cost_component,
            time_component=resp.objective.time_component,
            compliance_component=resp.objective.compliance_component,
            esg_component=resp.objective.esg_component,
            total_cost_pln=round(total_cost, 2),
            suppliers_used=active,
        ))
    return DomainTrendResponse(points=pts, total_domains=len(pts))
