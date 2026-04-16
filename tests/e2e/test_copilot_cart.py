"""
Browser E2E: user types 'dodaj 3 klocki hamulcowe do koszyka' into
the assistant panel and the global cart badge updates to 3.

Exercises the full JS stack: assistant input → POST /copilot/chat →
action dispatcher → s1AddToCartFromCopilot → updateGlobalCartBadge.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_copilot_add_to_cart_updates_badge(page: Page, live_base_url: str):
    page.goto(f"{live_base_url}/ui")
    page.wait_for_load_state("networkidle")

    # Assistant chat input is always visible in the assistant-mode panel
    input_ = page.locator("#copilotInput")
    expect(input_).to_be_visible(timeout=10_000)

    # Badge is hidden until cart has items
    badge = page.locator("#globalCartBadge")

    input_.fill("dodaj 3 klocki hamulcowe do koszyka")
    input_.press("Enter")

    # Wait for the badge to show up with the right count. We use a locator
    # assertion (retries automatically) so timing jitter doesn't make the
    # test flake.
    expect(badge).to_be_visible(timeout=15_000)
    expect(badge).to_have_text("3", timeout=5_000)

    # Copilot reply must have landed in the transcript
    messages = page.locator("#copilotMessages").inner_text()
    assert "klocki" in messages.lower() or "hamulc" in messages.lower()
