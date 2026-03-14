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

_MOCK_ALLEGRO: list[dict] = [
    {"id": "ALLEGRO-MOCK-1", "name": "Laptop Lenovo ThinkPad T14 Gen5 i7/16GB/512SSD", "price": 5499.00, "currency": "PLN",
     "category": "marketplace", "unit": "szt", "image_url": "", "delivery_cost": 0,
     "suppliers": [{"id": "SUP-ALLEGRO-LENOVO", "name": "LenovoPartner_PL", "unit_price": 5499.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-1"},
    {"id": "ALLEGRO-MOCK-2", "name": "Monitor Dell UltraSharp U2723QE 27\" 4K USB-C", "price": 2199.00, "currency": "PLN",
     "category": "marketplace", "unit": "szt", "image_url": "", "delivery_cost": 0,
     "suppliers": [{"id": "SUP-ALLEGRO-DELL", "name": "DellStore_Official", "unit_price": 2199.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-2"},
    {"id": "ALLEGRO-MOCK-3", "name": "Krzeslo biurowe Ergohuman Elite G2 mesh", "price": 3890.00, "currency": "PLN",
     "category": "marketplace", "unit": "szt", "image_url": "", "delivery_cost": 49.99,
     "suppliers": [{"id": "SUP-ALLEGRO-ERGO", "name": "ErgoDesign24", "unit_price": 3890.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-3"},
    {"id": "ALLEGRO-MOCK-4", "name": "Papier ksero Pollux A4 80g 5 ryz (2500 ark)", "price": 89.90, "currency": "PLN",
     "category": "marketplace", "unit": "op", "image_url": "", "delivery_cost": 9.99,
     "suppliers": [{"id": "SUP-ALLEGRO-BIURO", "name": "BiuroPlus_Hurtownia", "unit_price": 89.90}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-4"},
    {"id": "ALLEGRO-MOCK-5", "name": "Toner HP 26X CF226X oryginalny 9000 str.", "price": 459.00, "currency": "PLN",
     "category": "marketplace", "unit": "szt", "image_url": "", "delivery_cost": 0,
     "suppliers": [{"id": "SUP-ALLEGRO-HP", "name": "HPSupplies_PL", "unit_price": 459.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-5"},
    {"id": "ALLEGRO-MOCK-6", "name": "Wiertarko-wkretarka Makita DDF484Z 18V LXT body", "price": 649.00, "currency": "PLN",
     "category": "marketplace", "unit": "szt", "image_url": "", "delivery_cost": 0,
     "suppliers": [{"id": "SUP-ALLEGRO-MAKITA", "name": "MakitaPro_PL", "unit_price": 649.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-6"},
    {"id": "ALLEGRO-MOCK-7", "name": "Rekawice robocze nitrylowe 100szt L niebieskie", "price": 24.90, "currency": "PLN",
     "category": "marketplace", "unit": "op", "image_url": "", "delivery_cost": 6.99,
     "suppliers": [{"id": "SUP-ALLEGRO-BHP", "name": "BHP_Expert", "unit_price": 24.90}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-7"},
    {"id": "ALLEGRO-MOCK-8", "name": "Kabel sieciowy Cat6a S/FTP 305m szpula", "price": 890.00, "currency": "PLN",
     "category": "marketplace", "unit": "szpula", "image_url": "", "delivery_cost": 19.99,
     "suppliers": [{"id": "SUP-ALLEGRO-IT", "name": "NetworkPro_PL", "unit_price": 890.00}],
     "source": "allegro_mock", "external_url": "https://allegro.pl", "external_id": "MOCK-8"},
]


def mock_allegro_search(query: str, limit: int = 20) -> list[dict]:
    """Mock search — filter mock items by query string."""
    q = query.lower()
    matches = [item for item in _MOCK_ALLEGRO if q in item["name"].lower()]
    if not matches:
        # Return all mock items if nothing matches specifically
        matches = _MOCK_ALLEGRO
    return matches[:limit]


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
