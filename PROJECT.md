# INTERCARS Order Portfolio Optimizer v3.1.0

**Platforma optymalizacji portfela zamówień dla INTERCARS** — wielokryterialna optymalizacja zakupów z analizą ryzyka, process mining i guided buying.

**Live:** https://web-production-8d81d.up.railway.app/ui
**API Docs:** https://web-production-8d81d.up.railway.app/docs
**Hosting:** Railway.app
**Repo:** github.com/pawelmamcarz/intercars-optimizer

---

## Architektura

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (SPA)                        │
│              app/static/index.html (~149KB)              │
│    5 tabów: Optimizer | Buying | Process | What-If | Risk│
└───────────────────────┬─────────────────────────────────┘
                        │ REST JSON
┌───────────────────────▼─────────────────────────────────┐
│                  FastAPI REST API                         │
│              9 routerów, 102 endpointy                    │
│                   prefix: /api/v1/                        │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│  routes  │ buying   │   mip    │ whatif   │  digging     │
│  (33)    │ (14)     │  (4)     │ (5)      │  (19)        │
├──────────┼──────────┼──────────┼──────────┼──────────────┤
│  risk    │integr.   │   db     │          │              │
│  (6)     │ (6)      │  (15)   │          │              │
└──────┬───┴──────┬───┴─────┬───┴──────────┴──────────────┘
       │          │         │
┌──────▼───┐ ┌───▼────┐ ┌──▼──────────┐
│ Optimizer│ │ Buying │ │  Turso DB   │
│ HiGHS LP │ │ Engine │ │  (libsql)   │
│ PuLP MIP │ │ P2P    │ │  opcjonalna │
└──────────┘ └────────┘ └─────────────┘
```

**Trzy warstwy:**
1. **Data Layer** — dane demo (10 domen), Turso DB, upload CSV/XLSX
2. **Optimization Layer** — HiGHS (LP continuous), PuLP (MIP binary), Monte Carlo
3. **Decision Layer** — REST API + Dashboard SPA

---

## Stack technologiczny

| Komponent | Technologia |
|-----------|-------------|
| Backend | **FastAPI** + Pydantic v2 |
| Solver LP | **HiGHS** (scipy.optimize.linprog) |
| Solver MIP | **PuLP** + HiGHS backend |
| Process Mining | **pm4py** (DFG, conformance, anomalies) |
| Baza danych | **Turso** (libsql) — opcjonalna, HTTP API |
| Frontend | Vanilla JS + **Chart.js** + **Cytoscape.js** |
| Hosting | **Railway.app** ($5/mo) |
| CI/CD | GitHub → Railway auto-deploy |
| Python | 3.11 |

---

## Baza danych — Turso/libsql

Opcjonalna baza danych Turso podłączona przez HTTP API (zero dodatkowych zależności — czysty `urllib`).

**Konfiguracja (env vars):**
```
INTERCARS_TURSO_DATABASE_URL=libsql://your-db.turso.io
INTERCARS_TURSO_AUTH_TOKEN=eyJ...
```

**Tabele:**
- `suppliers` — dostawcy per domena
- `demand` — zapotrzebowanie per domena
- `optimization_results` — wyniki optymalizacji
- `p2p_events` — logi zdarzeń P2P (process mining)

**Endpointy DB** (`/api/v1/db/`):
- CRUD suppliers, demand, results, p2p-events
- Upload CSV/XLSX
- Seed demo data
- Status check

**Fallback:** Gdy brak env vars → `DB_AVAILABLE=False`, apka działa na danych demo (in-memory).

---

## 10 domen zakupowych

| # | Domena | Typ | Wagi (cost/time/compliance/esg) |
|---|--------|-----|---------------------------------|
| 1 | parts | DIRECT | 0.40 / 0.30 / 0.15 / 0.15 |
| 2 | oe_components | DIRECT | 0.35 / 0.25 / 0.25 / 0.15 |
| 3 | oils | DIRECT | 0.45 / 0.25 / 0.15 / 0.15 |
| 4 | batteries | DIRECT | 0.35 / 0.30 / 0.15 / 0.20 |
| 5 | tires | DIRECT | 0.40 / 0.25 / 0.15 / 0.20 |
| 6 | bodywork | DIRECT | 0.35 / 0.30 / 0.20 / 0.15 |
| 7 | it_services | INDIRECT | 0.35 / 0.25 / 0.20 / 0.20 |
| 8 | logistics | INDIRECT | 0.30 / 0.40 / 0.15 / 0.15 |
| 9 | packaging | INDIRECT | 0.45 / 0.20 / 0.10 / 0.25 |
| 10 | facility_mgmt | INDIRECT | 0.40 / 0.25 / 0.20 / 0.15 |

Wagi scentralizowane w `app/data_layer.py:DOMAIN_WEIGHTS` — single source of truth.

---

## Moduły i endpointy (102 total)

### 1. Core Optimization — 33 endpointy (`app/routes.py`)

Wielokryterialna optymalizacja LP z frontem Pareto i profilami radarowymi.

| Endpoint | Opis |
|----------|------|
| `POST /optimize` | Optymalizacja z custom danymi |
| `GET /optimize/demo/{domain}` | Demo optymalizacja |
| `POST /dashboard` | Pareto front + radar |
| `POST /pareto` | Front Pareto (custom) |
| `POST /pareto-xy` | XY scatter Pareto (koszt vs jakość) |
| `POST /radar` | Profile radarowe dostawców |
| `GET /domains` | Lista 10 domen |
| `GET /domains/extended` | Domeny + subdomeny |
| `POST /process-mining` | P2P process mining |
| ... | + 24 kolejne |

**Kryteria optymalizacji:**
- **Koszt** (unit cost + logistics)
- **Czas dostawy** (lead time)
- **Compliance** (SLA / zgodność)
- **ESG** (sustainability / niezawodność)

**Constrainty:**
- C1–C5: Demand, capacity, regional, diversification (LP)
- C10: Min supplier count
- C11: Geographic diversity
- C12: ESG floor (min 0.70)
- C13: Payment terms cap (max 60 dni)
- C14: Contract lock-in
- C15: Preferred supplier bonus

### 2. Optimized Buying — 14 endpointów (`app/buying_routes.py`)

Guided buying inspirowany SAP Ariba — katalog → koszyk → optymalizacja → zamówienie.

| Endpoint | Opis |
|----------|------|
| `GET /buying/catalog` | Katalog produktów |
| `GET /buying/categories` | Kategorie |
| `POST /buying/calculate` | Reguły koszyka |
| `POST /buying/optimize` | Krok 1: optymalizuj |
| `POST /buying/checkout` | Krok 2: złóż zamówienie |
| `POST /buying/order-from-optimizer` | Zamówienie z Tab 1 |
| `POST /buying/orders/{id}/approve` | Zatwierdzenie |
| `POST /buying/orders/{id}/generate-po` | Generuj PO |
| `POST /buying/orders/{id}/confirm` | Potwierdzenie dostawcy |
| `POST /buying/orders/{id}/ship` | W dostawie |
| `POST /buying/orders/{id}/deliver` | Odbiór towaru |
| `POST /buying/orders/{id}/cancel` | Anuluj |
| `GET /buying/orders/{id}/timeline` | Audit log |

**Cykl życia zamówienia:**
```
draft → pending_approval → approved → po_generated → confirmed → in_delivery → delivered
                                                                              ↘ cancelled
