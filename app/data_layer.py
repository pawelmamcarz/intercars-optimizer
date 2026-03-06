"""
Data Layer — EWM integration & realistic INTERCARS demo data.

In production this module talks to the local EWM system.

Two demo datasets:
  1. Auto-parts procurement — 8 suppliers, 12 products, 5 regions
  2. IT Services procurement — 6 integrators, 5 projects, 3 competency areas
"""
from __future__ import annotations

from app.schemas import DemandItem, SupplierInput

# ═══════════════════════════════════════════════════════════════════
#  DEMO 1 — Części Zamienne (Auto-parts)
# ═══════════════════════════════════════════════════════════════════

# Regions (INTERCARS warehouse clusters)
REGION_LABELS: dict[str, str] = {
    "PL-MA": "Małopolska (Kraków)",
    "PL-SL": "Śląsk (Katowice)",
    "PL-MZ": "Mazowsze (Warszawa)",
    "PL-WP": "Wielkopolska (Poznań)",
    "PL-PM": "Pomorze (Gdańsk)",
}

DEMO_SUPPLIERS: list[SupplierInput] = [
    # ── Tier-1: Duzi dostawcy OE ──────────────────────────
    SupplierInput(
        supplier_id="VND-TRW",
        name="TRW Automotive (DE)",
        unit_cost=38.50,
        logistics_cost=7.20,
        lead_time_days=4.0,
        compliance_score=0.97,
        esg_score=0.91,
        min_order_qty=500,
        max_capacity=25000,
        served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP", "PL-PM"],
    ),
    SupplierInput(
        supplier_id="VND-BOSCH",
        name="Bosch Aftermarket (DE)",
        unit_cost=41.00,
        logistics_cost=6.50,
        lead_time_days=3.5,
        compliance_score=0.98,
        esg_score=0.94,
        min_order_qty=300,
        max_capacity=30000,
        served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP", "PL-PM"],
    ),
    # ── Tier-2: Regionalny aftermarket ────────────────────
    SupplierInput(
        supplier_id="VND-LUMAG",
        name="LuMag Parts Lublin",
        unit_cost=29.80,
        logistics_cost=3.10,
        lead_time_days=1.5,
        compliance_score=0.88,
        esg_score=0.72,
        min_order_qty=100,
        max_capacity=12000,
        served_regions=["PL-MA", "PL-SL", "PL-MZ"],
    ),
    SupplierInput(
        supplier_id="VND-KRAFT",
        name="KraftPol Bydgoszcz",
        unit_cost=31.20,
        logistics_cost=4.00,
        lead_time_days=2.0,
        compliance_score=0.86,
        esg_score=0.68,
        min_order_qty=200,
        max_capacity=15000,
        served_regions=["PL-WP", "PL-PM", "PL-MZ"],
    ),
    SupplierInput(
        supplier_id="VND-BREMBO",
        name="Brembo Poland (Częstochowa)",
        unit_cost=52.00,
        logistics_cost=2.80,
        lead_time_days=2.5,
        compliance_score=0.96,
        esg_score=0.89,
        min_order_qty=150,
        max_capacity=8000,
        served_regions=["PL-SL", "PL-MA"],
    ),
    # ── Tier-3: Dostawcy niszowi / ESG-champions ──────────
    SupplierInput(
        supplier_id="VND-GREENF",
        name="GreenFilter CZ (Brno)",
        unit_cost=35.40,
        logistics_cost=5.60,
        lead_time_days=3.0,
        compliance_score=0.91,
        esg_score=0.98,
        min_order_qty=80,
        max_capacity=6000,
        served_regions=["PL-MA", "PL-SL"],
    ),
    SupplierInput(
        supplier_id="VND-SKSLOV",
        name="SK Automotive Žilina",
        unit_cost=33.00,
        logistics_cost=5.20,
        lead_time_days=3.5,
        compliance_score=0.84,
        esg_score=0.76,
        min_order_qty=250,
        max_capacity=10000,
        served_regions=["PL-MA", "PL-SL", "PL-WP"],
    ),
    SupplierInput(
        supplier_id="VND-RAPID",
        name="RapidStock Gdańsk",
        unit_cost=34.50,
        logistics_cost=1.90,
        lead_time_days=0.5,
        compliance_score=0.82,
        esg_score=0.61,
        min_order_qty=50,
        max_capacity=4000,
        served_regions=["PL-PM"],
    ),
]

