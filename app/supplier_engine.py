"""
Supplier Management Engine — profiles, VIES lookup, certificates, contacts, self-assessment.

In-memory store with demo data. VIES API via urllib (zero extra dependencies).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.schemas import (
    CertificationType,
    ContactPerson,
    ContactRole,
    SelfAssessmentAnswer,
    SelfAssessmentQuestion,
    SelfAssessmentResponse,
    SupplierCertificate,
    SupplierCreateRequest,
    SupplierInput,
    SupplierProfile,
    ViesLookupResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_suppliers: dict[str, SupplierProfile] = {}
_vies_cache: dict[str, tuple[ViesLookupResponse, float]] = {}  # nip -> (response, timestamp)
_VIES_CACHE_TTL = 86400  # 24 hours
_suppliers_hydrated = False


def _persist_supplier(profile: SupplierProfile) -> None:
    """Write-through: save supplier profile to DB. Silent fallback."""
    try:
        from app.database import DB_AVAILABLE, _get_client, db_save_supplier_profile
        if not DB_AVAILABLE:
            return
        client = _get_client()
        db_save_supplier_profile(client, profile.model_dump(mode="json"))
    except Exception as e:
        logger.warning("Supplier DB persist failed: %s", e)


def _delete_supplier_from_db(supplier_id: str) -> None:
    """Remove supplier from DB."""
    try:
        from app.database import DB_AVAILABLE, _get_client, db_delete_supplier_profile
        if not DB_AVAILABLE:
            return
        client = _get_client()
        db_delete_supplier_profile(client, supplier_id)
    except Exception as e:
        logger.warning("Supplier DB delete failed: %s", e)


def _hydrate_suppliers_from_db() -> None:
    """Load supplier profiles from DB into in-memory cache. Called once on first access."""
    global _suppliers_hydrated
    if _suppliers_hydrated:
        return
    _suppliers_hydrated = True
    try:
        from app.database import DB_AVAILABLE, _get_client, db_list_supplier_profiles
        if not DB_AVAILABLE:
            return
        client = _get_client()
        rows = db_list_supplier_profiles(client)
        for row in rows:
            sid = row.get("supplier_id")
            if sid and sid not in _suppliers:
                try:
                    profile = SupplierProfile(**row)
                    _suppliers[sid] = profile
                except Exception:
                    logger.warning("Failed to hydrate supplier %s", sid)
        if rows:
            logger.info("Hydrated %d supplier profiles from database", len(rows))
    except Exception as e:
        logger.warning("Supplier hydration failed: %s", e)

# ---------------------------------------------------------------------------
# VIES API client
# ---------------------------------------------------------------------------

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"


def vies_lookup(country_code: str, vat_number: str) -> ViesLookupResponse:
    """Query EU VIES for VAT number validation. Returns company name + address."""
    cache_key = f"{country_code}{vat_number}"
    now = datetime.now(timezone.utc).timestamp()

    # Check cache
    if cache_key in _vies_cache:
        cached, ts = _vies_cache[cache_key]
        if now - ts < _VIES_CACHE_TTL:
            return cached

    payload = json.dumps({"countryCode": country_code, "vatNumber": vat_number}).encode()
    req = urllib.request.Request(
        VIES_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = ViesLookupResponse(
            valid=data.get("valid", False),
            name=data.get("name", "").strip() or "",
            address=data.get("address", "").strip() or "",
            country_code=data.get("countryCode", country_code),
            vat_number=data.get("vatNumber", vat_number),
            request_date=data.get("requestDate", ""),
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:
        logger.warning("VIES lookup failed for %s%s: %s", country_code, vat_number, e)
        result = ViesLookupResponse(
            valid=False,
            country_code=country_code,
            vat_number=vat_number,
            request_date=datetime.now(timezone.utc).isoformat(),
        )

    _vies_cache[cache_key] = (result, now)
    return result


# ---------------------------------------------------------------------------
# Self-assessment questionnaire
# ---------------------------------------------------------------------------

ASSESSMENT_QUESTIONS: list[SelfAssessmentQuestion] = [
    # Quality (3)
    SelfAssessmentQuestion(question_id="Q01", category="quality", question_text="System zarzadzania jakoscia (ISO 9001 lub rownowazny)?", weight=1.5),
    SelfAssessmentQuestion(question_id="Q02", category="quality", question_text="Wskaznik reklamacji ponizej 2% w ostatnich 12 miesiacach?", weight=1.0),
    SelfAssessmentQuestion(question_id="Q03", category="quality", question_text="Regularne audyty wewnetrzne i dzialania korygujace?", weight=1.0),
    # Delivery (3)
    SelfAssessmentQuestion(question_id="Q04", category="delivery", question_text="Terminowosc dostaw powyzej 95%?", weight=1.5),
    SelfAssessmentQuestion(question_id="Q05", category="delivery", question_text="Elastycznosc w reagowaniu na zmiany zamowien?", weight=1.0),
    SelfAssessmentQuestion(question_id="Q06", category="delivery", question_text="Zdolnosc do obslugi zamowien ekspresowych (24-48h)?", weight=1.0),
    # Sustainability (3)
    SelfAssessmentQuestion(question_id="Q07", category="sustainability", question_text="Certyfikat srodowiskowy (ISO 14001, EMAS)?", weight=1.5),
    SelfAssessmentQuestion(question_id="Q08", category="sustainability", question_text="Raportowanie emisji CO2 i plan redukcji?", weight=1.0),
    SelfAssessmentQuestion(question_id="Q09", category="sustainability", question_text="Polityka zrownowazonych zakupow w lancuchu dostaw?", weight=1.0),
    # Innovation (3)
    SelfAssessmentQuestion(question_id="Q10", category="innovation", question_text="Inwestycje w R&D powyzej 3% przychodow?", weight=1.0),
    SelfAssessmentQuestion(question_id="Q11", category="innovation", question_text="Wdrozenie systemow EDI / integracja API?", weight=1.0),
    SelfAssessmentQuestion(question_id="Q12", category="innovation", question_text="Gotowsc do wspolnych projektow rozwojowych?", weight=1.0),
]


def get_assessment_questions() -> list[SelfAssessmentQuestion]:
    return ASSESSMENT_QUESTIONS


def submit_assessment(supplier_id: str, answers: list[SelfAssessmentAnswer]) -> Optional[SelfAssessmentResponse]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None

    q_map = {q.question_id: q for q in ASSESSMENT_QUESTIONS}
    cat_totals: dict[str, float] = {}
    cat_weights: dict[str, float] = {}

    for a in answers:
        q = q_map.get(a.question_id)
        if not q:
            continue
        cat_totals[q.category] = cat_totals.get(q.category, 0.0) + a.score * q.weight
        cat_weights[q.category] = cat_weights.get(q.category, 0.0) + 5.0 * q.weight

    category_scores = {}
    for cat in cat_totals:
        category_scores[cat] = round(cat_totals[cat] / max(cat_weights[cat], 1e-9), 2)

    overall = round(sum(category_scores.values()) / max(len(category_scores), 1), 2)

    result = SelfAssessmentResponse(
        supplier_id=supplier_id,
        submitted_at=datetime.now(timezone.utc).isoformat(),
        answers=answers,
        overall_score=overall,
        category_scores=category_scores,
    )
    supplier.self_assessment = result
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return result


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _gen_id(prefix: str, length: int = 8) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:length].upper()}"


def create_supplier(req: SupplierCreateRequest) -> SupplierProfile:
    """Create supplier from NIP — auto-lookup VIES."""
    vies = vies_lookup("PL", req.nip)
    now = datetime.now(timezone.utc).isoformat()

    profile = SupplierProfile(
        supplier_id=_gen_id("SUP"),
        name=req.name_override or vies.name or f"Dostawca {req.nip}",
        nip=req.nip,
        vat_valid=vies.valid,
        address=req.address_override or vies.address or "",
        country_code="PL",
        domains=req.domains,
        created_at=now,
        updated_at=now,
    )
    _suppliers[profile.supplier_id] = profile
    _persist_supplier(profile)
    return profile


def get_supplier(supplier_id: str) -> Optional[SupplierProfile]:
    _hydrate_suppliers_from_db()
    return _suppliers.get(supplier_id)


def list_suppliers(domain: Optional[str] = None, search: Optional[str] = None) -> list[SupplierProfile]:
    _hydrate_suppliers_from_db()
    result = list(_suppliers.values())
    if domain:
        result = [s for s in result if domain in s.domains]
    if search:
        q = search.lower()
        result = [s for s in result if q in s.name.lower() or q in s.nip or q in s.address.lower()]
    return result


def update_supplier(supplier_id: str, updates: dict) -> Optional[SupplierProfile]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None
    for k, v in updates.items():
        if hasattr(supplier, k) and k not in ("supplier_id", "created_at"):
            setattr(supplier, k, v)
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return supplier


def delete_supplier(supplier_id: str) -> bool:
    removed = _suppliers.pop(supplier_id, None) is not None
    if removed:
        _delete_supplier_from_db(supplier_id)
    return removed


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

def add_certificate(supplier_id: str, cert: SupplierCertificate) -> Optional[SupplierProfile]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None
    cert.cert_id = _gen_id("CERT", 6)
    supplier.certificates.append(cert)
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return supplier


def remove_certificate(supplier_id: str, cert_id: str) -> Optional[SupplierProfile]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None
    supplier.certificates = [c for c in supplier.certificates if c.cert_id != cert_id]
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return supplier


def get_expiring_certificates(days_ahead: int = 90) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = []
    for s in _suppliers.values():
        for c in s.certificates:
            if c.expiry_date and c.expiry_date <= cutoff:
                result.append({
                    "supplier_id": s.supplier_id,
                    "supplier_name": s.name,
                    "cert_id": c.cert_id,
                    "cert_type": c.cert_type.value if hasattr(c.cert_type, "value") else str(c.cert_type),
                    "expiry_date": c.expiry_date,
                    "expired": c.expiry_date < today,
                    "days_remaining": (datetime.strptime(c.expiry_date, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days,
                })
    result.sort(key=lambda x: x["expiry_date"])
    return result


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def add_contact(supplier_id: str, contact: ContactPerson) -> Optional[SupplierProfile]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None
    contact.contact_id = _gen_id("CON", 6)
    supplier.contacts.append(contact)
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return supplier


def remove_contact(supplier_id: str, contact_id: str) -> Optional[SupplierProfile]:
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None
    supplier.contacts = [c for c in supplier.contacts if c.contact_id != contact_id]
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return supplier


# ---------------------------------------------------------------------------
# Optimizer bridge
# ---------------------------------------------------------------------------

def supplier_to_optimizer_input(supplier_id: str) -> Optional[SupplierInput]:
    """Convert SupplierProfile → SupplierInput for the optimizer."""
    supplier = _suppliers.get(supplier_id)
    if not supplier:
        return None

    # Calculate compliance from certs + assessment
    cert_bonus = min(len(supplier.certificates) * 0.12, 0.36)
    assess_quality = 0.0
    assess_sustain = 0.0
    if supplier.self_assessment:
        assess_quality = supplier.self_assessment.category_scores.get("quality", 0.0) * 0.4
        assess_sustain = supplier.self_assessment.category_scores.get("sustainability", 0.0) * 0.4

    compliance = min(0.30 + cert_bonus + assess_quality, 1.0)

    env_certs = sum(1 for c in supplier.certificates if c.cert_type in (
        CertificationType.iso_14001, CertificationType.emas, CertificationType.iso_50001
    ))
    esg = min(0.25 + env_certs * 0.15 + assess_sustain, 1.0)

    existing = supplier.optimizer_input
    opt = SupplierInput(
        supplier_id=supplier.supplier_id,
        name=supplier.name,
        unit_cost=existing.unit_cost if existing else 100.0,
        logistics_cost=existing.logistics_cost if existing else 15.0,
        lead_time_days=existing.lead_time_days if existing else 5.0,
        compliance_score=round(compliance, 2),
        esg_score=round(esg, 2),
        min_order_qty=existing.min_order_qty if existing else 0,
        max_capacity=existing.max_capacity if existing else 10000,
        served_regions=existing.served_regions if existing else ["PL-MA"],
        payment_terms_days=existing.payment_terms_days if existing else 30.0,
        is_preferred=existing.is_preferred if existing else False,
        region_code=supplier.country_code,
    )
    supplier.optimizer_input = opt
    supplier.updated_at = datetime.now(timezone.utc).isoformat()
    _persist_supplier(supplier)
    return opt


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _init_demo_suppliers() -> None:
    now = datetime.now(timezone.utc).isoformat()
    exp_ok = (datetime.now(timezone.utc) + timedelta(days=540)).strftime("%Y-%m-%d")
    exp_soon = (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d")
    exp_past = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    demos = [
        SupplierProfile(
            supplier_id="SUP-TRW",
            name="TRW Automotive (DE)",
            nip="5261234567",
            vat_valid=True,
            address="ul. Przemyslowa 15, 30-001 Krakow",
            country_code="DE",
            website="https://www.trw.com",
            founded_year=1904,
            employee_count=60000,
            annual_revenue_pln=850_000_000,
            domains=["parts", "oe_components"],
            certificates=[
                SupplierCertificate(cert_id="CERT-001", cert_type=CertificationType.iso_9001, issuer="TUV Rheinland", issue_date="2023-03-15", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-002", cert_type=CertificationType.iatf_16949, issuer="Bureau Veritas", issue_date="2023-06-01", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-003", cert_type=CertificationType.iso_14001, issuer="TUV Rheinland", issue_date="2022-11-10", expiry_date=exp_soon),
            ],
            contacts=[
                ContactPerson(contact_id="CON-001", name="Hans Mueller", role=ContactRole.key_account, email="h.mueller@trw.com", phone="+49 151 1234567", is_primary=True),
                ContactPerson(contact_id="CON-002", name="Anna Kowalska", role=ContactRole.quality, email="a.kowalska@trw.com", phone="+48 601 234567"),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-TRW", name="TRW Automotive (DE)", unit_cost=38.50, logistics_cost=7.20, lead_time_days=4.0, compliance_score=0.97, esg_score=0.91, min_order_qty=500, max_capacity=25000, served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP", "PL-PM"], region_code="DE", payment_terms_days=45.0, is_preferred=True),
            created_at=now, updated_at=now,
        ),
        SupplierProfile(
            supplier_id="SUP-BOSCH",
            name="Bosch Aftermarket (DE)",
            nip="5271234568",
            vat_valid=True,
            address="ul. Jutrzenki 105, 02-231 Warszawa",
            country_code="DE",
            website="https://www.bosch.com",
            founded_year=1886,
            employee_count=400000,
            annual_revenue_pln=1_200_000_000,
            domains=["parts", "oe_components", "batteries"],
            certificates=[
                SupplierCertificate(cert_id="CERT-004", cert_type=CertificationType.iso_9001, issuer="DQS", issue_date="2023-01-20", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-005", cert_type=CertificationType.iatf_16949, issuer="DQS", issue_date="2023-04-15", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-006", cert_type=CertificationType.iso_50001, issuer="TUV Sud", issue_date="2022-08-01", expiry_date=exp_soon),
            ],
            contacts=[
                ContactPerson(contact_id="CON-003", name="Klaus Weber", role=ContactRole.sales, email="k.weber@bosch.com", phone="+49 711 1234567", is_primary=True),
                ContactPerson(contact_id="CON-004", name="Magdalena Nowak", role=ContactRole.logistics, email="m.nowak@bosch.com", phone="+48 602 345678"),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-BOSCH", name="Bosch Aftermarket (DE)", unit_cost=42.00, logistics_cost=6.50, lead_time_days=3.0, compliance_score=0.95, esg_score=0.93, min_order_qty=200, max_capacity=30000, served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP", "PL-DS"], region_code="DE", payment_terms_days=60.0, is_preferred=True),
            created_at=now, updated_at=now,
        ),
        SupplierProfile(
            supplier_id="SUP-LUMAG",
            name="LuMag Parts Lublin",
            nip="7121234569",
            vat_valid=True,
            address="ul. Metalurgiczna 8, 20-200 Lublin",
            country_code="PL",
            website="https://www.lumag.pl",
            founded_year=1998,
            employee_count=120,
            annual_revenue_pln=45_000_000,
            domains=["parts"],
            certificates=[
                SupplierCertificate(cert_id="CERT-007", cert_type=CertificationType.iso_9001, issuer="PCBC", issue_date="2023-09-01", expiry_date=exp_ok),
            ],
            contacts=[
                ContactPerson(contact_id="CON-005", name="Tomasz Wisniewski", role=ContactRole.management, email="t.wisniewski@lumag.pl", phone="+48 603 456789", is_primary=True),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-LUMAG", name="LuMag Parts Lublin", unit_cost=28.00, logistics_cost=4.50, lead_time_days=2.0, compliance_score=0.82, esg_score=0.68, min_order_qty=100, max_capacity=8000, served_regions=["PL-LU", "PL-MA", "PL-MZ"], region_code="PL", payment_terms_days=30.0),
            created_at=now, updated_at=now,
        ),
        SupplierProfile(
            supplier_id="SUP-KRAFT",
            name="KraftPol Bydgoszcz",
            nip="5541234570",
            vat_valid=True,
            address="ul. Fordońska 120, 85-001 Bydgoszcz",
            country_code="PL",
            website="https://www.kraftpol.pl",
            founded_year=2005,
            employee_count=85,
            annual_revenue_pln=32_000_000,
            domains=["parts", "bodywork"],
            certificates=[
                SupplierCertificate(cert_id="CERT-008", cert_type=CertificationType.iso_9001, issuer="PCBC", issue_date="2022-05-15", expiry_date=exp_past),
                SupplierCertificate(cert_id="CERT-009", cert_type=CertificationType.iso_14001, issuer="Bureau Veritas", issue_date="2023-02-01", expiry_date=exp_ok),
            ],
            contacts=[
                ContactPerson(contact_id="CON-006", name="Piotr Kaczmarek", role=ContactRole.sales, email="p.kaczmarek@kraftpol.pl", phone="+48 604 567890", is_primary=True),
                ContactPerson(contact_id="CON-007", name="Ewa Szymanska", role=ContactRole.quality, email="e.szymanska@kraftpol.pl", phone="+48 605 678901"),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-KRAFT", name="KraftPol Bydgoszcz", unit_cost=31.00, logistics_cost=5.80, lead_time_days=3.0, compliance_score=0.85, esg_score=0.78, min_order_qty=200, max_capacity=12000, served_regions=["PL-KP", "PL-WP", "PL-PM"], region_code="PL", payment_terms_days=45.0),
            created_at=now, updated_at=now,
        ),
        SupplierProfile(
            supplier_id="SUP-BREMBO",
            name="Brembo Poland",
            nip="5731234571",
            vat_valid=True,
            address="ul. Czestochowska 25, 42-200 Czestochowa",
            country_code="IT",
            website="https://www.brembo.com",
            founded_year=1961,
            employee_count=12000,
            annual_revenue_pln=320_000_000,
            domains=["parts", "oe_components"],
            certificates=[
                SupplierCertificate(cert_id="CERT-010", cert_type=CertificationType.iso_9001, issuer="DNV", issue_date="2023-07-01", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-011", cert_type=CertificationType.iatf_16949, issuer="DNV", issue_date="2023-07-01", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-012", cert_type=CertificationType.emas, issuer="EU EMAS", issue_date="2023-01-15", expiry_date=exp_ok),
            ],
            contacts=[
                ContactPerson(contact_id="CON-008", name="Marco Rossi", role=ContactRole.key_account, email="m.rossi@brembo.com", phone="+39 035 1234567", is_primary=True),
                ContactPerson(contact_id="CON-009", name="Katarzyna Zielinska", role=ContactRole.logistics, email="k.zielinska@brembo.com", phone="+48 606 789012"),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-BREMBO", name="Brembo Poland", unit_cost=52.00, logistics_cost=8.50, lead_time_days=5.0, compliance_score=0.96, esg_score=0.94, min_order_qty=300, max_capacity=20000, served_regions=["PL-SL", "PL-MA", "PL-OP"], region_code="IT", payment_terms_days=60.0, contract_min_allocation=0.10, is_preferred=True),
            created_at=now, updated_at=now,
        ),
        SupplierProfile(
            supplier_id="SUP-CASTROL",
            name="Castrol Polska",
            nip="5261234572",
            vat_valid=True,
            address="ul. Marynarska 15, 02-674 Warszawa",
            country_code="GB",
            website="https://www.castrol.com/pl",
            founded_year=1899,
            employee_count=7000,
            annual_revenue_pln=180_000_000,
            domains=["oils"],
            certificates=[
                SupplierCertificate(cert_id="CERT-013", cert_type=CertificationType.iso_9001, issuer="Lloyd's Register", issue_date="2023-05-20", expiry_date=exp_ok),
                SupplierCertificate(cert_id="CERT-014", cert_type=CertificationType.iso_14001, issuer="Lloyd's Register", issue_date="2023-05-20", expiry_date=exp_ok),
            ],
            contacts=[
                ContactPerson(contact_id="CON-010", name="Jan Lewandowski", role=ContactRole.sales, email="j.lewandowski@castrol.com", phone="+48 607 890123", is_primary=True),
            ],
            optimizer_input=SupplierInput(supplier_id="SUP-CASTROL", name="Castrol Polska", unit_cost=45.00, logistics_cost=5.00, lead_time_days=3.0, compliance_score=0.92, esg_score=0.88, min_order_qty=100, max_capacity=50000, served_regions=["PL-MZ", "PL-MA", "PL-SL", "PL-WP", "PL-DS", "PL-PM"], region_code="GB", payment_terms_days=30.0),
            created_at=now, updated_at=now,
        ),
    ]

    for s in demos:
        _suppliers[s.supplier_id] = s


# Initialize on import
_init_demo_suppliers()
