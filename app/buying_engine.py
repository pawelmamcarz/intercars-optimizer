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

APPROVAL_POLICIES: dict = {
    "workflow_mode": "sequential",        # "sequential" | "parallel"
    "thresholds": [
        {
            "id": "auto_approve",
            "name": "Auto-zatwierdzenie",
            "max_amount": 5000.0,
            "max_quantity": 50,
            "approvers": [],
            "action": "auto_approve",
            "description": "Zamówienia do 5 000 PLN i 50 szt — automatycznie zatwierdzone",
        },
        {
            "id": "manager_approval",
            "name": "Zatwierdzenie kierownika",
            "max_amount": 25000.0,
            "max_quantity": 200,
            "approvers": ["manager@flowproc.eu"],
            "action": "require_approval",
            "description": "Zamówienia 5 001–25 000 PLN — zatwierdzenie kierownika działu",
        },
        {
            "id": "director_approval",
            "name": "Zatwierdzenie dyrektora",
            "max_amount": 100000.0,
            "max_quantity": 1000,
            "approvers": ["manager@flowproc.eu", "director@flowproc.eu"],
            "action": "require_approval",
            "description": "Zamówienia 25 001–100 000 PLN — kierownik + dyrektor",
        },
        {
            "id": "board_approval",
            "name": "Zatwierdzenie zarządu",
            "max_amount": 999999999,
            "max_quantity": 999999999,
            "approvers": ["manager@flowproc.eu", "director@flowproc.eu", "cfo@flowproc.eu"],
            "action": "require_approval",
            "description": "Zamówienia > 100 000 PLN — kierownik + dyrektor + CFO",
        },
    ],
    "category_rules": [
        {
            "category": "it_services",
            "budget_limit": 25000.0,
            "extra_approver": "it-manager@flowproc.eu",
            "description": "IT wymaga dodatkowego zatwierdzenia IT Managera",
        },
        {
            "category": "oe_components",
            "budget_limit": 50000.0,
            "extra_approver": "quality@flowproc.eu",
            "description": "Komponenty OE wymagają zatwierdzenia Działu Jakości",
        },
    ],
    "item_policies": [
        {
            "id": "high_value_item",
            "condition": "unit_price > 1000",
            "action": "flag_approval",
            "description": "Pozycje > 1 000 PLN/szt wymagają zatwierdzenia",
        },
        {
            "id": "catalog_required",
            "condition": "not_in_catalog",
            "action": "flag_warning",
            "description": "Pozycje spoza katalogu — ostrzeżenie compliance",
        },
    ],
}


def get_approval_policies() -> dict:
    """Return current approval workflow configuration."""
    return APPROVAL_POLICIES.copy()


def update_approval_policies(updates: dict) -> dict:
    """Update approval workflow configuration."""
    global APPROVAL_POLICIES
    if "workflow_mode" in updates:
        APPROVAL_POLICIES["workflow_mode"] = updates["workflow_mode"]
    if "thresholds" in updates:
        APPROVAL_POLICIES["thresholds"] = updates["thresholds"]
    if "category_rules" in updates:
        APPROVAL_POLICIES["category_rules"] = updates["category_rules"]
    if "item_policies" in updates:
        APPROVAL_POLICIES["item_policies"] = updates["item_policies"]
    return APPROVAL_POLICIES


def evaluate_approval(cart_state: dict) -> dict:
    """
    Evaluate approval requirements for a cart based on current policies.
    Returns approval chain, required approvers, and policy matches.
    """
    subtotal = cart_state.get("subtotal", 0)
    total_items = cart_state.get("total_items", 0)
    items = cart_state.get("items", [])
    policies = APPROVAL_POLICIES

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

# In-memory order store (write-through cache — always synced with DB)
_orders: dict[str, dict] = {}
_orders_hydrated = False


def _persist_order(order: dict, action: str = "order_updated") -> None:
    """Write-through: save order to DB + add event. Silent fallback if no DB."""
    try:
        from app.database import DB_AVAILABLE, _get_client, db_save_order, db_add_order_event
        if not DB_AVAILABLE:
            return
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
        logger.warning("Order DB persist failed (in-memory still OK): %s", e)


