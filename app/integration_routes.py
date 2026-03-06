"""
v3.1 — Generic RFQ Integration Routes (vendor-agnostic).

Endpoints:
  POST /integration/rfq/import   — import RFQ, optionally auto-optimise
  POST /integration/rfq/export   — export optimisation result (generic JSON)
  GET  /integration/status       — health-check RFQ connectivity
  POST /integration/webhook      — receive events (rfq.created, bid.received, etc.)
  GET  /integration/rfq/demo     — generate a demo RFQ
  GET  /integration/rfq/{rfq_id} — retrieve stored RFQ
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.integration_engine import (
    RfqTransformer,
    generate_demo_rfq,
    get_rfq,
    list_rfqs,
    store_rfq,
)
from app.optimizer import run_optimization
from app.schemas import (
    CriteriaWeights,
    IntegrationStatusResponse,
    RfqExportRequest,
    RfqExportResponse,
    RfqImportRequest,
    RfqResponse,
    WebhookPayload,
    WebhookResponse,
)

integration_router = APIRouter(prefix="/integration", tags=["integration"])


# ── RFQ Import ────────────────────────────────────────────────────────

@integration_router.post(
    "/rfq/import",
    response_model=RfqResponse,
    summary="Import RFQ and optionally run optimisation",
)
async def rfq_import(req: RfqImportRequest) -> RfqResponse:
    """
    Accept an RFQ (with bids), store it, and optionally run the optimizer.

    If `auto_optimize=True`, converts bids → SupplierInput, runs LP/MIP,
    and returns the allocation result alongside the stored RFQ.
    """
    rfq = req.rfq
    store_rfq(rfq)

    opt_result = None
    if req.auto_optimize:
        suppliers, demand = RfqTransformer.rfq_to_optimizer_input(rfq)
        weights = CriteriaWeights(
            lambda_param=0.5,
            w_cost=0.40, w_time=0.30, w_compliance=0.15, w_esg=0.15,
        )
        resp, _ = run_optimization(
            suppliers=suppliers, demand=demand, weights=weights,
            mode=req.optimization_mode, max_vendor_share=0.60,
        )
        if resp.success:
            opt_result = resp

    return RfqResponse(
        success=True,
        rfq_id=rfq.rfq_id,
        message="RFQ imported" + (" and optimised" if opt_result else ""),
        imported_line_items=len(rfq.line_items),
        imported_bids=len(rfq.bids),
        optimization_result=opt_result,
    )


# ── RFQ Export ───────────────────────────────────────────────────────

@integration_router.post(
    "/rfq/export",
    response_model=RfqExportResponse,
    summary="Export optimisation result (generic RFQ JSON format)",
)
async def rfq_export(req: RfqExportRequest) -> RfqExportResponse:
    """
    Convert stored RFQ + allocation result → generic export rows.

    Compatible with any downstream ERP/sourcing system.
    Requires the RFQ to be previously imported via /rfq/import.
    """
    rfq = get_rfq(req.rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail=f"RFQ {req.rfq_id} not found")

    rows = RfqTransformer.optimization_to_export(
        rfq_id=req.rfq_id,
        allocations=req.allocations,
        line_items=req.line_items,
    )
    total_val = sum(r.total_line_value_pln for r in rows)
    return RfqExportResponse(
        success=True,
        rfq_id=req.rfq_id,
        export_format="GENERIC-RFQ-JSON",
        rows=rows,
        total_value_pln=total_val,
    )


# ── Integration Status ───────────────────────────────────────────────

@integration_router.get(
    "/status",
    response_model=IntegrationStatusResponse,
    summary="Check RFQ integration connectivity status",
)
async def integration_status() -> IntegrationStatusResponse:
    """
    Health-check for external RFQ integration endpoints.

    In demo mode returns simulated connectivity status.
    In production, would ping the configured RFQ import/export APIs.
    """
    import_ok = bool(settings.rfq_import_api_key)
    export_ok = bool(settings.rfq_export_api_key)
    pending = [r for r in list_rfqs() if r["status"] == "active"]

    return IntegrationStatusResponse(
        rfq_import_configured=import_ok,
        rfq_export_configured=export_ok,
        pending_rfqs=len(pending),
        import_url=settings.rfq_import_url,
        export_url=settings.rfq_export_url,
    )


# ── Webhook ───────────────────────────────────────────────────────────

@integration_router.post(
    "/webhook",
    response_model=WebhookResponse,
    summary="Receive webhook events from external RFQ system",
)
async def webhook_receive(payload: WebhookPayload) -> WebhookResponse:
    """
    Process incoming webhook events:
    - rfq.created → log new RFQ
    - bid.received → log bid update
    - rfq.closed → mark RFQ as closed
    """
    event = payload.event_type
    rfq_id = payload.rfq_id

    if event == "rfq.closed":
        rfq = get_rfq(rfq_id)
        if rfq:
            rfq.status = "closed"
            store_rfq(rfq)
        msg = f"RFQ {rfq_id} closed"
    elif event == "rfq.created":
        msg = f"RFQ {rfq_id} registered (awaiting bids)"
    elif event == "bid.received":
        msg = f"Bid received for RFQ {rfq_id}"
    else:
        msg = f"Unknown event '{event}' for RFQ {rfq_id}"

    return WebhookResponse(
        success=True,
        event_type=event,
        processed=True,
        message=msg,
    )


# ── RFQ Retrieval ─────────────────────────────────────────────────────

@integration_router.get(
    "/rfq/demo",
    summary="Generate a demo RFQ for testing",
)
async def rfq_demo(domain: str = "parts"):
    """Generate and store a demo RFQ with 5 line items and 4 bids."""
    rfq = generate_demo_rfq(domain)
    store_rfq(rfq)
    return {
        "rfq": rfq,
        "message": f"Demo RFQ {rfq.rfq_id} generated and stored",
    }


@integration_router.get(
    "/rfq/{rfq_id}",
    summary="Retrieve a stored RFQ by ID",
)
async def rfq_get(rfq_id: str):
    """Fetch a previously stored RFQ."""
    rfq = get_rfq(rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail=f"RFQ {rfq_id} not found")
    return {"rfq": rfq, "stored_rfqs": len(list_rfqs())}
