# INTERCARS Procurement Optimization Platform — v4.0.0

## Zakres wdrożenia

**Wersja:** 4.0.0
**Data wdrożenia:** 2026-03-14
**Platforma:** FastAPI + Railway.app
**Live:** https://web-production-8d81d.up.railway.app/ui
**API Docs:** https://web-production-8d81d.up.railway.app/docs
**Repozytorium:** github.com/pawelmamcarz/intercars-optimizer

---

## 1. Architektura systemu

### 1.1 Stack technologiczny

| Warstwa | Technologia | Rola |
|---------|------------|------|
| Backend | **FastAPI** (Python 3.11+) | REST API, async, OpenAPI auto-docs |
| Solver LP | **SciPy** `linprog` + **HiGHS** | Optymalizacja ciągła (continuous) |
| Solver MIP | **PuLP** + **HiGHS** | Optymalizacja binarna (integer) |
| Modele danych | **Pydantic v2** | Walidacja, serializacja, schematy |
| Konfiguracja | **pydantic-settings** | Env-vars z prefixem `INTERCARS_` |
| Process Mining | **pm4py** + **pandas** | DFG, warianty, bottlenecki |
| Baza danych | **Turso / libSQL** (opcjonalna) | Persystencja wyników, dostawców, zdarzeń |
| Auth | **passlib** + **python-jose** | JWT tokens, role-based access (admin/user/supplier) |
| Frontend | **Vanilla JS** + **Chart.js 4.4.7** + **Cytoscape.js 3.28.1** | SPA, 5-step wizard + 3 portale |
| Deploy | **Railway.app** | Auto-deploy z main branch |
| Testy | **pytest** + **httpx** (TestClient) | 31 testów API |

