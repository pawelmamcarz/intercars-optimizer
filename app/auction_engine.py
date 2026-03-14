"""
Reverse Auction / E-Sourcing Engine — v4.1

Umożliwia tworzenie aukcji odwróconych, w których dostawcy licytują cenowo "w dół".
Kupiec tworzy aukcję na bazie RFQ, dostawcy składają oferty w portalu.
Po zamknięciu aukcji, wynik może być automatycznie przekazany do optymalizatora HiGHS.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ── In-memory store ──────────────────────────────────────────────

_auctions: dict[str, "Auction"] = {}


# ── Models ───────────────────────────────────────────────────────

class AuctionStatus(str, Enum):
    draft = "draft"
    published = "published"
    active = "active"
    closing = "closing"
    closed = "closed"
    awarded = "awarded"
    cancelled = "cancelled"


class AuctionType(str, Enum):
    reverse = "reverse"           # cena w dół
    english_reverse = "english_reverse"  # rundy z obniżką
    sealed_bid = "sealed_bid"     # oferty zamknięte, jedno podejście


class AuctionLineItem(BaseModel):
    line_id: str = ""
    product_name: str
    unspsc_code: str = ""
    quantity: float = 1.0
    unit: str = "szt"
    max_unit_price: float = 0.0  # cena startowa / max
    description: str = ""


class Bid(BaseModel):
    bid_id: str = ""
    auction_id: str = ""
    supplier_id: str
    supplier_name: str = ""
    line_id: str = ""
    unit_price: float
    lead_time_days: int = 14
    notes: str = ""
    submitted_at: str = ""
    is_valid: bool = True


class AuctionRound(BaseModel):
    round_number: int
    started_at: str
    ended_at: str = ""
    min_decrement_pct: float = 2.0  # min obniżka % per runda


class AuctionCreate(BaseModel):
    title: str
    description: str = ""
    auction_type: AuctionType = AuctionType.reverse
    domain: str = "parts"
    line_items: list[AuctionLineItem] = []
    invited_suppliers: list[str] = []  # supplier_ids
    start_time: str = ""  # ISO datetime, empty = now
    end_time: str = ""    # ISO datetime, empty = +48h
    auto_extend_minutes: int = 5  # przedłużenie przy ofercie w ostatnich N min
    min_decrement_pct: float = 2.0  # min obniżka %
    reserve_price: float = 0.0     # cena rezerwowa (opcjonalna)
    currency: str = "PLN"
    max_rounds: int = 1  # 1 = ciągła aukcja, >1 = rundy


class BidSubmit(BaseModel):
    line_id: str = ""
    unit_price: float
    lead_time_days: int = 14
    notes: str = ""


class Auction(BaseModel):
    auction_id: str = ""
    title: str = ""
    description: str = ""
    auction_type: AuctionType = AuctionType.reverse
    status: AuctionStatus = AuctionStatus.draft
    domain: str = "parts"
    created_by: str = ""
    created_at: str = ""
    start_time: str = ""
    end_time: str = ""
    auto_extend_minutes: int = 5
    min_decrement_pct: float = 2.0
    reserve_price: float = 0.0
    currency: str = "PLN"
    max_rounds: int = 1
    current_round: int = 1
    line_items: list[AuctionLineItem] = []
    invited_suppliers: list[str] = []
    bids: list[Bid] = []
    rounds: list[AuctionRound] = []
    awarded_supplier_id: str = ""
    savings_pct: float = 0.0


# ── Engine functions ─────────────────────────────────────────────

def create_auction(data: AuctionCreate, created_by: str = "buyer") -> Auction:
    """Tworzy nową aukcję odwróconą."""
    now = datetime.utcnow()
    auction_id = f"AUC-{uuid.uuid4().hex[:8].upper()}"

    # Assign line IDs
    for i, li in enumerate(data.line_items):
        if not li.line_id:
            li.line_id = f"L{i+1:03d}"

    start = data.start_time or (now + timedelta(hours=1)).isoformat()
    end = data.end_time or (now + timedelta(hours=49)).isoformat()

    auction = Auction(
        auction_id=auction_id,
        title=data.title,
        description=data.description,
        auction_type=data.auction_type,
        status=AuctionStatus.draft,
        domain=data.domain,
        created_by=created_by,
        created_at=now.isoformat(),
        start_time=start,
        end_time=end,
        auto_extend_minutes=data.auto_extend_minutes,
        min_decrement_pct=data.min_decrement_pct,
        reserve_price=data.reserve_price,
        currency=data.currency,
        max_rounds=data.max_rounds,
        line_items=data.line_items,
        invited_suppliers=data.invited_suppliers,
    )
    _auctions[auction_id] = auction
    return auction


def publish_auction(auction_id: str) -> Auction:
    """Publikuje aukcję — dostawcy mogą ją zobaczyć."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    if a.status not in (AuctionStatus.draft,):
        raise ValueError(f"Cannot publish auction in status {a.status}")
    a.status = AuctionStatus.published
    return a


