# On-call playbook

Compact runbook for Flow Procurement incidents. Targets the **production
Railway deployment** (`flow-procurement.up.railway.app`).

## 1. First 5 minutes — triage

1. **Is the app up?** `curl -sf https://flow-procurement.up.railway.app/health`
   - 200 `{"status":"ok","version":"5.1.x"}` → process is running
   - Timeout / 502 → jump to section 2 (container down)
2. **Is it healthy deep?** `curl -sf .../health/ready` → per-subsystem
   verdict. Red on `database` or `solver` is a hard incident.
3. **What's wrong?** Check `/metrics` → sort by `error_rate` desc, look
   at `p99_ms` to find the slow / broken route.
4. **What changed?** Railway → Deployments tab → latest deploy. Compare
   SHA against `main` history.

## 2. Common failure modes

### 2.1 Container won't start

Symptoms: Railway Deploy Logs loop with stack traces or `Error: …`.

Likely causes and fixes:
- **Missing env var** (`FLOW_JWT_SECRET` etc.) → Railway → Variables →
  add/correct → redeploy. The list is in `.env.example`.
- **Dockerfile build regression** → check GitHub Actions `docker-build`
  job on the last PR. CI runs a smoke `/health` check so this should
  catch most cases pre-merge.
- **Dependency drift** → look for pypdf / tesseract / sentry-sdk import
  errors in Deploy Logs. Pin in `requirements.txt`.

Rollback: `git revert <sha> && git push` — Railway auto-redeploys.

### 2.2 5xx spike

Symptoms: `/metrics` shows `error_rate > 0.05` on one or more routes.

Check in order:
- **Sentry** (if `FLOW_SENTRY_DSN` set) — sorted by frequency/recency.
- **JSON request logs** — grep by `"rid":"<id>"` to trace a single
  request through.
- **LLM outage** — copilot / document extract routes fail? Check
  `/health/ready.checks.llm.status`. Anthropic status page:
  `https://status.anthropic.com/`. Gemini fallback kicks in
  automatically; if it also fails the endpoint returns 502.

Mitigations:
- Bump `FLOW_RATE_LIMIT_PER_MINUTE` if users are self-DoSing.
- Switch `FLOW_PDF_OCR_ENABLED=false` if Tesseract crashes on a
  specific file.

### 2.3 Slow responses (p99 > 5s)

Symptoms: `/metrics.routes[*].p99_ms` breaches 5000 on one route.

By route:
- `/dashboard/pareto-xy-mc*` — reduce `mc_iterations` query param.
- `/buying/suppliers/scorecard` — the catalog grew; consider the
  `limit` query param instead of loading everything.
- `/copilot/document/extract-file` — oversized scanned PDF;
  the 5 MB guard helps. If OCR itself is slow, disable and ask
  the user to paste text.
- Generic `/api/v1/*` — check `/health/ready.database.latency_ms`.
  If DB slow, Turso console has live query stats.

### 2.4 Wrong data on dashboard

Symptoms: counts don't reconcile with reality, cards show odd numbers.

- Check `X-Tenant-ID` header or JWT payload — is the user in the
  right tenant? Everything downstream filters on it.
- Contracts table is seeded only for `demo`. Other tenants start
  empty (by design).
- The demo seeder makes one generator pass per module reload; if you
  restart the process you get a fresh deterministic set, but if other
  data exists in the cache (orders) it's stale. Rare in prod.

## 3. Ops runbook

### Roll version back
1. `git log --oneline -10` — find the pre-incident SHA.
2. `git revert <incident-sha>` — or fast-forward: `git reset --hard
   <pre-incident>` and force push (use sparingly, coordinate first).
3. Railway auto-deploys the new SHA in ~3 minutes.

### Rotate secrets
- `FLOW_JWT_SECRET`: generate 64-char random, update Railway Variables,
  redeploy. **All existing JWT tokens invalidated** — users need to
  re-login. Do this in a low-traffic window.
- `FLOW_LLM_API_KEY` / `FLOW_GEMINI_API_KEY`: same flow, no user
  impact beyond the brief window where the old key is revoked and the
  new one isn't deployed yet.
- `FLOW_TURSO_AUTH_TOKEN`: Turso dashboard → Tokens → revoke old +
  generate new → update Railway → redeploy.

### Force DB re-seed
Should never be needed — `init_db()` is idempotent. If contracts
vanish, check `contracts` table in Turso console directly.

### Investigate a specific request
1. User reports a bad response. Ask them for `X-Request-ID` (we send
   it in the response header — UI should surface this in a future
   sprint).
2. Railway log search → grep that rid in the JSON log stream.
3. Match against Sentry — same rid is tagged there.

## 4. Contacts

- **Platform owner**: mamcarz@...
- **Railway account**: same
- **Anthropic**: support@anthropic.com (LLM outages)
- **Turso**: console.turso.tech (DB issues)

## 5. Paging thresholds

These aren't wired yet but documenting the intent so we know what to
build when adding PagerDuty / Opsgenie / email alerts:

| Signal | Threshold | Severity |
|--------|-----------|----------|
| `/health` fails 3 consecutive probes | 30s | P1 — wake someone |
| Error rate on any `/api/v1/*` route | > 5% over 5min | P2 |
| p99 latency any route | > 10s over 5min | P3 |
| Sentry event rate | > 10 events/min | P2 |
| Rate-limit 429s | > 100/min | P3 (capacity issue) |
