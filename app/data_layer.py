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
#  DEMO 3 — Komponenty OE (Original Equipment) — DIRECT
# ═══════════════════════════════════════════════════════════════════

OE_REGION_LABELS: dict[str, str] = {
    "EURO":  "Europa Zachodnia",
    "CEE":   "Europa Środkowo-Wschodnia",
    "ASIA":  "Azja (import)",
}

OE_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="OE-CONTINENTAL", name="Continental AG (DE)", unit_cost=78.00,
        logistics_cost=8.50, lead_time_days=6.0, compliance_score=0.98, esg_score=0.93,
        min_order_qty=500, max_capacity=20000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-VALEO", name="Valeo (FR)", unit_cost=72.50,
        logistics_cost=9.20, lead_time_days=7.0, compliance_score=0.97, esg_score=0.91,
        min_order_qty=400, max_capacity=18000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-DENSO", name="Denso (JP/PL)", unit_cost=85.00,
        logistics_cost=4.30, lead_time_days=5.0, compliance_score=0.99, esg_score=0.96,
        min_order_qty=300, max_capacity=15000, served_regions=["EURO", "CEE", "ASIA"]),
    SupplierInput(supplier_id="OE-MAGNETI", name="Magneti Marelli (IT)", unit_cost=68.00,
        logistics_cost=7.80, lead_time_days=8.0, compliance_score=0.94, esg_score=0.87,
        min_order_qty=600, max_capacity=22000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-AISIN", name="Aisin Seiki (JP/CZ)", unit_cost=91.00,
        logistics_cost=5.50, lead_time_days=4.5, compliance_score=0.98, esg_score=0.95,
        min_order_qty=200, max_capacity=10000, served_regions=["CEE", "ASIA"]),
]

OE_DEMAND: list[DemandItem] = [
    DemandItem(product_id="OE-ALTR-220",  demand_qty=3000, destination_region="EURO"),
    DemandItem(product_id="OE-STRTR-110", demand_qty=2500, destination_region="CEE"),
    DemandItem(product_id="OE-COMP-AC",   demand_qty=1800, destination_region="EURO"),
    DemandItem(product_id="OE-TURBO-VNT", demand_qty=1200, destination_region="CEE"),
    DemandItem(product_id="OE-INJ-CR",    demand_qty=4000, destination_region="ASIA"),
]

OE_PRODUCT_LABELS: dict[str, str] = {
    "OE-ALTR-220":  "Alternator 220A OE",
    "OE-STRTR-110": "Rozrusznik 110kW OE",
    "OE-COMP-AC":   "Kompresor klimatyzacji OE",
    "OE-TURBO-VNT": "Turbosprężarka VNT OE",
    "OE-INJ-CR":    "Wtryskiwacz Common Rail OE",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 4 — Oleje i Płyny Eksploatacyjne — DIRECT
# ═══════════════════════════════════════════════════════════════════

OIL_REGION_LABELS: dict[str, str] = {
    "BULK":  "Dostawy hurtowe (cysterna)",
    "UNIT":  "Dostawy jednostkowe (paleta)",
}

OIL_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="OIL-CASTROL", name="Castrol (BP/UK)", unit_cost=24.50,
        logistics_cost=3.20, lead_time_days=3.0, compliance_score=0.97, esg_score=0.88,
        min_order_qty=1000, max_capacity=50000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-MOBIL", name="Mobil (ExxonMobil)", unit_cost=26.80,
        logistics_cost=2.80, lead_time_days=2.5, compliance_score=0.98, esg_score=0.85,
        min_order_qty=800, max_capacity=40000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-ORLEN", name="Orlen Oil (PL)", unit_cost=19.20,
        logistics_cost=1.50, lead_time_days=1.0, compliance_score=0.92, esg_score=0.78,
        min_order_qty=500, max_capacity=60000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-TOTAL", name="TotalEnergies (FR)", unit_cost=25.00,
        logistics_cost=4.10, lead_time_days=4.0, compliance_score=0.96, esg_score=0.92,
        min_order_qty=600, max_capacity=35000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-LOTOS", name="Lotos Oil (PL)", unit_cost=18.50,
        logistics_cost=1.20, lead_time_days=1.5, compliance_score=0.90, esg_score=0.74,
        min_order_qty=400, max_capacity=45000, served_regions=["BULK", "UNIT"]),
]

