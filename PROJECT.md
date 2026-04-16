# Flow Procurement Platform v5.1.65

**AI-first platforma optymalizacji portfela zamówień** — asystent zakupowy prowadzi kupca od zapotrzebowania przez optymalizację do zamówienia. Wielokryterialna optymalizacja LP/MIP (HiGHS), symulowane konektory BI/ERP/WMS, przetwarzanie dokumentów PDF/DOCX/EML z OCR, supplier scorecard, spend analytics i end-to-end 5-krokowy wizard.

> **Changelog:** `CHANGELOG.md` | **Contributing:** `CONTRIBUTING.md` | **Security:** `SECURITY.md` | **On-call:** `ops/ONCALL.md` | **Deploy:** `ops/DEPLOY.md`

**Live:** https://flow-procurement.up.railway.app/ui
**Admin:** https://flow-procurement.up.railway.app/admin-ui
**Portal dostawcy:** https://flow-procurement.up.railway.app/portal-ui
**API Docs:** https://flow-procurement.up.railway.app/docs
**Repo:** github.com/pawelmamcarz/flow-procurement

---

## Architektura v5.1

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (3 portale SPA)                          │
│  index.html (AI dashboard)  │  admin.html  │  portal.html  │ requester  │
│  ┌─────────────────────────────────────────┐                             │
│  │  Step 0: AI Assistant (pełnopanelowy)   │  12 ES modules (.js)       │
│  │  Step 1: Zapotrzebowanie (Direct/Ind.)  │  4 pliki CSS               │
│  │  Step 2: Dostawcy + Scorecard           │  Chart.js + Cytoscape.js   │
│  │  Step 3: Optymalizacja + MC + Shadow    │                             │
│  │  Step 4: Zamówienie + Aukcje            │                             │
│  │  Step 5: Monitoring + Process Mining    │                             │
│  └─────────────────────────────────────────┘                             │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │ REST JSON + WebSocket
┌──────────────────────────▼───────────────────────────────────────────────┐
│                    FastAPI REST API (193 endpointów)                      │
│                        prefix: /api/v1/                                  │
│                                                                          │
│  ┌─────────┬──────────┬──────────┬──────────┬──────────┬──────────┐     │
│  │ routes  │ buying   │ copilot  │  bi      │ supplier │ whatif   │     │
│  │ (40)    │ (30)     │  (5)     │  (10)    │ (15)     │ (8)      │     │
│  ├─────────┼──────────┼──────────┼──────────┼──────────┼──────────┤     │
│  │ risk    │ integr.  │ db/CRUD  │ portal   │ admin    │ auth     │     │
│  │ (9)     │ (6)      │ (15)     │ (13)     │ (15)     │ (8)      │     │
│  ├─────────┼──────────┼──────────┼──────────┼──────────┼──────────┤     │
│  │ auction │ predict  │ project  │ digging  │ ewm/wms  │ superadm │     │
│  │ (10)    │ (6)      │ (4)      │ (18)     │ (7)      │ (8)      │     │
│  └─────────┴──────────┴──────────┴──────────┴──────────┴──────────┘     │
│                                                                          │
│  ┌─── Middleware ──────────────────────────────────────────────────┐     │
│  │ CORS │ SecurityHeaders │ ObservabilityMW │ TenantMW │ RateLimit│     │
│  └─────────────────────────────────────────────────────────────────┘     │
└──────┬────────────┬──────────────┬────────────────┬──────────────────────┘
       │            │              │                │
┌──────▼───┐  ┌────▼─────┐  ┌────▼──────────┐  ┌──▼──────────────────┐
│ Optimizer│  │ AI Engine│  │  Turso DB     │  │  BI Mock Layer      │
│ HiGHS LP │  │ Haiku 4.5│  │  (libsql)     │  │  ERP·BI·CRM·FIN·WMS│
│ PuLP MIP │  │ Sonnet4.6│  │  14 tables    │  │  BIConnector iface  │
│ Pareto+MC│  │ Gemini FB│  │  aws-eu-west  │  │  5 mock adapters    │
└──────────┘  │ DocParser│  └───────────────┘  └─────────────────────┘
              │ OCR/PDF  │
              └──────────┘
