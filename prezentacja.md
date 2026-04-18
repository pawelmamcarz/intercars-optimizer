# Flow Procurement Platform
## Prezentacja dla klienta — pełen opis funkcjonalności

**Wersja platformy:** v2026.16.1.0 (Tesla-style: YYYY.WW.BUILD.PATCH)
**Data:** 2026-04-17
**Domena produkcyjna:** `flowprocurement.com` (uruchamiana) · `flow-procurement.up.railway.app`
**Repo:** `github.com/pawelmamcarz/flow-procurement`

---

## Spis treści

1. [Executive summary](#1-executive-summary)
2. [Problem biznesowy i nasza odpowiedź](#2-problem-biznesowy-i-nasza-odpowiedź)
3. [Korzyści biznesowe — liczby](#3-korzyści-biznesowe--liczby)
4. [Architektura w pigułce](#4-architektura-w-pigułce)
5. [AI Copilot — serce platformy](#5-ai-copilot--serce-platformy)
6. [Wizard kupca — 6 kroków od zapotrzebowania do dostawy](#6-wizard-kupca--6-kroków)
7. [Portal dostawcy](#7-portal-dostawcy)
8. [Backoffice admina](#8-backoffice-admina)
9. [Superadmin — zarządzanie platformą](#9-superadmin)
10. [Silnik optymalizacyjny](#10-silnik-optymalizacyjny)
11. [Supplier Scorecard 5D](#11-supplier-scorecard-5d)
12. [Zarządzanie kontraktami](#12-zarządzanie-kontraktami)
13. [Aukcje odwrotne + Marketplace](#13-aukcje-odwrotne--marketplace)
14. [Risk, Prediction, OSINT](#14-risk-prediction-osint)
15. [Konektory BI / ERP / WMS](#15-konektory-bi--erp--wms)
16. [Document ingestion](#16-document-ingestion)
17. [Process Mining](#17-process-mining)
18. [Projekty zakupowe](#18-projekty-zakupowe)
19. [Integracja RFQ + EWM](#19-integracja-rfq--ewm)
20. [Multi-tenant SaaS + Auth](#20-multi-tenant-saas--auth)
21. [Observability + Security](#21-observability--security)
22. [Stack technologiczny](#22-stack-technologiczny)
23. [Baza danych (14 tabel)](#23-baza-danych)
24. [API — ~243 endpointy](#24-api--243-endpointy)
25. [CI/CD + DevOps](#25-cicd--devops)
26. [Konta demo](#26-konta-demo)
27. [Mapa skalowania i roadmap](#27-skalowanie-i-roadmap)
28. [Scenariusze demo dla klienta](#28-scenariusze-demo)

---

## 1. Executive summary

**Flow Procurement** to platforma typu _AI-first e-sourcing suite_, która zamienia tradycyjny proces zakupowy (email → Excel → ręczna decyzja → SAP) na jeden wizard z asystentem AI prowadzącym kupca od zapotrzebowania, przez wybór dostawców, optymalizację wielokryterialną, aż po wystawienie zamówienia i monitoring realizacji.

**Co wyróżnia:**
- **AI Copilot pełnopanelowy** — zajmuje ~45% dashboardu, pisze się do niego naturalnym językiem („dodaj 3 klocki Bosch do koszyka", „optymalizuj z wagą ESG 30%"), obsługuje wklejone maile/PDF-y i proponuje proaktywne karty akcji.
- **Matematyczny silnik decyzyjny** — HiGHS LP + PuLP MIP, 15+ constraintów (C1–C15b), front Pareto, Monte Carlo (1000× iteracji), shadow prices, scenario chaining, agregacja subdomenowa.
- **Multi-tenant SaaS** — jedna instancja obsługuje wielu klientów z izolacją danych na poziomie bazy (Turso libSQL, 14 tabel, `tenant_id` w każdej).
- **Procurement end-to-end** — katalog, RFQ, aukcje odwrotne, kontrakty, scorecard dostawców, spend analytics, process mining, alerty predykcyjne, OSINT (KRS/CEIDG/VIES).
- **Gotowy do integracji** — 5 adapterów BI/ERP/WMS z interfejsem `BIConnector` (mock→real), cXML PunchOut, Allegro OAuth, webhook-based RFQ export/import.

**Skala:**
- **~243 endpointy REST** `/api/v1/*`
- **55 modułów Python / ~24 500 LOC**
- **10 domen zakupowych × 27 subdomen** (6 Direct + 4 Indirect)
- **14 tabel w Turso (libSQL)** z pełną izolacją tenantów
- **160 testów automatycznych** (157 unit/integration + 3 Playwright E2E)
- **3 workflowy CI** (ci.yml, post-deploy.yml, nightly-smoke.yml) + k6 load test jako PR gate

---

## 2. Problem biznesowy i nasza odpowiedź

### Przed platformą

Typowy proces zakupowy w firmie dystrybucyjnej lub produkcyjnej:

1. Dział operacji wysyła mailem listę potrzeb do kupca.
2. Kupiec kopiuje do Excela, ręcznie pyta 3–5 dostawców o wyceny.
3. Porównuje oferty w tabeli — tylko cena, bez uwzględnienia terminów, ESG, kontraktów, rozproszenia ryzyka.
4. Decyzja heurystyczna („Bosch zawsze najszybszy, więc weźmiemy od nich"), zamówienie w SAP.
5. Po dostawie — brak systemowego monitorowania jakości, lead-time slippage, koncentracji ryzyka u jednego dostawcy.

**Koszty tego modelu:**
- 5–15% nadpłat ukrytych w „wygodnych" decyzjach kupca.
- Ryzyko uzależnienia od jednego dostawcy (widzimy często 80–100% spend w jednej ręce).
- Brak audytu **dlaczego** dokonano danego wyboru (compliance).
- Kontrakty wygasające bez alertu → renegocjacje pod presją czasu.
- „Indirect spend" (IT, logistyka, facility) poza kontrolą — wyciek 10–20% budżetu.

### Flow Procurement

**Jeden ekran, jeden asystent, matematyczny optymalizator w tle.**

Kupiec wkleja email od operacji → AI wyciąga produkty i ilości → system sugeruje dostawców z katalogu → solver dobiera alokację wg wybranych wag (cena/czas/ESG/compliance) z 15+ constraintami → kupiec widzi front Pareto i Monte Carlo confidence fan → zatwierdza → zamówienie idzie do approval workflow → po realizacji process mining pokazuje wąskie gardła.

Wszystko z pełnym audit logiem: kto/kiedy/jakie wagi/jakie constrainty/jaki wynik.

---

## 3. Korzyści biznesowe — liczby

| Wymiar | Efekt | Mechanizm |
|--------|-------|-----------|
| **Oszczędności na spend** | 3–8% portfelu rocznie | Front Pareto + relaxacja „sweet-spotu" (λ≈0.5–0.7) + shadow prices pokazujące, który constraint kosztuje ile |
| **Redukcja koncentracji ryzyka** | Max 60% udziału u 1 dostawcy (C5) | Constraint dywersyfikacji + karta proaktywna „Inter Cars ma 100% spendu" |
| **Czas kupca na RFQ** | Z 2–4 godzin do 10–20 minut | Document ingestion (AI wyciąga produkty z maila/PDF) + catalog matching |
| **Renegocjacje kontraktów** | 100% pokrycie alertem 90 dni przed wygaśnięciem | Recommendation Engine R1 (contract_expiry) |
| **Compliance audit** | Pełny audit log per decyzja | Baza DB + JSON log lines + Sentry |
| **ESG raportowanie** | Scoring 0–100 per dostawca automatycznie | Supplier Scorecard 5D + mocked BI anomaly detection |
| **Visibility na Indirect spend** | Osobny tracking Direct vs Indirect | Taxonomy 10 domen × 27 subdomen + spend analytics |
| **Time-to-market nowego klienta** | <1 dzień | Multi-tenant: superadmin tworzy nowy tenant + seeduje demo data |

---

## 4. Architektura w pigułce

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (3 portale SPA)                            │
│  /ui                       │  /admin-ui           │  /portal-ui          │
│  Wizard kupca 6-step +     │  Katalog, reguły,    │  Dashboard dostawcy, │
│  pełnopanelowy AI Copilot  │  workflows, userzy   │  RFQ, oferty, aukcje │
│  12 ES modules · 4 CSS · Chart.js + Cytoscape.js                         │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ REST JSON + WebSocket (roadmap)
┌──────────────────────────────────▼───────────────────────────────────────┐
│                  FastAPI REST API — ~243 endpointów                      │
│                                                                          │
│  ┌────────┬─────────┬────────┬────────┬────────┬──────────┐              │
│  │ /buying│/optimize│/auction│/copilot│/admin  │/portal   │              │
│  │ (~25)  │ (~15)   │ (~11)  │ (~5)   │(~12)   │(~10)     │              │
│  ├────────┼─────────┼────────┼────────┼────────┼──────────┤              │
│  │ /bi    │/prediction│/risk │/market │/ewm    │/auth     │              │
│  │ (~8)   │ (~4)    │ (~5)   │ (~8)   │(~6)    │(~5)      │              │
│  ├────────┼─────────┼────────┼────────┼────────┼──────────┤              │
│  │/process│/whatif  │/mip    │/project│/digging│/superadmin│             │
│  │(~10)   │ (~3)    │ (~4)   │ (~5)   │(~10)   │ (~7)     │              │
│  └────────┴─────────┴────────┴────────┴────────┴──────────┘              │
│                                                                          │
│  Middleware: CORS · SecurityHeaders · Observability (X-Request-ID)       │
│             · TenantContext · RateLimit                                  │
└──────┬───────────┬─────────────┬──────────────┬──────────────────────────┘
       │           │             │              │
┌──────▼─────┐ ┌──▼────────┐ ┌──▼─────────┐ ┌──▼────────────────────────┐
│ Optimizer  │ │ AI Engine │ │  Turso DB   │ │   BI Connector Layer     │
│ HiGHS LP   │ │ Haiku 4.5 │ │  (libSQL)   │ │   ERP · BI · CRM · FIN  │
│ PuLP MIP   │ │ Sonnet4.6 │ │  14 tabel   │ │   · WMS (mock + iface)  │
│ Pareto+MC  │ │ Gemini FB │ │ aws-eu-west │ │                          │
└────────────┘ │ DocParser │ └─────────────┘ └──────────────────────────┘
               │ OCR/PDF   │
               └───────────┘
```

### Cztery warstwy aplikacji

1. **Data Layer** — Turso libSQL (14 tabel), katalog UNSPSC 8-cyfrowy, upload CSV/XLSX/CIF/PDF/DOCX/EML.
2. **AI Layer** — Claude Haiku 4.5 (szybkie intent matching, ~0.002 PLN/zapytanie) / Sonnet 4.6 (reasoning, ~0.03 PLN) / Gemini 2.0 Flash (fallback). Document extraction, catalog matching.
3. **Optimization Layer** — HiGHS (continuous LP via `scipy.optimize.linprog`) + PuLP (MIP, binary), Monte Carlo, Pareto front, shadow prices, What-If scenario chaining, subdomain aggregation.
4. **Decision Layer** — REST API (~243 endpointy) + 3 portale SPA + AI Assistant jako główny interfejs.

---

## 5. AI Copilot — serce platformy

**Status:** ⚠️ Partial — Regex intent routing + LLM fallback + document ingestion ✅. Proactive action cards ⚠️ — `dispatchActionCard()` nie ma pełnej logiki dla wszystkich `action_type` (np. `navigate_to_supplier_filter` nie działa).

Asystent nie jest „chatbotem w rogu" — zajmuje **~45% szerokości dashboardu** (Step 0). Kupiec pisze naturalnym językiem, Copilot wykonuje akcje w interfejsie (dodaje do koszyka, przełącza krok, ustawia wagi solvera, uruchamia optymalizację).

### Intent routing — regex pierwszy, LLM fallback

```
Wiadomość kupca
    │
    ├─► Regex intent match ─────────── 0 ms, 0 PLN
    │     32 wzorce: add_to_cart, navigate, optimize,
    │     set_weights, filter_esg, filter_region,
    │     create_auction, explain, query_best_supplier
    │
    └─► LLM fallback (gdy regex miss)
          │
          ├─► Proste pytanie ─── Claude Haiku 4.5 (~0.002 PLN)
          │     < 300 znaków, brak keywords reasoning
          │
          └─► Złożone pytanie ── Claude Sonnet 4.6 (~0.03 PLN)
                „dlaczego", „porównaj", „rekomenduj", > 300 znaków
                │
                └─► Oba fail ────── Gemini 2.0 Flash (final fallback)
```

### 7 kategorii komend

| Kategoria | Przykłady | Co robi pod spodem |
|-----------|-----------|---------------------|
| **Dodawanie do koszyka** | „dodaj 3 klocki Bosch", „wrzuc 5 filtrów oleju" | Regex → `search_catalog()` fuzzy match → `add_to_cart` action → JS mutuje `state._s1SelectedItems` |
| **Nawigacja** | „przejdź do optymalizacji", „pokaż dostawców", „krok 2" | `navigate {step: N}` → `goStep(N)` |
| **Optymalizacja** | „optymalizuj filtry olejowe", „najszybsza dostawa", „ustaw wagę ESG 30%" | `optimize` / `set_weights` actions → solver run |
| **Filtrowanie** | „tylko dostawcy z ESG > 0.80", „tylko polska" | `filter_esg`, `filter_region` |
| **Analizy** | „wyjaśnij front Pareto", „pokaż Monte Carlo" | Static explanation templates + navigate |
| **Dokumenty** | Wklejony email / upload PDF z zamówieniem | LLM extraction (Haiku) → catalog match → add_to_cart |
| **Aukcje** | „utwórz aukcję na klocki" | `create_auction` action |

### Szablony wyjaśnień (edukacja kupca)

Asystent potrafi wyjaśnić (z pełnym kontekstem w wiadomości) 5 tematów:
1. **Front Pareto** — czym jest, co to jest parametr λ, jak czytać trade-off curve.
2. **Monte Carlo** — 1000 iteracji z perturbacją, P5/P95, robustness score.
3. **DFG** — Directly-Follows Graph, wąskie gardła, kolorowanie.
4. **Allocation** — dlaczego zamówienie zostało podzielone między N dostawców, które constrainty były wiążące.
5. **Constrainty C1–C15** — demand coverage, capacity, diversification, regional, ESG floor, contract lock-in.

### Proaktywne karty akcji (5 reguł)

Na dashboardzie, po prawej stronie panelu asystenta, renderowane są karty z `RecommendationEngine`:

| Reguła | Trigger | Przykład karty |
|--------|---------|----------------|
| **R1: Contract expiry** | Kontrakt wygasa <90 dni | 📅 „Kontrakt z Bosch wygasa za 14 dni (parts, 1.8M PLN/rok). Zaplanuj renegocjacje" |
| **R2: Supplier concentration** | >70% spend u 1 dostawcy | ⚠️ „Inter Cars ma 100% spendu w parts — rozważ dywersyfikację" |
| **R3: Direct/Indirect drift** | Dominujący kind >80% | 📊 „Spend Indirect prawie zero — czy IT jest pod kontrolą?" |
| **R4: YoY anomaly** | BI anomaly >20% | 📉 „oils: spend ▼ 72% YoY — zbadaj przyczynę" |
| **R5: Single-source risk** | Produkt OE bez alternatywy | ⚠️ „2 produkty OE bez alternatywy w katalogu" |

### Document ingestion — end-to-end

```
Email / PDF / DOCX / tekst
    │
    ├─ Paste tekst ──► POST /copilot/document/extract
    │
    └─ Upload plik ──► POST /copilot/document/extract-file
                         │
                    document_parser.extract_text()
                    ├─ PDF: pypdf text layer → jeśli <50 zn. → Tesseract OCR (pol+eng)
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

Obsługuje: PDF (w tym skanowane PDF-y przez Tesseract), DOCX z tabelami, surowe emaile (.eml), TXT, CSV.

---

## 6. Wizard kupca — 6 kroków

**Status:** ⚠️ Partial — Step 0–5 renderują się poprawnie; kluczowe braki UX: Step 3→4 nie auto-populuje koszyka wynikiem solvera; Step 5 process mining filter per-supplier nie zaimplementowany.

Główny interfejs kupca (`/ui`). Cały proces od „mam zapotrzebowanie" do „zamówienie złożone + monitoring".

### Step 0 — Dashboard + AI Assistant

Ekran startowy, pełen kontekstu biznesowego:
- **KPI row** — liczba zamówień, total spend, oszczędności (last 30 dni), compliance rate.
- **Widget Spend** — wybór okresu (30/90/365/all), duży PLN number, stacked bar Direct/Indirect, top-N kategorii z paskami.
- **Widget BI Status** — 5 chipów z kolorem statusu konektorów (ERP/BI/CRM/Finance/WMS). Żółty=mock, zielony=real, czerwony=degraded.
- **Widget Taxonomy** — drzewo 10 domen × 27 subdomen z UNSPSC 8-cyfrowy.
- **AI Copilot** — pełnopanelowy po lewej, z polem tekstowym + paste area dla dokumentów.
- **Proactive action cards** — po prawej stronie Copilot, 5 reguł rekomendacji.

### Step 1 — Zapotrzebowanie

Kupiec definiuje co chce kupić:
- **UNSPSC search** — live search 8-cyfrowy (Segment → Family → Class → Commodity).
- **Direct / Indirect / Marketplace switch** — segmentacja spend.
- **Katalog produktów** — lista z filtrami (kategoria, dostawca, cena, ESG).
- **Allegro marketplace** — przeszukiwanie publicznych ofert (OAuth device_code).
- **cXML PunchOut** — integracja z katalogami SAP (np. Inter Cars API).
- **Modal detalu produktu** — specs, dostawcy alternatywni, historia cen, obraz.
- **Koszyk** — `state._s1SelectedItems` z qty editorem.

### Step 2 — Dostawcy + Supplier Scorecard

Automatyczne dopasowanie dostawców i ich ocena:
- **Auto-match** — system mapuje każdy item z koszyka na dostawców katalogowych.
- **Supplier Scorecard** — scoring 0–100 z 5 wymiarów (ESG / Compliance / Contract / Concentration / Single-source), widoczne jako Top 5 / Bottom 3.
- **Supplier detail modal** — kontakty, certyfikaty (ISO, IATF), validacja VIES/KRS, historia performance.
- **Self-assessment dostawcy** — pytania → odpowiedzi zasilają risk engine.
- **Certyfikaty** — lista z expiry tracking (90-day warning).

### Step 3 — Optymalizacja

Matematyczne serce platformy:
- **Switch domeny** — parts, oils, tires, batteries, vehicles, oe_components, it_services, logistics, packaging, facility_mgmt.
- **Suwaki wag** — λ (0–1), w_cost, w_time, w_compliance, w_esg.
- **Solver mode** — continuous (LP, HiGHS) / mip (binary, PuLP).
- **Presety wag** — cost-focused, balanced, quality-focused, esg-focused (1 click).
- **Full pipeline** — solver run + Monte Carlo (1000 iter.) + shadow prices + KPI.
- **Front Pareto** — wykres trade-off curve λ vs objective.
- **Tabela alokacji** — supplier / product / fraction / cost / time / compliance / esg. Sortowanie i filtry.
- **Shadow prices** — sensitivity per constraint (cena, capacity, compliance).
- **Create order from optimizer** — jedno kliknięcie konwertuje alokację na zamówienie (Step 4).

### Step 4 — Zamówienie

Operacyjny checkout:
- **4 widoki**: cart-review / order-builder / checkout / my-orders.
- **Cart review** — podsumowanie, auto-kalkulacja freight + tax.
- **Order builder** — grid produktów, update qty, re-run optymalizacji dla nowego koszyka.
- **Checkout modal** — wybór dostawcy, lead time, payment terms.
- **Approval workflow** — status chain: Draft → Pending → Approved → PO generated → Confirmed → Shipped → Delivered / Cancelled.
- **Audit trail** — każda akcja z timestampem, userem, notatką.
- **Akcje**: approve / generate-po / confirm / ship / deliver / cancel.
- **Create auction** — reverse auction z wybranych items (Step 4 bezpośrednio do Step F).

### Step 5 — Monitoring + Process Mining

Co się dzieje po zamówieniu:
- **Process Mining section**:
  - DFG widok (frequency / performance) renderowany w Cytoscape.js.
  - Bottleneck detection: red flag activities (np. Create Order → Receive > 30 dni).
  - Conformance rate: % traces zgodnych z happy path.
  - Top trace variants + frequency.
- **Alerts section**:
  - Alert grid z ikonami (delay / quality / capacity).
  - Probability, impact PLN, supplier.
- **Predictions section**:
  - Predictive profiles dostawców: on-time rate, avg delay, quality score.
  - Scatter chart pozycjonujący dostawców.

---

## 7. Portal dostawcy

**Status:** ✅ Production — Dashboard, profile, orders, RFQ, aukcje, certyfikaty, self-assessment wszystkie działają.

Oddzielny SPA `/portal-ui`, login przez JWT (rola `supplier`). Co widzi vendor:

| Funkcja | Endpoint | Opis |
|---------|----------|------|
| **Dashboard** | `GET /portal/dashboard` | KPI: orders, revenue, rating, outstanding RFQs |
| **Profile** | `GET/PUT /portal/me` | Dane firmowe, bank, VAT, kontakty |
| **My orders** | `GET /portal/my-orders` | Zamówienia z klienta + status |
| **Order detail** | `GET /portal/orders/{id}` | Pełne PO + line items + timeline |
| **My RFQs** | `GET /portal/my-rfqs` | Zapytania ofertowe, na które został zaproszony |
| **RFQ detail** | `GET /portal/rfqs/{id}` | Line items + deadline + wymagania |
| **Submit bid** | `POST /portal/rfqs/{id}/bid` | Złożenie oferty |
| **Certyfikaty** | `GET /portal/my-certificates` | ISO, IATF, inne cert z expiry |
| **Upload certyfikat** | `POST /portal/certificates` | Nowy dokument |
| **Expiring certs** | `GET /portal/my-certs-expiring` | 90-day warning |
| **Self-assessment** | `GET /portal/assessment-questions` + `POST /portal/assessment` | Pytania + odpowiedzi |
| **Aukcje** | `GET /auctions` + `POST /auctions/{id}/bid` | Active reverse auctions + bidowanie |

---

## 8. Backoffice admina

**Status:** ⚠️ Partial — Katalog, reguły, workflows, userzy ✅. Brakuje UI do edycji kontraktów (endpoint `/buying/contracts` istnieje, UI nie). OSINT lookup wysyłany, ale response nie parsowany.

SPA `/admin-ui`, rola `admin`. Zarządza tenantem (nie platformą):

| Funkcja | Endpointy | Opis |
|---------|-----------|------|
| **UNSPSC search** | `GET /admin/unspsc/search?q=...` | Przeszukiwanie katalogu UNSPSC |
| **D&B DUNS** | `GET /admin/duns/{duns}` | Validacja D&B numeru |
| **Katalog** | `GET/POST/DELETE /admin/catalog` | CRUD SKU |
| **Import CIF** | `POST /admin/catalog/import-cif` | Bulk upload w formacie cXML/CIF |
| **Reguły biznesowe** | `GET/POST/DELETE /admin/rules` | Progi, rabaty, ograniczenia |
| **Workflows** | `GET/POST/DELETE /admin/workflows` | Approval chain configuration |
| **Użytkownicy** | `GET/POST /admin/users` | CRUD userów w tenant, przypisanie ról |
| **Admin dashboard** | `GET /admin/dashboard` | Stats: orders, users, spend, compliance |

---

## 9. Superadmin

**Status:** ✅ Production — Zarządzanie tenantami, tworzenie, stats, seed demo users wszystkie działają.

Platform-level (rola `super_admin`). Zarządza wszystkimi tenantami:

| Funkcja | Endpointy |
|---------|-----------|
| **Lista tenantów** | `GET /tenants` |
| **Detale tenanta** | `GET /tenants/{id}` |
| **Nowy klient** | `POST /tenants` (tworzy tenant + seed demo data) |
| **Edycja** | `PUT /tenants/{id}` |
| **Dezaktywacja** | `DELETE /tenants/{id}` |
| **Userzy tenanta** | `GET /tenants/{id}/users` |
| **Platform stats** | `GET /superadmin/stats` |
| **Seed demo users** | `POST /auth/admin/seed-demo-users?reset_existing=true` |
| **Reset hasła dowolnego usera** | `POST /auth/admin/users/{username}/reset-password` |

---

## 10. Silnik optymalizacyjny

**Status:** ✅ Production — HiGHS LP + PuLP MIP, 15 constraintów (C1-C15b), Pareto front, Monte Carlo, Shadow prices, Scenario chaining, Subdomain optimization. Wszystko w pełni zaimplementowane i przetestowane.

### Funkcja celu

```
min  Σ_{i,j} [ λ·w_c·ĉ[i,j] + (1-λ)·w_t·t̂[i,j] + w_r·(1-r̂[i]) + w_e·(1-ê[i]) ] · x[i,j]
```

gdzie:
- `x[i,j]` = fracja zamówienia dostawcy `i` dla produktu `j` (continuous [0,1]) lub binary (MIP),
- `λ ∈ [0,1]` — balans cost vs time, sweeping dla Pareto,
- `w_c, w_t, w_r, w_e` — wagi cost / time / compliance / ESG (suma=1),
- `ĉ, t̂, r̂, ê` — min-max znormalizowane kryteria (po wszystkich parach `(i,j)`).

### Constrainty C1–C15b

| # | Constraint | Typ | LP | MIP | Opis biznesowy |
|---|-----------|-----|:--:|:---:|-----------------|
| C1 | Demand coverage | equality | ✅ | ✅ | Każdy produkt musi być w 100% pokryty |
| C2 | Capacity | ≤ | ✅ | ✅ | Dostawca nie przeforsowany (Σ x·D ≤ Cap) |
| C3 | Min order | bound | — | ✅ | Block if D_j < MOQ_i (all-or-nothing) |
| C4 | Regional block | bound | ✅ | ✅ | Dostawca nie obsługuje tego regionu → x=0 |
| C5 | Diversification | ≤ | ✅ | ✅ | Max α% udziału jednego dostawcy (domyślnie 60%) |
| C6–C7 | Single vendor/competency, SLA floor | MIP | — | ✅ | Dla IT services |
| C8 | Budget ceiling | MIP | — | ✅ | Total spend ≤ budżet |
| C9 | Max products/supplier | MIP | — | ✅ | Limit złożoności portfela |
| C10 | Min active suppliers | post | ⚠️ | ✅ | Min 2 dostawców w finalnej alokacji |
| C11 | Geographic diversification | ≥ ε | ✅ | ✅ | Min liczba regionów |
| C12 | ESG floor | ≥ | ✅ | ✅ | Ważona średnia ESG ≥ 0.70 |
| C13 | Payment terms | ≤ | ✅ | ✅ | Ważona średnia ≤ 60 dni |
| C14 | Contract lock-in | bound | ✅ | ✅ | Preferowany dostawca musi mieć min alokację |
| C15a | Preferred bonus | soft | ✅ | ✅ | 5% redukcja kosztu w celu dla `is_preferred=true` |
| C15b | Min preferred share | ≥ | ✅ | ✅ | Σ_preferred ≥ X% wolumenu |

### Zaawansowane capabilities

- **Front Pareto** — sweeping λ od 0 do 1 (domyślnie 11 kroków), dla każdego λ pełny run solvera, collect objective + breakdown (cost/time/compliance/esg).
- **Monte Carlo** — 1000 iteracji z random perturbation (std 10% cost, 15% time), zwraca P5/mean/P95 per λ, robustness score (stabilność wyboru dostawców).
- **Shadow prices** — LP duals z HiGHS dla każdego binding constraint — UI pokazuje „który constraint kosztuje Cię ile w celu".
- **What-If chaining** — `WhatIfEngine.compare_scenarios(scenarios: list[Scenario])` — run 2–10 scenariuszy, zwraca comparison matrix (cumulative deltas względem baseline).
- **Subdomain-level optimizer** — osobna optymalizacja per subdomena (np. brake_systems w domenie parts), potem agregacja w ramach domeny.

---

## 11. Supplier Scorecard 5D

**Status:** ✅ Production — wszystkie 5 wymiarów działa na demo data. ⚠️ Brakuje hookup do real BI signals (ERP invoices, YoY anomalies) — obecnie używa `bi_mock.py` z deterministic seed.

Kompozytowy scoring 0–100 per dostawca (5 wymiarów × 20% wagi):

| Wymiar | Źródło | Skala 0–100 |
|--------|--------|-------------|
| **ESG** | `SupplierInput.esg_score` | `esg × 100` |
| **Compliance** | `SupplierInput.compliance_score` | `compliance × 100` |
| **Contract** | `contract_engine.expiring_within()` | Active long-term=90, expiring <30d=40, no contract=55 |
| **Concentration** | `spend_map(orders)` per supplier | Share >85%=20 (krytyczne), >70%=45, <50%=90 |
| **Single-source risk** | catalog products z 1 dostawcą | 100% single-source=20, 0% single=100 |

**Endpoint**: `GET /buying/suppliers/scorecard?limit=20` — zwraca listę dostawców z per-wymiarem + composite + share %. UI Step 2 pokazuje Top 5 (zielone chipy) i Bottom 3 (czerwone).

---

## 12. Zarządzanie kontraktami

**Status:** ⚠️ Partial — Tabele `contracts` i `contract_audit` istnieją, CRUD endpointy działają. Audit log na create/update/delete kontraktu ✅ (contract_engine.py wywołuje `_audit()` → `db_append_contract_audit()`). **Braki:** (1) `contract_engine._CONTRACTS = {}` trzyma kontrakty w pamięci jako cache — DB write ma fallback, ale reads idą z cache; (2) brak linku order→contract audit (order approval dla supplier z active contract nie jest logowane w contract_audit); (3) brak UI edycji w adminie (tylko backend API).

### Model danych

```python
Contract:
  id, supplier_id, supplier_name, category,
  start_date, end_date,
  committed_volume_pln, price_lock,
  status (active|expired|terminated), notes
```

Metody: `days_to_expiry(today)`, `is_active(today)`, `expiring_within(days)`.

### Endpoints

- `GET /buying/contracts` — lista wszystkich kontraktów tenanta.
- `POST /buying/contracts` — create/upsert.
- `DELETE /buying/contracts/{id}`.
- `GET /buying/contracts/{id}/audit` — pełen audit trail (kto/kiedy/co zmienił).

### Integracje

- **Recommendation Engine R1** — automatyczna karta 90 dni przed wygaśnięciem.
- **Constraint C14** — preferowani dostawcy z aktywnym kontraktem dostają gwarantowaną alokację min.
- **Constraint C15a** — soft bonus 5% w funkcji celu.
- **Scorecard** — wymiar Contract bezpośrednio z `contract_engine`.

---

## 13. Aukcje odwrotne + Marketplace

**Status:** ⚠️ Partial — Pełny lifecycle aukcji (draft → awarded) działa, ale `_auctions` jest in-memory dict (restart = utrata). Portal dostawcy bidding ✅. **Braki:** items w UI jako JSON textarea (nie form builder); brak przycisku „Award" na Step 4 po deadline; brak WebSocket real-time (teraz polling). Allegro OAuth + cXML PunchOut ✅.

### Reverse auction engine

**Typy aukcji**:
- `reverse` — klasyczna (dostawcy zbijają cenę w dół w otwartej ramie czasowej).
- `english_reverse` — rundy (np. 3 rundy po 10 min).
- `sealed_bid` — oferty zamknięte, otwarcie po deadline.

**Status flow**:
```
draft → published → active → closing → closed → awarded
                                              → cancelled
```

**Endpointy** (11):
- `POST /auctions` — create (z RFQ lub od zera).
- `GET /auctions` — list z filtrami.
- `GET /auctions/{id}` — detail.
- `GET /auctions/{id}/ranking` — aktualne oferty rankowane.
- `GET /auctions/{id}/stats` — avg price, participation rate.
- `POST /auctions/{id}/publish|start|close|award|cancel` — lifecycle.
- `POST /auctions/{id}/bid` — supplier submits bid.

### Marketplace integrations

**Allegro** (OAuth device_code flow):
- `GET /marketplace/allegro/auth/start` — zainicjuj OAuth.
- `POST /marketplace/allegro/auth/poll` — poll za token.
- `GET /marketplace/allegro/search?q=...&limit=...&sort=...` — przeszukaj publiczne oferty.

**cXML PunchOut** (SAP integration standard):
- `POST /marketplace/punchout/setup` — start session z katalogiem dostawcy.
- `GET /marketplace/punchout/browse/{session_id}` — browse.
- `POST /marketplace/punchout/cart/{session_id}` — add item.
- `POST /marketplace/punchout/return/{session_id}` — return cart do kupca.

---

## 14. Risk, Prediction, OSINT

**Status:** ⚠️ Partial — Risk Heatmap + Monte Carlo ✅. Prediction Engine ⚠️ — tylko heurystyczny ensemble (XGBoost/RF planowany po zebraniu 1000+ historical orders). OSINT ❌ — endpoint `/supplier/{id}/osint` działa, ale UI (admin + Step 2) nie parsuje response — KRS/CEIDG/VIES/CPI fields niewidoczne dla usera. Fragile na network errors (silent fallbacks w async calls).

### Risk Heatmap Engine

`RiskHeatmapEngine.compute(suppliers, demand, allocations)` → heatmapa dostawca × produkt z etykietami:
- `low` (<0.25) / `medium` (<0.50) / `high` (<0.75) / `critical` (≥0.75)

**Composite**: `0.4 × single_source_risk + 0.3 × capacity_utilisation + 0.3 × esg_risk`.

### Prediction Engine

- `build_supplier_profiles(events)` → per-supplier profile:
  - `on_time_rate`, `avg_delay_days`, `quality_score`, `seasonal_risk`, `trend` (improving/stable/declining).
- `predict_delay(input)` → `DelayPrediction` z probability, predicted days, confidence, factors.
- `compute_risk_alerts(profiles)` → lista `PredictiveAlert` (delay / quality / capacity / seasonal).

### OSINT Engine

Due diligence dostawcy z 4 darmowych źródeł:
1. **KRS** (Krajowy Rejestr Sądowy) — via `rejestr.io`.
2. **CEIDG** — `dane.biznes.gov.pl`.
3. **VIES** — EU VAT validation.
4. **GUS/REGON** (BIR) — placeholder.
5. **Transparency International CPI** — country risk scoring (per kraj siedziby).

**Endpoint**: `GET /supplier/{id}/osint` — zwraca wszystkie findings.

### Alerts Engine

`generate_alerts(orders, allocations, suppliers, risk_profiles)` → lista alertów:
- `severity`: low / medium / high / critical.
- `type`, `title`, `supplier_id`, `probability`, `impact_pln`, `recommendation`.

---

## 15. Konektory BI / ERP / WMS

**Status:** ⚠️ Mock — wszystkie 5 adapterów zwracają deterministyczne mock data (sha256 seed per kategoria × miesiąc). Interface `BIConnector` gotowy do podmiany na real HTTP client. Real integracja wymaga dostarczenia kluczy API przez klienta (effort: 2-4 dni per system).

5 adapterów z interfejsem `BIConnector` — obecnie **deterministyczny mock** (sha256 seed per kategoria × miesiąc), gotowe do podmiany na real HTTP client.

| System | Adapter | Metody zwracające |
|--------|---------|-------------------|
| **SAP ERP** | `ErpConnector` | `get_invoices(months, category, supplier)`, `get_purchase_orders(months)`, `get_budget_positions(year)` |
| **Enterprise BI** | `BiWarehouseConnector` | `get_historical_spend(months, category)` (24 mies.), `yoy_anomalies(threshold_pct)` |
| **Salesforce CRM** | `CrmConnector` | `get_demand_forecast(horizon_weeks)` — per kategoria |
| **Finance Ledger** | `FinanceConnector` | `get_cash_position()` (available/committed/at_risk), `get_overdue_invoices()` (DPO/DSO) |
| **SAP EWM** | `WmsConnector` | `get_stock_levels()` (per SKU per warehouse + reorder point) |

### Endpoints (`/api/v1/bi/*`)

- `GET /bi/status` — lista wszystkich konektorów + health snapshot (widget na dashboardzie).
- `GET /bi/erp/invoices | /bi/erp/purchase-orders | /bi/erp/budget`.
- `GET /bi/warehouse/spend-history | /bi/warehouse/yoy-anomalies`.
- `GET /bi/crm/demand-forecast`.
- `GET /bi/finance/cash-position | /bi/finance/overdue`.
- `GET /bi/wms/stock`.

### Status integracji

Wszystkie obecnie MOCK. Podmianę na real HTTP client robimy per klient na podstawie dostępnych kluczy API (typowo 1–3 dni pracy per konektor).

---

## 16. Document ingestion

**Status:** ⚠️ Partial — Ekstrakcja PDF/DOCX/EML/TXT + OCR fallback ✅. Catalog matching ✅. **Braki UX:** paste widget mało widoczny (mały przycisk „Dokumenty" w Step 0); unmatched items są silently dropped (`.filter(it => it.matched_id)` w copilot.js:267) — user nie widzi ile items pominięto ani nie ma opcji „Dodaj jako ad-hoc".

### Obsługiwane formaty

| Format | Biblioteka | Fallback |
|--------|------------|----------|
| **PDF** | `pypdf` (text layer) | Tesseract OCR (pol+eng) jeśli tekst <50 zn. |
| **DOCX** | `python-docx` | — |
| **EML** | stdlib `email.parser.BytesParser` | — |
| **TXT / CSV** | UTF-8 → CP1250 → latin-1 fallback chain | — |

### Pipeline

```
upload / paste
    │
    ▼
detect_format(filename, content_type, raw_bytes)
    │
    ├─ PDF ──► extract_text_from_pdf(raw)
    │          └─ if text < 50 chars AND FLOW_PDF_OCR_ENABLED=true
    │             └─► _ocr_pdf(raw)  [Tesseract pol+eng]
    │
    ├─ DOCX ─► extract_from_docx(raw)
    │          └─ paragraphs + table cells merged
    │
    ├─ EML ──► parse_email(raw)
    │          └─ From / Subject / body
    │
    └─ TXT ──► best-effort decode
         │
         ▼
    Claude Haiku (JSON extraction prompt)
    → { items: [{name, qty, unit, price, note}] }
         │
         ▼
    buying_engine.search_catalog(name) per item
    → match → CopilotAction(add_to_cart, {sku, qty})
    → no match → "ad-hoc" sugestia
```

### Normalizacja

- PDF: page limit 30, priorytet tekst layer.
- DOCX: cell contents merged newlines.
- EML: RFC 5322 compliant.

---

## 17. Process Mining

**Status:** ⚠️ Partial — Backend (DFG, lead times, bottlenecks, conformance, variants, rework, SLA, anomalies) ✅ wszystkie 10 endpointów działa. **Braki UI:** `loadMonitoringForSource()` w step5-monitoring.js to empty scaffold — supplier selector wyświetla się, ale filtrowanie per-supplier nie działa (backend orders list ignoruje `?supplier=`); bottleneck detection kolorowanie red edge w DFG nie zaimplementowane.

Moduł oparty o czysty Python + opcjonalnie `pm4py`. Pracuje na event logu P2P (purchase-to-pay).

### Format event logu

```json
[
  {"case_id": "PO-2026-001", "activity": "Create RFQ",
   "timestamp": "2026-04-10T09:14:00Z", "resource": "buyer@...", "cost": 0},
  ...
]
```

### Capabilities + endpointy (10)

| Funkcja | Endpoint | Zwraca |
|---------|----------|--------|
| **DFG Discovery** | `POST /process-mining/dfg` | Directly-Follows Graph: nodes (activities), edges (freq + avg time) |
| **Lead times** | `POST /process-mining/lead-times` | Avg/median/P95 per transition |
| **Bottlenecks** | `POST /process-mining/bottlenecks` | Slowest transitions + rework loops |
| **Variants** | `POST /process-mining/variants` | Top trace variants z frequency + avg duration |
| **Conformance** | `POST /process-mining/conformance` | % traces matching happy path |
| **Handovers** | `POST /process-mining/handovers` | Resource handoff matrix |
| **Rework** | `POST /process-mining/rework` | Rework loops + rates (backward edges) |
| **SLA monitor** | `POST /process-mining/sla-monitor` | Traces naruszające SLA |
| **Anomalies** | `POST /process-mining/anomalies` | Z-score outliers per case |
| **Full report** | `POST /process-mining/full-report` | Pełna analiza jednym call'em |

UI Step 5 renderuje DFG w Cytoscape.js — klikalne nody, heatmapa wolnych edges.

---

## 18. Projekty zakupowe

**Status:** ⚠️ Partial — CREATE/READ działa. Brakuje UPDATE/DELETE + pełnego lifecycle (transition endpoints: submit → approve → order → deliver). Budget validation nie zaimplementowana.

Agregat projektu (np. „Wymiana floty Q3") grupuje wiele zamówień pod jedną inicjatywą:

### Model

```python
Project:
  project_id, title, description, status,
  requester, department, mpk (cost center), gl_account,
  budget_limit, items: list[ProjectItem],
  subtotal, estimated_savings, final_total,
  domain, unspsc_code

ProjectItem:
  id, name, quantity, unit, price,
  category, unspsc, supplier_id, supplier_name

ProjectEvent:
  timestamp, action, actor, note
```

### Lifecycle

`draft → submitted → budget_check → approved → ordering → ordered → in_delivery → delivered → closed`

### Endpointy

- `POST /projects` — create.
- `GET /projects` — list z filtrami.
- `GET /projects/{id}` — detail z items + events.
- `PUT /projects/{id}` — update.
- `DELETE /projects/{id}`.

---

## 19. Integracja RFQ + EWM

**Status:** ⚠️ RFQ partial / ❌ EWM stub — RFQ Transformer + in-memory store działa (MVP). Webhook hooks skonfigurowane ale niesprawdzone z real endpoint. EWM wszystkie 6 endpointów zwracają placeholder data (`_wrap()` → `"source": "placeholder"`) — czeka na spec API od klienta.

### RFQ Transformer

- `rfq_to_optimizer_input(rfq)` → `(list[SupplierInput], list[DemandItem])` — zamiana zewnętrznego RFQ na format solvera.
- `optimizer_result_to_rfq_export(allocations, rfq)` → `list[RfqExportRow]` — zapis wyniku do RFQ (gotowe do wysyłki).

### RFQ Store

In-memory (MVP):
- `store_rfq(rfq)` → `rfq_id`.
- `get_rfq(rfq_id)`.
- `list_rfqs()` → `[{rfq_id, title, status, domain, line_items, bids_count}]`.

### Webhook hooks

- `FLOW_RFQ_IMPORT_URL` + `FLOW_RFQ_EXPORT_URL` (vendor-agnostic REST).
- `FLOW_WEBHOOK_SECRET` dla HMAC signature verification.

### EWM

`ewm_integration.py` — placeholder SAP EWM REST client (warehouse operations). Podmiana na real client po dostarczeniu kluczy przez klienta.

---

## 20. Multi-tenant SaaS + Auth

**Status:** ❌ Critical gaps — JWT auth ✅, `TenantContextMiddleware` ✅ (ContextVar + X-Tenant-ID + JWT claim), `_migrate_tenant_id()` dodaje kolumnę do 11 tabel ✅. **Ale:** (1) endpointy `/api/v1/*` + `/buying/*` **BEZ `Depends(get_current_user)`** — publiczne; (2) `db_insert_suppliers` + większość list queries filtruje po `domain` (business vertical) zamiast po `tenant_id` (SaaS customer) — **cross-tenant data leakage**; (3) `buying_routes.get_order()` (line 638) assume `tenant="demo"`. Przed prod multi-tenant trzeba to naprawić.

### JWT

- **Algorithm**: HS256.
- **Access token expiry**: 480 min (8h).
- **Refresh token expiry**: 30 dni.
- **Secret**: `FLOW_JWT_SECRET` env (64+ chars).

### Role

| Rola | Zakres |
|------|--------|
| `super_admin` | Platform-level (tenanty, cross-tenant stats) |
| `admin` | Tenant-level (katalog, reguły, workflows, userzy) |
| `buyer` | Zakupy, checkout, monitoring |
| `supplier` | Portal dostawcy |

### Tenant isolation

- **ContextVar per request** — `tenant_ctx.set(tenant_id)` w middleware.
- **Resolution order**: `X-Tenant-ID` header → JWT claim `tenant_id` → default `"demo"`.
- **Wire'd**: contracts, spend analytics, scorecard, concentration rule, orders, catalog items, supplier_profiles, business_rules, workflow_steps.
- **Super admin cross-tenant**: endpointy `/tenants/*` ignorują ContextVar (świadomie).

### Auth endpoints

- `POST /auth/login` → access + refresh.
- `POST /auth/register` (admin tworzy).
- `GET /auth/me`.
- `POST /auth/change-password`.
- `POST /auth/refresh`.
- `POST /auth/admin/seed-demo-users?reset_existing=true` — recovery dla demo.
- `POST /auth/admin/users/{username}/reset-password` — super_admin reset.

---

## 21. Observability + Security

**Status:** ✅ Mostly production — X-Request-ID middleware, JSON structured logs, `/metrics` (p50/p95/p99), Sentry opt-in, rate limiting wszystko działa. **Braki:** request_id nie jest injectowany do JSON error responses (user dostaje `{"detail": "..."}` bez ID do debugowania); Sentry PII scrubbing obejmuje headers ale nie request body (tokeny w payload mogą wyciec).

### Request tracing

- **X-Request-ID** (UUID4, 16 hex chars) attached automatycznie w middleware.
- `request.state.request_id` propagowany do logów.

### JSON structured logging

Każdy request jako JSON:
```json
{"timestamp": "2026-04-17T08:22:14Z", "request_id": "a3f2...",
 "method": "POST", "path": "/api/v1/optimize", "status": 200,
 "latency_ms": 243, "user_id": "buyer", "tenant_id": "demo"}
```

### Metrics

- `GET /metrics` — in-process rolling metrics (500 ostatnich latencies per route):
  - count, error_count, error_rate.
  - p50 / p95 / p99 latency per (method, route_bucket).
- Format JSON, łatwy do zescrape'owania przez Prometheus (jeśli klient chce).

### Error tracking

- **Sentry opt-in** via `FLOW_SENTRY_DSN`.
- Integration: FastAPI + Starlette + logging.
- PII scrubbing włączone.
- Release tag: `flow-procurement@2026.16.1.0`.

### Rate limiting

- Per-IP per-minute na `/api/v1/*`.
- Configurable via `FLOW_RATE_LIMIT_PER_MINUTE` (0 = off).
- Backend: in-memory (Redis-ready).

### Security headers

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY`.
- `Referrer-Policy: strict-origin-when-cross-origin`.

### CORS

- `FLOW_CORS_ORIGINS` (comma-separated).
- Domyślnie: `https://flowprocurement.com, https://www.flowprocurement.com, https://flow-procurement.up.railway.app, http://localhost:*` (dev).

---

## 22. Stack technologiczny

| Warstwa | Technologia | Uwagi |
|---------|-------------|-------|
| **Backend** | FastAPI + Pydantic v2 | 55 modułów, ~24 500 LOC |
| **Solver LP** | HiGHS (via `scipy.optimize.linprog`) | C1–C5, C11–C15b |
| **Solver MIP** | PuLP + HiGHS backend | Binary allocation |
| **AI Copilot** | Claude Haiku 4.5 / Sonnet 4.6 / Gemini 2.0 Flash | Smart routing per query complexity |
| **Document parsing** | pypdf + python-docx + Tesseract OCR | PDF/DOCX/EML/TXT, pol+eng |
| **Process Mining** | pm4py (opt) + pure Python DFG | DFG, conformance, anomalies |
| **Baza danych** | Turso (libSQL) aws-eu-west-1 | 14 tabel, fallback: lokalne SQLite |
| **Frontend** | Vanilla JS (ES modules) + Chart.js + Cytoscape.js | 12 modułów, 4 CSS |
| **Hosting** | Railway.app europe-west4 | Dockerfile, 2 workers |
| **DNS** | Cloudflare (flowprocurement.com) | DNS-only (Railway zarządza TLS) |
| **CI/CD** | GitHub Actions (3 workflows) | lint + test matrix 3.11/3.12 + Docker smoke + E2E + k6 PR gate |
| **Error tracking** | Sentry (opt-in) | FastAPI + Starlette integration |
| **Monitoring** | `/metrics` (p50/p95/p99) + JSON logs | X-Request-ID per request |
| **E2E tests** | Playwright chromium | Login + Copilot cart add |
| **Load tests** | k6 | SLO: p95 <1.5s, error <1% |

---

## 23. Baza danych

### 14 tabel w Turso (libSQL)

| Tabela | Opis |
|--------|------|
| `tenants` | Multi-tenant SaaS (demo + custom tenanty klientów) |
| `users` | JWT auth (superadmin/admin/buyer/supplier) |
| `suppliers` | Dostawcy per tenant per domena |
| `demand` | Zapotrzebowanie per domena |
| `orders` | Zamówienia z pełnym lifecycle |
| `order_events` | Audit log zamówień |
| `contracts` | Kontrakty (CRUD + expiry tracking) |
| `contract_audit` | Kto/kiedy/co zmienił w kontrakcie |
| `optimization_results` | Wyniki solvera (historia decyzji) |
| `p2p_events` | Event log P2P dla process mining |
| `supplier_profiles` | Profile z certyfikatami |
| `catalog_items` | Produkty katalogowe (SKU + UNSPSC) |
| `business_rules` | Reguły (progi, rabaty, constrainty per tenant) |
| `workflow_steps` | Approval workflow per tenant |

### Uwagi techniczne

- **Latency**: ~100ms Railway europe-west4 → Turso aws-eu-west-1 (akceptowalne).
- **HTTP API** Turso serializuje zapisy → 2 workery bez race condition.
- **Backup**: automatyczny daily snapshot Turso (managed).
- **Fallback**: jeśli env `FLOW_TURSO_*` nie ustawione, app używa lokalnego SQLite (tylko dev/test).

---

## 24. API — ~243 endpointy

Wszystkie pod prefixem `/api/v1/`. Pełna dokumentacja OpenAPI pod `/docs` (Swagger) i `/redoc`.

### Routery

| Prefix | Liczba ≈ | Obszar |
|--------|:---:|---------|
| `/buying` | 25+ | Katalog, koszyk, optymalizacja koszyka, orders, contracts, scorecard |
| `/optimize` | 3 | Core LP/MIP optimization |
| `/mip` | 4 | Dedicated MIP solver + compare |
| `/whatif` | 3 | Scenariusze |
| `/process-mining` | 10 | DFG, bottlenecks, conformance, itd. |
| `/auth` | 5+ | Login, register, refresh, me, change-password |
| `/admin` | 12 | Katalog, rules, workflows, users |
| `/superadmin` | 7 | Tenanty, platform stats |
| `/portal` | 10 | Profile, orders, RFQ, certs, assessment |
| `/auctions` | 11 | Lifecycle + bid |
| `/marketplace` | 8 | Allegro + PunchOut |
| `/bi` | 8 | ERP / BI / CRM / Finance / WMS |
| `/prediction` | 4 | Delay forecast + profiles + alerts |
| `/risk` | 5 | Heatmap, MC, negotiation |
| `/integration` | 6 | RFQ in/out |
| `/project` | 5 | Projekty zakupowe |
| `/supplier` | 4 | VIES + OSINT |
| `/domains` | 2 | Registry + extended |
| `/weights` | 1 | Live weight management |
| `/demo/{domain}` | 2 | Demo data |
| `/db` | 8 | Internal seed endpoints |
| `/health`, `/ready`, `/metrics` | 3 | Observability |

### Konwencje

- Wszystkie odpowiedzi JSON.
- Błędy: `{"detail": "...", "request_id": "a3f2..."}` z odpowiednim HTTP status.
- Autoryzacja: `Authorization: Bearer <jwt>` (większość endpointów wymaga auth).
- Tenant context: `X-Tenant-ID: demo` (opcjonalny, fallback na JWT claim).

---

## 25. CI/CD + DevOps

### 3 workflowy GitHub Actions

```
Push to main ──┬─► ci.yml ───────────────────────────────────────┐
               │   ├─ Lint (ruff 0.6.9)                         │
               │   ├─ Test matrix (pytest 3.11 + 3.12)           │
               │   ├─ Docker build + smoke (/health 200)         │
               │   ├─ E2E Playwright (login + Copilot cart)      │
               │   └─ Load test k6 (PR only, SLO p95<1.5s)       │
               │                                                  │
               └─► post-deploy.yml ──────────────────────────────┐
                   ├─ Wait for Railway version match (~5 min)    │
                   ├─ Smoke test 10 endpoints on prod            │
                   └─ Open GitHub issue on failure               │
                                                                 │
Cron 06:00 UTC ─► nightly-smoke.yml ─────────────────────────────┘
                   ├─ Smoke test (bez wait)
                   └─ Issue on failure (deduped via update_existing)
```

### Dodatkowo: autobump-version.yml

Na każdy push do `main` workflow `autobump-version` podbija wersję `YYYY.WW.BUILD.PATCH`:
- Source of truth: `.version` w repo.
- `BUILD` inkrement co push, reset na nowy tydzień ISO.
- `PATCH` tylko ręcznie (hotfix).
- Commit back z `[skip ci]` żeby nie zapętlić.

### Testy

- **157 unit/integration** tests (pytest).
- **3 Playwright E2E** tests (login, dashboard load, Copilot add-to-cart).
- **k6 load** — PR gate z thresholds `http_req_duration p95<1500ms`, `http_req_failed<1%`.
- **Coverage** — ~56% baseline, Codecov integration.

### Deploy

- **Railway** auto-deploy z `main`.
- **Zero-downtime** — Railway rolling update.
- **Rollback**: `git revert <bad-sha> && git push` → Railway redeploys.

---

## 26. Konta demo

| User | Hasło | Rola | Co może |
|------|-------|------|---------|
| `superadmin` | `super123!` | super_admin | Zarządzanie tenantami, reset userów |
| `admin` | `admin123` | admin | Backoffice, katalog, konfiguracja |
| `buyer` | `buyer123` | buyer | Dashboard, wizard 6-step, checkout |
| `trw` | `trw123` | supplier | Portal dostawcy TRW |
| `brembo` | `brembo123` | supplier | Portal dostawcy Brembo |
| `bosch` | `bosch123` | supplier | Portal dostawcy Bosch |
| `kraft` | `kraft123` | supplier | Portal dostawcy Kraft |

**Recovery**: jeśli demo loginy nie działają:
```
POST /auth/admin/seed-demo-users?reset_existing=true
```
(wywoływane jako superadmin).

---

## 27. Skalowanie i roadmap

### Zrealizowane (MVP-1..5 + Phase A+B)

| Faza | Opis | Status |
|------|------|:---:|
| A1 | BI connectors (5 mock adapters + `BIConnector` interface) | ✅ |
| A2 | 27 subdomen (widget + summary + taxonomy UNSPSC) | ✅ |
| A3 | Hard C14/C15b constrainty | ✅ |
| B1 | Shadow prices (LP sensitivity) | ✅ |
| B2 | Monte Carlo na froncie Pareto (confidence fan P5/mean/P95) | ✅ |
| B3 | Scenario chaining (What-If v2 — cumulative deltas) | ✅ |
| B4 | Subdomain-level optimization + domain aggregate | ✅ |
| MVP-1 | AI Assistant jako główny UI + proactive cards | ✅ |
| MVP-2 | Document ingestion (paste + PDF/DOCX/EML + OCR) | ✅ |
| MVP-3 | Spend analytics (Direct/Indirect breakdown) | ✅ |
| MVP-4 | Contracts + Recommendation Engine (5 reguł) | ✅ |
| MVP-5 | Supplier Scorecard (composite 0–100 z 5 wymiarów) | ✅ |

### Do realizacji — CRITICAL (przed multi-tenant prod)

| Item | Opis | Effort | Priorytet |
|------|------|:---:|:---:|
| **Auth na `/api/v1/*`** | Dodać `dependencies=[Depends(get_current_user)]` do 15 routerów; wydzielić public sub-router dla /buying/catalog | 3h | 🔴 |
| **Tenant isolation w queries** | `db_insert_*` i list queries — przełączyć z `WHERE domain=?` na `WHERE tenant_id=?` (ContextVar już wired) | 5h | 🔴 |
| **`buying_routes.get_order()` 403** | Zwracać 403 gdy `order.tenant_id != current_tenant()` | 1h | 🔴 |
| **Contract audit writes** | `approve_order()` + `generate_purchase_orders()` wołają `db_append_contract_audit()` (helper już istnieje) | 2h | 🟠 |
| **Contract store → DB** | Usunąć `_CONTRACTS = {}` cache, czytać/pisać przez `db_list_contracts`/`db_upsert_contract` | 2h | 🟠 |
| **Tenant isolation regresja** | 3 testy: user tenant_A nie widzi orderów/suppliers/contracts tenant_B | 2h | 🔴 |

### Do realizacji — DEMO POLISH (6 scenariuszy 100%)

| Item | Scenariusz | Effort | Priorytet |
|------|------|:---:|:---:|
| Unmatched items UI (warning + „ad-hoc" button) | B | 1h | 🟢 |
| Step 3 → 4 auto-populate cart z solver output | A | 2h | 🟢 |
| `dispatchActionCard()` routing + `navigate_to_contracts` case | C | 2h | 🟢 |
| Admin UI edycji kontraktów | C | 2h | 🟡 |
| OSINT render (KRS/CEIDG/VIES/CPI sub-cards) | E | 3h | 🟢 |
| Process mining `?supplier=` backend filter + UI | F | 4h | 🟡 |
| Bottleneck red-edge rendering w DFG | F | 1h | 🟡 |
| Auction form builder (items) + Award button Step 4 | D | 4h | 🟡 |
| Auction DB persistence (tabela + migration) | D | 2h | 🟡 |

### Do realizacji — DX / HARDENING

| Item | Opis | Effort |
|------|------|:---:|
| request_id w error JSON body | exception handler injectuje `request.state.request_id` | 1h |
| Sentry body PII scrubbing | `before_send` hook scrubbuje emails/NIPy z payload | 1h |
| Cart localStorage persistence | `_s1SelectedItems` survive refresh | 1h |
| Projects CRUD + lifecycle transitions | UPDATE/DELETE + submit→approve→order→deliver | 1 dzień |

### Do realizacji — po uzgodnieniu z klientem

| Item | Opis | Effort |
|------|------|:---:|
| Real BI connectors | Podpięcie SAP/ERP/CRM klienta — po dostarczeniu kluczy API | 2–4 dni per system |
| EWM real integration | Po dostarczeniu spec API od klienta | 2–5 dni |
| Multi-replica Redis | Rate limiter + metrics backend na Redis (scaling) | 0.5 dnia |
| Staging environment | Oddzielna gałąź `staging` na Railway + CI gate | 0.5 dnia |
| Subdomain weights | Osobne wagi per subdomena (dziedziczone z domeny) | 1 dzień |
| UNSPSC LLM fallback | Claude klasyfikuje gdy keyword-matching „Nieklasyfikowane" | 0.5 dnia |
| WebSocket live auction | Push oferty realtime do UI | 1 dzień |
| Zaawansowany raporting | PDF/Excel export Pareto / Monte Carlo / Scorecard | 1 dzień |
| Real email notifications | SendGrid/Postmark integration dla alertów | 0.5 dnia |
| Email webhook ingest | Mail przychodzący → auto-parse + create RFQ | 1–2 dni |
| Mobile-first portal dostawcy | PWA z offline bid queue | 2 dni |
| ML prediction model (XGBoost/RF) | Po zebraniu 1000+ historical orders | 3–5 dni |

**Całkowity effort przed prezentacją (CRITICAL + DEMO POLISH):** ~40h (~1 sprint).

---

## 28. Scenariusze demo dla klienta

**Legenda statusu:**
- ✅ działa end-to-end bez friction
- ⚠️ działa, ale z brakami UX (wymaga dokończenia przed prezentacją)
- ❌ backend gotowy, UI niekompletny (wymaga implementacji)

| # | Scenariusz | Status | Znane braki |
|---|-----------|:------:|-------------|
| A | Klocki hamulcowe od 0 do zamówienia w 4 minuty | ⚠️ | Step 3→4 nie auto-populuje alokacji solvera — user musi ręcznie potwierdzić checkout |
| B | Ingest emaila z zapotrzebowaniem | ⚠️ | Unmatched items są silently dropped (brak UI info + fallback na ad-hoc) |
| C | Alert kontraktu wygasającego | ❌ | Karta ma CTA, ale `dispatchActionCard()` nie ma implementacji akcji; brak UI edycji kontraktów w adminie |
| D | Aukcja odwrotna na oleje | ⚠️ | Items jako JSON textarea (nie form builder); brak przycisku „Award" na Step 4 po deadline; aukcje in-memory (nie w DB) |
| E | Due diligence nowego dostawcy (OSINT) | ❌ | `suppViesLookup()` wysyła request ale nie parsuje response (KRS/CEIDG/CPI niewidoczne); OSINT nie na karcie Step 2 |
| F | Process mining na slow supplierze | ⚠️ | `loadMonitoringForSource()` to empty scaffold — supplier selector jest, ale filtrowanie nie zaimplementowane |

### Scenariusz A — „Klocki hamulcowe od 0 do zamówienia w 4 minuty"

1. Login jako `buyer` / `buyer123`.
2. Step 0: Copilot → wpisz „dodaj 3 klocki hamulcowe Bosch do koszyka".
3. Copilot mapuje na SKU `BOSCH-BRK-3041` i dodaje do `state._s1SelectedItems`.
4. Copilot → „przejdź do dostawców".
5. Step 2: widać Scorecard — Bosch 84, TRW 78, Brembo 92.
6. Copilot → „optymalizuj z wagą cena 50%".
7. Step 3: solver biegnie, widać front Pareto + Monte Carlo confidence fan.
8. Kupiec akceptuje alokację (np. 60% Brembo, 40% TRW).
9. „Create order from optimizer" → Step 4 checkout.
10. Approve → PO generated → Confirmed.

**Cały proces: ~4 min.** (tradycyjnie: 1–2 godziny).

### Scenariusz B — „Ingest emaila z zapotrzebowaniem"

1. Login jako `buyer`.
2. Step 0: do paste area wrzucasz surowego maila od działu operacji:
   ```
   Hej, potrzebujemy:
   - klocki hamulcowe Brembo 4 szt.
   - filtry oleju Knecht 10 szt.
   - olej Mobil 1 5W30 20 litrów
   ```
3. Copilot → Claude Haiku ekstraktuje 3 items → mapuje na katalog → dodaje wszystkie do koszyka.
4. „Optymalizuj wszystko z wagą ESG 30%".
5. Solver biegnie, widać split alokacji. Dalej jak w scenariuszu A.

### Scenariusz C — „Alert kontraktu wygasającego"

1. Login jako `buyer`.
2. Na dashboardzie karta proaktywna: **📅 Kontrakt z Bosch wygasa za 14 dni**.
3. CTA: „Zaplanuj renegocjacje" → przełącza na Step 2 z filtrem supplier=Bosch.
4. Widać scorecard Bosch, historię zamówień, kontrakt detail.
5. Admin przechodzi do `/admin-ui` → tabela kontraktów → edit → nowa data końca.
6. Audit trail aktualizuje się automatycznie.

### Scenariusz D — „Aukcja odwrotna na oleje"

1. Login jako `buyer`.
2. Step 4 → „Create auction" → wybierz items (olej Mobil 1 5W30, Shell Helix 10W40).
3. Wybierz typ: `reverse`, deadline 48h, zaproś 3 dostawców.
4. Login jako `trw` lub `brembo` (portal dostawcy).
5. Aukcja na liście — bid submit → widzisz swoje miejsce w rankingu.
6. Po deadline: buyer `award` → winning supplier → PO generated automatically.

### Scenariusz E — „Due diligence nowego dostawcy"

1. Login jako `admin`.
2. `/admin-ui` → Katalog → dodaj dostawcę (nowy NIP).
3. `GET /supplier/{id}/osint` — zwraca:
   - **KRS**: data rejestracji, forma prawna, kapitał zakładowy.
   - **CEIDG**: aktywność.
   - **VIES**: aktywny VAT EU.
   - **TI CPI**: country risk score.
4. Jeśli którykolwiek red flag → blokada dodania.

### Scenariusz F — „Process mining na slow supplierze"

1. Login jako `buyer`.
2. Step 5 → Process Mining.
3. Wybierz „Kraft" z listy supplier.
4. Widać DFG: `Create Order → Approve → Generate PO → Confirm → Ship → Deliver`.
5. Czerwona krawędź: `Confirm → Ship` avg 14 dni (happy path: 3 dni).
6. Conformance: 64% (część traces ma dodatkowy cykl `Cancel → Recreate`).
7. Alert predykcyjny: „Kraft — delay risk 72% dla najbliższych 3 zamówień".
8. Decyzja biznesowa: spadek share Kraft w kolejnej optymalizacji (weight_time ↑).

---

## 29. Powiązane dokumenty

Prezentacja jest **single-source-of-truth dla klienta**. Szczegóły techniczne / ops / historyczne w osobnych plikach:

| Plik | Zawiera |
|------|---------|
| `PROJECT.md` | Pełna dokumentacja techniczna (stack, solver constrainty, schema DB, AI routing) |
| `CHANGELOG.md` | Historia zmian per release (v5.x → Tesla YYYY.WW.BUILD) |
| `README.md` | Quick start — uruchomienie lokalne |
| `CONTRIBUTING.md` | Reguły kontrybucji, workflow, konwencje |
| `SECURITY.md` | Policy bezpieczeństwa + incident response |
| `ops/ONCALL.md` | On-call runbook (SLO, playbook incydentów) |
| `ops/DEPLOY.md` | Procedura deployu na Railway |
| `ops/STAGING.md` | Setup środowiska staging |
| `ops/SECRETS.md` | Rotacja secrets + Railway Variables |
| `ops/ALERTING.md` | Reguły alertów (Sentry + nightly smoke) |
| `docs/archive/` | Przestarzałe wersje zakresu (SCOPE v3.1, v4.0, ARCHITECTURE v5.0.16, DEMO_ACCESS v5.1.0) — tylko do celów audytu |

---

## Kontakt

- **Repo**: `github.com/pawelmamcarz/flow-procurement`
- **Live demo**: https://flowprocurement.com (uruchamiane) · https://flow-procurement.up.railway.app
- **API docs**: https://flowprocurement.com/docs
- **Dev**: Pawel Mamcarz · pawel@mamcarz.com

---

_Wersja platformy na dzień 2026-04-17: **v2026.16.1.0** (Tesla-style versioning)_
