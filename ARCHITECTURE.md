# Flow Procurement Platform — Architecture & Marketplace Integration

**Version:** 5.0.16
**Date:** 2026-03-14
**Production:** https://flow-procurement.up.railway.app
**API Docs:** https://flow-procurement.up.railway.app/docs

---

## 1. Przegad platformy

Flow Procurement Platform to kompletny system e-procurement klasy enterprise:

```
                      +---------------------+
                      |   Frontend (SPA)    |
                      |   /ui  /admin-ui    |
                      |   /portal-ui        |
                      |   /superadmin-ui    |
                      +----------+----------+
                                 |
                      +----------v----------+
                      |   FastAPI Backend   |
                      |   Python 3.11+      |
                      +----------+----------+
                                 |
              +------------------+------------------+
              |                  |                  |
     +--------v------+  +-------v-------+  +-------v--------+
     | Buying Engine |  | Optimizer     |  | Marketplace    |
     | (Katalog,     |  | (HiGHS LP,   |  | Engine         |
     |  UNSPSC,      |  |  Pareto,     |  | (Allegro API,  |
     |  Zamowienia)  |  |  Monte Carlo)|  |  PunchOut cXML)|
     +---------------+  +---------------+  +----------------+
```

### Moduly

| Modul | Plik | Opis |
|-------|------|------|
| **Config** | `app/config.py` | Parametry env (Pydantic Settings), prefix `FLOW_` |
| **Main** | `app/main.py` | FastAPI app, montowanie routerow |
| **Buying Engine** | `app/buying_engine.py` | Katalog produktow, UNSPSC mapping, zamowienia |
| **Buying Routes** | `app/buying_routes.py` | REST API dla katalogu, koszykow, PO |
| **Optimizer Engine** | `app/engine.py` | HiGHS LP solver, Pareto front, Monte Carlo |
| **Optimizer Routes** | `app/routes.py` | REST API optymalizacji |
| **Marketplace Engine** | `app/marketplace_engine.py` | Allegro OAuth2, PunchOut cXML, mock catalog |
| **Marketplace Routes** | `app/marketplace_routes.py` | REST API marketplace |
| **Auth** | `app/auth.py` | JWT authentication, multi-tenant |
| **Portal** | `app/portal_routes.py` | Supplier Portal API |
| **Admin** | `app/admin_routes.py` | Backoffice admin API |
| **Super Admin** | `app/superadmin_routes.py` | Multi-tenant SaaS management |
| **AI Copilot** | `app/copilot_routes.py` | LLM-powered procurement assistant |
| **Process Mining** | `app/process_mining.py` | SLA analysis, anomaly detection |

---

## 2. Marketplace — Architektura

### 2.1 Allegro API Integration

```
  +--------------------+
  |  Frontend (UI)     |
  |  mktAllegroSearch()|------> GET /marketplace/allegro/search?q=...
  |  mktAllegroAuth()  |------> Redirect to allegro.pl/auth/oauth/authorize
  +--------------------+
           |
           v
  +--------------------+          +-------------------+
  | Marketplace Routes |          | Allegro REST API  |
  | (FastAPI)          |<-------->| allegro.pl        |
  |                    |          | OAuth2 auth_code  |
  +--------------------+          +-------------------+
           |
           v
  +--------------------+
  | AllegroClient      |
  | - OAuth2 token     |
  | - search()         |
  | - mock fallback    |
  +--------------------+
```

**Flow autoryzacji (authorization_code):**

1. User klika "Polacz z Allegro" w UI
2. Frontend pobiera `client_id` z `/marketplace/allegro/status`
3. Redirect do `https://allegro.pl/auth/oauth/authorize?response_type=code&client_id=...&redirect_uri=.../callback`
4. User loguje sie na Allegro i autoryzuje
5. Allegro redirectuje na `/api/v1/marketplace/allegro/callback?code=...`
6. Backend wymienia `code` na `access_token` (POST do `allegro.pl/auth/oauth/token`)
7. Token przechowywany w pameci `AllegroClient._token`
8. Frontend polluje `/status` co 3s i wykrywa `has_token: true`

**Fallback:** Gdy Allegro API nieskonfigurowane lub 403 — automatyczny fallback na 55-elementowy mock catalog z inteligentnym wyszukiwaniem (tag-based scoring).

