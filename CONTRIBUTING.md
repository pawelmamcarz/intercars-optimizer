# Contributing

Fast onboarding for people touching the repo.

## Local setup

```bash
cd intercars_optimizer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest httpx ruff
cp .env.example .env     # fill in FLOW_LLM_API_KEY, FLOW_JWT_SECRET
python3 -m uvicorn app.main:app --reload --port 8000
```

UI: `http://localhost:8000/ui` — AI assistant panel on Step 0.
API docs: `http://localhost:8000/docs` — full Swagger UI.

## Testing

```bash
pytest tests/ -v          # 148 tests across solver, BI, scorecard, copilot
pytest tests/test_copilot_cart.py -v   # focused subset
```

New feature? Add a test next to existing ones in
`tests/test_copilot_cart.py`. We don't split test files unless a module
grows beyond ~500 LOC of tests.

## Coding rules

- **No comments about the work itself.** Don't write `# added for B4
  roadmap`. If the why is obvious from naming or context, skip the
  comment. If it's non-obvious, explain the constraint, not the feature
  history.
- **Descriptive names.** `loadDashActionCards`, `_rule_yoy_anomaly`,
  `generate_pareto_with_mc` — not `fetchData1` or `_helper2`.
- **Frontend modules are ES modules.** `import` / `export` at the top,
  `type="module"` script tags in HTML. No inline globals — wire through
  `window.*` only in the bootstrap block in `index.html`.
- **Python 3.11+ typing.** Use builtin generics (`list[dict]`) and
  `X | Y` unions. `Optional[X]` only when consumed by older code.

## Commit messages

- One-line summary in imperative present: `feat: …`, `fix: …`,
  `docs: …`, `refactor: …`, `ci: …`, `polish: …`.
- Body explains *why*, references roadmap phase (A1/B2/...) when
  applicable, notes breaking changes explicitly.
- Footer: `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`
  when AI-assisted.

## Pre-commit version bump

The pre-commit hook auto-bumps the PATCH version in `app/config.py`
and the footer in `app/static/index.html`. Don't bump by hand.

## Deploy

`main` branch auto-deploys to Railway via the repo's connected
environment. No staging environment yet — every green commit on main
goes to prod. Watch the Build Logs and Deploy Logs in Railway for the
first ~5 minutes after a push.

Rollback: `git revert <sha>` + push. Railway redeploys on push.

## Adding a new dashboard widget

1. Backend data: expose via a `/api/v1/...` JSON endpoint.
2. Frontend loader: `export async function loadXWidget() { ... }` in
   `app/static/js/step0-dashboard.js`.
3. Register in `loadStartDashboard()` so it runs on every return to
   Step 0.
4. CSS: add classes prefixed `dash-x-*` in `components.css`.
5. Mobile: test at ≤768px. Widgets should stack, not scroll
   horizontally.
6. Tests: at least endpoint schema + empty-state edge case.

## Adding a new LLM-driven action

1. Declare an `action_type` string in `CopilotAction.action_type` (no
   enum — just document in `copilot_engine.py`).
2. Backend handler: a rule in `_INTENT_PATTERNS` for the regex path,
   plus a `<<ACTION:name>>{"..."}<<END>>` fallback in the tool-use
   prompt for the LLM path.
3. Frontend: `case 'name':` in `copilot.js:executeCopilotAction`.
4. Test both paths: `process_message` returns the action for a regex
   hit, and `extract_items_from_text`-style parsing handles LLM output.

## Dependencies

Dependabot opens weekly PRs. Review the grouped `non-breaking` PR,
merge if CI is green. Breaking changes open individually — triage
before merging.
