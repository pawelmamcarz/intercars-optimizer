# Changelog

Wszystkie istotne zmiany platformy Flow Procurement.
Wersjonowanie: `MAJOR.MINOR.PATCH` — auto-bumpnięte na PATCH przez pre-commit hook.

## [Unreleased] — 2026-04-18 system audit

### Added
- **Audit komprehensywny** — 3-agentowa analiza backendu / UX / cross-cutting. Raport w `prezentacja.md` per moduł jako `Status: ✅/⚠️/❌`.
- **Status markers** w `prezentacja.md` — każda sekcja SPA ma linię statusu z listą znanych braków.
- **Roadmap z priorytetami** w §27: CRITICAL (multi-tenant prod blockers), DEMO POLISH (6 scenariuszy), DX/HARDENING, „po kluczach klienta".

### Fixed
- `prezentacja.md §28` — tabela 6 scenariuszy demo z realnym statusem: A ⚠️, B ⚠️, C ❌, D ⚠️, E ❌, F ⚠️. Wcześniej wszystkie prezentowane jako ✅.

### Known issues (discovered in audit)
- **Security:** `/api/v1/*` + `/buying/*` endpointy bez `Depends(get_current_user)` — publiczne.
- **Multi-tenant:** `db_insert_suppliers` i list queries filtrują po `domain` (business vertical) zamiast `tenant_id` — cross-tenant data leakage risk.
- **Contract audit (correction):** re-weryfikacja: `contract_audit` działa dla CRUD na kontraktach (`upsert_contract()` / `delete_contract()` w contract_engine.py wołają `_audit()` → `db_append_contract_audit()`). Initial audit claim o „dead code" był nietrafiony. Genuiny gap: brak linku order→contract audit (gdy order approval dotyczy supplier'a z active contract, nie jest to rejestrowane w contract_audit). Low priority.
- **Contract store:** `_CONTRACTS = {}` in-memory cache zamiast czytać z tabeli `contracts`.
- **Copilot action cards:** `dispatchActionCard()` w `copilot.js:120` nie implementuje wszystkich `action_type` (alert kontraktu CTA nie działa).
- **OSINT:** endpoint `/supplier/{id}/osint` działa, ale `suppViesLookup()` (admin.html:1511) nie parsuje response; brak OSINT na Step 2.
- **Step 3→4 handoff:** `createOrderFromOptimizer()` nie auto-populuje koszyka wynikiem solvera — user musi manual checkout.
- **Process mining filter:** `loadMonitoringForSource()` empty scaffold; `?supplier=` na `/buying/orders` ignorowany.
- **Auctions:** `_auctions = {}` in-memory (restart = utrata); items w UI jako JSON textarea.
- **Error responses:** brak `request_id` w JSON body — utrudnia debugowanie.

## v5.1.37 — 2026-04-16

### Polish & hardening
- **Mobile layouts** (<768px): Step 2 scorecard, taxonomy subdomeny, shadow prices, What-If chain — cleanly stackują się w dwa rzędy.
- **Shared utils** (`app/static/js/ui.js`): `plnShort()`, `loadingHtml()`, `emptyHtml()` — jeden standard across widgets.
- **A11y**: action cards dostają `tabindex`, `role="button"`, `aria-label`, keyboard support (Enter/Space).

## v5.1.36 — Supplier Scorecard (MVP-5)

- **Kompozytowy scoring 0-100** per dostawca z 5 wymiarów (ESG, compliance, contract status, concentration, single-source risk).
- `GET /api/v1/buying/suppliers/scorecard?category=X` — ranked list z rekomendacjami.
- Widget na Step 2 „Policz scoring" → Top 5 + Bottom 3.
- Silnik: `app/supplier_scorecard.py`.

## v5.1.35 — B4 Subdomain optimization

- Solver per subdomena w domenie z agregacją domain-level.
- `GET /api/v1/dashboard/subdomain-aggregate/demo?domain=parts`.
- Widget „Optymalizuj ▶" w taxonomy panelu na dashboardzie.

## v5.1.34 — Backlog cleanup

- Supplier concentration rule używa allokacji solver jako fallback (gdy brak `purchase_orders[]`).
- Contract audit log — nowa tabela `contract_audit` z historią create/update/delete + diff.
- `GET /api/v1/buying/contracts/{id}/audit`.