OIL_DEMAND: list[DemandItem] = [
    DemandItem(product_id="OIL-5W30-SYN",  demand_qty=15000, destination_region="UNIT"),
    DemandItem(product_id="OIL-5W40-SYN",  demand_qty=12000, destination_region="UNIT"),
    DemandItem(product_id="OIL-ATF-DIII",   demand_qty=4000,  destination_region="BULK"),
    DemandItem(product_id="OIL-BRAKE-DOT4", demand_qty=8000,  destination_region="UNIT"),
    DemandItem(product_id="OIL-COOL-G12",   demand_qty=6000,  destination_region="BULK"),
]

OIL_PRODUCT_LABELS: dict[str, str] = {
    "OIL-5W30-SYN":  "Olej silnikowy 5W-30 syntetyk",
    "OIL-5W40-SYN":  "Olej silnikowy 5W-40 syntetyk",
    "OIL-ATF-DIII":  "Olej ATF Dexron III",
    "OIL-BRAKE-DOT4": "Płyn hamulcowy DOT4",
    "OIL-COOL-G12":  "Płyn chłodniczy G12+",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 5 — Akumulatory i Elektro — DIRECT
# ═══════════════════════════════════════════════════════════════════

BAT_REGION_LABELS: dict[str, str] = {
    "12V":   "Akumulatory 12V standard",
    "EFB":   "Technologia EFB (Start-Stop)",
    "AGM":   "Technologia AGM (Premium)",
}

BAT_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="BAT-VARTA", name="Varta (Clarios/DE)", unit_cost=185.00,
        logistics_cost=12.00, lead_time_days=3.0, compliance_score=0.98, esg_score=0.91,
        min_order_qty=100, max_capacity=8000, served_regions=["12V", "EFB", "AGM"]),
    SupplierInput(supplier_id="BAT-BOSCH", name="Bosch Batteries (DE)", unit_cost=195.00,
        logistics_cost=10.00, lead_time_days=3.5, compliance_score=0.97, esg_score=0.93,
        min_order_qty=80, max_capacity=6000, served_regions=["12V", "EFB", "AGM"]),
    SupplierInput(supplier_id="BAT-CENTRA", name="Centra (Exide/PL)", unit_cost=135.00,
        logistics_cost=5.50, lead_time_days=1.5, compliance_score=0.91, esg_score=0.79,
        min_order_qty=200, max_capacity=15000, served_regions=["12V", "EFB"]),
    SupplierInput(supplier_id="BAT-YUASA", name="Yuasa (JP/UK)", unit_cost=210.00,
        logistics_cost=15.00, lead_time_days=5.0, compliance_score=0.96, esg_score=0.88,
        min_order_qty=50, max_capacity=4000, served_regions=["12V", "EFB", "AGM"]),
    SupplierInput(supplier_id="BAT-JENOX", name="Jenox Akumulatory (PL)", unit_cost=120.00,
        logistics_cost=4.00, lead_time_days=1.0, compliance_score=0.87, esg_score=0.72,
        min_order_qty=150, max_capacity=12000, served_regions=["12V", "EFB"]),
]

BAT_DEMAND: list[DemandItem] = [
    DemandItem(product_id="BAT-12V-60AH",  demand_qty=3500, destination_region="12V"),
    DemandItem(product_id="BAT-12V-74AH",  demand_qty=2800, destination_region="12V"),
    DemandItem(product_id="BAT-EFB-70AH",  demand_qty=1800, destination_region="EFB"),
    DemandItem(product_id="BAT-AGM-80AH",  demand_qty=1200, destination_region="AGM"),
    DemandItem(product_id="BAT-AGM-95AH",  demand_qty=800,  destination_region="AGM"),
]

