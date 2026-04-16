# Flow Procurement Platform — Dokumentacja prezentacyjna

**Wersja:** 5.1.37 (latest release) / core v5.1.65
**Data:** 2026-04-16
**Status:** Production
**Live:** https://flow-procurement.up.railway.app/ui
**API Docs:** https://flow-procurement.up.railway.app/docs

> Ten dokument jest single-source-of-truth do prezentacji dla klienta.
> Wcześniejsze wersje dokumentacji znajdują się w `docs/archive/`.
> Szczegółowa dokumentacja techniczna: `PROJECT.md` | Historia zmian: `CHANGELOG.md`.

---

## 1. Czym jest Flow Procurement

**AI-first platforma zakupowa klasy enterprise** — zamiast klasycznego formularza, asystent AI prowadzi kupca od zapotrzebowania przez optymalizację do zamówienia.

### Propozycja wartości

| Problem | Rozwiązanie | Efekt |
|---------|-------------|-------|
| Długi czas decyzji zakupowej | AI Copilot + 5-krokowy wizard | Zamówienie w < 5 min |
| Subiektywny wybór dostawcy | Solver LP/MIP z 12 constraintami (ESG, compliance, koszt, czas) | Audytowalne decyzje |
| Ryzyko koncentracji | Monte Carlo + Supplier Scorecard + alerty proaktywne | Early warning na 5 rodzajów ryzyka |
| Ręczne przetwarzanie RFQ/e-maili | Document Ingestion (PDF/DOCX/EML + OCR) | Auto-ekstrakcja pozycji do koszyka |
| Rozproszone dane (ERP/BI/WMS/CRM/Finance) | 5 symulowanych konektorów + jednolity interface | Plug-and-play na dane klienta |

---

## 2. Architektura — 4 warstwy

```
┌────────────────────────────────────────────────────────────────┐
│  FRONTEND (3 portale SPA, 12 ES modułów)                       │
│  Dashboard /ui  │  Admin /admin-ui  │  Portal dostawcy        │
│  Step 0: AI Assistant (~45% ekranu)                            │
│  Step 1–5: Zapotrzebowanie → Dostawcy → Optymalizacja          │
│           → Zamówienie → Monitoring                             │
└──────────────────────────┬─────────────────────────────────────┘
                           │ REST JSON + WebSocket
┌──────────────────────────▼─────────────────────────────────────┐
│  BACKEND — FastAPI (193 endpointy, 24 routery)                 │
│  Middleware: CORS · Security · Observability · Tenant · RateLim│
└──┬──────────┬──────────┬──────────┬──────────┬────────────────┘
   │          │          │          │          │
┌──▼────┐ ┌──▼────┐ ┌──▼────┐ ┌──▼────┐ ┌──▼─────────────┐
│Solver │ │AI     │ │Turso  │ │BI Mock│ │Document Parser │
│HiGHS  │ │Haiku  │ │libSQL │ │ERP·BI │ │pypdf · docx    │
│LP/MIP │ │Sonnet │ │14 tab.│ │CRM·FIN│ │Tesseract OCR   │
│Pareto │ │Gemini │ │eu-west│ │WMS    │ │pol+eng         │
│+MC+   │ │(routin│ │       │ │5 adap.│ │                │
│Shadow │ │g per  │ │       │ │       │ │                │
│prices │ │query) │ │       │ │       │ │                │
└───────┘ └───────┘ └───────┘ └───────┘ └────────────────┘
```

### Stack

| Warstwa | Technologia |
|---------|-------------|
| Backend | FastAPI + Pydantic v2 (~24.5K LOC Python) |
| Solver | HiGHS (LP ciągły) + PuLP/HiGHS (MIP binarny) |
| AI | Claude Haiku 4.5 / Sonnet 4.6 / Gemini 2.0 Flash (smart routing) |
| Dokumenty | pypdf + python-docx + Tesseract OCR (pol+eng) |
| Process Mining | pm4py (DFG, conformance, anomalies) |
| DB | Turso libSQL (aws-eu-west-1, 14 tabel) |
| Frontend | Vanilla JS ES Modules + Chart.js + Cytoscape.js |
| Hosting | Railway.app (Dockerfile, europe-west4) |
| CI/CD | GitHub Actions — lint + test + Docker + E2E Playwright + k6 |

