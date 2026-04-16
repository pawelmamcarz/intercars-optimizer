# Alerting

ONCALL.md lists the paging thresholds we want to enforce. This doc
describes how to actually wire them up — two paths depending on how
much infrastructure you want.

## Option A — Railway + external uptime (minimal)

Best for a one-person team.

1. **Uptime monitor** — pick one of:
   - [Better Stack](https://betterstack.com) (generous free tier)
   - [Uptime Robot](https://uptimerobot.com)
   - [Healthchecks.io](https://healthchecks.io) (push-based)
2. **Checks**:
   - `GET https://flow-procurement.up.railway.app/health` every 60s
   - `GET /health/ready` every 5 minutes, alert on `status=degraded`
3. **Notification** — route to Slack / email / SMS. Threshold from
   ONCALL.md: 3 consecutive failures (~3 min) = P1.

No code changes needed. Estimated effort: 20 minutes.

## Option B — PagerDuty / Opsgenie (proper on-call)

Best when multiple people rotate on-call.

1. Create a PagerDuty service, grab the Events API integration key.
2. Set `FLOW_PAGERDUTY_ROUTING_KEY=<key>` in Railway Variables.
3. Add the alert bridge below to `app/main.py` (or a new router) —
   triggers a PD incident when an internal rule decides something
   bad is happening:

```python
# app/alerting_bridge.py  (skeleton, not wired in yet)
import httpx, os

PD_URL = "https://events.pagerduty.com/v2/enqueue"

def page(summary: str, severity: str = "error", custom: dict | None = None):
    key = os.environ.get("FLOW_PAGERDUTY_ROUTING_KEY", "").strip()
    if not key:
        return  # No-op outside prod
    payload = {
        "routing_key": key,
        "event_action": "trigger",
        "payload": {
            "summary": summary,
            "source": "flow-procurement",
            "severity": severity,
            "custom_details": custom or {},
        },
    }
    try:
        httpx.post(PD_URL, json=payload, timeout=5.0)
    except Exception:
        pass  # Don't blow up the request path over a failed page
```

4. Hook into the ObservabilityMiddleware to page when a route's
   5-minute error rate crosses 5%:

```python
# Inside the /metrics summary loop, compare against a remembered
# baseline per route. If error_rate > 0.05 for the last N requests
# AND count >= 20, call page("...").
```

5. Opsgenie works identically with its [Alert API](https://docs.opsgenie.com/docs/alert-api).

### Paging thresholds (target)

Copy from `ops/ONCALL.md` — these are the rules we want to eventually
enforce automatically:

| Signal | Threshold | Severity |
|--------|-----------|----------|
| `/health` fails 3 consecutive probes | 30s | P1 (critical) |
| Error rate on any `/api/v1/*` route | > 5% over 5min | P2 (error) |
| p99 latency any route | > 10s over 5min | P3 (warning) |
| Sentry event rate | > 10 events/min | P2 |
| Rate-limit 429s | > 100/min | P3 (capacity) |

## Runtime visibility

Three always-on signals before any paging exists:

- **Railway Metrics tab** — CPU, memory, network. Set manual alerts
  at 85% memory (saves us from OOM-kill surprises).
- **`/metrics` endpoint** — scrape every minute from a small script
  or dashboard, keep a 24h rolling view of p99 per route.
- **Structured JSON logs** — ship to Axiom / Grafana Loki / Datadog
  if you need retention beyond Railway's 7-day default.

## What NOT to alert on

- Anything slow during a cold start (first 60s after deploy). Mute
  alerts during deploys or set a 2-min grace window.
- Infeasible solver results — they're user errors (bad constraints),
  not platform errors. They're already surfaced in the UI.
- LLM 429s from Anthropic — handled by the Gemini fallback path.
  Only page when **both** upstream LLMs fail (covered by overall
  error rate anyway).
