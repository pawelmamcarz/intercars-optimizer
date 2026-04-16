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


def _dict_to_contract(d: dict) -> Contract:
    def _parse_date(v) -> date:
        if isinstance(v, date):
            return v
        return date.fromisoformat(str(v)[:10])

    return Contract(
        id=d["id"],
        supplier_id=d["supplier_id"],
        supplier_name=d["supplier_name"],
        category=d["category"],
        start_date=_parse_date(d["start_date"]),
        end_date=_parse_date(d["end_date"]),
        committed_volume_pln=float(d.get("committed_volume_pln") or 0),
        price_lock=bool(d.get("price_lock")),
        status=d.get("status") or "active",
        notes=d.get("notes") or "",
    )


def _contract_to_dict_for_db(c: Contract) -> dict:
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
    }


def _try_db():
    """Return (client, ok) if Turso is available and the contracts table
    has been initialised; else (None, False)."""
    try:
        from app.database import DB_AVAILABLE, _get_client
        if not DB_AVAILABLE:
            return None, False
        return _get_client(), True
    except Exception as exc:
        log.debug("contract_engine: DB unavailable, falling back to memory: %s", exc)
        return None, False


def _ensure_seeded(client) -> None:
    """Make sure the DB has at least the demo seed — idempotent."""
    from app.database import db_count_contracts, db_upsert_contract
    try:
        if db_count_contracts(client) > 0:
            return
        for c in _demo_contracts():
            db_upsert_contract(client, _contract_to_dict_for_db(c))
        log.info("contract_engine: seeded demo contracts into DB")
    except Exception as exc:
        log.warning("contract_engine: seeding failed, staying in-memory: %s", exc)


def list_contracts() -> list[Contract]:
    client, ok = _try_db()
    if ok:
        try:
            from app.database import db_list_contracts
            _ensure_seeded(client)
            rows = db_list_contracts(client)
            return [_dict_to_contract(r) for r in rows]
        except Exception as exc:
            log.warning("list_contracts DB read failed, falling back: %s", exc)
    return list(_get_cache())


def get_contract(contract_id: str) -> Optional[Contract]:
    client, ok = _try_db()
    if ok:
        try:
            from app.database import db_get_contract
            row = db_get_contract(client, contract_id)
            if row:
                return _dict_to_contract(row)
        except Exception as exc:
            log.warning("get_contract DB read failed, falling back: %s", exc)
    for c in _get_cache():
        if c.id == contract_id:
            return c
    return None


def _audit(client, contract_id: str, action: str, actor: str, diff: dict) -> None:
    """Best-effort audit append — swallow errors so audit never blocks
    the write path itself."""
    try:
        import json
        from app.database import db_append_contract_audit
        db_append_contract_audit(
            client, contract_id, action, actor=actor,
            diff=json.dumps(diff, ensure_ascii=False, default=str),
        )
    except Exception as exc:
        log.warning("contract audit append failed: %s", exc)


def upsert_contract(contract_dict: dict, actor: str = "system") -> Contract:
    """Insert or update a contract. Persists to Turso when available, else
    mutates the in-memory cache. Writes an audit entry on success."""
    c = _dict_to_contract(contract_dict)
    client, ok = _try_db()
    if ok:
        try:
            from app.database import db_get_contract, db_upsert_contract
            before = db_get_contract(client, c.id)
            action = "update" if before else "create"
            db_upsert_contract(client, _contract_to_dict_for_db(c))
            diff = _build_diff(before, _contract_to_dict_for_db(c)) if before else {"after": _contract_to_dict_for_db(c)}
            _audit(client, c.id, action, actor, diff)
            return c
        except Exception as exc:
            log.warning("upsert_contract DB write failed: %s", exc)
    cache = _get_cache()
    for i, existing in enumerate(cache):
        if existing.id == c.id:
            cache[i] = c
            return c
    cache.append(c)
    return c


def delete_contract(contract_id: str, actor: str = "system") -> bool:
    client, ok = _try_db()
    if ok:
        try:
            from app.database import db_delete_contract, db_get_contract
            before = db_get_contract(client, contract_id)
            affected = db_delete_contract(client, contract_id)
            if affected:
                _audit(client, contract_id, "delete", actor, {"before": before})
                return True
        except Exception as exc:
            log.warning("delete_contract DB failed: %s", exc)
    cache = _get_cache()
    for i, c in enumerate(cache):
        if c.id == contract_id:
            cache.pop(i)
            return True
    return False


def get_contract_audit(contract_id: str) -> list[dict]:
    client, ok = _try_db()
    if not ok:
        return []
    try:
        from app.database import db_get_contract_audit
        return db_get_contract_audit(client, contract_id)
    except Exception as exc:
        log.warning("get_contract_audit failed: %s", exc)
        return []


def _build_diff(before: dict, after: dict) -> dict:
    """Produce {field: {"from": ..., "to": ...}} for every changed column.
    Anything identical is skipped — the audit log stays tight."""
    diff: dict = {}
    keys = set(before.keys()) | set(after.keys())
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diff[k] = {"from": b, "to": a}
    return diff


def expiring_within(days: int) -> list[Contract]:
    """Contracts with end_date within `days` from today and still active.
    Returns earliest expiry first. Reads through `list_contracts` so the
    Turso source is used transparently when available."""
    today = date.today()
    out = [c for c in list_contracts()
           if c.is_active(today) and 0 <= c.days_to_expiry(today) <= days]
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