---

## 3. AI Copilot — serce platformy

Asystent pracuje **pełnopanelowo** (Step 0 dashboardu) i rozumie zarówno komendy zakupowe, jak i pliki.

### Co potrafi

| Scenariusz | Przykładowa komenda | Mechanizm |
|------------|---------------------|-----------|
| Dodawanie do koszyka | „dodaj 3 klocki Bosch do koszyka" | Regex NLP → catalog fuzzy match → mutacja stanu |
| Nawigacja | „przejdź do optymalizacji" | `navigate` action |
| Optymalizacja | „optymalizuj filtry olejowe", „najszybsza dostawa" | `set_weights` + solver run |
| Filtrowanie | „tylko ESG > 0.80", „tylko Polska" | `filter_esg` / `filter_region` |
| Aukcje | „utwórz aukcję na klocki" | `create_auction` |
| Dokumenty | Upload PDF / wklej e-mail | Haiku JSON extraction → catalog match |

### Smart routing modeli

```
Wiadomość
  ├─ Regex match (32 wzorce) ─────── 0 ms, 0 PLN
  └─ LLM fallback
      ├─ Proste (< 300 zn.)      → Haiku 4.5 (~0.002 PLN/call)
      ├─ Złożone („dlaczego") → Sonnet 4.6 (~0.03 PLN/call)
      └─ Oba fail                  → Gemini 2.0 Flash
```

### Proaktywne karty akcji (5 reguł)

| Reguła | Trigger | Przykład |
|--------|---------|----------|
| R1 Contract expiry | kontrakt kończy się < 90 dni | „Umowa z Bosch wygasa za 14 dni" |
| R2 Supplier concentration | udział > 70% | „Inter Cars ma 100% spendu" |
| R3 Direct/Indirect drift | spend Indirect ≈ 0 | „Spend Indirect prawie zero" |
| R4 YoY anomaly | ±20% YoY | „oils: spend ▼ 72% YoY" |
| R5 Single-source risk | 1 dostawca na produkt | „2 produkty OE bez alternatywy" |

---

## 4. Silnik optymalizacji

### Funkcja celu

```
min  λ · Σᵢⱼ (w_cost·cᵢⱼ + w_time·tᵢⱼ) · xᵢⱼ · Dⱼ
   + (1-λ) · Σᵢⱼ (w_compliance·(1-compᵢ) + w_esg·(1-esgᵢ)) · xᵢⱼ · Dⱼ
```

### Constrainty (12 typów)

| ID | Constraint | Opis |
|----|-----------|------|
| C1 | Demand coverage | Σ xᵢⱼ = 1 per produkt |
| C2 | Capacity | Σ xᵢⱼ·Dⱼ ≤ Capᵢ |
| C3 | Min order qty | Block gdy Dⱼ < MOQᵢ |
| C4 | Regional block | Region dostawcy |
| C5 | Diversification | Max 60% per dostawca |
| C10 | Min suppliers | ≥ 2 aktywnych |
| C11 | Geographic diversity | Min regiony |
| C12 | ESG floor | avg ESG ≥ 0.70 |
| C13 | Payment terms | avg ≤ 60 dni |
| C14 | Contract lock-in | gwarantowana min alokacja |
| C15a | Preferred bonus | –5% koszt dla preferred |
| C15b | Min preferred share | Σ preferred ≥ X% |

### Zaawansowane analizy (Phase B — wszystkie zrealizowane)

| Feature | Opis |
|---------|------|
| **B1 Shadow Prices** | Duale LP z HiGHS — „który constraint kosztuje Cię ile". UI z chipami binding constraints. |
| **B2 Monte Carlo na Pareto** | Dla każdego λ mini-MC (25/50/100 iter) → P5/mean/P95 → confidence fan na wykresie. |
| **B3 Scenario chaining** | Łańcuchowe What-If — każdy krok to delta na poprzednim stanie. |
| **B4 Subdomain optimization** | Solver per subdomena + agregacja domain-level. |

