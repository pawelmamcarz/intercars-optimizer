# Security Policy

## Supported versions

Flow Procurement ships from `main`. Only the latest tag on Railway is
supported — older versions are considered archived. Check the version
badge in the top-right of the UI (`v5.1.x`) or the `/health` endpoint.

## Reporting a vulnerability

**Do not open a public GitHub issue** for security reports. Email the
maintainer instead — response within 2 business days, fix target within
7 days for high-severity issues.

Expected content:
- Affected endpoint / component (file:line if you can pinpoint it)
- Reproduction: minimal curl / steps / payload
- Impact assessment (data exposure? privilege escalation? DoS?)
- Suggested mitigation if you have one

## Hardening checklist (ops)

**Secrets**
- `FLOW_JWT_SECRET` — rotate every 90 days. 64+ random chars.
- `FLOW_LLM_API_KEY`, `FLOW_GEMINI_API_KEY` — rotate at least quarterly
  or whenever a collaborator leaves. Keep usage tiers separate.
- `FLOW_TURSO_AUTH_TOKEN` — rotate annually; scoped to a single database.

**Transport**
- Railway terminates TLS. Don't disable HTTPS-only redirects.
- `FLOW_CORS_ORIGINS` must list exact production origins — no wildcards.

**Rate limiting**
- `FLOW_RATE_LIMIT_PER_MINUTE=120` in production. Bump to 300 if legit
  traffic starts 429-ing. In-memory; push to Redis before adding replicas.

**Auth**
- Only `admin` and `super_admin` roles can mutate catalog, suppliers,
  business rules. `buyer` role is read+checkout.
- JWT access tokens live 8h by default. Refresh tokens 30d. Disable a
  compromised user by flipping `users.is_active=0`.

**Input**
- Document uploads capped at 5 MB per file (`/copilot/document/extract-file`).
- LLM inputs truncated to 4000 chars before prompt send.
- All user-provided text is `escHtml`-ed on the frontend before `innerHTML`.

## Known risks (documented, not fixed)

- Single-replica rate limiter. Won't survive horizontal scaling — needs
  Redis or a fronting CDN layer.
- `/metrics` is unauthenticated. Useful for quick ops but expose it
  behind the admin tenant when multi-tenant deployments start.
- Demo seed data for contracts/BI is deterministic and public. Keep
  real supplier data out of the demo tenant.

## Dependencies

Automated via Dependabot:
- Weekly PRs for `pip` (grouped by minor/patch non-breaking updates)
- Weekly PRs for GitHub Actions and Dockerfile base image
- High-severity alerts open issues via GitHub Security tab

Manual audit: `pip-audit` or `safety check` before major releases.
