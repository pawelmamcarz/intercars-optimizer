"""
v3.1 — Generic RFQ Integration Engine (vendor-agnostic).

Provides:
- RfqTransformer: convert RFQ bids ↔ optimizer SupplierInput/DemandItem
- In-memory RFQ store (CRUD)
- Demo RFQ generator
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.schemas import (
    AllocationRow,
    DemandItem,
    RfqHeader,
    RfqLineItem,
    RfqSupplierBid,
    RfqExportRow,
    SupplierInput,
)


# ── In-memory RFQ store ──────────────────────────────────────────────

_rfq_store: dict[str, dict] = {}


def store_rfq(rfq: RfqHeader) -> str:
    """Persist an RFQ (or overwrite existing)."""
    _rfq_store[rfq.rfq_id] = {
        "rfq": rfq,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    return rfq.rfq_id


def get_rfq(rfq_id: str) -> Optional[RfqHeader]:
    entry = _rfq_store.get(rfq_id)
    return entry["rfq"] if entry else None


def list_rfqs() -> list[dict]:
    return [
        {
            "rfq_id": k,
            "title": v["rfq"].title,
            "status": v["rfq"].status,
            "domain": v["rfq"].procurement_domain,
            "line_items": len(v["rfq"].line_items),
            "bids": len(v["rfq"].bids),
            "stored_at": v["stored_at"],
        }
        for k, v in _rfq_store.items()
    ]


# ── RFQ ↔ Optimizer conversion ───────────────────────────────────────

class RfqTransformer:
    """Convert between generic RFQ format and optimizer input/output."""

    @staticmethod
    def rfq_to_optimizer_input(
        rfq: RfqHeader,
    ) -> tuple[list[SupplierInput], list[DemandItem]]:
        """
        Convert RFQ bids → SupplierInput list + line items → DemandItem list.

        Groups bids by supplier_id; each line item becomes a demand item.
        """
        # Group bids by supplier
        supplier_bids: dict[str, list[RfqSupplierBid]] = {}
        for bid in rfq.bids:
            supplier_bids.setdefault(bid.supplier_id, []).append(bid)

        suppliers: list[SupplierInput] = []
        for sid, bids in supplier_bids.items():
            base = bids[0]
            suppliers.append(SupplierInput(
                supplier_id=sid,
                name=base.supplier_name,
                unit_cost=base.bid_unit_price,
                logistics_cost=base.bid_logistics_cost,
                lead_time_days=base.lead_time_days,
                compliance_score=base.compliance_score,
                esg_score=base.esg_score,
                min_order_qty=0.0,
                max_capacity=base.capacity,
                served_regions=base.regions_served,
                payment_terms_days=base.payment_terms_days,
                region_code=base.regions_served[0] if base.regions_served else None,
            ))

        demand: list[DemandItem] = []
        for li in rfq.line_items:
            demand.append(DemandItem(
                product_id=li.material_number,
                demand_qty=li.quantity,
                destination_region=li.destination_region,
            ))

        return suppliers, demand

    @staticmethod
    def optimization_to_export(
        rfq_id: str,
        allocations: list[AllocationRow],
        line_items: list[RfqLineItem],
    ) -> list[RfqExportRow]:
        """
        Convert optimization allocations → generic RFQ export rows.

        Only exports allocations with fraction > 0.01.
        """
        item_map = {li.material_number: li for li in line_items}
        rows: list[RfqExportRow] = []

        for alloc in allocations:
            if alloc.allocated_fraction < 0.01:
                continue
            li = item_map.get(alloc.product_id)
            rows.append(RfqExportRow(
                rfq_id=rfq_id,
                line_item_id=li.line_item_id if li else alloc.product_id,
                awarded_supplier_id=alloc.supplier_id,
                awarded_supplier_name=alloc.supplier_name,
                material_number=alloc.product_id,
                awarded_quantity=alloc.allocated_qty,
                unit_price=alloc.unit_cost,
                logistics_cost=alloc.logistics_cost,
                total_line_value_pln=alloc.unit_cost * alloc.allocated_qty,
                lead_time_days=alloc.lead_time_days,
                plant=li.destination_plant if li else "PL01",
                purchase_order_type="STANDARD",
            ))
        return rows


# ── Demo RFQ generator ───────────────────────────────────────────────

def generate_demo_rfq(domain: str = "parts") -> RfqHeader:
    """Generate a realistic demo RFQ for testing integration flow."""
    rfq_id = f"RFQ-DEMO-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)

    line_items = [
        RfqLineItem(
            line_item_id="LI-001",
            material_number="BRK-PAD-001",
            description="Brake Pad Set — front axle",
            quantity=5000,
            unit_of_measure="PC",
            required_delivery_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
            destination_region="PL-MA",
            destination_plant="PL01",
        ),
        RfqLineItem(
            line_item_id="LI-002",
            material_number="BRK-DSC-002",
            description="Brake Disc — ventilated 280mm",
            quantity=3000,
            unit_of_measure="PC",
            required_delivery_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
            destination_region="PL-MA",
            destination_plant="PL01",
        ),
        RfqLineItem(
            line_item_id="LI-003",
            material_number="FLT-OIL-003",
            description="Oil Filter — spin-on",
            quantity=8000,
            unit_of_measure="PC",
            required_delivery_date=(now + timedelta(days=45)).strftime("%Y-%m-%d"),
            destination_region="PL-SL",
            destination_plant="PL02",
        ),
        RfqLineItem(
            line_item_id="LI-004",
            material_number="FLT-AIR-004",
            description="Air Filter — panel",
            quantity=6000,
            unit_of_measure="PC",
            required_delivery_date=(now + timedelta(days=45)).strftime("%Y-%m-%d"),
            destination_region="CZ-PR",
            destination_plant="CZ01",
        ),
        RfqLineItem(
            line_item_id="LI-005",
            material_number="SUS-ARM-005",
            description="Control Arm — front lower",
            quantity=2000,
            unit_of_measure="PC",
            required_delivery_date=(now + timedelta(days=60)).strftime("%Y-%m-%d"),
            destination_region="PL-MA",
            destination_plant="PL01",
        ),
    ]

    bids = [
        RfqSupplierBid(
            supplier_id="TRW-BID", supplier_name="TRW Automotive",
            line_item_id="LI-001",
            bid_unit_price=42.0, bid_logistics_cost=3.5, lead_time_days=5,
            compliance_score=0.95, esg_score=0.88, payment_terms_days=30,
            capacity=15000, regions_served=["PL-MA", "DE-BY"],
        ),
        RfqSupplierBid(
            supplier_id="BOSCH-BID", supplier_name="Robert Bosch GmbH",
            line_item_id="LI-001",
            bid_unit_price=45.0, bid_logistics_cost=4.0, lead_time_days=4,
            compliance_score=0.97, esg_score=0.92, payment_terms_days=45,
            capacity=20000, regions_served=["DE-BY", "CZ-PR"],
        ),
        RfqSupplierBid(
            supplier_id="MANN-BID", supplier_name="MANN+HUMMEL",
            line_item_id="LI-003",
            bid_unit_price=38.0, bid_logistics_cost=3.0, lead_time_days=7,
            compliance_score=0.90, esg_score=0.85, payment_terms_days=30,
            capacity=12000, regions_served=["PL-MA"],
        ),
        RfqSupplierBid(
            supplier_id="SACHS-BID", supplier_name="ZF Sachs",
            line_item_id="LI-005",
            bid_unit_price=50.0, bid_logistics_cost=5.0, lead_time_days=3,
            compliance_score=0.98, esg_score=0.90, payment_terms_days=60,
            capacity=10000, regions_served=["DE-BY", "PL-MA", "CZ-PR"],
        ),
    ]

    return RfqHeader(
        rfq_id=rfq_id,
        title=f"Demo RFQ — {domain.replace('_', ' ').title()} Domain",
        procurement_domain=domain,
        buyer_org="Inter Cars S.A.",
        created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        deadline=(now + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        currency="PLN",
        line_items=line_items,
        bids=bids,
        status="active",
    )
