# Flow Procurement Platform — Demo Access Guide

**Production:** https://flow-procurement.up.railway.app
**Version:** 5.0.7
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

| Rola | Login | Haslo | Uprawnienia |
|------|-------|-------|-------------|
| **Super Admin** | `superadmin` | `super123!` | Zarzadzanie tenantami, tworzenie organizacji, statystyki platformy |
| **Admin** | `admin` | `admin123` | Zarzadzanie uzytkownikami w organizacji, konfiguracja, zatwierdzanie zamowien |
| **Buyer** | `buyer` | `buyer123` | Tworzenie zapotrzebowan, zamowienia z katalogu, ad hoc, CIF, marketplace |

### Dostawcy (Portal)

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
3. Wybierz kategorie UNSPSC (np. 251010 Samochody)
4. Dodaj produkty do koszyka → Dalej: Dostawcy → Optymalizacja → Zamowienie

### 2. Marketplace / Allegro (Buyer)
1. Krok 1 → Wybierz "Marketplace"
2. Allegro: wpisz fraze i szukaj (mock w trybie demo)
3. PunchOut: przegladaj katalog zewnetrzny (cXML demo)
4. Dodaj produkty do koszyka — integruja sie z normalnym flow

### 3. Portal dostawcy
1. Zaloguj sie jako `trw` / `trw123`
2. Wejdz na `/portal-ui`
3. Zobacz zamowienia do potwierdzenia, statusy PO

### 4. Optymalizacja (dowolny user)
1. `/ui` → Krok 3: Optymalizacja
2. Wybierz domene (np. Hamulce, Oleje, IT)
3. Suwak Lambda: 0=koszt, 1=jakosc
4. Run → Pareto front, alokacje, radar

### 5. Super Admin — Multi-tenant
1. Zaloguj sie jako `superadmin` / `super123!`
2. Wejdz na `/superadmin-ui`
3. Tworzenie nowych tenantow (organizacji)
4. Statystyki platformy, zarzadzanie uzytkownikami

### 6. Upload CIF/CSV
1. Krok 1 → "Z pliku CIF / CSV"
2. Wgraj plik z pozycjami → automatyczna klasyfikacja UNSPSC
3. Pobierz szablon: `/api/v1/cif/template`

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
```

---

## Klucze API (env vars)

| Zmienna | Opis | Wymagane |
|---------|------|----------|
| `FLOW_JWT_SECRET` | Secret do JWT tokenow | Tak (produkcja) |
| `FLOW_TURSO_DATABASE_URL` | Turso/LibSQL database URL | Opcjonalne |
| `FLOW_TURSO_AUTH_TOKEN` | Turso auth token | Opcjonalne |
| `FLOW_ALLEGRO_CLIENT_ID` | Allegro API Client ID | Opcjonalne |
| `FLOW_ALLEGRO_CLIENT_SECRET` | Allegro API Client Secret | Opcjonalne |
| `FLOW_LLM_API_KEY` | Claude API key (AI Copilot) | Opcjonalne |
| `FLOW_GEMINI_API_KEY` | Gemini API key (fallback) | Opcjonalne |