```

**Cztery warstwy:**
1. **Data Layer** — 10 domen × 27 subdomen, Turso DB (14 tabel), upload CSV/XLSX/CIF/PDF/DOCX/EML
2. **AI Layer** — Claude Haiku 4.5 (routine) / Sonnet 4.6 (reasoning) / Gemini 2.0 Flash (fallback), NLP intent matching, dokument extraction, catalog matching
3. **Optimization Layer** — HiGHS LP (continuous) + PuLP MIP (binary), Monte Carlo, Pareto front, shadow prices, scenario chaining, subdomain aggregation
4. **Decision Layer** — REST API (193 endp.) + 3 portale SPA + AI Assistant jako główny interfejs

---

## Stack technologiczny

| Komponent | Technologia | Uwagi |
|-----------|-------------|-------|
| Backend | **FastAPI** + Pydantic v2 | 55 modułów Python, ~24.5K LOC |
| Solver LP | **HiGHS** (scipy.optimize.linprog) | C1-C5, C11-C15b constrainty |
| Solver MIP | **PuLP** + HiGHS backend | Binary allocation per product |
| AI Copilot | **Claude Haiku 4.5** / **Sonnet 4.6** / **Gemini 2.0 Flash** | Smart routing per query complexity |
| Document Parser | **pypdf** + **python-docx** + **Tesseract OCR** | PDF/DOCX/EML/TXT, pol+eng OCR |
| Process Mining | **pm4py** (DFG, conformance, anomalies) | |
| Baza danych | **Turso** (libSQL) — aws-eu-west-1 | 14 tabel, fallback: local SQLite |
| Frontend | Vanilla JS (ES modules) + **Chart.js** + **Cytoscape.js** | 12 modułów, 4 CSS files |
| Hosting | **Railway.app** | Dockerfile, 2 workers, europe-west4 |
| CI/CD | **GitHub Actions** | lint + test (3.11/3.12) + Docker smoke + E2E Playwright + k6 gate |
| Error tracking | **Sentry** (opt-in via `FLOW_SENTRY_DSN`) | FastAPI + Starlette integration |
| Monitoring | In-process `/metrics` (p50/p95/p99) + JSON logs | X-Request-ID per request |

---

## AI Copilot — główny interfejs platformy

Asystent zakupowy jest **pełnopanelowy na dashboardzie** (Step 0, ~45% ekranu) i prowadzi kupca przez cały proces.

### Co potrafi

| Kategoria | Przykładowe komendy | Jak działa |
|-----------|---------------------|------------|
| **Dodawanie do koszyka** | „dodaj 3 klocki hamulcowe Bosch do koszyka" | Regex NLP → `search_catalog()` fuzzy match → `add_to_cart` action → JS mutuje `state._s1SelectedItems` |
| **Nawigacja** | „przejdź do optymalizacji", „pokaż dostawców" | `navigate {step: N}` action → `goStep(N)` |
| **Optymalizacja** | „optymalizuj filtry olejowe", „najszybsza dostawa" | `optimize` / `set_weights` actions → solver run |
| **Filtrowanie** | „tylko dostawcy z ESG > 0.80", „tylko polska" | `filter_esg` / `filter_region` actions |
| **Analizy** | „wyjaśnij front Pareto", „pokaż Monte Carlo" | Static explanation templates + navigate |
| **Dokumenty** | Wklej email / upload PDF z zamówieniem | LLM extraction (Haiku) → catalog match → add_to_cart |
| **Aukcje** | „utwórz aukcję na klocki" | `create_auction` action |

### Routing modeli

```
Wiadomość użytkownika
    │
    ├─ Regex intent match ─────── szybka ścieżka (0ms, 0 PLN)
    │   32 wzorców: add_to_cart, navigate, optimize, filter, explain...
    │
    └─ LLM fallback ───────────── gdy regex miss
        │
        ├─ Proste pytanie ──── Claude Haiku 4.5 (512 tok, ~0.002 PLN)
        │   Heurystyka: msg < 300 znaków, brak keywords reasoning
        │
        └─ Złożone pytanie ── Claude Sonnet 4.6 (1024 tok, ~0.03 PLN)
            Heurystyka: „dlaczego", „porównaj", „rekomenduj", msg > 300 zn.
            │
            └─ Oba fail ──────── Gemini 2.0 Flash (final fallback)