BAT_PRODUCT_LABELS: dict[str, str] = {
    "BAT-12V-60AH": "Akumulator 12V 60Ah standard",
    "BAT-12V-74AH": "Akumulator 12V 74Ah standard",
    "BAT-EFB-70AH": "Akumulator EFB 70Ah Start-Stop",
    "BAT-AGM-80AH": "Akumulator AGM 80Ah Premium",
    "BAT-AGM-95AH": "Akumulator AGM 95Ah Premium",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 6 — Logistyka i Transport — INDIRECT
# ═══════════════════════════════════════════════════════════════════

LOG_REGION_LABELS: dict[str, str] = {
    "FTL": "Full Truck Load",
    "LTL": "Less Than Truckload",
    "CEP": "Kurier / CEP",
}

LOG_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="LOG-RABEN", name="Raben Group (PL)", unit_cost=4.20,
        logistics_cost=0.80, lead_time_days=1.0, compliance_score=0.96, esg_score=0.88,
        min_order_qty=100, max_capacity=50000, served_regions=["FTL", "LTL"]),
    SupplierInput(supplier_id="LOG-GEIS", name="Geis (DE/CZ)", unit_cost=4.80,
        logistics_cost=1.10, lead_time_days=1.5, compliance_score=0.94, esg_score=0.85,
        min_order_qty=80, max_capacity=40000, served_regions=["FTL", "LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-DHL", name="DHL Freight (DE)", unit_cost=5.50,
        logistics_cost=0.60, lead_time_days=2.0, compliance_score=0.98, esg_score=0.94,
        min_order_qty=50, max_capacity=30000, served_regions=["FTL", "LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-POCZTA", name="Poczta Polska Logistyka", unit_cost=3.20,
        logistics_cost=0.50, lead_time_days=2.5, compliance_score=0.86, esg_score=0.75,
        min_order_qty=200, max_capacity=60000, served_regions=["LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-PEKAES", name="Pekaes SA (PL)", unit_cost=3.90,
        logistics_cost=0.70, lead_time_days=1.0, compliance_score=0.93, esg_score=0.82,
        min_order_qty=150, max_capacity=45000, served_regions=["FTL", "LTL"]),
]

LOG_DEMAND: list[DemandItem] = [
    DemandItem(product_id="LOG-FTL-WEST",  demand_qty=8000,  destination_region="FTL"),
    DemandItem(product_id="LOG-FTL-SOUTH", demand_qty=6000,  destination_region="FTL"),
    DemandItem(product_id="LOG-LTL-DAILY", demand_qty=12000, destination_region="LTL"),
    DemandItem(product_id="LOG-CEP-EXPRESS",demand_qty=5000,  destination_region="CEP"),
]

LOG_PRODUCT_LABELS: dict[str, str] = {
    "LOG-FTL-WEST":   "FTL trasa zachód (DE/FR)",
    "LOG-FTL-SOUTH":  "FTL trasa południe (CZ/SK)",
    "LOG-LTL-DAILY":  "LTL dystrybucja dzienna PL",
    "LOG-CEP-EXPRESS": "Kurier ekspres 24h",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 7 — Opakowania i Materiały — INDIRECT
# ═══════════════════════════════════════════════════════════════════

PKG_REGION_LABELS: dict[str, str] = {
    "KARTON":  "Kartony i tektura",
    "FOLIA":   "Folie i stretch",
    "PALETY":  "Palety i nośniki",
}

PKG_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="PKG-MONDI", name="Mondi Group (AT/PL)", unit_cost=2.80,
        logistics_cost=0.40, lead_time_days=3.0, compliance_score=0.95, esg_score=0.94,
        min_order_qty=5000, max_capacity=200000, served_regions=["KARTON", "FOLIA"]),
    SupplierInput(supplier_id="PKG-SMURFIT", name="Smurfit Kappa (IE/PL)", unit_cost=3.10,
        logistics_cost=0.55, lead_time_days=4.0, compliance_score=0.96, esg_score=0.96,
        min_order_qty=3000, max_capacity=150000, served_regions=["KARTON", "FOLIA"]),
    SupplierInput(supplier_id="PKG-AGATA", name="Agata Opakowania (PL)", unit_cost=2.20,
        logistics_cost=0.25, lead_time_days=1.5, compliance_score=0.89, esg_score=0.78,
        min_order_qty=2000, max_capacity=100000, served_regions=["KARTON", "FOLIA", "PALETY"]),
    SupplierInput(supplier_id="PKG-CHEP", name="CHEP Pooling (UK)", unit_cost=5.50,
        logistics_cost=0.80, lead_time_days=5.0, compliance_score=0.98, esg_score=0.97,
        min_order_qty=500, max_capacity=30000, served_regions=["PALETY"]),
    SupplierInput(supplier_id="PKG-EUROPAL", name="EuroPal Poznań (PL)", unit_cost=4.10,
        logistics_cost=0.30, lead_time_days=2.0, compliance_score=0.91, esg_score=0.82,
        min_order_qty=1000, max_capacity=50000, served_regions=["PALETY"]),
]

PKG_DEMAND: list[DemandItem] = [
    DemandItem(product_id="PKG-BOX-A4",    demand_qty=50000, destination_region="KARTON"),
    DemandItem(product_id="PKG-BOX-HEAVY", demand_qty=20000, destination_region="KARTON"),
    DemandItem(product_id="PKG-STRETCH",   demand_qty=15000, destination_region="FOLIA"),
    DemandItem(product_id="PKG-EUR-PALET", demand_qty=8000,  destination_region="PALETY"),
]

PKG_PRODUCT_LABELS: dict[str, str] = {
    "PKG-BOX-A4":    "Karton fasonowy A4 (standard)",
    "PKG-BOX-HEAVY": "Karton wzmocniony (ciężki towar)",
    "PKG-STRETCH":   "Folia stretch paletowa",
    "PKG-EUR-PALET": "Paleta EUR 1200×800",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 8 — MRO (Maintenance, Repair, Operations) — INDIRECT
# ═══════════════════════════════════════════════════════════════════

MRO_REGION_LABELS: dict[str, str] = {
    "MECH":  "Mechaniczne / narzędzia",
    "ELEC":  "Elektryka / automatyka",
    "BHP":   "BHP / odzież robocza",
}

MRO_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="MRO-WUERTH", name="Würth Polska", unit_cost=45.00,
        logistics_cost=3.50, lead_time_days=2.0, compliance_score=0.96, esg_score=0.89,
        min_order_qty=50, max_capacity=10000, served_regions=["MECH", "ELEC", "BHP"]),
    SupplierInput(supplier_id="MRO-HILTI", name="Hilti (LI/PL)", unit_cost=68.00,
        logistics_cost=4.00, lead_time_days=3.0, compliance_score=0.98, esg_score=0.93,
        min_order_qty=30, max_capacity=5000, served_regions=["MECH", "ELEC"]),
    SupplierInput(supplier_id="MRO-GRAINGER", name="RS Components (UK)", unit_cost=55.00,
        logistics_cost=6.50, lead_time_days=4.0, compliance_score=0.95, esg_score=0.91,
        min_order_qty=20, max_capacity=8000, served_regions=["MECH", "ELEC", "BHP"]),
    SupplierInput(supplier_id="MRO-DRAGER", name="Dräger BHP (DE)", unit_cost=82.00,
        logistics_cost=5.00, lead_time_days=5.0, compliance_score=0.99, esg_score=0.95,
        min_order_qty=10, max_capacity=3000, served_regions=["BHP"]),
    SupplierInput(supplier_id="MRO-TOOLS24", name="Tools24.pl (PL)", unit_cost=32.00,
        logistics_cost=2.00, lead_time_days=1.0, compliance_score=0.88, esg_score=0.74,
        min_order_qty=100, max_capacity=15000, served_regions=["MECH", "ELEC", "BHP"]),
]