### 2.2 PunchOut cXML Integration

```
  +--------------------+          +--------------------+
  |  Procurement App   |          | External Supplier  |
  |  (Buyer)           |          | (Allegro via cXML) |
  +--------------------+          +--------------------+
           |                               |
           |  1. PunchOutSetupRequest       |
           |  (cXML POST)                   |
           +------------------------------>|
           |                               |
           |  2. PunchOutSetupResponse      |
           |  (Browse URL)                  |
           |<------------------------------+
           |                               |
           |  3. Browse catalog             |
           |  GET /punchout/browse/{id}     |
           +------------------------------>|
           |                               |
           |  4. Product catalog            |
           |  (Allegro mock + enterprise)   |
           |<------------------------------+
           |                               |
           |  5. Add to cart                |
           |  POST /punchout/cart/{id}      |
           +------------------------------>|
           |                               |
           |  6. PunchOutOrderMessage       |
           |  (cXML with cart items)        |
           |<------------------------------+
```

**Protokol cXML 1.2.014:**
- `PunchOutSetupRequest` — inicjalizacja sesji, buyer_cookie, redirect URL
- `PunchOutSetupResponse` — status 200, browse URL
- `PunchOutOrderMessage` — finalizacja koszyka, lista pozycji z cenami

**Mapowanie kategorii (nasze domeny -> Allegro tagi):**

| Nasza kategoria | Allegro tagi |
|----------------|--------------|
| `it` | laptop, komputer, monitor, drukarka, toner, ssd, switch |
| `office` | papier, biuro, segregator, dlugopis, tablica |
| `furniture` | krzeslo, biurko, szafa, fotel, meble |
| `safety` | bhp, rekawice, okulary, kask, buty, ochrona |
| `tools` | wiertarka, narzedzia, klucze, szlifierka, pila |
| `cleaning` | czystosc, recznik, mydlo, plyn, higiena |
| `electrical` | led, panel, zarowka, oswietlenie, kabel, elektro |
| `parts` | klocki, hamulcowe, filtr, motoryzacja, opony |
| `packaging` | karton, opakowanie, folia, tasma, paleta, logistyka |
| `food` | kawa, woda, herbata, cukier, zywnosc |
| `hvac` | klimatyzacja, filtr, wentylacja |

### 2.3 Katalog PunchOut

PunchOut browse laczy dwa zrodla danych:

1. **Allegro Mock** (55 produktow) — symuluje oferty z Allegro.pl
   - IT/Elektronika (15), Biuro (6), Meble (4), BHP (6), Narzedzia (5)
   - Czystosc (4), Chemia (3), Elektro (4), Opakowania (4), Motoryzacja (5), Zywnosc (4)

2. **Enterprise PunchOut Catalog** (50+ produktow) — symuluje katalog dostawcy ramowego
   - Produkty z numerami umow ramowych (np. `FWZ/2024/IT-001`)
   - Dostawcy enterprise (Dell, Steelcase, Makita, Schneider Electric, Daikin...)
   - Licencje SaaS (M365, Adobe CC)
   - Uslugi serwisowe

**Filtrowanie:** Endpoint `GET /punchout/browse/{session_id}?category=it` filtruje oba zrodla.

---

## 3. UNSPSC Smart Mapping

```
  UNSPSC Code (np. 251010)
         |
         v
  _UNSPSC_DEEP_MAP  ──> 251010 → "vehicles" (exact match)
         |
         v (if not found)
  _UNSPSC_TO_CATEGORIES ──> segment 25 → "vehicles"
         |
         v (if not found)
  Neighbor segments ──> 24,26 → closest match
         |
         v
  Catalog items filtered by category
```

**Hierarchia UNSPSC:**
- 2 cyfry = Segment (np. 25 = Pojazdy)
- 4 cyfry = Family (np. 2510 = Pojazdy silnikowe)
- 6 cyfr = Class (np. 251015 = Samochody osobowe)
- 8 cyfr = Commodity (np. 25101500 = Czesci samochodowe)

**Mapowanie obejmuje 55 segmentow UNSPSC** od 10 (Gornictwo) do 95 (Nieruchomosci).

---