```

### Proaktywne karty akcji (Step 0)

Dashboard po prawej stronie panelu asystenta renderuje karty z `RecommendationEngine` (5 reguł):

| Reguła | Źródło danych | Przykład karty |
|--------|---------------|----------------|
| R1: Contract expiry | `contract_engine.expiring_within(90)` | 📅 „Kontrakt z Bosch wygasa za 14 dni" |
| R2: Supplier concentration | `buying_engine._load_orders()` + alloc fallback | ⚠️ „Inter Cars ma 100% spendu" |
| R3: Direct/Indirect drift | `buying_engine.spend_analytics()` | 📊 „Spend Indirect prawie zero" |
| R4: YoY anomaly | `bi_mock.yoy_anomalies(20%)` | 📉 „oils: spend ▼ 72% YoY" |
| R5: Single-source risk | `buying_engine.get_catalog()` | ⚠️ „2 OE produkty bez alternatywy" |

### Document Ingestion

```
Email / PDF / DOCX / tekst
    │
    ├─ Paste tekst ──► POST /copilot/document/extract
    │                    │
    └─ Upload plik ──► POST /copilot/document/extract-file
                         │
                    document_parser.extract_text()
                    ├─ PDF: pypdf text layer → jeśli < 50 zn. → Tesseract OCR (pol+eng)
                    ├─ DOCX: python-docx paragraphs + table cells
                    ├─ EML: stdlib email parser (From/Subject + body)
                    └─ TXT/CSV: UTF-8 / CP1250 / latin-1 fallback chain
                         │
                    Claude Haiku (JSON extraction prompt)
                    → {items: [{name, qty, unit, price, note}]}
                         │
                    buying_engine.search_catalog(name) per item
                    → match → CopilotAction(add_to_cart)
                    → no match → "ad-hoc" w suggestion list