def start_auction(auction_id: str) -> Auction:
    """Rozpoczyna aktywną fazę licytacji."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    if a.status not in (AuctionStatus.published,):
        raise ValueError(f"Cannot start auction in status {a.status}")
    a.status = AuctionStatus.active
    a.start_time = datetime.utcnow().isoformat()
    if a.max_rounds > 1:
        a.rounds.append(AuctionRound(
            round_number=1,
            started_at=a.start_time,
            min_decrement_pct=a.min_decrement_pct,
        ))
    return a


def submit_bid(auction_id: str, supplier_id: str, supplier_name: str, bid_data: BidSubmit) -> Bid:
    """Dostawca składa ofertę w aktywnej aukcji."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    if a.status != AuctionStatus.active:
        raise ValueError(f"Auction is not active (status: {a.status})")

    # Check supplier is invited (or auction is open)
    if a.invited_suppliers and supplier_id not in a.invited_suppliers:
        raise ValueError(f"Supplier {supplier_id} is not invited to this auction")

    # Determine target line
    line_id = bid_data.line_id or (a.line_items[0].line_id if a.line_items else "L001")

    # Validate min decrement
    current_best = get_best_bid(auction_id, line_id)
    if current_best and a.auction_type == AuctionType.reverse:
        max_allowed = current_best.unit_price * (1 - a.min_decrement_pct / 100)
        if bid_data.unit_price > max_allowed:
            raise ValueError(
                f"Bid must be at least {a.min_decrement_pct}% lower than current best "
                f"({current_best.unit_price:.2f}). Max allowed: {max_allowed:.2f}"
            )

    # Validate against max price
    line_item = next((li for li in a.line_items if li.line_id == line_id), None)
    if line_item and line_item.max_unit_price > 0 and bid_data.unit_price > line_item.max_unit_price:
        raise ValueError(f"Bid exceeds maximum price ({line_item.max_unit_price:.2f})")

    now = datetime.utcnow()

    # Auto-extend if bid in last N minutes
    if a.auto_extend_minutes > 0 and a.end_time:
        try:
            end_dt = datetime.fromisoformat(a.end_time)
            remaining = (end_dt - now).total_seconds() / 60
            if 0 < remaining < a.auto_extend_minutes:
                a.end_time = (now + timedelta(minutes=a.auto_extend_minutes)).isoformat()
        except (ValueError, TypeError):
            pass

    bid = Bid(
        bid_id=f"BID-{uuid.uuid4().hex[:8].upper()}",
        auction_id=auction_id,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        line_id=line_id,
        unit_price=bid_data.unit_price,
        lead_time_days=bid_data.lead_time_days,
        notes=bid_data.notes,
        submitted_at=now.isoformat(),
    )
    a.bids.append(bid)
    return bid


def get_best_bid(auction_id: str, line_id: str = "") -> Optional[Bid]:
    """Zwraca najlepszą (najniższą) ofertę dla pozycji."""
    a = _auctions.get(auction_id)
    if not a:
        return None
    valid_bids = [b for b in a.bids if b.is_valid and (not line_id or b.line_id == line_id)]
    if not valid_bids:
        return None
    return min(valid_bids, key=lambda b: b.unit_price)


