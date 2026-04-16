# Deployment guide

Flow Procurement deploys to Railway from `main` on every push. This
document covers the full lifecycle: first-time setup, ongoing deploys,
staging environment, and the go-live checklist.

## Current topology

- **GitHub**: `github.com/pawelmamcarz/flow-procurement` (push to main = deploy)
- **Railway**: single service, single replica, `europe-west4` region
- **Domain**: `flow-procurement.up.railway.app` (Railway-managed TLS)
- **Database**: Turso/libSQL (optional — falls back to SQLite in-container)
- **Container**: `Dockerfile` runtime (Python 3.11-slim + OCR stack)
- **Startup**: `start.sh` → `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`

## First-time Railway setup

1. Create project → connect GitHub repo → pick `main` branch.
2. Enable **Docker** builder (auto-detected from `Dockerfile` +
   `railway.json`).
3. Set **Variables** (all required unless marked optional):

   **Core**
   - `FLOW_JWT_SECRET` — 64+ random chars (critical).
   - `FLOW_LLM_API_KEY` — Anthropic key for the AI copilot.
   - `FLOW_GEMINI_API_KEY` — Google key (fallback only).

   **Database** (optional but recommended for prod persistence)
   - `FLOW_TURSO_DATABASE_URL`
   - `FLOW_TURSO_AUTH_TOKEN`

   **Hardening** (recommended for prod)
   - `FLOW_RATE_LIMIT_PER_MINUTE=120`
   - `FLOW_CORS_ORIGINS=https://flow-procurement.up.railway.app`
   - `FLOW_SENTRY_DSN=...` (optional but high-value)

   Full list in `.env.example`.

4. Deploy. First build takes ~5 minutes (scipy + numpy + highspy +
   tesseract). Subsequent builds reuse layers and finish in ~30 seconds.
5. Verify: `curl https://<service>.up.railway.app/health/ready` should
   return 200 with `status: "ok"` and all checks non-degraded.

## Routine deploy

Push to `main`. Railway picks it up automatically.

### Before you push

- Run tests locally: `pytest tests/ -v` — all 150+ green.
- Commit message follows the format in `CONTRIBUTING.md`.
- If you changed `requirements.txt` or `Dockerfile`, expect a full
  rebuild (~5 min).
- If you added a new secret, set it in Railway Variables **before**
  pushing — the deploy will fail health-check otherwise.

### During deploy

1. Watch **Build Logs** — should get a green `Build time: N seconds`
   within 3-8 minutes.
2. **Deploy Logs** — look for `INFO: Uvicorn running on ...` and
   `INFO: Application startup complete.` (x2 for 2 workers).
3. Healthcheck starts 10s after container start; expect
   `[1/1] Healthcheck succeeded!` within 30s.

### Verify prod

```bash
# Readiness probe — all subsystems should be ok
curl https://flow-procurement.up.railway.app/health/ready | jq

# Badge shows the new version
curl -s https://flow-procurement.up.railway.app/ui | grep -o 'v5\.1\.[0-9]*' | head -1

# A spot check on each surface
curl -sf https://flow-procurement.up.railway.app/api/v1/bi/status > /dev/null
curl -sf https://flow-procurement.up.railway.app/api/v1/domains/extended > /dev/null
```

### Rollback

```bash
git revert <bad-sha>
git push origin main
```

Railway redeploys the revert commit. Pre-commit hook bumps the PATCH
version so the rollback is distinguishable from the original deploy.

## Staging environment (proposed, not yet wired)

Right now `main` → prod with no gate. Plan for an isolated staging
tier:

1. **Railway**: create a second service in the same project, name it
   `flow-procurement-staging`, point at a `staging` branch.
2. **Branch flow**: feature branches → PR into `staging` → PR into
   `main` → prod. The `staging` service rebuilds on every merge to
   `staging`.
3. **Variables**: mirror prod but use separate `FLOW_TURSO_*`,
   `FLOW_SENTRY_ENV=staging`, test LLM keys if available.
4. **Domain**: `flow-procurement-staging.up.railway.app`.
5. **Smoke gate**: add a CI step that runs `ops/load-test.js` against
   staging after each merge; block `main` merges when staging load
   test fails thresholds.

Estimated effort: 0.5 day of Railway config + ~2h CI plumbing.

## Go-live checklist

One-time review before announcing the platform to outside users.

### Security
- [ ] `FLOW_JWT_SECRET` rotated to a production-grade random value
      (not the placeholder from `.env.example`).
- [ ] `FLOW_CORS_ORIGINS` restricted to real origins (no `*`, no
      localhost).
- [ ] `FLOW_RATE_LIMIT_PER_MINUTE` set to a non-zero value (120 is
      the default recommendation).
- [ ] `FLOW_SENTRY_DSN` configured and a test event captured.
- [ ] SSH access to Railway limited to maintainer accounts.
- [ ] GitHub: branch protection on `main` (require PR review before
      merge).

### Data
- [ ] Turso database created, credentials stored in Railway Variables.
- [ ] `/health/ready.checks.database.status` returns `"ok"` with
      latency < 100ms.
- [ ] Demo contracts + orders seeded successfully (first request to
      `/buying/contracts` triggers the seed).
- [ ] Real supplier data (if applicable) imported in a non-demo
      tenant via `POST /buying/suppliers/...` endpoints.

### Observability
- [ ] `/metrics` returns current counts after a few minutes of
      traffic.
- [ ] JSON log lines visible in Railway Deploy Logs — one per
      request with rid + latency.
- [ ] Sentry dashboard shows the release tag `flow-procurement@5.1.x`.
- [ ] ONCALL.md has correct contact emails.

### Performance
- [ ] `ops/load-test.js` passes thresholds against prod at 10 VU.
- [ ] Initial dashboard load (Step 0) completes in < 2s p95.
- [ ] `/dashboard/pareto-xy-mc` with default params finishes in < 3s.

### Dependencies
- [ ] Dependabot enabled (`.github/dependabot.yml` committed).
- [ ] `pip-audit` or `safety check` clean (no high-severity
      vulnerabilities).
- [ ] Docker base image (`python:3.11-slim`) on the latest patch.

### UX smoke
- [ ] Dashboard action cards load with real counts (pending approvals).
- [ ] "Wklej dokument" flow extracts items from a pasted email.
- [ ] "Policz scoring" on Step 2 ranks suppliers Top 5 / Bottom 3.
- [ ] "Odpal MC" generates a confidence fan in < 5s.
- [ ] "Chain What-If" produces a 5-step timeline.
- [ ] Mobile (DevTools 375px width) — no horizontal scroll.

### Docs
- [ ] CHANGELOG.md updated with the go-live version.
- [ ] CONTRIBUTING.md and SECURITY.md link from README.
- [ ] PROJECT.md reflects current endpoint list.

## Post-deploy observability sweep (weekly)

- Top 5 slowest routes from `/metrics` — investigate anything new.
- Error rate per route — check Sentry grouping for the top issue.
- Rate-limit 429s — bump `FLOW_RATE_LIMIT_PER_MINUTE` if legit
  traffic is hitting the ceiling.
- Disk / memory on Railway Metrics tab.
