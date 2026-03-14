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


def punchout_browse(session_id: str) -> list[dict]:
    """Return mock catalog for PunchOut browsing."""
    session = _punchout_sessions.get(session_id)
    if not session or session.status != "active":
        return []

    # Return a subset of our internal catalog tagged as PunchOut source
    from app.buying_engine import CATALOG
    items = []
    for p in CATALOG[:30]:
        items.append({
            **p,
            "id": f"PO-{session_id}-{p['id']}",
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