---

## 5. 10 domen × 27 subdomen

| # | Domena | Typ | Subdomeny | Wagi (C/T/SLA/ESG) |
|---|--------|-----|-----------|---------------------|
| 1 | parts | DIRECT | brake_systems, filters, suspension | 0.40/0.30/0.15/0.15 |
| 2 | oe_components | DIRECT | engine, electrical, transmission | 0.35/0.25/0.25/0.15 |
| 3 | oils | DIRECT | engine_oils, transmission_fluids | 0.45/0.25/0.15/0.15 |
| 4 | batteries | DIRECT | starter, agm_efb | 0.35/0.30/0.15/0.20 |
| 5 | tires | DIRECT | summer, winter, all_season | 0.40/0.25/0.15/0.20 |
| 6 | bodywork | DIRECT | panels, lighting, glass | 0.35/0.30/0.20/0.15 |
| 7 | it_services | INDIRECT | dev, cloud, data_analytics | 0.35/0.25/0.20/0.20 |
| 8 | logistics | INDIRECT | domestic, international, last_mile | 0.30/0.40/0.15/0.15 |
| 9 | packaging | INDIRECT | cardboard, plastics | 0.45/0.20/0.10/0.25 |
| 10 | facility_mgmt | INDIRECT | maintenance, safety, cleaning | 0.40/0.25/0.20/0.15 |

**Łącznie:** 6 Direct + 4 Indirect = **10 domen**, 16 + 11 = **27 subdomen**.

---

## 6. Moduły biznesowe (MVP-1 → MVP-5)

| MVP | Moduł | Stan | Endpoint kluczowy |
|-----|-------|------|-------------------|
| MVP-1 | AI Assistant jako główny UI + proaktywne karty | ✅ | `GET /copilot/recommendations` |
| MVP-2 | Document ingestion (paste / PDF / DOCX / EML + OCR) | ✅ | `POST /copilot/document/extract-file` |
| MVP-3 | Spend analytics (Direct/Indirect, top-N) | ✅ | `GET /buying/spend-analytics` |
| MVP-4 | Contracts + RecommendationEngine (5 reguł) | ✅ | `GET /buying/contracts`, audit log |
| MVP-5 | Supplier Scorecard (composite 0-100 z 5 wymiarów) | ✅ | `GET /buying/suppliers/scorecard` |

### Supplier Scorecard (MVP-5) — detale

Kompozytowy scoring 0-100 (5 wymiarów, equal weight 20%):

| Wymiar | Źródło | Zakres |
|--------|--------|--------|
| ESG | SupplierInput.esg_score | 0 → 0, 1.0 → 100 |
| Compliance | SupplierInput.compliance_score | 0 → 0, 1.0 → 100 |
| Contract | contract_engine.expiring_within() | active long=90, 30d expiry=40, brak=55 |
| Concentration | spend_map(orders) per supplier | >85%=20, >70%=45, <50%=90 |
| Single-source | katalog z 1 dostawcą | 100%=20 |

UI: widget „Top 5 + Bottom 3" na Step 2, chipy per wymiar.

---

## 7. BI / ERP / WMS / CRM / Finance — 5 konektorów

Interface `BIConnector` z 5 symulowanymi adapterami (deterministic seed `sha256(category × month)`). Gotowe do podmiany na real HTTP client po dostarczeniu kluczy przez klienta.

| System | Adapter | Dane |
|--------|---------|------|
| SAP ERP | `ErpConnector` | Invoices, POs, budget positions per year |
| Enterprise BI | `BiWarehouseConnector` | 24 mies. spend + YoY anomaly detection |
| Salesforce CRM | `CrmConnector` | Weekly demand forecast per category |
| Finance Ledger | `FinanceConnector` | Cash, AP/AR, DPO/DSO, overdue invoices |
| SAP EWM | `WmsConnector` | Stock per warehouse + reorder point |

