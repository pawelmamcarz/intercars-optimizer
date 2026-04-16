"""
bi_routes.py — BI / ERP / CRM / Finance / WMS integration endpoints.

Thin layer on top of `app.bi_mock`. The routes stay identical when the
adapter later swaps from the mock to a real HTTP client — only the
connector implementations change.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.bi_mock import get_connector, list_connectors

bi_router = APIRouter(tags=["BI / ERP / WMS Integration (simulated)"])


@bi_router.get("/bi/status")
def bi_status():
    """List every registered connector and its health snapshot."""
    return {"success": True, "connectors": list_connectors()}


@bi_router.get("/bi/erp/invoices")
def bi_erp_invoices(
    months: int = Query(3, ge=1, le=24),
    category: str | None = None,
    supplier_id: str | None = None,
):
    erp = get_connector("erp")
    invoices = erp.get_invoices(months=months, category=category, supplier_id=supplier_id)
    total = sum(i["amount_pln"] for i in invoices)
    return {
        "success": True,
        "count": len(invoices),
        "total_pln": round(total, 2),
        "invoices": invoices,
    }


@bi_router.get("/bi/erp/purchase-orders")
def bi_erp_purchase_orders(months: int = Query(3, ge=1, le=24)):
    erp = get_connector("erp")
    return {"success": True, "purchase_orders": erp.get_purchase_orders(months=months)}


@bi_router.get("/bi/erp/budget")
def bi_erp_budget(year: int | None = None):
    erp = get_connector("erp")
    return {"success": True, "budget": erp.get_budget_positions(year=year)}


@bi_router.get("/bi/warehouse/spend-history")
def bi_spend_history(
    months: int = Query(24, ge=1, le=36),
    category: str | None = None,
):
    bi = get_connector("bi")
    return {"success": True, "spend": bi.get_historical_spend(months=months, category=category)}


@bi_router.get("/bi/warehouse/yoy-anomalies")
def bi_yoy_anomalies(threshold_pct: float = Query(20.0, ge=5.0, le=100.0)):
    bi = get_connector("bi")
    return {"success": True, "anomalies": bi.yoy_anomalies(threshold_pct=threshold_pct)}


@bi_router.get("/bi/crm/demand-forecast")
def bi_demand_forecast(horizon_weeks: int = Query(12, ge=1, le=52)):
    crm = get_connector("crm")
    return {"success": True, "forecasts": crm.get_demand_forecast(horizon_weeks=horizon_weeks)}


@bi_router.get("/bi/finance/cash-position")
def bi_cash_position():
    fin = get_connector("finance")
    return {"success": True, "position": fin.get_cash_position()}


@bi_router.get("/bi/finance/overdue")
def bi_overdue():
    fin = get_connector("finance")
    return {"success": True, "overdue": fin.get_overdue_invoices()}


@bi_router.get("/bi/wms/stock")
def bi_wms_stock():
    wms = get_connector("wms")
    return {"success": True, "stock": wms.get_stock_levels()}
