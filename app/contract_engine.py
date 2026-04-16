"""
contract_engine.py — MVP-4

In-memory demo contracts. A proper follow-up sprint will move these to the
Turso `contracts` table with CRUD + audit log; for MVP-4 the stubs only need
to feed RecommendationEngine so the dashboard shows real dates-relative
expiry cards instead of hardcoded strings.

Schema intentionally small: the downstream `RecommendationEngine` only
cares about supplier + end_date + committed_volume.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Contract:
    id: str
    supplier_id: str
    supplier_name: str
    category: str                 # UNSPSC domain (parts, it_services, ...)
    start_date: date
    end_date: date
    committed_volume_pln: float   # annual commitment
    price_lock: bool = False
    status: str = "active"        # active | expired | terminated
    notes: str = ""

    def days_to_expiry(self, today: Optional[date] = None) -> int:
        t = today or date.today()
        return (self.end_date - t).days

    def is_active(self, today: Optional[date] = None) -> bool:
        t = today or date.today()
        return self.start_date <= t <= self.end_date and self.status == "active"


def _demo_contracts() -> list[Contract]:
    """Seed set — spread end_dates across near/medium/far so the
    RecommendationEngine has something interesting to surface for each
    urgency bucket (30/60/90 day thresholds)."""
    today = date.today()
    return [
        Contract(
            id="CNT-BOSCH-001",
            supplier_id="SUP-BOSCH",
            supplier_name="Bosch Aftermarket (DE)",
            category="parts",
            start_date=today - timedelta(days=350),
            end_date=today + timedelta(days=14),
            committed_volume_pln=1_800_000,
            price_lock=True,
            notes="Roczny kontrakt na czesci hamulcowe; committed volume 60%.",
        ),
        Contract(
            id="CNT-TRW-002",
            supplier_id="SUP-TRW",
            supplier_name="TRW Automotive (DE)",
            category="parts",
            start_date=today - timedelta(days=180),
            end_date=today + timedelta(days=45),
            committed_volume_pln=950_000,
            price_lock=False,
            notes="Konkurencyjny kontrakt rowolegly, mozliwa renegocjacja.",
        ),
        Contract(
            id="CNT-RABEN-003",
            supplier_id="SUP-RABEN",
            supplier_name="Raben Logistics Polska",
            category="logistics",
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=300),
            committed_volume_pln=420_000,
            price_lock=False,
            notes="Umowa ramowa na transport PL-DE-PL.",
        ),
        Contract(
            id="CNT-ACCENTURE-004",
            supplier_id="SUP-ACCENTURE",
            supplier_name="Accenture Polska",
            category="it_services",
            start_date=today - timedelta(days=300),
            end_date=today + timedelta(days=85),
            committed_volume_pln=1_200_000,
            price_lock=True,
            notes="Outsourcing IT, 2-letni. Wygasa w 85 dni — decyzja Q2.",
        ),
        Contract(
            id="CNT-CASTROL-005",
            supplier_id="SUP-CASTROL",
            supplier_name="Castrol Poland",
            category="oils",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=335),
            committed_volume_pln=680_000,
            price_lock=True,
            notes="Swiezo zawarty, 12 miesiecy; bez akcji wymaganej.",
        ),
    ]


# Process-wide cache. First call materialises the list.
_CONTRACTS: list[Contract] = []


def _get_cache() -> list[Contract]:
    global _CONTRACTS
    if not _CONTRACTS:
        _CONTRACTS = _demo_contracts()
    return _CONTRACTS


def list_contracts() -> list[Contract]:
    return list(_get_cache())


def get_contract(contract_id: str) -> Optional[Contract]:
    for c in _get_cache():
        if c.id == contract_id:
            return c
    return None


def expiring_within(days: int) -> list[Contract]:
    """Contracts with end_date within `days` from today and still active.
    Returns earliest expiry first."""
    today = date.today()
    out = [c for c in _get_cache() if c.is_active(today) and 0 <= c.days_to_expiry(today) <= days]
    return sorted(out, key=lambda c: c.days_to_expiry(today))


def reset_cache() -> None:
    """Test hook — force re-seed so tests controlling dates work."""
    global _CONTRACTS
    _CONTRACTS = []


def contract_to_dict(c: Contract) -> dict:
    today = date.today()
    return {
        "id": c.id,
        "supplier_id": c.supplier_id,
        "supplier_name": c.supplier_name,
        "category": c.category,
        "start_date": c.start_date.isoformat(),
        "end_date": c.end_date.isoformat(),
        "committed_volume_pln": c.committed_volume_pln,
        "price_lock": c.price_lock,
        "status": c.status,
        "notes": c.notes,
        "days_to_expiry": c.days_to_expiry(today),
        "is_active": c.is_active(today),
    }