### 1.2 Zależności (requirements.txt)

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
scipy>=1.12.0
PuLP>=2.8.0
highspy>=1.7.0
numpy>=1.26.0
pm4py>=2.7.0
pandas>=2.2.0
openpyxl>=3.1.0
python-multipart>=0.0.9
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
```

### 1.3 Struktura plików (13 630 linii Python + 4 934 linii HTML)

| Plik | Linii | Opis |
|------|------:|------|
| `app/data_layer.py` | 1 373 | 10 domen × 27 subdomen — dane demo |
| `app/schemas.py` | 1 264 | Modele Pydantic — wszystkie schematy API |
| `app/database.py` | 1 007 | Turso/libSQL client + CRUD |
| `app/buying_routes.py` | 917 | Router buying — katalog, CIF, UNSPSC, zamówienia |
| `app/routes.py` | 830 | Router główny — optymalizacja, demo, dashboard |
| `app/optimizer.py` | 754 | Solver LP (SciPy/HiGHS) + constrainty C1-C15 |
| `app/buying_engine.py` | 720 | Silnik buying — katalog, koszyk, lifecycle |
| `app/process_digging.py` | 634 | Process Digging Engine — 10 analiz |
| `app/supplier_engine.py` | 541 | Silnik dostawców — profile, certyfikaty, VAT |
| `app/solver_mip.py` | 450 | Solver MIP (PuLP/HiGHS) |
| `app/process_digging_routes.py` | 396 | Endpointy Process Digging |
| `app/risk_engine.py` | 350 | Risk Heatmap + Monte Carlo + Negotiation |
| `app/process_miner.py` | 306 | Process Miner — DFG, warianty, lead-times |
| `app/mip_routes.py` | 280 | Endpointy MIP |
| `app/alerts_engine.py` | 285 | Silnik alertów (optymalizacja + process) |
| `app/whatif_engine.py` | 239 | What-If Engine — scenariusze porównawcze |
| `app/integration_engine.py` | 247 | RFQ Transformer + in-memory store |
| `app/whatif_routes.py` | 212 | Endpointy What-If + Alerts |
| `app/db_routes.py` | 217 | Endpointy bazy danych |
| `app/integration_routes.py` | 203 | Endpointy integracji RFQ |
| `app/ewm_integration.py` | 198 | EWM placeholder — 7 endpointów (await client API) |
| `app/upload.py` | 194 | Parser CSV/XLSX upload |
| `app/risk_routes.py` | 162 | Endpointy Risk Engine |
| `app/admin_routes.py` | ~300 | Admin panel — katalog, dostawcy, UNSPSC |
| `app/portal_routes.py` | ~250 | Portal dostawcy — certyfikaty, zamówienia |
| `app/supplier_routes.py` | ~300 | Zarządzanie dostawcami |
| `app/auth.py` | ~200 | Autentykacja JWT, role-based access |
| `app/pareto.py` | 134 | Generator Pareto front (1D + XY) |
| `app/main.py` | 93 | App factory, 13 routerów, CORS, lifespan |
| `app/config.py` | 75 | Settings — env-overridable |
| **app/static/index.html** | **3 890** | **Dashboard SPA — 5-step wizard** |
| `app/static/admin.html` | 537 | Admin panel UI |
| `app/static/portal.html` | 507 | Portal dostawcy UI |
| `tests/test_api.py` | 460 | 31 testów API (pytest + httpx) |

---

## 2. Co nowego w v4.0 (vs v3.1)

### 2.1 Guided Procurement Wizard (5 kroków)

Nowy UX zastępujący statyczny dashboard — prowadzi użytkownika przez cały proces P2P:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 1. Zapotrze- │ →  │ 2. Dostawcy  │ →  │ 3. Optyma-   │ →  │ 4. Zamówienie│ →  │ 5. Monitoring│
│    bowanie   │    │              │    │    lizacja   │    │              │    │   i analiza  │
│              │    │ Zarządzanie  │    │ HiGHS Solver │    │ Optimized    │    │ Process      │
│ UNSPSC +     │    │ dostawcami,  │    │ LP/MIP,      │    │ Buying,      │    │ Mining,      │
│ 3 ścieżki:  │    │ certyfikaty, │    │ parametry,   │    │ koszyk,      │    │ alerty,      │
│ katalog/     │    │ VIES, ryzyko │    │ Pareto front │    │ lifecycle PO │    │ ryzyko,      │
│ adhoc/CIF    │    │              │    │              │    │              │    │ what-if      │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 Step 1 — Rozgałęzienie ścieżek zakupowych

Krok 1 oferuje 3 metody budowania zapotrzebowania po wyborze kategorii UNSPSC:

| Ścieżka | Opis | Funkcje |
|---------|------|---------|
| **Z katalogu** | Przeglądanie katalogu produktów | Karty produktów z obrazkami, qty +/-, wyszukiwarka, podsumowanie live |
| **Ad hoc** | Ręczne wpisanie pozycji jednorazowych | Tabela z UNSPSC search per wiersz, auto-kalkulacja wartości |
| **Z pliku CIF/CSV** | Upload pliku CIF V3.0 z katalogiem dostawcy | Auto-klasyfikacja UNSPSC (80+ reguł keyword), parsowanie wieloformatowe |

### 2.3 Klasyfikacja UNSPSC

- **45+ kodów UNSPSC** zmapowanych dla automotive parts
- **Wyszukiwarka** po kodzie, nazwie PL/EN, słowach kluczowych
- **Auto-klasyfikacja CIF** — 80+ reguł keyword-based
- **Endpoint:** `GET /api/v1/unspsc/search?q=hamulce`
- **Integracja w admin panel** — UNSPSC search przy dodawaniu produktów

### 2.4 Trzy portale UI

| Portal | URL | Rola | Funkcje |
|--------|-----|------|---------|
| **Dashboard** | `/ui` | Kupiec / Manager | 5-step wizard, optymalizacja, zamówienia |
| **Admin** | `/admin-ui` | Administrator | Zarządzanie katalogiem, dostawcami, UNSPSC |
| **Portal dostawcy** | `/portal-ui` | Dostawca | Certyfikaty, zamówienia, profil |

### 2.5 EWM Integration (placeholder)

7 endpointów Extended Warehouse Management — gotowe do podpięcia pod rzeczywiste API klienta:

| Endpoint | Opis |
|----------|------|
| `GET /ewm/status` | Status połączenia EWM |
| `GET /ewm/stock/{product_id}` | Stan magazynowy produktu |
| `GET /ewm/stock` | Bulk query stanów magazynowych |
| `POST /ewm/goods-receipt` | Potwierdzenie przyjęcia towaru |
| `POST /ewm/reservation` | Rezerwacja magazynowa |
| `GET /ewm/warehouses` | Lista magazynów |
| `GET /ewm/movements` | Ostatnie ruchy magazynowe |

### 2.6 Mobile Responsive

- **@media 1024px** — tablet layout (2 kolumny, mniejsze karty)
- **@media 768px** — mobile layout (1 kolumna, hamburger menu)
- Ścieżki Step 1 przechodzą na układ pionowy na mobile

### 2.7 Test Suite

- **31 testów API** pokrywających wszystkie moduły
- **pytest + httpx TestClient** — bez potrzeby uruchamiania serwera
- **Czas:** ~2.2s (cały suite)

---

## 3. Endpointy API — 165 endpointów

### 3.1 Podsumowanie routerów

| # | Router | Plik | Endpointy | Opis |
|---|--------|------|----------:|------|
| 1 | Core Optimization | `routes.py` | 34 | LP/MIP, Pareto, dashboard, demo |
| 2 | Buying & CIF | `buying_routes.py` | 20 | Katalog, CIF upload, UNSPSC, zamówienia |
| 3 | Process Digging | `process_digging_routes.py` | 18 | 10 analiz zaawansowanych |
| 4 | Database CRUD | `db_routes.py` | 15 | Suppliers, demand, results, P2P events |
| 5 | Admin | `admin_routes.py` | 15 | Zarządzanie katalogiem, dostawcami |
| 6 | Supplier Management | `supplier_routes.py` | 15 | Profile, certyfikaty, oceny |
| 7 | Supplier Portal | `portal_routes.py` | 13 | Portal dostawcy |
| 8 | Risk Engine | `risk_routes.py` | 9 | Heatmap, Monte Carlo, negocjacje |
| 9 | EWM Integration | `ewm_integration.py` | 7 | Magazyn (placeholder) |
| 10 | RFQ Integration | `integration_routes.py` | 6 | Generic RFQ API |
| 11 | What-If & Alerts | `whatif_routes.py` | 5 | Scenariusze, alerty |
| 12 | MIP Solver | `mip_routes.py` | 4 | Binary optimization |
| 13 | Auth | `auth.py` | 4 | JWT login, register, roles |
| | **Razem** | | **165** | |

### 3.2 Nowe endpointy w v4.0

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/cif/upload` | Upload i parsowanie pliku CIF/CSV z auto-klasyfikacją UNSPSC |
| `GET` | `/api/v1/cif/template` | Pobranie szablonu CIF (10 pozycji) |
| `GET` | `/api/v1/unspsc/search` | Wyszukiwarka UNSPSC (kod, keyword, PL/EN) |
| `GET` | `/api/v1/buying/kpi` | KPI dashboard (zamówienia, wydatki, oszczędności) |
| `GET` | `/api/v1/buying/catalog` | Katalog produktów z cenami i obrazkami |
| `GET` | `/api/v1/buying/categories` | Kategorie produktowe |
| `GET` | `/api/v1/ewm/status` | EWM connection status |
| `GET` | `/api/v1/ewm/stock/{id}` | Stan magazynowy produktu |
| `GET` | `/api/v1/ewm/stock` | Bulk stock query |
| `POST` | `/api/v1/ewm/goods-receipt` | Przyjęcie towaru |
| `POST` | `/api/v1/ewm/reservation` | Rezerwacja magazynowa |
| `GET` | `/api/v1/ewm/warehouses` | Lista magazynów |
| `GET` | `/api/v1/ewm/movements` | Ruchy magazynowe |
| `POST` | `/api/v1/auth/login` | JWT login |
| `POST` | `/api/v1/auth/register` | Rejestracja użytkownika |
| `GET` | `/api/v1/suppliers` | Lista dostawców z profilami |
| `POST` | `/api/v1/suppliers` | Dodaj dostawcę |

