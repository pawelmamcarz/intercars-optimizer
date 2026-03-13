"""
Supplier Management — API routes.

GET  /suppliers/                         → list suppliers (query: domain, search)
POST /suppliers/                         → create supplier from NIP (VIES auto-lookup)
GET  /suppliers/{id}                     → supplier profile
PUT  /suppliers/{id}                     → update profile
DELETE /suppliers/{id}                   → delete supplier
POST /suppliers/vies-lookup              → VIES VAT validation
POST /suppliers/{id}/certificates        → add certificate
DELETE /suppliers/{id}/certificates/{cid}→ remove certificate
GET  /suppliers/certificates/expiring    → expiring certs (90 days default)
POST /suppliers/{id}/contacts            → add contact
DELETE /suppliers/{id}/contacts/{cid}    → remove contact
GET  /suppliers/assessment/questions     → self-assessment questionnaire
POST /suppliers/{id}/assessment          → submit self-assessment
GET  /suppliers/{id}/optimizer-input     → get/generate SupplierInput
POST /suppliers/{id}/run-optimization    → run optimization with this supplier
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.data_layer import get_domain_data, DOMAIN_WEIGHTS
from app.optimizer import run_optimization
from app.schemas import (
    ContactPerson,
    CriteriaWeights,
    SelfAssessmentAnswer,
    SupplierCertificate,
    SupplierCreateRequest,
    SupplierProfile,
    ViesLookupRequest,
    ViesLookupResponse,
)
from app.supplier_engine import (
    add_certificate,
    add_contact,
    create_supplier,
    delete_supplier,
    get_assessment_questions,
    get_expiring_certificates,
    get_supplier,
    list_suppliers,
    remove_certificate,
    remove_contact,
    submit_assessment,
    supplier_to_optimizer_input,
    update_supplier,
    vies_lookup,
)

supplier_router = APIRouter(tags=["Supplier Management"])


# ── CRUD ──────────────────────────────────────────────────────────────────

@supplier_router.get("/suppliers/", summary="List all suppliers", tags=["suppliers"])
def api_list_suppliers(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    search: Optional[str] = Query(None, description="Search by name/NIP/address"),
):
    suppliers = list_suppliers(domain=domain, search=search)
    return {"suppliers": [s.model_dump() for s in suppliers], "total": len(suppliers)}


@supplier_router.post("/suppliers/", response_model=SupplierProfile, summary="Create supplier from NIP", tags=["suppliers"])
def api_create_supplier(req: SupplierCreateRequest):
    return create_supplier(req)


@supplier_router.get("/suppliers/certificates/expiring", summary="List expiring certificates", tags=["suppliers"])
def api_expiring_certs(days_ahead: int = Query(90, ge=1, le=365)):
    certs = get_expiring_certificates(days_ahead)
    return {"expiring": certs, "total": len(certs), "days_ahead": days_ahead}


@supplier_router.get("/suppliers/assessment/questions", summary="Self-assessment questionnaire", tags=["suppliers"])
def api_assessment_questions():
    questions = get_assessment_questions()
    return {"questions": [q.model_dump() for q in questions], "total": len(questions)}


@supplier_router.get("/suppliers/{supplier_id}", response_model=SupplierProfile, summary="Get supplier profile", tags=["suppliers"])
def api_get_supplier(supplier_id: str):
    s = get_supplier(supplier_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


@supplier_router.put("/suppliers/{supplier_id}", response_model=SupplierProfile, summary="Update supplier", tags=["suppliers"])
def api_update_supplier(supplier_id: str, updates: dict):
    s = update_supplier(supplier_id, updates)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


@supplier_router.delete("/suppliers/{supplier_id}", summary="Delete supplier", tags=["suppliers"])
def api_delete_supplier(supplier_id: str):
    if not delete_supplier(supplier_id):
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return {"success": True, "message": f"Supplier {supplier_id} deleted"}


# ── VIES ──────────────────────────────────────────────────────────────────

@supplier_router.post("/suppliers/vies-lookup", response_model=ViesLookupResponse, summary="VIES VAT lookup", tags=["suppliers"])
def api_vies_lookup(req: ViesLookupRequest):
    return vies_lookup(req.country_code, req.vat_number)


# ── Certificates ──────────────────────────────────────────────────────────

@supplier_router.post("/suppliers/{supplier_id}/certificates", response_model=SupplierProfile, summary="Add certificate", tags=["suppliers"])
def api_add_cert(supplier_id: str, cert: SupplierCertificate):
    s = add_certificate(supplier_id, cert)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


@supplier_router.delete("/suppliers/{supplier_id}/certificates/{cert_id}", response_model=SupplierProfile, summary="Remove certificate", tags=["suppliers"])
def api_remove_cert(supplier_id: str, cert_id: str):
    s = remove_certificate(supplier_id, cert_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


# ── Contacts ──────────────────────────────────────────────────────────────

@supplier_router.post("/suppliers/{supplier_id}/contacts", response_model=SupplierProfile, summary="Add contact person", tags=["suppliers"])
def api_add_contact(supplier_id: str, contact: ContactPerson):
    s = add_contact(supplier_id, contact)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


@supplier_router.delete("/suppliers/{supplier_id}/contacts/{contact_id}", response_model=SupplierProfile, summary="Remove contact", tags=["suppliers"])
def api_remove_contact(supplier_id: str, contact_id: str):
    s = remove_contact(supplier_id, contact_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return s


# ── Self-assessment ───────────────────────────────────────────────────────

@supplier_router.post("/suppliers/{supplier_id}/assessment", summary="Submit self-assessment", tags=["suppliers"])
def api_submit_assessment(supplier_id: str, answers: list[SelfAssessmentAnswer]):
    result = submit_assessment(supplier_id, answers)
    if not result:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return result.model_dump()


# ── Optimizer bridge ──────────────────────────────────────────────────────

@supplier_router.get("/suppliers/{supplier_id}/optimizer-input", summary="Get optimizer SupplierInput", tags=["suppliers"])
def api_optimizer_input(supplier_id: str):
    opt = supplier_to_optimizer_input(supplier_id)
    if not opt:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return opt.model_dump()


@supplier_router.post("/suppliers/{supplier_id}/run-optimization", summary="Run optimization with this supplier", tags=["suppliers"])
def api_run_optimization(supplier_id: str, domain: str = Query("parts")):
    """Run optimization injecting this supplier's profile into domain data."""
    opt_input = supplier_to_optimizer_input(supplier_id)
    if not opt_input:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")

    try:
        data = get_domain_data(domain)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown domain: {domain}")

    suppliers = data["suppliers"]
    # Replace matching supplier or append
    replaced = False
    for i, s in enumerate(suppliers):
        if s.supplier_id == opt_input.supplier_id:
            suppliers[i] = opt_input
            replaced = True
            break
    if not replaced:
        suppliers.append(opt_input)

    wc, wt, wcomp, wesg = DOMAIN_WEIGHTS.get(domain, (0.40, 0.30, 0.15, 0.15))
    weights = CriteriaWeights(lambda_param=0.5, w_cost=wc, w_time=wt, w_compliance=wcomp, w_esg=wesg)

    resp, _ = run_optimization(suppliers=suppliers, demand=data["demand"], weights=weights)
    return resp.model_dump()
