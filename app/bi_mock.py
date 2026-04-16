"""
bi_mock.py — Simulated external BI / ERP / WMS / CRM / Finance systems.

Stands in for the real INTERCARS integrations (SAP ERP, SAP EWM, BI
warehouse, Salesforce/CRM, finance ledger) until we get API keys. Every
adapter returns data that *looks* like it came from a production system —
enough to drive recommendations, spend analytics and risk rules.

Design rules:
1. Deterministic per (category, supplier, month) — re-running the same
   request returns the same numbers so tests and the dashboard stay
   stable between renders.
2. Thin `BIConnector` base class that each adapter subclasses. Real
   adapters later slot in by subclassing the same interface.
3. No external network calls — we synthesise data locally from a seeded
   RNG so the platform keeps working offline and on Railway.

The adapters are intentionally small — this is stage-set data, not a
full BI warehouse. When real connectors arrive, swap the
`_generate_*` functions for `httpx.get(...)` and keep the route layer
unchanged.
"""
from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

log = logging.getLogger(__name__)


def _seeded_rng(*parts: Any) -> random.Random:
    """Return a Random instance seeded by a stable hash of the inputs.

    Same (parts) → same sequence. Used everywhere so repeated calls to the
    same endpoint in the same day return identical numbers. The
    month-level granularity means data subtly evolves as time passes but
    is stable within a day.
    """
    key = "|".join(str(p) for p in parts).encode()
    seed = int(hashlib.sha256(key).hexdigest()[:8], 16)
    return random.Random(seed)


# ─── Connector protocol ──────────────────────────────────────────────


class BIConnector(Protocol):
    """What every adapter (mock or real) must implement."""

    name: str

    def health(self) -> dict: ...


@dataclass
class AdapterStatus:
    name: str
    status: str           # "ok" | "degraded" | "mock"
    latency_ms: float
    source: str           # "mock" | "sap_erp" | etc
    last_sync: str
    records_available: int = 0
    note: str = ""


# ─── ERP mock (invoices + purchase orders + budget lines) ────────────


@dataclass
class ErpConnector:
    name: str = "SAP ERP (mock)"

    def health(self) -> dict:
        return AdapterStatus(
            name=self.name, status="mock", latency_ms=42.0,
            source="mock", last_sync=datetime.now(timezone.utc).isoformat(),
            records_available=_count_invoices(months=6),
            note="Simulated. Swap for real SAP adapter when credentials available.",
        ).__dict__

    def get_invoices(self, *, months: int = 3, category: str | None = None,
                     supplier_id: str | None = None) -> list[dict]:
        return _generate_invoices(months=months, category=category, supplier_id=supplier_id)

    def get_purchase_orders(self, *, months: int = 3) -> list[dict]:
        return _generate_purchase_orders(months=months)

    def get_budget_positions(self, year: int | None = None) -> list[dict]:
        return _generate_budget(year or date.today().year)


# ─── BI warehouse mock (historical spend, YoY trends) ────────────────


@dataclass
class BiWarehouseConnector:
    name: str = "Enterprise BI (mock)"

    def health(self) -> dict:
        return AdapterStatus(
            name=self.name, status="mock", latency_ms=120.0,
            source="mock", last_sync=datetime.now(timezone.utc).isoformat(),
            records_available=len(_CATEGORIES) * 24,
            note="24 months of synthesized spend per category.",
        ).__dict__

    def get_historical_spend(self, *, months: int = 24,
                             category: str | None = None) -> list[dict]:
        return _generate_historical_spend(months=months, category=category)

    def yoy_anomalies(self, *, threshold_pct: float = 20.0) -> list[dict]:
        """Return categories whose last-quarter spend is >threshold_pct above
        the same quarter last year."""
        history = _generate_historical_spend(months=24)
        # Aggregate per (category, quarter) to compare YoY
        grouped: dict[tuple[str, str], float] = {}
        for row in history:
            key = (row["category"], row["quarter"])
            grouped[key] = grouped.get(key, 0) + row["spend_pln"]
        anomalies = []
        quarters = sorted({q for _, q in grouped.keys()})
        if len(quarters) < 5:
            return anomalies
        latest = quarters[-1]
        year_ago = quarters[-5]  # same quarter one year back
        cats = {c for c, _ in grouped.keys()}
        for cat in cats:
            current = grouped.get((cat, latest), 0)
            previous = grouped.get((cat, year_ago), 0)
            if previous <= 1000:
                continue
            delta_pct = (current - previous) / previous * 100
            if abs(delta_pct) >= threshold_pct:
                anomalies.append({
                    "category": cat,
                    "current_quarter": latest,
                    "reference_quarter": year_ago,
                    "current_spend": round(current, 2),
                    "reference_spend": round(previous, 2),
                    "delta_pct": round(delta_pct, 1),
                    "direction": "up" if delta_pct > 0 else "down",
                })
        anomalies.sort(key=lambda a: abs(a["delta_pct"]), reverse=True)
        return anomalies