```

**Cross-module integration:**
- Tab 1 Optimizer → "Złóż zamówienie" → tworzy order w Buying
- Buying → "Otwórz w optymalizatorze" → ładuje domenę w Tab 1

### 3. MIP Binary Optimization — 4 endpointy (`app/mip_routes.py`)

Dedykowany solver MIP (0/1) z constraintami IT.

| Endpoint | Opis |
|----------|------|
| `POST /mip/optimize` | MIP z custom danymi |
| `GET /mip/optimize/demo` | Demo MIP |
| `POST /mip/compare` | LP vs MIP porównanie |
| `GET /mip/compare/demo` | Demo porównanie |

### 4. What-If & Alerts — 5 endpointów (`app/whatif_routes.py`)

Scenariusze i alerty optymalizacyjne.

| Endpoint | Opis |
|----------|------|
| `POST /whatif/scenarios` | 2-10 scenariuszy |
| `GET /whatif/scenarios/demo` | Demo (Baseline/Budget/Green) |
| `POST /whatif/alerts` | Alerty z wyniku optymalizacji |
| `POST /whatif/alerts/process` | Alerty procesowe |
| `GET /whatif/alerts/demo` | Demo alerty |

### 5. Process Mining — 19 endpointów (`app/process_digging_routes.py`)

Zaawansowany process mining P2P z pm4py.

| Analiza | POST | GET demo |
|---------|------|----------|
| DFG (Directly Follows Graph) | `/process-digging/dfg` | `/process-digging/demo/dfg` |
| Performance DFG | `/process-digging/performance-dfg` | — |
| Lead Time | `/process-digging/lead-time` | `/process-digging/demo/lead-time` |
| Bottlenecks | `/process-digging/bottlenecks` | `/process-digging/demo/bottlenecks` |
| Variants | `/process-digging/variants` | `/process-digging/demo/variants` |
| Conformance | `/process-digging/conformance` | — |
| Handovers | `/process-digging/handovers` | — |
| Rework/Loops | `/process-digging/rework` | `/process-digging/demo/rework` |
| SLA Monitor | `/process-digging/sla-monitor` | `/process-digging/demo/sla` |
| Anomalies | `/process-digging/anomalies` | `/process-digging/demo/anomalies` |
| Full Report | `/process-digging/full-report` | — |

### 6. Risk Engine — 6 endpointów (`app/risk_routes.py`)

Analiza ryzyka, symulacja Monte Carlo, wsparcie negocjacji.

| Endpoint | Opis |
|----------|------|
| `POST /risk/heatmap` | Heatmapa ryzyka (supplier × product) |
| `GET /risk/heatmap/demo` | Demo heatmap |
| `POST /risk/monte-carlo` | Symulacja MC (1000 iteracji) |
| `GET /risk/monte-carlo/demo` | Demo MC (500 iteracji) |
| `POST /risk/negotiation` | Cele negocjacyjne |
| `GET /risk/negotiation/demo` | Demo negocjacje |

**Risk composite** = 0.4×single_source + 0.3×capacity_util + 0.3×esg_risk

### 7. RFQ Integration — 6 endpointów (`app/integration_routes.py`)

Generyczny interfejs RFQ (vendor-agnostic, bez lock-in SAP/Ariba).

| Endpoint | Opis |
|----------|------|
| `POST /integration/rfq/import` | Import RFQ + auto-optymalizacja |
| `POST /integration/rfq/export` | Eksport wyniku |
| `GET /integration/status` | Health check |
| `POST /integration/webhook` | Webhook (rfq.created, bid.received) |
| `GET /integration/rfq/demo` | Demo RFQ |
| `GET /integration/rfq/{rfq_id}` | Pobierz zapisany RFQ |

### 8. Database CRUD — 15 endpointów (`app/db_routes.py`)

CRUD operacje na Turso DB + upload CSV/XLSX.

| Endpoint | Opis |
|----------|------|
| `GET /db/status` | Status bazy |
| `GET/POST/DELETE /db/suppliers` | CRUD dostawcy |
| `GET/POST/DELETE /db/demand` | CRUD zapotrzebowanie |
| `GET /db/results` | Lista wyników |
| `GET /db/results/{id}` | Szczegóły wyniku |
| `GET/POST/DELETE /db/p2p-events` | CRUD zdarzenia P2P |
| `POST /db/seed/{domain}` | Seed demo danych |
| `POST /db/seed-p2p` | Seed zdarzeń P2P |

---

## Dashboard UI (5 tabów)

### Tab 1: Optimization
- Wybór domeny (10 przycisków) + subdomena
- Suwaki wag (cost/time/compliance/esg)
- Front Pareto (liniowy + XY scatter)
- Tabela alokacji
- Profile radarowe dostawców
- Sankey diagram (supplier → product)
- Cost donut chart
- **"Złóż zamówienie"** — bridge do modułu Buying

### Tab 2: Optimized Buying
- Katalog produktów z filtrami
- Koszyk z regułami ilościowymi
- **Dwustopniowy checkout:** optymalizuj → potwierdź zamówienie
- Lista zamówień z lifecycle
- Timeline / audit log

### Tab 3: Process Mining
- DFG (Directly Follows Graph) — Cytoscape.js
- Lead time analysis
- Bottleneck detection
- Conformance checking
- SLA monitoring

### Tab 4: What-If Scenarios
- Porównanie 2-10 scenariuszy
- Alerty optymalizacyjne i procesowe
- Cross-domain trend chart

### Tab 5: Risk
- Risk heatmap (supplier × product)
- Monte Carlo histogram
- Supplier stability chart
- Negotiation targets

---

## Struktura plików

```
intercars_optimizer/
├── app/
│   ├── __init__.py
│   ├── main.py              (93 LOC)  — FastAPI setup, route registration
│   ├── config.py             (75 LOC)  — Pydantic Settings, env vars
│   ├── schemas.py         (1,159 LOC)  — 67 modeli Pydantic
│   ├── data_layer.py      (1,373 LOC)  — dane demo, 10 domen, DOMAIN_WEIGHTS
│   ├── optimizer.py         (754 LOC)  — LP solver, profiling
│   ├── solver_mip.py        (450 LOC)  — MIP solver (PuLP + HiGHS)
│   ├── pareto.py            (134 LOC)  — generacja frontu Pareto
│   ├── routes.py            (830 LOC)  — 33 endpointy core
│   ├── buying_engine.py     (655 LOC)  — katalog, koszyk, zamówienia
│   ├── buying_routes.py     (477 LOC)  — 14 endpointów buying
│   ├── mip_routes.py        (280 LOC)  — 4 endpointy MIP
│   ├── whatif_engine.py     (239 LOC)  — silnik scenariuszy
│   ├── whatif_routes.py     (212 LOC)  — 5 endpointów what-if
│   ├── process_miner.py     (306 LOC)  — DFG, lead time, variants
│   ├── process_digging.py   (634 LOC)  — zaawansowany process mining
│   ├── process_digging_routes.py (396 LOC) — 19 endpointów
│   ├── alerts_engine.py     (285 LOC)  — silnik alertów
│   ├── risk_engine.py       (350 LOC)  — Monte Carlo, heatmap, negocjacje
│   ├── risk_routes.py       (162 LOC)  — 6 endpointów risk
│   ├── integration_engine.py (247 LOC) — RFQ transformer
│   ├── integration_routes.py (203 LOC) — 6 endpointów RFQ
│   ├── database.py          (456 LOC)  — Turso HTTP client
│   ├── db_routes.py         (217 LOC)  — 15 endpointów DB
│   ├── upload.py            (194 LOC)  — CSV/XLSX parser
│   └── static/
│       └── index.html    (148,791 B)   — dashboard SPA
├── Procfile                             — Railway config
├── runtime.txt                          — Python 3.11
├── requirements.txt                     — 12 zależności
├── vercel.json                          — Vercel config (legacy)
└── PROJECT.md                           — ta dokumentacja
```

**Total: 10,181 LOC Python + 149KB frontend**

---

## Konfiguracja (env vars)

Wszystkie zmienne z prefixem `INTERCARS_`:

| Zmienna | Default | Opis |
|---------|---------|------|
| `TURSO_DATABASE_URL` | — | URL bazy Turso |
| `TURSO_AUTH_TOKEN` | — | Token auth Turso |
| `DEFAULT_SOLVER_MODE` | continuous | LP lub binary |
| `DEFAULT_MAX_VENDOR_SHARE` | 0.60 | Max udział dostawcy |
| `DEFAULT_SLA_TARGET_HOURS` | 120.0 | SLA target (5 dni) |
| `DEFAULT_ANOMALY_Z_THRESHOLD` | 2.0 | Z-score anomalii |
| `DEFAULT_MIN_SUPPLIER_COUNT` | 2 | Min dostawców |
| `DEFAULT_MIN_ESG_SCORE` | 0.70 | Min ESG |
| `DEFAULT_MAX_PAYMENT_TERMS_DAYS` | 60.0 | Max termin płatności |
| `MONTE_CARLO_ITERATIONS` | 1000 | Iteracje MC |
| `SOLVER_TIME_LIMIT_SECONDS` | 60.0 | Limit solvera |
| `MIP_GAP_TOLERANCE` | 1e-4 | Tolerancja MIP |

---

## Uruchomienie lokalne

```bash
cd intercars_optimizer
pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000

# Dashboard: http://localhost:8000/ui
# API Docs:  http://localhost:8000/docs
# Health:    http://localhost:8000/health
```

---

## Zależności (requirements.txt)

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
scipy>=1.12.0          # HiGHS LP solver
PuLP>=2.8.0            # MIP solver
highspy>=1.7.0         # HiGHS Python binding
numpy>=1.26.0          # numerics
pm4py>=2.7.0           # process mining
pandas>=2.2.0          # data manipulation
openpyxl>=3.1.0        # XLSX upload
python-multipart>=0.0.9 # file upload
```

---

## Historia wersji

| Wersja | Opis |
|--------|------|
| 1.0.0 | Core LP optimizer, 3 domeny, basic dashboard |
| 2.0.0 | MIP solver, Process Mining, What-If, 8 domen |
| 2.5.0 | Database Turso, 68 endpointów, 4-tab UI |
| 3.0.0 | 10 domen + subdomeny, C10-C15, RFQ integration, Risk Engine |
| **3.1.0** | **Optimized Buying, cross-module integration, Railway deploy** |