### 3.3 Buying — pełny lifecycle zamówienia

```
draft → pending_approval → approved → po_generated → confirmed → in_delivery → delivered
                                                                               ↘ cancelled
```

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/buying/calculate` | Reguły koszyka |
| `POST` | `/api/v1/buying/optimize` | Optymalizuj koszyk |
| `POST` | `/api/v1/buying/checkout` | Złóż zamówienie |
| `POST` | `/api/v1/buying/order-from-optimizer` | Zamówienie z wyników solvera |
| `POST` | `/api/v1/buying/orders/{id}/approve` | Zatwierdzenie managera |
| `POST` | `/api/v1/buying/orders/{id}/generate-po` | Generuj Purchase Order |
| `POST` | `/api/v1/buying/orders/{id}/confirm` | Potwierdzenie dostawcy |
| `POST` | `/api/v1/buying/orders/{id}/ship` | Wysyłka |
| `POST` | `/api/v1/buying/orders/{id}/deliver` | Odbiór towaru |
| `POST` | `/api/v1/buying/orders/{id}/cancel` | Anulowanie |
| `GET` | `/api/v1/buying/orders/{id}/timeline` | Audit log |

---

## 4. 10 Domen Procurement

### 4.1 Domeny DIRECT (6) — klasyfikacja UNSPSC

| # | Domena | UNSPSC | Label PL | Subdomeny |
|---|--------|--------|----------|-----------|
| 1 | `parts` | 25101500 | Części zamienne | `brake_systems`, `filters`, `suspension` |
| 2 | `oe_components` | 25102000 | Komponenty OE | `engine_parts`, `electrical`, `transmission` |
| 3 | `oils` | 15121500 | Oleje i płyny | `engine_oils`, `transmission_fluids` |
| 4 | `batteries` | 25172000 | Akumulatory | `starter_batteries`, `agm_efb` |
| 5 | `tires` | 25171500 | Opony | `summer_tires`, `winter_tires`, `all_season` |
| 6 | `bodywork` | 26101100 | Nadwozia i oświetlenie | `body_panels`, `lighting`, `glass` |

### 4.2 Domeny INDIRECT (4)

| # | Domena | UNSPSC | Label PL | Subdomeny |
|---|--------|--------|----------|-----------|
| 7 | `it_services` | 43211500 | Usługi IT | `development`, `cloud_infra`, `data_analytics` |
| 8 | `logistics` | 78101800 | Logistyka | `domestic`, `international`, `last_mile` |
| 9 | `packaging` | 24112400 | Opakowania | `cardboard`, `plastics` |
| 10 | `facility_management` | 27111700 | Zarządzanie obiektem | `maintenance`, `safety_equipment`, `cleaning` |

---

## 5. Solver — Optymalizacja wielokryterialna

### 5.1 Funkcja celu

```
min  λ · Σᵢ Σⱼ (w_cost·cᵢⱼ + w_time·tᵢⱼ) · xᵢⱼ · Dⱼ
   + (1-λ) · Σᵢ Σⱼ (w_compliance·(1-compᵢ) + w_esg·(1-esgᵢ)) · xᵢⱼ · Dⱼ
