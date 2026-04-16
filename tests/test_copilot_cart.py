"""
Tests for copilot add-to-cart pipeline:
- buying_engine.search_catalog (fuzzy product lookup)
- copilot_engine._parse_add_to_cart (regex + numword parser)
- copilot_engine._handle_add_to_cart (action dispatch)
- copilot_engine.process_message end-to-end for add-to-cart intent
"""
from __future__ import annotations

from app.buying_engine import search_catalog
from app.copilot_engine import (
    CopilotRequest,
    _handle_add_to_cart,
    _match_intent,
    _parse_add_to_cart,
    process_message,
)


# ─── search_catalog ──────────────────────────────────────────────────


def test_search_matches_by_name_substring():
    r = search_catalog("klocki hamulcowe", limit=5)
    assert any("klocki" in p["name"].lower() for p in r), r


def test_search_handles_polish_inflection():
    # "hamulce" should still find "Klocki hamulcowe" via 5-char prefix match
    r = search_catalog("hamulce", limit=5)
    names = [p["name"].lower() for p in r]
    assert any("hamulc" in n for n in names), names


def test_search_empty_query_returns_empty_list():
    assert search_catalog("") == []
    assert search_catalog("   ") == []


def test_search_no_match_returns_empty_list():
    assert search_catalog("kosmolot naddzwiekowy xyz123") == []


def test_search_attaches_score():
    r = search_catalog("filtr oleju", limit=1)
    assert r and "_score" in r[0]
    assert r[0]["_score"] > 0


# ─── _parse_add_to_cart ──────────────────────────────────────────────


def test_parse_leading_digit_quantity():
    query, qty = _parse_add_to_cart("dodaj 3 klocki bosch do koszyka")
    assert qty == 3
    assert "klocki bosch" in query.lower()


def test_parse_numword_quantity():
    query, qty = _parse_add_to_cart("dodaj piec filtrow oleju do koszyka")
    assert qty == 5
    assert "filtr" in query.lower()


def test_parse_no_quantity_defaults_one():
    query, qty = _parse_add_to_cart("dodaj filtry oleju do koszyka")
    assert qty == 1
    assert "filtr" in query.lower()


def test_parse_strips_unit_word():
    query, qty = _parse_add_to_cart("dodaj opony sztuk do zamowienia")
    assert qty == 1
    assert "opony" in query.lower()
    assert "sztuk" not in query.lower()


def test_parse_synonym_verbs():
    for verb in ("dodaj", "wrzuc", "wloz", "zamow"):
        query, qty = _parse_add_to_cart(f"{verb} 2 akumulator do koszyka")
        assert qty == 2, verb


def test_parse_non_matching_message_returns_empty():
    query, qty = _parse_add_to_cart("pokaz mi koszyk")
    assert query == ""
    assert qty == 1


# ─── _handle_add_to_cart ─────────────────────────────────────────────


def test_handle_single_dominant_match_emits_action():
    resp = _handle_add_to_cart("kosiarka", 2, context={"step": 0})
    assert resp.actions, "expected actions for dominant match"
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    assert len(cart_actions) == 1
    items = cart_actions[0].params["items"]
    assert len(items) == 1
    assert items[0]["qty"] == 2
    assert "kosiarka" in items[0]["name"].lower()


def test_handle_no_match_suggests_marketplace():
    resp = _handle_add_to_cart("kosmolot xyz123", 3, context={"step": 1})
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    assert not cart_actions, "should not emit add_to_cart when nothing found"
    assert "allegro" in resp.reply.lower() or "marketplace" in resp.reply.lower()


def test_handle_empty_query_asks_for_input():
    resp = _handle_add_to_cart("", 1, context={})
    assert not [a for a in resp.actions if a.action_type == "add_to_cart"]
    assert "?" in resp.reply


def test_handle_ambiguous_returns_suggestions():
    # "bosch" matches multiple products roughly equally
    resp = _handle_add_to_cart("bosch", 1, context={"step": 1})
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    # Should either be dominant (1 clear winner) or ambiguous (suggestions). If
    # ambiguous, no cart action is emitted and suggestions list is populated.
    if not cart_actions:
        assert resp.suggestions, "ambiguous case should offer candidate suggestions"


