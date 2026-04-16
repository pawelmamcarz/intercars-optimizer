# INTERCARS Procurement Optimization Platform v4.0.0

**Platforma optymalizacji portfela zamówień dla INTERCARS** — guided 5-step procurement wizard z wielokryterialną optymalizacją, analizą ryzyka, process mining, klasyfikacją UNSPSC i integracją EWM.

**Live:** https://web-production-8d81d.up.railway.app/ui
**Admin:** https://web-production-8d81d.up.railway.app/admin-ui
**Portal dostawcy:** https://web-production-8d81d.up.railway.app/portal-ui
**API Docs:** https://web-production-8d81d.up.railway.app/docs
**Hosting:** Railway.app
**Repo:** github.com/pawelmamcarz/intercars-optimizer

---

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (3 portale SPA)                   │
│    index.html (220KB)  │  admin.html (30KB)  │  portal.html  │
│    5-step wizard:      │  Katalog, UNSPSC    │  Certyfikaty  │
│    Zapotrzeb→Dostaw→   │  Dostawcy, Config   │  Zamówienia   │
│    Optymalizuj→Zamów→  │                     │  Profil       │
│    Monitor             │                     │               │
└────────────────────────┬────────────────────────────────────┘
                         │ REST JSON
┌────────────────────────▼────────────────────────────────────┐
│                   FastAPI REST API                            │
│              13 routerów, 165 endpointów                      │
│                    prefix: /api/v1/                           │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  routes  │ buying   │ supplier │  admin   │  digging        │
│  (34)    │ (20)     │  (15)    │  (15)    │  (18)           │
├──────────┼──────────┼──────────┼──────────┼─────────────────┤
│  risk    │integr.   │   db     │  portal  │  ewm    │ auth  │
│  (9)     │ (6)      │  (15)    │  (13)    │  (7)    │ (4)   │
└──────┬───┴──────┬───┴─────┬───┴──────────┴─────────┴───────┘
       │          │         │
┌──────▼───┐ ┌───▼────┐ ┌──▼──────────┐  ┌──────────────┐
│ Optimizer│ │ Buying │ │  Turso DB   │  │  EWM (placeholder) │
│ HiGHS LP │ │ Engine │ │  (libsql)   │  │  7 endpoints  │
│ PuLP MIP │ │ UNSPSC │ │  opcjonalna │  │  await client │
└──────────┘ │ CIF    │ └─────────────┘  └──────────────┘
             └────────┘
