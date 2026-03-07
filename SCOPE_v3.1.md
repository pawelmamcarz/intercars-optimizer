# INTERCARS Order Portfolio Optimizer — v3.1.0

## Zakres wdrożenia

**Wersja:** 3.1.0
**Data wdrożenia:** 2026-03-06
**Platforma:** FastAPI + Vercel (serverless)
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
| Frontend | **Vanilla JS** + **Chart.js 4.4.7** + **Cytoscape.js 3.28.1** | SPA, 5-tabowy dashboard |
| Deploy | **Vercel** (serverless) | Auto-deploy z main branch |

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
```

### 1.3 Struktura plików (10 402 linii kodu)

| Plik | Linii | Opis |
|------|------:|------|
| `app/schemas.py` | 1 158 | Modele Pydantic — wszystkie schematy API |
| `app/data_layer.py` | 1 125 | 10 domen × 27 subdomen — dane demo |
| `app/static/index.html` | 1 613 | Frontend SPA — 5 tabów, wykresy, interakcje |
| `app/routes.py` | 849 | Router główny — optymalizacja, demo, dashboard, domeny |
| `app/optimizer.py` | 754 | Solver LP (SciPy/HiGHS) + constrainty C1-C15 |
| `app/process_digging.py` | 603 | Process Digging Engine — 10 analiz |
| `app/database.py` | 456 | Turso/libSQL client + CRUD |
| `app/solver_mip.py` | 450 | Solver MIP (PuLP/HiGHS) + constrainty C10-C15 |
| `app/process_digging_routes.py` | 396 | Endpointy Process Digging |
| `app/risk_engine.py` | 350 | Risk Heatmap + Monte Carlo + Negotiation |
| `app/mip_routes.py` | 293 | Endpointy MIP |
| `app/alerts_engine.py` | 285 | Silnik alertów (optymalizacja + process) |
| `app/process_miner.py` | 283 | Process Miner — DFG, warianty, lead-times |
| `app/integration_engine.py` | 247 | RFQ Transformer + in-memory store |
| `app/whatif_engine.py` | 239 | What-If Engine — scenariusze porównawcze |
| `app/whatif_routes.py` | 225 | Endpointy What-If + Alerts |
| `app/db_routes.py` | 217 | Endpointy bazy danych |
| `app/integration_routes.py` | 203 | Endpointy integracji RFQ |
| `app/upload.py` | 194 | Parser CSV/XLSX upload |
| `app/risk_routes.py` | 162 | Endpointy Risk Engine |
| `app/pareto.py` | 134 | Generator Pareto front (1D + XY) |
| `app/main.py` | 91 | App factory, 7 routerów, CORS, lifespan |
| `app/config.py` | 75 | Settings — env-overridable |

---

## 2. Endpointy API — 86 endpointów

### 2.1 Optimization (2 endpointy)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/optimize` | Optymalizacja portfela zamówień (LP ciągłe) |
| `GET` | `/api/v1/optimize/demo` | Demo optymalizacja (dowolna domena) |

**Solver LP (continuous):**
- Funkcja celu: `min λ·koszt_norm + (1-λ)·jakość_norm`
- Wagi: `w_cost`, `w_time`, `w_compliance`, `w_esg` (konfigurowalne per domena)
- Constrainty C1-C5 (bazowe) + C10-C15 (rozszerzone — patrz sekcja 5)

### 2.2 MIP Solver (4 endpointy)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/mip/optimize` | Optymalizacja MIP (zmienne binarne) |
| `GET` | `/api/v1/mip/optimize/demo` | Demo MIP (dowolna domena) |
| `POST` | `/api/v1/mip/compare` | Porównanie LP vs MIP |
| `GET` | `/api/v1/mip/compare/demo` | Demo porównanie LP vs MIP |

**Solver MIP (binary):**
- Zmienne binarne `y[i]` ∈ {0,1} — wybór dostawcy tak/nie
- Zmienne ciągłe `x[i,j]` — alokacja frakcyjna per produkt
- HiGHS z `mip_gap_tolerance` i `time_limit_seconds` (konfigurowalne)

