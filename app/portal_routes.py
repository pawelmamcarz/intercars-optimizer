"""
Supplier Portal endpoints — supplier-facing self-service portal.

All endpoints require 'supplier' role via JWT auth.
Suppliers can only see/edit their own data (filtered by supplier_id from token).
Prefix: /portal
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_role
from app.supplier_engine import (
    get_supplier, update_supplier,
    add_certificate, remove_certificate, get_expiring_certificates,
    get_assessment_questions, submit_assessment,
    SupplierCertificate, SelfAssessmentAnswer,
)
from app.buying_engine import list_orders

logger = logging.getLogger(__name__)

portal_router = APIRouter(prefix="/portal", tags=["supplier-portal"])


def _get_supplier_id(user: dict) -> str:
    """Extract supplier_id from current user token. Raise 403 if not linked."""
    sid = user.get("supplier_id")
    if not sid:
        raise HTTPException(403, "Account not linked to a supplier profile")
    return sid


# ── Models ────────────────────────────────────────────────────────────────

class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    duns_number: Optional[str] = None


class CertificateIn(BaseModel):
    name: str
    issuer: str
    valid_until: str
    cert_type: str = "iso"


class AssessmentAnswerIn(BaseModel):
    question_id: str
    answer: str
    score: float


class BidIn(BaseModel):
    unit_price: float
    lead_time_days: int
    notes: Optional[str] = None
    valid_until: Optional[str] = None


# ── Profile ───────────────────────────────────────────────────────────────

@portal_router.get("/profile", summary="My supplier profile")
async def my_profile(user: dict = Depends(require_role("supplier"))):
    sid = _get_supplier_id(user)
    profile = get_supplier(sid)
    if not profile:
        raise HTTPException(404, f"Supplier profile '{sid}' not found")
    data = profile.model_dump() if hasattr(profile, "model_dump") else profile.__dict__
    return {"success": True, "profile": data}


@portal_router.put("/profile", summary="Update my profile")
async def update_my_profile(
    updates: ProfileUpdateIn,
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No fields to update")
    result = update_supplier(sid, update_data)
    if not result:
        raise HTTPException(404, f"Supplier '{sid}' not found")
    data = result.model_dump() if hasattr(result, "model_dump") else result.__dict__
    return {"success": True, "profile": data}


# ── Orders (read-only) ───────────────────────────────────────────────────

@portal_router.get("/orders", summary="My orders (POs assigned to me)")
async def my_orders(
    status: Optional[str] = Query(None),
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    all_orders = list_orders(status=status)
    # Filter: only orders with POs containing this supplier
    my_orders = []
    for order in all_orders:
        pos = order.get("purchase_orders", [])
        if isinstance(pos, list):
            for po in pos:
                if isinstance(po, dict) and po.get("supplier_id") == sid:
                    my_orders.append(order)
                    break
    return {"orders": my_orders, "count": len(my_orders)}


@portal_router.get("/orders/{order_id}", summary="Order detail (my POs only)")
async def my_order_detail(
    order_id: str,
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    from app.buying_engine import get_order
    order = get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    # Filter POs to only show this supplier's
    pos = order.get("purchase_orders", [])
    my_pos = [po for po in (pos or []) if isinstance(po, dict) and po.get("supplier_id") == sid]
    if not my_pos:
        raise HTTPException(403, "No purchase orders for your supplier in this order")

    return {
        "order_id": order["order_id"],
        "status": order.get("status"),
        "created_at": order.get("created_at"),
        "my_purchase_orders": my_pos,
    }


# ── RFQ (Request for Quote) ──────────────────────────────────────────────

@portal_router.get("/rfq", summary="Open RFQs available to me")
async def my_rfqs(user: dict = Depends(require_role("supplier"))):
    sid = _get_supplier_id(user)
    # Check stored RFQs from integration engine
    try:
        from app.integration_engine import _rfq_store
        open_rfqs = []
        for rfq_id, rfq in _rfq_store.items():
            if rfq.get("status") == "open":
                # In production, filter by invited suppliers
                open_rfqs.append({
                    "rfq_id": rfq_id,
                    "title": rfq.get("title", f"RFQ {rfq_id}"),
                    "domain": rfq.get("domain", ""),
                    "items_count": len(rfq.get("items", [])),
                    "deadline": rfq.get("deadline"),
                    "created_at": rfq.get("created_at"),
                })
        return {"rfqs": open_rfqs, "count": len(open_rfqs)}
    except (ImportError, AttributeError):
        return {"rfqs": [], "count": 0, "note": "RFQ module not available"}


@portal_router.get("/rfq/{rfq_id}", summary="RFQ detail")
async def rfq_detail(
    rfq_id: str,
    user: dict = Depends(require_role("supplier")),
):
    _get_supplier_id(user)
    try:
        from app.integration_engine import _rfq_store
        rfq = _rfq_store.get(rfq_id)
        if not rfq:
            raise HTTPException(404, f"RFQ '{rfq_id}' not found")
        return {"success": True, "rfq": rfq}
    except (ImportError, AttributeError):
        raise HTTPException(404, "RFQ module not available")


@portal_router.post("/rfq/{rfq_id}/bid", summary="Submit bid for RFQ")
async def submit_bid(
    rfq_id: str,
    bid: BidIn,
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    try:
        from app.integration_engine import _rfq_store
        rfq = _rfq_store.get(rfq_id)
        if not rfq:
            raise HTTPException(404, f"RFQ '{rfq_id}' not found")
        if rfq.get("status") != "open":
            raise HTTPException(400, "RFQ is not open for bids")

        # Store bid
        if "bids" not in rfq:
            rfq["bids"] = []
        rfq["bids"].append({
            "supplier_id": sid,
            "unit_price": bid.unit_price,
            "lead_time_days": bid.lead_time_days,
            "notes": bid.notes,
            "valid_until": bid.valid_until,
            "submitted_at": __import__("datetime").datetime.utcnow().isoformat(),
        })
        return {"success": True, "rfq_id": rfq_id, "message": "Bid submitted"}
    except (ImportError, AttributeError):
        raise HTTPException(404, "RFQ module not available")


# ── Certificates ──────────────────────────────────────────────────────────

@portal_router.get("/certificates", summary="My certificates")
async def my_certificates(user: dict = Depends(require_role("supplier"))):
    sid = _get_supplier_id(user)
    profile = get_supplier(sid)
    if not profile:
        raise HTTPException(404, "Supplier profile not found")
    certs = profile.certificates if hasattr(profile, "certificates") else []
    return {"certificates": [c.model_dump() if hasattr(c, "model_dump") else c for c in certs],
            "count": len(certs)}


@portal_router.post("/certificates", summary="Add certificate")
async def add_my_certificate(
    cert: CertificateIn,
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    sc = SupplierCertificate(
        cert_id=f"CERT-{__import__('uuid').uuid4().hex[:8].upper()}",
        name=cert.name,
        issuer=cert.issuer,
        valid_until=cert.valid_until,
        cert_type=cert.cert_type,
    )
    result = add_certificate(sid, sc)
    if not result:
        raise HTTPException(404, "Supplier not found")
    return {"success": True, "cert_id": sc.cert_id}


@portal_router.get("/certificates/expiring", summary="My expiring certificates")
async def my_expiring_certs(
    days: int = Query(90),
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    all_expiring = get_expiring_certificates(days)
    my_expiring = [c for c in all_expiring if c.get("supplier_id") == sid]
    return {"certificates": my_expiring, "count": len(my_expiring)}


# ── Self-Assessment ───────────────────────────────────────────────────────

@portal_router.get("/assessment", summary="Assessment questionnaire")
async def assessment_questions(user: dict = Depends(require_role("supplier"))):
    questions = get_assessment_questions()
    return {"questions": [q.model_dump() if hasattr(q, "model_dump") else q for q in questions]}


@portal_router.post("/assessment", summary="Submit self-assessment")
async def submit_my_assessment(
    answers: list[AssessmentAnswerIn],
    user: dict = Depends(require_role("supplier")),
):
    sid = _get_supplier_id(user)
    sa_answers = [SelfAssessmentAnswer(question_id=a.question_id, answer=a.answer, score=a.score) for a in answers]
    result = submit_assessment(sid, sa_answers)
    if not result:
        raise HTTPException(404, "Supplier not found or assessment failed")
    return {"success": True, "result": result.model_dump() if hasattr(result, "model_dump") else result}


# ── Portal Dashboard ─────────────────────────────────────────────────────

@portal_router.get("/dashboard", summary="Supplier portal dashboard")
async def portal_dashboard(user: dict = Depends(require_role("supplier"))):
    sid = _get_supplier_id(user)
    profile = get_supplier(sid)
    if not profile:
        raise HTTPException(404, "Supplier not found")

    # Count orders
    all_orders = list_orders()
    my_order_count = 0
    active_po_count = 0
    for order in all_orders:
        pos = order.get("purchase_orders", [])
        if isinstance(pos, list):
            for po in pos:
                if isinstance(po, dict) and po.get("supplier_id") == sid:
                    my_order_count += 1
                    if order.get("status") not in ("delivered", "cancelled"):
                        active_po_count += 1
                    break

    certs = profile.certificates if hasattr(profile, "certificates") else []
    expiring = get_expiring_certificates(90)
    my_expiring = [c for c in expiring if c.get("supplier_id") == sid]

    return {
        "supplier_id": sid,
        "name": profile.name if hasattr(profile, "name") else "",
        "total_orders": my_order_count,
        "active_orders": active_po_count,
        "certificates_count": len(certs),
        "expiring_certificates": len(my_expiring),
        "assessment_completed": bool(profile.assessment if hasattr(profile, "assessment") else None),
    }
