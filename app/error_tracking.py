"""
error_tracking.py — optional Sentry integration.

No-op when the `sentry-sdk` package isn't installed or `FLOW_SENTRY_DSN`
isn't set. Production enables it by adding the DSN to Railway Variables;
local dev leaves it off so stack traces land in the terminal instead of
a remote dashboard.

Integrates cleanly with:
  - FastAPI (auto request breadcrumbs + error capture)
  - Starlette middleware (captures inside ObservabilityMiddleware pipeline)
  - stdlib logging (warnings/errors bubble up as Sentry events)
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_initialised = False


def init_sentry() -> bool:
    """Configure Sentry if DSN + package are both available.

    Returns True when Sentry is active after the call; False when left
    disabled (no DSN, missing SDK, or double-init prevented)."""
    global _initialised
    if _initialised:
        return True

    dsn = os.environ.get("FLOW_SENTRY_DSN", "").strip()
    if not dsn:
        log.info("Sentry disabled: FLOW_SENTRY_DSN not set")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError as exc:
        log.warning("Sentry disabled: sentry-sdk not installed (%s)", exc)
        return False

    try:
        env = os.environ.get("FLOW_SENTRY_ENV", "production")
        # Attach release from the app version so Sentry groups errors by deploy.
        from app.config import settings
        release = f"flow-procurement@{settings.app_version}"

        sentry_sdk.init(
            dsn=dsn,
            release=release,
            environment=env,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            # Sampling: 100% error events, 10% performance traces to keep
            # quota sane. Override via FLOW_SENTRY_TRACES_SAMPLE_RATE.
            traces_sample_rate=float(
                os.environ.get("FLOW_SENTRY_TRACES_SAMPLE_RATE", "0.10") or 0.10
            ),
            send_default_pii=False,
            before_send=_scrub_sensitive,
        )
        _initialised = True
        log.info("Sentry enabled (release=%s, env=%s)", release, env)
        return True
    except Exception as exc:
        log.warning("Sentry init failed: %s", exc)
        return False


_SENSITIVE_KEYS = frozenset({
    "authorization", "cookie", "x-api-key", "x-turso-auth",
    "password", "token", "api_key", "jwt_secret", "refresh_token",
    "access_token", "secret", "session",
})

# NIP (Polish tax id): 10 digits, optionally with dashes. Matches common
# formats like "123-456-78-90" or "1234567890".
import re as _re
_NIP_RE = _re.compile(r"\b(\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}|\d{10})\b")
_EMAIL_RE = _re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _scrub_value(val):
    """Recursively redact sensitive keys and PII patterns in a nested value."""
    if isinstance(val, dict):
        return {k: ("[redacted]" if k.lower() in _SENSITIVE_KEYS else _scrub_value(v))
                for k, v in val.items()}
    if isinstance(val, list):
        return [_scrub_value(v) for v in val]
    if isinstance(val, str):
        s = val
        s = _EMAIL_RE.sub("[email-redacted]", s)
        s = _NIP_RE.sub("[nip-redacted]", s)
        return s
    return val


def _scrub_sensitive(event: dict, hint: dict) -> dict:
    """Strip header / query / body keys that might leak tokens or PII
    before the event leaves the process.

    Covers three surfaces that Sentry captures by default:
      1. `request.headers` — bearer tokens, cookies, API keys
      2. `request.query_string` — tokens smuggled via URL
      3. `request.data` — JSON body sometimes echoed in breadcrumbs; scrub
         recursively so nested structures don't leak nip/email/token values.
    """
    try:
        req = event.get("request") or {}
        headers = req.get("headers") or {}
        for key in list(headers.keys()):
            if key.lower() in _SENSITIVE_KEYS:
                headers[key] = "[redacted]"
        query = req.get("query_string") or ""
        if any(tok in query.lower() for tok in _SENSITIVE_KEYS):
            req["query_string"] = "[redacted]"
        # Body scrub — recursive so nested form fields / JSON dicts are covered.
        body = req.get("data")
        if body is not None:
            req["data"] = _scrub_value(body)
        # Breadcrumbs often echo request payloads too; scrub those recursively.
        for crumb in event.get("breadcrumbs", {}).get("values", []) or []:
            if crumb.get("data"):
                crumb["data"] = _scrub_value(crumb["data"])
    except Exception:
        pass
    return event


def capture_message(message: str, level: str = "info", **tags) -> None:
    """Convenience wrapper — safe to call even when Sentry is disabled."""
    if not _initialised:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, str(v))
            sentry_sdk.capture_message(message, level=level)
    except Exception as exc:
        log.debug("capture_message failed: %s", exc)
