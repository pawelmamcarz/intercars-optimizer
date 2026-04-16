"""
What-If Scenario & Alerts Router — scenario comparison + alert generation.

Endpoints:
  POST /whatif/scenarios         — run 2-10 scenarios with custom data
  GET  /whatif/scenarios/demo    — demo comparison (Baseline vs Tight Budget vs Green)
  POST /whatif/alerts            — generate optimization alerts
  POST /whatif/alerts/process    — generate process alerts from event log
  GET  /whatif/alerts/demo       — demo alerts from demo data
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.alerts_engine import AlertsEngine, Alert
from app.data_layer import get_domain_data, get_p2p_demo_events, DOMAIN_WEIGHTS
from app.process_digging import ProcessDiggingEngine
from app.schemas import (
    AlertThresholds,
    AlertsResponse,
    CriteriaWeights,
    DemandItem,
    DemoDomain,
    SupplierInput,
    WhatIfRequest,
    WhatIfResponse,
)
from app.whatif_engine import WhatIfEngine

whatif_router = APIRouter()


# ── Request models ─────────────────────────────────────────────────

class OptimizationAlertRequest(BaseModel):
    """Request for optimization alerts — includes solver result + thresholds."""

    result: dict = Field(..., description="Optimization result dict (from /optimize or /mip/optimize)")
    thresholds: Optional[AlertThresholds] = None


class ProcessAlertRequest(BaseModel):
    """Request for process alerts — includes event log."""

    events: list[dict] = Field(..., min_length=2)
    thresholds: Optional[AlertThresholds] = None
    sla_target_hours: Optional[float] = Field(None, gt=0)



# -----------------------------------------------------------------------
# 1. What-If Scenarios
# -----------------------------------------------------------------------

@whatif_router.post(
    "/whatif/scenarios",
    response_model=WhatIfResponse,
    summary="Run 2-10 optimisation scenarios and compare results",
    tags=["what-if"],
)
async def whatif_scenarios(req: WhatIfRequest) -> WhatIfResponse:
    """
    **What-If Scenario Builder** — run multiple scenarios with different parameters.

    Each scenario can vary: lambda, weights, mode (LP/MIP), budget, SLA floor, etc.
    Returns a comparison matrix showing which scenario is best for each metric.
    """
    engine = WhatIfEngine(suppliers=req.suppliers, demand=req.demand)
    specs = [s.model_dump() for s in req.scenarios]
    result = engine.run_all(specs)
    return WhatIfResponse(**result)


@whatif_router.get(
    "/whatif/scenarios/demo",
    response_model=WhatIfResponse,
    summary="Demo what-if comparison: Baseline vs Tight Budget vs Green Focus",
    tags=["what-if"],
)
async def whatif_scenarios_demo(
    domain: DemoDomain = DemoDomain.it_services,
) -> WhatIfResponse:
    """Run 3 pre-built scenarios on demo data for comparison."""
    try:
        data = get_domain_data(domain.value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain.value}")

    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain.value, (0.40, 0.30, 0.15, 0.15))

    scenarios = [
        {
            "label": "Baseline (LP)",
            "lambda_param": 0.5,
            "w_cost": wc, "w_time": wt, "w_compliance": wcomp, "w_esg": wesg,
            "mode": "continuous",
            "max_vendor_share": 0.60,
        },
        {
            "label": "Cost Focus (LP)",
            "lambda_param": 0.9,
            "w_cost": 0.50, "w_time": 0.20, "w_compliance": 0.15, "w_esg": 0.15,
            "mode": "continuous",
            "max_vendor_share": 1.0,
        },
        {
            "label": "Green Focus (LP)",
            "lambda_param": 0.3,
            "w_cost": 0.25, "w_time": 0.25, "w_compliance": 0.20, "w_esg": 0.30,
            "mode": "continuous",
            "max_vendor_share": 0.50,
        },
    ]

    engine = WhatIfEngine(suppliers=data["suppliers"], demand=data["demand"])
    result = engine.run_all(scenarios)
    return WhatIfResponse(**result)


class ChainStep(BaseModel):
    """One incremental delta applied on top of the accumulated state."""
    label: Optional[str] = None
    lambda_param: Optional[float] = None
    w_cost: Optional[float] = None
    w_time: Optional[float] = None
    w_compliance: Optional[float] = None
    w_esg: Optional[float] = None
    mode: Optional[str] = None
    max_vendor_share: Optional[float] = None
    sla_floor: Optional[float] = None
    total_budget: Optional[float] = None
    max_products_per_supplier: Optional[int] = None


class ChainRequest(BaseModel):
    suppliers: list[SupplierInput] = Field(..., min_length=1)
    demand: list[DemandItem] = Field(..., min_length=1)
    base: Optional[ChainStep] = None
    steps: list[ChainStep] = Field(..., min_length=1, max_length=10)


@whatif_router.post(
    "/whatif/chain",
    summary="Phase B3 — cumulative scenario chain (each step deltas on top of previous)",
    tags=["what-if"],
)
async def whatif_chain(req: ChainRequest) -> dict:
    engine = WhatIfEngine(suppliers=req.suppliers, demand=req.demand)
    steps = [s.model_dump(exclude_none=True) for s in req.steps]
    base = req.base.model_dump(exclude_none=True) if req.base else None
    return engine.run_chain(steps=steps, base=base)


@whatif_router.get(
    "/whatif/chain/demo",
    summary="Demo scenario chain on demo data",
    tags=["what-if"],
)
async def whatif_chain_demo(domain: DemoDomain = DemoDomain.parts) -> dict:
    try:
        data = get_domain_data(domain.value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain.value}")

    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain.value, (0.40, 0.30, 0.15, 0.15))
    base = {
        "label": "Start (baseline)",
        "lambda_param": 0.5,
        "w_cost": wc, "w_time": wt, "w_compliance": wcomp, "w_esg": wesg,
        "mode": "continuous",
        "max_vendor_share": 0.60,
    }
    # Story: buyer starts balanced, then asks 4 "a co jesli..." questions
    steps = [
        {"label": "...a co jesli tanszy?", "lambda_param": 0.9, "w_cost": 0.55, "w_time": 0.15},
        {"label": "...oraz min dywersyfikacja 50%", "max_vendor_share": 0.50},
        {"label": "...a gdyby budget 500k PLN?", "total_budget": 500000, "mode": "continuous"},
        {"label": "...plus priorytet ESG", "w_esg": 0.30, "w_cost": 0.35},
    ]
    engine = WhatIfEngine(suppliers=data["suppliers"], demand=data["demand"])
    return engine.run_chain(steps=steps, base=base)


# -----------------------------------------------------------------------
# 2. Alerts
# -----------------------------------------------------------------------

@whatif_router.post(
    "/whatif/alerts",
    response_model=AlertsResponse,
    summary="Generate optimisation alerts from solver result",
    tags=["alerts"],
)
async def whatif_alerts(req: OptimizationAlertRequest) -> AlertsResponse:
    """
    **Optimisation Alerts** — check solver results for issues.

    Detects: budget overrun, supplier concentration, infeasible products, high cost.
    """
    thresholds = req.thresholds.model_dump() if req.thresholds else None
    engine = AlertsEngine(thresholds=thresholds)
    alerts = engine.check_optimization(req.result)
    return AlertsResponse(**engine.format_response(alerts))


@whatif_router.post(
    "/whatif/alerts/process",
    response_model=AlertsResponse,
    summary="Generate process alerts from P2P event log",
    tags=["alerts"],
)
async def whatif_alerts_process(req: ProcessAlertRequest) -> AlertsResponse:
    """
    **Process Alerts** — analyze event log and flag issues.

    Detects: SLA breaches, low conformance, bottlenecks, rework, anomalies.
    """
    try:
        pm_engine = ProcessDiggingEngine(req.events)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    report = pm_engine.full_report()
    thresholds = req.thresholds.model_dump() if req.thresholds else None
    alerts_engine = AlertsEngine(thresholds=thresholds)
    alerts = alerts_engine.check_process(report)
    return AlertsResponse(**alerts_engine.format_response(alerts))


@whatif_router.get(
    "/whatif/alerts/demo",
    response_model=AlertsResponse,
    summary="Demo alerts from demo data (optimization + process)",
    tags=["alerts"],
)
async def whatif_alerts_demo(
    domain: DemoDomain = DemoDomain.it_services,
) -> AlertsResponse:
    """Generate alerts from demo optimization + demo P2P data."""
    import logging
    logger = logging.getLogger(__name__)
    alerts_engine = AlertsEngine()
    all_alerts = []

    # 1. Optimization alerts from demo LP run
    try:
        from app.optimizer import run_optimization
        data = get_domain_data(domain.value)
        wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain.value, (0.40, 0.30, 0.15, 0.15))
        weights = CriteriaWeights(lambda_param=0.5, w_cost=wc, w_time=wt, w_compliance=wcomp, w_esg=wesg)
        resp, _ = run_optimization(
            suppliers=data["suppliers"], demand=data["demand"],
            weights=weights, max_vendor_share=0.60,
        )
        opt_result = {
            "success": resp.success,
            "message": resp.message,
            "objective": resp.objective.model_dump(),
            "allocations": [a.model_dump() for a in resp.allocations],
            "diagnostics": resp.diagnostics.model_dump() if hasattr(resp, 'diagnostics') and resp.diagnostics else {},
        }
        all_alerts.extend(alerts_engine.check_optimization(opt_result))
    except Exception as e:
        logger.warning("Alert demo — optimization failed: %s", e)
        all_alerts.append(Alert(
            severity="warning",
            category="optimization",
            title="Optymalizacja niedostepna",
            description=f"Solver nie mogl uruchomic demo: {str(e)[:120]}",
        ))

    # 2. Process alerts from demo P2P data
    try:
        pm_engine = ProcessDiggingEngine(get_p2p_demo_events())
        report = pm_engine.full_report()
        all_alerts.extend(alerts_engine.check_process(report))
    except Exception as e:
        logger.warning("Alert demo — process mining failed: %s", e)
        all_alerts.append(Alert(
            severity="info",
            category="process",
            title="Process Mining niedostepny",
            description=f"Nie udalo sie wygenerowac analizy P2P: {str(e)[:120]}",
        ))

    # 3. Always add some useful system alerts
    if not all_alerts:
        all_alerts.append(Alert(
            severity="info",
            category="optimization",
            title="System gotowy",
            description="Brak alertow krytycznych. Wszystkie moduly dzialaja poprawnie.",
        ))

    return AlertsResponse(**alerts_engine.format_response(all_alerts))
