"""
Process Digging — dedicated FastAPI router for advanced P2P analysis.

Endpoints:
  POST /process-digging/performance-dfg   — DFG weighted by transition time
  POST /process-digging/conformance       — compare discovered vs reference process
  POST /process-digging/handovers         — resource handover social network
  POST /process-digging/full-report       — all analyses in one call
  GET  /process-digging/demo/...          — convenience endpoints using demo data
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data_layer import get_p2p_demo_events
from app.process_digging import ProcessDiggingEngine
from app.schemas import (
    BottleneckResponse,
    ConformanceResponse,
    DFGResponse,
    FullProcessDiggingReport,
    HandoverResponse,
    LeadTimeResponse,
    PerformanceDFGResponse,
    ProcessMiningRequest,
    VariantResponse,
)

digging_router = APIRouter()


# ── Request model with optional reference path override ──────────────────

class ConformanceRequest(BaseModel):
    """Request for conformance checking with optional custom reference path."""

    events: list[dict] = Field(..., min_length=2)
    reference_path: Optional[list[str]] = Field(
        None,
        description="Custom reference path. If omitted, uses INTERCARS standard P2P.",
    )
    top_n: int = Field(5, ge=1, le=50)


class DiggingRequest(BaseModel):
    """Request for full process digging report."""

    events: list[dict] = Field(..., min_length=2)
    top_n: int = Field(5, ge=1, le=50)
    reference_path: Optional[list[str]] = None


# ── Helper: convert ProcessMiningRequest events to dicts ─────────────────

def _pm_events_to_dicts(req: ProcessMiningRequest) -> list[dict]:
    return [e.model_dump() for e in req.events]


def _build_engine(events: list[dict]) -> ProcessDiggingEngine:
    """Create engine, raising 503 if pm4py unavailable."""
    try:
        return ProcessDiggingEngine(events)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# -----------------------------------------------------------------------
# POST endpoints — accept custom event logs
# -----------------------------------------------------------------------

@digging_router.post(
    "/process-digging/dfg",
    response_model=DFGResponse,
    summary="Frequency DFG via Process Digging Engine",
    tags=["process-digging"],
)
async def digging_dfg(req: ProcessMiningRequest) -> DFGResponse:
    """Discover frequency-based DFG using the Process Digging Engine."""
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.discover_dfg()
    return DFGResponse(**result)


@digging_router.post(
    "/process-digging/performance-dfg",
    response_model=PerformanceDFGResponse,
    summary="Performance DFG — edges weighted by transition time",
    tags=["process-digging"],
)
async def digging_performance_dfg(req: ProcessMiningRequest) -> PerformanceDFGResponse:
    """
    **Performance DFG** — each edge carries avg/median/p95 transition time (hours).

    This is what BI dashboards need to visualise bottlenecks directly on the graph.
    """
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.discover_performance_dfg()
    return PerformanceDFGResponse(**result)


@digging_router.post(
    "/process-digging/lead-times",
    response_model=LeadTimeResponse,
    summary="Lead times via Process Digging Engine",
    tags=["process-digging"],
)
async def digging_lead_times(req: ProcessMiningRequest) -> LeadTimeResponse:
    """Per-transition and per-case lead time statistics."""
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.compute_lead_times()
    return LeadTimeResponse(**result)


@digging_router.post(
    "/process-digging/bottlenecks",
    response_model=BottleneckResponse,
    summary="Bottleneck detection via Process Digging Engine",
    tags=["process-digging"],
)
async def digging_bottlenecks(req: ProcessMiningRequest) -> BottleneckResponse:
    """Multi-layer bottleneck detection: transition, activity, and case level."""
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.detect_bottlenecks(top_n=req.top_n)
    return BottleneckResponse(**result)


@digging_router.post(
    "/process-digging/variants",
    response_model=VariantResponse,
    summary="Variant analysis via Process Digging Engine",
    tags=["process-digging"],
)
async def digging_variants(req: ProcessMiningRequest) -> VariantResponse:
    """Group cases by unique activity trace with frequency and duration stats."""
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.analyze_variants()
    return VariantResponse(**result)


@digging_router.post(
    "/process-digging/conformance",
    response_model=ConformanceResponse,
    summary="Conformance check — discovered vs reference P2P path",
    tags=["process-digging"],
)
async def digging_conformance(req: ConformanceRequest) -> ConformanceResponse:
    """
    **Conformance Checking** — compare discovered process against reference path.

    Returns per-case fitness (0..1), missing/extra activities, order correctness.
    Default reference: INTERCARS standard P2P (8 steps).
    """
    engine = _build_engine(req.events)
    result = engine.check_conformance(reference_path=req.reference_path)
    return ConformanceResponse(**result)


@digging_router.post(
    "/process-digging/handovers",
    response_model=HandoverResponse,
    summary="Resource handover — social network analysis",
    tags=["process-digging"],
)
async def digging_handovers(req: ProcessMiningRequest) -> HandoverResponse:
    """
    **Resource Handover Analysis** — who passes work to whom.

    Returns social network graph of resource interactions.
    Requires 'resource' field in event log entries.
    """
    engine = _build_engine(_pm_events_to_dicts(req))
    result = engine.analyze_handovers()
    return HandoverResponse(**result)


@digging_router.post(
    "/process-digging/full-report",
    response_model=FullProcessDiggingReport,
    summary="Full process digging report — all analyses combined",
    tags=["process-digging"],
)
async def digging_full_report(req: DiggingRequest) -> FullProcessDiggingReport:
    """
    **Complete P2P Process Analysis** in one call.

    Returns: DFG (frequency + performance), lead times, bottlenecks,
    variants, conformance, and resource handovers.

    Ideal for BI dashboard initial load (Power BI, Tableau, Qlik, Looker, Metabase).
    """
    engine = _build_engine(req.events)
    report = engine.full_report(top_n=req.top_n)

    # Patch conformance if custom reference path provided
    if req.reference_path:
        report["conformance"] = engine.check_conformance(reference_path=req.reference_path)

    return FullProcessDiggingReport(
        dfg_frequency=DFGResponse(**report["dfg_frequency"]),
        dfg_performance=PerformanceDFGResponse(**report["dfg_performance"]),
        lead_times=LeadTimeResponse(**report["lead_times"]),
        bottlenecks=BottleneckResponse(**report["bottlenecks"]),
        variants=VariantResponse(**report["variants"]),
        conformance=ConformanceResponse(**report["conformance"]),
        handovers=HandoverResponse(**report["handovers"]),
    )


# -----------------------------------------------------------------------
# Demo endpoints — uses built-in P2P event log
# -----------------------------------------------------------------------

@digging_router.get(
    "/process-digging/demo/performance-dfg",
    response_model=PerformanceDFGResponse,
    summary="Performance DFG from demo P2P data",
    tags=["process-digging"],
)
async def digging_demo_performance_dfg() -> PerformanceDFGResponse:
    """Performance DFG on built-in demo P2P event log."""
    engine = _build_engine(get_p2p_demo_events())
    result = engine.discover_performance_dfg()
    return PerformanceDFGResponse(**result)


@digging_router.get(
    "/process-digging/demo/conformance",
    response_model=ConformanceResponse,
    summary="Conformance check from demo P2P data",
    tags=["process-digging"],
)
async def digging_demo_conformance() -> ConformanceResponse:
    """Conformance checking on demo data vs INTERCARS standard P2P path."""
    engine = _build_engine(get_p2p_demo_events())
    result = engine.check_conformance()
    return ConformanceResponse(**result)


@digging_router.get(
    "/process-digging/demo/handovers",
    response_model=HandoverResponse,
    summary="Resource handovers from demo P2P data",
    tags=["process-digging"],
)
async def digging_demo_handovers() -> HandoverResponse:
    """Resource handover social network on demo data."""
    engine = _build_engine(get_p2p_demo_events())
    result = engine.analyze_handovers()
    return HandoverResponse(**result)


@digging_router.get(
    "/process-digging/demo/full-report",
    response_model=FullProcessDiggingReport,
    summary="Full process digging report from demo data",
    tags=["process-digging"],
)
async def digging_demo_full_report(top_n: int = 5) -> FullProcessDiggingReport:
    """Complete P2P analysis on built-in demo data — one call for BI dashboards."""
    engine = _build_engine(get_p2p_demo_events())
    report = engine.full_report(top_n=top_n)
    return FullProcessDiggingReport(
        dfg_frequency=DFGResponse(**report["dfg_frequency"]),
        dfg_performance=PerformanceDFGResponse(**report["dfg_performance"]),
        lead_times=LeadTimeResponse(**report["lead_times"]),
        bottlenecks=BottleneckResponse(**report["bottlenecks"]),
        variants=VariantResponse(**report["variants"]),
        conformance=ConformanceResponse(**report["conformance"]),
        handovers=HandoverResponse(**report["handovers"]),
    )