# ─── CRM mock (demand forecast) ──────────────────────────────────────


@dataclass
class CrmConnector:
    name: str = "Salesforce CRM (mock)"

    def health(self) -> dict:
        return AdapterStatus(
            name=self.name, status="mock", latency_ms=88.0,
            source="mock", last_sync=datetime.now(timezone.utc).isoformat(),
            records_available=len(_CATEGORIES),
            note="Quarterly demand forecast per product category.",
        ).__dict__

    def get_demand_forecast(self, *, horizon_weeks: int = 12) -> list[dict]:
        return _generate_demand_forecast(horizon_weeks=horizon_weeks)


# ─── Finance mock (cash flow, payment terms) ─────────────────────────


@dataclass
class FinanceConnector:
    name: str = "Finance Ledger (mock)"

    def health(self) -> dict:
        return AdapterStatus(
            name=self.name, status="mock", latency_ms=55.0,
            source="mock", last_sync=datetime.now(timezone.utc).isoformat(),
            records_available=_count_invoices(months=3),
            note="Cash position + outstanding AP/AR.",
        ).__dict__

    def get_cash_position(self) -> dict:
        rng = _seeded_rng("cashflow", date.today().strftime("%Y-%m"))
        cash = 4_500_000 + rng.randint(-800_000, 1_200_000)
        ap = 1_800_000 + rng.randint(-400_000, 600_000)   # accounts payable
        ar = 2_900_000 + rng.randint(-500_000, 700_000)   # accounts receivable
        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "cash_balance_pln": cash,
            "accounts_payable_pln": ap,
            "accounts_receivable_pln": ar,
            "net_working_capital_pln": cash + ar - ap,
            "days_payable_outstanding": rng.randint(38, 52),
            "days_sales_outstanding": rng.randint(55, 72),
        }

    def get_overdue_invoices(self) -> list[dict]:
        # Return 3–5 invoices "overdue" (synthesized)
        rng = _seeded_rng("overdue", date.today().strftime("%Y-%m-%d"))
        invoices = _generate_invoices(months=3)
        candidates = rng.sample(invoices, k=min(5, len(invoices)))
        out = []
        for inv in candidates:
            out.append({
                **inv,
                "days_overdue": rng.randint(3, 45),
                "risk": "high" if rng.random() < 0.3 else "medium",
            })
        return out


# ─── WMS connector (replaces the old placeholder) ────────────────────


@dataclass
class WmsConnector:
    name: str = "SAP EWM (mock)"

    def health(self) -> dict:
        return AdapterStatus(
            name=self.name, status="mock", latency_ms=60.0,
            source="mock", last_sync=datetime.now(timezone.utc).isoformat(),
            records_available=60,
            note="Stock levels + movements generated per run.",
        ).__dict__

    def get_stock_levels(self) -> list[dict]:
        rng = _seeded_rng("wms-stock", date.today().isoformat())
        warehouses = ["WH-KRK", "WH-WAW", "WH-GDA"]
        out = []
        for cat in _CATEGORIES:
            for wh in warehouses:
                avail = rng.randint(50, 2_000)
                reserved = rng.randint(0, int(avail * 0.4))
                out.append({
                    "category": cat,
                    "warehouse": wh,
                    "available": avail,
                    "reserved": reserved,
                    "below_reorder_point": avail - reserved < 200,
                })
        return out


# ─── Category/supplier seed data ─────────────────────────────────────


_CATEGORIES = [
    "parts", "oe_components", "oils", "batteries", "tires", "bodywork",
    "it_services", "logistics", "packaging", "facility_management",
]

_SUPPLIERS_PER_CAT = {
    "parts": ["SUP-TRW", "SUP-BOSCH", "SUP-BREMBO", "SUP-DELPHI"],
    "oe_components": ["SUP-CONTINENTAL", "SUP-DENSO", "SUP-VALEO"],
    "oils": ["SUP-CASTROL", "SUP-SHELL", "SUP-MOBIL"],
    "batteries": ["SUP-VARTA", "SUP-EXIDE", "SUP-MOLL"],
    "tires": ["SUP-MICHELIN", "SUP-CONTINENTAL", "SUP-DEBICA"],
    "bodywork": ["SUP-AUTOFIT", "SUP-KLOKKERHOLM"],
    "it_services": ["SUP-ACCENTURE", "SUP-CAPGEMINI", "SUP-DELOITTE"],
    "logistics": ["SUP-RABEN", "SUP-KUEHNE", "SUP-DHL"],
    "packaging": ["SUP-MONDI", "SUP-STORA"],
    "facility_management": ["SUP-ISS", "SUP-SODEXO"],
}


# ─── Generators ──────────────────────────────────────────────────────


def _iter_months(back: int) -> list[tuple[int, int]]:
    """Return (year, month) tuples for the last `back` months, oldest first."""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(back):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def _quarter(year: int, month: int) -> str:
    return f"{year}-Q{(month - 1) // 3 + 1}"


