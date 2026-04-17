# Flow Procurement Platform — Demo Access Guide

**Production:** https://flow-procurement.up.railway.app
**Version:** 5.1.0
**API Docs:** https://flow-procurement.up.railway.app/docs

---

## URLs

| Panel | URL | Opis |
|-------|-----|------|
| **Procurement UI** | `/ui` | Glowna aplikacja — zamowienia, optymalizacja, monitoring |
| **Admin Backoffice** | `/admin-ui` | Zarzadzanie uzytkownikami, ustawienia |
| **Super Admin** | `/superadmin-ui` | Zarzadzanie tenantami (multi-tenant SaaS) |
| **Portal Dostawcy** | `/portal-ui` | Widok dostawcy — potwierdzanie PO, dostawy |
| **Swagger API** | `/docs` | Interaktywna dokumentacja REST API |

---

## Konta demo (tenant: demo)

### Administracja

| Rola | Login | Haslo | Panel | Uprawnienia |
|------|-------|-------|-------|-------------|
| **Super Admin** | `superadmin` | `super123!` | `/superadmin-ui` | Zarzadzanie tenantami, tworzenie organizacji, statystyki platformy |
| **Admin** | `admin` | `admin123` | `/admin-ui` | Zarzadzanie uzytkownikami w organizacji, konfiguracja, zatwierdzanie zamowien |
| **Buyer** | `buyer` | `buyer123` | `/ui` | Tworzenie zapotrzebowan, zamowienia z katalogu, ad hoc, CIF, marketplace |

### Dostawcy (Portal `/portal-ui`)

| Dostawca | Login | Haslo | Supplier ID | Specjalizacja |
|----------|-------|-------|-------------|---------------|
| **TRW Automotive** | `trw` | `trw123` | TRW-001 | Hamulce, zawieszenie |
| **Brembo** | `brembo` | `brembo123` | BREMBO-001 | Tarcze hamulcowe, zaciski |
| **Bosch** | `bosch` | `bosch123` | BOSCH-001 | Elektryka, elektronika OE |
| **Kraft** | `kraft` | `kraft123` | KRAFT-001 | Czesci zamienne aftermarket |

---

## Scenariusze demo

### 1. Zamowienie z katalogu (Buyer)
1. Zaloguj sie jako `buyer` / `buyer123`
2. Wejdz na `/ui` → Krok 1: Zapotrzebowanie
3. Wybierz sciezke "Z katalogu" → wybierz kategorie UNSPSC (np. 25 Pojazdy, 44 Biuro)
4. Dodaj produkty do koszyka (ilosc +/-)
5. Dalej: Dostawcy → Optymalizacja → Zamowienie

### 2. Marketplace — Allegro Search (Buyer)
1. Krok 1 → Wybierz "Marketplace"
2. Tab "Allegro" — wpisz fraze, np. `laptop`, `wiertarka`, `papier A4`
3. Wyniki z inteligentnego mock katalogu (55 produktow, tag-based scoring)
4. Dodaj produkty do koszyka — integruja sie z normalnym flow zakupowym
5. (Opcjonalnie) Klilknij "Polacz z Allegro" → autoryzacja OAuth2 → realne oferty

### 3. Marketplace — PunchOut cXML (Buyer)
1. Krok 1 → Marketplace → Tab "PunchOut cXML (Allegro)"
2. System automatycznie tworzy sesje cXML (`PunchOutSetupRequest`)
3. Wyswietla katalog z **filtrami kategorii**: IT, Biuro, Meble, BHP, Narzedzia, Czystosc, Elektro, Motoryzacja, Opakowania, Catering
4. **100+ produktow** z dwoch zrodel: Allegro mock + katalog enterprise (z numerami umow ramowych)
5. Dodaj do koszyka → "Eksportuj koszyk cXML" → generuje `PunchOutOrderMessage`
6. Przycisk "XML" → podglad surowego cXML 1.2.014

### 4. Portal dostawcy
1. Zaloguj sie jako `trw` / `trw123`
2. Wejdz na `/portal-ui`
3. Zobacz zamowienia do potwierdzenia, statusy PO, historia dostaw

### 5. Optymalizacja wielokryterialna
1. `/ui` → Krok 3: Optymalizacja
2. Wybierz domene (np. Hamulce, Oleje, IT, Biuro)
3. Suwak Lambda: 0 = minimalizacja kosztu, 1 = maksymalizacja jakosci
4. Run → Pareto front (11 punktow), alokacje dostawcow, radar chart
5. Monte Carlo → symulacja ryzyka (1000 iteracji)