def get_bid_ranking(auction_id: str, line_id: str = "") -> list[dict]:
    """Zwraca ranking ofert dla pozycji."""
    a = _auctions.get(auction_id)
    if not a:
        return []
    valid_bids = [b for b in a.bids if b.is_valid and (not line_id or b.line_id == line_id)]
    # Group by supplier — keep only latest bid per supplier per line
    latest: dict[str, Bid] = {}
    for b in valid_bids:
        key = f"{b.supplier_id}:{b.line_id}"
        if key not in latest or b.submitted_at > latest[key].submitted_at:
            latest[key] = b
    ranked = sorted(latest.values(), key=lambda b: b.unit_price)
    return [
        {
            "rank": i + 1,
            "supplier_id": b.supplier_id,
            "supplier_name": b.supplier_name,
            "unit_price": b.unit_price,
            "lead_time_days": b.lead_time_days,
            "submitted_at": b.submitted_at,
            "bid_id": b.bid_id,
        }
        for i, b in enumerate(ranked)
    ]


def close_auction(auction_id: str) -> Auction:
    """Zamyka aukcję — koniec licytacji."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    a.status = AuctionStatus.closed

    # Calculate savings
    for li in a.line_items:
        best = get_best_bid(auction_id, li.line_id)
        if best and li.max_unit_price > 0:
            a.savings_pct = round((1 - best.unit_price / li.max_unit_price) * 100, 1)
    return a


def award_auction(auction_id: str, supplier_id: str) -> Auction:
    """Przyznaje aukcję wybranemu dostawcy."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    if a.status not in (AuctionStatus.closed,):
        raise ValueError(f"Auction must be closed before awarding (status: {a.status})")
    a.status = AuctionStatus.awarded
    a.awarded_supplier_id = supplier_id
    return a


def cancel_auction(auction_id: str) -> Auction:
    """Anuluje aukcję."""
    a = _auctions.get(auction_id)
    if not a:
        raise ValueError(f"Auction {auction_id} not found")
    a.status = AuctionStatus.cancelled
    return a


def list_auctions(
    domain: str = "",
    status: str = "",
    supplier_id: str = "",
) -> list[Auction]:
    """Listuje aukcje z opcjonalnym filtrem."""
    result = list(_auctions.values())
    if domain:
        result = [a for a in result if a.domain == domain]
    if status:
        result = [a for a in result if a.status == status]
    if supplier_id:
        result = [a for a in result if supplier_id in a.invited_suppliers or not a.invited_suppliers]
    return sorted(result, key=lambda a: a.created_at, reverse=True)


def get_auction(auction_id: str) -> Optional[Auction]:
    return _auctions.get(auction_id)


def get_auction_stats(auction_id: str) -> dict:
    """Statystyki aukcji — do dashboardu kupca."""
    a = _auctions.get(auction_id)
    if not a:
        return {}

    total_bids = len(a.bids)
    unique_suppliers = len(set(b.supplier_id for b in a.bids))
    best_bids = {}
    for li in a.line_items:
        best = get_best_bid(auction_id, li.line_id)
        if best:
            best_bids[li.line_id] = {
                "line_id": li.line_id,
                "product_name": li.product_name,
                "max_price": li.max_unit_price,
                "best_price": best.unit_price,
                "best_supplier": best.supplier_name,
                "savings_pct": round((1 - best.unit_price / li.max_unit_price) * 100, 1) if li.max_unit_price > 0 else 0,
            }

    total_savings = 0
    total_start = 0
    for li in a.line_items:
        best = get_best_bid(auction_id, li.line_id)
        if best and li.max_unit_price > 0:
            total_start += li.max_unit_price * li.quantity
            total_savings += (li.max_unit_price - best.unit_price) * li.quantity

    return {
        "auction_id": auction_id,
        "status": a.status,
        "total_bids": total_bids,
        "unique_suppliers": unique_suppliers,
        "invited_suppliers": len(a.invited_suppliers),
        "line_items_count": len(a.line_items),
        "best_bids": best_bids,
        "total_start_value": round(total_start, 2),
        "total_best_value": round(total_start - total_savings, 2),
        "total_savings_pln": round(total_savings, 2),
        "total_savings_pct": round(total_savings / total_start * 100, 1) if total_start > 0 else 0,
        "time_remaining": _time_remaining(a),
    }