def _generate_historical_spend(*, months: int = 24,
                               category: str | None = None) -> list[dict]:
    out = []
    cats = [category] if category else _CATEGORIES
    for cat in cats:
        for y, m in _iter_months(months):
            rng = _seeded_rng("spend", cat, y, m)
            # Base budget depends on category — direct is bigger
            base = 450_000 if cat in {"parts", "oe_components", "tires",
                                      "oils", "batteries", "bodywork"} else 120_000
            # Long-term growth trend
            trend = 1 + (y - 2024) * 0.06 + m * 0.004
            seasonal = 1 + 0.15 * ((m % 6) / 6 - 0.5)  # mild seasonality
            noise = rng.uniform(0.75, 1.25)
            spend = base * trend * seasonal * noise
            out.append({
                "category": cat,
                "year": y,
                "month": m,
                "quarter": _quarter(y, m),
                "spend_pln": round(spend, 2),
                "order_count": rng.randint(3, 35),
            })
    return out


def _generate_invoices(*, months: int = 3, category: str | None = None,
                       supplier_id: str | None = None) -> list[dict]:
    out = []
    for y, m in _iter_months(months):
        rng = _seeded_rng("invoices", y, m)
        cats = [category] if category else _CATEGORIES
        for cat in cats:
            if supplier_id:
                suppliers = [supplier_id]
            else:
                suppliers = _SUPPLIERS_PER_CAT.get(cat, ["SUP-UNKNOWN"])
            for sid in suppliers:
                n_invoices = rng.randint(1, 4)
                for i in range(n_invoices):
                    amount = round(rng.uniform(8_000, 95_000), 2)
                    day = rng.randint(1, 27)
                    out.append({
                        "invoice_id": f"INV-{y}{m:02d}-{sid[-4:]}-{i + 1:02d}",
                        "supplier_id": sid,
                        "category": cat,
                        "issued_at": f"{y}-{m:02d}-{day:02d}",
                        "amount_pln": amount,
                        "payment_terms_days": rng.choice([14, 30, 45, 60]),
                        "status": rng.choice(["paid", "paid", "paid", "pending"]),
                    })
    return out


def _count_invoices(*, months: int = 6) -> int:
    # Rough estimate without full generation — each (month × category) yields
    # ~len(suppliers) * 2 invoices on average.
    total_sups = sum(len(s) for s in _SUPPLIERS_PER_CAT.values())
    return months * total_sups * 2


def _generate_purchase_orders(*, months: int = 3) -> list[dict]:
    out = []
    for y, m in _iter_months(months):
        rng = _seeded_rng("po", y, m)
        for cat in _CATEGORIES:
            for sid in _SUPPLIERS_PER_CAT.get(cat, []):
                for i in range(rng.randint(0, 3)):
                    amount = round(rng.uniform(5_000, 75_000), 2)
                    out.append({
                        "po_id": f"PO-{y}{m:02d}-{sid[-4:]}-{i + 1:02d}",
                        "supplier_id": sid,
                        "category": cat,
                        "issued_at": f"{y}-{m:02d}-{rng.randint(1, 27):02d}",
                        "amount_pln": amount,
                        "status": rng.choice(["confirmed", "shipped", "delivered"]),
                    })
    return out


def _generate_budget(year: int) -> list[dict]:
    out = []
    for cat in _CATEGORIES:
        rng = _seeded_rng("budget", cat, year)
        allocated = rng.randint(800_000, 6_500_000)
        used = int(allocated * rng.uniform(0.3, 1.15))  # some overrun
        out.append({
            "year": year,
            "category": cat,
            "allocated_pln": allocated,
            "used_pln": used,
            "available_pln": max(0, allocated - used),
            "overrun": used > allocated,
            "utilization_pct": round(used / allocated * 100, 1),
        })
    return out


def _generate_demand_forecast(*, horizon_weeks: int = 12) -> list[dict]:
    out = []
    today = date.today()
    for cat in _CATEGORIES:
        rng = _seeded_rng("forecast", cat)
        base = rng.randint(800, 5_000)
        weekly = []
        for w in range(horizon_weeks):
            trend = 1 + w * 0.01
            noise = rng.uniform(0.85, 1.15)
            weekly.append({
                "week_of": (today + timedelta(weeks=w)).isoformat(),
                "forecast_qty": int(base * trend * noise),
            })
        out.append({
            "category": cat,
            "horizon_weeks": horizon_weeks,
            "weekly_forecast": weekly,
            "confidence": round(rng.uniform(0.72, 0.93), 2),
        })
    return out


# ─── Registry ────────────────────────────────────────────────────────


_CONNECTORS: dict[str, BIConnector] = {
    "erp": ErpConnector(),
    "bi": BiWarehouseConnector(),
    "crm": CrmConnector(),
    "finance": FinanceConnector(),
    "wms": WmsConnector(),
}


def get_connector(name: str) -> BIConnector | None:
    return _CONNECTORS.get(name)


def list_connectors() -> list[dict]:
    return [c.health() for c in _CONNECTORS.values()]