MRO_DEMAND: list[DemandItem] = [
    DemandItem(product_id="MRO-KLUCZ-SET", demand_qty=500,  destination_region="MECH"),
    DemandItem(product_id="MRO-WIERTLA",   demand_qty=800,  destination_region="MECH"),
    DemandItem(product_id="MRO-CZUJNIK",   demand_qty=300,  destination_region="ELEC"),
    DemandItem(product_id="MRO-KASK-BHP",  demand_qty=1200, destination_region="BHP"),
    DemandItem(product_id="MRO-REKAW-BHP", demand_qty=2000, destination_region="BHP"),
]

MRO_PRODUCT_LABELS: dict[str, str] = {
    "MRO-KLUCZ-SET": "Zestaw kluczy nasadowych",
    "MRO-WIERTLA":   "Wiertła HSS (komplet)",
    "MRO-CZUJNIK":   "Czujnik indukcyjny PNP",
    "MRO-KASK-BHP":  "Kask ochronny BHP klasa II",
    "MRO-REKAW-BHP": "Rękawice robocze antypoślizgowe",
}


# ═══════════════════════════════════════════════════════════════════
#  Public API — getter functions
# ═══════════════════════════════════════════════════════════════════

# Parts (existing)
def get_demo_suppliers() -> list[SupplierInput]: return DEMO_SUPPLIERS
def get_demo_demand() -> list[DemandItem]: return DEMO_DEMAND
def get_region_labels() -> dict[str, str]: return REGION_LABELS
def get_product_labels() -> dict[str, str]: return PRODUCT_LABELS

