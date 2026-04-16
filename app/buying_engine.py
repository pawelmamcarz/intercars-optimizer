"""
Optimized Buying Engine — guided buying catalog + cart rules + order lifecycle.

Inspired by SAP Ariba Guided Buying, adapted for Flow Procurement.
Catalog items map to optimizer domains → checkout runs multi-domain optimization.
Order lifecycle: draft → pending_approval → approved → po_generated → confirmed → delivered.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

# ── Catalog ────────────────────────────────────────────────────────────────

CATEGORIES = [
    # ── Direct (automotive) ──
    {"id": "parts",         "label": "Części zamienne",     "icon": "🔧", "group": "direct"},
    {"id": "oe_components", "label": "Komponenty OE",       "icon": "⚙️", "group": "direct"},
    {"id": "oils",          "label": "Oleje i płyny",       "icon": "🛢️", "group": "direct"},
    {"id": "batteries",     "label": "Akumulatory",         "icon": "🔋", "group": "direct"},
    {"id": "tires",         "label": "Opony",               "icon": "🚗", "group": "direct"},
    {"id": "bodywork",      "label": "Nadwozia i oświetl.", "icon": "💡", "group": "direct"},
    # ── Indirect (services & consumables) ──
    {"id": "it_services",   "label": "IT / Licencje",       "icon": "💻", "group": "indirect"},
    {"id": "logistics",     "label": "Logistyka",           "icon": "📦", "group": "indirect"},
    {"id": "mro",           "label": "MRO / Narzędzia",     "icon": "🛠️", "group": "indirect"},
    {"id": "packaging",     "label": "Opakowania",          "icon": "📋", "group": "indirect"},
    # ── UNSPSC extended categories ──
    {"id": "chemicals",     "label": "Chemikalia",          "icon": "🧪", "group": "direct"},
    {"id": "electrical",    "label": "Elektryka i kable",   "icon": "⚡", "group": "direct"},
    {"id": "construction",  "label": "Budownictwo",         "icon": "🏗️", "group": "direct"},
    {"id": "office",        "label": "Biuro i papier",      "icon": "🗂️", "group": "indirect"},
    {"id": "safety",        "label": "BHP i ochrona",       "icon": "🦺", "group": "indirect"},
    {"id": "furniture",     "label": "Meble",               "icon": "🪑", "group": "indirect"},
    {"id": "cleaning",      "label": "Środki czystości",    "icon": "🧹", "group": "indirect"},
    {"id": "food",          "label": "Żywność i catering",  "icon": "🍽️", "group": "indirect"},
    {"id": "medical",       "label": "Medyczne",            "icon": "🏥", "group": "indirect"},
    {"id": "lab_equipment", "label": "Sprzęt pomiarowy",    "icon": "🔬", "group": "indirect"},
    {"id": "hvac",          "label": "HVAC i instalacje",   "icon": "🌡️", "group": "indirect"},
    {"id": "steel",         "label": "Stal i metale",       "icon": "🔩", "group": "direct"},
    {"id": "electronics",   "label": "Elektronika",         "icon": "🖥️", "group": "indirect"},
    {"id": "printing",      "label": "Druk i reklama",      "icon": "🖨️", "group": "indirect"},
    {"id": "transport_svc", "label": "Usługi transportowe", "icon": "🚛", "group": "indirect"},
    {"id": "consulting",    "label": "Doradztwo i szkolenia","icon": "🎓", "group": "indirect"},
    # ── Additional UNSPSC segments ──
    {"id": "raw_materials",  "label": "Surowce mineralne",   "icon": "🪨", "group": "direct"},
    {"id": "rubber_plastics","label": "Tworzywa i guma",     "icon": "🧱", "group": "direct"},
    {"id": "paper",          "label": "Papier i tektura",    "icon": "📄", "group": "direct"},
    {"id": "fuels",          "label": "Paliwa i smary",      "icon": "⛽", "group": "direct"},
    {"id": "mining_equip",   "label": "Sprzęt górniczy",     "icon": "⛏️", "group": "direct"},
    {"id": "agri_equip",     "label": "Maszyny rolnicze",    "icon": "🚜", "group": "direct"},
    {"id": "construction_eq","label": "Maszyny budowlane",   "icon": "🏗️", "group": "direct"},
    {"id": "industrial_mach","label": "Maszyny przemysłowe", "icon": "🏭", "group": "direct"},
    {"id": "lighting",       "label": "Oświetlenie",         "icon": "💡", "group": "indirect"},
    {"id": "printing_equip", "label": "Drukarki i foto",     "icon": "📷", "group": "indirect"},
    {"id": "sports",         "label": "Sport i rekreacja",   "icon": "🏋️", "group": "indirect"},
    {"id": "pharma",         "label": "Farmaceutyki",        "icon": "💊", "group": "indirect"},
    {"id": "appliances",     "label": "AGD",                 "icon": "🍳", "group": "indirect"},
    {"id": "clothing",       "label": "Odzież robocza",      "icon": "👔", "group": "indirect"},
    {"id": "publications",   "label": "Wydawnictwa",         "icon": "📚", "group": "indirect"},
    {"id": "prefab",         "label": "Budynki i konstr.",   "icon": "🏠", "group": "direct"},
    {"id": "construction_svc","label": "Usługi budowlane",   "icon": "🔨", "group": "indirect"},
    {"id": "production_svc", "label": "Usługi produkcyjne",  "icon": "🏭", "group": "indirect"},
    {"id": "environmental",  "label": "Usługi środowiskowe", "icon": "🌿", "group": "indirect"},
    {"id": "engineering_svc","label": "Usługi inżynieryjne", "icon": "📐", "group": "indirect"},
    {"id": "utilities",      "label": "Media i komunalne",   "icon": "💧", "group": "indirect"},
    {"id": "financial_svc",  "label": "Usługi finansowe",    "icon": "💰", "group": "indirect"},
    {"id": "healthcare_svc", "label": "Usługi zdrowotne",    "icon": "🩺", "group": "indirect"},
    {"id": "travel",         "label": "Podróże i eventy",    "icon": "✈️", "group": "indirect"},
    {"id": "bearings",       "label": "Łożyska i uszczelki", "icon": "⚙️", "group": "direct"},
    {"id": "semiconductors", "label": "Komponenty elektron.", "icon": "🔌", "group": "direct"},
    {"id": "vehicles",       "label": "Pojazdy i flota",     "icon": "🚗", "group": "direct"},
    {"id": "fleet_svc",      "label": "Leasing i fleet mgmt","icon": "🔑", "group": "indirect"},
    {"id": "horticulture",   "label": "Zieleń i rośliny",    "icon": "🌿", "group": "indirect"},
    {"id": "industrial_clean","label":"Sprzątanie przemysł.", "icon": "🧹", "group": "indirect"},
    {"id": "agri_services",  "label": "Usługi rolne/leśne",  "icon": "🌾", "group": "indirect"},
    {"id": "mining_services","label": "Usługi wydobywcze",   "icon": "⛏️", "group": "indirect"},
    {"id": "real_estate",    "label": "Nieruchomości",        "icon": "🏢", "group": "indirect"},
    {"id": "decorations",    "label": "Dekoracje i gadżety", "icon": "🎁", "group": "indirect"},
]

CATALOG: list[dict] = [
    # ── Części zamienne ─────────────────────────────────────────────────
    {
        "id": "BRK-001", "name": "Klocki hamulcowe TRW GDB1550",
        "description": "Klocki hamulcowe przód, ceramiczne. Homologacja ECE R90.",
        "price": 185.0, "category": "parts", "delivery_days": 2,
        "weight_kg": 0.8, "unit": "kpl", "requires_approval": False,
        "image": "brake-pads",
        "suppliers": [{"id": "SUP-TRW", "name": "TRW Automotive (DE)", "unit_price": 185.0}],
    },
    {
        "id": "FIL-001", "name": "Filtr oleju MANN W712/73",
        "description": "Filtr oleju silnikowego. Pasuje do VW/Audi/Skoda.",
        "price": 32.0, "category": "parts", "delivery_days": 1,
        "weight_kg": 0.3, "unit": "szt", "requires_approval": False,
        "image": "oil-filter",
        "suppliers": [
            {"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 32.0},
            {"id": "SUP-INTERCARS", "name": "Inter Cars S.A.", "unit_price": 29.50},
        ],
    },
    {
        "id": "DSC-001", "name": "Tarcza hamulcowa Brembo 09.5802",
        "description": "Tarcza wentylowana 280mm przód. Powłoka UV.",
        "price": 245.0, "category": "parts", "delivery_days": 3,
        "weight_kg": 4.5, "unit": "szt", "requires_approval": False,
        "image": "brake-disc",
        "suppliers": [{"id": "SUP-BREMBO", "name": "Brembo Poland", "unit_price": 245.0}],
    },
    {
        "id": "AMO-001", "name": "Amortyzator Sachs 313 478",
        "description": "Amortyzator przód gazowy. Oryginalna jakość ZF.",
        "price": 320.0, "category": "parts", "delivery_days": 3,
        "weight_kg": 3.2, "unit": "szt", "requires_approval": False,
        "image": "shock-absorber",
        "suppliers": [{"id": "SUP-TRW", "name": "TRW Automotive (DE)", "unit_price": 320.0}],
    },
    {
        "id": "PAS-001", "name": "Pasek wieloklinowy Gates 6PK1070",
        "description": "Pasek napędu osprzętu silnika. EPDM micro-V.",
        "price": 58.0, "category": "parts", "delivery_days": 1,
        "weight_kg": 0.2, "unit": "szt", "requires_approval": False,
        "image": "belt",
        "suppliers": [
            {"id": "SUP-INTERCARS", "name": "Inter Cars S.A.", "unit_price": 55.0},
            {"id": "SUP-MOTO", "name": "Moto-Profil (Grupa Brembo)", "unit_price": 58.0},
        ],
    },

    # ── Komponenty OE ───────────────────────────────────────────────────
    {
        "id": "ALT-001", "name": "Alternator Bosch 0 124 525 014",
        "description": "Alternator 14V 120A. Jakość OE, regulator napięcia.",
        "price": 890.0, "category": "oe_components", "delivery_days": 5,
        "weight_kg": 5.8, "unit": "szt", "requires_approval": False,
        "image": "alternator",
        "suppliers": [{"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 890.0}],
    },
    {
        "id": "PMP-001", "name": "Pompa wody SKF VKPC 86416",
        "description": "Pompa wody z uszczelką. Łożysko ceramiczne.",
        "price": 210.0, "category": "oe_components", "delivery_days": 4,
        "weight_kg": 1.5, "unit": "szt", "requires_approval": False,
        "image": "water-pump",
        "suppliers": [
            {"id": "SUP-BREMBO", "name": "Brembo Poland", "unit_price": 210.0},
            {"id": "SUP-TRW", "name": "TRW Automotive (DE)", "unit_price": 225.0},
        ],
    },
    {
        "id": "ROZ-001", "name": "Rozrusznik Valeo 438170",
        "description": "Rozrusznik 12V 1.1kW. Regenerowany OE.",
        "price": 780.0, "category": "oe_components", "delivery_days": 5,
        "weight_kg": 4.2, "unit": "szt", "requires_approval": True,
        "image": "starter",
        "suppliers": [{"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 780.0}],
    },

    # ── Oleje i płyny ───────────────────────────────────────────────────
    {
        "id": "OIL-001", "name": "Castrol EDGE 5W-30 LL 5L",
        "description": "Olej syntetyczny Titanium FST. VW 504/507.",
        "price": 189.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 4.6, "unit": "szt", "requires_approval": False,
        "image": "engine-oil",
        "suppliers": [{"id": "SUP-CASTROL", "name": "Castrol Polska", "unit_price": 189.0}],
    },
    {
        "id": "OIL-002", "name": "Shell Helix Ultra ECT 5W-30 4L",
        "description": "Olej syntetyczny PurePlus. MB 229.51, BMW LL-04.",
        "price": 165.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 3.8, "unit": "szt", "requires_approval": False,
        "image": "engine-oil-2",
        "suppliers": [{"id": "SUP-CASTROL", "name": "Castrol Polska", "unit_price": 165.0}],
    },
    {
        "id": "BRF-001", "name": "Płyn hamulcowy ATE SL.6 DOT4 1L",
        "description": "Płyn hamulcowy klasy DOT4. T. wrzenia 265°C.",
        "price": 45.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 1.1, "unit": "szt", "requires_approval": False,
        "image": "brake-fluid",
        "suppliers": [{"id": "SUP-TRW", "name": "TRW Automotive (DE)", "unit_price": 45.0}],
    },
    {
        "id": "CLN-001", "name": "Płyn do spryskiwaczy zimowy -22°C 5L",
        "description": "Koncentrat z alkoholem izopropylowym. Nie pozostawia smug.",
        "price": 25.0, "category": "oils", "delivery_days": 1,
        "weight_kg": 5.2, "unit": "szt", "requires_approval": False,
        "image": "washer-fluid",
        "suppliers": [{"id": "SUP-INTERCARS", "name": "Inter Cars S.A.", "unit_price": 25.0}],
    },

    # ── Akumulatory ─────────────────────────────────────────────────────
    {
        "id": "BAT-001", "name": "Varta Blue Dynamic E11 74Ah",
        "description": "Akumulator 12V 74Ah 680A(EN). Wymiary 278x175x190.",
        "price": 420.0, "category": "batteries", "delivery_days": 2,
        "weight_kg": 18.5, "unit": "szt", "requires_approval": False,
        "image": "battery",
        "suppliers": [{"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 420.0}],
    },
    {
        "id": "BAT-002", "name": "Exide Premium EA770 77Ah",
        "description": "Akumulator 12V 77Ah 760A(EN). Carbon Boost 2.0.",
        "price": 385.0, "category": "batteries", "delivery_days": 2,
        "weight_kg": 19.2, "unit": "szt", "requires_approval": False,
        "image": "battery-2",
        "suppliers": [{"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 385.0}],
    },
    {   # Auto-bundle item (injected when batteries in cart)
        "id": "BUNDLE-CAB", "name": "Kable rozruchowe 600A 3m",
        "description": "Kable rozruchowe miedziane z zaciskami izolowanymi.",
        "price": 89.0, "category": "batteries", "delivery_days": 1,
        "weight_kg": 1.5, "unit": "kpl", "requires_approval": False,
        "image": "jumper-cables", "_is_bundle_source": True,
        "suppliers": [{"id": "SUP-BOSCH", "name": "Bosch Aftermarket (DE)", "unit_price": 89.0}],
    },

    # ── Opony ───────────────────────────────────────────────────────────
    {
        "id": "TIR-001", "name": "Continental PremiumContact 6 205/55R16",
        "description": "Opona letnia. EU label: A/A/71dB. Run-flat.",
        "price": 480.0, "category": "tires", "delivery_days": 3,
        "weight_kg": 8.5, "unit": "szt", "requires_approval": False,
        "image": "tire-continental",
        "suppliers": [{"id": "SUP-MOTO", "name": "Moto-Profil (Grupa Brembo)", "unit_price": 480.0}],
    },
    {
        "id": "TIR-002", "name": "Michelin Pilot Sport 5 225/45R17",
        "description": "Opona letnia premium. EU label: A/A/70dB.",
        "price": 620.0, "category": "tires", "delivery_days": 4,
        "weight_kg": 9.2, "unit": "szt", "requires_approval": False,
        "image": "tire-michelin",
        "suppliers": [{"id": "SUP-MOTO", "name": "Moto-Profil (Grupa Brembo)", "unit_price": 620.0}],
    },
    {
        "id": "TIR-003", "name": "Hankook Ventus Prime 4 195/65R15",
        "description": "Opona letnia ekonomiczna. EU label: A/B/69dB.",
        "price": 340.0, "category": "tires", "delivery_days": 2,
        "weight_kg": 7.8, "unit": "szt", "requires_approval": False,
        "image": "tire-hankook",
        "suppliers": [{"id": "SUP-INTERCARS", "name": "Inter Cars S.A.", "unit_price": 340.0}],
    },

    # ── Nadwozia / Oświetlenie ──────────────────────────────────────────
    {
        "id": "REF-001", "name": "Reflektor przedni LED (lewy)",
        "description": "Lampa przód LED z DRL. Homologacja E4. Hella OE.",
        "price": 1250.0, "category": "bodywork", "delivery_days": 7,
        "weight_kg": 2.8, "unit": "szt", "requires_approval": True,
        "image": "headlight",
        "suppliers": [{"id": "SUP-BREMBO", "name": "Brembo Poland", "unit_price": 1250.0}],
    },
    {
        "id": "ZDR-001", "name": "Zderzak przedni surowy do lakierowania",
        "description": "Zderzak PP z otworami na czujniki PDC.",
        "price": 890.0, "category": "bodywork", "delivery_days": 7,
        "weight_kg": 4.5, "unit": "szt", "requires_approval": False,
        "image": "bumper",
        "suppliers": [{"id": "SUP-MOTO", "name": "Moto-Profil (Grupa Brembo)", "unit_price": 890.0}],
    },

    # ── IT / Licencje ───────────────────────────────────────────────────
    {
        "id": "SAP-001", "name": "Licencja SAP moduł MM (roczna)",
        "description": "Named-user license SAP Materials Management.",
        "price": 12000.0, "category": "it_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "lic", "requires_approval": True,
        "image": "sap-license",
        "suppliers": [],
    },
    {
        "id": "ERP-001", "name": "Serwis ERP — aktualizacja kwartalna",
        "description": "Usługa aktualizacji i optymalizacji modułów ERP.",
        "price": 4500.0, "category": "it_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "usł", "requires_approval": False,
        "image": "erp-service",
        "suppliers": [],
    },

    # ── Logistyka ───────────────────────────────────────────────────────
    {
        "id": "PAL-001", "name": "Paleta EUR EPAL 1200x800",
        "description": "Paleta drewniana certyfikowana EPAL. Nowa.",
        "price": 42.0, "category": "logistics", "delivery_days": 2,
        "weight_kg": 25.0, "unit": "szt", "requires_approval": False,
        "image": "pallet",
        "suppliers": [],
    },

    # ── MRO / Narzędzia ─────────────────────────────────────────────────
    {
        "id": "NRZ-001", "name": "Zestaw kluczy Wera Kraftform 12szt",
        "description": "Zestaw wkrętaków Kraftform Plus z Lasertip.",
        "price": 380.0, "category": "mro", "delivery_days": 3,
        "weight_kg": 2.5, "unit": "kpl", "requires_approval": False,
        "image": "tools-wera",
        "suppliers": [],
    },
    {
        "id": "BHP-001", "name": "Rękawice robocze nitrylowe 100 par",
        "description": "Rękawice jednorazowe, pudrowane. Rozmiar L.",
        "price": 220.0, "category": "mro", "delivery_days": 2,
        "weight_kg": 5.0, "unit": "op", "requires_approval": False,
        "image": "gloves",
        "suppliers": [],
    },

    # ── Opakowania ──────────────────────────────────────────────────────
    {
        "id": "FOL-001", "name": "Folia stretch 23μm 500mm 2.4kg",
        "description": "Folia do owijania palet. Rozciągliwość 300%.",
        "price": 18.0, "category": "packaging", "delivery_days": 1,
        "weight_kg": 2.4, "unit": "rol", "requires_approval": False,
        "image": "stretch-film",
        "suppliers": [],
    },
    {
        "id": "KRT-001", "name": "Karton klapowy 600x400x400 3W",
        "description": "Karton trójwarstwowy fala B. Brązowy.",
        "price": 4.50, "category": "packaging", "delivery_days": 1,
        "weight_kg": 0.6, "unit": "szt", "requires_approval": False,
        "image": "cardboard-box",
        "suppliers": [{"id": "SUP-MONDI", "name": "Mondi Packaging PL", "unit_price": 4.50}],
    },

    # ══════════════════════════════════════════════════════════════════════
    # UNSPSC EXTENDED CATALOG — segments 10-95, families level 2
    # ══════════════════════════════════════════════════════════════════════

    # ── 12: Chemikalia ─────────────────────────────────────────────────
    {
        "id": "CHM-001", "name": "Izopropanol techniczny 99.9% 5L",
        "description": "Alkohol izopropylowy czysty. UNSPSC 12142100. Do czyszczenia i odtłuszczania.",
        "price": 45.0, "category": "chemicals", "delivery_days": 2,
        "weight_kg": 4.2, "unit": "szt", "requires_approval": False, "image": "chemical",
        "suppliers": [{"id": "SUP-BRENNTAG", "name": "Brenntag Polska", "unit_price": 45.0}],
    },
    {
        "id": "CHM-002", "name": "Aceton techniczny 5L",
        "description": "Rozpuszczalnik organiczny. UNSPSC 12161500. Czystość >99%.",
        "price": 38.0, "category": "chemicals", "delivery_days": 2,
        "weight_kg": 4.0, "unit": "szt", "requires_approval": False, "image": "chemical-2",
        "suppliers": [{"id": "SUP-BRENNTAG", "name": "Brenntag Polska", "unit_price": 38.0},
                      {"id": "SUP-AVANTOR", "name": "Avantor (Polska Chemia)", "unit_price": 35.0}],
    },
    {
        "id": "CHM-003", "name": "Smar litowy ŁT-4S 0.8kg",
        "description": "Smar wielozadaniowy litowy. UNSPSC 15121500. Zakres -30 do +120°C.",
        "price": 28.0, "category": "chemicals", "delivery_days": 1,
        "weight_kg": 0.9, "unit": "szt", "requires_approval": False, "image": "grease",
        "suppliers": [{"id": "SUP-ORLEN", "name": "Orlen Oil Kraków", "unit_price": 28.0}],
    },

    # ── 26: Elektryka i kable ──────────────────────────────────────────
    {
        "id": "ELK-001", "name": "Kabel YKY 5x2.5mm² 100m",
        "description": "Kabel instalacyjny miedziany. UNSPSC 26121600. Izolacja PVC.",
        "price": 620.0, "category": "electrical", "delivery_days": 3,
        "weight_kg": 18.0, "unit": "bęben", "requires_approval": False, "image": "cable",
        "suppliers": [{"id": "SUP-HELUKABEL", "name": "Helukabel Polska", "unit_price": 620.0},
                      {"id": "SUP-TELE", "name": "Tele-Fonika Kraków", "unit_price": 595.0}],
    },
    {
        "id": "ELK-002", "name": "Rozdzielnica modułowa 3x12 IP65",
        "description": "Rozdzielnica natynkowa z szyną DIN. UNSPSC 26131500.",
        "price": 340.0, "category": "electrical", "delivery_days": 4,
        "weight_kg": 5.5, "unit": "szt", "requires_approval": False, "image": "switchboard",
        "suppliers": [{"id": "SUP-HAGER", "name": "Hager Polo Tychy", "unit_price": 340.0}],
    },
    {
        "id": "ELK-003", "name": "Wyłącznik różnicowo-prądowy 40A 30mA",
        "description": "Wyłącznik ochronny AC typ A. UNSPSC 26131800.",
        "price": 85.0, "category": "electrical", "delivery_days": 2,
        "weight_kg": 0.3, "unit": "szt", "requires_approval": False, "image": "rcd",
        "suppliers": [{"id": "SUP-HAGER", "name": "Hager Polo Tychy", "unit_price": 85.0},
                      {"id": "SUP-LEGRAND", "name": "Legrand Polska", "unit_price": 92.0}],
    },

    # ── 22/60: Budownictwo ─────────────────────────────────────────────
    {
        "id": "BUD-001", "name": "Cement portlandzki CEM I 42.5R 25kg",
        "description": "Cement szybkowiążący. UNSPSC 30111500. Klasa wytrzymałości 42.5.",
        "price": 22.0, "category": "construction", "delivery_days": 2,
        "weight_kg": 25.0, "unit": "worek", "requires_approval": False, "image": "cement",
        "suppliers": [{"id": "SUP-CEMEX", "name": "CEMEX Polska", "unit_price": 22.0},
                      {"id": "SUP-LAFARGE", "name": "Lafarge Polska", "unit_price": 21.0}],
    },
    {
        "id": "BUD-002", "name": "Płyta g-k Knauf 12.5mm 1200x2600",
        "description": "Płyta gipsowo-kartonowa standardowa. UNSPSC 30161500.",
        "price": 32.0, "category": "construction", "delivery_days": 3,
        "weight_kg": 28.0, "unit": "szt", "requires_approval": False, "image": "drywall",
        "suppliers": [{"id": "SUP-KNAUF", "name": "Knauf Polska", "unit_price": 32.0}],
    },
    {
        "id": "BUD-003", "name": "Wełna mineralna Isover 100mm 5m²",
        "description": "Wełna izolacyjna szklana. UNSPSC 30141600. Lambda 0.035.",
        "price": 65.0, "category": "construction", "delivery_days": 3,
        "weight_kg": 4.5, "unit": "paczka", "requires_approval": False, "image": "insulation",
        "suppliers": [{"id": "SUP-SAINT", "name": "Saint-Gobain Polska", "unit_price": 65.0}],
    },

    # ── 44: Biuro i papier ─────────────────────────────────────────────
    {
        "id": "BIU-001", "name": "Papier ksero A4 80g 500ark",
        "description": "Papier biurowy biały. UNSPSC 44121500. Klasa C, białość 146 CIE.",
        "price": 18.0, "category": "office", "delivery_days": 1,
        "weight_kg": 2.5, "unit": "ryza", "requires_approval": False, "image": "paper",
        "suppliers": [{"id": "SUP-LYRECO", "name": "Lyreco Polska", "unit_price": 18.0},
                      {"id": "SUP-STAPLES", "name": "Staples Solutions", "unit_price": 17.50}],
    },
    {
        "id": "BIU-002", "name": "Toner HP 26A CF226A oryginalny",
        "description": "Toner do HP LaserJet Pro M402. UNSPSC 44103100. Wydajność 3100 str.",
        "price": 320.0, "category": "office", "delivery_days": 2,
        "weight_kg": 0.8, "unit": "szt", "requires_approval": False, "image": "toner",
        "suppliers": [{"id": "SUP-LYRECO", "name": "Lyreco Polska", "unit_price": 320.0}],
    },
    {
        "id": "BIU-003", "name": "Segregator A4 75mm 10szt",
        "description": "Segregator z mechanizmem dźwigniowym. UNSPSC 44112000.",
        "price": 42.0, "category": "office", "delivery_days": 1,
        "weight_kg": 6.0, "unit": "op", "requires_approval": False, "image": "binder",
        "suppliers": [{"id": "SUP-LYRECO", "name": "Lyreco Polska", "unit_price": 42.0},
                      {"id": "SUP-STAPLES", "name": "Staples Solutions", "unit_price": 40.0}],
    },

    # ── 46: BHP i ochrona ─────────────────────────────────────────────
    {
        "id": "BHP-002", "name": "Kask ochronny JSP EVO3 z wentylacją",
        "description": "Kask przemysłowy EN 397. UNSPSC 46181500. Regulacja obwodu.",
        "price": 65.0, "category": "safety", "delivery_days": 2,
        "weight_kg": 0.4, "unit": "szt", "requires_approval": False, "image": "helmet",
        "suppliers": [{"id": "SUP-PROCURATOR", "name": "Procurator BHP", "unit_price": 65.0},
                      {"id": "SUP-WURTH", "name": "Würth Polska", "unit_price": 72.0}],
    },
    {
        "id": "BHP-003", "name": "Obuwie robocze S3 Uvex 1 roz. 42-46",
        "description": "Trzewiki ochronne S3 SRC. UNSPSC 46181600. Stalowy podnosek.",
        "price": 380.0, "category": "safety", "delivery_days": 3,
        "weight_kg": 1.2, "unit": "para", "requires_approval": False, "image": "safety-boots",
        "suppliers": [{"id": "SUP-PROCURATOR", "name": "Procurator BHP", "unit_price": 380.0}],
    },
    {
        "id": "BHP-004", "name": "Gaśnica proszkowa ABC 6kg GP-6x",
        "description": "Gaśnica z manometrem. UNSPSC 46191500. Certyfikat CNBOP.",
        "price": 120.0, "category": "safety", "delivery_days": 2,
        "weight_kg": 9.5, "unit": "szt", "requires_approval": False, "image": "extinguisher",
        "suppliers": [{"id": "SUP-KZWM", "name": "KZWM Ogniochron", "unit_price": 120.0}],
    },

    # ── 49: Meble ──────────────────────────────────────────────────────
    {
        "id": "MEB-001", "name": "Biurko regulowane elektrycznie 160x80",
        "description": "Biurko sit-stand z panelem sterowania. UNSPSC 49101600.",
        "price": 2200.0, "category": "furniture", "delivery_days": 7,
        "weight_kg": 35.0, "unit": "szt", "requires_approval": True, "image": "desk",
        "suppliers": [{"id": "SUP-KINNARPS", "name": "Kinnarps Polska", "unit_price": 2200.0},
                      {"id": "SUP-STEELCASE", "name": "Steelcase CEE", "unit_price": 2450.0}],
    },
    {
        "id": "MEB-002", "name": "Krzesło ergonomiczne Haworth Zody",
        "description": "Krzesło biurowe z regulacją lędźwiową. UNSPSC 49111500.",
        "price": 3200.0, "category": "furniture", "delivery_days": 14,
        "weight_kg": 18.0, "unit": "szt", "requires_approval": True, "image": "chair",
        "suppliers": [{"id": "SUP-KINNARPS", "name": "Kinnarps Polska", "unit_price": 3200.0},
                      {"id": "SUP-STEELCASE", "name": "Steelcase CEE", "unit_price": 3400.0}],
    },
    {
        "id": "MEB-003", "name": "Szafa aktowa metalowa 195x100x42",
        "description": "Szafa na dokumenty z zamkiem. UNSPSC 49121500.",
        "price": 890.0, "category": "furniture", "delivery_days": 7,
        "weight_kg": 45.0, "unit": "szt", "requires_approval": False, "image": "cabinet",
        "suppliers": [{"id": "SUP-KINNARPS", "name": "Kinnarps Polska", "unit_price": 890.0}],
    },

    # ── 47: Środki czystości ───────────────────────────────────────────
    {
        "id": "CZY-001", "name": "Płyn do mycia podłóg przemysłowych 10L",
        "description": "Koncentrat alkaliczny. UNSPSC 47131500. Rozcieńczenie 1:100.",
        "price": 85.0, "category": "cleaning", "delivery_days": 2,
        "weight_kg": 10.5, "unit": "kanister", "requires_approval": False, "image": "floor-cleaner",
        "suppliers": [{"id": "SUP-ECOLAB", "name": "Ecolab Polska", "unit_price": 85.0},
                      {"id": "SUP-KÄRCHER", "name": "Kärcher Polska", "unit_price": 92.0}],
    },
    {
        "id": "CZY-002", "name": "Myjka ciśnieniowa Kärcher HD 5/15C",
        "description": "Myjka ciśnieniowa 150 bar. UNSPSC 47121800. Zasilanie 230V.",
        "price": 3200.0, "category": "cleaning", "delivery_days": 5,
        "weight_kg": 25.0, "unit": "szt", "requires_approval": True, "image": "pressure-washer",
        "suppliers": [{"id": "SUP-KÄRCHER", "name": "Kärcher Polska", "unit_price": 3200.0}],
    },

    # ── 50: Żywność i catering ─────────────────────────────────────────
    {
        "id": "FOD-001", "name": "Kawa ziarnista Lavazza Qualità Oro 1kg",
        "description": "Kawa do ekspresu automatycznego. UNSPSC 50201700.",
        "price": 72.0, "category": "food", "delivery_days": 1,
        "weight_kg": 1.0, "unit": "szt", "requires_approval": False, "image": "coffee",
        "suppliers": [{"id": "SUP-MAKRO", "name": "Makro Cash&Carry", "unit_price": 72.0}],
    },
    {
        "id": "FOD-002", "name": "Woda mineralna paleta 504 butelki 0.5L",
        "description": "Woda źródlana niegazowana. UNSPSC 50202300.",
        "price": 380.0, "category": "food", "delivery_days": 2,
        "weight_kg": 260.0, "unit": "paleta", "requires_approval": False, "image": "water",
        "suppliers": [{"id": "SUP-MAKRO", "name": "Makro Cash&Carry", "unit_price": 380.0}],
    },

    # ── 42: Medyczne ───────────────────────────────────────────────────
    {
        "id": "MED-001", "name": "Apteczka zakładowa DIN 13157",
        "description": "Apteczka pierwszej pomocy. UNSPSC 42172000. Komplet wkładów.",
        "price": 180.0, "category": "medical", "delivery_days": 2,
        "weight_kg": 2.5, "unit": "kpl", "requires_approval": False, "image": "first-aid",
        "suppliers": [{"id": "SUP-PROCURATOR", "name": "Procurator BHP", "unit_price": 180.0}],
    },
    {
        "id": "MED-002", "name": "Defibrylator AED Philips HS1",
        "description": "Automatyczny defibrylator zewnętrzny. UNSPSC 42171800.",
        "price": 5500.0, "category": "medical", "delivery_days": 7,
        "weight_kg": 1.5, "unit": "szt", "requires_approval": True, "image": "aed",
        "suppliers": [{"id": "SUP-MEDLINE", "name": "Medline International", "unit_price": 5500.0}],
    },

    # ── 41: Sprzęt pomiarowy ───────────────────────────────────────────
    {
        "id": "POM-001", "name": "Multimetr cyfrowy Fluke 179",
        "description": "Multimetr True-RMS z termometrem. UNSPSC 41111500.",
        "price": 1450.0, "category": "lab_equipment", "delivery_days": 3,
        "weight_kg": 0.6, "unit": "szt", "requires_approval": False, "image": "multimeter",
        "suppliers": [{"id": "SUP-FLUKE", "name": "Fluke / Elma Instruments", "unit_price": 1450.0}],
    },
    {
        "id": "POM-002", "name": "Suwmiarka cyfrowa Mitutoyo 150mm",
        "description": "Suwmiarka IP67 z wyjściem danych. UNSPSC 41111600.",
        "price": 680.0, "category": "lab_equipment", "delivery_days": 3,
        "weight_kg": 0.3, "unit": "szt", "requires_approval": False, "image": "caliper",
        "suppliers": [{"id": "SUP-MITUTOYO", "name": "Mitutoyo Polska", "unit_price": 680.0}],
    },

    # ── 40: HVAC i instalacje ──────────────────────────────────────────
    {
        "id": "HVC-001", "name": "Klimatyzator split Samsung WindFree 3.5kW",
        "description": "Klimatyzator ścienny z WiFi. UNSPSC 40101700. Klasa A+++.",
        "price": 4200.0, "category": "hvac", "delivery_days": 5,
        "weight_kg": 35.0, "unit": "kpl", "requires_approval": True, "image": "air-conditioner",
        "suppliers": [{"id": "SUP-DAIKIN", "name": "Daikin Europe Poland", "unit_price": 4200.0}],
    },
    {
        "id": "HVC-002", "name": "Pompa obiegowa Grundfos ALPHA2 25-60",
        "description": "Pompa c.o. energooszczędna. UNSPSC 40141700. Klasa A.",
        "price": 890.0, "category": "hvac", "delivery_days": 3,
        "weight_kg": 2.8, "unit": "szt", "requires_approval": False, "image": "pump",
        "suppliers": [{"id": "SUP-GRUNDFOS", "name": "Grundfos Polska", "unit_price": 890.0}],
    },

    # ── 30: Stal i metale ──────────────────────────────────────────────
    {
        "id": "STL-001", "name": "Profil stalowy IPE 200 6m",
        "description": "Dwuteownik stalowy S235JR. UNSPSC 30101500.",
        "price": 420.0, "category": "steel", "delivery_days": 5,
        "weight_kg": 134.0, "unit": "szt", "requires_approval": False, "image": "steel-beam",
        "suppliers": [{"id": "SUP-ARCELOR", "name": "ArcelorMittal Poland", "unit_price": 420.0},
                      {"id": "SUP-KONSORCJUM", "name": "Konsorcjum Stali", "unit_price": 435.0}],
    },
    {
        "id": "STL-002", "name": "Blacha stalowa DC01 2mm 1250x2500",
        "description": "Blacha zimnowalcowana. UNSPSC 30101700.",
        "price": 280.0, "category": "steel", "delivery_days": 4,
        "weight_kg": 49.0, "unit": "arkusz", "requires_approval": False, "image": "steel-sheet",
        "suppliers": [{"id": "SUP-ARCELOR", "name": "ArcelorMittal Poland", "unit_price": 280.0}],
    },
    {
        "id": "STL-003", "name": "Śruby M10x50 kl.8.8 ocynk 100szt",
        "description": "Śruby z łbem sześciokątnym ISO 4017. UNSPSC 31161500.",
        "price": 48.0, "category": "steel", "delivery_days": 1,
        "weight_kg": 3.5, "unit": "op", "requires_approval": False, "image": "bolts",
        "suppliers": [{"id": "SUP-WURTH", "name": "Würth Polska", "unit_price": 48.0},
                      {"id": "SUP-HILTI", "name": "Hilti Polska", "unit_price": 52.0}],
    },

    # ── 32/43: Elektronika ─────────────────────────────────────────────
    {
        "id": "ELE-001", "name": "Monitor Dell U2723QE 27\" 4K USB-C",
        "description": "Monitor IPS UltraSharp z hubem USB-C. UNSPSC 43211900.",
        "price": 2400.0, "category": "electronics", "delivery_days": 3,
        "weight_kg": 6.8, "unit": "szt", "requires_approval": True, "image": "monitor",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (Dell)", "unit_price": 2400.0}],
    },
    {
        "id": "ELE-002", "name": "Laptop Lenovo ThinkPad T14s Gen4 i7/16/512",
        "description": "Laptop biznesowy 14\" WUXGA. UNSPSC 43211500.",
        "price": 6500.0, "category": "electronics", "delivery_days": 5,
        "weight_kg": 1.3, "unit": "szt", "requires_approval": True, "image": "laptop",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (Lenovo)", "unit_price": 6500.0},
                      {"id": "SUP-AB", "name": "AB S.A. Wrocław", "unit_price": 6350.0}],
    },
    {
        "id": "ELE-003", "name": "Switch sieciowy Cisco SG350-28 28-port",
        "description": "Switch zarządzalny PoE+. UNSPSC 43222600.",
        "price": 3800.0, "category": "electronics", "delivery_days": 5,
        "weight_kg": 3.5, "unit": "szt", "requires_approval": True, "image": "switch",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (Cisco)", "unit_price": 3800.0}],
    },

    # ── 45/82: Druk i reklama ──────────────────────────────────────────
    {
        "id": "DRK-001", "name": "Wizytówki firmowe 500szt 350g mat",
        "description": "Druk offsetowy dwustronny. UNSPSC 82121500.",
        "price": 120.0, "category": "printing", "delivery_days": 5,
        "weight_kg": 0.5, "unit": "op", "requires_approval": False, "image": "business-cards",
        "suppliers": [{"id": "SUP-ARGO", "name": "Argo-Graf Drukarnia", "unit_price": 120.0}],
    },
    {
        "id": "DRK-002", "name": "Roll-up reklamowy 85x200cm z wydrukiem",
        "description": "Kaseta aluminiowa z nadrukiem. UNSPSC 82101500.",
        "price": 280.0, "category": "printing", "delivery_days": 3,
        "weight_kg": 4.0, "unit": "szt", "requires_approval": False, "image": "rollup",
        "suppliers": [{"id": "SUP-ARGO", "name": "Argo-Graf Drukarnia", "unit_price": 280.0}],
    },

    # ── 78: Usługi transportowe ────────────────────────────────────────
    {
        "id": "TRS-001", "name": "Transport krajowy FTL 24t (do 500km)",
        "description": "Full truckload Polska. UNSPSC 78101800.",
        "price": 2800.0, "category": "transport_svc", "delivery_days": 1,
        "weight_kg": 0.0, "unit": "kurs", "requires_approval": False, "image": "truck",
        "suppliers": [{"id": "SUP-RABEN", "name": "Raben Logistics", "unit_price": 2800.0},
                      {"id": "SUP-DHL", "name": "DHL Freight PL", "unit_price": 2950.0}],
    },
    {
        "id": "TRS-002", "name": "Kurier krajowy paczka do 30kg",
        "description": "Dostawa door-to-door 24h. UNSPSC 78102200.",
        "price": 18.0, "category": "transport_svc", "delivery_days": 1,
        "weight_kg": 0.0, "unit": "szt", "requires_approval": False, "image": "courier",
        "suppliers": [{"id": "SUP-DHL", "name": "DHL Express PL", "unit_price": 18.0},
                      {"id": "SUP-INPOST", "name": "InPost", "unit_price": 14.0}],
    },

    # ── 80/86: Doradztwo i szkolenia ───────────────────────────────────
    {
        "id": "SZK-001", "name": "Szkolenie BHP okresowe (grupa 15 osób)",
        "description": "Szkolenie z zakresu BHP dla pracowników. UNSPSC 86101700.",
        "price": 1500.0, "category": "consulting", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "usł", "requires_approval": False, "image": "training",
        "suppliers": [{"id": "SUP-SGS", "name": "SGS Polska", "unit_price": 1500.0}],
    },
    {
        "id": "SZK-002", "name": "Audyt ISO 9001 — certyfikacja",
        "description": "Audyt certyfikujący QMS. UNSPSC 80101500.",
        "price": 12000.0, "category": "consulting", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "usł", "requires_approval": True, "image": "audit",
        "suppliers": [{"id": "SUP-TUVSUD", "name": "TÜV SÜD Polska", "unit_price": 12000.0},
                      {"id": "SUP-BSI", "name": "BSI Group Polska", "unit_price": 11500.0}],
    },
    {
        "id": "SZK-003", "name": "Konsulting Lean Manufacturing 5 dni",
        "description": "Warsztaty optymalizacji procesów produkcji. UNSPSC 80101600.",
        "price": 18000.0, "category": "consulting", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "usł", "requires_approval": True, "image": "consulting",
        "suppliers": [{"id": "SUP-DELOITTE", "name": "Deloitte Consulting CE", "unit_price": 18000.0}],
    },

    # ── Extra: MRO rozszerzenie ────────────────────────────────────────
    {
        "id": "NRZ-002", "name": "Wiertarko-wkrętarka Hilti SF 6H-22",
        "description": "Akumulatorowa 22V z walizką. UNSPSC 27112000.",
        "price": 2100.0, "category": "mro", "delivery_days": 3,
        "weight_kg": 2.4, "unit": "szt", "requires_approval": False, "image": "drill",
        "suppliers": [{"id": "SUP-HILTI", "name": "Hilti Polska", "unit_price": 2100.0},
                      {"id": "SUP-WURTH", "name": "Würth Polska", "unit_price": 2250.0}],
    },
    {
        "id": "NRZ-003", "name": "Szlifierka kątowa Bosch GWS 22-230",
        "description": "Szlifierka 230mm 2200W. UNSPSC 27112100.",
        "price": 680.0, "category": "mro", "delivery_days": 2,
        "weight_kg": 5.2, "unit": "szt", "requires_approval": False, "image": "grinder",
        "suppliers": [{"id": "SUP-BOSCH-PT", "name": "Bosch Power Tools", "unit_price": 680.0}],
    },

    # ── Extra: IT rozszerzenie ─────────────────────────────────────────
    {
        "id": "IT-003", "name": "Microsoft 365 E3 (roczna, 1 user)",
        "description": "Subskrypcja cloud Office+Teams+SharePoint. UNSPSC 43232300.",
        "price": 1320.0, "category": "it_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "lic", "requires_approval": False, "image": "m365",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (Microsoft)", "unit_price": 1320.0},
                      {"id": "SUP-AB", "name": "AB S.A. Wrocław", "unit_price": 1290.0}],
    },
    {
        "id": "IT-004", "name": "Serwer Dell PowerEdge R750xs",
        "description": "Serwer rack 2U Xeon Silver 4314. UNSPSC 43211500.",
        "price": 28000.0, "category": "it_services", "delivery_days": 14,
        "weight_kg": 25.0, "unit": "szt", "requires_approval": True, "image": "server",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (Dell)", "unit_price": 28000.0}],
    },

    # ── Extra: Logistyka rozszerzenie ──────────────────────────────────
    {
        "id": "LOG-001", "name": "Regał paletowy 3 poziomy 2700kg/półka",
        "description": "Regał magazynowy z certyfikatem. UNSPSC 24102000.",
        "price": 1800.0, "category": "logistics", "delivery_days": 7,
        "weight_kg": 120.0, "unit": "moduł", "requires_approval": True, "image": "shelf",
        "suppliers": [{"id": "SUP-MECALUX", "name": "Mecalux Polska", "unit_price": 1800.0}],
    },
    {
        "id": "LOG-002", "name": "Taśma pakowa brązowa 48mm 66m 36szt",
        "description": "Taśma klejąca akrylowa do kartonów. UNSPSC 24112400.",
        "price": 95.0, "category": "logistics", "delivery_days": 1,
        "weight_kg": 4.0, "unit": "karton", "requires_approval": False, "image": "tape",
        "suppliers": [{"id": "SUP-MONDI", "name": "Mondi Packaging PL", "unit_price": 95.0}],
    },

    # ── Seg 11 — Surowce mineralne ───────────────────────────────────────
    {
        "id": "MIN-001", "name": "Piasek kwarcowy 0.1-0.5mm 25kg",
        "description": "Piasek filtracyjny do uzdatniania wody. UNSPSC 11101500.",
        "price": 35.0, "category": "raw_materials", "delivery_days": 3,
        "weight_kg": 25.0, "unit": "worek", "requires_approval": False, "image": "sand",
        "suppliers": [{"id": "SUP-SIBELCO", "name": "Sibelco Poland", "unit_price": 35.0}],
    },
    {
        "id": "MIN-002", "name": "Żwir bazaltowy 8-16mm Big Bag 1t",
        "description": "Kruszywo budowlane bazaltowe. UNSPSC 11101700.",
        "price": 180.0, "category": "raw_materials", "delivery_days": 5,
        "weight_kg": 1000.0, "unit": "t", "requires_approval": False, "image": "gravel",
        "suppliers": [{"id": "SUP-LAFARGE", "name": "Lafarge Polska", "unit_price": 180.0},
                      {"id": "SUP-HEIDELBERG", "name": "HeidelbergCement Polska", "unit_price": 175.0}],
    },

    # ── Seg 13 — Tworzywa sztuczne i guma ────────────────────────────────
    {
        "id": "RUB-001", "name": "Granulat PE-HD Virgin 25kg",
        "description": "Polietylen wysokiej gęstości do wtrysku. UNSPSC 13111000.",
        "price": 125.0, "category": "rubber_plastics", "delivery_days": 5,
        "weight_kg": 25.0, "unit": "worek", "requires_approval": False, "image": "pellets",
        "suppliers": [{"id": "SUP-BASF", "name": "BASF Polska", "unit_price": 125.0},
                      {"id": "SUP-SABIC", "name": "SABIC Europe", "unit_price": 120.0}],
    },
    {
        "id": "RUB-002", "name": "Uszczelka EPDM profil D 100m",
        "description": "Uszczelka gumowa samoprzylepna do drzwi/okien. UNSPSC 13111500.",
        "price": 85.0, "category": "rubber_plastics", "delivery_days": 2,
        "weight_kg": 3.0, "unit": "rolka", "requires_approval": False, "image": "seal",
        "suppliers": [{"id": "SUP-TRELLEBORG", "name": "Trelleborg Sealing", "unit_price": 85.0}],
    },
    {
        "id": "RUB-003", "name": "Pianka poliuretanowa montażowa 750ml 12szt",
        "description": "Pianka PU do wypełniania i uszczelniania. UNSPSC 13112000.",
        "price": 145.0, "category": "rubber_plastics", "delivery_days": 1,
        "weight_kg": 8.5, "unit": "karton", "requires_approval": False, "image": "foam",
        "suppliers": [{"id": "SUP-HENKEL", "name": "Henkel Polska (Ceresit)", "unit_price": 145.0},
                      {"id": "SUP-SOUDAL", "name": "Soudal Polska", "unit_price": 138.0}],
    },

    # ── Seg 14 — Papier i tektura ────────────────────────────────────────
    {
        "id": "PAP-001", "name": "Tektura falista 3W 1200x800mm 100ark",
        "description": "Tektura trójwarstwowa do opakowań. UNSPSC 14111500.",
        "price": 320.0, "category": "paper", "delivery_days": 3,
        "weight_kg": 35.0, "unit": "paleta", "requires_approval": False, "image": "cardboard",
        "suppliers": [{"id": "SUP-MONDI", "name": "Mondi Packaging PL", "unit_price": 320.0},
                      {"id": "SUP-DS-SMITH", "name": "DS Smith Polska", "unit_price": 310.0}],
    },
    {
        "id": "PAP-002", "name": "Papier pakowy brązowy 90g 1m 50m",
        "description": "Papier makulaturowy do pakowania. UNSPSC 14111800.",
        "price": 48.0, "category": "paper", "delivery_days": 2,
        "weight_kg": 5.0, "unit": "rolka", "requires_approval": False, "image": "paper",
        "suppliers": [{"id": "SUP-MONDI", "name": "Mondi Corrugated", "unit_price": 48.0}],
    },

    # ── Seg 15 — Paliwa i smary ──────────────────────────────────────────
    {
        "id": "FUL-001", "name": "Olej napędowy ON eurodiesel 1000L",
        "description": "Paliwo diesel wg normy EN 590. UNSPSC 15121500.",
        "price": 5800.0, "category": "fuels", "delivery_days": 1,
        "weight_kg": 840.0, "unit": "1000L", "requires_approval": True, "image": "diesel",
        "suppliers": [{"id": "SUP-ORLEN", "name": "PKN Orlen S.A.", "unit_price": 5800.0},
                      {"id": "SUP-BP", "name": "BP Europa SE", "unit_price": 5850.0}],
    },
    {
        "id": "FUL-002", "name": "Smar przemysłowy Mobilux EP2 18kg",
        "description": "Smar łożyskowy wielofunkcyjny. UNSPSC 15121900.",
        "price": 320.0, "category": "fuels", "delivery_days": 3,
        "weight_kg": 18.0, "unit": "wiadro", "requires_approval": False, "image": "grease",
        "suppliers": [{"id": "SUP-MOBIL", "name": "ExxonMobil Lubricants", "unit_price": 320.0}],
    },
    {
        "id": "FUL-003", "name": "Gaz propan-butan LPG autocysterna 5000L",
        "description": "LPG do floty pojazdów i ogrzewania. UNSPSC 15111500.",
        "price": 11500.0, "category": "fuels", "delivery_days": 2,
        "weight_kg": 2500.0, "unit": "dostawa", "requires_approval": True, "image": "lpg",
        "suppliers": [{"id": "SUP-ORLEN", "name": "Orlen Paliwa", "unit_price": 11500.0}],
    },

    # ── Seg 20 — Sprzęt górniczy ─────────────────────────────────────────
    {
        "id": "GOR-001", "name": "Wiertnica rdzeniowa Hilti DD 250-CA",
        "description": "Wiertnica diamentowa do betonu 250mm. UNSPSC 20101500.",
        "price": 18500.0, "category": "mining_equip", "delivery_days": 14,
        "weight_kg": 22.0, "unit": "szt", "requires_approval": True, "image": "drill",
        "suppliers": [{"id": "SUP-HILTI", "name": "Hilti Poland", "unit_price": 18500.0}],
    },
    {
        "id": "GOR-002", "name": "Pompa odwadniająca Flygt 2201 50m³/h",
        "description": "Pompa zatapialna do wykopów i odwadniania. UNSPSC 20121500.",
        "price": 8900.0, "category": "mining_equip", "delivery_days": 10,
        "weight_kg": 85.0, "unit": "szt", "requires_approval": True, "image": "pump",
        "suppliers": [{"id": "SUP-XYLEM", "name": "Xylem Water Solutions (Flygt)", "unit_price": 8900.0}],
    },

    # ── Seg 21 — Maszyny rolnicze ────────────────────────────────────────
    {
        "id": "AGR-001", "name": "Kosiarka bijakowa Claas Disco 3200",
        "description": "Kosiarka do trawy i zieleni. UNSPSC 21101500.",
        "price": 24000.0, "category": "agri_equip", "delivery_days": 21,
        "weight_kg": 650.0, "unit": "szt", "requires_approval": True, "image": "mower",
        "suppliers": [{"id": "SUP-CLAAS", "name": "Claas Polska", "unit_price": 24000.0}],
    },
    {
        "id": "AGR-002", "name": "Opryskiwacz ciągnikowy Amazone UF 1801",
        "description": "Opryskiwacz polowy 1800L z belką 18m. UNSPSC 21101800.",
        "price": 42000.0, "category": "agri_equip", "delivery_days": 30,
        "weight_kg": 1200.0, "unit": "szt", "requires_approval": True, "image": "sprayer",
        "suppliers": [{"id": "SUP-AMAZONE", "name": "Amazone H. Dreyer SE", "unit_price": 42000.0}],
    },

    # ── Seg 22 — Maszyny budowlane ───────────────────────────────────────
    {
        "id": "MBD-001", "name": "Minikoparka Cat 301.7 CR 1.7t",
        "description": "Kompaktowa koparka gąsienicowa. UNSPSC 22101500.",
        "price": 185000.0, "category": "construction_eq", "delivery_days": 60,
        "weight_kg": 1700.0, "unit": "szt", "requires_approval": True, "image": "excavator",
        "suppliers": [{"id": "SUP-CAT", "name": "Caterpillar (Bergerat Monnoyeur)", "unit_price": 185000.0}],
    },
    {
        "id": "MBD-002", "name": "Zagęszczarka płytowa Wacker DPU 6555",
        "description": "Zagęszczarka rewersyjna 500kg. UNSPSC 22101900.",
        "price": 28000.0, "category": "construction_eq", "delivery_days": 14,
        "weight_kg": 500.0, "unit": "szt", "requires_approval": True, "image": "compactor",
        "suppliers": [{"id": "SUP-WACKER", "name": "Wacker Neuson SE", "unit_price": 28000.0}],
    },

    # ── Seg 23 — Maszyny przemysłowe ─────────────────────────────────────
    {
        "id": "MPR-001", "name": "Tokarka CNC DMG Mori CLX 350 V4",
        "description": "Centrum tokarskie CNC z osią Y. UNSPSC 23111500.",
        "price": 420000.0, "category": "industrial_mach", "delivery_days": 90,
        "weight_kg": 4500.0, "unit": "szt", "requires_approval": True, "image": "cnc",
        "suppliers": [{"id": "SUP-DMG", "name": "DMG Mori Polska", "unit_price": 420000.0}],
    },
    {
        "id": "MPR-002", "name": "Spawarka MIG/MAG Fronius TPS 320i",
        "description": "Spawarka inwertorowa 320A synergiczna. UNSPSC 23161500.",
        "price": 18500.0, "category": "industrial_mach", "delivery_days": 7,
        "weight_kg": 35.0, "unit": "szt", "requires_approval": True, "image": "welder",
        "suppliers": [{"id": "SUP-FRONIUS", "name": "Fronius International GmbH", "unit_price": 18500.0},
                      {"id": "SUP-LINCOLN", "name": "Lincoln Electric Europe", "unit_price": 17800.0}],
    },
    {
        "id": "MPR-003", "name": "Sprężarka śrubowa Atlas Copco GA 30+ FF",
        "description": "Kompresor 30kW z osuszaczem. UNSPSC 23101500.",
        "price": 65000.0, "category": "industrial_mach", "delivery_days": 21,
        "weight_kg": 680.0, "unit": "szt", "requires_approval": True, "image": "compressor",
        "suppliers": [{"id": "SUP-ATLAS", "name": "Atlas Copco Polska", "unit_price": 65000.0}],
    },

    # ── Seg 31 — Łożyska, uszczelki, napędy ─────────────────────────────
    {
        "id": "LOZ-001", "name": "Łożysko kulkowe SKF 6205-2RS1",
        "description": "Łożysko kulkowe jednorzędowe 25x52x15mm. UNSPSC 31121500.",
        "price": 28.0, "category": "bearings", "delivery_days": 1,
        "weight_kg": 0.13, "unit": "szt", "requires_approval": False, "image": "bearing",
        "suppliers": [{"id": "SUP-SKF", "name": "SKF Polska", "unit_price": 28.0},
                      {"id": "SUP-FAG", "name": "Schaeffler (INA/FAG)", "unit_price": 26.50}],
    },
    {
        "id": "LOZ-002", "name": "Pasek zębaty Gates PowerGrip HTD 8M-1200",
        "description": "Pasek napędowy synchroniczny HTD. UNSPSC 31291500.",
        "price": 145.0, "category": "bearings", "delivery_days": 3,
        "weight_kg": 0.5, "unit": "szt", "requires_approval": False, "image": "timing-belt",
        "suppliers": [{"id": "SUP-GATES", "name": "Gates Europe", "unit_price": 145.0}],
    },
    {
        "id": "LOZ-003", "name": "O-ring Viton FPM 50x3mm 100szt",
        "description": "Uszczelka oringowa chemoodporna. UNSPSC 31271500.",
        "price": 210.0, "category": "bearings", "delivery_days": 2,
        "weight_kg": 0.3, "unit": "opak", "requires_approval": False, "image": "oring",
        "suppliers": [{"id": "SUP-TRELLEBORG", "name": "Trelleborg Sealing", "unit_price": 210.0},
                      {"id": "SUP-FREUDENBERG", "name": "Freudenberg Sealing", "unit_price": 205.0}],
    },

    # ── Seg 32 — Komponenty elektroniczne ────────────────────────────────
    {
        "id": "SEM-001", "name": "Mikrokontroler STM32F407VGT6 10szt",
        "description": "MCU ARM Cortex-M4 168MHz 1MB Flash. UNSPSC 32101500.",
        "price": 280.0, "category": "semiconductors", "delivery_days": 7,
        "weight_kg": 0.05, "unit": "opak", "requires_approval": False, "image": "mcu",
        "suppliers": [{"id": "SUP-FARNELL", "name": "Farnell / element14", "unit_price": 280.0},
                      {"id": "SUP-MOUSER", "name": "Mouser Electronics", "unit_price": 275.0}],
    },
    {
        "id": "SEM-002", "name": "Kondensator elektrolityczny 100uF 50V 50szt",
        "description": "Kondensator aluminiowy 105°C. UNSPSC 32121500.",
        "price": 35.0, "category": "semiconductors", "delivery_days": 3,
        "weight_kg": 0.1, "unit": "opak", "requires_approval": False, "image": "capacitor",
        "suppliers": [{"id": "SUP-TME", "name": "TME Electronic Components", "unit_price": 35.0}],
    },

    # ── Seg 39 — Oświetlenie ─────────────────────────────────────────────
    {
        "id": "LMP-001", "name": "Oprawa LED przemysłowa Philips BY121P 150W",
        "description": "Highbay LED 20000lm IP65 do hali. UNSPSC 39111500.",
        "price": 890.0, "category": "lighting", "delivery_days": 5,
        "weight_kg": 4.5, "unit": "szt", "requires_approval": False, "image": "highbay",
        "suppliers": [{"id": "SUP-PHILIPS", "name": "Signify (Philips Lighting)", "unit_price": 890.0},
                      {"id": "SUP-OSRAM", "name": "Ledvance (OSRAM)", "unit_price": 850.0}],
    },
    {
        "id": "LMP-002", "name": "Lampa awaryjna LED 3W 1h IP65",
        "description": "Oprawa ewakuacyjna z piktogramem. UNSPSC 39121500.",
        "price": 120.0, "category": "lighting", "delivery_days": 3,
        "weight_kg": 0.6, "unit": "szt", "requires_approval": False, "image": "emergency",
        "suppliers": [{"id": "SUP-HYUNDAI", "name": "Hyundai Lighting Europe", "unit_price": 120.0}],
    },

    # ── Seg 45 — Drukarki i sprzęt foto/audio ───────────────────────────
    {
        "id": "PRN-001", "name": "Drukarka laserowa HP LaserJet Pro M404dn",
        "description": "Drukarka mono A4 40str/min duplex LAN. UNSPSC 45101500.",
        "price": 1250.0, "category": "printing_equip", "delivery_days": 3,
        "weight_kg": 12.0, "unit": "szt", "requires_approval": False, "image": "printer",
        "suppliers": [{"id": "SUP-ALSO", "name": "Also Polska (HP)", "unit_price": 1250.0},
                      {"id": "SUP-AB", "name": "AB S.A. Wrocław", "unit_price": 1220.0}],
    },
    {
        "id": "PRN-002", "name": "Projektor Epson EB-992F Full HD 4000lm",
        "description": "Projektor do sal konferencyjnych WiFi. UNSPSC 45111600.",
        "price": 3200.0, "category": "printing_equip", "delivery_days": 5,
        "weight_kg": 3.6, "unit": "szt", "requires_approval": True, "image": "projector",
        "suppliers": [{"id": "SUP-AB", "name": "AB S.A. Wrocław (Epson)", "unit_price": 3200.0}],
    },

    # ── Seg 48 — Sport i rekreacja ───────────────────────────────────────
    {
        "id": "SPR-001", "name": "Stół do ping-ponga Sponeta S6-13i",
        "description": "Stół turniejowy do świetlicy pracowniczej. UNSPSC 49201500.",
        "price": 3800.0, "category": "sports", "delivery_days": 10,
        "weight_kg": 95.0, "unit": "szt", "requires_approval": True, "image": "table-tennis",
        "suppliers": [{"id": "SUP-SPORTPLUS", "name": "Decathlon Pro B2B", "unit_price": 3800.0}],
    },
    {
        "id": "SPR-002", "name": "Rower miejski Kross Trans 4.0 28\"",
        "description": "Rower do programu Bike2Work. UNSPSC 25141500.",
        "price": 2400.0, "category": "sports", "delivery_days": 7,
        "weight_kg": 15.0, "unit": "szt", "requires_approval": True, "image": "bicycle",
        "suppliers": [{"id": "SUP-KROSS", "name": "Kross S.A.", "unit_price": 2400.0}],
    },

    # ── Seg 51 — Farmaceutyki ────────────────────────────────────────────
    {
        "id": "PHA-001", "name": "Apteczka zakładowa DIN 13169 (duża)",
        "description": "Apteczka przemysłowa >50 pracowników z wyposażeniem. UNSPSC 42172000.",
        "price": 320.0, "category": "pharma", "delivery_days": 3,
        "weight_kg": 3.5, "unit": "szt", "requires_approval": False, "image": "firstaid",
        "suppliers": [{"id": "SUP-MEDLINE", "name": "Medline Industries (PL)", "unit_price": 320.0}],
    },
    {
        "id": "PHA-002", "name": "Plaster opatrunkowy Hartmann Omniplast 5mx2.5cm 12szt",
        "description": "Plaster na tkaninie do szafki apteczki. UNSPSC 42311500.",
        "price": 65.0, "category": "pharma", "delivery_days": 2,
        "weight_kg": 0.5, "unit": "opak", "requires_approval": False, "image": "plaster",
        "suppliers": [{"id": "SUP-HARTMANN", "name": "Paul Hartmann Polska", "unit_price": 65.0}],
    },

    # ── Seg 52 — AGD ─────────────────────────────────────────────────────
    {
        "id": "AGD-001", "name": "Zmywarka Bosch SMS4HVW33E 60cm A++",
        "description": "Zmywarka wolnostojąca do kuchni biurowej. UNSPSC 52141500.",
        "price": 2400.0, "category": "appliances", "delivery_days": 5,
        "weight_kg": 48.0, "unit": "szt", "requires_approval": True, "image": "dishwasher",
        "suppliers": [{"id": "SUP-BSHG", "name": "BSH Sprzęt Gosp. Dom. (Bosch)", "unit_price": 2400.0}],
    },
    {
        "id": "AGD-002", "name": "Lodówka Samsung RT38CG6624S9 375L",
        "description": "Lodówka do pokoju socjalnego A++. UNSPSC 52141500.",
        "price": 2800.0, "category": "appliances", "delivery_days": 5,
        "weight_kg": 62.0, "unit": "szt", "requires_approval": True, "image": "fridge",
        "suppliers": [{"id": "SUP-SAMSUNG", "name": "Samsung Electronics Polska", "unit_price": 2800.0}],
    },

    # ── Seg 53 — Odzież robocza ──────────────────────────────────────────
    {
        "id": "ODZ-001", "name": "Kombinezon roboczy Mascot Bonn 12012-098 granatowy",
        "description": "Kombinezon dwuczęściowy bawełna/poliester. UNSPSC 53101500.",
        "price": 185.0, "category": "clothing", "delivery_days": 5,
        "weight_kg": 1.2, "unit": "szt", "requires_approval": False, "image": "coverall",
        "suppliers": [{"id": "SUP-MASCOT", "name": "Mascot International (DK)", "unit_price": 185.0},
                      {"id": "SUP-POLTEX", "name": "Poltex Sp. z o.o.", "unit_price": 175.0}],
    },
    {
        "id": "ODZ-002", "name": "Koszulka polo firmowa z haftem logo 50szt",
        "description": "Polo bawełna 210g z logo firmy. UNSPSC 53101600.",
        "price": 1250.0, "category": "clothing", "delivery_days": 14,
        "weight_kg": 12.0, "unit": "50szt", "requires_approval": True, "image": "polo",
        "suppliers": [{"id": "SUP-PROMOSTARS", "name": "Promostars (Stedman)", "unit_price": 1250.0}],
    },

    # ── Seg 55 — Wydawnictwa ─────────────────────────────────────────────
    {
        "id": "PUB-001", "name": "Prenumerata roczna Dziennik Gazeta Prawna",
        "description": "Prenumerata dziennika z serwisem online. UNSPSC 55101500.",
        "price": 960.0, "category": "publications", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": False, "image": "newspaper",
        "suppliers": [{"id": "SUP-INFOR", "name": "Infor PL S.A.", "unit_price": 960.0}],
    },
    {
        "id": "PUB-002", "name": "Norma PN-EN ISO 9001:2015 (PDF)",
        "description": "Licencja elektroniczna normy jakości. UNSPSC 55111500.",
        "price": 185.0, "category": "publications", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "lic", "requires_approval": False, "image": "standard",
        "suppliers": [{"id": "SUP-PKN", "name": "Polski Komitet Normalizacyjny", "unit_price": 185.0}],
    },

    # ── Seg 60 — Budynki prefabrykowane ──────────────────────────────────
    {
        "id": "PRE-001", "name": "Kontener biurowy 6x2.4m z klimatyzacją",
        "description": "Kontener modułowy biurowy wyposażony. UNSPSC 60101000.",
        "price": 28000.0, "category": "prefab", "delivery_days": 21,
        "weight_kg": 2800.0, "unit": "szt", "requires_approval": True, "image": "container",
        "suppliers": [{"id": "SUP-CONTAINEX", "name": "Containex Container-Handels GmbH", "unit_price": 28000.0},
                      {"id": "SUP-ALGECO", "name": "Algeco Polska", "unit_price": 26500.0}],
    },
    {
        "id": "PRE-002", "name": "Wiata magazynowa stalowa 10x20m",
        "description": "Hala namiotowa z konstrukcją stalową. UNSPSC 60103900.",
        "price": 85000.0, "category": "prefab", "delivery_days": 30,
        "weight_kg": 5000.0, "unit": "szt", "requires_approval": True, "image": "warehouse",
        "suppliers": [{"id": "SUP-INSTAL", "name": "Instal-Projekt S.A.", "unit_price": 85000.0}],
    },

    # ── Seg 72 — Usługi budowlane ────────────────────────────────────────
    {
        "id": "USB-001", "name": "Malowanie biura 200m² (ściany + sufit)",
        "description": "Usługa malowania z materiałem farba Dulux. UNSPSC 72131500.",
        "price": 6800.0, "category": "construction_svc", "delivery_days": 5,
        "weight_kg": 0.0, "unit": "usługa", "requires_approval": True, "image": "painting",
        "suppliers": [{"id": "SUP-SKANSKA", "name": "Skanska Polska", "unit_price": 6800.0}],
    },
    {
        "id": "USB-002", "name": "Wymiana posadzki epoksydowej 500m²",
        "description": "Wykonanie posadzki żywicznej w hali produkcyjnej. UNSPSC 72111200.",
        "price": 42000.0, "category": "construction_svc", "delivery_days": 14,
        "weight_kg": 0.0, "unit": "usługa", "requires_approval": True, "image": "flooring",
        "suppliers": [{"id": "SUP-STRABAG", "name": "Strabag Polska", "unit_price": 42000.0}],
    },

    # ── Seg 73 — Usługi produkcyjne ──────────────────────────────────────
    {
        "id": "UPR-001", "name": "Cynkowanie ogniowe detali do 6m (1 tona)",
        "description": "Cynkowanie zanurzeniowe wg ISO 1461. UNSPSC 73111500.",
        "price": 3200.0, "category": "production_svc", "delivery_days": 7,
        "weight_kg": 0.0, "unit": "t", "requires_approval": False, "image": "galvanizing",
        "suppliers": [{"id": "SUP-VOESTALPINE", "name": "Voestalpine Böhler Welding", "unit_price": 3200.0}],
    },
    {
        "id": "UPR-002", "name": "Cięcie laserowe CNC blacha do 20mm (100h)",
        "description": "Usługa cięcia laserowego fiber. UNSPSC 73101500.",
        "price": 15000.0, "category": "production_svc", "delivery_days": 10,
        "weight_kg": 0.0, "unit": "100h", "requires_approval": True, "image": "laser",
        "suppliers": [{"id": "SUP-TRUMPF", "name": "Trumpf Polska", "unit_price": 15000.0}],
    },

    # ── Seg 76/77 — Usługi środowiskowe ──────────────────────────────────
    {
        "id": "ENV-001", "name": "Wywóz odpadów przemysłowych kontener 7m³",
        "description": "Odbiór i utylizacja odpadów zmieszanych. UNSPSC 76111500.",
        "price": 850.0, "category": "environmental", "delivery_days": 1,
        "weight_kg": 0.0, "unit": "kontener", "requires_approval": False, "image": "waste",
        "suppliers": [{"id": "SUP-REMONDIS", "name": "Remondis Polska", "unit_price": 850.0},
                      {"id": "SUP-VEOLIA", "name": "Veolia Polska", "unit_price": 820.0}],
    },
    {
        "id": "ENV-002", "name": "Raport środowiskowy + pomiar emisji",
        "description": "Opracowanie raportu ESG z pomiarem emisji GHG. UNSPSC 77101500.",
        "price": 8500.0, "category": "environmental", "delivery_days": 21,
        "weight_kg": 0.0, "unit": "raport", "requires_approval": True, "image": "environment",
        "suppliers": [{"id": "SUP-SGS", "name": "SGS Polska", "unit_price": 8500.0},
                      {"id": "SUP-BUREAU", "name": "Bureau Veritas Polska", "unit_price": 8200.0}],
    },

    # ── Seg 81 — Usługi inżynieryjne ────────────────────────────────────
    {
        "id": "UIN-001", "name": "Projekt instalacji elektrycznej NN obiekt 2000m²",
        "description": "Dokumentacja projektowa instalacji siłowej i oświetlenia. UNSPSC 81101500.",
        "price": 18000.0, "category": "engineering_svc", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "projekt", "requires_approval": True, "image": "blueprint",
        "suppliers": [{"id": "SUP-SWECO", "name": "Sweco Polska", "unit_price": 18000.0}],
    },
    {
        "id": "UIN-002", "name": "Usługa outsourcing IT helpdesk L1/L2 (miesięcznie)",
        "description": "Wsparcie IT 8/5 do 50 użytkowników. UNSPSC 81111500.",
        "price": 8500.0, "category": "engineering_svc", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "mies", "requires_approval": True, "image": "helpdesk",
        "suppliers": [{"id": "SUP-ATOS", "name": "Atos Polska", "unit_price": 8500.0},
                      {"id": "SUP-COMPUTACENTER", "name": "Computacenter AG", "unit_price": 8200.0}],
    },

    # ── Seg 83 — Media i komunalne ───────────────────────────────────────
    {
        "id": "UTL-001", "name": "Energia elektryczna taryfa C21 (MWh)",
        "description": "Dostawa energii elektrycznej dla firm. UNSPSC 83101500.",
        "price": 680.0, "category": "utilities", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "MWh", "requires_approval": True, "image": "electricity",
        "suppliers": [{"id": "SUP-PGE", "name": "PGE Obrót S.A.", "unit_price": 680.0},
                      {"id": "SUP-TAURON", "name": "Tauron Sprzedaż", "unit_price": 670.0},
                      {"id": "SUP-ENEA", "name": "Enea S.A.", "unit_price": 675.0}],
    },
    {
        "id": "UTL-002", "name": "Gaz ziemny GZ-50 taryfa W-5 (MWh)",
        "description": "Dostawa gazu ziemnego wysokometanowego. UNSPSC 83111500.",
        "price": 290.0, "category": "utilities", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "MWh", "requires_approval": True, "image": "gas",
        "suppliers": [{"id": "SUP-PGNIG", "name": "PGNiG Obrót Detaliczny", "unit_price": 290.0}],
    },

    # ── Seg 84 — Usługi finansowe ────────────────────────────────────────
    {
        "id": "FIN-001", "name": "Audyt finansowy roczny (spółka średnia)",
        "description": "Badanie sprawozdania finansowego wg MSSF. UNSPSC 84121500.",
        "price": 45000.0, "category": "financial_svc", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "audyt", "requires_approval": True, "image": "audit",
        "suppliers": [{"id": "SUP-KPMG", "name": "KPMG Polska", "unit_price": 45000.0},
                      {"id": "SUP-EY", "name": "EY Polska (Ernst & Young)", "unit_price": 42000.0},
                      {"id": "SUP-PWC", "name": "PwC Polska", "unit_price": 44000.0}],
    },
    {
        "id": "FIN-002", "name": "Polisa ubezpieczeniowa majątkowa (rok)",
        "description": "OC + mienie + all-risk zakład produkcyjny. UNSPSC 84131500.",
        "price": 28000.0, "category": "financial_svc", "delivery_days": 7,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "insurance",
        "suppliers": [{"id": "SUP-PZU", "name": "PZU S.A.", "unit_price": 28000.0},
                      {"id": "SUP-WARTA", "name": "TUiR Warta S.A.", "unit_price": 26500.0},
                      {"id": "SUP-ALLIANZ", "name": "Allianz Polska", "unit_price": 27000.0}],
    },

    # ── Seg 85 — Usługi zdrowotne ────────────────────────────────────────
    {
        "id": "ZDR-002", "name": "Medycyna pracy — pakiet badań okresowych (50 os.)",
        "description": "Badania wstępne/okresowe pracowników. UNSPSC 85101500.",
        "price": 7500.0, "category": "healthcare_svc", "delivery_days": 14,
        "weight_kg": 0.0, "unit": "pakiet", "requires_approval": True, "image": "medical-check",
        "suppliers": [{"id": "SUP-LUX", "name": "LUX MED Sp. z o.o.", "unit_price": 7500.0},
                      {"id": "SUP-MEDICOVER", "name": "Medicover Polska", "unit_price": 7200.0}],
    },
    {
        "id": "ZDR-003", "name": "Pakiet prywatnej opieki medycznej (50 os./rok)",
        "description": "Abonament medyczny Comfort dla pracowników. UNSPSC 85121500.",
        "price": 42000.0, "category": "healthcare_svc", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "healthcare",
        "suppliers": [{"id": "SUP-LUX", "name": "LUX MED Sp. z o.o.", "unit_price": 42000.0},
                      {"id": "SUP-MEDICOVER", "name": "Medicover Polska", "unit_price": 40000.0},
                      {"id": "SUP-ENEL", "name": "Enel-Med S.A.", "unit_price": 38000.0}],
    },

    # ── Seg 90 — Podróże i eventy ────────────────────────────────────────
    {
        "id": "TRV-001", "name": "Konferencja firmowa 100 os. (hotel + catering 2 dni)",
        "description": "Organizacja eventu z salą konferencyjną. UNSPSC 90101500.",
        "price": 65000.0, "category": "travel", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "event", "requires_approval": True, "image": "conference",
        "suppliers": [{"id": "SUP-ACCOR", "name": "Accor Hotels (Novotel/Mercure)", "unit_price": 65000.0},
                      {"id": "SUP-MARRIOTT", "name": "Marriott International", "unit_price": 72000.0}],
    },
    {
        "id": "TRV-002", "name": "Bilety lotnicze Europa r/t 20 podróży",
        "description": "Kontyngent biletów lotniczych dla handlowców. UNSPSC 90121500.",
        "price": 24000.0, "category": "travel", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "pakiet", "requires_approval": True, "image": "flights",
        "suppliers": [{"id": "SUP-WTUR", "name": "Weco Travel (TMC)", "unit_price": 24000.0},
                      {"id": "SUP-BCD", "name": "BCD Travel Poland", "unit_price": 23000.0}],
    },

    # ── Seg 25 — Pojazdy i flota ─────────────────────────────────────────
    {
        "id": "VEH-001", "name": "Skoda Octavia Combi 2.0 TDI Style",
        "description": "Samochód osobowy kombi 150KM DSG, klasa C. Flota handlowców. UNSPSC 25101500.",
        "price": 142000.0, "category": "vehicles", "delivery_days": 90,
        "weight_kg": 1450.0, "unit": "szt", "requires_approval": True, "image": "car",
        "suppliers": [{"id": "SUP-SKODA", "name": "Skoda Auto Polska", "unit_price": 142000.0},
                      {"id": "SUP-PORSCHE-INT", "name": "Porsche Inter Auto Polska", "unit_price": 140500.0}],
    },
    {
        "id": "VEH-002", "name": "Toyota Corolla 1.8 Hybrid Comfort",
        "description": "Samochód osobowy sedan hybrid 140KM, klasa C. UNSPSC 25101500.",
        "price": 128000.0, "category": "vehicles", "delivery_days": 60,
        "weight_kg": 1370.0, "unit": "szt", "requires_approval": True, "image": "car",
        "suppliers": [{"id": "SUP-TOYOTA", "name": "Toyota Motor Poland", "unit_price": 128000.0},
                      {"id": "SUP-TOYOTA-FLEET", "name": "Toyota Fleet (Kinto)", "unit_price": 126500.0}],
    },
    {
        "id": "VEH-003", "name": "Volkswagen Transporter T6.1 2.0 TDI L2H1",
        "description": "Samochód dostawczy furgon 150KM, ładowność 1.3t. UNSPSC 25101900.",
        "price": 185000.0, "category": "vehicles", "delivery_days": 120,
        "weight_kg": 1950.0, "unit": "szt", "requires_approval": True, "image": "van",
        "suppliers": [{"id": "SUP-VW-SAMOCHODY", "name": "Volkswagen Samochody Dostawcze", "unit_price": 185000.0}],
    },
    {
        "id": "VEH-004", "name": "Mercedes-Benz Sprinter 314 CDI furgon L3H2",
        "description": "Dostawczy 2.0 diesel 143KM, ładowność 1.5t, V=14m³. UNSPSC 25101900.",
        "price": 225000.0, "category": "vehicles", "delivery_days": 90,
        "weight_kg": 2150.0, "unit": "szt", "requires_approval": True, "image": "sprinter",
        "suppliers": [{"id": "SUP-MERCEDES", "name": "Mercedes-Benz Polska (Vans)", "unit_price": 225000.0}],
    },
    {
        "id": "VEH-005", "name": "Iveco Daily 35S16 V 3520 H2 furgon",
        "description": "Furgon dostawczy 160KM Hi-Matic, ładowność 1.6t. UNSPSC 25101900.",
        "price": 198000.0, "category": "vehicles", "delivery_days": 60,
        "weight_kg": 2100.0, "unit": "szt", "requires_approval": True, "image": "van",
        "suppliers": [{"id": "SUP-IVECO", "name": "Iveco Poland", "unit_price": 198000.0}],
    },
    {
        "id": "VEH-006", "name": "MAN TGE 3.180 skrzyniowy 4x2",
        "description": "Samochód dostawczy z zabudową skrzyniową 3.5t. UNSPSC 25101900.",
        "price": 210000.0, "category": "vehicles", "delivery_days": 90,
        "weight_kg": 2300.0, "unit": "szt", "requires_approval": True, "image": "truck",
        "suppliers": [{"id": "SUP-MAN", "name": "MAN Truck & Bus Polska", "unit_price": 210000.0}],
    },
    {
        "id": "VEH-007", "name": "Renault Kangoo Van E-Tech Electric",
        "description": "Elektryczny furgon dostawczy 122KM, zasięg 300km. UNSPSC 25101500.",
        "price": 165000.0, "category": "vehicles", "delivery_days": 60,
        "weight_kg": 1800.0, "unit": "szt", "requires_approval": True, "image": "ev-van",
        "suppliers": [{"id": "SUP-RENAULT", "name": "Renault Polska", "unit_price": 165000.0}],
    },
    {
        "id": "VEH-008", "name": "Tesla Model Y Long Range (firmowy)",
        "description": "Samochód elektryczny 533km zasięg, klasa SUV. UNSPSC 25101500.",
        "price": 229000.0, "category": "vehicles", "delivery_days": 30,
        "weight_kg": 1979.0, "unit": "szt", "requires_approval": True, "image": "tesla",
        "suppliers": [{"id": "SUP-TESLA", "name": "Tesla Poland (direct)", "unit_price": 229000.0}],
    },
    {
        "id": "VEH-009", "name": "Volvo FH 460 ciągnik siodłowy 4x2",
        "description": "Ciągnik siodłowy Euro 6 do transportu ciężkiego. UNSPSC 25101700.",
        "price": 520000.0, "category": "vehicles", "delivery_days": 120,
        "weight_kg": 7800.0, "unit": "szt", "requires_approval": True, "image": "truck",
        "suppliers": [{"id": "SUP-VOLVO-TRUCKS", "name": "Volvo Trucks Polska", "unit_price": 520000.0}],
    },
    {
        "id": "VEH-010", "name": "DAF XF 480 FT ciągnik siodłowy",
        "description": "Ciągnik siodłowy 13L PACCAR MX-13 Euro 6. UNSPSC 25101700.",
        "price": 495000.0, "category": "vehicles", "delivery_days": 90,
        "weight_kg": 7500.0, "unit": "szt", "requires_approval": True, "image": "truck",
        "suppliers": [{"id": "SUP-DAF", "name": "DAF Trucks Polska", "unit_price": 495000.0}],
    },
    {
        "id": "VEH-011", "name": "Wózek widłowy Toyota Tonero 2.5t diesel",
        "description": "Wózek widłowy czołowy 2.5t podnoszenie 4.7m. UNSPSC 24112200.",
        "price": 125000.0, "category": "vehicles", "delivery_days": 30,
        "weight_kg": 4200.0, "unit": "szt", "requires_approval": True, "image": "forklift",
        "suppliers": [{"id": "SUP-TOYOTA-MH", "name": "Toyota Material Handling Polska", "unit_price": 125000.0}],
    },
    {
        "id": "VEH-012", "name": "Wózek widłowy Linde E20 elektryczny",
        "description": "Wózek elektryczny 2.0t z baterią Li-Ion 80V. UNSPSC 24112200.",
        "price": 145000.0, "category": "vehicles", "delivery_days": 45,
        "weight_kg": 3800.0, "unit": "szt", "requires_approval": True, "image": "forklift-elec",
        "suppliers": [{"id": "SUP-LINDE", "name": "Linde Material Handling Polska", "unit_price": 145000.0},
                      {"id": "SUP-STILL", "name": "STILL Polska (KION Group)", "unit_price": 142000.0}],
    },
    {
        "id": "VEH-013", "name": "Przyczepa ciężarowa Wielton NS-3 Mega",
        "description": "Naczepa kurtynowa 13.6m 24t ładowności. UNSPSC 25181800.",
        "price": 135000.0, "category": "vehicles", "delivery_days": 60,
        "weight_kg": 7200.0, "unit": "szt", "requires_approval": True, "image": "trailer",
        "suppliers": [{"id": "SUP-WIELTON", "name": "Wielton S.A.", "unit_price": 135000.0},
                      {"id": "SUP-KRONE", "name": "Krone Trailer GmbH", "unit_price": 142000.0}],
    },
    {
        "id": "VEH-014", "name": "Quad Polaris Sportsman 570 EPS (teren zakładowy)",
        "description": "ATV do przemieszczania się na terenie zakładu. UNSPSC 25172000.",
        "price": 42000.0, "category": "vehicles", "delivery_days": 14,
        "weight_kg": 320.0, "unit": "szt", "requires_approval": True, "image": "quad",
        "suppliers": [{"id": "SUP-POLARIS", "name": "Polaris Poland", "unit_price": 42000.0}],
    },

    # ── Leasing i Fleet Management ───────────────────────────────────────
    {
        "id": "FLT-001", "name": "Leasing operacyjny Skoda Octavia 36 mies.",
        "description": "Full-service leasing z ubezpieczeniem, serwisem, oponami. UNSPSC 80151500.",
        "price": 2850.0, "category": "fleet_svc", "delivery_days": 14,
        "weight_kg": 0.0, "unit": "mies", "requires_approval": True, "image": "leasing",
        "suppliers": [{"id": "SUP-ARVAL", "name": "Arval Service Lease Polska", "unit_price": 2850.0},
                      {"id": "SUP-LEASEPLAN", "name": "LeasePlan Polska", "unit_price": 2900.0},
                      {"id": "SUP-ALD", "name": "ALD Automotive Polska", "unit_price": 2800.0}],
    },
    {
        "id": "FLT-002", "name": "Leasing elektryka — Tesla Model Y 48 mies.",
        "description": "Leasing z ładowaniem i serwisem EV. UNSPSC 80151500.",
        "price": 4200.0, "category": "fleet_svc", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "mies", "requires_approval": True, "image": "ev-leasing",
        "suppliers": [{"id": "SUP-ARVAL", "name": "Arval Service Lease Polska", "unit_price": 4200.0},
                      {"id": "SUP-ALPHABET", "name": "Alphabet Polska (BMW Group)", "unit_price": 4100.0}],
    },
    {
        "id": "FLT-003", "name": "Zarządzanie flotą GPS — 50 pojazdów (rok)",
        "description": "Monitoring GPS + telematyka + raporty paliwowe. UNSPSC 80151600.",
        "price": 18000.0, "category": "fleet_svc", "delivery_days": 7,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "fleet-gps",
        "suppliers": [{"id": "SUP-WEBFLEET", "name": "Webfleet (Bridgestone)", "unit_price": 18000.0},
                      {"id": "SUP-GPSONE", "name": "Navifleet Sp. z o.o.", "unit_price": 15000.0}],
    },
    {
        "id": "FLT-004", "name": "Karty paliwowe Orlen 100 szt (flota)",
        "description": "Program kart paliwowych z raportowaniem. UNSPSC 15121500.",
        "price": 0.0, "category": "fleet_svc", "delivery_days": 7,
        "weight_kg": 0.0, "unit": "aktywacja", "requires_approval": True, "image": "fuel-card",
        "suppliers": [{"id": "SUP-ORLEN", "name": "Orlen Flota", "unit_price": 0.0},
                      {"id": "SUP-BP", "name": "BP Fleet Solutions", "unit_price": 0.0},
                      {"id": "SUP-SHELL", "name": "Shell Fleet Solutions", "unit_price": 0.0}],
    },
    {
        "id": "FLT-005", "name": "Wynajem krótkoterminowy — furgon 3.5t (30 dni)",
        "description": "Wynajem na okres wzmożonych dostaw. UNSPSC 78111800.",
        "price": 4500.0, "category": "fleet_svc", "delivery_days": 1,
        "weight_kg": 0.0, "unit": "30 dni", "requires_approval": True, "image": "rental",
        "suppliers": [{"id": "SUP-EUROPCAR", "name": "Europcar Polska", "unit_price": 4500.0},
                      {"id": "SUP-HERTZ", "name": "Hertz Polska", "unit_price": 4800.0},
                      {"id": "SUP-AVIS", "name": "Avis Budget Group PL", "unit_price": 4600.0}],
    },

    # ── Seg 10 — Rośliny, zieleń, ogrodnictwo ───────────────────────────
    {
        "id": "ZIE-001", "name": "Drzewka ozdobne thuja Brabant 180cm 20szt",
        "description": "Żywopłot iglasty do terenu zakładowego. UNSPSC 10151500.",
        "price": 1200.0, "category": "horticulture", "delivery_days": 7,
        "weight_kg": 80.0, "unit": "20szt", "requires_approval": False, "image": "trees",
        "suppliers": [{"id": "SUP-BRUNS", "name": "Bruns Pflanzen (DE)", "unit_price": 1200.0}],
    },
    {
        "id": "ZIE-002", "name": "Rośliny doniczkowe do biura — zestaw 30szt",
        "description": "Rośliny oczyszczające powietrze (fikus, sansewieria, zamia). UNSPSC 10151700.",
        "price": 1800.0, "category": "horticulture", "delivery_days": 5,
        "weight_kg": 45.0, "unit": "zestaw", "requires_approval": False, "image": "office-plants",
        "suppliers": [{"id": "SUP-STRELITZIA", "name": "Strelitzia.pl (Green Office)", "unit_price": 1800.0},
                      {"id": "SUP-FLORENSIS", "name": "Florensis Polska", "unit_price": 1650.0}],
    },
    {
        "id": "ZIE-003", "name": "Usługa utrzymania zieleni zakładowej (rok)",
        "description": "Pielęgnacja trawników, żywopłotów, rabat kwiatowych. UNSPSC 70111700.",
        "price": 24000.0, "category": "agri_services", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "gardening",
        "suppliers": [{"id": "SUP-LASY", "name": "Green Service Polska", "unit_price": 24000.0}],
    },

    # ── Seg 56 — Dekoracje, gadżety firmowe ──────────────────────────────
    {
        "id": "GAD-001", "name": "Kubki firmowe ceramiczne z logo 200szt",
        "description": "Kubek 330ml z nadrukiem sublimacyjnym. UNSPSC 56121500.",
        "price": 2400.0, "category": "decorations", "delivery_days": 14,
        "weight_kg": 60.0, "unit": "200szt", "requires_approval": False, "image": "mugs",
        "suppliers": [{"id": "SUP-AXPOL", "name": "Axpol Trading S.A.", "unit_price": 2400.0},
                      {"id": "SUP-PAR", "name": "PAR Sp. z o.o. (gadżety)", "unit_price": 2200.0}],
    },
    {
        "id": "GAD-002", "name": "Powerbank reklamowy 10000mAh z logo 100szt",
        "description": "Powerbank z grawerem laserowym logo. UNSPSC 56121500.",
        "price": 4500.0, "category": "decorations", "delivery_days": 21,
        "weight_kg": 25.0, "unit": "100szt", "requires_approval": True, "image": "powerbank",
        "suppliers": [{"id": "SUP-AXPOL", "name": "Axpol Trading S.A.", "unit_price": 4500.0}],
    },
    {
        "id": "GAD-003", "name": "Choinka bożonarodzeniowa sztuczna 220cm + dekoracje",
        "description": "Choinka premium do recepcji z bombkami firmowymi. UNSPSC 56101500.",
        "price": 850.0, "category": "decorations", "delivery_days": 7,
        "weight_kg": 15.0, "unit": "zestaw", "requires_approval": False, "image": "xmas-tree",
        "suppliers": [{"id": "SUP-ALLEGRO", "name": "Allegro Business (marketplace)", "unit_price": 850.0}],
    },

    # ── Seg 71 — Usługi wydobywcze / górnicze ────────────────────────────
    {
        "id": "GRN-001", "name": "Badania geotechniczne gruntu (100m odwiertów)",
        "description": "Odwierty geotechniczne + dokumentacja geologiczna. UNSPSC 71121500.",
        "price": 18000.0, "category": "mining_services", "delivery_days": 14,
        "weight_kg": 0.0, "unit": "raport", "requires_approval": True, "image": "geotechnics",
        "suppliers": [{"id": "SUP-GEOTEKO", "name": "Geoteko Sp. z o.o.", "unit_price": 18000.0}],
    },

    # ── Seg 76 — Sprzątanie przemysłowe ──────────────────────────────────
    {
        "id": "SPZ-001", "name": "Usługa sprzątania hali produkcyjnej 2000m² (mies.)",
        "description": "Sprzątanie codzienne z dezynfekcją. UNSPSC 76111500.",
        "price": 8500.0, "category": "industrial_clean", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "mies", "requires_approval": True, "image": "cleaning-svc",
        "suppliers": [{"id": "SUP-ISS", "name": "ISS Facility Services Polska", "unit_price": 8500.0},
                      {"id": "SUP-SODEXO", "name": "Sodexo Polska", "unit_price": 8200.0}],
    },
    {
        "id": "SPZ-002", "name": "Usługa sprzątania biura 500m² (mies.)",
        "description": "Sprzątanie 5x/tydzień, mycie okien co miesiąc. UNSPSC 76111500.",
        "price": 3200.0, "category": "industrial_clean", "delivery_days": 0,
        "weight_kg": 0.0, "unit": "mies", "requires_approval": True, "image": "office-clean",
        "suppliers": [{"id": "SUP-ISS", "name": "ISS Facility Services Polska", "unit_price": 3200.0},
                      {"id": "SUP-IMPEL", "name": "Impel Facility Services", "unit_price": 3000.0}],
    },

    # ── Seg 95 — Nieruchomości ───────────────────────────────────────────
    {
        "id": "NIE-001", "name": "Wynajem hali magazynowej 1000m² (rok)",
        "description": "Hala klasy A z rampami i ogrzewaniem. UNSPSC 95121500.",
        "price": 240000.0, "category": "real_estate", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "warehouse-rent",
        "suppliers": [{"id": "SUP-PANATTONI", "name": "Panattoni Europe", "unit_price": 240000.0},
                      {"id": "SUP-PROLOGIS", "name": "Prologis Polska", "unit_price": 235000.0},
                      {"id": "SUP-SEGRO", "name": "SEGRO Logistics", "unit_price": 238000.0}],
    },
    {
        "id": "NIE-002", "name": "Wynajem biura 200m² centrum Warszawa (rok)",
        "description": "Biuro klasy A+ z recepcją i parkingiem. UNSPSC 95121600.",
        "price": 360000.0, "category": "real_estate", "delivery_days": 30,
        "weight_kg": 0.0, "unit": "rok", "requires_approval": True, "image": "office-rent",
        "suppliers": [{"id": "SUP-JLL", "name": "JLL Poland", "unit_price": 360000.0},
                      {"id": "SUP-CBRE", "name": "CBRE Poland", "unit_price": 355000.0},
                      {"id": "SUP-SAVILLS", "name": "Savills Polska", "unit_price": 358000.0}],
    },
]

# Pre-index
_CATALOG_BY_ID = {p["id"]: p for p in CATALOG}

BUNDLE_CABLE_ID = "BUNDLE-CAB"


def get_catalog(category: str | None = None) -> list[dict]:
    """Return catalog items, optionally filtered by category.
    Tries DB first (catalog_items table), falls back to hardcoded CATALOG."""
    try:
        from app.database import DB_AVAILABLE, _get_client, db_list_catalog
        if DB_AVAILABLE:
            client = _get_client()
            db_items = db_list_catalog(client, category)
            if db_items:
                return db_items
    except Exception:
        pass
    # Fallback to hardcoded catalog
    items = [p for p in CATALOG if not p.get("_is_bundle_source")]
    if category:
        items = [p for p in items if p["category"] == category]
    return items


def get_categories() -> list[dict]:
    return CATEGORIES


_PL_DIACRITICS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def _normalize(s: str) -> str:
    return (s or "").translate(_PL_DIACRITICS).lower().strip()


def search_catalog(query: str, limit: int = 5) -> list[dict]:
    """Fuzzy-match catalog items by keyword, used by the AI copilot to resolve
    phrases like "klocki hamulcowe Bosch" into concrete product IDs.

    Scoring: name substring > description substring > category substring.
    Each distinct token of the query adds to the total so multi-word queries
    rank items matching more tokens higher. Items with score == 0 are excluded.
    Returned items carry an extra "_score" field for debugging/telemetry.
    """
    if not query or not query.strip():
        return []
    items = get_catalog(None)
    tokens = [t for t in _normalize(query).split() if len(t) >= 2]
    if not tokens:
        return []
    scored: list[tuple[float, dict]] = []
    for p in items:
        name = _normalize(p.get("name", ""))
        desc = _normalize(p.get("description", ""))
        cat = _normalize(p.get("category", ""))
        score = 0.0
        for tok in tokens:
            # Exact substring hit
            if tok in name:
                score += 3.0
            elif len(tok) >= 4 and _prefix_hit(name, tok):
                # Polish inflection: "hamulce" ~ "hamulcowe" via shared stem
                score += 2.0
            if tok in desc:
                score += 1.5
            elif len(tok) >= 4 and _prefix_hit(desc, tok):
                score += 1.0
            if tok in cat:
                score += 1.0
        if score > 0:
            scored.append((score, {**p, "_score": score}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def _prefix_hit(text: str, token: str) -> bool:
    """True if any word in text shares a >= 4-char stem with token
    (handles Polish inflection: 'hamulce' ~ 'hamulcowe')."""
    if len(token) < 4:
        return False
    stem = token[: max(4, len(token) - 2)]
    for word in text.split():
        if len(word) < 4:
            continue
        # Forward match: 'hamulcowe' starts with 'hamul' (stem of 'hamulce')
        if word.startswith(stem):
            return True
        # Reverse match: catches 'klocki' token vs 'klockow' text word.
        # Require the shared prefix to be at least 4 chars so 'na' vs 'naddzw'
        # does not trigger.
        common = word[:4]
        if stem.startswith(common) and len(common) >= 4:
            return True
    return False


# ── Cart Rules Engine ──────────────────────────────────────────────────────

def calculate_cart_state(raw_items: list[dict]) -> dict:
    """
    Apply 10 business rules to a raw cart.

    Input: [{"id": "BRK-001", "quantity": 4}, ...]
    Output: full cart state with items, totals, errors, warnings, bundles.
    """
    # Resolve items from catalog
    items: list[dict] = []
    for raw in raw_items:
        product = _CATALOG_BY_ID.get(raw["id"])
        if not product:
            continue
        items.append({
            **product,
            "quantity": max(1, int(raw.get("quantity", 1))),
            "_is_forced_bundle": False,
        })

    errors: list[str] = []
    warnings: list[str] = []
    discount = 0.0

    # ── RULE 1: Zestaw akumulatorowy (battery → auto-inject cables) ────
    has_battery = any(i["category"] == "batteries" and i["id"] != BUNDLE_CABLE_ID for i in items)
    cable_in_cart = any(i["id"] == BUNDLE_CABLE_ID for i in items)
    if has_battery and not cable_in_cart:
        cable = _CATALOG_BY_ID.get(BUNDLE_CABLE_ID)
        if cable:
            items.append({**cable, "quantity": 1, "_is_forced_bundle": True})
            warnings.append("Zestaw akumulatorowy: automatycznie dodano kable rozruchowe 600A.")
    elif not has_battery and cable_in_cart:
        items = [i for i in items if i["id"] != BUNDLE_CABLE_ID]

    # ── Calculate subtotal ─────────────────────────────────────────────
    subtotal = sum(i["price"] * i["quantity"] for i in items)

    # ── RULE 2: Minimum logistyczne (500 PLN) ──────────────────────────
    if 0 < subtotal < 500:
        errors.append(f"Minimalna wartość zamówienia to 500 PLN (brakuje {500 - subtotal:.0f} PLN).")

    # ── RULE 3: Oleje w opakowaniach (multiples of 4) ──────────────────
    for i in items:
        if i["category"] == "oils" and i["id"].startswith("OIL-") and i["quantity"] % 4 != 0:
            errors.append(f'{i["name"]}: oleje silnikowe należy zamawiać w wielokrotnościach 4 szt.')

    # ── RULE 4: Promocja oponowa (4+ szt tego samego = 8% rabat) ──────
    for i in items:
        if i["category"] == "tires" and i["quantity"] >= 4:
            sets_of_4 = i["quantity"] // 4
            disc = sets_of_4 * 4 * i["price"] * 0.08
            discount += disc
            warnings.append(f'Promocja oponowa: {sets_of_4} komplet(y) {i["name"][:30]}… → -{disc:.0f} PLN (8%).')

    # ── RULE 5: Komplet opon (nie wielokrotność 4 → warning) ──────────
    for i in items:
        if i["category"] == "tires" and i["quantity"] % 4 != 0:
            warnings.append(f'{i["name"][:30]}…: zalecane zamawianie opon w kompletach po 4 szt.')

    # ── RULE 6: Rabat ilościowy na opakowania (10+ szt → 12%) ─────────
    for i in items:
        if i["category"] == "packaging" and i["quantity"] >= 10:
            disc = i["price"] * i["quantity"] * 0.12
            discount += disc
            warnings.append(f'Rabat ilościowy: {i["name"][:30]}… ({i["quantity"]} szt) → -{disc:.0f} PLN (12%).')

    # ── RULE 7: Approval Workflow (policy-based) ────────────────────────
    # Build a temporary cart_state for evaluation
    _temp_items = []
    for i in items:
        _temp_items.append({
            "id": i["id"], "name": i["name"], "price": i["price"],
            "quantity": i["quantity"], "category": i["category"],
            "line_total": i["price"] * i["quantity"],
            "requires_approval": i.get("requires_approval", False),
        })
    _temp_state = {"subtotal": subtotal, "total_items": sum(i["quantity"] for i in items), "items": _temp_items}
    approval_result = evaluate_approval(_temp_state)
    requires_approval = approval_result["requires_approval"]
    if requires_approval:
        for reason in approval_result["reasons"]:
            warnings.append(f"⚠️ {reason}")

    # ── RULE 8: Limit budżetowy IT (max 25 000 PLN) ───────────────────
    it_total = sum(i["price"] * i["quantity"] for i in items if i["category"] == "it_services")
    if it_total > 25000:
        errors.append(f"Przekroczony limit budżetowy IT: {it_total:,.0f} PLN > 25 000 PLN.")

    # ── RULE 9: Koszty dostawy ─────────────────────────────────────────
    total_weight = sum(i["weight_kg"] * i["quantity"] for i in items)
    if total_weight > 100:
        shipping = 250.0
        warnings.append(f"Fracht ciężki ({total_weight:.0f} kg > 100 kg): koszt dostawy 250 PLN.")
    elif subtotal > 1000:
        shipping = 0.0
        warnings.append("Darmowa dostawa (zamówienie > 1 000 PLN).")
    else:
        shipping = 49.0

    # ── RULE 10: Limit wielkości zamówienia (max 100 szt) ──────────────
    total_qty = sum(i["quantity"] for i in items)
    if total_qty > 100:
        errors.append(f"Przekroczony limit zamówienia: {total_qty} szt > 100 szt.")

    # ── Czas dostawy ──────────────────────────────────────────────────
    delivery_days = max((i["delivery_days"] for i in items), default=0)

    # ── Total ─────────────────────────────────────────────────────────
    total = subtotal - discount + shipping

    # Build clean item list for response
    response_items = []
    for i in items:
        response_items.append({
            "id": i["id"],
            "name": i["name"],
            "price": i["price"],
            "quantity": i["quantity"],
            "category": i["category"],
            "unit": i.get("unit", "szt"),
            "weight_kg": i["weight_kg"],
            "line_total": i["price"] * i["quantity"],
            "is_forced_bundle": i.get("_is_forced_bundle", False),
            "requires_approval": i.get("requires_approval", False),
        })

    return {
        "items": response_items,
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "shipping_fee": round(shipping, 2) if items else 0.0,
        "total": round(total, 2) if items else 0.0,
        "total_weight_kg": round(total_weight, 1),
        "total_items": total_qty,
        "delivery_days": delivery_days,
        "requires_manager_approval": requires_approval,
        "approval": approval_result,
        "errors": errors,
        "warnings": warnings,
        "can_checkout": len(errors) == 0 and len(items) > 0,
    }


def map_cart_to_demand(cart_state: dict) -> dict[str, list[dict]]:
    """
    Map cart items to optimizer demand per domain.

    Returns: {"parts": [DemandItem, ...], "oils": [...], ...}
    """
    demand_by_domain: dict[str, list[dict]] = {}
    for item in cart_state["items"]:
        domain = item["category"]
        if domain not in demand_by_domain:
            demand_by_domain[domain] = []
        demand_by_domain[domain].append({
            "product_id": item["id"],
            "demand_qty": item["quantity"],
            "destination_region": "PL-MA",  # default Kraków hub
        })
    return demand_by_domain


# ── Approval Workflow Engine (Ariba-style) ─────────────────────────────────

_DEFAULT_APPROVAL_POLICIES: dict = {
    "workflow_mode": "sequential",
    "thresholds": [
        {"id": "auto_approve", "name": "Auto-zatwierdzenie", "max_amount": 5000.0, "max_quantity": 50, "approvers": [], "action": "auto_approve", "description": "Zamówienia do 5 000 PLN i 50 szt — automatycznie zatwierdzone"},
        {"id": "manager_approval", "name": "Zatwierdzenie kierownika", "max_amount": 25000.0, "max_quantity": 200, "approvers": ["manager@flowproc.eu"], "action": "require_approval", "description": "Zamówienia 5 001–25 000 PLN — zatwierdzenie kierownika działu"},
        {"id": "director_approval", "name": "Zatwierdzenie dyrektora", "max_amount": 100000.0, "max_quantity": 1000, "approvers": ["manager@flowproc.eu", "director@flowproc.eu"], "action": "require_approval", "description": "Zamówienia 25 001–100 000 PLN — kierownik + dyrektor"},
        {"id": "board_approval", "name": "Zatwierdzenie zarządu", "max_amount": 999999999, "max_quantity": 999999999, "approvers": ["manager@flowproc.eu", "director@flowproc.eu", "cfo@flowproc.eu"], "action": "require_approval", "description": "Zamówienia > 100 000 PLN — kierownik + dyrektor + CFO"},
    ],
    "category_rules": [
        {"category": "it_services", "budget_limit": 25000.0, "extra_approver": "it-manager@flowproc.eu", "description": "IT wymaga dodatkowego zatwierdzenia IT Managera"},
        {"category": "oe_components", "budget_limit": 50000.0, "extra_approver": "quality@flowproc.eu", "description": "Komponenty OE wymagają zatwierdzenia Działu Jakości"},
    ],
    "item_policies": [
        {"id": "high_value_item", "condition": "unit_price > 1000", "action": "flag_approval", "description": "Pozycje > 1 000 PLN/szt wymagają zatwierdzenia"},
        {"id": "catalog_required", "condition": "not_in_catalog", "action": "flag_warning", "description": "Pozycje spoza katalogu — ostrzeżenie compliance"},
    ],
}


def _load_approval_policies() -> dict:
    """Load approval policies from DB, falling back to defaults."""
    try:
        import json as _json
        from app.database import _get_client, db_list_rules
        client = _get_client()
        rows = db_list_rules(client, rule_type="approval_policy")
        if rows:
            config = rows[0].get("config", {})
            if isinstance(config, str):
                config = _json.loads(config)
            return config
    except Exception as e:
        logger.warning("Failed to load approval policies from DB: %s", e)
    return _DEFAULT_APPROVAL_POLICIES.copy()


def _save_approval_policies(policies: dict) -> None:
    """Persist approval policies to DB as a business rule."""
    try:
        import json as _json
        from app.database import _get_client
        client = _get_client()
        config_json = _json.dumps(policies)
        now = datetime.now().isoformat()
        rs = client.execute(
            "UPDATE business_rules SET config=?, updated_at=? WHERE rule_type=? AND rule_key=?",
            [config_json, now, "approval_policy", "default"],
        )
        if rs.rows_affected == 0:
            client.execute(
                "INSERT INTO business_rules (rule_type, rule_key, config, is_active, description, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                ["approval_policy", "default", config_json, 1, "Polityka zatwierdzania zamówień", now, now],
            )
    except Exception as e:
        logger.error("Failed to save approval policies: %s", e)
        raise


def get_approval_policies() -> dict:
    """Return current approval workflow configuration."""
    return _load_approval_policies()


def update_approval_policies(updates: dict) -> dict:
    """Update approval workflow configuration."""
    policies = _load_approval_policies()
    if "workflow_mode" in updates:
        policies["workflow_mode"] = updates["workflow_mode"]
    if "thresholds" in updates:
        policies["thresholds"] = updates["thresholds"]
    if "category_rules" in updates:
        policies["category_rules"] = updates["category_rules"]
    if "item_policies" in updates:
        policies["item_policies"] = updates["item_policies"]
    _save_approval_policies(policies)
    return policies


def evaluate_approval(cart_state: dict) -> dict:
    """
    Evaluate approval requirements for a cart based on current policies.
    Returns approval chain, required approvers, and policy matches.
    """
    subtotal = cart_state.get("subtotal", 0)
    total_items = cart_state.get("total_items", 0)
    items = cart_state.get("items", [])
    policies = _load_approval_policies()

    result = {
        "requires_approval": False,
        "approval_level": "auto_approve",
        "approval_level_name": "Auto-zatwierdzenie",
        "workflow_mode": policies["workflow_mode"],
        "approvers": [],
        "reasons": [],
        "category_flags": [],
        "item_flags": [],
        "policy_matches": [],
    }

    # 1. Amount/quantity threshold check
    for threshold in policies["thresholds"]:
        if subtotal <= threshold["max_amount"] and total_items <= threshold["max_quantity"]:
            result["approval_level"] = threshold["id"]
            result["approval_level_name"] = threshold["name"]
            if threshold["action"] == "require_approval":
                result["requires_approval"] = True
                result["approvers"] = list(threshold["approvers"])
                result["reasons"].append(
                    f"Wartość {subtotal:,.0f} PLN / {total_items} szt "
                    f"→ {threshold['name']}"
                )
            result["policy_matches"].append({
                "policy": threshold["id"],
                "type": "threshold",
                "description": threshold["description"],
            })
            break

    # 2. Category-specific rules
    item_categories = set(i.get("category", "") for i in items)
    for rule in policies.get("category_rules", []):
        if rule["category"] in item_categories:
            cat_total = sum(
                i.get("line_total", 0) for i in items
                if i.get("category") == rule["category"]
            )
            if cat_total > rule.get("budget_limit", float("inf")):
                result["requires_approval"] = True
                result["reasons"].append(
                    f"Kategoria {rule['category']}: {cat_total:,.0f} PLN "
                    f"> limit {rule['budget_limit']:,.0f} PLN"
                )
            if rule.get("extra_approver") and rule["extra_approver"] not in result["approvers"]:
                result["approvers"].append(rule["extra_approver"])
                result["category_flags"].append({
                    "category": rule["category"],
                    "approver": rule["extra_approver"],
                    "description": rule["description"],
                })

    # 3. Item-level policies
    for item in items:
        if item.get("requires_approval"):
            result["requires_approval"] = True
            result["item_flags"].append({
                "item_id": item["id"],
                "item_name": item.get("name", ""),
                "reason": "Produkt wymaga zatwierdzenia (requires_approval)",
            })
            result["reasons"].append(f"Pozycja '{item.get('name', '')[:30]}' wymaga zatwierdzenia")

        # High-value item check
        if item.get("price", 0) > 1000:
            result["item_flags"].append({
                "item_id": item["id"],
                "item_name": item.get("name", ""),
                "reason": f"Cena jednostkowa {item['price']:,.0f} PLN > 1 000 PLN",
            })

    # 4. Build approval chain based on workflow mode
    if result["requires_approval"] and result["approvers"]:
        if policies["workflow_mode"] == "parallel":
            result["approval_chain"] = [{
                "step": 1,
                "type": "parallel",
                "approvers": result["approvers"],
                "description": "Wszyscy zatwierdzają równolegle",
            }]
        else:  # sequential
            result["approval_chain"] = [
                {
                    "step": i + 1,
                    "type": "sequential",
                    "approver": approver,
                    "description": f"Krok {i + 1}: {approver}",
                }
                for i, approver in enumerate(result["approvers"])
            ]
    else:
        result["approval_chain"] = []

    return result


# ── Order Lifecycle ───────────────────────────────────────────────────────

ORDER_STATUSES = [
    "draft",
    "pending_approval",
    "approved",
    "po_generated",
    "confirmed",
    "in_delivery",
    "delivered",
    "cancelled",
]

STATUS_LABELS = {
    "draft": "Szkic",
    "pending_approval": "Oczekuje na zatwierdzenie",
    "approved": "Zatwierdzone",
    "po_generated": "PO wygenerowane",
    "confirmed": "Potwierdzone przez dostawców",
    "in_delivery": "W dostawie",
    "delivered": "Dostarczone",
    "cancelled": "Anulowane",
}

# Valid status transitions
_TRANSITIONS = {
    "draft":             ["pending_approval", "approved", "cancelled"],
    "pending_approval":  ["approved", "cancelled"],
    "approved":          ["po_generated", "cancelled"],
    "po_generated":      ["confirmed", "cancelled"],
    "confirmed":         ["in_delivery"],
    "in_delivery":       ["delivered"],
    "delivered":         [],
    "cancelled":         [],
}

logger = logging.getLogger(__name__)

# ── DB-first order storage ──────────────────────────────────────────────

def _save_order(order: dict, action: str = "order_updated") -> None:
    """Persist order to DB and log event."""
    try:
        from app.database import _get_client, db_save_order, db_add_order_event
        client = _get_client()
        db_save_order(client, order)
        last = order["history"][-1] if order.get("history") else {}
        db_add_order_event(
            client, order["order_id"],
            action=last.get("action", action),
            status=order["status"],
            actor=last.get("actor", "system"),
            note=last.get("note", ""),
        )
    except Exception as e:
        logger.error("Order DB save failed for %s: %s", order.get("order_id"), e)
        raise


def _load_order(order_id: str) -> dict | None:
    """Load a single order from DB, enriching with events and status label."""
    try:
        from app.database import _get_client, db_get_order, db_get_order_events
        client = _get_client()
        row = db_get_order(client, order_id)
        if not row:
            return None
        row["history"] = db_get_order_events(client, order_id)
        row["status_label"] = STATUS_LABELS.get(row.get("status", ""), row.get("status", ""))
        return row
    except Exception as e:
        logger.error("Order DB load failed for %s: %s", order_id, e)
        return None


def _load_orders(status: str | None = None, limit: int = 500) -> list[dict]:
    """Load orders from DB, enriching each with events and status labels."""
    try:
        from app.database import _get_client, db_list_orders, db_get_order_events
        client = _get_client()
        rows = db_list_orders(client, status=status, limit=limit)
        for row in rows:
            row["history"] = db_get_order_events(client, row["order_id"])
            row["status_label"] = STATUS_LABELS.get(row.get("status", ""), row.get("status", ""))
        return rows
    except Exception as e:
        logger.error("Order DB list failed: %s", e)
        return []


def create_order(
    cart_state: dict,
    optimization_result: dict,
    mpk: str,
    gl_account: str,
    requester: str = "procurement.bot@flowproc.eu",
) -> dict:
    """Create a new order from checkout results."""
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()

    requires_approval = cart_state.get("requires_manager_approval", False)
    initial_status = "pending_approval" if requires_approval else "approved"

    order = {
        "order_id": order_id,
        "status": initial_status,
        "status_label": STATUS_LABELS[initial_status],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "requester": requester,
        "mpk": mpk,
        "gl_account": gl_account,
        # Cart data
        "items": cart_state["items"],
        "subtotal": cart_state["subtotal"],
        "discount": cart_state["discount"],
        "shipping_fee": cart_state["shipping_fee"],
        "total": cart_state["total"],
        "total_items": cart_state["total_items"],
        "delivery_days": cart_state["delivery_days"],
        "requires_manager_approval": requires_approval,
        # Optimization
        "optimized_cost": optimization_result.get("optimized_cost", 0),
        "savings_pln": optimization_result.get("savings_pln", 0),
        "domain_results": optimization_result.get("domain_results", []),
        # PO tracking
        "purchase_orders": [],
        # History
        "history": [
            {
                "timestamp": now.isoformat(),
                "action": "order_created",
                "status": initial_status,
                "actor": requester,
                "note": f"Zamówienie utworzone. Wartość: {cart_state['total']:.2f} PLN.",
            }
        ],
    }

    _save_order(order, action="order_created")
    return order


def get_order(order_id: str) -> dict | None:
    return _load_order(order_id)


def list_orders(status: str | None = None) -> list[dict]:
    return _load_orders(status=status)


# ─── Spend analytics (MVP-3) ────────────────────────────────────────

_CATEGORY_GROUP = {c["id"]: c.get("group", "direct") for c in CATEGORIES}
_CATEGORY_LABEL = {c["id"]: c.get("label", c["id"]) for c in CATEGORIES}


def spend_analytics(period_days: int | None = 90, tenant_id: str | None = None) -> dict:
    """Aggregate spend across orders for dashboard widget.

    Rolls up `items[].line_total` per category and kind (Direct / Indirect).
    Period filter matches `created_at >= today - period_days`; pass `None`
    to include all orders. When `tenant_id` is omitted the call resolves
    the active request tenant via `app.tenant_context.current_tenant()`,
    falling back to 'demo' outside a request scope. Returns totals,
    per-kind, and top-N categories.
    """
    from datetime import datetime, timedelta

    cutoff = None
    if period_days and period_days > 0:
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()

    if tenant_id is None:
        try:
            from app.tenant_context import current_tenant
            tenant_id = current_tenant()
        except Exception:
            tenant_id = "demo"

    orders = [
        o for o in _load_orders()
        if (o.get("tenant_id") or "demo") == tenant_id
    ]

    total = 0.0
    direct_total = 0.0
    indirect_total = 0.0
    per_category: dict[str, dict] = {}
    order_count = 0

    for o in orders:
        ts = o.get("created_at") or ""
        if cutoff and ts and ts < cutoff:
            continue
        order_count += 1
        items = o.get("items") or []
        for it in items:
            cat = it.get("category") or "unknown"
            line = float(it.get("line_total") or 0)
            if line <= 0:
                continue
            total += line
            group = _CATEGORY_GROUP.get(cat, "direct")
            if group == "indirect":
                indirect_total += line
            else:
                direct_total += line
            bucket = per_category.setdefault(cat, {
                "category": cat,
                "label": _CATEGORY_LABEL.get(cat, cat),
                "group": group,
                "spend": 0.0,
                "items": 0,
            })
            bucket["spend"] += line
            bucket["items"] += int(it.get("quantity") or 0)

    top_categories = sorted(per_category.values(), key=lambda b: b["spend"], reverse=True)[:6]

    return {
        "period_days": period_days,
        "order_count": order_count,
        "total_spend": round(total, 2),
        "direct_spend": round(direct_total, 2),
        "indirect_spend": round(indirect_total, 2),
        "direct_pct": round(direct_total / total * 100, 1) if total else 0.0,
        "indirect_pct": round(indirect_total / total * 100, 1) if total else 0.0,
        "top_categories": [
            {**b, "spend": round(b["spend"], 2)} for b in top_categories
        ],
    }


def transition_order(
    order_id: str,
    new_status: str,
    actor: str = "system",
    note: str = "",
) -> dict | None:
    """Move order to a new status if transition is valid."""
    order = _load_order(order_id)
    if not order:
        return None

    current = order["status"]
    allowed = _TRANSITIONS.get(current, [])
    if new_status not in allowed:
        return {
            "error": True,
            "message": f"Niedozwolona zmiana statusu: {STATUS_LABELS.get(current, current)} → {STATUS_LABELS.get(new_status, new_status)}.",
            "allowed_transitions": [{"status": s, "label": STATUS_LABELS[s]} for s in allowed],
        }

    now = datetime.now()
    order["status"] = new_status
    order["status_label"] = STATUS_LABELS[new_status]
    order["updated_at"] = now.isoformat()
    order["history"].append({
        "timestamp": now.isoformat(),
        "action": f"status_changed_to_{new_status}",
        "status": new_status,
        "actor": actor,
        "note": note or f"Status zmieniony na: {STATUS_LABELS[new_status]}.",
    })

    _save_order(order, action=f"status_changed_to_{new_status}")
    return order


def approve_order(order_id: str, approver: str = "manager@flowproc.eu") -> dict | None:
    """Approve an order (shortcut for pending_approval → approved)."""
    return transition_order(order_id, "approved", actor=approver, note=f"Zatwierdzone przez {approver}.")


def generate_purchase_orders(order_id: str) -> dict | None:
    """Generate POs from optimization allocations (approved → po_generated)."""
    order = _load_order(order_id)
    if not order:
        return None
    if order["status"] != "approved":
        return {
            "error": True,
            "message": f"PO można generować tylko dla zamówień zatwierdzonych (aktualnie: {order['status_label']}).",
        }

    now = datetime.now()
    pos: list[dict] = []
    po_seq = 1

    for dr in order.get("domain_results", []):
        if not dr.get("success"):
            continue
        # Group allocations by supplier
        by_supplier: dict[str, list[dict]] = {}
        for alloc in dr.get("allocations", []):
            sid = alloc["supplier_id"]
            by_supplier.setdefault(sid, []).append(alloc)

        for supplier_id, allocs in by_supplier.items():
            po_id = f"PO-{order_id.split('-', 1)[1]}-{po_seq:02d}"
            po_total = sum(a.get("allocated_cost_pln", 0) for a in allocs)
            po = {
                "po_id": po_id,
                "supplier_id": supplier_id,
                "supplier_name": allocs[0].get("supplier_name", supplier_id),
                "domain": dr["domain"],
                "lines": [
                    {
                        "product_id": a["product_id"],
                        "quantity": a["allocated_qty"],
                        "unit_cost": a["unit_cost"],
                        "logistics_cost": a["logistics_cost"],
                        "line_total": a.get("allocated_cost_pln", 0),
                    }
                    for a in allocs
                ],
                "po_total_pln": round(po_total, 2),
                "status": "sent",
                "created_at": now.isoformat(),
                "expected_delivery": (now + timedelta(days=max(a.get("lead_time_days", 5) for a in allocs))).strftime("%Y-%m-%d"),
            }
            pos.append(po)
            po_seq += 1

    order["purchase_orders"] = pos
    _save_order(order, action="po_generated")
    # transition also saves, but we need POs persisted first
    return transition_order(order_id, "po_generated", actor="system", note=f"Wygenerowano {len(pos)} zamówień zakupu (PO).")


def confirm_order(order_id: str) -> dict | None:
    """Mark POs as confirmed by suppliers (po_generated → confirmed)."""
    order = _load_order(order_id)
    if not order:
        return None
    if order["status"] != "po_generated":
        return {"error": True, "message": f"PO można potwierdzić tylko w statusie 'PO wygenerowane' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "confirmed"
        po["confirmed_at"] = now.isoformat()
    _save_order(order, action="po_confirmed")
    return transition_order(order_id, "confirmed", actor="supplier.portal", note="Wszystkie PO potwierdzone przez dostawców.")


def ship_order(order_id: str) -> dict | None:
    """Mark order as in delivery (confirmed → in_delivery)."""
    return transition_order(order_id, "in_delivery", actor="logistics", note="Przesyłka odebrana przez przewoźnika.")


def deliver_order(order_id: str) -> dict | None:
    """Mark order as delivered (in_delivery → delivered) + GR."""
    order = _load_order(order_id)
    if not order:
        return None
    if order["status"] != "in_delivery":
        return {"error": True, "message": f"Dostawę można potwierdzić tylko w statusie 'W dostawie' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "delivered"
        po["delivered_at"] = now.isoformat()
    _save_order(order, action="po_delivered")
    return transition_order(order_id, "delivered", actor="warehouse", note="Goods Receipt (GR) zaksięgowane.")


def cancel_order(order_id: str, reason: str = "") -> dict | None:
    """Cancel an order at any cancellable stage."""
    return transition_order(order_id, "cancelled", actor="user", note=reason or "Zamówienie anulowane.")