### 6. Super Admin — Multi-tenant
1. Zaloguj sie jako `superadmin` / `super123!`
2. Wejdz na `/superadmin-ui`
3. Tworzenie nowych tenantow (organizacji), zarzadzanie planami
4. Statystyki platformy, zarzadzanie uzytkownikami globalnie

### 7. Upload CIF/CSV
1. Krok 1 → "Z pliku CIF / CSV"
2. Wgraj plik z pozycjami → automatyczna klasyfikacja UNSPSC
3. Pobierz szablon: `GET /api/v1/cif/template`

### 8. AI Copilot
1. Ikona czatu w prawym dolnym rogu
2. Zadaj pytanie o procurement, np. "Jaki dostawca ma najlepsza cene na klocki hamulcowe?"
3. AI (Claude/Gemini) analizuje dane i odpowiada w kontekscie

---

## API Authentication

```bash
# Login
curl -X POST https://flow-procurement.up.railway.app/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Response: {"access_token":"eyJ...", "token_type":"bearer"}

# Use token
curl https://flow-procurement.up.railway.app/api/v1/buying/catalog \
  -H "Authorization: Bearer eyJ..."

# Marketplace search (no auth required)
curl "https://flow-procurement.up.railway.app/api/v1/marketplace/allegro/search?q=laptop&limit=10"

# PunchOut session
curl -X POST https://flow-procurement.up.railway.app/api/v1/marketplace/punchout/setup
# => {"session_id":"abc12345","cxml_response":"<?xml ...>"}

curl "https://flow-procurement.up.railway.app/api/v1/marketplace/punchout/browse/abc12345?category=it"
```

---

## Klucze API (env vars)

| Zmienna | Opis | Wymagane |
|---------|------|----------|
| `FLOW_JWT_SECRET` | Secret do JWT tokenow | Tak (produkcja) |
| `FLOW_TURSO_DATABASE_URL` | Turso/LibSQL database URL | Opcjonalne |
| `FLOW_TURSO_AUTH_TOKEN` | Turso auth token | Opcjonalne |
| `FLOW_ALLEGRO_CLIENT_ID` | Allegro API Client ID (typ: przegladarka) | Opcjonalne |
| `FLOW_ALLEGRO_CLIENT_SECRET` | Allegro API Client Secret | Opcjonalne |
| `FLOW_LLM_API_KEY` | Claude API key (AI Copilot) | Opcjonalne |
| `FLOW_GEMINI_API_KEY` | Gemini API key (fallback) | Opcjonalne |

---

## Co nowego w v5.1.0

- **Welcome Dashboard** — nowa strona startowa z hero, 4 quick actions, 6 KPI, ostatnia aktywnosc, szybki dostep
- **Step 0 "Start"** — dashboard jako domyslny widok po wejsciu na /ui (gwiazda w stepper bar)
- **Quick Actions** — Nowe zapotrzebowanie, Marketplace (Allegro+PunchOut), Optymalizuj, Monitoring
- **KPI live** — dostawcy, zamowienia, katalog, wydatki, oszczednosci, compliance z API
- **Ostatnia aktywnosc** — feed ostatnich zamowien z kolorami statusow
- **Szybki dostep** — linki do Admin, Portal, API, dostawcow, ryzyka, AI Copilot
- **UX jargon removal** — usuniecie Lambda, LP relaxation, HiGHS z UI; presety optymalizacji
- **Copilot v5.1** — swiadomosc Allegro, PunchOut, marketplace

## Changelog v5.0.16

- **Allegro PunchOut cXML** — pelna integracja marketplace z filtrami kategorii
- **100+ produktow w PunchOut** — Allegro mock + enterprise catalog z umowami ramowymi
- **11 kategorii filtrowania** — IT, Biuro, BHP, Meble, Narzedzia, Czystosc, Elektro, Motoryzacja, Opakowania, Catering, HVAC
- **OAuth2 authorization_code** — poprawiony flow autoryzacji Allegro (dynamic redirect_uri)
- **Smart UNSPSC mapping** — 55 segmentow z hierarchicznym fallbackiem
- **Allegro jako fallback** — gdy katalog wewnetrzny pusty, link "Szukaj na Allegro"
- **Unified Cart** — sidebar koszyk zsynchronizowany z koszykiem marketplace/katalogu
- **Step 4 dostawcy** — tabela zamowien pokazuje dostawce, badge zrodla (Allegro/PunchOut)
- **AI Copilot v5.1** — swiadomosc Allegro, PunchOut, marketplace; nowe sugestie
- **Copilot LLM fallback** — Claude (primary) → Gemini (fallback) automatycznie
