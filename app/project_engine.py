"""
Purchase Project Engine — Projekt Zakupowy

A purchase project groups the entire procurement flow:
  Zapotrzebowanie → Budżet → Dostawcy → Optymalizacja → Zamówienie → Monitoring

Each project belongs to a user (requester) and has a lifecycle:
  draft → submitted → budget_check → approved → ordering → ordered → in_delivery → delivered → closed

For non-professional users (requesters), the flow is simplified:
  draft → submitted → approved → ordered → delivered
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from pydantic import BaseModel

log = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────────────


class ProjectItem(BaseModel):
    """Single line item within a purchase project."""

    id: str
    name: str
    quantity: int = 1
    unit: str = "szt"
    price: float = 0.0
    category: str = ""
    unspsc: str = ""
    supplier_id: str = ""
    supplier_name: str = ""


class ProjectEvent(BaseModel):
    """Immutable audit-trail entry for a project."""

    timestamp: str
    action: str  # created, submitted, budget_approved, approved, ordered, delivered, cancelled, comment
    actor: str  # email of who did it
    note: str = ""


class Project(BaseModel):
    """Full purchase-project aggregate root."""

    project_id: str
    title: str = ""
    description: str = ""
    status: str = "draft"
    status_label: str = "Szkic"

    # Ownership
    requester: str = ""  # email of person who created it
    requester_name: str = ""
    department: str = ""
    mpk: str = ""  # cost center (Miejsce Powstawania Kosztów)
    gl_account: str = ""
    budget_limit: float = 0.0  # max budget for this project

    # Items
    items: list[ProjectItem] = []

    # Totals
    subtotal: float = 0.0
    estimated_savings: float = 0.0
    final_total: float = 0.0

    # Category context
    domain: str = "parts"
    unspsc_code: str = ""
    unspsc_label: str = ""

    # Linked entities
    order_ids: list[str] = []  # linked orders from buying_engine

    # Approval
    requires_approval: bool = True
    approval_chain: list[str] = []  # emails of approvers
    approved_by: list[str] = []

    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    submitted_at: str = ""
    approved_at: str = ""
    ordered_at: str = ""
    delivered_at: str = ""

    # History / audit trail
    history: list[ProjectEvent] = []

    # User type
    is_professional: bool = True  # professional buyer vs simple requester


# ── Status labels (Polish) ────────────────────────────────────────────────────

STATUS_LABELS: dict[str, str] = {
    "draft": "Szkic",
    "submitted": "Złożone",
    "budget_check": "Weryfikacja budżetu",
    "approved": "Zatwierdzone",
    "ordering": "W trakcie zamawiania",
    "ordered": "Zamówione",
    "in_delivery": "W dostawie",
    "delivered": "Dostarczone",
    "closed": "Zamknięte",
    "cancelled": "Anulowane",
}

# Valid transitions per status
TRANSITIONS: dict[str, list[str]] = {
    "draft": ["submitted", "cancelled"],
    "submitted": ["budget_check", "approved", "cancelled"],  # budget_check for pro, direct approve for simple
    "budget_check": ["approved", "cancelled"],
    "approved": ["ordering", "cancelled"],
    "ordering": ["ordered", "cancelled"],
    "ordered": ["in_delivery"],
    "in_delivery": ["delivered"],
    "delivered": ["closed"],
    "closed": [],
    "cancelled": [],
}


# ── In-memory store ──────────────────────────────────────────────────────────

_PROJECTS: dict[str, Project] = {}


# ── Helper ────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string with trailing Z."""
    return datetime.utcnow().isoformat() + "Z"


def _pick_fields(data: dict, model_cls: type[BaseModel]) -> dict:
    """Return only the keys from *data* that are valid fields of *model_cls*."""
    valid = model_cls.model_fields
    return {k: v for k, v in data.items() if k in valid}


# ── Public API ────────────────────────────────────────────────────────────────