### 2.3 Dashboard (7 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/dashboard` | Pareto front + profile dostawców |
| `GET` | `/api/v1/dashboard/demo` | Demo dashboard (dowolna domena) |
| `POST` | `/api/v1/dashboard/pareto-xy` | XY Pareto scatter (koszt PLN vs jakość) |
| `GET` | `/api/v1/dashboard/pareto-xy/demo` | Demo XY Pareto |
| `GET` | `/api/v1/dashboard/sankey/demo` | Sankey diagram przepływów alokacji |
| `GET` | `/api/v1/dashboard/donut/demo` | Donut rozkładu kosztów per dostawca |
| `GET` | `/api/v1/dashboard/trend/demo` | Trend porównania cross-domain |

### 2.4 Domains & Demo Data (8 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `GET` | `/api/v1/domains` | Lista 10 domen z metadanymi |
| `GET` | `/api/v1/domains/extended` | 10 domen z subdomenami |
| `GET` | `/api/v1/domains/{domain}/subdomains` | Subdomeny danej domeny |
| `GET` | `/api/v1/demo/{domain}/suppliers` | Demo dostawcy (domena) |
| `GET` | `/api/v1/demo/{domain}/demand` | Demo popyt (domena) |
| `GET` | `/api/v1/demo/{domain}/labels` | Etykiety produktów i regionów |
| `GET` | `/api/v1/demo/{domain}/{subdomain}/suppliers` | Demo dostawcy (subdomena) |
| `GET` | `/api/v1/demo/{domain}/{subdomain}/demand` | Demo popyt (subdomena) |
| `GET` | `/api/v1/demo/{domain}/{subdomain}/labels` | Etykiety (subdomena) |

### 2.5 Integration — Generic RFQ API (6 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/integration/rfq/import` | Import RFQ + opcjonalna auto-optymalizacja |
| `POST` | `/api/v1/integration/rfq/export` | Eksport wyniku w formacie GENERIC-RFQ-JSON |
| `GET` | `/api/v1/integration/status` | Health-check konektywności RFQ |
| `POST` | `/api/v1/integration/webhook` | Webhook: rfq.created, bid.received, rfq.closed |
| `GET` | `/api/v1/integration/rfq/demo` | Generowanie demo RFQ (5 pozycji, 4 oferty) |
| `GET` | `/api/v1/integration/rfq/{rfq_id}` | Pobranie zapisanego RFQ |

**Kluczowa cecha v3.1:** 100% vendor-agnostic — zero referencji do SAP/Ariba. Kompatybilne z dowolnym systemem sourcingowym.

### 2.6 Risk Engine (6 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/risk/heatmap` | Risk heatmap z wyniku optymalizacji |
| `GET` | `/api/v1/risk/heatmap/demo` | Demo risk heatmap |
| `POST` | `/api/v1/risk/monte-carlo` | Symulacja Monte Carlo (N iteracji) |
| `GET` | `/api/v1/risk/monte-carlo/demo` | Demo Monte Carlo (500 iteracji) |
| `POST` | `/api/v1/risk/negotiation` | Analiza celów negocjacyjnych |
| `GET` | `/api/v1/risk/negotiation/demo` | Demo cele negocjacyjne |