```

**Trzy warstwy:**
1. **Data Layer** — dane demo (10 domen), Turso DB, upload CSV/XLSX/CIF
2. **Optimization Layer** — HiGHS (LP continuous), PuLP (MIP binary), Monte Carlo
3. **Decision Layer** — REST API + 3 portale SPA + 5-step wizard

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

## Moduły i endpointy (165 total)

### 1. Core Optimization — 34 endpointy (`app/routes.py`)

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

### 2. Buying, CIF & UNSPSC — 20 endpointów (`app/buying_routes.py`)

Guided buying z 3 ścieżkami zakupowymi, CIF V3.0, auto-klasyfikacja UNSPSC.

| Endpoint | Opis |
|----------|------|
| `GET /buying/catalog` | Katalog produktów z cenami |
| `GET /buying/categories` | Kategorie produktowe |
| `GET /buying/kpi` | KPI dashboard (wydatki, zamówienia, oszczędności) |
| `POST /buying/calculate` | Reguły koszyka |
| `POST /buying/optimize` | Optymalizuj koszyk |
| `POST /buying/checkout` | Złóż zamówienie |
| `POST /buying/order-from-optimizer` | Zamówienie z wyników solvera |
| `POST /buying/orders/{id}/approve` | Zatwierdzenie managera |
| `POST /buying/orders/{id}/generate-po` | Generuj Purchase Order |
| `POST /buying/orders/{id}/confirm` | Potwierdzenie dostawcy |
| `POST /buying/orders/{id}/ship` | Wysyłka |
| `POST /buying/orders/{id}/deliver` | Odbiór towaru |
| `POST /buying/orders/{id}/cancel` | Anuluj |
| `GET /buying/orders/{id}/timeline` | Audit log |
| `POST /cif/upload` | Upload CIF/CSV z auto-klasyfikacją UNSPSC |
| `GET /cif/template` | Pobranie szablonu CIF (10 pozycji) |
| `GET /unspsc/search` | Wyszukiwarka UNSPSC (45+ kodów) |

**4 ścieżki zakupowe (Step 1)** — z badge Direct/Indirect dopasowanym do typowego use case:
1. **Z katalogu** (Direct) — przeglądanie produktów z kartami, qty +/-, wyszukiwarka
2. **Z pliku CIF/CSV** (Direct) — upload z automatyczną klasyfikacją UNSPSC (80+ reguł)
3. **Ad hoc** (Indirect) — ręczne wpisanie pozycji z UNSPSC search per wiersz
4. **Marketplace** (Indirect) — Allegro + PunchOut cXML

Wybór typu zakupu (Direct/Indirect) filtruje widoczne kategorie UNSPSC i wyróżnia ścieżki pasujące do typu — pozostałe są dostępne, ale przyciemnione.

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

### 9. Admin Panel — 15 endpointów (`app/admin_routes.py`)

Zarządzanie katalogiem produktów, dostawcami, konfiguracją. UI: `/admin-ui`

### 10. Supplier Portal — 13 endpointów (`app/portal_routes.py`)

Portal dostawcy — certyfikaty, zamówienia, profil. UI: `/portal-ui`

### 11. Supplier Management — 15 endpointów (`app/supplier_routes.py`)

Profile dostawców, certyfikaty, oceny, weryfikacja VAT (VIES).

### 12. EWM Integration — 7 endpointów (`app/ewm_integration.py`)

Extended Warehouse Management (placeholder — await client EWM API):
- Stock levels, goods receipt, reservations, warehouses, movements

### 13. Auth — 4 endpointy (`app/auth.py`)

JWT authentication, role-based access (admin/user/supplier).

---

## Dashboard UI — 5-step Guided Procurement Wizard

### Krok 1: Zapotrzebowanie
- **Rodzaj zakupu** — toggle Direct / Indirect / Wszystkie (domyślnie Wszystkie)
  - **Direct** (6 domen): parts, oe_components, oils, batteries, tires, bodywork — produkty do sprzedaży
  - **Indirect** (4 domeny): it_services, logistics, packaging, facility_management — OPEX
  - Filtr grupuje kategorie UNSPSC i przyciemnia ścieżki zakupowe niepasujące do typu
- Wybór kategorii UNSPSC (wyszukiwarka + quick-select pogrupowane Direct/Indirect)
- **4 ścieżki (badge Direct/Indirect):** Z katalogu | Z pliku CIF/CSV | Ad hoc | Marketplace (Allegro/PunchOut)
- Context bar pokazuje chip typu zakupu (Direct/Indirect) obok kategorii
- Podsumowanie zapotrzebowania live (pozycje, wartość PLN)

### Krok 2: Dostawcy
- Karty dostawców (NIP, kraj, certyfikaty, kategorie UNSPSC)
- Weryfikacja VAT (VIES)
- Filtrowanie, dodawanie nowych dostawców

### Krok 3: Optymalizacja
- Solver LP/MIP z parametrami (lambda, wagi, tryb)
- Front Pareto (liniowy + XY scatter)
- Profile radarowe, tabela alokacji, Sankey, Cost donut

### Krok 4: Zamówienie
- Optimized Buying — katalog z koszykiem
- Lifecycle: draft → approved → PO → confirmed → delivered
- Approval workflow (>15 000 PLN → manager)

### Krok 5: Monitoring i analiza
- Process Mining (DFG Cytoscape.js)
- Alerty (optymalizacja + procesowe)
- Risk Heatmap + Monte Carlo
- What-If scenarios

---

## Struktura plików

```
intercars_optimizer/
├── app/
│   ├── __init__.py
│   ├── main.py              (93 LOC)  — FastAPI setup, 13 routerów
│   ├── config.py             (75 LOC)  — Pydantic Settings, env vars
│   ├── auth.py             (~200 LOC)  — JWT auth, role-based access
│   ├── schemas.py         (1,264 LOC)  — modele Pydantic
│   ├── data_layer.py      (1,373 LOC)  — dane demo, 10 domen
│   ├── database.py        (1,007 LOC)  — Turso/libSQL client + CRUD
│   ├── optimizer.py         (754 LOC)  — LP solver (SciPy/HiGHS)
│   ├── solver_mip.py        (450 LOC)  — MIP solver (PuLP/HiGHS)
│   ├── buying_engine.py     (720 LOC)  — katalog, koszyk, lifecycle
│   ├── buying_routes.py     (917 LOC)  — 20 endp. buying/CIF/UNSPSC
│   ├── supplier_engine.py   (541 LOC)  — profile, certyfikaty, VAT
│   ├── supplier_routes.py  (~300 LOC)  — 15 endp. zarządzanie dostawcami
│   ├── admin_routes.py     (~300 LOC)  — 15 endp. admin panel
│   ├── portal_routes.py    (~250 LOC)  — 13 endp. portal dostawcy
│   ├── ewm_integration.py   (198 LOC)  — 7 endp. EWM (placeholder)
│   ├── routes.py            (830 LOC)  — 34 endp. core optimization
│   ├── mip_routes.py        (280 LOC)  — 4 endp. MIP
│   ├── process_miner.py     (306 LOC)  — DFG, lead time, variants
│   ├── process_digging.py   (634 LOC)  — 10 analiz zaawansowanych
│   ├── process_digging_routes.py (396 LOC) — 18 endp.
│   ├── risk_engine.py       (350 LOC)  — Monte Carlo, heatmap
│   ├── risk_routes.py       (162 LOC)  — 9 endp. risk
│   ├── alerts_engine.py     (285 LOC)  — silnik alertów
│   ├── whatif_engine.py     (239 LOC)  — scenariusze
│   ├── whatif_routes.py     (212 LOC)  — 5 endp. what-if
│   ├── integration_engine.py (247 LOC) — RFQ transformer
│   ├── integration_routes.py (203 LOC) — 6 endp. RFQ
│   ├── db_routes.py         (217 LOC)  — 15 endp. DB
│   ├── pareto.py            (134 LOC)  — Pareto front
│   ├── upload.py            (194 LOC)  — CSV/XLSX parser
│   └── static/
│       ├── index.html     (3,890 LOC)  — dashboard SPA (220KB)
│       ├── admin.html       (537 LOC)  — admin panel (30KB)
│       └── portal.html      (507 LOC)  — portal dostawcy (25KB)
├── tests/
│   ├── __init__.py
│   └── test_api.py          (460 LOC)  — 31 testów API
├── 10 pozycji.cif                       — sample CIF file
├── Procfile                             — Railway config
├── runtime.txt                          — Python 3.11
├── requirements.txt                     — 14 zależności
├── SCOPE_v4.0.md                        — szczegółowy zakres wdrożenia
└── PROJECT.md                           — ta dokumentacja
```

**Total: 13,630 LOC Python + 4,934 LOC HTML + 460 LOC tests**

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

## Roadmap — Trzy kroki kolejnej fazy

> Kierunek rozwoju platformy poza v4.0.0: od integracji danych BI, przez zapanowanie nad wydatkami, po automatyzację relacji z dostawcami i klientami wewnętrznymi.

### Kroki w skrócie

- **Krok 1 — Integracja BI:** spięcie danych z wewnętrznych systemów BI (ERP, WMS, finanse, sprzedaż) w jeden obraz kosztowy.
- **Krok 2 — Spend control:** analiza zebranych danych → kontrola i redukcja wydatków (kategoryzacja UNSPSC, benchmarki, alerty).
- **Krok 3 — Automatyzacja relacji:** workflow komunikacji z dostawcami (RFQ, PO, potwierdzenia) i klientami wew. (zapotrzebowania, approvals).

### Krok 1: Zebranie informacji z systemów BI firmy

**Cel:** zbudować jedno źródło prawdy o zakupach, łącząc dane z rozproszonych systemów BI.

**Źródła danych:**
- ERP / finanse — faktury, PO, budżety kosztowe
- WMS / EWM — stany magazynowe, ruchy towarów (dziś placeholder w `app/ewm_integration.py`)
- CIF V3.0 + CSV/XLSX — kanał już obsługiwany przez `app/buying_routes.py` (`/cif/upload`)
- Systemy sprzedażowe / CRM — rotacje, forecast popytu

**Efekt:** rozszerzenie Data Layer (`app/data_layer.py` + Turso) o konektory BI oraz audytowalne logi ingestii w `p2p_events`.

**KPI:** % pokrycia wydatków danymi z BI, świeżość danych (SLA ingestii), % automatycznej klasyfikacji UNSPSC.

### Krok 2: Zapanowanie nad wydatkami na podstawie analizy danych

**Cel:** przekuć zintegrowane dane BI w aktywną kontrolę wydatków.

**Zakres:**
- Rozbudowa `GET /buying/kpi` (`app/buying_routes.py`) o wielowymiarowy spend dashboard (kategoria × dostawca × region × okres)
- Scenariusze what-if na realnych danych (`app/whatif_engine.py`) — prognozy i symulacje kosztów
- Alerty odchyleń budżetowych (`app/alerts_engine.py`) — push do managerów
- Risk scoring vendorów na pełnym spendzie (`app/risk_engine.py`) + Monte Carlo

**Efekt:** manager widzi gdzie płyną pieniądze, dlaczego i jak je uszczelnić — zamiast post-mortem w Excelu.

**KPI:** % managed spend, zidentyfikowane oszczędności PLN/mc, liczba zareagowanych alertów, hit-rate rekomendacji solvera.

### Krok 3: Automatyzacja kontaktów z dostawcami i klientami wewnętrznymi

**Cel:** zautomatyzować powtarzalną komunikację i workflow decyzyjny end-to-end.

**Zakres:**
- Portal dostawcy (`app/portal_routes.py`) — auto-notyfikacje RFQ, potwierdzenia dostaw, przypomnienia o certyfikatach
- Buying lifecycle (`app/buying_engine.py`) — automatyczne approvals, eskalacje >15 000 PLN, auto-PO
- Klienci wewnętrzni — self-service zgłoszenia zapotrzebowania (Krok 1 wizarda), statusy w czasie rzeczywistym
- Webhooks (`app/integration_routes.py`) — dwukierunkowa integracja z ERP / ITSM (rfq.created, bid.received, order.confirmed)

**Efekt:** zakup przechodzi od zgłoszenia do dostawy z minimalną interwencją ludzką; zespół zakupowy zajmuje się wyjątkami, nie rutyną.

**KPI:** % zamówień bez ręcznego dotyku (touchless rate), skrócenie lead time P2P, NPS klientów wewnętrznych, % RFQ zamkniętych w SLA.

### Tabela fazowa

| Faza | Cel biznesowy | Źródła / moduły | Wynik | Zależności |
|------|---------------|-----------------|-------|------------|
| 1 | Jeden obraz zakupów | ERP, WMS/EWM, CIF, CRM → Turso (`data_layer.py`, `database.py`) | Spend data lake + ingestion logs | Dostęp do API systemów BI |
| 2 | Kontrola i redukcja wydatków | `buying_routes.py`, `risk_engine.py`, `whatif_engine.py`, `alerts_engine.py` | Spend dashboard + alerty + scoring | Faza 1 (dane) |
| 3 | Automatyzacja workflow | `portal_routes.py`, `buying_engine.py`, `integration_routes.py`, `supplier_routes.py` | Touchless P2P + webhooks ERP | Faza 2 (reguły z analizy) |

---

## Historia wersji

| Wersja | Endp. | Opis |
|--------|------:|------|
| 1.0.0 | ~10 | Core LP optimizer, 3 domeny, basic dashboard |
| 2.0.0 | ~30 | MIP solver, Process Mining, What-If, 8 domen |
| 2.5.0 | 68 | Database Turso, 4-tab UI |
| 3.0.0 | 86 | 10 domen + subdomeny, C10-C15, RFQ integration, Risk Engine |
| 3.1.0 | 86 | Optimized Buying, cross-module integration, Railway deploy |
| **4.0.0** | **165** | **Guided 5-step wizard, 3 ścieżki zakupowe (katalog/adhoc/CIF), UNSPSC klasyfikacja, EWM placeholder, admin panel, portal dostawcy, JWT auth, 31 testów, mobile responsive** |