## v5.1.33 — B3 Scenario chaining (What-If v2)

- Łańcuchowe scenariusze — każdy krok to delta na wcześniejszym stanie.
- Auto-normalizacja wag do sum=1.0.
- `POST /api/v1/whatif/chain` + `GET /whatif/chain/demo`.
- Widget w Step 3 „↔ Chain What-If" renderuje timeline z delta arrow.

## v5.1.32 — B2 Monte Carlo na Pareto froncie

- Dla każdego punktu λ solver + mini-MC (25/50/100 iter) → P5/mean/P95 kosztu.
- Confidence band wokół deterministycznej krzywej.
- `POST /api/v1/dashboard/pareto-xy-mc`.
- Widget w Step 3 „⚡ Odpal MC" — Chart.js fan chart.

## v5.1.31 — Phase A2 (27 subdomen) + A1 (BI widget)

- Widget „Taksonomia zakupow" na dashboardzie: 10 domen + 27 subdomen z licznikami.
- Summary w `/domains/extended` (direct/indirect breakdown).
- Slajd 3 z prezentacji ProcurementSafety domknięty.

## v5.1.30 — B1 Shadow prices

- Backend wyciąga duale z HiGHS (`result.ineqlin.marginals`).
- Nowa karta na Step 3 „Shadow prices — co kosztuje każde ograniczenie".
- Binding constraints z kolorowymi chipami kind (esg/payment/capacity/...).

## v5.1.29 — Simulated BI + WMS + ERP + CRM + Finance

- `app/bi_mock.py` — 5 adapterów z deterministic seed.
- `BIConnector` interface do podmiany na realne API.
- Nowa reguła `_rule_yoy_anomaly` w silniku rekomendacji.
- 10 endpointów `/bi/*`.

## v5.1.28 — Contracts → Turso

- Tabela `contracts` z CRUD.
- `POST /buying/contracts` + `DELETE /buying/contracts/{id}`.
- `list_contracts()` i `get_contract()` transparentnie czytają z DB (fallback in-memory).

## v5.1.27 — PDF OCR fallback

- Tesseract + poppler w Dockerfile (`pol+eng`).
- `extract_text_from_pdf` odpala OCR gdy warstwa tekstu < 50 chars.
- Config flag `FLOW_PDF_OCR_ENABLED=false` do dev.

## v5.1.24 — MVP-2b Document upload

- `app/document_parser.py` — PDF/DOCX/EML/TXT.
- `POST /copilot/document/extract-file` (multipart, max 5 MB).
- UI drop-zone w panel asystenta.

## v5.1.23 — MVP-2a Paste email/text

- Claude Haiku ekstraktuje pozycje z wklejonego tekstu.
- `POST /copilot/document/extract`.
- Review list z catalog matching + „Dodaj wszystkie do koszyka".

## v5.1.22 — MVP-1 AI Assistant jako główny UI

- Full-panel copilot na dashboardzie Step 0 (45% szerokości).
- Proactive action cards z `recommendation_engine`.
- `GET /api/v1/copilot/recommendations`.
- Auto-toggle mini/full między krokami.

## v5.1.21 — Copilot cart automation

- Claude rozumie „dodaj 3 klocki Bosch do koszyka" → mutuje `state._s1SelectedItems`.
- `s1AddToCartFromCopilot()` shared mutator.
- Regex intent + LLM tool-use fallback.

## v5.1.20 — Copilot model tiering

- Haiku 4.5 dla rutynowego Q&A, Sonnet 4.6 dla reasoning (keyword/length heuristic).
- Gemini 2.0 Flash jako final fallback.

## v5.1.0–5.1.19 — Phase 3 refactor + Direct/Indirect

- Inline CSS/JS → moduły ES (`app/static/css/*.css`, `app/static/js/*.js`).
- Direct/Indirect toggle na Step 1.
- Dashboard hero + quick-action tiles.
- Railway Dockerfile + `start.sh` (wrapper dla `$PORT` expansion).

## v5.0 i wcześniej

Guided 5-step wizard, 165 endpointów, Monte Carlo, What-If, Process Mining, RFQ, Risk Engine. Zob. `git log`.