### 2.7 Process Mining (9 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/process-mining/dfg` | Directly-Follows Graph z event logu |
| `POST` | `/api/v1/process-mining/lead-times` | Lead-times między aktywnościami |
| `POST` | `/api/v1/process-mining/bottlenecks` | Detekcja bottlenecków |
| `POST` | `/api/v1/process-mining/variants` | Analiza wariantów procesowych |
| `GET` | `/api/v1/process-mining/demo/dfg` | Demo DFG |
| `GET` | `/api/v1/process-mining/demo/lead-times` | Demo lead-times |
| `GET` | `/api/v1/process-mining/demo/bottlenecks` | Demo bottlenecki |
| `GET` | `/api/v1/process-mining/demo/variants` | Demo warianty |
| `GET` | `/api/v1/process-mining/demo/events` | Demo event log P2P (10 case'ów) |

### 2.8 Process Digging (16 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/process-digging/dfg` | Frequency DFG |
| `POST` | `/api/v1/process-digging/lead-times` | Lead-times |
| `POST` | `/api/v1/process-digging/bottlenecks` | Bottlenecki |
| `POST` | `/api/v1/process-digging/variants` | Warianty |
| `POST` | `/api/v1/process-digging/anomalies` | Anomalie statystyczne (z-score) |
| `POST` | `/api/v1/process-digging/conformance` | Conformance check vs referencja |
| `POST` | `/api/v1/process-digging/rework` | Detekcja reworku / pętli |
| `POST` | `/api/v1/process-digging/handovers` | Social network — przekazania zasobów |
| `POST` | `/api/v1/process-digging/performance-dfg` | Performance DFG (wagi = czas) |
| `POST` | `/api/v1/process-digging/sla-monitor` | Monitoring SLA vs target |
| `POST` | `/api/v1/process-digging/full-report` | Pełny raport (wszystkie analizy) |
| `GET` | `/api/v1/process-digging/demo/anomalies` | Demo anomalie |
| `GET` | `/api/v1/process-digging/demo/conformance` | Demo conformance |
| `GET` | `/api/v1/process-digging/demo/rework` | Demo rework |
| `GET` | `/api/v1/process-digging/demo/handovers` | Demo handovers |
| `GET` | `/api/v1/process-digging/demo/performance-dfg` | Demo performance DFG |
| `GET` | `/api/v1/process-digging/demo/sla-monitor` | Demo SLA monitor |
| `GET` | `/api/v1/process-digging/demo/full-report` | Demo pełny raport |

### 2.9 What-If & Alerts (5 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `POST` | `/api/v1/whatif/scenarios` | 2-10 scenariuszy porównawczych |
| `GET` | `/api/v1/whatif/scenarios/demo` | Demo: Baseline vs Tight Budget vs Green Focus |
| `POST` | `/api/v1/whatif/alerts` | Alerty z wyniku optymalizacji |
| `POST` | `/api/v1/whatif/alerts/process` | Alerty z event logu P2P |
| `GET` | `/api/v1/whatif/alerts/demo` | Demo alerty (optymalizacja + process) |

### 2.10 Database (14 endpointów)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `GET` | `/api/v1/db/status` | Sprawdzenie dostępności bazy |
| `POST` | `/api/v1/db/seed/{domain}` | Seed danych demo do bazy |
| `POST` | `/api/v1/db/seed-p2p` | Seed zdarzeń P2P do bazy |
| `GET` | `/api/v1/db/suppliers` | Pobranie dostawców z bazy |
| `POST` | `/api/v1/db/suppliers/upload` | Upload dostawców CSV/XLSX |
| `DELETE` | `/api/v1/db/suppliers` | Usunięcie dostawców domeny |
| `GET` | `/api/v1/db/demand` | Pobranie popytu z bazy |
| `POST` | `/api/v1/db/demand/upload` | Upload popytu CSV/XLSX |
| `DELETE` | `/api/v1/db/demand` | Usunięcie popytu domeny |
| `GET` | `/api/v1/db/results` | Lista wyników optymalizacji |
| `GET` | `/api/v1/db/results/{result_id}` | Szczegóły wyniku |
| `GET` | `/api/v1/db/p2p-events` | Pobranie zdarzeń P2P |
| `POST` | `/api/v1/db/p2p-events/upload` | Upload zdarzeń P2P CSV/XLSX |
| `DELETE` | `/api/v1/db/p2p-events` | Usunięcie zdarzeń P2P |
| `GET` | `/api/v1/db/p2p-events/datasets` | Lista datasetów P2P |

### 2.11 Utility (4 endpointy)

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `GET` | `/health` | Health check + wersja |
| `POST` | `/api/v1/stealth` | Stealth mode — surowe diagnostyki solvera |
| `GET` | `/api/v1/stealth/demo` | Demo stealth |
| `GET` | `/api/v1/weights/defaults` | Aktualne wagi domyślne |
| `PUT` | `/api/v1/weights/defaults` | Zmiana wag w runtime |

---

## 3. 10 Domen Procurement

### 3.1 Domeny DIRECT (6)

| # | Domena | Label PL | Subdomeny |
|---|--------|----------|-----------|
| 1 | `parts` | Części zamienne | `brake_systems`, `filters`, `suspension` |
| 2 | `oe_components` | Komponenty OE | `engine_parts`, `electrical`, `transmission` |
| 3 | `oils` | Oleje i płyny | `engine_oils`, `transmission_fluids` |
| 4 | `batteries` | Akumulatory | `starter_batteries`, `agm_efb` |
| 5 | `tires` | Opony | `summer_tires`, `winter_tires`, `all_season` |
| 6 | `bodywork` | Nadwozia i oświetlenie | `body_panels`, `lighting`, `glass` |

### 3.2 Domeny INDIRECT (4)

| # | Domena | Label PL | Subdomeny |
|---|--------|----------|-----------|
| 7 | `it_services` | Usługi IT | `development`, `cloud_infra`, `data_analytics` |
| 8 | `logistics` | Logistyka | `domestic`, `international`, `last_mile` |
| 9 | `packaging` | Opakowania | `cardboard`, `plastics` |
| 10 | `facility_management` | Zarządzanie obiektem | `maintenance`, `safety_equipment`, `cleaning` |

### 3.3 Struktura danych per subdomena

Każda subdomena zawiera:
- **3-5 dostawców** z pełnym profilem (koszt, logistyka, lead-time, compliance, ESG, pojemność, regiony, warunki płatności)
- **3-4 produkty** z popytem i regionem docelowym
- **Etykiety** produktów i regionów (PL)

### 3.4 Wagi domyślne per domena

| Domena | w_cost | w_time | w_compliance | w_esg |
|--------|--------|--------|-------------|-------|
| parts | 0.40 | 0.30 | 0.15 | 0.15 |
| oe_components | 0.35 | 0.30 | 0.20 | 0.15 |
| oils | 0.45 | 0.25 | 0.15 | 0.15 |
| batteries | 0.35 | 0.25 | 0.20 | 0.20 |
| tires | 0.35 | 0.30 | 0.15 | 0.20 |
| bodywork | 0.40 | 0.25 | 0.20 | 0.15 |
| it_services | 0.35 | 0.25 | 0.20 | 0.20 |
| logistics | 0.30 | 0.35 | 0.20 | 0.15 |
| packaging | 0.45 | 0.20 | 0.15 | 0.20 |
| facility_management | 0.40 | 0.25 | 0.20 | 0.15 |

---

## 4. Solver — Optymalizacja wielokryterialna

### 4.1 Funkcja celu

```
min  λ · Σᵢ Σⱼ (w_cost·cᵢⱼ + w_time·tᵢⱼ) · xᵢⱼ · Dⱼ
   + (1-λ) · Σᵢ Σⱼ (w_compliance·(1-compᵢ) + w_esg·(1-esgᵢ)) · xᵢⱼ · Dⱼ
```

Gdzie:
- `xᵢⱼ` — frakcja popytu produktu j realizowana przez dostawcę i
- `Dⱼ` — popyt na produkt j
- `λ` — trade-off koszt vs jakość (0–1)
- `cᵢⱼ` — koszt jednostkowy + logistyka (znormalizowane)
- `tᵢⱼ` — lead-time (znormalizowane)
- `compᵢ` — compliance score dostawcy i (0–1)
- `esgᵢ` — ESG score dostawcy i (0–1)

### 4.2 Tryby solvera

| Tryb | Solver | Zmienne | Opis |
|------|--------|---------|------|
| `continuous` | SciPy linprog + HiGHS | `xᵢⱼ ∈ [0, 1]` | LP ciągłe — split zamówień |
| `binary` | PuLP + HiGHS MIP | `yᵢ ∈ {0,1}`, `xᵢⱼ ∈ [0,1]` | MIP — wybór dostawców binarny |

---

## 5. Constrainty solvera (C1–C15)

### 5.1 Constrainty bazowe (C1–C5)

| ID | Nazwa | Opis | Typ |
|----|-------|------|-----|
| C1 | Demand fulfillment | `Σᵢ xᵢⱼ = 1` dla każdego produktu j | Equality |
| C2 | Capacity limits | `Σⱼ xᵢⱼ · Dⱼ ≤ capacityᵢ` | Upper bound |
| C3 | Min order quantity | `xᵢⱼ · Dⱼ ≥ MOQᵢ` (jeśli xᵢⱼ > 0) | Conditional |
| C4 | Non-negativity | `xᵢⱼ ≥ 0` | Bound |
| C5 | Max vendor share | `Σⱼ xᵢⱼ · Dⱼ ≤ max_share · Q_total` | Diversification |

### 5.2 Constrainty rozszerzone (C10–C15) — NOWE w v3.0+

| ID | Nazwa | Opis | LP | MIP |
|----|-------|------|----|-----|
| C10 | Min supplier count | Minimum N aktywnych dostawców | Advisory (soft) | Hard: `Σ yᵢ ≥ N` |
| C11 | Geographic diversity | Min 1 dostawca z każdego wymaganego regionu | `Σᵢ∈region xᵢⱼ ≥ ε` | Binary region vars |
| C12 | ESG floor | Średni ważony ESG ≥ próg | `Σ esgᵢ·xᵢⱼ·Dⱼ ≥ min_esg · Q_total` | Hard constraint |
| C13 | Payment terms cap | Średnie ważone warunki płatności ≤ limit | `Σ payᵢ·xᵢⱼ·Dⱼ ≤ max_days · Q_total` | Hard constraint |
| C14 | Contract lock-in | Gwarantowana minimalna alokacja | `bounds[i,j] ≥ contract_min` | `Σⱼ xᵢⱼ ≥ 1` (locked) |
| C15 | Preferred supplier bonus | Redukcja kosztu obiektywnego dla preferowanych | `cᵢⱼ *= (1 - bonus)` | Coefficient adjust |

### 5.3 Domyślne wartości constraintów

```python
default_min_supplier_count = 2
default_min_esg_score = 0.70
default_max_payment_terms_days = 60.0
default_preferred_supplier_bonus = 0.05
default_max_vendor_share = 0.60  # max 60% wolumenu na dostawcę
```

---

## 6. Integracja RFQ — Generic Open API

### 6.1 Architektura

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

### 6.2 Model RFQ

**RfqHeader:**
- `rfq_id` — unikalny identyfikator
- `title` — tytuł zapytania
- `procurement_domain` — domena (parts, tires, etc.)
- `buyer_org` — organizacja kupująca
- `created_at`, `deadline` — daty
- `currency` — waluta (PLN)
- `status` — draft | active | closed | awarded
- `line_items[]` — pozycje RFQ
- `bids[]` — oferty dostawców

**RfqLineItem:**
- `line_item_id`, `material_number`, `description`
- `quantity`, `unit_of_measure`
- `required_delivery_date`
- `destination_region`, `destination_plant`

**RfqSupplierBid:**
- `supplier_id`, `supplier_name`
- `bid_unit_price`, `bid_logistics_cost`
- `lead_time_days`, `compliance_score`, `esg_score`
- `payment_terms_days`, `capacity`
- `regions_served[]`

### 6.3 Flow importu RFQ

1. `POST /integration/rfq/import` z body `{rfq, auto_optimize, optimization_mode}`
2. RFQ zapisywany w in-memory store
3. Jeśli `auto_optimize=true`:
   - Bids → `SupplierInput[]` (via `RfqTransformer`)
   - Line items → `DemandItem[]`
   - Uruchomienie LP/MIP solvera
   - Wynik alokacji zwracany w response
4. Eksport: `POST /integration/rfq/export` → `RfqExportRow[]` (format: `GENERIC-RFQ-JSON`)

### 6.4 Webhook events

| Event | Opis |
|-------|------|
| `rfq.created` | Nowe RFQ zarejestrowane |
| `bid.received` | Nowa oferta od dostawcy |
| `rfq.closed` | RFQ zamknięte (oznaczane w store) |

### 6.5 Vendor-agnostic

v3.1 nie zawiera **żadnych** referencji do SAP, Ariba ani żadnego konkretnego systemu ERP/sourcingowego. API jest w pełni generyczne i kompatybilne z:
- SAP Ariba, Coupa, Jaggaer, Oracle Procurement Cloud
- Dowolnym systemem z REST API
- Customowymi integracjami klienta

---

## 7. Risk Engine

### 7.1 Risk Heatmap

**Composite risk score** per para (dostawca × produkt):

```
risk = 0.4 × single_source_risk + 0.3 × capacity_utilization_risk + 0.3 × esg_risk
```

| Label | Zakres | Kolor |
|-------|--------|-------|
| `low` | < 0.25 | Zielony |
| `medium` | 0.25 – 0.49 | Żółty |
| `high` | 0.50 – 0.74 | Czerwony |
| `critical` | ≥ 0.75 | Fioletowy |

### 7.2 Monte Carlo Simulation

- **N iteracji** (domyślnie 1000, demo 500)
- Perturbacja kosztów: rozkład log-normalny z `σ = cost_std_pct` (domyślnie 10%)
- Perturbacja czasów: rozkład log-normalny z `σ = time_std_pct` (domyślnie 15%)
- Każda iteracja: pełne uruchomienie solvera LP
- **Wyniki:**
  - `cost_mean_pln`, `cost_std_pln`
  - `cost_p5_pln`, `cost_p95_pln` (przedział ufności 90%)
  - `robustness_score` — % iteracji feasible
  - `supplier_stability{}` — % iteracji w których dostawca jest wybrany
  - `cost_histogram[]` — bins do wizualizacji

### 7.3 Negotiation Assistant

Analiza celów negocjacyjnych na podstawie alokacji:

| Priorytet | Kryteria |
|-----------|----------|
| **High** | Udział > 30% AND koszt > mediany |
| **Medium** | Udział > 15% OR koszt w top quartile |
| **Low** | Pozostałe |

Wyniki: `target_reduction_pct`, `estimated_savings_pln`, `recommended_action`

---

## 8. Process Mining & Digging

### 8.1 Process Mining (bazowy)

| Analiza | Opis |
|---------|------|
| DFG | Directly-Follows Graph — mapa przepływu procesu P2P |
| Lead-times | Czasy przejść między aktywnościami |
| Bottlenecks | Detekcja wąskich gardeł (max czasy) |
| Variants | Analiza wariantów ścieżek procesowych |

### 8.2 Process Digging (zaawansowany — 10 analiz)

| # | Analiza | Opis |
|---|---------|------|
| 1 | Frequency DFG | Mapa częstotliwości przejść |
| 2 | Lead-times | Statystyki czasów per przejście |
| 3 | Bottlenecks | Identyfikacja wąskich gardeł |
| 4 | Variants | Warianty procesowe z częstotliwością |
| 5 | Anomalies | Anomalie statystyczne (z-score > próg) |
| 6 | Conformance | Porównanie z referencyjną ścieżką P2P |
| 7 | Rework | Detekcja pętli i powtórzeń aktywności |
| 8 | Handovers | Analiza sieci społecznej — przekazania między zasobami |
| 9 | Performance DFG | DFG z wagami = czasy przejść |
| 10 | SLA Monitor | Porównanie case'ów vs target SLA |

### 8.3 Full Report

`POST /process-digging/full-report` — uruchamia wszystkie 10 analiz jednocześnie i zwraca zbiorczy raport.

---

## 9. What-If & Alerts

### 9.1 What-If Scenarios

- Definiowanie 2-10 scenariuszy z różnymi wagami / parametrami
- Równoległe uruchamianie solvera
- Porównanie wyników: koszt, jakość, liczba dostawców, vendor share

**Demo scenariusze:**
1. **Baseline** — domyślne wagi
2. **Tight Budget** — `w_cost=0.70`
3. **Green Focus** — `w_esg=0.50`

### 9.2 Alerts Engine

**Typy alertów optymalizacji:**
- Single-source risk (dostawca > 80% wolumenu)
- Low ESG score (< próg)
- High lead-time
- Capacity utilization > 90%
- Vendor concentration

**Typy alertów procesowych:**
- Long-running cases (> SLA)
- Rework detected
- Non-conformant paths
- Bottleneck activities

---

## 10. Frontend — 5-tabowy Dashboard

### 10.1 Struktura tabów

| Tab | Nazwa | Zawartość |
|-----|-------|-----------|
| 1 | **Optimization** | Solver, Pareto, XY Scatter, Sankey, Donut, Constrainty |
| 2 | **Process Mining** | DFG (Cytoscape.js), warianty, bottlenecki |
| 3 | **What-If** | Scenariusze porównawcze, trend cross-domain |
| 4 | **Alerts** | Alerty optymalizacji + procesowe |
| 5 | **Risk** | Heatmap, Monte Carlo histogram, supplier stability, negotiation |

### 10.2 Wykresy i wizualizacje

| Wykres | Technologia | Tab | Opis |
|--------|------------|-----|------|
| Pareto Front | Chart.js line | 1 | Trade-off λ vs objective |
| XY Pareto Scatter | Chart.js scatter | 1 | Koszt PLN (X) vs jakość (Y) |
| Supplier Radar | Chart.js radar | 1 | Profile dostawców (4 wymiary) |
| Allocation Bar | Chart.js stacked bar | 1 | Alokacja per produkt |
| Sankey Diagram | Vanilla SVG | 1 | Przepływy dostawca → produkt |
| Cost Donut | Chart.js doughnut | 1 | Rozkład kosztów per dostawca |
| DFG Graph | Cytoscape.js | 2 | Directed graph P2P |
| Scenario Comparison | Chart.js grouped bar | 3 | Porównanie scenariuszy |
| Cross-domain Trend | Chart.js stacked bar | 3 | Trendy per domena |
| Risk Heatmap | HTML table + CSS | 5 | Dostawca × produkt (kolorowane) |
| MC Histogram | Chart.js bar | 5 | Rozkład kosztów Monte Carlo |
| Supplier Stability | Chart.js horizontal bar | 5 | % stabilności per dostawca |
| Negotiation Table | HTML table | 5 | Cele negocjacyjne z priorytetami |

### 10.3 Interakcje

- **Domain buttons** — 10 przycisków, automatyczna zmiana wag i danych
- **Subdomain selector** — dropdown pod domain buttons
- **Lambda slider** — regulacja trade-off koszt/jakość
- **Weight sliders** — 4 suwaki (cost, time, compliance, ESG)
- **Constraint inputs** — min suppliers, ESG floor, max payment terms
- **Mode toggle** — continuous / binary
- **Pareto steps** — liczba punktów Pareto (3-25)

---

## 11. Baza danych (opcjonalna)

### 11.1 Turso / libSQL

- Połączenie via HTTP API (env: `INTERCARS_TURSO_DATABASE_URL`, `INTERCARS_TURSO_AUTH_TOKEN`)
- Aplikacja działa bez bazy — fallback na dane demo
- Tabele: `suppliers`, `demand`, `optimization_results`, `p2p_events`

### 11.2 Upload danych

- **CSV / XLSX** upload dostawców, popytu i zdarzeń P2P
- Automatyczne parsowanie via `openpyxl` + `python-multipart`
- Walidacja schematów Pydantic po parsowaniu

---

## 12. Konfiguracja (env vars)

Wszystkie parametry overridable via zmienne środowiskowe z prefixem `INTERCARS_`:

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `INTERCARS_DEFAULT_SOLVER_MODE` | `continuous` | Tryb solvera |
| `INTERCARS_DEFAULT_PARETO_STEPS` | `11` | Punkty Pareto |
| `INTERCARS_DEFAULT_LAMBDA` | `0.5` | Trade-off koszt/jakość |
| `INTERCARS_DEFAULT_W_COST` | `0.40` | Waga kosztu |
| `INTERCARS_DEFAULT_W_TIME` | `0.30` | Waga czasu |
| `INTERCARS_DEFAULT_W_COMPLIANCE` | `0.15` | Waga compliance |
| `INTERCARS_DEFAULT_W_ESG` | `0.15` | Waga ESG |
| `INTERCARS_DIVERSIFICATION_ENABLED` | `True` | Vendor diversification |
| `INTERCARS_DEFAULT_MAX_VENDOR_SHARE` | `0.60` | Max udział dostawcy |
| `INTERCARS_DEFAULT_MIN_SUPPLIER_COUNT` | `2` | Min dostawców (C10) |
| `INTERCARS_DEFAULT_MIN_ESG_SCORE` | `0.70` | Min ESG (C12) |
| `INTERCARS_DEFAULT_MAX_PAYMENT_TERMS_DAYS` | `60.0` | Max warunki płatności (C13) |
| `INTERCARS_DEFAULT_PREFERRED_SUPPLIER_BONUS` | `0.05` | Bonus preferowany (C15) |
| `INTERCARS_RFQ_IMPORT_URL` | `https://rfq.intercars.eu/api/v1/import` | URL importu RFQ |
| `INTERCARS_RFQ_EXPORT_URL` | `https://rfq.intercars.eu/api/v1/export` | URL eksportu RFQ |
| `INTERCARS_RFQ_IMPORT_API_KEY` | `""` | Klucz API importu |
| `INTERCARS_RFQ_EXPORT_API_KEY` | `""` | Klucz API eksportu |
| `INTERCARS_WEBHOOK_SECRET` | `""` | Secret webhooka |
| `INTERCARS_MONTE_CARLO_ITERATIONS` | `1000` | Iteracji MC |
| `INTERCARS_MONTE_CARLO_COST_STD_PCT` | `0.10` | Odch. kosztu MC |
| `INTERCARS_MONTE_CARLO_TIME_STD_PCT` | `0.15` | Odch. czasu MC |
| `INTERCARS_SOLVER_TIME_LIMIT_SECONDS` | `60.0` | Limit czasu solvera |
| `INTERCARS_MIP_GAP_TOLERANCE` | `1e-4` | MIP gap |
| `INTERCARS_DEFAULT_SLA_TARGET_HOURS` | `120.0` | SLA target (5 dni) |
| `INTERCARS_DEFAULT_ANOMALY_Z_THRESHOLD` | `2.0` | Z-score anomalii |
| `INTERCARS_TURSO_DATABASE_URL` | `None` | URL bazy Turso |
| `INTERCARS_TURSO_AUTH_TOKEN` | `None` | Token bazy Turso |

---

## 13. API Documentation

- **OpenAPI/Swagger UI:** `https://<host>/docs`
- **ReDoc:** `https://<host>/redoc`
- **OpenAPI JSON:** `https://<host>/openapi.json`
- **Frontend UI:** `https://<host>/ui`

Automatycznie generowana dokumentacja OpenAPI 3.1 ze schematami Pydantic, przykładami i opisami.

---

## 14. Historia wersji

| Wersja | Data | Endpointy | Kluczowe zmiany |
|--------|------|-----------|-----------------|
| 1.0.0 | — | ~10 | MVP: LP solver, 1 domena (parts) |
| 2.0.0 | — | ~30 | 8 domen, Process Mining, MIP solver |
| 2.4.0 | — | 53 | Process Digging Engine (10 analiz), dedykowany MIP |
| 2.5.0 | — | 68 | What-If, Alerts Engine, DFG Cytoscape, 4-tab UI |
| 3.0.0 | — | 86 | 10 domen+27 subdomen, C10-C15, Risk Engine, Monte Carlo, 5-tab UI |
| **3.1.0** | **2026-03-06** | **86** | **Generic RFQ API (vendor-agnostic), zero SAP/Ariba** |

---

## 15. Podsumowanie v3.1.0

| Metryka | Wartość |
|---------|---------|
| Endpointy API | **86** |
| Domeny procurement | **10** (6 direct + 4 indirect) |
| Subdomeny | **27** |
| Constrainty solvera | **11** (C1-C5 + C10-C15) |
| Analizy Process Mining | **4** (bazowe) |
| Analizy Process Digging | **10** (zaawansowane) |
| Wizualizacje dashboard | **13** typów wykresów |
| Taby UI | **5** |
| Pliki Python | **23** |
| Linii kodu | **10 402** |
| Zależności pip | **12** |
| Zewnętrzne zależności vendorowe | **0** (vendor-agnostic) |