def create_project(
    requester: str,
    title: str = "",
    items: list[dict] | None = None,
    domain: str = "parts",
    unspsc_code: str = "",
    mpk: str = "",
    is_professional: bool = True,
    **kwargs,
) -> dict:
    """Create a new purchase project and return its dict representation."""

    now = _now_iso()
    project_id = f"PRJ-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # Build item list
    project_items: list[ProjectItem] = []
    subtotal = 0.0
    if items:
        for raw in items:
            pi = ProjectItem(**_pick_fields(raw, ProjectItem))
            project_items.append(pi)
            subtotal += pi.price * pi.quantity

    effective_title = title or f"Zapotrzebowanie {project_id}"

    project = Project(
        project_id=project_id,
        title=effective_title,
        requester=requester,
        status="draft",
        status_label="Szkic",
        items=project_items,
        subtotal=subtotal,
        final_total=subtotal,
        domain=domain,
        unspsc_code=unspsc_code,
        mpk=mpk,
        is_professional=is_professional,
        created_at=now,
        updated_at=now,
        history=[
            ProjectEvent(
                timestamp=now,
                action="created",
                actor=requester,
                note=f"Projekt utworzony: {effective_title}",
            )
        ],
        **_pick_fields(kwargs, Project),
    )

    _PROJECTS[project_id] = project
    log.info("Project %s created by %s (%d items, %.2f PLN)", project_id, requester, len(project_items), subtotal)
    return project.model_dump()


def get_project(project_id: str) -> dict | None:
    """Return a single project by ID, or ``None`` if it does not exist."""
    p = _PROJECTS.get(project_id)
    return p.model_dump() if p else None


