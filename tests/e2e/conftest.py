"""
tests/e2e/conftest.py — fixture spinning up a real uvicorn for browser tests.

Design:
- Session-scoped server fixture starts uvicorn in a subprocess on a
  random free port, waits for /health to return 200, yields the
  base URL, and tears the process down on session exit.
- Each test gets a fresh Playwright browser context via pytest-playwright,
  pointed at `base_url` through the `live_base_url` fixture.
- LLM calls are disabled (FLOW_LLM_API_KEY unset + no FLOW_SENTRY_DSN)
  so the copilot uses its regex / add_to_cart intent path and tests
  stay hermetic — no outbound traffic, no flakiness.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_base_url() -> str:
    port = _free_port()
    env = {
        **os.environ,
        "FLOW_JWT_SECRET": "e2e-fixture-secret",
        "FLOW_PDF_OCR_ENABLED": "false",
        "FLOW_RATE_LIMIT_PER_MINUTE": "0",   # no throttling in tests
        "FLOW_LLM_API_KEY": "",              # copilot stays on regex path
        "FLOW_SENTRY_DSN": "",
        "PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1.0) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        raise RuntimeError(f"uvicorn did not come up on {url} within 30s")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
