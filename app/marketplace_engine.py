"""
Marketplace integration engine.

- AllegroClient: OAuth2 client_credentials → search public offers
- PunchOut: mock cXML PunchOut session management
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#  ALLEGRO CLIENT
# ═══════════════════════════════════════════════════════════════════

class AllegroClient:
    """Allegro REST API client with OAuth2 device_code flow."""

    _token: str | None = None
    _token_expires: float = 0.0
    _device_code: str | None = None
    _user_code: str | None = None
    _verification_url: str | None = None

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.allegro_client_id and settings.allegro_client_secret)

    @classmethod
    def has_token(cls) -> bool:
        return bool(cls._token and time.time() < cls._token_expires - 60)

    @classmethod
    async def start_device_flow(cls) -> dict:
        """Start device_code flow. Returns user_code + verification URL."""
        if not cls.is_configured():
            raise RuntimeError("Allegro API not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://allegro.pl/auth/oauth/device",
                data={"client_id": settings.allegro_client_id},
                auth=(settings.allegro_client_id, settings.allegro_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            cls._device_code = data["device_code"]
            cls._user_code = data["user_code"]
            cls._verification_url = data.get("verification_uri_complete", data["verification_uri"])
            logger.info("Allegro device flow started: code=%s", cls._user_code)
            return {
                "user_code": cls._user_code,
                "verification_url": cls._verification_url,
                "expires_in": data.get("expires_in", 3600),
            }

    @classmethod
    async def poll_device_token(cls) -> bool:
        """Poll for device token after user authorizes. Returns True if token acquired."""
        if not cls._device_code:
            return False

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.allegro_auth_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": cls._device_code,
                },
                auth=(settings.allegro_client_id, settings.allegro_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                data = resp.json()
                cls._token = data["access_token"]
                cls._token_expires = time.time() + data.get("expires_in", 43200)
                cls._device_code = None
                logger.info("Allegro user token acquired, expires in %ds", data.get("expires_in", 0))
                return True
            # 400 = authorization_pending (user hasn't approved yet)
            return False

    @classmethod
    async def _ensure_token(cls):
        """Ensure we have a valid token."""
        if cls._token and time.time() < cls._token_expires - 60:
            return

        # Try client_credentials first (works for some endpoints)
        if not cls.is_configured():
            raise RuntimeError("Allegro API not configured (FLOW_ALLEGRO_CLIENT_ID / FLOW_ALLEGRO_CLIENT_SECRET)")

        # If we have a pending device flow, try polling
        if cls._device_code:
            acquired = await cls.poll_device_token()
            if acquired:
                return

        # Try client_credentials as fallback
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.allegro_auth_url,
                data={"grant_type": "client_credentials"},
                auth=(settings.allegro_client_id, settings.allegro_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            cls._token = data["access_token"]
            cls._token_expires = time.time() + data.get("expires_in", 43200)
            logger.info("Allegro client_credentials token acquired, expires in %ds", data.get("expires_in", 0))

    @classmethod
    async def search(cls, query: str, limit: int = 20, category_id: str | None = None) -> list[dict]:
        """Search Allegro offers and return normalized product list."""
        await cls._ensure_token()

        params: dict[str, Any] = {"phrase": query, "limit": min(limit, 60)}
        if category_id:
            params["category.id"] = category_id

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.allegro_api_base}/offers/listing",
                params=params,
                headers={
                    "Authorization": f"Bearer {cls._token}",
                    "Accept": "application/vnd.allegro.public.v1+json",
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        # Merge regular + promoted
        items_raw = data.get("items", {})
        offers = items_raw.get("promoted", []) + items_raw.get("regular", [])

        return [_normalize_allegro_offer(o) for o in offers[:limit]]

    @classmethod
    async def get_offer(cls, offer_id: str) -> dict | None:
        """Get single Allegro offer details."""
        await cls._ensure_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.allegro_api_base}/offers/listing",
                params={"phrase": offer_id, "limit": 1},
                headers={
                    "Authorization": f"Bearer {cls._token}",
                    "Accept": "application/vnd.allegro.public.v1+json",
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items", {}).get("regular", []) + data.get("items", {}).get("promoted", [])
            return _normalize_allegro_offer(items[0]) if items else None


def _normalize_allegro_offer(offer: dict) -> dict:
    """Transform Allegro offer JSON into our catalog item format."""
    price_info = offer.get("sellingMode", {}).get("price", {})
    price = float(price_info.get("amount", 0))
    currency = price_info.get("currency", "PLN")

    images = offer.get("images", [])
    image_url = images[0].get("url", "") if images else ""

    seller = offer.get("seller", {})
    seller_name = seller.get("login", "Allegro Seller")
    seller_id = seller.get("id", "unknown")

    delivery = offer.get("delivery", {})
    delivery_price = delivery.get("lowestPrice", {}).get("amount", "0")

    offer_id = str(offer.get("id", ""))

    return {
        "id": f"ALLEGRO-{offer_id}",
        "name": offer.get("name", ""),
        "price": price,
        "currency": currency,
        "category": "marketplace",
        "unit": "szt",
        "image_url": image_url,
        "delivery_cost": float(delivery_price),
        "suppliers": [
            {"id": f"SUP-ALLEGRO-{seller_id}", "name": seller_name, "unit_price": price}
        ],
        "source": "allegro",
        "external_url": f"https://allegro.pl/oferta/{offer_id}",
        "external_id": offer_id,
    }


# ── Mock Allegro results (when API not configured) ──────────────

def _m(mid, name, price, seller, unit="szt", delivery=0, tags=""):
    """Helper: build mock Allegro item."""
    return {
        "id": f"ALLEGRO-{mid}", "name": name, "price": price, "currency": "PLN",
        "category": "marketplace", "unit": unit, "image_url": "", "delivery_cost": delivery,
        "suppliers": [{"id": f"SUP-ALLEGRO-{mid}", "name": seller, "unit_price": price}],
        "source": "allegro_mock", "external_url": f"https://allegro.pl/oferta/{mid}",
        "external_id": mid, "_tags": tags,
    }


_MOCK_ALLEGRO: list[dict] = [
    # ── IT / Elektronika ──
    _m("IT01", "Laptop Lenovo ThinkPad T14 Gen5 i7/16GB/512SSD", 5499, "LenovoPartner_PL", tags="laptop komputer lenovo thinkpad"),
    _m("IT02", "Laptop Dell Latitude 5540 i5/8GB/256SSD", 3899, "DellStore_PL", tags="laptop dell komputer"),
    _m("IT03", "MacBook Air M3 15\" 16GB/512SSD", 7299, "iSpot_PL", tags="laptop apple macbook komputer"),
    _m("IT04", "Monitor Dell UltraSharp U2723QE 27\" 4K USB-C", 2199, "DellStore_PL", tags="monitor dell ekran"),
    _m("IT05", "Monitor Samsung Odyssey G5 34\" WQHD 165Hz", 1599, "SamsungPro_PL", tags="monitor samsung ekran"),
    _m("IT06", "Drukarka HP LaserJet Pro M404dn mono", 1289, "HPSupplies_PL", tags="drukarka hp laser"),
    _m("IT07", "Drukarka Brother MFC-L2732DW mono wifi", 999, "BrotherOffice_PL", tags="drukarka brother"),
    _m("IT08", "Toner HP 26X CF226X oryginalny 9000 str.", 459, "HPSupplies_PL", tags="toner hp druk"),
    _m("IT09", "Toner Brother TN-2421 oryginalny 3000 str.", 189, "BrotherOffice_PL", tags="toner brother druk"),
    _m("IT10", "Kabel sieciowy Cat6a S/FTP 305m szpula", 890, "NetworkPro_PL", unit="szpula", delivery=19.99, tags="kabel siec it"),
    _m("IT11", "Switch TP-Link TL-SG1024DE 24-port Gigabit", 389, "NetworkPro_PL", tags="switch siec it"),
    _m("IT12", "UPS APC Back-UPS 1500VA 230V", 899, "UPS_Expert", tags="ups zasilanie it"),
    _m("IT13", "Dysk SSD Samsung 990 Pro 2TB NVMe M.2", 749, "SamsungPro_PL", tags="dysk ssd samsung it"),
    _m("IT14", "Mysz Logitech MX Master 3S bezprzewodowa", 449, "LogitechPro_PL", tags="mysz logitech komputer"),
    _m("IT15", "Klawiatura Logitech MX Keys S bezprzewodowa", 499, "LogitechPro_PL", tags="klawiatura logitech komputer"),
    # ── Biuro ──
    _m("BIU01", "Papier ksero Pollux A4 80g 5 ryz (2500 ark)", 89.90, "BiuroPlus_Hurtownia", unit="op", delivery=9.99, tags="papier biuro a4"),
    _m("BIU02", "Papier ksero HP Premium A4 90g karton 2500 ark", 129, "HPSupplies_PL", unit="karton", tags="papier biuro a4 hp"),
    _m("BIU03", "Segregator A4/75mm Esselte No.1 Power 10 szt.", 79.90, "BiuroPlus_Hurtownia", unit="op", tags="segregator biuro"),
    _m("BIU04", "Dlugopis Pilot G2 czarny 0.5mm 12 szt.", 49.90, "BiuroPlus_Hurtownia", unit="op", tags="dlugopis biuro pilot"),
    _m("BIU05", "Tablica magnetyczna sucho-scieralna 120x90cm", 279, "Tablice24_PL", tags="tablica biuro"),
    _m("BIU06", "Niszczarka Fellowes 73Ci P-4 12 ark.", 799, "BiuroPlus_Hurtownia", tags="niszczarka biuro fellowes"),
    # ── Meble biurowe ──
    _m("MEB01", "Krzeslo biurowe Ergohuman Elite G2 mesh", 3890, "ErgoDesign24", delivery=49.99, tags="krzeslo biuro ergonomiczne meble"),
    _m("MEB02", "Biurko regulowane elektrycznie 160x80 biale", 2490, "ErgoDesign24", delivery=99, tags="biurko meble regulowane"),
    _m("MEB03", "Szafa aktowa metalowa 195x92x42cm", 1290, "MetalMeble_PL", delivery=149, tags="szafa meble metalowa biuro"),
    _m("MEB04", "Fotel obrotowy Markus IKEA czarny", 799, "IKEA_Partner", delivery=69, tags="fotel krzeslo biuro ikea meble"),
    # ── BHP / Ochrona ──
    _m("BHP01", "Rekawice robocze nitrylowe 100szt L niebieskie", 24.90, "BHP_Expert", unit="op", delivery=6.99, tags="rekawice bhp ochrona nitryl"),
    _m("BHP02", "Okulary ochronne 3M SecureFit 400 przezroczyste", 29.90, "BHP_Expert", tags="okulary bhp ochrona 3m"),
    _m("BHP03", "Kask ochronny 3M Peltor G3000 bialy", 89, "BHP_Expert", tags="kask bhp ochrona 3m"),
    _m("BHP04", "Buty robocze S3 Puma Safety Velocity 2.0", 449, "BHP_Expert", tags="buty robocze bhp ochrona puma"),
    _m("BHP05", "Apteczka zakladowa DIN 13157 scienna", 149, "BHP_Expert", tags="apteczka bhp pierwsza pomoc"),
    _m("BHP06", "Kamizelka odblaskowa zolta EN ISO 20471 10szt", 49.90, "BHP_Expert", unit="op", tags="kamizelka odblaskowa bhp"),
    # ── Narzedzia ──
    _m("NAR01", "Wiertarko-wkretarka Makita DDF484Z 18V LXT body", 649, "MakitaPro_PL", tags="wiertarka makita narzedzia"),
    _m("NAR02", "Szlifierka katowa Bosch GWS 22-230 JH 2200W", 599, "BoschPro_PL", tags="szlifierka bosch narzedzia"),
    _m("NAR03", "Kompresor Metabo Power 250-10W 10L 230V", 799, "MetaboStore_PL", tags="kompresor metabo narzedzia"),
    _m("NAR04", "Zestaw kluczy nasadowych 1/4+1/2 94 szt Proxxon", 399, "NarzedziaMax_PL", tags="klucze nasadowe narzedzia proxxon"),
    _m("NAR05", "Pila tarczowa Makita HS7611 1600W 190mm", 549, "MakitaPro_PL", tags="pila tarczowa makita narzedzia"),
    # ── Czystosc / Higiena ──
    _m("CZY01", "Recznik papierowy ZZ bialy 4000 szt karton", 59.90, "HigienaPro_PL", unit="karton", tags="recznik papier higiena czystosc"),
    _m("CZY02", "Mydlo w plynie antybakteryjne 5L kanister", 34.90, "HigienaPro_PL", unit="kanister", tags="mydlo higiena czystosc"),
    _m("CZY03", "Plyn do mycia podlog Clinex Floral Ocean 5L", 29.90, "HigienaPro_PL", unit="kanister", tags="plyn podloga czystosc clinex"),
    _m("CZY04", "Worki na smieci 120L LDPE czarne 25szt", 14.90, "HigienaPro_PL", unit="rolka", tags="worki smieci czystosc"),
    # ── Chemia przemyslowa ──
    _m("CHE01", "Srodek odrdzewiacz WD-40 Specialist 400ml x 6", 119, "WD40_Dystrybucja", unit="op", tags="wd40 chemia odrdzewiacz spray"),
    _m("CHE02", "Smar litowy EP2 Orlen Liten 4.5kg", 69, "OrlenOil_PL", tags="smar orlen chemia"),
    _m("CHE03", "Plyn hamulcowy DOT4 ATE 1L", 39.90, "ATE_Partner", tags="plyn hamulcowy chemia motoryzacja"),
    # ── Elektro / Oswietlenie ──
    _m("ELE01", "Zarowka LED Philips E27 13W=100W 4000K 6 szt", 49.90, "Philips_Electric", unit="op", tags="zarowka led philips oswietlenie"),
    _m("ELE02", "Oprawa LED panel 60x60 40W 4000K natynkowa", 89, "LedLighting_PL", tags="panel led oprawa oswietlenie"),
    _m("ELE03", "Przedluzacz beben 50m 3x2.5mm2 IP44", 229, "ElektroMax_PL", tags="przedluzacz beben kabel elektro"),
    _m("ELE04", "Akumulator 18650 Samsung INR 3500mAh 2szt", 39.90, "BatteryStore_PL", unit="op", tags="akumulator bateria samsung"),
    # ── Opakowania / Logistyka ──
    _m("PAK01", "Karton klapowy 600x400x400mm 3W 20szt", 89, "PakPro_PL", unit="op", delivery=29, tags="karton opakowanie logistyka"),
    _m("PAK02", "Folia stretch reczna 23mic 3kg transparentna", 29.90, "PakPro_PL", unit="rolka", tags="folia stretch opakowanie logistyka"),
    _m("PAK03", "Tasma pakowa Scotch 50mm x 66m brazowa 6szt", 34.90, "3M_Dystrybucja", unit="op", tags="tasma pakowa opakowanie 3m"),
    _m("PAK04", "Paleta EUR 1200x800mm drewniana nowa EPAL", 49, "PaletyPL", tags="paleta eur logistyka drewno"),
    # ── Motoryzacja / Flota ──
    _m("MOT01", "Olej silnikowy Castrol EDGE 5W-30 LL 5L", 189, "CastrolShop_PL", unit="kanister", tags="olej silnikowy castrol motoryzacja"),
    _m("MOT02", "Opony zimowe Continental WinterContact TS870P 225/45R17", 599, "OponySklep_PL", tags="opony zimowe continental motoryzacja"),
    _m("MOT03", "Akumulator Varta Blue Dynamic E11 74Ah 680A", 389, "AkuExpert_PL", tags="akumulator varta motoryzacja"),
    _m("MOT04", "Klocki hamulcowe Brembo P 85 075 przod VW/Audi", 189, "BremboShop_PL", unit="kpl", tags="klocki hamulcowe brembo motoryzacja"),
    _m("MOT05", "Filtr oleju MANN W712/95 VW/Audi/Skoda", 24.90, "FiltryPro_PL", tags="filtr olej mann motoryzacja"),
    # ── Zywnosc / Catering ──
    _m("ZYW01", "Kawa ziarnista Lavazza Qualita Oro 1kg", 69, "KawaPro24", tags="kawa ziarnista lavazza zywnosc"),
    _m("ZYW02", "Woda mineralna Zywiec Zdroj 1.5L zgrzewka 6szt", 9.90, "ZywiecZdroj_PL", unit="zgrzewka", tags="woda mineralna zywnosc"),
    _m("ZYW03", "Herbata Lipton Yellow Label 100 torebek", 19.90, "Lipton_Store", unit="op", tags="herbata lipton zywnosc"),
    _m("ZYW04", "Cukier bialy krysztol 1kg x 10 szt", 39.90, "HurtSpozywczy_PL", unit="op", tags="cukier zywnosc"),
]


def mock_allegro_search(query: str, limit: int = 20) -> list[dict]:
    """Smart mock search — searches name + tags, scores by relevance."""
    q = query.lower().split()
    scored = []
    for item in _MOCK_ALLEGRO:
        searchable = (item["name"] + " " + item.get("_tags", "")).lower()
        score = sum(1 for word in q if word in searchable)
        # Bonus for exact phrase match
        if query.lower() in searchable:
            score += 3
        if score > 0:
            scored.append((score, item))

    if not scored:
        # No matches — return top items
        return _MOCK_ALLEGRO[:limit]

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


# ═══════════════════════════════════════════════════════════════════
#  PUNCHOUT (cXML mock)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PunchOutSession:
    session_id: str
    buyer_cookie: str
    browser_form_post_url: str
    status: str = "active"  # active | completed | cancelled
    created_at: float = field(default_factory=time.time)
    cart_items: list[dict] = field(default_factory=list)


# In-memory session store
_punchout_sessions: dict[str, PunchOutSession] = {}


# ── Dedicated PunchOut external catalog (simulates supplier's cXML catalog) ──
_PUNCHOUT_CATALOG: list[dict] = [
    # ── Biuro & IT ──────────────────────────────────────────────────
    {"id": "PO-IT-001", "name": "Laptop Dell Latitude 5540 i7/16GB/512SSD",
     "description": "Laptop biznesowy 15.6\" FHD, Intel i7-1365U, 16GB DDR5, 512GB SSD, Win11 Pro, 3Y NBD",
     "price": 5290.0, "category": "it", "delivery_days": 5, "unit": "szt", "image": "laptop",
     "supplier_name": "Dell Technologies", "contract_no": "FWZ/2024/IT-001"},
    {"id": "PO-IT-002", "name": "Monitor Dell U2723QE 27\" 4K USB-C",
     "description": "Monitor IPS 27\" 4K UHD, USB-C 90W, HDMI, DP, regulacja wysokosci, VESA",
     "price": 2190.0, "category": "it", "delivery_days": 3, "unit": "szt", "image": "monitor",
     "supplier_name": "Dell Technologies", "contract_no": "FWZ/2024/IT-001"},
    {"id": "PO-IT-003", "name": "Stacja dokujaca Dell WD22TB4 Thunderbolt",
     "description": "Stacja dokujaca Thunderbolt 4, 2x DP, HDMI, 3x USB-A, 2x USB-C, RJ45, 130W",
     "price": 890.0, "category": "it", "delivery_days": 3, "unit": "szt", "image": "docking",
     "supplier_name": "Dell Technologies", "contract_no": "FWZ/2024/IT-001"},
    {"id": "PO-IT-004", "name": "Mysz Logitech MX Master 3S bezprzewodowa",
     "description": "Mysz bezprzewodowa, Bluetooth + USB, 8000 DPI, ciche klikanie, MagSpeed scroll",
     "price": 399.0, "category": "it", "delivery_days": 2, "unit": "szt", "image": "mouse",
     "supplier_name": "Logitech", "contract_no": "FWZ/2024/IT-002"},
    {"id": "PO-IT-005", "name": "Klawiatura Logitech MX Keys S",
     "description": "Klawiatura bezprzewodowa, podswietlana, Bluetooth + USB, Smart Actions",
     "price": 459.0, "category": "it", "delivery_days": 2, "unit": "szt", "image": "keyboard",
     "supplier_name": "Logitech", "contract_no": "FWZ/2024/IT-002"},
    {"id": "PO-IT-006", "name": "Drukarka HP LaserJet Pro M404dn",
     "description": "Drukarka laserowa mono, duplex, siec, 40 str/min, toner CF259A",
     "price": 1290.0, "category": "it", "delivery_days": 4, "unit": "szt", "image": "printer",
     "supplier_name": "HP Inc.", "contract_no": "FWZ/2024/IT-003"},
    {"id": "PO-IT-007", "name": "Toner HP CF259A (59A) oryginalny",
     "description": "Toner oryginalny do HP LaserJet Pro M404/M428, 3000 stron, czarny",
     "price": 389.0, "category": "it", "delivery_days": 1, "unit": "szt", "image": "toner",
     "supplier_name": "HP Inc.", "contract_no": "FWZ/2024/IT-003"},
    {"id": "PO-IT-008", "name": "Switch sieciowy TP-Link TL-SG1024DE 24-port GbE",
     "description": "Przelacznik zarzadzalny 24x GbE, VLAN, QoS, IGMP, rackmount 19\"",
     "price": 459.0, "category": "it", "delivery_days": 3, "unit": "szt", "image": "switch",
     "supplier_name": "TP-Link", "contract_no": "FWZ/2024/IT-004"},

    # ── Artykuly biurowe ────────────────────────────────────────────
    {"id": "PO-BIU-001", "name": "Papier ksero Pollux A4 80g 500 ark.",
     "description": "Papier biurowy A4, bialos CIE 161, 500 arkuszy, FSC certified",
     "price": 19.90, "category": "office", "delivery_days": 1, "unit": "ryza", "image": "paper",
     "supplier_name": "Europapier Polska", "contract_no": "FWZ/2024/BIU-001"},
    {"id": "PO-BIU-002", "name": "Segregator Esselte Vivida A4 75mm",
     "description": "Segregator dzwigniowy A4, grzbiet 75mm, PP, mechanizm precyzyjny, kolory mix",
     "price": 8.50, "category": "office", "delivery_days": 1, "unit": "szt", "image": "binder",
     "supplier_name": "Esselte", "contract_no": "FWZ/2024/BIU-001"},
    {"id": "PO-BIU-003", "name": "Dlugopis Pilot G-2 0.5mm niebieski (12 szt)",
     "description": "Dlugopis zelowy, gumowy uchwyt, przezroczysta obudowa, op. 12 szt",
     "price": 42.0, "category": "office", "delivery_days": 1, "unit": "op", "image": "pen",
     "supplier_name": "Pilot", "contract_no": "FWZ/2024/BIU-001"},
    {"id": "PO-BIU-004", "name": "Karteczki samoprzylepne Post-it 76x76 mm (12 bl.)",
     "description": "Zólte karteczki, 12 bloczków x 100 karteczek, klej repositionable",
     "price": 38.0, "category": "office", "delivery_days": 1, "unit": "op", "image": "notes",
     "supplier_name": "3M", "contract_no": "FWZ/2024/BIU-002"},
    {"id": "PO-BIU-005", "name": "Koperty C4 229x324mm biale (250 szt)",
     "description": "Koperty biurowe C4, biale, samoprzylepne z paskiem, 250 szt",
     "price": 65.0, "category": "office", "delivery_days": 2, "unit": "op", "image": "envelope",
     "supplier_name": "Europapier Polska", "contract_no": "FWZ/2024/BIU-001"},

    # ── BHP / Srodki ochrony ───────────────────────────────────────
    {"id": "PO-BHP-001", "name": "Rekawice robocze nitrylowe M (100 szt)",
     "description": "Rekawice jednorazowe nitrylowe, bezpudrowe, rozmiar M, niebieskie",
     "price": 28.0, "category": "safety", "delivery_days": 1, "unit": "op", "image": "gloves",
     "supplier_name": "Medisept", "contract_no": "FWZ/2024/BHP-001"},
    {"id": "PO-BHP-002", "name": "Okulary ochronne 3M SecureFit SF201",
     "description": "Okulary ochronne, soczewki bezbarwne, powloka AS/AF, EN 166",
     "price": 24.0, "category": "safety", "delivery_days": 2, "unit": "szt", "image": "goggles",
     "supplier_name": "3M", "contract_no": "FWZ/2024/BHP-001"},
    {"id": "PO-BHP-003", "name": "Buty robocze S3 Puma Rio Black Mid",
     "description": "Trzewiki robocze S3, nosek kompozytowy, wkladka antyprzebiciowa, rozmiary 39-47",
     "price": 289.0, "category": "safety", "delivery_days": 5, "unit": "para", "image": "boots",
     "supplier_name": "Puma Safety", "contract_no": "FWZ/2024/BHP-002"},
    {"id": "PO-BHP-004", "name": "Kask ochronny 3M G3000 z wentylacją",
     "description": "Kask przemyslowy, regulacja pokretlem, wentylacja, EN 397, bialy",
     "price": 67.0, "category": "safety", "delivery_days": 3, "unit": "szt", "image": "helmet",
     "supplier_name": "3M", "contract_no": "FWZ/2024/BHP-001"},
    {"id": "PO-BHP-005", "name": "Kamizelka odblaskowa XL zólta EN ISO 20471",
     "description": "Kamizelka ostrzegawcza klasa 2, zólta, rozmiar XL, 2 pasy odblaskowe",
     "price": 12.0, "category": "safety", "delivery_days": 1, "unit": "szt", "image": "vest",
     "supplier_name": "Reis", "contract_no": "FWZ/2024/BHP-003"},

    # ── Chemia gospodarcza & czystosc ──────────────────────────────
    {"id": "PO-CHE-001", "name": "Plyn do mycia podlog Voigt Nano Floor VC 640 5L",
     "description": "Koncentrat do mycia podlog, nanotechnologia, antypoślizgowy, pH 7-8",
     "price": 42.0, "category": "cleaning", "delivery_days": 2, "unit": "szt", "image": "cleaner",
     "supplier_name": "Voigt", "contract_no": "FWZ/2024/CHE-001"},
    {"id": "PO-CHE-002", "name": "Reczniki papierowe ZZ biale 2-w (20 x 200 szt)",
     "description": "Reczniki skladane ZZ, celuloza 2-warstwowa, biale, karton 4000 szt",
     "price": 89.0, "category": "cleaning", "delivery_days": 2, "unit": "karton", "image": "towel",
     "supplier_name": "Tork", "contract_no": "FWZ/2024/CHE-001"},
    {"id": "PO-CHE-003", "name": "Mydlo w plynie antybakteryjne 5L",
     "description": "Mydlo perlowe, pH 5.5, z gliceryna, dozownik lub uzupelniacz 5L",
     "price": 24.0, "category": "cleaning", "delivery_days": 1, "unit": "szt", "image": "soap",
     "supplier_name": "Voigt", "contract_no": "FWZ/2024/CHE-001"},
    {"id": "PO-CHE-004", "name": "Worki na smieci 120L czarne (25 szt) LDPE",
     "description": "Worki mocne LDPE, 120L, 40 mikronów, czarne, rolka 25 szt",
     "price": 14.0, "category": "cleaning", "delivery_days": 1, "unit": "rolka", "image": "bags",
     "supplier_name": "Jan Niezbedny", "contract_no": "FWZ/2024/CHE-002"},

    # ── Meble biurowe ──────────────────────────────────────────────
    {"id": "PO-MEB-001", "name": "Fotel biurowy ergonomiczny Steelcase Leap V2",
     "description": "Fotel obrotowy, mechanizm LiveBack, regulacja wysokosci, podlokietniki 4D, 12 lat gwarancji",
     "price": 4890.0, "category": "furniture", "delivery_days": 14, "unit": "szt", "image": "chair",
     "supplier_name": "Steelcase", "contract_no": "FWZ/2024/MEB-001"},
    {"id": "PO-MEB-002", "name": "Biurko z regulacja wysokosci 160x80cm",
     "description": "Biurko sit-stand elektryczne, blat melaminowy 160x80, kolumny teleskopowe 65-128cm",
     "price": 2490.0, "category": "furniture", "delivery_days": 10, "unit": "szt", "image": "desk",
     "supplier_name": "Kinnarps", "contract_no": "FWZ/2024/MEB-001"},
    {"id": "PO-MEB-003", "name": "Szafa aktowa metalowa 195x92x42cm",
     "description": "Szafa biurowa zamykana na klucz, 4 polki, RAL 7035 jasnoszara, spawana",
     "price": 890.0, "category": "furniture", "delivery_days": 7, "unit": "szt", "image": "cabinet",
     "supplier_name": "Stalgast", "contract_no": "FWZ/2024/MEB-002"},
    {"id": "PO-MEB-004", "name": "Kontener mobilny 3-szufladowy z zamkiem",
     "description": "Kontener podbiurkowy metalowy, 3 szuflady, zamek centralny, kolka, bialy",
     "price": 490.0, "category": "furniture", "delivery_days": 5, "unit": "szt", "image": "pedestal",
     "supplier_name": "Kinnarps", "contract_no": "FWZ/2024/MEB-001"},

    # ── Narzedzia & warsztat ───────────────────────────────────────
    {"id": "PO-NAR-001", "name": "Wiertarko-wkretarka Makita DDF484RTJ 18V 5.0Ah",
     "description": "Wiertarko-wkretarka akumulatorowa, 2x 5.0Ah, moment 54Nm, BL motor, walizka",
     "price": 1690.0, "category": "tools", "delivery_days": 3, "unit": "szt", "image": "drill",
     "supplier_name": "Makita", "contract_no": "FWZ/2024/NAR-001"},
    {"id": "PO-NAR-002", "name": "Zestaw kluczy nasadowych 1/2\" 172 elem. Gedore Red",
     "description": "Klucze nasadowe + plasko-oczkowe, grzechotki, bity, walizka ABS",
     "price": 890.0, "category": "tools", "delivery_days": 3, "unit": "kpl", "image": "wrench-set",
     "supplier_name": "Gedore", "contract_no": "FWZ/2024/NAR-001"},
    {"id": "PO-NAR-003", "name": "Suwmiarka cyfrowa 150mm Mitutoyo 500-196-30",
     "description": "Suwmiarka elektroniczna 150mm, rozdzielczosc 0.01mm, IP67, wyjscie danych",
     "price": 590.0, "category": "tools", "delivery_days": 5, "unit": "szt", "image": "caliper",
     "supplier_name": "Mitutoyo", "contract_no": "FWZ/2024/NAR-002"},
    {"id": "PO-NAR-004", "name": "Klucz dynamometryczny 1/2\" 40-200 Nm Hazet 5122-3CT",
     "description": "Klucz dynamometryczny z mechanizmem zatrzaskowym, certyfikat kalibracji",
     "price": 790.0, "category": "tools", "delivery_days": 4, "unit": "szt", "image": "torque",
     "supplier_name": "Hazet", "contract_no": "FWZ/2024/NAR-001"},

    # ── Elektrotechnika & instalacje ───────────────────────────────
    {"id": "PO-ELE-001", "name": "Przewód YDYp 3x2.5mm² 100m",
     "description": "Przewód plaski instalacyjny YDYp 3x2.5mm², miedziany, 450/750V, 100m",
     "price": 420.0, "category": "electrical", "delivery_days": 2, "unit": "100m", "image": "cable",
     "supplier_name": "NKT Cables", "contract_no": "FWZ/2024/ELE-001"},
    {"id": "PO-ELE-002", "name": "Rozdzielnica natynkowa 3x12 IP65 Hager",
     "description": "Rozdzielnica modułowa 36 mod., IP65, drzwi przezroczyste, szyna TH35",
     "price": 320.0, "category": "electrical", "delivery_days": 4, "unit": "szt", "image": "panel",
     "supplier_name": "Hager", "contract_no": "FWZ/2024/ELE-001"},
    {"id": "PO-ELE-003", "name": "Wylacznik nadpradowy S301 B16 1P Schneider",
     "description": "Wylacznik nadmiarowo-pradowy 1P, B16A, zdolnosc zwarciowa 6kA, DIN",
     "price": 18.0, "category": "electrical", "delivery_days": 1, "unit": "szt", "image": "breaker",
     "supplier_name": "Schneider Electric", "contract_no": "FWZ/2024/ELE-002"},
    {"id": "PO-ELE-004", "name": "Oprawa LED panel 60x60 40W 4000K",
     "description": "Panel LED sufitowy 60x60cm, 40W, 4000lm, 4000K neutralna, UGR<19, IP44",
     "price": 129.0, "category": "electrical", "delivery_days": 3, "unit": "szt", "image": "led",
     "supplier_name": "Philips Lighting", "contract_no": "FWZ/2024/ELE-003"},

    # ── Motoryzacja / Flota ────────────────────────────────────────
    {"id": "PO-MOT-001", "name": "Olej silnikowy Castrol EDGE 5W-30 LL 5L",
     "description": "Olej w pelni syntetyczny 5W-30, spec. VW 504/507, BMW LL-04, 5 litrow",
     "price": 189.0, "category": "oils", "delivery_days": 2, "unit": "szt", "image": "oil",
     "supplier_name": "Castrol", "contract_no": "FWZ/2024/MOT-001"},
    {"id": "PO-MOT-002", "name": "Opony zimowe Continental WinterContact TS870 205/55R16",
     "description": "Opona zimowa, indeks predkosci H (210 km/h), etykieta B/B/71dB",
     "price": 459.0, "category": "parts", "delivery_days": 3, "unit": "szt", "image": "tire",
     "supplier_name": "Continental", "contract_no": "FWZ/2024/MOT-002"},
    {"id": "PO-MOT-003", "name": "Akumulator Varta Blue Dynamic E11 74Ah 680A",
     "description": "Akumulator rozruchowy 12V 74Ah 680A EN, P+, wymiary 278x175x190mm",
     "price": 389.0, "category": "parts", "delivery_days": 2, "unit": "szt", "image": "battery",
     "supplier_name": "Varta", "contract_no": "FWZ/2024/MOT-003"},
    {"id": "PO-MOT-004", "name": "Plynu hamulcowy DOT4 ATE TYP 200 1L",
     "description": "Plyn hamulcowy DOT4, temp. wrzenia suchy 260°C, mokry 165°C, FMVSS 116",
     "price": 42.0, "category": "oils", "delivery_days": 1, "unit": "szt", "image": "brake-fluid",
     "supplier_name": "ATE", "contract_no": "FWZ/2024/MOT-001"},

    # ── Opakowania & logistyka ─────────────────────────────────────
    {"id": "PO-OPK-001", "name": "Karton klapowy 600x400x400mm 3W fala BC (10 szt)",
     "description": "Karton transportowy 3-warstwowy, fala BC, nośność 30kg, 10 szt",
     "price": 45.0, "category": "packaging", "delivery_days": 2, "unit": "op", "image": "box",
     "supplier_name": "DS Smith", "contract_no": "FWZ/2024/OPK-001"},
    {"id": "PO-OPK-002", "name": "Folia stretch maszynowa 500mm 23mic 16kg (6 rolek)",
     "description": "Folia stretch do owijarki, 500mm, 23 mikrony, przezroczysta, 6 rolek",
     "price": 210.0, "category": "packaging", "delivery_days": 3, "unit": "op", "image": "wrap",
     "supplier_name": "Manuli Stretch", "contract_no": "FWZ/2024/OPK-001"},
    {"id": "PO-OPK-003", "name": "Paleta EUR 1200x800mm EPAL certyfikowana",
     "description": "Europaleta drewniana 1200x800, EPAL/ISPM15, nosnosc 1500kg, nowa",
     "price": 52.0, "category": "packaging", "delivery_days": 2, "unit": "szt", "image": "pallet",
     "supplier_name": "PalNET", "contract_no": "FWZ/2024/OPK-002"},
    {"id": "PO-OPK-004", "name": "Tasma pakowa brazowa 48mm x 66m (36 rolek)",
     "description": "Tasma samoprzylepna PP, akrylowy klej, brazowa, 36 rolek/karton",
     "price": 85.0, "category": "packaging", "delivery_days": 1, "unit": "karton", "image": "tape",
     "supplier_name": "Tesa", "contract_no": "FWZ/2024/OPK-001"},

    # ── Srodki spozywcze / catering ────────────────────────────────
    {"id": "PO-ZYW-001", "name": "Kawa ziarnista Lavazza Qualita Oro 1kg",
     "description": "Kawa ziarnista 100% Arabica, srednie palenie, opakowanie 1kg",
     "price": 79.0, "category": "food", "delivery_days": 2, "unit": "szt", "image": "coffee",
     "supplier_name": "Lavazza", "contract_no": "FWZ/2024/ZYW-001"},
    {"id": "PO-ZYW-002", "name": "Woda mineralna Zywiec Zdroj 1.5L (6 szt)",
     "description": "Woda zródlana niegazowana, zgrzewka 6 x 1.5L, PET",
     "price": 12.0, "category": "food", "delivery_days": 1, "unit": "zgrzewka", "image": "water",
     "supplier_name": "Zywiec Zdroj", "contract_no": "FWZ/2024/ZYW-001"},
    {"id": "PO-ZYW-003", "name": "Herbata Lipton Yellow Label (100 torebek)",
     "description": "Herbata czarna ekspresowa, 100 torebek, pojedynczo pakowanych",
     "price": 22.0, "category": "food", "delivery_days": 1, "unit": "op", "image": "tea",
     "supplier_name": "Unilever", "contract_no": "FWZ/2024/ZYW-001"},
    {"id": "PO-ZYW-004", "name": "Cukier bialy w saszetkach 5g (1000 szt)",
     "description": "Cukier bialy krysztal, saszetki 5g, karton 1000 szt",
     "price": 65.0, "category": "food", "delivery_days": 2, "unit": "karton", "image": "sugar",
     "supplier_name": "Diamant", "contract_no": "FWZ/2024/ZYW-002"},

    # ── HVAC / klimatyzacja ────────────────────────────────────────
    {"id": "PO-HVC-001", "name": "Klimatyzator Daikin Sensira FTXF35D 3.5kW",
     "description": "Klimatyzator split, chlodzenie 3.5kW, grzanie 4.0kW, A++, Wi-Fi ready",
     "price": 3290.0, "category": "hvac", "delivery_days": 7, "unit": "kpl", "image": "ac",
     "supplier_name": "Daikin", "contract_no": "FWZ/2024/HVC-001"},
    {"id": "PO-HVC-002", "name": "Filtr kasetowy G4 592x592x48mm (5 szt)",
     "description": "Filtr powietrza panelowy G4 do central wentylacyjnych, 5 szt",
     "price": 120.0, "category": "hvac", "delivery_days": 3, "unit": "op", "image": "air-filter",
     "supplier_name": "Lindab", "contract_no": "FWZ/2024/HVC-002"},

    # ── Uslugi / SaaS ─────────────────────────────────────────────
    {"id": "PO-SRV-001", "name": "Microsoft 365 Business Standard (roczna licencja)",
     "description": "Licencja roczna M365 Business Standard: Teams, Exchange, SharePoint, 1TB OneDrive",
     "price": 590.0, "category": "it", "delivery_days": 0, "unit": "licencja/rok", "image": "license",
     "supplier_name": "Microsoft", "contract_no": "FWZ/2024/SRV-001"},
    {"id": "PO-SRV-002", "name": "Adobe Creative Cloud All Apps (roczna licencja)",
     "description": "Subskrypcja roczna Adobe CC: Photoshop, Illustrator, InDesign, Premiere Pro, 100GB",
     "price": 2490.0, "category": "it", "delivery_days": 0, "unit": "licencja/rok", "image": "license",
     "supplier_name": "Adobe", "contract_no": "FWZ/2024/SRV-002"},
    {"id": "PO-SRV-003", "name": "Serwis klimatyzacji — przeglad roczny (1 urzadzenie)",
     "description": "Przeglad roczny klimatyzatora: czyszczenie, kontrola czynnika, filtr, raport",
     "price": 350.0, "category": "hvac", "delivery_days": 5, "unit": "usluga", "image": "service",
     "supplier_name": "Daikin Service", "contract_no": "FWZ/2024/SRV-003"},
]


def punchout_setup(buyer_cookie: str = "", browser_form_post_url: str = "") -> tuple[str, str]:
    """Create a PunchOut session. Returns (session_id, cxml_response)."""
    session_id = str(uuid.uuid4())[:8]
    if not buyer_cookie:
        buyer_cookie = f"FLOW-{session_id}"

    session = PunchOutSession(
        session_id=session_id,
        buyer_cookie=buyer_cookie,
        browser_form_post_url=browser_form_post_url or "https://flow-procurement.up.railway.app/api/v1/marketplace/punchout/return",
    )
    _punchout_sessions[session_id] = session

    # Build cXML response
    browse_url = f"/api/v1/marketplace/punchout/browse/{session_id}"
    xml_response = _build_setup_response(session_id, browse_url)

    logger.info("PunchOut session created: %s", session_id)
    return session_id, xml_response


def punchout_get_session(session_id: str) -> PunchOutSession | None:
    return _punchout_sessions.get(session_id)


def punchout_browse(session_id: str, category: str = "") -> list[dict]:
    """Browse PunchOut catalog — combines Allegro mock + dedicated PunchOut items.

    Simulates a real cXML PunchOut integration with Allegro as external supplier.
    Optional category filter maps our domains to Allegro-style tags.
    """
    session = _punchout_sessions.get(session_id)
    if not session or session.status != "active":
        return []

    # ── Map our categories to Allegro search tags ──
    _CATEGORY_TAG_MAP = {
        "it": "laptop komputer monitor drukarka toner ssd switch",
        "office": "papier biuro segregator dlugopis tablica",
        "furniture": "krzeslo biurko szafa fotel meble",
        "safety": "bhp rekawice okulary kask buty apteczka kamizelka ochrona",
        "tools": "wiertarka narzedzia klucze szlifierka pila kompresor",
        "cleaning": "czystosc recznik mydlo plyn worki higiena",
        "chemicals": "chemia wd40 smar odrdzewiacz",
        "electrical": "led panel zarowka oswietlenie kabel elektro",
        "packaging": "karton opakowanie folia tasma paleta logistyka",
        "oils": "olej motoryzacja castrol",
        "parts": "klocki hamulcowe filtr motoryzacja opony akumulator brembo",
        "food": "kawa woda herbata cukier zywnosc",
        "hvac": "klimatyzacja filtr wentylacja",
    }

    # Collect Allegro mock items (tagged as punchout source)
    items = []
    seen_ids = set()

    # 1) Allegro mock items
    for p in _MOCK_ALLEGRO:
        if category:
            tags_to_match = _CATEGORY_TAG_MAP.get(category, category)
            searchable = (p["name"] + " " + p.get("_tags", "")).lower()
            if not any(t in searchable for t in tags_to_match.split()):
                continue

        pid = f"PO-{session_id}-{p['id']}"
        seen_ids.add(pid)
        items.append({
            **p,
            "id": pid,
            "source": "punchout",
            "punchout_session": session_id,
        })

    # 2) Dedicated PunchOut catalog items (additional enterprise products)
    for p in _PUNCHOUT_CATALOG:
        if category:
            if p.get("category", "") != category:
                continue

        pid = f"PO-{session_id}-{p['id']}"
        if pid not in seen_ids:
            items.append({
                **p,
                "id": pid,
                "source": "punchout",
                "punchout_session": session_id,
            })

    return items


def punchout_add_to_cart(session_id: str, item_id: str, name: str, price: float, qty: int = 1) -> bool:
    """Add item to PunchOut session cart."""
    session = _punchout_sessions.get(session_id)
    if not session or session.status != "active":
        return False

    # Check if item already in cart
    for ci in session.cart_items:
        if ci["id"] == item_id:
            ci["qty"] += qty
            return True

    session.cart_items.append({
        "id": item_id, "name": name, "price": price, "qty": qty, "unit": "EA"
    })
    return True


def punchout_return_cart(session_id: str) -> tuple[list[dict], str]:
    """Finalize PunchOut session. Returns (cart_items, cxml_order_message)."""
    session = _punchout_sessions.get(session_id)
    if not session:
        return [], ""

    session.status = "completed"
    xml = _build_order_message(session)
    return session.cart_items, xml


def punchout_list_sessions() -> list[dict]:
    """List all PunchOut sessions (admin/debug)."""
    return [
        {
            "session_id": s.session_id,
            "status": s.status,
            "buyer_cookie": s.buyer_cookie,
            "cart_items": len(s.cart_items),
            "created_at": s.created_at,
        }
        for s in _punchout_sessions.values()
    ]


# ── cXML builders ───────────────────────────────────────────────

def _build_setup_response(session_id: str, browse_url: str) -> str:
    """Build cXML PunchOutSetupResponse."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    payload_id = hashlib.md5(f"{session_id}{ts}".encode()).hexdigest()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE cXML SYSTEM "http://xml.cxml.org/schemas/cXML/1.2.014/cXML.dtd">
