---
title: "🌙 Nightly smoke failed"
labels: prod-incident, smoke-test, scheduled
---

Scheduled (cron) smoke test failed against production.

- **Run time**: {{ env.RUN_DATE }}
- **Run logs**: {{ env.RUN_URL }}

Differs from post-deploy smoke: this fires daily regardless of
pushes. A failure here without a recent deploy usually means:

- An external dependency degraded (Anthropic LLM API, Turso).
- A time-based bug kicked in (contract expired, token rotation due).
- A secret expired or was revoked.

## Triage

1. Check `ops/ONCALL.md` for the common failure modes + fixes.
2. `curl -s https://flow-procurement.up.railway.app/health/ready | jq`
   — check `.checks` for anything with `status != ok`.
3. Railway Metrics tab — look for memory / CPU climb overnight.
4. Anthropic status page: https://status.anthropic.com/
5. Turso console: https://console.turso.tech/

This issue auto-updates on subsequent nightly failures. Close once
prod is healthy again.