DEMO_DEMAND: list[DemandItem] = [
    # Kraków hub  ──────────────────────────────────
    DemandItem(product_id="BRK-PAD-0041",  demand_qty=2400, destination_region="PL-MA"),
    DemandItem(product_id="OIL-FLT-1022",  demand_qty=1800, destination_region="PL-MA"),
    # Katowice hub ─────────────────────────────────
    DemandItem(product_id="TIM-BLT-3005",  demand_qty=3200, destination_region="PL-SL"),
    DemandItem(product_id="SPK-PLG-4010",  demand_qty=5000, destination_region="PL-SL"),
    # Warszawa CDN ─────────────────────────────────
    DemandItem(product_id="BRK-DSC-0087",  demand_qty=4000, destination_region="PL-MZ"),
    DemandItem(product_id="AIR-FLT-1055",  demand_qty=2800, destination_region="PL-MZ"),
    DemandItem(product_id="CLT-BRG-6002",  demand_qty=1500, destination_region="PL-MZ"),
    # Poznań hub ───────────────────────────────────
    DemandItem(product_id="WHL-HUB-7010",  demand_qty=2000, destination_region="PL-WP"),
    DemandItem(product_id="RAD-HSE-8003",  demand_qty=1200, destination_region="PL-WP"),
    # Gdańsk hub ───────────────────────────────────
    DemandItem(product_id="ABS-SNR-9001",  demand_qty=1600, destination_region="PL-PM"),
    DemandItem(product_id="SHK-ABS-9020",  demand_qty=2200, destination_region="PL-PM"),
    DemandItem(product_id="ENG-MNT-5050",  demand_qty=900,  destination_region="PL-PM"),
]

PRODUCT_LABELS: dict[str, str] = {
    "BRK-PAD-0041": "Klocki hamulcowe przód",
    "OIL-FLT-1022": "Filtr oleju silnikowego",
    "TIM-BLT-3005": "Pasek rozrządu (kit)",
    "SPK-PLG-4010": "Świece zapłonowe (kpl.)",
    "BRK-DSC-0087": "Tarcze hamulcowe przód",
    "AIR-FLT-1055": "Filtr powietrza",
    "CLT-BRG-6002": "Łożysko sprzęgła",
    "WHL-HUB-7010": "Piasta koła przód",
    "RAD-HSE-8003": "Przewód chłodnicy",
    "ABS-SNR-9001": "Czujnik ABS",
    "SHK-ABS-9020": "Amortyzator przód",
    "ENG-MNT-5050": "Poduszka silnika",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 2 — Usługi IT (IT Services Procurement)
# ═══════════════════════════════════════════════════════════════════

IT_REGION_LABELS: dict[str, str] = {
    "JAVA":  "Ekosystem Java / Spring",
    "CLOUD": "Cloud & DevOps (AWS/Azure)",
    "DATA":  "Data Engineering & AI/ML",
}

IT_DEMO_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(
        supplier_id="IT-ACCENTURE",
        name="Accenture Poland",
        unit_cost=1200.0,       # PLN / roboczogodzina
        logistics_cost=50.0,    # overhead PM
        lead_time_days=30.0,    # kickoff w dniach
        compliance_score=0.995, # SLA 99.5%
        esg_score=0.92,         # niezawodność historyczna
        min_order_qty=160,      # min 160 rbh (1 miesiąc)
        max_capacity=8000,
        served_regions=["JAVA", "CLOUD", "DATA"],
    ),
    SupplierInput(
        supplier_id="IT-CODETE",
        name="Codete (Kraków)",
        unit_cost=750.0,
        logistics_cost=20.0,
        lead_time_days=14.0,
        compliance_score=0.970,
        esg_score=0.88,
        min_order_qty=80,
        max_capacity=5000,
        served_regions=["JAVA", "CLOUD"],
    ),
    SupplierInput(
        supplier_id="IT-SOFTSERVE",
        name="SoftServe (UA/PL)",
        unit_cost=650.0,
        logistics_cost=30.0,
        lead_time_days=21.0,
        compliance_score=0.950,
        esg_score=0.85,
        min_order_qty=200,
        max_capacity=12000,
        served_regions=["JAVA", "CLOUD", "DATA"],
    ),
    SupplierInput(
        supplier_id="IT-NETGURU",
        name="Netguru (Poznań)",
        unit_cost=900.0,
        logistics_cost=25.0,
        lead_time_days=10.0,
        compliance_score=0.980,
        esg_score=0.91,
        min_order_qty=40,
        max_capacity=3000,
        served_regions=["JAVA", "CLOUD"],
    ),
    SupplierInput(
        supplier_id="IT-DELOITTE",
        name="Deloitte Digital",
        unit_cost=1400.0,
        logistics_cost=60.0,
        lead_time_days=45.0,
        compliance_score=0.999,
        esg_score=0.96,
        min_order_qty=320,
        max_capacity=10000,
        served_regions=["JAVA", "CLOUD", "DATA"],
    ),
    SupplierInput(
        supplier_id="IT-MLOPS",
        name="MLOps.pl (Wrocław)",
        unit_cost=850.0,
        logistics_cost=15.0,
        lead_time_days=7.0,
        compliance_score=0.940,
        esg_score=0.93,
        min_order_qty=40,
        max_capacity=2000,
        served_regions=["DATA"],
    ),
]

