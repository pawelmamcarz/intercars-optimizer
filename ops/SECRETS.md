# Secrets management

Flow Procurement stores every secret in Railway Variables — no secrets
in git, no external vault yet. This document covers the current setup,
rotation cadence, and the migration path to a proper secrets manager
when the org grows.

## Current secrets

| Name | Purpose | Rotation cadence | Blast radius if leaked |
|------|---------|------------------|------------------------|
| `FLOW_JWT_SECRET` | Signs access + refresh tokens | 90 days | All existing JWTs forged / valid — full account takeover |
| `FLOW_LLM_API_KEY` | Anthropic API access | Quarterly or on collaborator change | Abuse of our Anthropic quota / billing |
| `FLOW_GEMINI_API_KEY` | Google Gemini fallback | Quarterly | Same as above for Google |
| `FLOW_TURSO_AUTH_TOKEN` | Turso DB write access | Annually | Full DB read/write for the target DB only |
| `FLOW_ALLEGRO_CLIENT_SECRET` | Allegro marketplace API | Vendor-controlled, rotate on compromise | Scoped to our Allegro app |
| `FLOW_SENTRY_DSN` | Error ingest endpoint | Only if compromised (DSN is semi-public) | Attackers can spam our Sentry quota |
| `FLOW_REDIS_URL` | Redis credentials (optional) | With infra change | Rate-limit and cache data |

## Storage — current

Railway → Project → Variables → per-environment. Variables encrypted at
rest by Railway. No team-wide vault; maintainers see everything.

## Storage — target (migration path)

As the team grows past a single maintainer, move to a dedicated
secrets manager. Options in order of fit:

1. **1Password Connect** — cheap, handles rotation nicely, good UX for
   a 1-5 person team. Use the Railway Secrets sync integration (if
   available) or pull at deploy time via an init container.
2. **HashiCorp Vault / Doppler** — heavier, right for 10+ engineers.
3. **AWS Secrets Manager** — if we ever leave Railway.

Estimated effort: ~1 day of setup + token plumbing.

## Rotation runbook

For a low-traffic secret (API keys), one maintainer in ~15 minutes:

1. Generate new value in the upstream service (Anthropic console,
   Turso dashboard, `openssl rand -hex 32` for JWT).
2. Railway → Variables → update the variable.
3. Manual redeploy (Deployments tab → Redeploy).
4. Verify `/health/ready` passes and the relevant feature works
   (send a copilot query, log in, write a contract).
5. Revoke the old value in the upstream service (Anthropic console
   → API keys → revoke).
6. Announce in the team channel so nobody wonders why their local
   `.env` stopped working.

For `FLOW_JWT_SECRET` specifically: step 3 logs out every active
user. Do this during low traffic.

## What lives in git (safe)

- `.env.example` — variable **names** only, never real values.
- `requirements.txt`, `Dockerfile`, all code — no hardcoded secrets
  anywhere (`git grep -i 'password\|secret\|api_key' app/` is a
  canary — running it now should only surface class/field names).

## Backup

Railway Variables survive container restarts but **not project
deletion**. Export a backup after every rotation:

```bash
# Needs Railway CLI + authentication
railway variables --json > .secrets-backup-$(date +%Y%m%d).json
# Store the file encrypted offline (1Password attachment or similar)
```