```

---

## 10 domen × 27 subdomen

| # | Domena | Typ | Subdomeny | Wagi (C/T/SLA/ESG) |
|---|--------|-----|-----------|---------------------|
| 1 | parts | DIRECT | brake_systems, filters, suspension | 0.40/0.30/0.15/0.15 |
| 2 | oe_components | DIRECT | engine_parts, electrical, transmission | 0.35/0.25/0.25/0.15 |
| 3 | oils | DIRECT | engine_oils, transmission_fluids | 0.45/0.25/0.15/0.15 |
| 4 | batteries | DIRECT | starter_batteries, agm_efb | 0.35/0.30/0.15/0.20 |
| 5 | tires | DIRECT | summer, winter, all_season | 0.40/0.25/0.15/0.20 |
| 6 | bodywork | DIRECT | body_panels, lighting, glass | 0.35/0.30/0.20/0.15 |
| 7 | it_services | INDIRECT | development, cloud_infra, data_analytics | 0.35/0.25/0.20/0.20 |
| 8 | logistics | INDIRECT | domestic, international, last_mile | 0.30/0.40/0.15/0.15 |
| 9 | packaging | INDIRECT | cardboard, plastics | 0.45/0.20/0.10/0.25 |
| 10 | facility_mgmt | INDIRECT | maintenance, safety_equipment, cleaning | 0.40/0.25/0.20/0.15 |

Suma: **6 Direct + 4 Indirect = 10 domen**, **16 Direct + 11 Indirect = 27 subdomen**.

---

## Solver — constrainty C1-C15b

| # | Constraint | Typ | LP | MIP | Opis |
|---|-----------|-----|:--:|:---:|------|
| C1 | Demand coverage | equality | ✅ | ✅ | Σ x[i,j] = 1 per product |
| C2 | Capacity | ≤ | ✅ | ✅ | Σ x[i,j]·D_j ≤ Cap_i |
| C3 | Min order | bound | — | ✅ | Block if D_j < MOQ_i |
| C4 | Regional block | bound | ✅ | ✅ | x[i,j] = 0 if supplier doesn't serve region |
| C5 | Diversification | ≤ | ✅ | ✅ | Max 60% volume per supplier |
| C10 | Min suppliers | post-check | ⚠️ | ✅ | ≥ 2 active suppliers |
| C11 | Geographic div. | ≥ ε | ✅ | ✅ | Min regions represented |
| C12 | ESG floor | ≥ | ✅ | ✅ | Weighted avg ESG ≥ 0.70 |
| C13 | Payment terms | ≤ | ✅ | ✅ | Weighted avg ≤ 60 days |
| C14 | Contract lock-in | bound | ✅ | ✅ | Min allocation for contracted suppliers |
| C15a | Preferred bonus | soft | ✅ | ✅ | 5% objective reduction for is_preferred |
| C15b | Min preferred share | ≥ | ✅ | ✅ | Σ_preferred ≥ X% volume |

**Shadow prices (B1):** LP duals z HiGHS dla każdego binding constraint — UI pokazuje „który constraint kosztuje Cię ile w celu".

---

## Supplier Scorecard (MVP-5)

Kompozytowy scoring 0-100 per dostawca z 5 wymiarów (equal weight 20% each):

| Wymiar | Źródło | Scoring |
|--------|--------|---------|
| ESG | SupplierInput.esg_score | 0→0, 1.0→100 |
| Compliance | SupplierInput.compliance_score | 0→0, 1.0→100 |
| Contract | contract_engine.expiring_within() | Active long=90, expiring 30d=40, no contract=55 |
| Concentration | spend_map(orders) per supplier | Share >85%=20, >70%=45, <50%=90 |
| Single-source | catalog products with 1 supplier | 100% single-source=20 |

Endpoint: `GET /buying/suppliers/scorecard?limit=20` → Top 5 + Bottom 3 na UI Step 2 z chipami per wymiar.

---

## BI / ERP / WMS — symulowane konektory

5 adapterów z interface `BIConnector` — deterministic seed (sha256 per category × month), gotowe do podmiany na real HTTP client.

| System | Adapter | Dane |
|--------|---------|------|
| SAP ERP | `ErpConnector` | Invoices, POs, budget positions per year |
| Enterprise BI | `BiWarehouseConnector` | 24 mies. historical spend, YoY anomaly detection |
| Salesforce CRM | `CrmConnector` | Weekly demand forecast per category |
| Finance Ledger | `FinanceConnector` | Cash position, AP/AR, DPO/DSO, overdue invoices |
| SAP EWM | `WmsConnector` | Stock levels per warehouse + reorder point |

Widget na dashboardzie: 5 chipów z kolorem status (mock=żółty, real=zielony, degraded=czerwony).

---

## Spend Analytics

`GET /buying/spend-analytics?period_days=90` → breakdown Direct vs Indirect z top kategoriami.

Dashboard widget „Twój spend": okres (30/90/365/all), big number PLN, stacked bar Direct/Indirect, top-N kategorii z paskami.

---

## Baza danych — Turso (libSQL)

14 tabel w Turso (aws-eu-west-1, ~100ms latency z Railway europe-west4):

| Tabela | Opis |
|--------|------|
| `tenants` | Multi-tenant SaaS (demo + custom) |
| `users` | JWT auth (superadmin/admin/buyer/supplier) |
| `suppliers` | Dostawcy per domena |
| `demand` | Zapotrzebowanie per domena |
| `orders` | Zamówienia z lifecycle |
| `order_events` | Audit log zamówień |
| `contracts` | Kontrakty z dostawcami (CRUD + expiry tracking) |
| `contract_audit` | Kto/kiedy/co zmienił w kontrakcie |
| `optimization_results` | Wyniki solvera |
| `p2p_events` | Event log P2P (process mining) |
| `supplier_profiles` | Profile dostawców z certyfikatami |
| `catalog_items` | Produkty katalogowe |
| `business_rules` | Reguły biznesowe (progi, rabaty) |
| `workflow_steps` | Approval workflow konfiguracja |

**Tenant isolation:** ContextVar per request (X-Tenant-ID header → JWT claim → default "demo"). Wire'd w contracts, spend, scorecard, concentration rule.

---

## Observability & Ops

| Feature | Implementacja |
|---------|---------------|
| **Request tracing** | X-Request-ID per request (middleware), JSON log line per request |
| **Metrics** | `GET /metrics` — p50/p95/p99 latency per route, error count/rate |
| **Healthcheck** | `GET /health` (liveness) + `GET /health/ready` (per-subsystem: DB, LLM, BI, solver, OCR) |
| **Error tracking** | Sentry opt-in (FastAPI + Starlette + logging integration, PII scrubbing) |
| **Rate limiting** | Per-IP per-minute on /api/v1/* (env FLOW_RATE_LIMIT_PER_MINUTE), Redis-ready backend |
| **Secrets management** | Railway Variables + rotation cadence w `ops/SECRETS.md` |

---

## CI/CD Pipeline

```
Push to main ──┬── ci.yml ──────────────────────────────────────────────┐
               │  ├── Lint (ruff 0.6.9)                                │
               │  ├── Test (pytest 3.11 + 3.12, coverage → Codecov)    │
               │  ├── Docker build + smoke (/health 200)               │
               │  ├── E2E (Playwright chromium: login + copilot cart)   │
               │  └── Load test (k6, PR-only, SLO p95<1.5s)           │
               │                                                        │
               └── post-deploy.yml ─────────────────────────────────────┐
                  ├── Wait for Railway version match (~5 min)           │
                  ├── Smoke test (10 endpoints on prod)                 │
                  └── Open GitHub issue on failure                      │
                                                                        │