## 4. Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| **Backend** | Python 3.11, FastAPI, Uvicorn |
| **Solver** | HiGHS (LP/MIP), SciPy (Monte Carlo) |
| **Frontend** | Vanilla JS SPA, CSS Grid, Chart.js |
| **Auth** | JWT (PyJWT), bcrypt, multi-tenant |
| **Database** | Turso/LibSQL (opcjonalnie), in-memory |
| **AI** | Claude API (primary), Gemini (fallback) |
| **Marketplace** | Allegro REST API, cXML 1.2.014 |
| **Deployment** | Railway.app, GitHub CI/CD |
| **Versioning** | SemVer, pre-commit auto-bump |

---

## 5. REST API — Marketplace Endpoints

### Allegro

| Method | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/marketplace/allegro/status` | Status konfiguracji i autoryzacji |
| `GET` | `/marketplace/allegro/search?q=...&limit=20` | Wyszukiwanie produktow |
| `GET` | `/marketplace/allegro/callback?code=...` | OAuth2 callback (auth_code) |
| `POST` | `/marketplace/allegro/auth/start` | Start device_code flow (legacy) |
| `POST` | `/marketplace/allegro/auth/poll` | Poll device authorization |

### PunchOut cXML

| Method | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/marketplace/punchout/setup` | Utworz sesje PunchOut (cXML) |
| `GET` | `/marketplace/punchout/browse/{id}?category=` | Przegladaj katalog |
| `POST` | `/marketplace/punchout/cart/{id}` | Dodaj do koszyka |
| `POST` | `/marketplace/punchout/return/{id}` | Zwroc koszyk jako cXML |
| `GET` | `/marketplace/punchout/sessions` | Lista sesji (debug) |

Wszystkie endpointy pod prefixem `/api/v1/`.

---

## 6. Konfiguracja (env vars)

```bash
# Allegro Marketplace
FLOW_ALLEGRO_CLIENT_ID=<client_id>        # Aplikacja typu "przegladarka"
FLOW_ALLEGRO_CLIENT_SECRET=<secret>
FLOW_ALLEGRO_API_BASE=https://api.allegro.pl
FLOW_ALLEGRO_AUTH_URL=https://allegro.pl/auth/oauth/token

# AI Copilot
FLOW_LLM_API_KEY=<claude_api_key>
FLOW_LLM_PROVIDER=claude
FLOW_GEMINI_API_KEY=<gemini_key>          # fallback

# Auth
FLOW_JWT_SECRET=<secret>

# Database (opcjonalne)
FLOW_TURSO_DATABASE_URL=<turso_url>
FLOW_TURSO_AUTH_TOKEN=<turso_token>
```

---

## 7. Deployment

```bash
# Local development
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Railway (auto-deploy on push)
git push origin main
# Railway detects Procfile/nixpacks → builds → deploys

# Verify
curl https://flow-procurement.up.railway.app/api/v1/health
```

### Pre-commit hook
Automatyczny version bump (patch) przy kazdym udalnym uzyciu `git commit`:
- `app/config.py` — `app_version`
- `app/static/index.html` — wersja w UI

---

## 8. Scenariusze integracji Marketplace

### Scenariusz 1: Zamowienie z Allegro (mock)
1. Buyer wchodzi na `/ui` → Krok 1 → Marketplace
2. Tab "Allegro" — wpisuje "laptop" → wyniki z mock katalogu
3. Dodaje produkty do koszyka (ilosc +/-)
4. Przechodzi do Krok 2 (Dostawcy) → Krok 3 (Optymalizacja)

### Scenariusz 2: PunchOut cXML (Allegro jako dostawca zewnetrzny)
1. Buyer wchodzi na Marketplace → Tab "PunchOut cXML (Allegro)"
2. System tworzy sesje cXML (`PunchOutSetupRequest`)
3. Wyswietla katalog z filtrami kategorii (IT, BHP, Biuro...)
4. Buyer dodaje produkty → klika "Eksportuj koszyk cXML"
5. System generuje `PunchOutOrderMessage` z pozycjami
6. Koszyk integruje sie z normalnym flow zamowien

### Scenariusz 3: Allegro API (live — po weryfikacji aplikacji)
1. Admin klika "Polacz z Allegro" → redirect do allegro.pl
2. Loguje sie i autoryzuje aplikacje
3. System otrzymuje `access_token` via callback
4. Wyszukiwanie zwraca realne oferty z Allegro.pl
5. Fallback na mock przy bledach API

