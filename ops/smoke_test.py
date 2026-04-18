#!/usr/bin/env python3
"""
ops/smoke_test.py — production / staging smoke test.

Hits the 8 endpoints that matter for a dashboard page load plus the
critical copilot-add-to-cart path. Exits non-zero on any failure so
GitHub Actions can gate deploys and cron jobs.

Usage:
    BASE_URL=https://flow-procurement.up.railway.app python3 ops/smoke_test.py

Override credentials for staging / test tenants:
    SMOKE_USERNAME=admin SMOKE_PASSWORD=admin123 python3 ops/smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "https://flow-procurement.up.railway.app").rstrip("/")
USERNAME = os.environ.get("SMOKE_USERNAME", "admin")
PASSWORD = os.environ.get("SMOKE_PASSWORD", "admin123")
TIMEOUT = 15.0


def _request(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read().decode()) if r.headers.get("Content-Type", "").startswith("application/json") else {}
            return r.status, payload
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            payload = {"error": str(exc)}
        return exc.code, payload


def _check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _FAILURES.append(f"{name} — {detail}")


_FAILURES: list[str] = []


def main() -> int:
    started = time.time()
    print(f"Smoke test against {BASE_URL}")
    print("=" * 60)

    # 1. Liveness
    code, body = _request("GET", "/health")
    _check("health endpoint", code == 200 and body.get("status") == "ok",
           f"status={code}, body={body}")

    # 2. Readiness (every subsystem)
    code, body = _request("GET", "/health/ready")
    _check("health/ready status=ok", code == 200 and body.get("status") == "ok",
           f"status={code}, degraded={body.get('degraded')}")
    checks = body.get("checks", {})
    _check("  database check ok", checks.get("database", {}).get("status") in ("ok", "disabled"),
           str(checks.get("database")))
    _check("  solver check ok", checks.get("solver", {}).get("status") == "ok",
           str(checks.get("solver")))

    # 3. Metrics exposed
    code, body = _request("GET", "/metrics")
    _check("metrics endpoint returns routes+totals",
           code == 200 and "routes" in body and "totals" in body,
           f"status={code}")

    # 4. BI status (5 mock adapters)
    code, body = _request("GET", "/api/v1/bi/status")
    connectors = body.get("connectors") or []
    _check("bi/status returns >=5 connectors",
           code == 200 and len(connectors) >= 5,
           f"status={code}, count={len(connectors)}")

    # 5. Login as admin
    code, body = _request("POST", "/auth/login", {
        "username": USERNAME, "password": PASSWORD,
    })
    token = body.get("access_token") if code == 200 else None
    _check(f"auth/login as {USERNAME}", code == 200 and bool(token),
           f"status={code}, detail={body.get('detail')}")

    # 6. Copilot add-to-cart (regex path, no LLM required)
    code, body = _request("POST", "/api/v1/copilot/chat", {
        "message": "dodaj 3 klocki hamulcowe do koszyka",
        "context": {"step": 1, "domain": "parts"},
    })
    actions = body.get("actions") or []
    add_to_cart = [a for a in actions if a.get("action_type") == "add_to_cart"]
    _check("copilot add_to_cart action emitted",
           code == 200 and len(add_to_cart) == 1,
           f"status={code}, actions={[a.get('action_type') for a in actions]}")

    # 7. Contracts demo data visible (auth-gated since Faza 1.1)
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
    code, body = _request("GET", "/api/v1/buying/contracts", headers=auth_headers)
    count = body.get("count", 0) if code == 200 else 0
    _check("contracts seeded (>=1)", code == 200 and count >= 1,
           f"status={code}, count={count}")

    # 8. Recommendations render at least a few cards
    code, body = _request("GET", "/api/v1/copilot/recommendations?step=0")
    cards = body.get("cards") or []
    _check("recommendations >=3 cards",
           code == 200 and len(cards) >= 3,
           f"status={code}, count={len(cards)}")

    elapsed = time.time() - started
    print("=" * 60)
    if _FAILURES:
        print(f"\n{len(_FAILURES)} failure(s) in {elapsed:.1f}s:")
        for f in _FAILURES:
            print(f"  • {f}")
        return 1
    print(f"\nAll checks passed in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