Cron 06:00 UTC ── nightly-smoke.yml ────────────────────────────────────┘
                  ├── Smoke test (same script, no wait)
                  └── Issue on failure (deduped)
```

**157 unit/integration tests + 3 Playwright E2E tests = 160 total**
**Coverage: ~56% line (baseline)**

---

## Metrics sesji (v5.1.22 → v5.1.65)

| Metric | Wartość |
|--------|--------|
| Commity w tej sesji | ~58 |
| Nowe moduły Python | 10 (bi_mock, bi_routes, contract_engine, recommendation_engine, subdomain_optimizer, document_parser, supplier_scorecard, error_tracking, observability, tenant_context, rate_limit_backend) |
| Endpointy API | 165 → **193** (+17%) |
| Tabele DB | 10 → **14** (+4: contracts, contract_audit + idx) |
| Testy | 74 → **157** unit + **3** E2E = **160** (+116%) |
| CI workflows | 1 → **3** (ci + post-deploy + nightly) |
| Ops docs | 0 → **5** (ONCALL, DEPLOY, STAGING, SECRETS, ALERTING) |
| LOC Python | ~13.6K → **~24.5K** |

---

## Konta demo

| User | Hasło | Rola | Akcje |
|------|-------|------|-------|
| `superadmin` | `super123!` | super_admin | Zarządzanie tenantami, reset userów |
| `admin` | `admin123` | admin | Backoffice, katalog, konfiguracja |
| `buyer` | `buyer123` | buyer | Dashboard, zakupy, checkout |
| `trw` | `trw123` | supplier | Portal dostawcy TRW |
| `brembo` | `brembo123` | supplier | Portal dostawcy Brembo |
| `bosch` | `bosch123` | supplier | Portal dostawcy Bosch |
| `kraft` | `kraft123` | supplier | Portal dostawcy Kraft |

---

## Konfiguracja (env vars)

Prefix: `FLOW_`. Pełna lista z opisami w `.env.example`.

| Grupa | Klucze | Opis |
|-------|--------|------|
| Database | `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Turso libSQL (opcjonalne) |
| AI | `LLM_API_KEY`, `LLM_MODEL`, `LLM_HEAVY_MODEL`, `GEMINI_API_KEY` | Haiku/Sonnet/Gemini |
| Auth | `JWT_SECRET`, `JWT_ACCESS_EXPIRE_MINUTES` | Tokens |
| Solver | `DEFAULT_MAX_VENDOR_SHARE`, `DEFAULT_MIN_ESG_SCORE`, `MONTE_CARLO_ITERATIONS` | Constrainty |
| Docs | `PDF_OCR_ENABLED` | Tesseract on/off |
| Hardening | `RATE_LIMIT_PER_MINUTE`, `CORS_ORIGINS`, `SENTRY_DSN` | Prod |

