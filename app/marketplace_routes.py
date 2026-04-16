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

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
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
    from app.config import settings as _s
    return {
        "configured": AllegroClient.is_configured(),
        "has_token": AllegroClient.has_token(),
        "client_id": _s.allegro_client_id if AllegroClient.is_configured() else None,
        "pending_auth": bool(AllegroClient._device_code),
        "user_code": AllegroClient._user_code,
        "verification_url": AllegroClient._verification_url,
    }


@marketplace_router.get("/marketplace/allegro/callback")
async def allegro_callback(request: Request, code: str = Query(None)):
    """OAuth2 callback — exchange authorization code for token."""
    if not code:
        return HTMLResponse("<h2>Brak kodu autoryzacji</h2><p>Sprobuj ponownie.</p>")
    try:
        import httpx as _httpx
        from app.config import settings as _s
        # Build redirect_uri dynamically from the actual request URL
        redirect_uri = str(request.url).split("?")[0]
        logger.info("Allegro callback: redirect_uri=%s", redirect_uri)
        async with _httpx.AsyncClient() as client:
            resp = await client.post(
                _s.allegro_auth_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(_s.allegro_client_id, _s.allegro_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            logger.info("Allegro token exchange: status=%s body=%s", resp.status_code, resp.text[:300])
            if resp.status_code == 200:
                data = resp.json()
                AllegroClient._token = data["access_token"]
                import time
                AllegroClient._token_expires = time.time() + data.get("expires_in", 43200)
                return HTMLResponse(
                    "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                    "<h1 style='color:#22c55e'>&#10003; Allegro API polaczone!</h1>"
                    "<p>Mozesz zamknac to okno i wrocic do aplikacji.</p>"
                    "<script>setTimeout(()=>window.close(),3000)</script>"
                    "</body></html>"
                )
            return HTMLResponse(
                f"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                f"<h1 style='color:#ef4444'>Blad autoryzacji</h1>"
                f"<p>Status: {resp.status_code}</p>"
                f"<pre>{resp.text[:500]}</pre>"
                f"<p><a href='/ui'>Wroc do aplikacji</a></p>"
                f"</body></html>",
                status_code=400,
            )
    except Exception as e:
        logger.exception("Allegro callback error")
        return HTMLResponse(f"<h2>Blad: {e}</h2><p><a href='/ui'>Wroc do aplikacji</a></p>", status_code=500)


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
async def po_browse(session_id: str, category: str = Query("", description="Filter by category")):
    """Browse PunchOut catalog (Allegro + enterprise items)."""
    session = punchout_get_session(session_id)
    if not session:
        return {"error": "Session not found", "session_id": session_id}

    products = punchout_browse(session_id, category=category)
    return {
        "session_id": session_id,
        "status": session.status,
        "products": products,
        "cart_items": len(session.cart_items),
        "count": len(products),
        "source": "allegro_punchout",
        "category_filter": category or "all",
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
