---
title: "🔥 Prod smoke failed on {{ env.COMMIT_SHA }}"
labels: prod-incident, smoke-test
---

Post-deploy smoke test failed.

- **Commit**: `{{ env.COMMIT_SHA }}`
- **Run logs**: {{ env.RUN_URL }}

## Triage

1. Check `ops/smoke_test.py` output in the workflow logs — the failing
   `[FAIL]` lines list which endpoint + assertion broke.
2. Confirm via prod `/health/ready` whether a subsystem degraded:
   ```
   curl -s https://flow-procurement.up.railway.app/health/ready | jq
   ```
3. If the version on prod is **older** than the failed SHA, the deploy
   itself is stuck — check Railway Deployments tab.
4. Rollback runbook lives in `ops/ONCALL.md` → "Roll version back".

## Notes

This issue auto-updates on subsequent failures (same body, same title).
Close it once `main` smokes green again; the workflow will open a new
issue if the next push breaks something different.