# IT Services (existing)
def get_it_demo_suppliers() -> list[SupplierInput]: return IT_DEMO_SUPPLIERS
def get_it_demo_demand() -> list[DemandItem]: return IT_DEMO_DEMAND
def get_it_region_labels() -> dict[str, str]: return IT_REGION_LABELS
def get_it_product_labels() -> dict[str, str]: return IT_PRODUCT_LABELS

# ── NEW domains ──────────────────────────────────────────────────

# Domain registry — single source of truth
DOMAIN_DATA: dict[str, dict] = {
    "parts":         {"suppliers": DEMO_SUPPLIERS,    "demand": DEMO_DEMAND,    "products": PRODUCT_LABELS,     "regions": REGION_LABELS},
    "oe_components": {"suppliers": OE_SUPPLIERS,      "demand": OE_DEMAND,      "products": OE_PRODUCT_LABELS,  "regions": OE_REGION_LABELS},
    "oils":          {"suppliers": OIL_SUPPLIERS,      "demand": OIL_DEMAND,     "products": OIL_PRODUCT_LABELS, "regions": OIL_REGION_LABELS},
    "batteries":     {"suppliers": BAT_SUPPLIERS,      "demand": BAT_DEMAND,     "products": BAT_PRODUCT_LABELS, "regions": BAT_REGION_LABELS},
    "it_services":   {"suppliers": IT_DEMO_SUPPLIERS,  "demand": IT_DEMO_DEMAND, "products": IT_PRODUCT_LABELS,  "regions": IT_REGION_LABELS},
    "logistics":     {"suppliers": LOG_SUPPLIERS,      "demand": LOG_DEMAND,     "products": LOG_PRODUCT_LABELS, "regions": LOG_REGION_LABELS},
    "packaging":     {"suppliers": PKG_SUPPLIERS,      "demand": PKG_DEMAND,     "products": PKG_PRODUCT_LABELS, "regions": PKG_REGION_LABELS},
    "mro":           {"suppliers": MRO_SUPPLIERS,      "demand": MRO_DEMAND,     "products": MRO_PRODUCT_LABELS, "regions": MRO_REGION_LABELS},
}


def get_domain_data(domain: str) -> dict:
    """Return suppliers, demand, products, regions for any registered domain."""
    if domain not in DOMAIN_DATA:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(DOMAIN_DATA.keys())}")
    return DOMAIN_DATA[domain]
