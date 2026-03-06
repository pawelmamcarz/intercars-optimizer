"""
v3.0 — Risk Engine Routes.

Endpoints:
  POST /risk/heatmap              — risk heatmap from optimisation result
  GET  /risk/heatmap/demo         — demo risk heatmap
  POST /risk/monte-carlo          — Monte Carlo simulation
  GET  /risk/monte-carlo/demo     — demo MC (500 iterations)
  POST /risk/negotiation          — negotiation target analysis
  GET  /risk/negotiation/demo     — demo negotiation targets
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.optimizer import run_optimization
from app.risk_engine import MonteCarloEngine, NegotiationAssistant, RiskHeatmapEngine
from app.schemas import (
    CriteriaWeights,
    DemoDomain,
    MonteCarloRequest,
    MonteCarloResponse,
    NegotiationResponse,
    OptimizationRequest,
    RiskHeatmapResponse,
    SolverMode,
)

risk_router = APIRouter(prefix="/risk", tags=["risk"])


def _load_domain(domain: str):
    from app.data_layer import get_domain_data
    try:
        d = get_domain_data(domain)
        return d["suppliers"], d["demand"]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain}")


def _domain_weights(domain: str, lam: float = 0.5) -> CriteriaWeights:
    from app.routes import DOMAIN_WEIGHTS
    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
    return CriteriaWeights(lambda_param=lam, w_cost=wc, w_time=wt, w_compliance=wcomp, w_esg=wesg)


# ── Risk Heatmap ──────────────────────────────────────────────────────

@risk_router.post(
    "/heatmap",
    response_model=RiskHeatmapResponse,
    summary="Risk heatmap from optimisation result",
)
async def risk_heatmap(req: OptimizationRequest) -> RiskHeatmapResponse:
    resp, _ = run_optimization(
        suppliers=req.suppliers, demand=req.demand,
        weights=req.weights, mode=req.mode,
        max_vendor_share=req.max_vendor_share,
        constraints=req.constraints,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return RiskHeatmapEngine.compute(req.suppliers, req.demand, resp.allocations)


@risk_router.get(
    "/heatmap/demo",
    response_model=RiskHeatmapResponse,
    summary="Demo risk heatmap",
)
async def risk_heatmap_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> RiskHeatmapResponse:
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    resp, _ = run_optimization(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=SolverMode.continuous, max_vendor_share=max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return RiskHeatmapEngine.compute(suppliers, demand, resp.allocations)


# ── Monte Carlo ───────────────────────────────────────────────────────

@risk_router.post(
    "/monte-carlo",
    response_model=MonteCarloResponse,
    summary="Monte Carlo cost/risk simulation",
)
async def risk_monte_carlo(req: MonteCarloRequest) -> MonteCarloResponse:
    engine = MonteCarloEngine(
        suppliers=req.suppliers, demand=req.demand, weights=req.weights,
        n_iterations=req.n_iterations, cost_std_pct=req.cost_std_pct,
        time_std_pct=req.time_std_pct, max_vendor_share=req.max_vendor_share,
        seed=req.seed,
    )
    return engine.run()


@risk_router.get(
    "/monte-carlo/demo",
    response_model=MonteCarloResponse,
    summary="Demo Monte Carlo simulation (500 iterations)",
)
async def risk_monte_carlo_demo(
    domain: DemoDomain = DemoDomain.parts,
    n_iterations: int = 500,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> MonteCarloResponse:
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    engine = MonteCarloEngine(
        suppliers=suppliers, demand=demand, weights=weights,
        n_iterations=n_iterations, max_vendor_share=max_vendor_share,
        seed=42,
    )
    return engine.run()


# ── Negotiation ───────────────────────────────────────────────────────

@risk_router.post(
    "/negotiation",
    response_model=NegotiationResponse,
    summary="Negotiation target analysis",
)
async def risk_negotiation(req: OptimizationRequest) -> NegotiationResponse:
    resp, _ = run_optimization(
        suppliers=req.suppliers, demand=req.demand,
        weights=req.weights, mode=req.mode,
        max_vendor_share=req.max_vendor_share,
        constraints=req.constraints,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return NegotiationAssistant.analyze(req.suppliers, resp.allocations)


@risk_router.get(
    "/negotiation/demo",
    response_model=NegotiationResponse,
    summary="Demo negotiation targets",
)
async def risk_negotiation_demo(
    domain: DemoDomain = DemoDomain.parts,
    lambda_param: float = 0.5,
    max_vendor_share: float = 0.60,
) -> NegotiationResponse:
    suppliers, demand = _load_domain(domain.value)
    weights = _domain_weights(domain.value, lambda_param)
    resp, _ = run_optimization(
        suppliers=suppliers, demand=demand, weights=weights,
        mode=SolverMode.continuous, max_vendor_share=max_vendor_share,
    )
    if not resp.success:
        raise HTTPException(status_code=422, detail=resp.message)
    return NegotiationAssistant.analyze(suppliers, resp.allocations)