---

## Uruchomienie lokalne

```bash
cd intercars_optimizer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # uzupełnij FLOW_JWT_SECRET + FLOW_LLM_API_KEY
python3 -m uvicorn app.main:app --reload --port 8000

# Dashboard:  http://localhost:8000/ui
# API Docs:   http://localhost:8000/docs
# Health:     http://localhost:8000/health
# Metrics:    http://localhost:8000/metrics

# Testy
pytest tests/ -v                  # 157 unit/integration
pytest tests/e2e/ -v              # 3 Playwright E2E (wymaga `playwright install chromium`)
```

---

## Roadmap

### Zrealizowane (Phase A+B)

| Faza | Opis | Status |
|------|------|--------|
| A1 | BI connectors (5 mock adapters + BIConnector interface) | ✅ |
| A2 | 27 subdomen (widget + summary + taxonomy) | ✅ |
| A3 | Hard C14/C15b constrainty | ✅ |
| B1 | Shadow prices (LP sensitivity) | ✅ |
| B2 | Monte Carlo na Pareto froncie (confidence fan P5/mean/P95) | ✅ |
| B3 | Scenario chaining (What-If v2 — cumulative deltas) | ✅ |
| B4 | Subdomain-level optimization + domain aggregate | ✅ |
| MVP-1 | AI Assistant jako główny UI + proactive cards | ✅ |
| MVP-2 | Document ingestion (paste + PDF/DOCX/EML + OCR) | ✅ |
| MVP-3 | Spend analytics (Direct/Indirect breakdown) | ✅ |
| MVP-4 | Contracts + RecommendationEngine (5 reguł) | ✅ |
| MVP-5 | Supplier Scorecard (composite 0-100 z 5 wymiarów) | ✅ |

### Do zrobienia

| Item | Opis | Effort |
|------|------|--------|
| Realne BI connectors | Podpięcie SAP/ERP/CRM — wymaga kluczy API od klienta | 2-4 dni po dostarczeniu kluczy |
| Multi-replica Redis | Rate limiter + metrics backend na Redis | 0.5 dnia |
| Staging environment | Oddzielna gałąź `staging` na Railway | 0.5 dnia |
| Subdomain weights | Osobne wagi per subdomena (dziedziczone z domeny) | 1 dzień |
| UNSPSC LLM fallback | Claude klasyfikuje gdy keyword-matching zwraca „Nieklasyfikowane" | 0.5 dnia |
