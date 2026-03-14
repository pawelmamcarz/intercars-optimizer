"""
OSINT Risk Intelligence Engine — free public source lookups for supplier due diligence.

Sources:
  1. KRS (Krajowy Rejestr Sadowy) — rejestr.io API (free, no key required)
  2. CEIDG (Centralna Ewidencja i Informacja o Dzialalnosci Gospodarczej) — dane.biznes.gov.pl
  3. VIES (VAT Information Exchange System) — EU VAT validation
  4. GUS (Glowny Urzad Statystyczny) — REGON/BIR
  5. Transparency International CPI — country risk scoring

All lookups are best-effort: if a source is unavailable, partial results are returned.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Country risk scores (Transparency International CPI 2023 — inverted: higher = riskier)
_CPI_RISK = {
    "PL": 0.24, "DE": 0.10, "CZ": 0.28, "SK": 0.30, "HU": 0.40, "RO": 0.47,
    "BG": 0.53, "IT": 0.32, "FR": 0.14, "ES": 0.20, "UK": 0.12, "US": 0.13,
    "CN": 0.58, "TR": 0.46, "IN": 0.52, "UA": 0.55, "BY": 0.65, "RU": 0.68,
}


class OsintEngine:
    """Aggregates intelligence from free OSINT sources for supplier risk assessment."""

    @staticmethod
    async def lookup_nip(nip: str) -> dict[str, Any]:
        """Full OSINT lookup by Polish NIP number."""
        nip = re.sub(r"\D", "", nip)
        if len(nip) != 10:
            return {"error": "Invalid NIP — must be 10 digits", "nip": nip}

        results: dict[str, Any] = {
            "nip": nip,
            "lookup_timestamp": datetime.utcnow().isoformat(),
            "sources": [],
            "risk_signals": [],
            "risk_score": 0.0,  # 0 = safe, 1 = high risk
        }

        # 1. KRS via rejestr.io
        krs_data = await OsintEngine._lookup_krs(nip)
        if krs_data:
            results["krs"] = krs_data
            results["sources"].append("KRS (rejestr.io)")

        # 2. CEIDG via dane.biznes.gov.pl
        ceidg_data = await OsintEngine._lookup_ceidg(nip)
        if ceidg_data:
            results["ceidg"] = ceidg_data
            results["sources"].append("CEIDG (dane.biznes.gov.pl)")

        # 3. VIES VAT validation
        vies_data = await OsintEngine._lookup_vies(nip)
        if vies_data:
            results["vies"] = vies_data
            results["sources"].append("VIES (EU VAT)")

        # 4. Compute risk signals
        results["risk_signals"] = OsintEngine._analyze_signals(results)
        results["risk_score"] = OsintEngine._compute_risk_score(results)

        return results

    @staticmethod
    async def _lookup_krs(nip: str) -> Optional[dict]:
        """Query KRS via rejestr.io free API."""
        import urllib.request
        import json
        url = f"https://rejestr.io/api/v2/org?nip={nip}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "flow-procurement/3.3"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list) and data:
                    org = data[0]
                    return {
                        "name": org.get("name", ""),
                        "krs": org.get("krs", ""),
                        "regon": org.get("regon", ""),
                        "status": org.get("status", ""),
                        "legal_form": org.get("legalForm", ""),
                        "registration_date": org.get("registrationDate", ""),
                        "address": org.get("address", ""),
                        "capital": org.get("shareCapital", ""),
                        "pkd_main": org.get("mainPkd", ""),
                        "board_members": org.get("boardMembers", []),
                        "is_active": org.get("status", "").lower() in ("aktywny", "active", ""),
                    }
                elif isinstance(data, dict) and data.get("name"):
                    return {
                        "name": data.get("name", ""),
                        "krs": data.get("krs", ""),
                        "status": data.get("status", ""),
                        "is_active": True,
                    }
        except Exception as e:
            logger.warning("KRS lookup failed for NIP %s: %s", nip, e)
        return None

    @staticmethod
    async def _lookup_ceidg(nip: str) -> Optional[dict]:
        """Query CEIDG via dane.biznes.gov.pl (public, no key)."""
        import urllib.request
        import json
        url = f"https://dane.biznes.gov.pl/api/ceidg/v2/firma?nip={nip}"
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "flow-procurement/3.3",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                firms = data.get("firma", data) if isinstance(data, dict) else data
                if isinstance(firms, list) and firms:
                    firm = firms[0]
                    return {
                        "name": firm.get("nazwa", ""),
                        "owner": firm.get("wlasciciel", {}).get("imie", "") + " " + firm.get("wlasciciel", {}).get("nazwisko", ""),
                        "status": firm.get("status", ""),
                        "start_date": firm.get("dataRozpoczeciaDzialalnosci", ""),
                        "pkd_main": firm.get("pkd", [{}])[0].get("kod", "") if firm.get("pkd") else "",
                        "address": firm.get("adresDzialalnosci", {}).get("ulica", ""),
                        "is_active": str(firm.get("status", "")).upper() in ("AKTYWNY", "ACTIVE", "1"),
                    }
        except Exception as e:
            logger.debug("CEIDG lookup failed for NIP %s: %s", nip, e)
        return None

    @staticmethod
    async def _lookup_vies(nip: str) -> Optional[dict]:
        """Validate VAT number via VIES SOAP (simplified HTTP check)."""
        import urllib.request
        import json
        # Use ec.europa.eu VIES REST-like check
        url = f"https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
        payload = json.dumps({"countryCode": "PL", "vatNumber": nip}).encode()
        try:
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "User-Agent": "flow-procurement/3.3",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                return {
                    "valid": data.get("valid", False),
                    "name": data.get("name", ""),
                    "address": data.get("address", ""),
                    "request_date": data.get("requestDate", ""),
                }
        except Exception as e:
            logger.debug("VIES lookup failed for NIP %s: %s", nip, e)
        return None

    @staticmethod
    def _analyze_signals(results: dict) -> list[dict]:
        """Analyze gathered data for risk signals."""
        signals = []

        # KRS signals
        krs = results.get("krs")
        if krs:
            if not krs.get("is_active", True):
                signals.append({"source": "KRS", "severity": "high", "signal": "Podmiot nieaktywny lub wykreslony z rejestru"})
            reg_date = krs.get("registration_date", "")
            if reg_date:
                try:
                    rd = datetime.fromisoformat(reg_date.replace("Z", ""))
                    age_years = (datetime.utcnow() - rd).days / 365.25
                    if age_years < 1:
                        signals.append({"source": "KRS", "severity": "medium", "signal": f"Firma bardzo mloda ({age_years:.1f} lat)"})
                    elif age_years < 3:
                        signals.append({"source": "KRS", "severity": "low", "signal": f"Firma mloda ({age_years:.1f} lat)"})
                except (ValueError, TypeError):
                    pass
            capital = krs.get("capital")
            if capital and isinstance(capital, (int, float)) and capital < 50000:
                signals.append({"source": "KRS", "severity": "medium", "signal": f"Niski kapital zakladowy: {capital} PLN"})

        # CEIDG signals
        ceidg = results.get("ceidg")
        if ceidg:
            if not ceidg.get("is_active", True):
                signals.append({"source": "CEIDG", "severity": "high", "signal": "Dzialalnosc zawieszona lub wykreslona"})

        # VIES signals
        vies = results.get("vies")
        if vies:
            if not vies.get("valid", True):
                signals.append({"source": "VIES", "severity": "high", "signal": "Numer VAT nieaktywny w systemie VIES"})

        # No data at all
        if not krs and not ceidg and not vies:
            signals.append({"source": "OSINT", "severity": "medium", "signal": "Brak danych w publicznych rejestrach — weryfikacja reczna wymagana"})

        return signals

    @staticmethod
    def _compute_risk_score(results: dict) -> float:
        """Compute overall risk score 0..1 from signals."""
        severity_weights = {"high": 0.4, "medium": 0.2, "low": 0.1}
        score = 0.0
        for sig in results.get("risk_signals", []):
            score += severity_weights.get(sig.get("severity", "low"), 0.1)
        return round(min(score, 1.0), 2)

    @staticmethod
    async def lookup_company_name(name: str, country: str = "PL") -> dict[str, Any]:
        """OSINT lookup by company name (less precise than NIP)."""
        import urllib.request
        import json
        results: dict[str, Any] = {
            "query": name,
            "country": country,
            "lookup_timestamp": datetime.utcnow().isoformat(),
            "sources": [],
            "matches": [],
            "country_risk": _CPI_RISK.get(country.upper(), 0.5),
        }

        # Try rejestr.io name search
        try:
            encoded_name = urllib.request.quote(name)
            url = f"https://rejestr.io/api/v2/org?name={encoded_name}"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "flow-procurement/3.3"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    results["matches"] = [{"name": o.get("name", ""), "nip": o.get("nip", ""), "krs": o.get("krs", ""), "status": o.get("status", "")} for o in data[:10]]
                    results["sources"].append("KRS (rejestr.io)")
        except Exception as e:
            logger.debug("Name search failed: %s", e)

        return results

    @staticmethod
    def demo_lookup(nip: str) -> dict[str, Any]:
        """Synchronous demo lookup with simulated data (for offline/testing)."""
        nip = re.sub(r"\D", "", nip)
        # Deterministic demo data from NIP hash
        h = int(hashlib.md5(nip.encode()).hexdigest()[:8], 16)
        age_years = (h % 20) + 1
        capital = (h % 500 + 5) * 1000
        is_active = (h % 10) > 1  # 80% active
        vat_valid = (h % 10) > 0  # 90% valid

        signals = []
        if not is_active:
            signals.append({"source": "KRS", "severity": "high", "signal": "Podmiot nieaktywny w KRS (DEMO)"})
        if age_years < 2:
            signals.append({"source": "KRS", "severity": "medium", "signal": f"Firma mloda: {age_years} lat (DEMO)"})
        if capital < 50000:
            signals.append({"source": "KRS", "severity": "medium", "signal": f"Niski kapital: {capital} PLN (DEMO)"})
        if not vat_valid:
            signals.append({"source": "VIES", "severity": "high", "signal": "VAT nieaktywny (DEMO)"})

        score = sum(0.4 if s["severity"] == "high" else 0.2 if s["severity"] == "medium" else 0.1 for s in signals)

        return {
            "nip": nip,
            "demo": True,
            "lookup_timestamp": datetime.utcnow().isoformat(),
            "sources": ["KRS (demo)", "CEIDG (demo)", "VIES (demo)"],
            "krs": {
                "name": f"Demo Firma {nip[-4:]} Sp. z o.o.",
                "krs": f"{h % 999999:06d}",
                "regon": f"{h % 999999999:09d}",
                "status": "AKTYWNY" if is_active else "WYKRESLONY",
                "registration_date": (datetime.utcnow() - timedelta(days=age_years * 365)).strftime("%Y-%m-%d"),
                "capital": capital,
                "is_active": is_active,
            },
            "vies": {"valid": vat_valid, "name": f"Demo Firma {nip[-4:]}"},
            "risk_signals": signals,
            "risk_score": round(min(score, 1.0), 2),
        }