Widget: 5 chipów z kolorem statusu (mock=żółty, real=zielony, degraded=czerwony).

---

## 8. 5-krokowy wizard (UX)

| Krok | Ekran | Kluczowe funkcje |
|------|-------|------------------|
| **0. AI Assistant** | pełnopanelowy (45% ekranu) | Czat + proaktywne karty + document upload |
| **1. Zapotrzebowanie** | Direct/Indirect toggle | Katalog / Ad hoc / CIF V3.0 upload (80+ reguł UNSPSC) |
| **2. Dostawcy** | Karty + scorecard | VIES weryfikacja, Top 5 / Bottom 3 scorecardu, filtry |
| **3. Optymalizacja** | Wykres Pareto + MC + shadow prices | Solver LP/MIP, confidence fan, binding constraints, chain What-If |
| **4. Zamówienie** | Koszyk + lifecycle PO | Approval workflow (>15 000 PLN → manager), aukcje elektroniczne |
| **5. Monitoring** | Process Mining + alerty | DFG Cytoscape, risk heatmap, MC, scenario chaining |

### Wizualizacje (13 typów)

Pareto Front · XY Scatter · Supplier Radar · Allocation Bar · Sankey · Cost Donut · DFG Graph · Scenario Comparison · Cross-domain Trend · Risk Heatmap · MC Histogram · Supplier Stability · Negotiation Table

---

## 9. Bezpieczeństwo & Observability