```

### 5.2 Tryby solvera

| Tryb | Solver | Zmienne | Opis |
|------|--------|---------|------|
| `continuous` | SciPy linprog + HiGHS | `xᵢⱼ ∈ [0, 1]` | LP ciągłe — split zamówień |
| `binary` | PuLP + HiGHS MIP | `yᵢ ∈ {0,1}`, `xᵢⱼ ∈ [0,1]` | MIP — wybór dostawców binarny |

### 5.3 Constrainty (C1-C5, C10-C15)

| ID | Nazwa | Opis |
|----|-------|------|
| C1 | Demand fulfillment | `Σᵢ xᵢⱼ = 1` per produkt |
| C2 | Capacity limits | `Σⱼ xᵢⱼ · Dⱼ ≤ capacityᵢ` |
| C3 | Min order quantity | `xᵢⱼ · Dⱼ ≥ MOQᵢ` |
| C4 | Non-negativity | `xᵢⱼ ≥ 0` |
| C5 | Max vendor share | `Σⱼ xᵢⱼ · Dⱼ ≤ max_share · Q_total` |
| C10 | Min supplier count | Min N aktywnych dostawców |
| C11 | Geographic diversity | Min 1 dostawca per wymagany region |
| C12 | ESG floor | Średni ważony ESG ≥ 0.70 |
| C13 | Payment terms cap | Średnie warunki płatności ≤ 60 dni |
| C14 | Contract lock-in | Gwarantowana min alokacja |
| C15 | Preferred supplier bonus | Redukcja kosztu dla preferowanych |

---

## 6. Risk Engine

### 6.1 Risk Heatmap

```
risk = 0.4 × single_source_risk + 0.3 × capacity_utilization_risk + 0.3 × esg_risk
```

### 6.2 Monte Carlo Simulation

- N iteracji (domyślnie 1000)
- Perturbacja kosztów/czasów: rozkład log-normalny
- Wyniki: cost mean/std, P5/P95, robustness score, supplier stability

### 6.3 Negotiation Assistant

Analiza celów negocjacyjnych z priorytetami (High/Medium/Low) na podstawie alokacji i kosztów.

---

## 7. Process Mining & Digging

### 7.1 10 analiz Process Digging

| # | Analiza | Opis |
|---|---------|------|
| 1 | Frequency DFG | Mapa częstotliwości przejść |
| 2 | Lead-times | Statystyki czasów per przejście |
| 3 | Bottlenecks | Identyfikacja wąskich gardeł |
| 4 | Variants | Warianty procesowe |
| 5 | Anomalies | Anomalie statystyczne (z-score) |
| 6 | Conformance | Porównanie z referencyjną ścieżką P2P |
| 7 | Rework | Detekcja pętli i powtórzeń |
| 8 | Handovers | Sieć społeczna — przekazania zasobów |
| 9 | Performance DFG | DFG z wagami = czasy |
| 10 | SLA Monitor | Porównanie vs target SLA |

---

## 8. CIF V3.0 — Import katalogów

### 8.1 Format CIF (Catalogue Interchange Format)

```
CIF_I_V3.0
LOADMODE: F
CODEFORMAT: UNSPSC
SUPPLIERID_DOMAIN: DUNS
CURRENCY: PLN
FIELDNAMES: Name, UNSPSC, Description, UOM, LeadTime, Price
DATA
"Klocki hamulcowe TRW","25101500","Klocki hamulcowe przód","szt","5","185.00"
...
ENDOFDATA
```

### 8.2 Auto-klasyfikacja UNSPSC

- 80+ reguł keyword-based (hamulc→25101500, filtr→25101500, olej→15121500, ...)
- Fallback: kod z nagłówka CIF → `CODEFORMAT`
- Statystyki klasyfikacji w odpowiedzi API

---

## 9. Dashboard UI — 5-step Wizard

### 9.1 Krok 1: Zapotrzebowanie

- Wybór kategorii UNSPSC (wyszukiwarka + 10 przycisków quick-select)
- **3 ścieżki:** Z katalogu | Ad hoc | Z pliku CIF/CSV
- Podsumowanie zapotrzebowania (pozycje, wartość PLN)

### 9.2 Krok 2: Dostawcy

- Karty dostawców z profilami (NIP, kraj, certyfikaty, kategorie)
- Weryfikacja VAT (VIES)
- Filtrowanie po kategorii UNSPSC
- Dodawanie nowych dostawców

### 9.3 Krok 3: Optymalizacja

- Solver LP/MIP z parametrami (lambda, wagi, tryb)
- Front Pareto (liniowy + XY scatter)
- Profil radarowe dostawców
- Tabela alokacji, Sankey, Cost donut

### 9.4 Krok 4: Zamówienie

- Optimized Buying — katalog z koszykiem
- Lifecycle zamówienia (draft → delivered)
- Purchase Order generation
- Approval workflow (>15 000 PLN → manager)

### 9.5 Krok 5: Monitoring

- Process Mining (DFG Cytoscape.js)
- Alerty (optymalizacja + procesowe)
- Risk Heatmap + Monte Carlo
- What-If scenarios

### 9.6 Wizualizacje (13 typów)

| Wykres | Technologia | Krok |
|--------|------------|------|
| Pareto Front | Chart.js line | 3 |
| XY Pareto Scatter | Chart.js scatter | 3 |
| Supplier Radar | Chart.js radar | 3 |
| Allocation Bar | Chart.js stacked bar | 3 |
| Sankey Diagram | Vanilla SVG | 3 |
| Cost Donut | Chart.js doughnut | 3 |
| DFG Graph | Cytoscape.js | 5 |
| Scenario Comparison | Chart.js grouped bar | 5 |
| Cross-domain Trend | Chart.js stacked bar | 5 |
| Risk Heatmap | HTML table + CSS | 5 |
| MC Histogram | Chart.js bar | 5 |
| Supplier Stability | Chart.js horizontal bar | 5 |
| Negotiation Table | HTML table | 5 |

---

## 10. Integracja RFQ — Generic Open API

```
┌──────────────────┐     POST /rfq/import      ┌─────────────────────┐
│  Zewnętrzny       │ ──────────────────────────▶│  INTERCARS          │
│  System           │                            │  Optimizer          │
│  Sourcingowy      │◀──────────────────────────│                     │
│  (dowolny)        │     POST /rfq/export      │  LP/MIP Solver      │
│                   │                            │  Risk Engine        │
│                   │     POST /webhook          │  Monte Carlo        │
│                   │ ──────────────────────────▶│                     │
└──────────────────┘                            └─────────────────────┘
```

100% vendor-agnostic — zero referencji do SAP/Ariba. Kompatybilne z dowolnym systemem sourcingowym.

---

## 11. Konfiguracja (env vars)

Wszystkie z prefixem `INTERCARS_`:

| Zmienna | Default | Opis |
|---------|---------|------|
| `DEFAULT_SOLVER_MODE` | `continuous` | Tryb solvera |
| `DEFAULT_MAX_VENDOR_SHARE` | `0.60` | Max udział dostawcy |
| `DEFAULT_MIN_SUPPLIER_COUNT` | `2` | Min dostawców |
| `DEFAULT_MIN_ESG_SCORE` | `0.70` | Min ESG |
| `DEFAULT_MAX_PAYMENT_TERMS_DAYS` | `60.0` | Max termin płatności |
| `MONTE_CARLO_ITERATIONS` | `1000` | Iteracje MC |
| `SOLVER_TIME_LIMIT_SECONDS` | `60.0` | Limit solvera |
| `MIP_GAP_TOLERANCE` | `1e-4` | Tolerancja MIP |
| `TURSO_DATABASE_URL` | — | URL bazy Turso |
| `TURSO_AUTH_TOKEN` | — | Token Turso |

---

## 12. Historia wersji

| Wersja | Data | Endpointy | Kluczowe zmiany |
|--------|------|-----------|-----------------|
| 1.0.0 | — | ~10 | MVP: LP solver, 1 domena (parts) |
| 2.0.0 | — | ~30 | 8 domen, Process Mining, MIP solver |
| 2.4.0 | — | 53 | Process Digging Engine (10 analiz) |
| 2.5.0 | — | 68 | What-If, Alerts, 4-tab UI |
| 3.0.0 | — | 86 | 10 domen+subdomeny, C10-C15, Risk Engine, Monte Carlo |
| 3.1.0 | 2026-03-06 | 86 | Generic RFQ API (vendor-agnostic) |
| **4.0.0** | **2026-03-14** | **165** | **Guided 5-step wizard, 3 ścieżki zakupowe, UNSPSC, CIF V3.0, EWM, admin/portal, auth JWT, testy, mobile responsive** |

---

## 13. Podsumowanie v4.0.0

| Metryka | v3.1 | **v4.0** | Zmiana |
|---------|------|----------|--------|
| Endpointy API | 86 | **165** | +92% |
| Routery FastAPI | 7 | **13** | +86% |
| Portale UI | 1 | **3** | Dashboard + Admin + Portal |
| Kroki wizarda | — | **5** | Nowy guided flow |
| Ścieżki zakupowe | — | **3** | Katalog / Ad hoc / CIF |
| Kody UNSPSC | — | **45+** | Nowa klasyfikacja |
| Domeny procurement | 10 | **10** | — |
| Subdomeny | 27 | **27** | — |
| Constrainty solvera | 11 | **11** | C1-C5 + C10-C15 |
| Analizy Process Mining | 14 | **14** | 4 bazowe + 10 zaawansowanych |
| Wizualizacje | 13 | **13** | — |
| Pliki Python | 23 | **32** | +39% |
| Linii kodu Python | 10 402 | **13 630** | +31% |
| Linii kodu HTML | 1 613 | **4 934** | +206% |
| Testy API | 0 | **31** | Nowy suite |
| Zależności pip | 12 | **14** | +auth |
| Mobile responsive | Nie | **Tak** | 1024px + 768px breakpoints |
| Zewnętrzne zależności vendorowe | 0 | **0** | Vendor-agnostic |