def list_projects(
    requester: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List projects, optionally filtered by *requester* and/or *status*.

    Results are sorted newest-first.
    """
    result: list[dict] = []
    for p in _PROJECTS.values():
        if requester and p.requester != requester:
            continue
        if status and p.status != status:
            continue
        result.append(p.model_dump())
    return sorted(result, key=lambda x: x["created_at"], reverse=True)


def transition_project(
    project_id: str,
    new_status: str,
    actor: str,
    note: str = "",
) -> dict:
    """Transition a project to *new_status*.

    Raises ``ValueError`` when the project is not found or the transition is
    not allowed by the state machine.
    """
    p = _PROJECTS.get(project_id)
    if not p:
        raise ValueError(f"Project {project_id} not found")

    valid = TRANSITIONS.get(p.status, [])
    if new_status not in valid:
        raise ValueError(
            f"Cannot transition from '{p.status}' to '{new_status}'. "
            f"Valid transitions: {valid}"
        )

    now = _now_iso()
    p.status = new_status
    p.status_label = STATUS_LABELS.get(new_status, new_status)
    p.updated_at = now

    # Set milestone timestamps
    if new_status == "submitted":
        p.submitted_at = now
    elif new_status == "approved":
        p.approved_at = now
        if actor not in p.approved_by:
            p.approved_by.append(actor)
    elif new_status == "ordered":
        p.ordered_at = now
    elif new_status == "delivered":
        p.delivered_at = now

    label = STATUS_LABELS.get(new_status, new_status)
    p.history.append(
        ProjectEvent(
            timestamp=now,
            action=f"status_changed_to_{new_status}",
            actor=actor,
            note=note or f"Status zmieniony na: {label}",
        )
    )

    log.info("Project %s transitioned to '%s' by %s", project_id, new_status, actor)
    return p.model_dump()


def update_project_items(
    project_id: str,
    items: list[dict],
    actor: str,
) -> dict:
    """Replace items in a *draft* project.

    Raises ``ValueError`` if the project is not found or is not in draft status.
    """
    p = _PROJECTS.get(project_id)
    if not p:
        raise ValueError(f"Project {project_id} not found")
    if p.status != "draft":
        raise ValueError("Can only update items in draft status")

    now = _now_iso()
    p.items = [ProjectItem(**_pick_fields(raw, ProjectItem)) for raw in items]
    p.subtotal = sum(it.price * it.quantity for it in p.items)
    p.final_total = p.subtotal
    p.updated_at = now

    p.history.append(
        ProjectEvent(
            timestamp=now,
            action="items_updated",
            actor=actor,
            note=f"Zaktualizowano {len(p.items)} pozycji",
        )
    )

    log.info("Project %s items updated by %s (%d items)", project_id, actor, len(p.items))
    return p.model_dump()


def check_budget(project_id: str, actor: str) -> dict:
    """Check whether a project stays within its budget limit and evaluate
    approval requirements via the buying-engine policy.

    Returns a summary dict with ``budget_ok``, totals, and approval info.
    """
    p = _PROJECTS.get(project_id)
    if not p:
        raise ValueError(f"Project {project_id} not found")

    now = _now_iso()
    budget_ok = True
    notes: list[str] = []

    if p.budget_limit > 0 and p.final_total > p.budget_limit:
        budget_ok = False
        notes.append(
            f"Przekroczono budżet: {p.final_total:.0f} PLN > limit {p.budget_limit:.0f} PLN"
        )

    # Delegate to buying_engine approval policies
    from app.buying_engine import evaluate_approval

    approval_result = evaluate_approval(
        {
            "subtotal": p.final_total,
            "total_items": sum(it.quantity for it in p.items),
            "items": [it.model_dump() for it in p.items],
        }
    )

    p.requires_approval = approval_result.get("requires_approval", True)
    p.approval_chain = approval_result.get("approvers", [])

    event_note = (
        (f"Budżet {'OK' if budget_ok else 'PRZEKROCZONY'}. " + "; ".join(notes))
        if notes
        else f"Budżet OK ({p.final_total:.0f} PLN)"
    )
    p.history.append(
        ProjectEvent(timestamp=now, action="budget_checked", actor=actor, note=event_note)
    )
    p.updated_at = now

    log.info("Project %s budget check: ok=%s, total=%.2f", project_id, budget_ok, p.final_total)
    return {
        "project_id": project_id,
        "budget_ok": budget_ok,
        "total": p.final_total,
        "budget_limit": p.budget_limit,
        "requires_approval": p.requires_approval,
        "approval_chain": p.approval_chain,
        "notes": notes,
    }


def link_order(project_id: str, order_id: str, actor: str) -> dict:
    """Link an order (from ``buying_engine``) to this project.

    Raises ``ValueError`` if the project is not found.
    """
    p = _PROJECTS.get(project_id)
    if not p:
        raise ValueError(f"Project {project_id} not found")

    now = _now_iso()
    if order_id not in p.order_ids:
        p.order_ids.append(order_id)

    p.history.append(
        ProjectEvent(
            timestamp=now,
            action="order_linked",
            actor=actor,
            note=f"Powiązano zamówienie {order_id}",
        )
    )
    p.updated_at = now

    log.info("Project %s linked to order %s by %s", project_id, order_id, actor)
    return p.model_dump()


def add_comment(project_id: str, actor: str, comment: str) -> dict:
    """Append a free-text comment to the project audit trail.

    Raises ``ValueError`` if the project is not found.
    """
    p = _PROJECTS.get(project_id)
    if not p:
        raise ValueError(f"Project {project_id} not found")

    now = _now_iso()
    p.history.append(
        ProjectEvent(timestamp=now, action="comment", actor=actor, note=comment)
    )
    p.updated_at = now
    return p.model_dump()


def get_project_stats(requester: str | None = None) -> dict:
    """Return aggregate statistics across all projects (or filtered by requester).

    Keys: ``total_projects``, ``by_status``, ``total_value``, ``active``.
    """
    projects = list_projects(requester=requester)
    by_status: dict[str, int] = {}
    total_value = 0.0
    for p in projects:
        s = p["status"]
        by_status[s] = by_status.get(s, 0) + 1
        total_value += p["final_total"]

    return {
        "total_projects": len(projects),
        "by_status": by_status,
        "total_value": total_value,
        "active": sum(
            1
            for p in projects
            if p["status"] not in ("delivered", "closed", "cancelled")
        ),
    }
