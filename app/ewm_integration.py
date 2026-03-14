"""
EWM (Extended Warehouse Management) integration — placeholder module.

All endpoints return demo/mock data until the client provides the real
EWM API specification.  The module is wired into the main FastAPI app
under ``/api/v1/ewm``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

ewm_router = APIRouter(prefix="/ewm", tags=["EWM Integration"])

_PLACEHOLDER_NOTE = "Awaiting client EWM API specification"


# ── Pydantic models ────────────────────────────────────────────────

class GoodsReceiptItem(BaseModel):
    product_id: str
    qty: int


class GoodsReceiptRequest(BaseModel):
    order_id: str
    items: List[GoodsReceiptItem]


class ReservationRequest(BaseModel):
    order_id: str
    product_id: str
    qty: int
    warehouse: Optional[str] = None


# ── Helper ─────────────────────────────────────────────────────────

def _wrap(data: dict) -> dict:
    """Wrap every response in the standard placeholder envelope."""
    return {
        "success": True,
        "source": "placeholder",
        "note": _PLACEHOLDER_NOTE,
        "data": data,
    }


# ── Endpoints ──────────────────────────────────────────────────────

@ewm_router.get("/status")
async def ewm_status():
    """Return the EWM connection status.

    In the real integration this would ping the EWM health-check
    endpoint and report latency, authentication state, and API version.
    """
    logger.info("EWM status check requested (placeholder)")
    return _wrap({
        "status": "connected",
        "ewm_base_url": settings.ewm_base_url,
        "api_key_configured": bool(settings.ewm_api_key),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


@ewm_router.get("/stock/{product_id}")
async def ewm_stock_single(product_id: str):
    """Return stock levels for a single product.

    The real integration would call the EWM stock enquiry API,
    returning live available quantity, reserved quantity, and
    warehouse location(s).
    """
    logger.info("EWM stock query for product_id=%s (placeholder)", product_id)
    return _wrap({
        "product_id": product_id,
        "available_qty": 150,
        "reserved_qty": 30,
        "warehouse_location": "WH-KRK-A3-07",
    })


@ewm_router.get("/stock")
async def ewm_stock_bulk(
    product_ids: str = Query(
        ...,
        description="Comma-separated list of product IDs",
        examples=["IC-001,IC-002,IC-003"],
    ),
):
    """Return stock levels for multiple products in one call.

    The real integration would batch-query the EWM inventory API and
    return consolidated availability across all requested SKUs.
    """
    ids = [pid.strip() for pid in product_ids.split(",") if pid.strip()]
    logger.info("EWM bulk stock query for %d products (placeholder)", len(ids))
    items = [
        {
            "product_id": pid,
            "available_qty": 150 + i * 10,
            "reserved_qty": 30 + i * 5,
            "warehouse_location": f"WH-KRK-A{i + 1}-07",
        }
        for i, pid in enumerate(ids)
    ]
    return _wrap({"products": items, "total_queried": len(ids)})


@ewm_router.post("/goods-receipt")
async def ewm_goods_receipt(payload: GoodsReceiptRequest):
    """Confirm goods receipt from a delivery.

    The real integration would post the inbound delivery confirmation
    to EWM, updating on-hand inventory and triggering put-away tasks.
    """
    logger.info(
        "EWM goods receipt for order_id=%s with %d line(s) (placeholder)",
        payload.order_id,
        len(payload.items),
    )
    return _wrap({
        "order_id": payload.order_id,
        "receipt_id": f"GR-{payload.order_id}-001",
        "items_received": [
            {"product_id": it.product_id, "qty": it.qty, "status": "received"}
            for it in payload.items
        ],
        "received_at": datetime.now(timezone.utc).isoformat(),
    })


@ewm_router.post("/reservation")
async def ewm_reservation(payload: ReservationRequest):
    """Create a stock reservation for an order.

    The real integration would call the EWM reservation API to lock
    the requested quantity, preventing it from being allocated
    elsewhere until the reservation is consumed or cancelled.
    """
    logger.info(
        "EWM reservation for order_id=%s, product_id=%s, qty=%d (placeholder)",
        payload.order_id,
        payload.product_id,
        payload.qty,
    )
    return _wrap({
        "reservation_id": f"RES-{payload.order_id}-{payload.product_id}",
        "order_id": payload.order_id,
        "product_id": payload.product_id,
        "qty": payload.qty,
        "warehouse": payload.warehouse or "WH-KRK",
        "status": "reserved",
        "reserved_at": datetime.now(timezone.utc).isoformat(),
    })


@ewm_router.get("/warehouses")
async def ewm_warehouses():
    """List available warehouses.

    The real integration would fetch the warehouse master-data from
    EWM, including capacity, address, and operational status.
    """
    logger.info("EWM warehouses list requested (placeholder)")
    warehouses = [
        {"code": "WH-KRK", "name": "Krakow",  "status": "active", "capacity_pct": 72},
        {"code": "WH-WAW", "name": "Warsaw",   "status": "active", "capacity_pct": 58},
        {"code": "WH-GDA", "name": "Gdansk",   "status": "active", "capacity_pct": 41},
    ]
    return _wrap({"warehouses": warehouses})


@ewm_router.get("/movements")
async def ewm_movements():
    """Return recent stock movements.

    The real integration would query the EWM movement log, returning
    goods issues, goods receipts, transfers, and adjustments within
    a configurable time window.
    """
    logger.info("EWM movements list requested (placeholder)")
    now = datetime.now(timezone.utc).isoformat()
    movements = [
        {"movement_id": "MV-001", "type": "goods_receipt",  "product_id": "IC-001", "qty": 200, "warehouse": "WH-KRK", "timestamp": now},
        {"movement_id": "MV-002", "type": "goods_issue",    "product_id": "IC-002", "qty":  50, "warehouse": "WH-WAW", "timestamp": now},
        {"movement_id": "MV-003", "type": "transfer",       "product_id": "IC-003", "qty":  80, "warehouse": "WH-GDA", "timestamp": now},
    ]
    return _wrap({"movements": movements, "total": len(movements)})
