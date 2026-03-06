"""
Data Layer — EWM integration & realistic INTERCARS demo data.

In production this module talks to the local EWM system.

v3.0: 10 domains × 2-4 subdomains (~27 subdomen), enriched supplier fields
  DIRECT:   parts, oe_components, oils, batteries, tires, bodywork
  INDIRECT: it_services, logistics, packaging, facility_management
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
    SupplierInput(
        supplier_id="VND-SACHS",
        name="ZF Sachs (DE)",
        unit_cost=44.00,
        logistics_cost=6.80,
        lead_time_days=4.0,
        compliance_score=0.96,
        esg_score=0.90,
        min_order_qty=300,
        max_capacity=18000,
        served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP"],
    ),
    SupplierInput(
        supplier_id="VND-FEBI",
        name="Febi Bilstein (DE)",
        unit_cost=36.80,
        logistics_cost=5.40,
        lead_time_days=3.5,
        compliance_score=0.93,
        esg_score=0.86,
        min_order_qty=200,
        max_capacity=14000,
        served_regions=["PL-MA", "PL-SL", "PL-MZ", "PL-WP", "PL-PM"],
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
    SupplierInput(
        supplier_id="IT-ATOS",
        name="Atos IT Solutions (FR/PL)",
        unit_cost=1100.0,
        logistics_cost=45.0,
        lead_time_days=25.0,
        compliance_score=0.985,
        esg_score=0.90,
        min_order_qty=160,
        max_capacity=7000,
        served_regions=["JAVA", "CLOUD", "DATA"],
    ),
    SupplierInput(
        supplier_id="IT-EPAM",
        name="EPAM Systems (PL)",
        unit_cost=800.0,
        logistics_cost=20.0,
        lead_time_days=14.0,
        compliance_score=0.965,
        esg_score=0.87,
        min_order_qty=120,
        max_capacity=9000,
        served_regions=["JAVA", "CLOUD", "DATA"],
    ),
    SupplierInput(
        supplier_id="IT-SYTAC",
        name="Sytac (PL, Katowice)",
        unit_cost=680.0,
        logistics_cost=10.0,
        lead_time_days=10.0,
        compliance_score=0.945,
        esg_score=0.84,
        min_order_qty=60,
        max_capacity=3500,
        served_regions=["JAVA", "CLOUD"],
    ),
    SupplierInput(
        supplier_id="IT-CAPGEMINI",
        name="Capgemini Polska",
        unit_cost=1300.0,
        logistics_cost=55.0,
        lead_time_days=35.0,
        compliance_score=0.992,
        esg_score=0.94,
        min_order_qty=200,
        max_capacity=8000,
        served_regions=["JAVA", "CLOUD", "DATA"],
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
    SupplierInput(supplier_id="OE-MAHLE", name="Mahle (DE)", unit_cost=74.00,
        logistics_cost=7.00, lead_time_days=5.5, compliance_score=0.96, esg_score=0.90,
        min_order_qty=350, max_capacity=16000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-BOSCH-OE", name="Bosch OE Division (DE)", unit_cost=88.00,
        logistics_cost=6.00, lead_time_days=4.0, compliance_score=0.99, esg_score=0.94,
        min_order_qty=250, max_capacity=25000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-SCHAEFFLER", name="Schaeffler (INA/LuK/DE)", unit_cost=82.00,
        logistics_cost=8.00, lead_time_days=6.0, compliance_score=0.97, esg_score=0.92,
        min_order_qty=300, max_capacity=14000, served_regions=["EURO", "CEE"]),
    SupplierInput(supplier_id="OE-NGK", name="NGK Spark Plug (JP/PL)", unit_cost=65.00,
        logistics_cost=4.00, lead_time_days=3.5, compliance_score=0.95, esg_score=0.88,
        min_order_qty=500, max_capacity=30000, served_regions=["EURO", "CEE", "ASIA"]),
    SupplierInput(supplier_id="OE-HELLA-OE", name="Hella OE Electronics (DE)", unit_cost=95.00,
        logistics_cost=9.00, lead_time_days=7.0, compliance_score=0.97, esg_score=0.91,
        min_order_qty=150, max_capacity=8000, served_regions=["EURO", "CEE"]),
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
    SupplierInput(supplier_id="OIL-SHELL", name="Shell Lubricants (NL)", unit_cost=27.50,
        logistics_cost=3.80, lead_time_days=3.5, compliance_score=0.98, esg_score=0.91,
        min_order_qty=600, max_capacity=38000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-PETRONAS", name="Petronas Lubricants (MY/IT)", unit_cost=23.00,
        logistics_cost=4.50, lead_time_days=5.0, compliance_score=0.94, esg_score=0.83,
        min_order_qty=800, max_capacity=30000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-FUCHS", name="Fuchs Petrolub (DE)", unit_cost=28.00,
        logistics_cost=3.00, lead_time_days=3.0, compliance_score=0.96, esg_score=0.92,
        min_order_qty=500, max_capacity=25000, served_regions=["BULK", "UNIT"]),
    SupplierInput(supplier_id="OIL-MOTUL", name="Motul (FR)", unit_cost=32.00,
        logistics_cost=5.20, lead_time_days=4.5, compliance_score=0.95, esg_score=0.87,
        min_order_qty=300, max_capacity=15000, served_regions=["UNIT"]),
    SupplierInput(supplier_id="OIL-ARAL", name="Aral / BP Polska", unit_cost=22.80,
        logistics_cost=2.00, lead_time_days=2.0, compliance_score=0.93, esg_score=0.80,
        min_order_qty=700, max_capacity=42000, served_regions=["BULK", "UNIT"]),
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
    SupplierInput(supplier_id="BAT-EXIDE", name="Exide Technologies (US/PL)", unit_cost=165.00,
        logistics_cost=8.00, lead_time_days=3.0, compliance_score=0.94, esg_score=0.84,
        min_order_qty=120, max_capacity=10000, served_regions=["12V", "EFB", "AGM"]),
    SupplierInput(supplier_id="BAT-BANNER", name="Banner Batteries (AT)", unit_cost=175.00,
        logistics_cost=11.00, lead_time_days=4.0, compliance_score=0.95, esg_score=0.89,
        min_order_qty=80, max_capacity=7000, served_regions=["12V", "EFB", "AGM"]),
    SupplierInput(supplier_id="BAT-MOLL", name="Moll Batterien (DE)", unit_cost=200.00,
        logistics_cost=13.00, lead_time_days=4.5, compliance_score=0.96, esg_score=0.92,
        min_order_qty=60, max_capacity=5000, served_regions=["AGM", "EFB"]),
    SupplierInput(supplier_id="BAT-TOPLA", name="Topla (SI)", unit_cost=140.00,
        logistics_cost=7.00, lead_time_days=2.5, compliance_score=0.90, esg_score=0.78,
        min_order_qty=200, max_capacity=14000, served_regions=["12V", "EFB"]),
    SupplierInput(supplier_id="BAT-FIAMM", name="FIAMM Energy (IT)", unit_cost=155.00,
        logistics_cost=9.50, lead_time_days=5.0, compliance_score=0.93, esg_score=0.86,
        min_order_qty=100, max_capacity=9000, served_regions=["12V", "EFB", "AGM"]),
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
    SupplierInput(supplier_id="LOG-DSV", name="DSV Panalpina (DK)", unit_cost=5.20,
        logistics_cost=0.90, lead_time_days=2.0, compliance_score=0.97, esg_score=0.92,
        min_order_qty=60, max_capacity=35000, served_regions=["FTL", "LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-KUEHNE", name="Kühne + Nagel (CH)", unit_cost=6.00,
        logistics_cost=1.20, lead_time_days=2.5, compliance_score=0.98, esg_score=0.95,
        min_order_qty=40, max_capacity=25000, served_regions=["FTL", "LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-RHENUS", name="Rhenus Logistics (DE/PL)", unit_cost=4.50,
        logistics_cost=0.75, lead_time_days=1.5, compliance_score=0.95, esg_score=0.87,
        min_order_qty=100, max_capacity=40000, served_regions=["FTL", "LTL"]),
    SupplierInput(supplier_id="LOG-DPDS", name="DPD Polska (FR/PL)", unit_cost=4.00,
        logistics_cost=0.40, lead_time_days=1.0, compliance_score=0.92, esg_score=0.83,
        min_order_qty=200, max_capacity=55000, served_regions=["LTL", "CEP"]),
    SupplierInput(supplier_id="LOG-XPO", name="XPO Logistics (US/PL)", unit_cost=5.80,
        logistics_cost=1.00, lead_time_days=2.0, compliance_score=0.96, esg_score=0.90,
        min_order_qty=80, max_capacity=30000, served_regions=["FTL", "LTL"]),
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
    SupplierInput(supplier_id="PKG-DS-SMITH", name="DS Smith (UK/PL)", unit_cost=2.90,
        logistics_cost=0.45, lead_time_days=3.5, compliance_score=0.95, esg_score=0.93,
        min_order_qty=4000, max_capacity=180000, served_regions=["KARTON", "FOLIA"]),
    SupplierInput(supplier_id="PKG-SAICA", name="Saica Pack (ES/PL)", unit_cost=2.60,
        logistics_cost=0.50, lead_time_days=4.0, compliance_score=0.93, esg_score=0.90,
        min_order_qty=3500, max_capacity=140000, served_regions=["KARTON"]),
    SupplierInput(supplier_id="PKG-STORA", name="Stora Enso (FI/PL)", unit_cost=3.30,
        logistics_cost=0.60, lead_time_days=5.0, compliance_score=0.97, esg_score=0.97,
        min_order_qty=2500, max_capacity=120000, served_regions=["KARTON", "FOLIA"]),
    SupplierInput(supplier_id="PKG-BRAMBLES", name="Brambles / IFCO (AU)", unit_cost=6.20,
        logistics_cost=0.90, lead_time_days=6.0, compliance_score=0.96, esg_score=0.95,
        min_order_qty=400, max_capacity=25000, served_regions=["PALETY"]),
    SupplierInput(supplier_id="PKG-FOLPAK", name="FolPak Łódź (PL)", unit_cost=1.80,
        logistics_cost=0.20, lead_time_days=1.0, compliance_score=0.87, esg_score=0.73,
        min_order_qty=5000, max_capacity=250000, served_regions=["FOLIA"]),
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
    SupplierInput(supplier_id="MRO-STAHLW", name="Stahlwille (DE)", unit_cost=58.00,
        logistics_cost=4.50, lead_time_days=3.5, compliance_score=0.97, esg_score=0.91,
        min_order_qty=25, max_capacity=4000, served_regions=["MECH"]),
    SupplierInput(supplier_id="MRO-FACOM", name="Facom / Stanley (FR)", unit_cost=52.00,
        logistics_cost=5.00, lead_time_days=4.0, compliance_score=0.95, esg_score=0.88,
        min_order_qty=40, max_capacity=6000, served_regions=["MECH", "ELEC"]),
    SupplierInput(supplier_id="MRO-3M", name="3M Poland", unit_cost=40.00,
        logistics_cost=3.00, lead_time_days=2.0, compliance_score=0.97, esg_score=0.93,
        min_order_qty=50, max_capacity=12000, served_regions=["BHP", "MECH"]),
    SupplierInput(supplier_id="MRO-HONEYWELL", name="Honeywell Safety (US/PL)", unit_cost=75.00,
        logistics_cost=5.50, lead_time_days=4.0, compliance_score=0.98, esg_score=0.94,
        min_order_qty=15, max_capacity=4000, served_regions=["BHP", "ELEC"]),
    SupplierInput(supplier_id="MRO-WERA", name="Wera Werkzeuge (DE)", unit_cost=48.00,
        logistics_cost=3.80, lead_time_days=3.0, compliance_score=0.94, esg_score=0.87,
        min_order_qty=30, max_capacity=5000, served_regions=["MECH"]),
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
#  DEMO 9 — Opony (Tires) — DIRECT  (NEW v3.0)
# ═══════════════════════════════════════════════════════════════════

TIRE_REGION_LABELS: dict[str, str] = {
    "SUMMER": "Opony letnie",
    "WINTER": "Opony zimowe",
    "ALLSEA": "Opony całoroczne",
}

TIRE_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="TIRE-MICHELIN", name="Michelin (FR)", unit_cost=320.00,
        logistics_cost=18.00, lead_time_days=5.0, compliance_score=0.98, esg_score=0.95,
        min_order_qty=200, max_capacity=15000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="FR", payment_terms_days=60.0, is_preferred=True),
    SupplierInput(supplier_id="TIRE-CONTI", name="Continental Tires (DE)", unit_cost=290.00,
        logistics_cost=15.00, lead_time_days=4.0, compliance_score=0.97, esg_score=0.93,
        min_order_qty=300, max_capacity=20000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="DE", payment_terms_days=45.0, is_preferred=True),
    SupplierInput(supplier_id="TIRE-BRIDGE", name="Bridgestone (JP/PL)", unit_cost=305.00,
        logistics_cost=12.00, lead_time_days=4.5, compliance_score=0.96, esg_score=0.91,
        min_order_qty=250, max_capacity=18000, served_regions=["SUMMER", "WINTER"],
        region_code="JP", payment_terms_days=45.0),
    SupplierInput(supplier_id="TIRE-DEBICA", name="Dębica (Goodyear/PL)", unit_cost=195.00,
        logistics_cost=6.00, lead_time_days=2.0, compliance_score=0.92, esg_score=0.82,
        min_order_qty=500, max_capacity=25000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="PL", payment_terms_days=21.0, contract_min_allocation=0.15),
    SupplierInput(supplier_id="TIRE-NOKIAN", name="Nokian Tyres (FI)", unit_cost=340.00,
        logistics_cost=22.00, lead_time_days=7.0, compliance_score=0.95, esg_score=0.97,
        min_order_qty=150, max_capacity=10000, served_regions=["WINTER", "ALLSEA"],
        region_code="FI", payment_terms_days=60.0),
    SupplierInput(supplier_id="TIRE-PIRELLI", name="Pirelli (IT)", unit_cost=350.00,
        logistics_cost=19.00, lead_time_days=5.5, compliance_score=0.97, esg_score=0.93,
        min_order_qty=200, max_capacity=14000, served_regions=["SUMMER", "WINTER"],
        region_code="IT", payment_terms_days=45.0, is_preferred=True),
    SupplierInput(supplier_id="TIRE-HANKOOK", name="Hankook (KR/HU)", unit_cost=230.00,
        logistics_cost=10.00, lead_time_days=4.0, compliance_score=0.93, esg_score=0.85,
        min_order_qty=400, max_capacity=22000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="KR", payment_terms_days=30.0),
    SupplierInput(supplier_id="TIRE-GOODYEAR", name="Goodyear (US/LU)", unit_cost=280.00,
        logistics_cost=16.00, lead_time_days=5.0, compliance_score=0.96, esg_score=0.90,
        min_order_qty=300, max_capacity=18000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="US", payment_terms_days=45.0),
    SupplierInput(supplier_id="TIRE-KUMHO", name="Kumho Tire (KR)", unit_cost=185.00,
        logistics_cost=12.00, lead_time_days=6.0, compliance_score=0.90, esg_score=0.79,
        min_order_qty=500, max_capacity=28000, served_regions=["SUMMER", "ALLSEA"],
        region_code="KR", payment_terms_days=30.0),
    SupplierInput(supplier_id="TIRE-VREDESTEIN", name="Vredestein (Apollo/NL)", unit_cost=260.00,
        logistics_cost=14.00, lead_time_days=4.5, compliance_score=0.94, esg_score=0.88,
        min_order_qty=200, max_capacity=12000, served_regions=["SUMMER", "WINTER", "ALLSEA"],
        region_code="NL", payment_terms_days=45.0),
]

TIRE_DEMAND: list[DemandItem] = [
    DemandItem(product_id="TIRE-205-55R16-S", demand_qty=4000, destination_region="SUMMER"),
    DemandItem(product_id="TIRE-225-45R17-S", demand_qty=3000, destination_region="SUMMER"),
    DemandItem(product_id="TIRE-195-65R15-W", demand_qty=3500, destination_region="WINTER"),
    DemandItem(product_id="TIRE-205-55R16-W", demand_qty=4500, destination_region="WINTER"),
    DemandItem(product_id="TIRE-205-55R16-A", demand_qty=2500, destination_region="ALLSEA"),
]

TIRE_PRODUCT_LABELS: dict[str, str] = {
    "TIRE-205-55R16-S": "Opona letnia 205/55 R16",
    "TIRE-225-45R17-S": "Opona letnia 225/45 R17",
    "TIRE-195-65R15-W": "Opona zimowa 195/65 R15",
    "TIRE-205-55R16-W": "Opona zimowa 205/55 R16",
    "TIRE-205-55R16-A": "Opona całoroczna 205/55 R16",
}


# ═══════════════════════════════════════════════════════════════════
#  DEMO 10 — Części Nadwoziowe (Bodywork) — DIRECT  (NEW v3.0)
# ═══════════════════════════════════════════════════════════════════

BODY_REGION_LABELS: dict[str, str] = {
    "PANELS": "Blachy nadwozia",
    "LIGHTS": "Oświetlenie",
    "GLASS":  "Szyby i elementy szklane",
}

BODY_SUPPLIERS: list[SupplierInput] = [
    SupplierInput(supplier_id="BODY-BLIC", name="BLIC (PL)", unit_cost=145.00,
        logistics_cost=8.00, lead_time_days=3.0, compliance_score=0.91, esg_score=0.79,
        min_order_qty=100, max_capacity=12000, served_regions=["PANELS"],
        region_code="PL", payment_terms_days=21.0),
    SupplierInput(supplier_id="BODY-KLOK", name="Klokkerholm (DK)", unit_cost=185.00,
        logistics_cost=14.00, lead_time_days=5.0, compliance_score=0.95, esg_score=0.88,
        min_order_qty=80, max_capacity=8000, served_regions=["PANELS"],
        region_code="DK", payment_terms_days=45.0, is_preferred=True),
    SupplierInput(supplier_id="BODY-VANW", name="Van Wezel (BE)", unit_cost=165.00,
        logistics_cost=12.00, lead_time_days=4.0, compliance_score=0.93, esg_score=0.85,
        min_order_qty=120, max_capacity=10000, served_regions=["PANELS", "LIGHTS"],
        region_code="BE", payment_terms_days=30.0),
    SupplierInput(supplier_id="BODY-HELLA", name="Hella (DE)", unit_cost=220.00,
        logistics_cost=10.00, lead_time_days=4.0, compliance_score=0.98, esg_score=0.93,
        min_order_qty=60, max_capacity=6000, served_regions=["LIGHTS"],
        region_code="DE", payment_terms_days=60.0, is_preferred=True, contract_min_allocation=0.10),
    SupplierInput(supplier_id="BODY-DEPO", name="Depo Auto Lamps (TW/PL)", unit_cost=125.00,
        logistics_cost=7.00, lead_time_days=3.5, compliance_score=0.89, esg_score=0.75,
        min_order_qty=200, max_capacity=15000, served_regions=["LIGHTS"],
        region_code="TW", payment_terms_days=30.0),
    SupplierInput(supplier_id="BODY-SAINT", name="Saint-Gobain Sekurit (FR)", unit_cost=280.00,
        logistics_cost=16.00, lead_time_days=6.0, compliance_score=0.97, esg_score=0.94,
        min_order_qty=50, max_capacity=5000, served_regions=["GLASS"],
        region_code="FR", payment_terms_days=60.0, is_preferred=True),
    SupplierInput(supplier_id="BODY-PILK", name="Pilkington (UK/PL)", unit_cost=240.00,
        logistics_cost=11.00, lead_time_days=4.5, compliance_score=0.95, esg_score=0.90,
        min_order_qty=80, max_capacity=7000, served_regions=["GLASS"],
        region_code="UK", payment_terms_days=45.0),
    SupplierInput(supplier_id="BODY-TYCAR", name="TYC Automotive (TW/PL)", unit_cost=110.00,
        logistics_cost=6.50, lead_time_days=3.0, compliance_score=0.88, esg_score=0.74,
        min_order_qty=250, max_capacity=18000, served_regions=["LIGHTS", "PANELS"],
        region_code="TW", payment_terms_days=21.0),
    SupplierInput(supplier_id="BODY-MAGNETI-B", name="Magneti Marelli Body (IT)", unit_cost=195.00,
        logistics_cost=13.00, lead_time_days=5.0, compliance_score=0.96, esg_score=0.91,
        min_order_qty=70, max_capacity=6000, served_regions=["LIGHTS"],
        region_code="IT", payment_terms_days=60.0, is_preferred=True),
    SupplierInput(supplier_id="BODY-AGC", name="AGC Automotive (JP/BE)", unit_cost=260.00,
        logistics_cost=15.00, lead_time_days=6.0, compliance_score=0.96, esg_score=0.92,
        min_order_qty=60, max_capacity=5000, served_regions=["GLASS"],
        region_code="BE", payment_terms_days=45.0),
]

BODY_DEMAND: list[DemandItem] = [
    DemandItem(product_id="BODY-HOOD-VW",   demand_qty=800,  destination_region="PANELS"),
    DemandItem(product_id="BODY-FENDER-L",  demand_qty=1200, destination_region="PANELS"),
    DemandItem(product_id="BODY-BUMPER-FR", demand_qty=1500, destination_region="PANELS"),
    DemandItem(product_id="BODY-HEADL-L",   demand_qty=2000, destination_region="LIGHTS"),
    DemandItem(product_id="BODY-TAILL-R",   demand_qty=1800, destination_region="LIGHTS"),
    DemandItem(product_id="BODY-WINDSH-FR", demand_qty=1000, destination_region="GLASS"),
]

BODY_PRODUCT_LABELS: dict[str, str] = {
    "BODY-HOOD-VW":   "Maska silnika (VW Golf VII)",
    "BODY-FENDER-L":  "Błotnik przedni lewy (uniwersalny)",
    "BODY-BUMPER-FR": "Zderzak przedni (VW/Skoda)",
    "BODY-HEADL-L":   "Reflektor przedni lewy LED",
    "BODY-TAILL-R":   "Lampa tylna prawa",
    "BODY-WINDSH-FR": "Szyba czołowa (VW Golf VII)",
}


# ═══════════════════════════════════════════════════════════════════
#  V3.0 Supplier Enrichment — region_code, payment_terms, preferred
# ═══════════════════════════════════════════════════════════════════

_SUPPLIER_EXTRA: dict[str, dict] = {
    # parts
    "VND-TRW":    {"region_code": "DE", "payment_terms_days": 45.0, "is_preferred": True},
    "VND-BOSCH":  {"region_code": "DE", "payment_terms_days": 30.0, "is_preferred": True},
    "VND-LUMAG":  {"region_code": "PL", "payment_terms_days": 21.0},
    "VND-KRAFT":  {"region_code": "PL", "payment_terms_days": 30.0},
    "VND-BREMBO": {"region_code": "PL", "payment_terms_days": 60.0, "contract_min_allocation": 0.10},
    "VND-GREENF": {"region_code": "CZ", "payment_terms_days": 30.0},
    "VND-SKSLOV": {"region_code": "SK", "payment_terms_days": 45.0},
    "VND-RAPID":  {"region_code": "PL", "payment_terms_days": 14.0},
    "VND-SACHS":  {"region_code": "DE", "payment_terms_days": 45.0, "is_preferred": True},
    "VND-FEBI":   {"region_code": "DE", "payment_terms_days": 30.0},
    # oe_components
    "OE-CONTINENTAL": {"region_code": "DE", "payment_terms_days": 60.0, "is_preferred": True, "contract_min_allocation": 0.15},
    "OE-VALEO":       {"region_code": "FR", "payment_terms_days": 45.0},
    "OE-DENSO":       {"region_code": "JP", "payment_terms_days": 30.0, "is_preferred": True},
    "OE-MAGNETI":     {"region_code": "IT", "payment_terms_days": 60.0},
    "OE-AISIN":       {"region_code": "JP", "payment_terms_days": 45.0, "contract_min_allocation": 0.10},
    "OE-MAHLE":       {"region_code": "DE", "payment_terms_days": 45.0},
    "OE-BOSCH-OE":    {"region_code": "DE", "payment_terms_days": 30.0, "is_preferred": True},
    "OE-SCHAEFFLER":  {"region_code": "DE", "payment_terms_days": 60.0},
    "OE-NGK":         {"region_code": "JP", "payment_terms_days": 30.0},
    "OE-HELLA-OE":    {"region_code": "DE", "payment_terms_days": 45.0},
    # oils
    "OIL-CASTROL": {"region_code": "UK", "payment_terms_days": 45.0, "is_preferred": True},
    "OIL-MOBIL":   {"region_code": "US", "payment_terms_days": 30.0},
    "OIL-ORLEN":   {"region_code": "PL", "payment_terms_days": 14.0, "contract_min_allocation": 0.20},
    "OIL-TOTAL":   {"region_code": "FR", "payment_terms_days": 45.0},
    "OIL-LOTOS":   {"region_code": "PL", "payment_terms_days": 14.0},
    "OIL-SHELL":   {"region_code": "NL", "payment_terms_days": 45.0, "is_preferred": True},
    "OIL-PETRONAS": {"region_code": "MY", "payment_terms_days": 30.0},
    "OIL-FUCHS":   {"region_code": "DE", "payment_terms_days": 30.0},
    "OIL-MOTUL":   {"region_code": "FR", "payment_terms_days": 45.0},
    "OIL-ARAL":    {"region_code": "DE", "payment_terms_days": 21.0},
    # batteries
    "BAT-VARTA":  {"region_code": "DE", "payment_terms_days": 45.0, "is_preferred": True},
    "BAT-BOSCH":  {"region_code": "DE", "payment_terms_days": 30.0},
    "BAT-CENTRA": {"region_code": "PL", "payment_terms_days": 21.0, "contract_min_allocation": 0.15},
    "BAT-YUASA":  {"region_code": "JP", "payment_terms_days": 60.0},
    "BAT-JENOX":  {"region_code": "PL", "payment_terms_days": 14.0},
    "BAT-EXIDE":  {"region_code": "US", "payment_terms_days": 30.0},
    "BAT-BANNER": {"region_code": "AT", "payment_terms_days": 45.0},
    "BAT-MOLL":   {"region_code": "DE", "payment_terms_days": 60.0, "is_preferred": True},
    "BAT-TOPLA":  {"region_code": "SI", "payment_terms_days": 21.0},
    "BAT-FIAMM":  {"region_code": "IT", "payment_terms_days": 45.0},
    # it_services
    "IT-ACCENTURE": {"region_code": "PL", "payment_terms_days": 60.0, "is_preferred": True, "contract_min_allocation": 0.20},
    "IT-CODETE":    {"region_code": "PL", "payment_terms_days": 30.0},
    "IT-SOFTSERVE": {"region_code": "UA", "payment_terms_days": 30.0},
    "IT-NETGURU":   {"region_code": "PL", "payment_terms_days": 21.0},
    "IT-DELOITTE":  {"region_code": "US", "payment_terms_days": 90.0, "is_preferred": True},
    "IT-MLOPS":     {"region_code": "PL", "payment_terms_days": 14.0},
    "IT-ATOS":      {"region_code": "FR", "payment_terms_days": 60.0},
    "IT-EPAM":      {"region_code": "PL", "payment_terms_days": 30.0},
    "IT-SYTAC":     {"region_code": "PL", "payment_terms_days": 21.0},
    "IT-CAPGEMINI": {"region_code": "FR", "payment_terms_days": 90.0, "is_preferred": True},
    # logistics
    "LOG-RABEN":  {"region_code": "PL", "payment_terms_days": 30.0, "is_preferred": True},
    "LOG-GEIS":   {"region_code": "DE", "payment_terms_days": 45.0},
    "LOG-DHL":    {"region_code": "DE", "payment_terms_days": 30.0, "contract_min_allocation": 0.10},
    "LOG-POCZTA": {"region_code": "PL", "payment_terms_days": 14.0},
    "LOG-PEKAES": {"region_code": "PL", "payment_terms_days": 21.0},
    "LOG-DSV":    {"region_code": "DK", "payment_terms_days": 45.0},
    "LOG-KUEHNE": {"region_code": "CH", "payment_terms_days": 60.0, "is_preferred": True},
    "LOG-RHENUS": {"region_code": "DE", "payment_terms_days": 30.0},
    "LOG-DPDS":   {"region_code": "FR", "payment_terms_days": 21.0},
    "LOG-XPO":    {"region_code": "US", "payment_terms_days": 45.0},
    # packaging
    "PKG-MONDI":   {"region_code": "AT", "payment_terms_days": 45.0, "is_preferred": True},
    "PKG-SMURFIT": {"region_code": "IE", "payment_terms_days": 60.0},
    "PKG-AGATA":   {"region_code": "PL", "payment_terms_days": 21.0},
    "PKG-CHEP":    {"region_code": "UK", "payment_terms_days": 30.0, "contract_min_allocation": 0.15},
    "PKG-EUROPAL": {"region_code": "PL", "payment_terms_days": 14.0},
    "PKG-DS-SMITH": {"region_code": "UK", "payment_terms_days": 45.0},
    "PKG-SAICA":    {"region_code": "ES", "payment_terms_days": 30.0},
    "PKG-STORA":    {"region_code": "FI", "payment_terms_days": 60.0, "is_preferred": True},
    "PKG-BRAMBLES": {"region_code": "AU", "payment_terms_days": 45.0},
    "PKG-FOLPAK":   {"region_code": "PL", "payment_terms_days": 14.0},
    # mro / facility_management
    "MRO-WUERTH":   {"region_code": "DE", "payment_terms_days": 30.0, "is_preferred": True},
    "MRO-HILTI":    {"region_code": "LI", "payment_terms_days": 45.0},
    "MRO-GRAINGER": {"region_code": "UK", "payment_terms_days": 60.0},
    "MRO-DRAGER":   {"region_code": "DE", "payment_terms_days": 30.0, "contract_min_allocation": 0.10},
    "MRO-TOOLS24":  {"region_code": "PL", "payment_terms_days": 14.0},
    "MRO-STAHLW":   {"region_code": "DE", "payment_terms_days": 45.0},
    "MRO-FACOM":    {"region_code": "FR", "payment_terms_days": 30.0},
    "MRO-3M":       {"region_code": "US", "payment_terms_days": 30.0, "is_preferred": True},
    "MRO-HONEYWELL": {"region_code": "US", "payment_terms_days": 45.0},
    "MRO-WERA":     {"region_code": "DE", "payment_terms_days": 30.0},
}


def _enrich_suppliers() -> None:
    """Apply v3.0 extra fields to existing suppliers."""
    import itertools
    all_lists = [
        DEMO_SUPPLIERS, IT_DEMO_SUPPLIERS, OE_SUPPLIERS, OIL_SUPPLIERS,
        BAT_SUPPLIERS, LOG_SUPPLIERS, PKG_SUPPLIERS, MRO_SUPPLIERS,
    ]
    for s in itertools.chain(*all_lists):
        extra = _SUPPLIER_EXTRA.get(s.supplier_id)
        if extra:
            for k, v in extra.items():
                object.__setattr__(s, k, v)


_enrich_suppliers()


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
    # DIRECT domains
    "parts":               {"suppliers": DEMO_SUPPLIERS,    "demand": DEMO_DEMAND,    "products": PRODUCT_LABELS,      "regions": REGION_LABELS},
    "oe_components":       {"suppliers": OE_SUPPLIERS,      "demand": OE_DEMAND,      "products": OE_PRODUCT_LABELS,   "regions": OE_REGION_LABELS},
    "oils":                {"suppliers": OIL_SUPPLIERS,      "demand": OIL_DEMAND,     "products": OIL_PRODUCT_LABELS,  "regions": OIL_REGION_LABELS},
    "batteries":           {"suppliers": BAT_SUPPLIERS,      "demand": BAT_DEMAND,     "products": BAT_PRODUCT_LABELS,  "regions": BAT_REGION_LABELS},
    "tires":               {"suppliers": TIRE_SUPPLIERS,     "demand": TIRE_DEMAND,    "products": TIRE_PRODUCT_LABELS, "regions": TIRE_REGION_LABELS},
    "bodywork":            {"suppliers": BODY_SUPPLIERS,     "demand": BODY_DEMAND,    "products": BODY_PRODUCT_LABELS, "regions": BODY_REGION_LABELS},
    # INDIRECT domains
    "it_services":         {"suppliers": IT_DEMO_SUPPLIERS,  "demand": IT_DEMO_DEMAND, "products": IT_PRODUCT_LABELS,   "regions": IT_REGION_LABELS},
    "logistics":           {"suppliers": LOG_SUPPLIERS,      "demand": LOG_DEMAND,     "products": LOG_PRODUCT_LABELS,  "regions": LOG_REGION_LABELS},
    "packaging":           {"suppliers": PKG_SUPPLIERS,      "demand": PKG_DEMAND,     "products": PKG_PRODUCT_LABELS,  "regions": PKG_REGION_LABELS},
    "facility_management": {"suppliers": MRO_SUPPLIERS,      "demand": MRO_DEMAND,     "products": MRO_PRODUCT_LABELS,  "regions": MRO_REGION_LABELS},
    # backward-compat aliases
    "mro":                 {"suppliers": MRO_SUPPLIERS,      "demand": MRO_DEMAND,     "products": MRO_PRODUCT_LABELS,  "regions": MRO_REGION_LABELS},
}


def get_domain_data(domain: str) -> dict:
    """Return suppliers, demand, products, regions for any registered domain."""
    if domain not in DOMAIN_DATA:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(DOMAIN_DATA.keys())}")
    return DOMAIN_DATA[domain]


# ═══════════════════════════════════════════════════════════════════
#  SUBDOMAIN_DATA — v3.0 granular access
# ═══════════════════════════════════════════════════════════════════

def _build_subdomain(domain_suppliers, domain_demand, domain_products, domain_regions,
                     supplier_ids=None, product_ids=None, region_keys=None):
    """Build subdomain data by filtering domain-level data."""
    sups = [s for s in domain_suppliers if supplier_ids is None or s.supplier_id in supplier_ids]
    prods = {k: v for k, v in domain_products.items() if product_ids is None or k in product_ids}
    dem = [d for d in domain_demand if product_ids is None or d.product_id in product_ids]
    regs = {k: v for k, v in domain_regions.items() if region_keys is None or k in region_keys}
    return {"suppliers": sups, "demand": dem, "products": prods, "regions": regs}


SUBDOMAIN_DATA: dict[str, dict[str, dict]] = {
    "parts": {
        "brake_systems": _build_subdomain(
            DEMO_SUPPLIERS, DEMO_DEMAND, PRODUCT_LABELS, REGION_LABELS,
            supplier_ids={"VND-TRW", "VND-BREMBO", "VND-LUMAG", "VND-SACHS"},
            product_ids={"BRK-PAD-0041", "BRK-DSC-0087"}),
        "filters": _build_subdomain(
            DEMO_SUPPLIERS, DEMO_DEMAND, PRODUCT_LABELS, REGION_LABELS,
            supplier_ids={"VND-BOSCH", "VND-GREENF", "VND-FEBI"},
            product_ids={"OIL-FLT-1022", "AIR-FLT-1055"}),
        "suspension": _build_subdomain(
            DEMO_SUPPLIERS, DEMO_DEMAND, PRODUCT_LABELS, REGION_LABELS,
            supplier_ids={"VND-KRAFT", "VND-SKSLOV", "VND-RAPID", "VND-SACHS", "VND-FEBI"},
            product_ids={"SHK-ABS-9020", "ABS-SNR-9001", "ENG-MNT-5050"}),
    },
    "oe_components": {
        "engine_parts": _build_subdomain(
            OE_SUPPLIERS, OE_DEMAND, OE_PRODUCT_LABELS, OE_REGION_LABELS,
            supplier_ids={"OE-CONTINENTAL", "OE-VALEO", "OE-MAHLE", "OE-BOSCH-OE"},
            product_ids={"OE-TURBO-VNT", "OE-INJ-CR"}),
        "electrical": _build_subdomain(
            OE_SUPPLIERS, OE_DEMAND, OE_PRODUCT_LABELS, OE_REGION_LABELS,
            supplier_ids={"OE-DENSO", "OE-MAGNETI", "OE-HELLA-OE", "OE-NGK"},
            product_ids={"OE-ALTR-220", "OE-STRTR-110"}),
        "transmission": _build_subdomain(
            OE_SUPPLIERS, OE_DEMAND, OE_PRODUCT_LABELS, OE_REGION_LABELS,
            supplier_ids={"OE-AISIN", "OE-DENSO", "OE-SCHAEFFLER"},
            product_ids={"OE-COMP-AC"}),
    },
    "oils": {
        "engine_oils": _build_subdomain(
            OIL_SUPPLIERS, OIL_DEMAND, OIL_PRODUCT_LABELS, OIL_REGION_LABELS,
            supplier_ids={"OIL-CASTROL", "OIL-MOBIL", "OIL-ORLEN", "OIL-SHELL", "OIL-FUCHS", "OIL-MOTUL"},
            product_ids={"OIL-5W30-SYN", "OIL-5W40-SYN"}),
        "transmission_fluids": _build_subdomain(
            OIL_SUPPLIERS, OIL_DEMAND, OIL_PRODUCT_LABELS, OIL_REGION_LABELS,
            supplier_ids={"OIL-TOTAL", "OIL-LOTOS", "OIL-ORLEN", "OIL-PETRONAS", "OIL-ARAL"},
            product_ids={"OIL-ATF-DIII", "OIL-BRAKE-DOT4", "OIL-COOL-G12"}),
    },
    "batteries": {
        "starter_batteries": _build_subdomain(
            BAT_SUPPLIERS, BAT_DEMAND, BAT_PRODUCT_LABELS, BAT_REGION_LABELS,
            supplier_ids={"BAT-VARTA", "BAT-CENTRA", "BAT-JENOX", "BAT-EXIDE", "BAT-TOPLA"},
            product_ids={"BAT-12V-60AH", "BAT-12V-74AH"}),
        "agm_efb": _build_subdomain(
            BAT_SUPPLIERS, BAT_DEMAND, BAT_PRODUCT_LABELS, BAT_REGION_LABELS,
            supplier_ids={"BAT-VARTA", "BAT-BOSCH", "BAT-YUASA", "BAT-BANNER", "BAT-MOLL", "BAT-FIAMM"},
            product_ids={"BAT-EFB-70AH", "BAT-AGM-80AH", "BAT-AGM-95AH"}),
    },
    "tires": {
        "summer_tires": _build_subdomain(
            TIRE_SUPPLIERS, TIRE_DEMAND, TIRE_PRODUCT_LABELS, TIRE_REGION_LABELS,
            supplier_ids={"TIRE-MICHELIN", "TIRE-CONTI", "TIRE-BRIDGE", "TIRE-DEBICA", "TIRE-PIRELLI", "TIRE-HANKOOK", "TIRE-KUMHO"},
            product_ids={"TIRE-205-55R16-S", "TIRE-225-45R17-S"},
            region_keys={"SUMMER"}),
        "winter_tires": _build_subdomain(
            TIRE_SUPPLIERS, TIRE_DEMAND, TIRE_PRODUCT_LABELS, TIRE_REGION_LABELS,
            supplier_ids={"TIRE-NOKIAN", "TIRE-MICHELIN", "TIRE-CONTI", "TIRE-BRIDGE", "TIRE-PIRELLI", "TIRE-GOODYEAR", "TIRE-VREDESTEIN"},
            product_ids={"TIRE-195-65R15-W", "TIRE-205-55R16-W"},
            region_keys={"WINTER"}),
        "all_season": _build_subdomain(
            TIRE_SUPPLIERS, TIRE_DEMAND, TIRE_PRODUCT_LABELS, TIRE_REGION_LABELS,
            supplier_ids={"TIRE-CONTI", "TIRE-MICHELIN", "TIRE-DEBICA", "TIRE-HANKOOK", "TIRE-GOODYEAR", "TIRE-VREDESTEIN"},
            product_ids={"TIRE-205-55R16-A"},
            region_keys={"ALLSEA"}),
    },
    "bodywork": {
        "body_panels": _build_subdomain(
            BODY_SUPPLIERS, BODY_DEMAND, BODY_PRODUCT_LABELS, BODY_REGION_LABELS,
            supplier_ids={"BODY-BLIC", "BODY-KLOK", "BODY-VANW", "BODY-TYCAR"},
            product_ids={"BODY-HOOD-VW", "BODY-FENDER-L", "BODY-BUMPER-FR"},
            region_keys={"PANELS"}),
        "lighting": _build_subdomain(
            BODY_SUPPLIERS, BODY_DEMAND, BODY_PRODUCT_LABELS, BODY_REGION_LABELS,
            supplier_ids={"BODY-HELLA", "BODY-DEPO", "BODY-VANW", "BODY-TYCAR", "BODY-MAGNETI-B"},
            product_ids={"BODY-HEADL-L", "BODY-TAILL-R"},
            region_keys={"LIGHTS"}),
        "glass": _build_subdomain(
            BODY_SUPPLIERS, BODY_DEMAND, BODY_PRODUCT_LABELS, BODY_REGION_LABELS,
            supplier_ids={"BODY-SAINT", "BODY-PILK", "BODY-AGC"},
            product_ids={"BODY-WINDSH-FR"},
            region_keys={"GLASS"}),
    },
    "it_services": {
        "development": _build_subdomain(
            IT_DEMO_SUPPLIERS, IT_DEMO_DEMAND, IT_PRODUCT_LABELS, IT_REGION_LABELS,
            supplier_ids={"IT-ACCENTURE", "IT-CODETE", "IT-SOFTSERVE", "IT-EPAM", "IT-SYTAC"},
            product_ids={"PRJ-ERP-MIGR", "PRJ-MICROSERV"},
            region_keys={"JAVA"}),
        "cloud_infra": _build_subdomain(
            IT_DEMO_SUPPLIERS, IT_DEMO_DEMAND, IT_PRODUCT_LABELS, IT_REGION_LABELS,
            supplier_ids={"IT-NETGURU", "IT-DELOITTE", "IT-CODETE", "IT-ATOS", "IT-CAPGEMINI"},
            product_ids={"PRJ-K8S-INFRA", "PRJ-CI-CD"},
            region_keys={"CLOUD"}),
        "data_analytics": _build_subdomain(
            IT_DEMO_SUPPLIERS, IT_DEMO_DEMAND, IT_PRODUCT_LABELS, IT_REGION_LABELS,
            supplier_ids={"IT-MLOPS", "IT-SOFTSERVE", "IT-DELOITTE", "IT-EPAM", "IT-ATOS"},
            product_ids={"PRJ-DWH-BUILD"},
            region_keys={"DATA"}),
    },
    "logistics": {
        "domestic": _build_subdomain(
            LOG_SUPPLIERS, LOG_DEMAND, LOG_PRODUCT_LABELS, LOG_REGION_LABELS,
            supplier_ids={"LOG-RABEN", "LOG-PEKAES", "LOG-POCZTA", "LOG-DPDS", "LOG-RHENUS"},
            product_ids={"LOG-LTL-DAILY"},
            region_keys={"LTL"}),
        "international": _build_subdomain(
            LOG_SUPPLIERS, LOG_DEMAND, LOG_PRODUCT_LABELS, LOG_REGION_LABELS,
            supplier_ids={"LOG-GEIS", "LOG-DHL", "LOG-RABEN", "LOG-DSV", "LOG-KUEHNE", "LOG-XPO"},
            product_ids={"LOG-FTL-WEST", "LOG-FTL-SOUTH"},
            region_keys={"FTL"}),
        "last_mile": _build_subdomain(
            LOG_SUPPLIERS, LOG_DEMAND, LOG_PRODUCT_LABELS, LOG_REGION_LABELS,
            supplier_ids={"LOG-DHL", "LOG-POCZTA", "LOG-GEIS", "LOG-DPDS", "LOG-DSV"},
            product_ids={"LOG-CEP-EXPRESS"},
            region_keys={"CEP"}),
    },
    "packaging": {
        "cardboard": _build_subdomain(
            PKG_SUPPLIERS, PKG_DEMAND, PKG_PRODUCT_LABELS, PKG_REGION_LABELS,
            supplier_ids={"PKG-MONDI", "PKG-SMURFIT", "PKG-AGATA", "PKG-DS-SMITH", "PKG-SAICA", "PKG-STORA"},
            product_ids={"PKG-BOX-A4", "PKG-BOX-HEAVY"},
            region_keys={"KARTON"}),
        "plastics": _build_subdomain(
            PKG_SUPPLIERS, PKG_DEMAND, PKG_PRODUCT_LABELS, PKG_REGION_LABELS,
            supplier_ids={"PKG-AGATA", "PKG-CHEP", "PKG-EUROPAL", "PKG-BRAMBLES", "PKG-FOLPAK"},
            product_ids={"PKG-STRETCH", "PKG-EUR-PALET"},
            region_keys={"FOLIA", "PALETY"}),
    },
    "facility_management": {
        "maintenance": _build_subdomain(
            MRO_SUPPLIERS, MRO_DEMAND, MRO_PRODUCT_LABELS, MRO_REGION_LABELS,
            supplier_ids={"MRO-WUERTH", "MRO-HILTI", "MRO-TOOLS24", "MRO-STAHLW", "MRO-FACOM", "MRO-WERA"},
            product_ids={"MRO-KLUCZ-SET", "MRO-WIERTLA", "MRO-CZUJNIK"},
            region_keys={"MECH", "ELEC"}),
        "safety_equipment": _build_subdomain(
            MRO_SUPPLIERS, MRO_DEMAND, MRO_PRODUCT_LABELS, MRO_REGION_LABELS,
            supplier_ids={"MRO-DRAGER", "MRO-GRAINGER", "MRO-WUERTH", "MRO-3M", "MRO-HONEYWELL"},
            product_ids={"MRO-KASK-BHP", "MRO-REKAW-BHP"},
            region_keys={"BHP"}),
        "cleaning": {
            "suppliers": [
                SupplierInput(supplier_id="CLN-KARCHER", name="Kärcher (DE)", unit_cost=35.00,
                    logistics_cost=4.00, lead_time_days=3.0, compliance_score=0.96, esg_score=0.91,
                    min_order_qty=20, max_capacity=3000, served_regions=["CLEAN"],
                    region_code="DE", payment_terms_days=30.0, is_preferred=True),
                SupplierInput(supplier_id="CLN-HENKEL", name="Henkel Cleaning (DE)", unit_cost=18.00,
                    logistics_cost=2.50, lead_time_days=2.0, compliance_score=0.94, esg_score=0.88,
                    min_order_qty=100, max_capacity=8000, served_regions=["CLEAN"],
                    region_code="DE", payment_terms_days=45.0),
                SupplierInput(supplier_id="CLN-VOIGT", name="Voigt Chemia (PL)", unit_cost=12.00,
                    logistics_cost=1.50, lead_time_days=1.0, compliance_score=0.89, esg_score=0.76,
                    min_order_qty=200, max_capacity=15000, served_regions=["CLEAN"],
                    region_code="PL", payment_terms_days=14.0),
            ],
            "demand": [
                DemandItem(product_id="CLN-FLOOR-IND", demand_qty=500, destination_region="CLEAN"),
                DemandItem(product_id="CLN-DEGREASER", demand_qty=800, destination_region="CLEAN"),
            ],
            "products": {
                "CLN-FLOOR-IND": "Środek do mycia podłóg przemysłowych",
                "CLN-DEGREASER": "Odtłuszczacz przemysłowy",
            },
            "regions": {"CLEAN": "Środki czystości"},
        },
    },
}


def get_subdomain_data(domain: str, subdomain: str) -> dict:
    """Return suppliers, demand, products, regions for a specific subdomain."""
    canonical = "facility_management" if domain == "mro" else domain
    if canonical not in SUBDOMAIN_DATA:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(SUBDOMAIN_DATA.keys())}")
    subs = SUBDOMAIN_DATA[canonical]
    if subdomain not in subs:
        raise ValueError(f"Unknown subdomain: {subdomain} for domain {domain}. Available: {list(subs.keys())}")
    return subs[subdomain]


def get_domain_subdomains(domain: str) -> list[str]:
    """Return list of subdomain names for a given domain."""
    canonical = "facility_management" if domain == "mro" else domain
    if canonical not in SUBDOMAIN_DATA:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(SUBDOMAIN_DATA.keys())}")
    return list(SUBDOMAIN_DATA[canonical].keys())


def aggregate_domain_from_subdomains(domain: str) -> dict:
    """Aggregate all subdomains into a single domain-level dataset."""
    canonical = "facility_management" if domain == "mro" else domain
    if canonical not in SUBDOMAIN_DATA:
        raise ValueError(f"Unknown domain: {domain}")
    all_suppliers: list = []
    all_demand: list = []
    all_products: dict = {}
    all_regions: dict = {}
    seen_ids: set[str] = set()
    for sub_data in SUBDOMAIN_DATA[canonical].values():
        for s in sub_data["suppliers"]:
            if s.supplier_id not in seen_ids:
                all_suppliers.append(s)
                seen_ids.add(s.supplier_id)
        all_demand.extend(sub_data["demand"])
        all_products.update(sub_data["products"])
        all_regions.update(sub_data["regions"])
    return {"suppliers": all_suppliers, "demand": all_demand, "products": all_products, "regions": all_regions}


# ---------------------------------------------------------------------------
# Process Mining — Demo P2P (Procure-to-Pay) Event Log
# ---------------------------------------------------------------------------
# Realistic INTERCARS P2P process with 10 cases, covering:
#   happy path, budget rejection, 3-way match loop, express path, audit hold

P2P_DEMO_EVENTS: list[dict] = [
    # ── REQ-001  Happy path (standard) ───────────────────────────────
    {"case_id": "REQ-001", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-01T10:00:00", "resource": "Jan Kowalski",   "cost": 0},
    {"case_id": "REQ-001", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-01T11:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-001", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-01T14:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-001", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-02T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-001", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-02T15:00:00", "resource": "AutoParts Kraków","cost": 0},
    {"case_id": "REQ-001", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-05T10:00:00", "resource": "Magazyn Główny", "cost": 12500},
    {"case_id": "REQ-001", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-06T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-001", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-06T14:00:00", "resource": "System SAP",     "cost": 12500},
    {"case_id": "REQ-001", "activity": "Płatność",                    "timestamp": "2026-03-10T08:00:00", "resource": "Bank PKO",       "cost": 12500},

    # ── REQ-002  Budget rejection → re-submit ────────────────────────
    {"case_id": "REQ-002", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-03T08:00:00", "resource": "Piotr Wiśniewski","cost": 0},
    {"case_id": "REQ-002", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-03T08:45:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-002", "activity": "Odrzucenie - Brak Budżetu",   "timestamp": "2026-03-03T09:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-002", "activity": "Korekta Zapotrzebowania",     "timestamp": "2026-03-04T10:00:00", "resource": "Piotr Wiśniewski","cost": 0},
    {"case_id": "REQ-002", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-04T11:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-002", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-04T14:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-002", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-05T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-002", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-05T16:00:00", "resource": "Bosch Automotive","cost": 0},
    {"case_id": "REQ-002", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-09T11:00:00", "resource": "Magazyn Główny", "cost": 8700},
    {"case_id": "REQ-002", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-10T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-002", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-10T15:00:00", "resource": "System SAP",     "cost": 8700},
    {"case_id": "REQ-002", "activity": "Płatność",                    "timestamp": "2026-03-14T08:00:00", "resource": "Bank PKO",       "cost": 8700},

    # ── REQ-003  3-way match failure → re-verify ─────────────────────
    {"case_id": "REQ-003", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-02T09:00:00", "resource": "Marta Zielińska","cost": 0},
    {"case_id": "REQ-003", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-02T10:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-003", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-02T13:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-003", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-03T08:30:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-003", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-03T14:00:00", "resource": "Continental PL", "cost": 0},
    {"case_id": "REQ-003", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-07T10:00:00", "resource": "Magazyn Główny", "cost": 21000},
    {"case_id": "REQ-003", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-08T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-003", "activity": "Niezgodność 3-Way Match",     "timestamp": "2026-03-08T11:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-003", "activity": "Korekta Faktury",             "timestamp": "2026-03-09T14:00:00", "resource": "Continental PL", "cost": 0},
    {"case_id": "REQ-003", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-10T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-003", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-10T14:00:00", "resource": "System SAP",     "cost": 19800},
    {"case_id": "REQ-003", "activity": "Płatność",                    "timestamp": "2026-03-15T08:00:00", "resource": "Bank PKO",       "cost": 19800},

    # ── REQ-004  Express / urgent path ───────────────────────────────
    {"case_id": "REQ-004", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-04T07:30:00", "resource": "Tomasz Krawczyk","cost": 0},
    {"case_id": "REQ-004", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-04T07:45:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-004", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-04T08:00:00", "resource": "Dyrektor Ops",   "cost": 0},
    {"case_id": "REQ-004", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-04T08:30:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-004", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-04T09:00:00", "resource": "Varta Polska",   "cost": 0},
    {"case_id": "REQ-004", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-04T16:00:00", "resource": "Magazyn Główny", "cost": 4200},
    {"case_id": "REQ-004", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-05T08:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-004", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-05T10:00:00", "resource": "System SAP",     "cost": 4200},
    {"case_id": "REQ-004", "activity": "Płatność",                    "timestamp": "2026-03-06T08:00:00", "resource": "Bank PKO",       "cost": 4200},

    # ── REQ-005  Happy path (standard) ───────────────────────────────
    {"case_id": "REQ-005", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-05T09:00:00", "resource": "Ewa Szymańska",  "cost": 0},
    {"case_id": "REQ-005", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-05T10:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-005", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-05T14:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-005", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-06T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-005", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-06T14:00:00", "resource": "Castrol Polska", "cost": 0},
    {"case_id": "REQ-005", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-10T10:00:00", "resource": "Magazyn Główny", "cost": 15600},
    {"case_id": "REQ-005", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-11T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-005", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-11T14:00:00", "resource": "System SAP",     "cost": 15600},
    {"case_id": "REQ-005", "activity": "Płatność",                    "timestamp": "2026-03-17T08:00:00", "resource": "Bank PKO",       "cost": 15600},

    # ── REQ-006  Audit hold ──────────────────────────────────────────
    {"case_id": "REQ-006", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-06T08:00:00", "resource": "Jan Kowalski",   "cost": 0},
    {"case_id": "REQ-006", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-06T09:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-006", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-06T12:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-006", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-07T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-006", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-07T15:00:00", "resource": "Würth Polska",   "cost": 0},
    {"case_id": "REQ-006", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-11T10:00:00", "resource": "Magazyn Główny", "cost": 6800},
    {"case_id": "REQ-006", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-12T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-006", "activity": "Wstrzymanie - Audyt",         "timestamp": "2026-03-12T14:00:00", "resource": "Audyt Wewnętrzny","cost": 0},
    {"case_id": "REQ-006", "activity": "Zatwierdzenie Audytu",        "timestamp": "2026-03-14T10:00:00", "resource": "Audyt Wewnętrzny","cost": 0},
    {"case_id": "REQ-006", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-14T14:00:00", "resource": "System SAP",     "cost": 6800},
    {"case_id": "REQ-006", "activity": "Płatność",                    "timestamp": "2026-03-18T08:00:00", "resource": "Bank PKO",       "cost": 6800},

    # ── REQ-007  Happy path (large order) ────────────────────────────
    {"case_id": "REQ-007", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-07T09:00:00", "resource": "Marta Zielińska","cost": 0},
    {"case_id": "REQ-007", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-07T10:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-007", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-07T15:00:00", "resource": "Dyrektor Ops",   "cost": 0},
    {"case_id": "REQ-007", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-08T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-007", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-08T16:00:00", "resource": "Raben Logistics","cost": 0},
    {"case_id": "REQ-007", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-12T10:00:00", "resource": "Magazyn Główny", "cost": 34500},
    {"case_id": "REQ-007", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-13T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-007", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-13T14:00:00", "resource": "System SAP",     "cost": 34500},
    {"case_id": "REQ-007", "activity": "Płatność",                    "timestamp": "2026-03-19T08:00:00", "resource": "Bank PKO",       "cost": 34500},

    # ── REQ-008  Double rejection → escalation ───────────────────────
    {"case_id": "REQ-008", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-08T08:00:00", "resource": "Tomasz Krawczyk","cost": 0},
    {"case_id": "REQ-008", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-08T08:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-008", "activity": "Odrzucenie - Brak Budżetu",   "timestamp": "2026-03-08T09:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-008", "activity": "Korekta Zapotrzebowania",     "timestamp": "2026-03-09T10:00:00", "resource": "Tomasz Krawczyk","cost": 0},
    {"case_id": "REQ-008", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-09T11:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-008", "activity": "Odrzucenie - Brak Budżetu",   "timestamp": "2026-03-09T11:30:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-008", "activity": "Eskalacja do Dyrektora",      "timestamp": "2026-03-10T09:00:00", "resource": "Tomasz Krawczyk","cost": 0},
    {"case_id": "REQ-008", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-10T14:00:00", "resource": "Dyrektor Ops",   "cost": 0},
    {"case_id": "REQ-008", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-11T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-008", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-11T14:00:00", "resource": "DHL Supply Chain","cost": 0},
    {"case_id": "REQ-008", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-15T10:00:00", "resource": "Magazyn Główny", "cost": 11200},
    {"case_id": "REQ-008", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-16T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-008", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-16T14:00:00", "resource": "System SAP",     "cost": 11200},
    {"case_id": "REQ-008", "activity": "Płatność",                    "timestamp": "2026-03-20T08:00:00", "resource": "Bank PKO",       "cost": 11200},

    # ── REQ-009  Happy path (IT services) ────────────────────────────
    {"case_id": "REQ-009", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-10T09:00:00", "resource": "Ewa Szymańska",  "cost": 0},
    {"case_id": "REQ-009", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-10T10:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-009", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-10T14:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-009", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-11T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-009", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-11T11:00:00", "resource": "Comarch ERP",    "cost": 0},
    {"case_id": "REQ-009", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-14T10:00:00", "resource": "Dział IT",       "cost": 28000},
    {"case_id": "REQ-009", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-15T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-009", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-15T14:00:00", "resource": "System SAP",     "cost": 28000},
    {"case_id": "REQ-009", "activity": "Płatność",                    "timestamp": "2026-03-21T08:00:00", "resource": "Bank PKO",       "cost": 28000},

    # ── REQ-010  Partial delivery → split GR ─────────────────────────
    {"case_id": "REQ-010", "activity": "Utworzenie Zapotrzebowania",   "timestamp": "2026-03-11T08:00:00", "resource": "Piotr Wiśniewski","cost": 0},
    {"case_id": "REQ-010", "activity": "Sprawdzenie Budżetu",         "timestamp": "2026-03-11T09:00:00", "resource": "System SAP",     "cost": 0},
    {"case_id": "REQ-010", "activity": "Zatwierdzenie Zapotrzebowania","timestamp": "2026-03-11T13:00:00", "resource": "Anna Nowak",     "cost": 0},
    {"case_id": "REQ-010", "activity": "Wystawienie Zamówienia (PO)",  "timestamp": "2026-03-12T09:00:00", "resource": "Dział Zakupów",  "cost": 0},
    {"case_id": "REQ-010", "activity": "Potwierdzenie Dostawcy",      "timestamp": "2026-03-12T15:00:00", "resource": "Mondi Packaging", "cost": 0},
    {"case_id": "REQ-010", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-16T10:00:00", "resource": "Magazyn Główny", "cost": 5400},
    {"case_id": "REQ-010", "activity": "Częściowa Dostawa",           "timestamp": "2026-03-16T11:00:00", "resource": "Magazyn Główny", "cost": 0},
    {"case_id": "REQ-010", "activity": "Przyjęcie Towaru (GR)",       "timestamp": "2026-03-19T10:00:00", "resource": "Magazyn Główny", "cost": 3200},
    {"case_id": "REQ-010", "activity": "Weryfikacja Faktury",         "timestamp": "2026-03-20T09:00:00", "resource": "Dział Finansowy","cost": 0},
    {"case_id": "REQ-010", "activity": "Zaksięgowanie Faktury",       "timestamp": "2026-03-20T14:00:00", "resource": "System SAP",     "cost": 8600},
    {"case_id": "REQ-010", "activity": "Płatność",                    "timestamp": "2026-03-24T08:00:00", "resource": "Bank PKO",       "cost": 8600},
]


def get_p2p_demo_events() -> list[dict]:
    """Return demo P2P event log for Process Mining."""
    return P2P_DEMO_EVENTS