def _time_remaining(a: Auction) -> str:
    if a.status != AuctionStatus.active or not a.end_time:
        return ""
    try:
        end = datetime.fromisoformat(a.end_time)
        delta = end - datetime.utcnow()
        if delta.total_seconds() <= 0:
            return "Zakończona"
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}min"
    except (ValueError, TypeError):
        return ""


# ── Demo data ────────────────────────────────────────────────────

def seed_demo_auction() -> Auction:
    """Tworzy demo aukcję z przykładowymi ofertami."""
    now = datetime.utcnow()

    data = AuctionCreate(
        title="Aukcja — Klocki hamulcowe Q2/2026",
        description="Aukcja odwrócona na dostawę klocków hamulcowych (25101500) na Q2 2026. "
                    "Planowana ilość: 5000 kpl, dostawy do 3 magazynów w PL.",
        auction_type=AuctionType.reverse,
        domain="parts",
        line_items=[
            AuctionLineItem(
                line_id="L001",
                product_name="Klocki hamulcowe przód — segment C",
                unspsc_code="25101500",
                quantity=3000,
                unit="kpl",
                max_unit_price=195.00,
                description="Homologacja ECE R90, przód, segment C/D",
            ),
            AuctionLineItem(
                line_id="L002",
                product_name="Klocki hamulcowe tył — segment C",
                unspsc_code="25101500",
                quantity=2000,
                unit="kpl",
                max_unit_price=145.00,
                description="Homologacja ECE R90, tył, segment C/D",
            ),
        ],
        invited_suppliers=["TRW-001", "BOSCH-001", "BREMBO-001", "KRAFT-001"],
        start_time=(now - timedelta(hours=6)).isoformat(),
        end_time=(now + timedelta(hours=18)).isoformat(),
        auto_extend_minutes=5,
        min_decrement_pct=1.5,
        currency="PLN",
    )

    auction = create_auction(data, created_by="demo_buyer")
    auction.status = AuctionStatus.active

    # Simulate bids
    demo_bids = [
        # Round 1
        ("TRW-001", "TRW Automotive", "L001", 192.00, 7, -6),
        ("BOSCH-001", "Bosch Aftermarket", "L001", 189.50, 10, -5.5),
        ("BREMBO-001", "Brembo Poland", "L001", 188.00, 8, -5),
        ("KRAFT-001", "KraftPol", "L001", 191.00, 5, -4.5),
        # Round 2
        ("TRW-001", "TRW Automotive", "L001", 185.00, 7, -3),
        ("BOSCH-001", "Bosch Aftermarket", "L001", 183.50, 10, -2),
        ("BREMBO-001", "Brembo Poland", "L001", 182.00, 8, -1.5),
        # Round 3
        ("TRW-001", "TRW Automotive", "L001", 180.00, 7, -0.5),
        # L002
        ("TRW-001", "TRW Automotive", "L002", 142.00, 7, -5),
        ("BOSCH-001", "Bosch Aftermarket", "L002", 139.00, 10, -4),
        ("BREMBO-001", "Brembo Poland", "L002", 137.50, 8, -3),
        ("TRW-001", "TRW Automotive", "L002", 136.00, 7, -1),
    ]

    for sid, sname, lid, price, lt, hours_ago in demo_bids:
        bid = Bid(
            bid_id=f"BID-{uuid.uuid4().hex[:8].upper()}",
            auction_id=auction.auction_id,
            supplier_id=sid,
            supplier_name=sname,
            line_id=lid,
            unit_price=price,
            lead_time_days=lt,
            submitted_at=(now + timedelta(hours=hours_ago)).isoformat(),
        )
        auction.bids.append(bid)

    return auction
