"""
Purchase Project API routes.

Provides REST endpoints for managing purchase projects (projekty zakupowe).
Used by both professional buyers and simplified requester UI.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

project_router = APIRouter(tags=["projects"])


# ── Request models ──

class CreateProjectRequest(BaseModel):
    title: str = ""
    items: list[dict] = []
    domain: str = "parts"
    unspsc_code: str = ""
    mpk: str = ""
    gl_account: str = ""
    budget_limit: float = 0.0
    is_professional: bool = True
    requester: str = "buyer@flowproc.eu"
    requester_name: str = ""
    department: str = ""
    description: str = ""


class TransitionRequest(BaseModel):
    new_status: str
    actor: str = "buyer@flowproc.eu"
    note: str = ""


class UpdateItemsRequest(BaseModel):
    items: list[dict]
    actor: str = "buyer@flowproc.eu"


class CommentRequest(BaseModel):
    actor: str = "buyer@flowproc.eu"
    comment: str


# ── Endpoints ──

@project_router.post("/projects")
def create_project(req: CreateProjectRequest):
    """Create a new purchase project."""
    from app.project_engine import create_project as _create
    try:
        return _create(
            requester=req.requester,
            title=req.title,
            items=req.items,
            domain=req.domain,
            unspsc_code=req.unspsc_code,
            mpk=req.mpk,
            gl_account=req.gl_account,
            budget_limit=req.budget_limit,
            is_professional=req.is_professional,
            requester_name=req.requester_name,
            department=req.department,
            description=req.description,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@project_router.get("/projects")
def list_projects(
    requester: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List projects, optionally filtered."""
    from app.project_engine import list_projects as _list
    return {"projects": _list(requester=requester, status=status)}


@project_router.get("/projects/stats")
def project_stats(requester: Optional[str] = Query(None)):
    """Get project statistics."""
    from app.project_engine import get_project_stats
    return get_project_stats(requester=requester)


@project_router.get("/projects/{project_id}")
def get_project(project_id: str):
    """Get project details."""
    from app.project_engine import get_project as _get
    p = _get(project_id)
    if not p:
        raise HTTPException(404, f"Project {project_id} not found")
    return p


@project_router.put("/projects/{project_id}/transition")
def transition_project(project_id: str, req: TransitionRequest):
    """Transition project status."""
    from app.project_engine import transition_project as _transition
    try:
        return _transition(project_id, req.new_status, req.actor, req.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.put("/projects/{project_id}/submit")
def submit_project(project_id: str, actor: str = Query("buyer@flowproc.eu")):
    """Submit project for approval (shortcut)."""
    from app.project_engine import transition_project as _transition
    try:
        return _transition(project_id, "submitted", actor, "Zapotrzebowanie złożone do akceptacji")
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.put("/projects/{project_id}/approve")
def approve_project(project_id: str, actor: str = Query("manager@flowproc.eu")):
    """Approve project (shortcut)."""
    from app.project_engine import transition_project as _transition
    try:
        return _transition(project_id, "approved", actor, f"Zatwierdzone przez {actor}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.get("/projects/{project_id}/budget")
def check_budget(project_id: str, actor: str = Query("buyer@flowproc.eu")):
    """Check project budget."""
    from app.project_engine import check_budget as _check
    try:
        return _check(project_id, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.put("/projects/{project_id}/items")
def update_items(project_id: str, req: UpdateItemsRequest):
    """Update project items (draft only)."""
    from app.project_engine import update_project_items as _update
    try:
        return _update(project_id, req.items, req.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.post("/projects/{project_id}/comments")
def add_comment(project_id: str, req: CommentRequest):
    """Add comment to project."""
    from app.project_engine import add_comment as _comment
    try:
        return _comment(project_id, req.actor, req.comment)
    except ValueError as e:
        raise HTTPException(400, str(e))


@project_router.put("/projects/{project_id}/link-order")
def link_order(project_id: str, order_id: str = Query(...), actor: str = Query("buyer@flowproc.eu")):
    """Link an order to the project."""
    from app.project_engine import link_order as _link
    try:
        return _link(project_id, order_id, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