IT_DEMO_DEMAND: list[DemandItem] = [
    # Java / Spring ───────────────────────────────
    DemandItem(product_id="PRJ-ERP-MIGR",  demand_qty=2000, destination_region="JAVA"),
    DemandItem(product_id="PRJ-MICROSERV", demand_qty=1500, destination_region="JAVA"),
    # Cloud & DevOps ──────────────────────────────
    DemandItem(product_id="PRJ-K8S-INFRA", demand_qty=800,  destination_region="CLOUD"),
    DemandItem(product_id="PRJ-CI-CD",     demand_qty=600,  destination_region="CLOUD"),
    # Data Engineering & AI/ML ────────────────────
    DemandItem(product_id="PRJ-DWH-BUILD", demand_qty=1200, destination_region="DATA"),
]

IT_PRODUCT_LABELS: dict[str, str] = {
    "PRJ-ERP-MIGR":  "Migracja ERP do mikroserwisów",
    "PRJ-MICROSERV": "Budowa platformy mikroserwisowej",
    "PRJ-K8S-INFRA": "Infrastruktura Kubernetes",
    "PRJ-CI-CD":     "Pipeline CI/CD (GitHub Actions)",
    "PRJ-DWH-BUILD": "Budowa Data Warehouse + ML pipeline",
}


# ═══════════════════════════════════════════════════════════════════
#  Public API — getter functions
# ═══════════════════════════════════════════════════════════════════

def get_demo_suppliers() -> list[SupplierInput]:
    return DEMO_SUPPLIERS

def get_demo_demand() -> list[DemandItem]:
    return DEMO_DEMAND

def get_region_labels() -> dict[str, str]:
    return REGION_LABELS

def get_product_labels() -> dict[str, str]:
    return PRODUCT_LABELS

def get_it_demo_suppliers() -> list[SupplierInput]:
    return IT_DEMO_SUPPLIERS

def get_it_demo_demand() -> list[DemandItem]:
    return IT_DEMO_DEMAND

def get_it_region_labels() -> dict[str, str]:
    return IT_REGION_LABELS

def get_it_product_labels() -> dict[str, str]:
    return IT_PRODUCT_LABELS
