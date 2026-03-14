"""
Marketplace API routes — Allegro search + PunchOut demo.

GET  /marketplace/allegro/search     → search Allegro offers
GET  /marketplace/allegro/offer/{id} → single offer detail
POST /marketplace/punchout/setup     → create PunchOut session (cXML)
GET  /marketplace/punchout/browse/{session_id} → browse mock catalog
POST /marketplace/punchout/cart/{session_id}   → add to PunchOut cart
POST /marketplace/punchout/return/{session_id} → return cart as cXML
GET  /marketplace/punchout/sessions  → list sessions (debug)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.marketplace_engine import (
    AllegroClient,
    mock_allegro_search,
    punchout_setup,
    punchout_get_session,
    punchout_browse,
    punchout_add_to_cart,
    punchout_return_cart,
    punchout_list_sessions,
)

logger = logging.getLogger(__name__)

marketplace_router = APIRouter(tags=["Marketplace"])


# ── Schemas ─────────────────────────────────────────────────────

class PunchOutCartItem(BaseModel):
    item_id: str
    name: str
    price: float
    qty: int = 1


class PunchOutSetupRequest(BaseModel):
    buyer_cookie: str = ""
    browser_form_post_url: str = ""


# ── Allegro endpoints ──────────────────────────────────────────

@marketplace_router.post("/marketplace/allegro/auth/start")
async def allegro_auth_start():
    """Start Allegro device_code authorization flow."""
    if not AllegroClient.is_configured():
        return {"error": "Allegro API not configured", "configured": False}
    try:
        result = await AllegroClient.start_device_flow()
        return {"status": "pending", **result}
    except Exception as e:
        return {"error": str(e)}


@marketplace_router.post("/marketplace/allegro/auth/poll")
async def allegro_auth_poll():
    """Poll to check if user has authorized the device."""
    try:
        acquired = await AllegroClient.poll_device_token()
        return {"authorized": acquired, "has_token": AllegroClient.has_token()}
    except Exception as e:
        return {"authorized": False, "error": str(e)}


@marketplace_router.get("/marketplace/allegro/status")
async def allegro_status():
    """Check Allegro API configuration and auth status."""
    return {
        "configured": AllegroClient.is_configured(),
        "has_token": AllegroClient.has_token(),
        "pending_auth": bool(AllegroClient._device_code),
        "user_code": AllegroClient._user_code,
        "verification_url": AllegroClient._verification_url,
    }


@marketplace_router.get("/marketplace/allegro/search")
async def allegro_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=60),
):
    """Search Allegro marketplace for products."""
    if not AllegroClient.is_configured():
        # Fallback to mock results
        products = mock_allegro_search(q, limit)
        return {
            "products": products,
            "source": "allegro_mock",
            "query": q,
            "count": len(products),
            "note": "Tryb demo — ustaw FLOW_ALLEGRO_CLIENT_ID aby polaczyc z Allegro API",
        }

    try:
        products = await AllegroClient.search(q, limit)
        return {
            "products": products,
            "source": "allegro",
            "query": q,
            "count": len(products),
        }
    except Exception as e:
        logger.error("Allegro search error: %s", e)
        # Fallback to mock on error
        products = mock_allegro_search(q, limit)
        return {
            "products": products,
            "source": "allegro_mock",
            "query": q,
            "count": len(products),
            "error": str(e),
        }


# ── PunchOut endpoints ─────────────────────────────────────────

@marketplace_router.post("/marketplace/punchout/setup")
async def po_setup(req: PunchOutSetupRequest | None = None):
    """Create a new PunchOut session. Returns cXML SetupResponse."""
    buyer_cookie = req.buyer_cookie if req else ""
    post_url = req.browser_form_post_url if req else ""

    session_id, cxml = punchout_setup(buyer_cookie, post_url)

    return {
        "session_id": session_id,
        "status": "active",
        "cxml_response": cxml,
        "browse_url": f"/api/v1/marketplace/punchout/browse/{session_id}",
    }


@marketplace_router.get("/marketplace/punchout/browse/{session_id}")
async def po_browse(session_id: str):
    """Browse mock catalog for a PunchOut session."""
    session = punchout_get_session(session_id)
    if not session:
        return {"error": "Session not found", "session_id": session_id}

    products = punchout_browse(session_id)
    return {
        "session_id": session_id,
        "status": session.status,
        "products": products,
        "cart_items": len(session.cart_items),
        "count": len(products),
    }


@marketplace_router.post("/marketplace/punchout/cart/{session_id}")
async def po_add_to_cart(session_id: str, item: PunchOutCartItem):
    """Add item to PunchOut session cart."""
    ok = punchout_add_to_cart(session_id, item.item_id, item.name, item.price, item.qty)
    if not ok:
        return {"error": "Session not found or inactive", "session_id": session_id}

    session = punchout_get_session(session_id)
    return {
        "session_id": session_id,
        "added": item.item_id,
        "cart_items": len(session.cart_items) if session else 0,
        "cart_total": sum(ci["price"] * ci["qty"] for ci in session.cart_items) if session else 0,
    }


@marketplace_router.post("/marketplace/punchout/return/{session_id}")
async def po_return(session_id: str):
    """Finalize PunchOut session and return cart as cXML PunchOutOrderMessage."""
    cart_items, cxml = punchout_return_cart(session_id)
    if not cxml:
        return {"error": "Session not found", "session_id": session_id}

    return {
        "session_id": session_id,
        "status": "completed",
        "cart_items": cart_items,
        "cart_total": sum(ci["price"] * ci["qty"] for ci in cart_items),
        "cxml_order_message": cxml,
    }


@marketplace_router.get("/marketplace/punchout/sessions")
async def po_sessions():
    """List all PunchOut sessions (admin/debug)."""
    return {"sessions": punchout_list_sessions()}