### Scenariusz 4: Fallback Allegro dla pustego katalogu
1. Buyer wybiera kategorie UNSPSC (np. 251010 Samochody)
2. Katalog wewnetrzny nie ma produktow w tej kategorii
3. System wyswietla link "Szukaj na Allegro"
4. Przenosi do zakladki Marketplace z pre-wypelnionym zapytaniem

---

## 9. AI Copilot — Architektura

```
  +--------------------+          +-------------------+
  |  Frontend          |          | Claude API        |
  |  Copilot Widget    |------->  | (primary LLM)     |
  |  (chat, sugestie)  |          +-------------------+
  +--------------------+                  |
           |                     fallback v
  +--------------------+          +-------------------+
  | /api/v1/copilot/   |          | Gemini API        |
  | chat               |------->  | (fallback LLM)    |
  | suggestions        |          +-------------------+
  +--------------------+
           |
  +--------------------+
  | CopilotEngine      |
  | - system prompt    |
  | - intent detection |
  | - action mapping   |
  | - cart context     |
  +--------------------+
```

**Flow:**
1. User wpisuje pytanie w widget czatu (prawy dolny rog)
2. Frontend wysyla POST `/api/v1/copilot/chat` z wiadomoscia + kontekstem (step, domain, cart)
3. `CopilotEngine` wykrywa intent (regex → 12 kategorii: optimize, search, explain, navigate...)
4. Jesli intent rozpoznany → odpowiedz lokalna + akcje (navigate, optimize, set_weights, search)
5. Jesli intent niejasny → wysylka do LLM:
   - **Primary:** Claude (claude-sonnet-4-20250514) via Anthropic API
   - **Fallback 1:** Gemini (gemini-2.0-flash) via Google AI API
   - **Fallback 2:** odwrotnosc primary (jesli primary=gemini, fallback=claude)
6. Odpowiedz + sugestie follow-up wyswietlane w czacie
7. Akcje wykonywane automatycznie (np. `goStep(3)`, `selectCategory('parts')`)

**System prompt** zawiera:
- Pelna wiedze o platformie (5 krokow, UNSPSC, Allegro, PunchOut, dostawcy)
- Kontekst uzytkownika (aktualny krok, domena, zawartosc koszyka)
- Zasady: odpowiedzi po polsku, max 4-5 zdan, Markdown

**Sugestie kontekstowe:**
- Krok 1: "Szukaj na Allegro: laptop...", "Pokaz katalog hamulcow"
- Krok 2: "Filtruj dostawcow ISO 9001", "Sprawdz VAT w VIES"
- Krok 3: "Uruchom optymalizacje", "Wyjasnij front Pareto"
- Krok 4: "Pokaz status zamowien", "Utworz aukcje odwrocona"
- Krok 5: "Alerty predykcyjne ML", "Symulacja Monte Carlo"

---

## 10. Koszyk — Unified Cart System

Platforma ma dwa systemy koszyka ktore sa zsynchronizowane:

1. **`_s1SelectedItems`** (frontend) — pozycje wybrane w Kroku 1:
   - Z katalogu wewnetrznego
   - Z Allegro Marketplace (mock lub live)
   - Z PunchOut cXML
   - Kazdy item ma: `id`, `name`, `price`, `qty`, `source`, `suppliers`, `supplier_name`

2. **`obCart`** (API-backed) — koszyk zakupowy z `/api/v1/buying/cart`:
   - Synchronizowany z `_s1SelectedItems` przy przejsciu do Kroku 4
   - Obsluguje reguly biznesowe (bundles, approval workflow, progi kwotowe)

**Synchronizacja:**
- Sidebar cart (ikona koszyka w headerze) pokazuje `_s1SelectedItems` gdy `obCart` pusty
- Global badge liczy pozycje z obu zrodel
- Step 4 review laczy oba (tabela z dostawcami, badgami zrodla, podsumowaniem)

**Widok Step 4 (Zamowienie):**
- Tabela: Produkt | Dostawca | Ilosc | Cena jedn. | Wartosc
- Badge zrodla: Allegro (niebieski), PunchOut (fioletowy)
- Podsumowanie: ilosc pozycji, wartosc, zrodlo, liczba dostawcow
- Approval workflow: auto / kierownik / dyrektor / zarzad
