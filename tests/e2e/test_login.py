"""
Browser E2E: the dashboard loads, the version badge is visible, and
the assistant panel renders the three action cards.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_dashboard_renders_version_and_action_cards(page: Page, live_base_url: str):
    page.goto(f"{live_base_url}/ui")

    # Version badge in the header — Tesla-style YYYY.WW.BUILD[.PATCH]
    badge = page.locator("span.badge", has_text=re.compile(r"v\d{4}\.\d+\.\d+"))
    expect(badge).to_be_visible(timeout=10_000)

    # Assistant panel swaps in on Step 0 — the toolbar text is the
    # cheapest proof it rendered
    expect(page.locator(".assistant-toolbar")).to_contain_text("Asystent zakupowy")

    # Action cards populate from /api/v1/copilot/recommendations
    cards = page.locator(".dash-action-cards .action-card")
    expect(cards.first).to_be_visible(timeout=10_000)
    # at least 3 cards — one real-signal (approvals) plus rule-based ones
    assert cards.count() >= 3


@pytest.mark.e2e
def test_copilot_endpoint_reachable_via_browser(page: Page, live_base_url: str):
    """Smoke the JS module chain: /ui must load without console errors
    that block window bindings (goStep, sendCopilotMsg, etc.)."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    page.goto(f"{live_base_url}/ui")
    page.wait_for_load_state("networkidle")

    # Ignore favicon 404 which is expected (we don't ship one)
    blocking = [e for e in errors if "favicon" not in e.lower()]
    assert not blocking, f"Console errors broke page bootstrap: {blocking}"
