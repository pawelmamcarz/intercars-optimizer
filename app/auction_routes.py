"""
Auction API Routes — Reverse Auction / E-Sourcing

Buyer-facing endpoints for creating and managing reverse auctions.
Supplier-facing bid endpoints are in portal_routes.py.
"""

from fastapi import APIRouter, HTTPException, Query

from app.auction_engine import (
    AuctionCreate, BidSubmit, Auction,
    create_auction, publish_auction, start_auction,
    close_auction, award_auction, cancel_auction,
    list_auctions, get_auction, get_auction_stats,
    get_bid_ranking, submit_bid, seed_demo_auction,
)

auction_router = APIRouter(prefix="/auctions", tags=["Auctions / E-Sourcing"])


# ── Buyer endpoints ──────────────────────────────────────────────

@auction_router.post("/", response_model=dict)
async def api_create_auction(data: AuctionCreate):
    """Utwórz nową aukcję odwróconą."""
    auction = create_auction(data, created_by="buyer")
    return {"success": True, "auction": auction.model_dump()}


@auction_router.get("/", response_model=dict)
async def api_list_auctions(
    domain: str = Query("", description="Filtruj po domenie"),
    status: str = Query("", description="Filtruj po statusie"),
):
    """Lista aukcji (buyer view)."""
    auctions = list_auctions(domain=domain, status=status)
    return {
        "auctions": [a.model_dump() for a in auctions],
        "total": len(auctions),
    }


@auction_router.get("/demo", response_model=dict)
async def api_demo_auction():
    """Utwórz demo aukcję z przykładowymi ofertami."""
    auction = seed_demo_auction()
    stats = get_auction_stats(auction.auction_id)
    return {"auction": auction.model_dump(), "stats": stats}


@auction_router.get("/{auction_id}", response_model=dict)
async def api_get_auction(auction_id: str):
    """Szczegóły aukcji."""
    auction = get_auction(auction_id)
    if not auction:
        raise HTTPException(404, f"Auction {auction_id} not found")
    stats = get_auction_stats(auction_id)
    return {"auction": auction.model_dump(), "stats": stats}


@auction_router.get("/{auction_id}/ranking", response_model=dict)
async def api_get_ranking(auction_id: str, line_id: str = Query("")):
    """Ranking ofert dla aukcji (lub konkretnej pozycji)."""
    auction = get_auction(auction_id)
    if not auction:
        raise HTTPException(404, f"Auction {auction_id} not found")

    if line_id:
        return {"line_id": line_id, "ranking": get_bid_ranking(auction_id, line_id)}

    # Return ranking per line item
    rankings = {}
    for li in auction.line_items:
        rankings[li.line_id] = {
            "product_name": li.product_name,
            "max_price": li.max_unit_price,
            "ranking": get_bid_ranking(auction_id, li.line_id),
        }
    return {"rankings": rankings}


@auction_router.get("/{auction_id}/stats", response_model=dict)
async def api_get_stats(auction_id: str):
    """Statystyki aukcji — dashboard kupca."""
    stats = get_auction_stats(auction_id)
    if not stats:
        raise HTTPException(404, f"Auction {auction_id} not found")
    return stats


# ── Lifecycle ────────────────────────────────────────────────────

@auction_router.post("/{auction_id}/publish", response_model=dict)
async def api_publish(auction_id: str):
    """Opublikuj aukcję — widoczna dla dostawców."""
    try:
        auction = publish_auction(auction_id)
        return {"success": True, "status": auction.status}
    except ValueError as e:
        raise HTTPException(400, str(e))


@auction_router.post("/{auction_id}/start", response_model=dict)
async def api_start(auction_id: str):
    """Rozpocznij aktywną fazę licytacji."""
    try:
        auction = start_auction(auction_id)
        return {"success": True, "status": auction.status, "start_time": auction.start_time}
    except ValueError as e:
        raise HTTPException(400, str(e))


@auction_router.post("/{auction_id}/close", response_model=dict)
async def api_close(auction_id: str):
    """Zamknij aukcję — koniec licytacji."""
    try:
        auction = close_auction(auction_id)
        stats = get_auction_stats(auction_id)
        return {"success": True, "status": auction.status, "stats": stats}
    except ValueError as e:
        raise HTTPException(400, str(e))


@auction_router.post("/{auction_id}/award", response_model=dict)
async def api_award(auction_id: str, supplier_id: str = Query(...)):
    """Przyznaj aukcję wybranemu dostawcy."""
    try:
        auction = award_auction(auction_id, supplier_id)
        return {"success": True, "status": auction.status, "awarded_to": supplier_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@auction_router.post("/{auction_id}/cancel", response_model=dict)
async def api_cancel(auction_id: str):
    """Anuluj aukcję."""
    try:
        auction = cancel_auction(auction_id)
        return {"success": True, "status": auction.status}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Direct bid (for testing / buyer override) ────────────────────

@auction_router.post("/{auction_id}/bid", response_model=dict)
async def api_submit_bid(auction_id: str, supplier_id: str, supplier_name: str, data: BidSubmit):
    """Złóż ofertę (testowy / override kupca)."""
    try:
        bid = submit_bid(auction_id, supplier_id, supplier_name, data)
        return {"success": True, "bid": bid.model_dump()}
    except ValueError as e:
        raise HTTPException(400, str(e))