<cXML payloadID="{payload_id}" timestamp="{ts}" xml:lang="pl">
  <Response>
    <Status code="200" text="OK">Success</Status>
    <PunchOutSetupResponse>
      <StartPage>
        <URL>{browse_url}</URL>
      </StartPage>
    </PunchOutSetupResponse>
  </Response>
</cXML>"""


def _build_order_message(session: PunchOutSession) -> str:
    """Build cXML PunchOutOrderMessage from session cart."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    payload_id = hashlib.md5(f"{session.session_id}-return-{ts}".encode()).hexdigest()
    total = sum(ci["price"] * ci["qty"] for ci in session.cart_items)

    items_xml = ""
    for ci in session.cart_items:
        items_xml += f"""
      <ItemIn quantity="{ci['qty']}">
        <ItemID>
          <SupplierPartID>{ci['id']}</SupplierPartID>
        </ItemID>
        <ItemDetail>
          <UnitPrice><Money currency="PLN">{ci['price']:.2f}</Money></UnitPrice>
          <Description xml:lang="pl">{ci['name']}</Description>
          <UnitOfMeasure>{ci['unit']}</UnitOfMeasure>
        </ItemDetail>
      </ItemIn>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE cXML SYSTEM "http://xml.cxml.org/schemas/cXML/1.2.014/cXML.dtd">
<cXML payloadID="{payload_id}" timestamp="{ts}" xml:lang="pl">
  <Header>
    <From><Credential domain="FlowProcurement"><Identity>flow-marketplace</Identity></Credential></From>
    <To><Credential domain="Buyer"><Identity>{session.buyer_cookie}</Identity></Credential></To>
    <Sender><Credential domain="FlowProcurement"><Identity>flow</Identity></Credential></Sender>
  </Header>
  <Message>
    <PunchOutOrderMessage>
      <BuyerCookie>{session.buyer_cookie}</BuyerCookie>
      <PunchOutOrderMessageHeader operationAllowed="edit">
        <Total><Money currency="PLN">{total:.2f}</Money></Total>
      </PunchOutOrderMessageHeader>{items_xml}
    </PunchOutOrderMessage>
  </Message>
</cXML>"""