def hydrate_orders_from_db() -> None:
    """Load orders from DB into in-memory cache. Called once on first access."""
    global _orders_hydrated
    if _orders_hydrated:
        return
    _orders_hydrated = True
    try:
        from app.database import DB_AVAILABLE, _get_client, db_list_orders, db_get_order_events
        if not DB_AVAILABLE:
            return
        client = _get_client()
        rows = db_list_orders(client, limit=500)
        for row in rows:
            oid = row["order_id"]
            if oid not in _orders:
                # Reconstruct history from events
                events = db_get_order_events(client, oid)
                row["history"] = events
                row["status_label"] = STATUS_LABELS.get(row.get("status", ""), row.get("status", ""))
                _orders[oid] = row
        if rows:
            logger.info("Hydrated %d orders from database", len(rows))
    except Exception as e:
        logger.warning("Order hydration failed: %s", e)


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

    _orders[order_id] = order
    _persist_order(order, action="order_created")
    return order


def get_order(order_id: str) -> dict | None:
    hydrate_orders_from_db()
    return _orders.get(order_id)


def list_orders(status: str | None = None) -> list[dict]:
    hydrate_orders_from_db()
    orders = list(_orders.values())
    if status:
        orders = [o for o in orders if o["status"] == status]
    return sorted(orders, key=lambda o: o["created_at"], reverse=True)


def transition_order(
    order_id: str,
    new_status: str,
    actor: str = "system",
    note: str = "",
) -> dict | None:
    """Move order to a new status if transition is valid."""
    order = _orders.get(order_id)
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

    _persist_order(order, action=f"status_changed_to_{new_status}")
    return order


def approve_order(order_id: str, approver: str = "manager@flowproc.eu") -> dict | None:
    """Approve an order (shortcut for pending_approval → approved)."""
    return transition_order(order_id, "approved", actor=approver, note=f"Zatwierdzone przez {approver}.")


def generate_purchase_orders(order_id: str) -> dict | None:
    """Generate POs from optimization allocations (approved → po_generated)."""
    order = _orders.get(order_id)
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
    # transition_order will call _persist_order internally
    transition_order(order_id, "po_generated", actor="system", note=f"Wygenerowano {len(pos)} zamówień zakupu (PO).")
    return order


def confirm_order(order_id: str) -> dict | None:
    """Mark POs as confirmed by suppliers (po_generated → confirmed)."""
    order = _orders.get(order_id)
    if not order:
        return None
    if order["status"] != "po_generated":
        return {"error": True, "message": f"PO można potwierdzić tylko w statusie 'PO wygenerowane' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "confirmed"
        po["confirmed_at"] = now.isoformat()
    return transition_order(order_id, "confirmed", actor="supplier.portal", note="Wszystkie PO potwierdzone przez dostawców.")


def ship_order(order_id: str) -> dict | None:
    """Mark order as in delivery (confirmed → in_delivery)."""
    return transition_order(order_id, "in_delivery", actor="logistics", note="Przesyłka odebrana przez przewoźnika.")


def deliver_order(order_id: str) -> dict | None:
    """Mark order as delivered (in_delivery → delivered) + GR."""
    order = _orders.get(order_id)
    if not order:
        return None
    if order["status"] != "in_delivery":
        return {"error": True, "message": f"Dostawę można potwierdzić tylko w statusie 'W dostawie' (aktualnie: {order['status_label']})."}
    now = datetime.now()
    for po in order.get("purchase_orders", []):
        po["status"] = "delivered"
        po["delivered_at"] = now.isoformat()
    result = transition_order(order_id, "delivered", actor="warehouse", note="Goods Receipt (GR) zaksięgowane.")
    return result


def cancel_order(order_id: str, reason: str = "") -> dict | None:
    """Cancel an order at any cancellable stage."""
    return transition_order(order_id, "cancelled", actor="user", note=reason or "Zamówienie anulowane.")