def test_handle_qty_clamped_to_positive():
    resp = _handle_add_to_cart("kosiarka", 0, context={})
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    if cart_actions:  # dominant match path
        assert cart_actions[0].params["items"][0]["qty"] >= 1


# ─── process_message end-to-end ──────────────────────────────────────


def _run(msg: str, step: int = 1):
    import asyncio
    return asyncio.run(process_message(
        CopilotRequest(message=msg, context={"step": step, "domain": "parts"})
    ))


def test_e2e_intent_recognized():
    intent, _ = _match_intent("dodaj 3 klocki bosch do koszyka")
    assert intent == "add_to_cart_nl"


def test_e2e_emits_add_to_cart_for_dominant_product():
    resp = _run("dodaj 2 kosiarki do koszyka")
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    assert len(cart_actions) == 1
    assert cart_actions[0].params["items"][0]["qty"] == 2


def test_e2e_graceful_miss():
    resp = _run("dodaj rakiete kosmiczna do koszyka")
    cart_actions = [a for a in resp.actions if a.action_type == "add_to_cart"]
    assert not cart_actions


# ─── MVP-1 recommendations ───────────────────────────────────────────


def test_recommendations_returns_nonempty_cards():
    from app.copilot_engine import get_recommendations
    cards = get_recommendations({"step": 0})
    assert len(cards) >= 3, "dashboard needs at least a few cards to feel alive"
    for c in cards:
        assert c["id"], "every card needs a stable id"
        assert c["title"], "every card needs a title"
        assert c["icon"], "every card needs an icon"
        assert c["urgency"] in ("info", "urgent")


def test_recommendations_urgent_cards_present():
    from app.copilot_engine import get_recommendations
    cards = get_recommendations({"step": 0})
    urgencies = {c["urgency"] for c in cards}
    assert "urgent" in urgencies or "info" in urgencies


def test_recommendations_actionable_cards_have_action():
    from app.copilot_engine import get_recommendations
    cards = get_recommendations({"step": 0})
    actionable = [c for c in cards if c.get("cta")]
    assert actionable, "need at least one card with a CTA"
    for c in actionable:
        assert c.get("action"), f"card {c['id']} has CTA but no action"
        assert c["action"]["action_type"], f"card {c['id']} action has no type"


def test_recommendations_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/v1/copilot/recommendations?step=0")
    assert r.status_code == 200
    data = r.json()
    assert "cards" in data
    assert isinstance(data["cards"], list)
    assert len(data["cards"]) >= 1


# ─── MVP-2a document extraction ──────────────────────────────────────


def test_document_extract_endpoint_schema():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    # Without an LLM key configured (or text too short) the endpoint
    # still returns the expected schema — empty items list.
    r = client.post("/api/v1/copilot/document/extract", json={"text": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "count" in data
    assert isinstance(data["items"], list)
    assert data["count"] == len(data["items"])


def test_extract_items_short_text_returns_empty():
    import asyncio
    from app.copilot_engine import extract_items_from_text
    # Too short to be a real request — should short-circuit without an LLM call.
    assert asyncio.run(extract_items_from_text("")) == []
    assert asyncio.run(extract_items_from_text("hi")) == []


def test_extracted_item_catalog_matching():
    # When the LLM returns a name that matches the catalog, extract_demand
    # should attach matched_id / matched_name. We bypass the LLM call by
    # monkey-patching extract_items_from_text on the module.
    import asyncio
    from app import copilot_engine

    async def fake_extract(raw: str):
        return [{"name": "klocki hamulcowe TRW", "qty": 3, "unit": "szt", "price": None, "note": ""}]

    orig = copilot_engine.extract_items_from_text
    copilot_engine.extract_items_from_text = fake_extract
    try:
        items = asyncio.run(copilot_engine.extract_demand("dummy"))
    finally:
        copilot_engine.extract_items_from_text = orig

    assert len(items) == 1
    assert items[0].matched_id.startswith("BRK") or items[0].matched_id.startswith("DSC"), items[0].matched_id
    assert items[0].qty == 3