| Feature | Implementacja |
|---------|---------------|
| Auth | JWT (access + refresh), role-based (super_admin/admin/buyer/supplier) |
| Multi-tenant | ContextVar per request, X-Tenant-ID header → JWT claim → default `demo` |
| Rate limiting | Per-IP/min na /api/v1/*, Redis-ready backend |
| Request tracing | X-Request-ID per request, structured JSON logs |
| Metrics | `GET /metrics` — p50/p95/p99 per route + error rate |
| Healthcheck | `/health` (liveness) + `/health/ready` (DB, LLM, BI, solver, OCR) |
| Error tracking | Sentry opt-in (FastAPI + Starlette + PII scrubbing) |
| Secrets | Railway Variables + rotation cadence w `ops/SECRETS.md` |

---

## 10. CI/CD

```
Push to main ──┬── ci.yml ──────────────────────────────────┐
               │  ├── ruff lint                             │
               │  ├── pytest (3.11 + 3.12) → Codecov        │
               │  ├── Docker build + smoke (/health)        │
               │  ├── Playwright E2E (login + copilot cart)  │
               │  └── k6 load test (PR-only, SLO p95<1.5s) │
               └── post-deploy.yml ─────────────────────────┤
                  ├── Wait for Railway version (~5 min)     │
                  └── Smoke 10 endpoints on prod            │
Cron 06:00 UTC ── nightly-smoke.yml ───────────────────────┘
```

**Pokrycie testami:** 157 unit/integration + 3 Playwright E2E = **160 testów**, ~56% line coverage.

---

## 11. Dostępy demo

**Base URL:** https://flow-procurement.up.railway.app

| Rola | Login | Hasło | Panel |
|------|-------|-------|-------|
| Super Admin | `superadmin` | `super123!` | `/superadmin-ui` — zarządzanie tenantami |
| Admin | `admin` | `admin123` | `/admin-ui` — backoffice, katalog |
| Buyer | `buyer` | `buyer123` | `/ui` — dashboard, zakupy |
| Supplier (TRW) | `trw` | `trw123` | `/portal-ui` |
| Supplier (Brembo) | `brembo` | `brembo123` | `/portal-ui` |
| Supplier (Bosch) | `bosch` | `bosch123` | `/portal-ui` |
| Supplier (Kraft) | `kraft` | `kraft123` | `/portal-ui` |

---

## 12. Scenariusze demo do prezentacji

### Scenariusz A — „Od e-maila do zamówienia w 90 sekund"
1. Login jako `buyer` → `/ui` → Step 0 (AI Assistant)
2. Wklej e-mail z zapotrzebowaniem (lub upload PDF)
3. Copilot ekstraktuje pozycje → match w katalogu → dodaje do koszyka
4. „optymalizuj" → Step 3: Pareto + MC + shadow prices
5. „złóż zamówienie" → Step 4: PO wygenerowane

### Scenariusz B — „Decyzja z uzasadnieniem (auditability)"
1. Step 3 → włącz MIP mode (binary)
2. Pokaż Shadow prices — „C12 (ESG floor) kosztuje Cię 12 400 PLN"
3. Pokaż chain What-If — „co jeśli podniesiemy ESG floor z 0.70 do 0.80"
4. Eksport audit logu zamówienia

### Scenariusz C — „Monitoring ryzyka"
1. Step 2 → Scorecard → Bottom 3 z uzasadnieniem per wymiar
2. Step 5 → Risk Heatmap → pokaż single-source risk
3. Dashboard → proaktywne karty (R2 concentration, R4 YoY anomaly)

### Scenariusz D — „Portal dostawcy"
1. Login jako `trw` → `/portal-ui`
2. Lista zamówień do potwierdzenia
3. Zarządzanie certyfikatami (ESG, ISO, VAT)

---

## 13. Metryki produktu (aktualne)

| Metryka | Wartość |
|---------|---------|
| Endpointy API | **193** (24 routery) |
| Tabele DB | **14** w Turso libSQL |
| Moduły Python | **55** (~24.5K LOC) |
| Testy | **157** unit/integration + **3** E2E = **160** |
| Coverage | ~56% line |
| Domeny / subdomeny | **10 / 27** |
| Constrainty solvera | **12** (C1-C5, C10-C15b) |
| Wizualizacje | **13** typów |
| AI modele | **3** (Haiku 4.5 / Sonnet 4.6 / Gemini 2.0 Flash) |
| Konektory BI/ERP | **5** mock adapterów |
| Dostępne wersje | v3.1 → v5.1.37 (ostatnia) |

---

## 14. Roadmap

### ✅ Zrealizowane (Phase A + B + MVP 1-5)

A1 BI connectors · A2 27 subdomen · A3 Hard constrainty · B1 Shadow prices · B2 Monte Carlo na Pareto · B3 Scenario chaining · B4 Subdomain optimization · MVP-1 AI Assistant · MVP-2 Document ingestion · MVP-3 Spend analytics · MVP-4 Contracts + Recommendations · MVP-5 Supplier Scorecard

### 🟡 Do wdrożenia po dostarczeniu danych klienta

| Item | Effort | Wymaga |
|------|--------|--------|
| Realne BI/ERP connectors | 2-4 dni | klucze API od klienta (SAP, CRM) |
| Multi-replica Redis | 0.5 dnia | Redis instance |
| Staging environment | 0.5 dnia | Railway staging branch |
| Subdomain weights | 1 dzień | walidacja biznesowa wag |
| UNSPSC LLM fallback | 0.5 dnia | — |

---

## 15. Gdzie szukać szczegółów

| Temat | Plik |
|-------|------|
| Pełna dokumentacja techniczna | `PROJECT.md` |
| Historia zmian per release | `CHANGELOG.md` |
| Bezpieczeństwo + incident response | `SECURITY.md` |
| Jak kontrybuować | `CONTRIBUTING.md` |
| On-call runbook | `ops/ONCALL.md` |
| Deploy procedure | `ops/DEPLOY.md` |
| Staging setup | `ops/STAGING.md` |
| Secrets rotation | `ops/SECRETS.md` |
| Alerting rules | `ops/ALERTING.md` |
| **Archiwum starych wersji** | **`docs/archive/`** |

---

*Dokument wygenerowany 2026-04-16 dla prezentacji klienckiej. W razie zmian w platformie aktualizuj razem z `CHANGELOG.md` i bumpnij wersję w nagłówku.*
