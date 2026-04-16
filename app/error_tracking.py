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


def _scrub_sensitive(event: dict, hint: dict) -> dict:
    """Strip header / query / body keys that might leak tokens or PII
    before the event leaves the process."""
    _SENSITIVE = {"authorization", "cookie", "x-api-key", "x-turso-auth",
                  "password", "token", "api_key", "jwt_secret"}
    try:
        req = event.get("request") or {}
        headers = req.get("headers") or {}
        for key in list(headers.keys()):
            if key.lower() in _SENSITIVE:
                headers[key] = "[redacted]"
        query = req.get("query_string") or ""
        if any(tok in query.lower() for tok in _SENSITIVE):
            req["query_string"] = "[redacted]"
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
