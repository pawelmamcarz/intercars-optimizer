"""
Predictive Analytics Engine — v4.1

Od Process Mining (analiza wsteczna) do Process Prediction (analiza predykcyjna).
Wykorzystuje dane historyczne z p2p_events do przewidywania opóźnień, ryzyka i rekomendacji.

Model: Ensemble (statistics-based + heuristic scoring).
W przyszłości: XGBoost / Random Forest po zebraniu wystarczającej ilości danych.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel


# ── Models ───────────────────────────────────────────────────────

class PredictionInput(BaseModel):
    supplier_id: str
    product_id: str = ""
    domain: str = "parts"
    quantity: float = 100
    destination_region: str = "PL"
    order_value_pln: float = 0.0


class DelayPrediction(BaseModel):
    supplier_id: str
    product_id: str
    probability_delay: float  # 0-1
    predicted_delay_days: float
    confidence: float  # 0-1
    risk_level: str  # low, medium, high, critical
    factors: list[dict]  # contributing factors
    recommendation: str
    alternative_suppliers: list[dict] = []


class SupplierPerformanceProfile(BaseModel):
    supplier_id: str
    supplier_name: str = ""
    total_orders: int = 0
    on_time_rate: float = 0.0
    avg_delay_days: float = 0.0
    delay_std_days: float = 0.0
    avg_lead_time_days: float = 0.0
    quality_score: float = 0.0  # from rework rate
    seasonal_risk: dict = {}  # month -> risk multiplier
    trend: str = ""  # improving, stable, declining


class PredictiveAlert(BaseModel):
    alert_id: str = ""
    severity: str = "medium"  # low, medium, high, critical
    alert_type: str = ""  # delay_risk, quality_risk, capacity_risk, seasonal_risk
    title: str = ""
    description: str = ""
    supplier_id: str = ""
    probability: float = 0.0
    impact_pln: float = 0.0
    recommendation: str = ""
    created_at: str = ""


# ── Training / Profile Building ──────────────────────────────────

def build_supplier_profiles(events: list[dict]) -> dict[str, SupplierPerformanceProfile]:
    """Buduje profile wydajności dostawców z historii zdarzeń P2P."""
    # Group events by case
    cases: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        cases[e.get("case_id", "")].append(e)

    # Analyze per supplier
    supplier_stats: dict[str, dict] = defaultdict(lambda: {
        "orders": 0, "delays": 0, "delay_days": [], "lead_times": [],
        "rework_count": 0, "monthly_delays": defaultdict(int),
        "monthly_orders": defaultdict(int),
    })

    for case_id, case_events in cases.items():
        sorted_events = sorted(case_events, key=lambda e: e.get("timestamp", ""))
        if not sorted_events:
            continue

        # Extract supplier from resource or case metadata
        supplier_id = ""
        for ev in sorted_events:
            res = ev.get("resource", "")
            # Skip buyer resources (buyer_1, buyer_2, etc.)
            if res and not res.startswith("buyer_"):
                supplier_id = res
                break
        if not supplier_id:
            # Use case_id prefix as supplier hint
            supplier_id = case_id.split("-")[0] if "-" in case_id else "UNKNOWN"

        stats = supplier_stats[supplier_id]
        stats["orders"] += 1

        # Calculate lead time (first to last event)
        try:
            start = datetime.fromisoformat(sorted_events[0]["timestamp"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(sorted_events[-1]["timestamp"].replace("Z", "+00:00"))
            lt_days = (end - start).total_seconds() / 86400
            stats["lead_times"].append(lt_days)

            # Monthly tracking
            month = start.month
            stats["monthly_orders"][month] += 1
        except (ValueError, KeyError):
            pass

        # Check for delays (heuristic: if "Opóźnienie" or "Delay" in activity)
        for ev in sorted_events:
            act = ev.get("activity", "").lower()
            if "opóźni" in act or "delay" in act or "late" in act:
                stats["delays"] += 1
                # Estimate delay from next event gap
                idx = sorted_events.index(ev)
                if idx < len(sorted_events) - 1:
                    try:
                        t1 = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
                        t2 = datetime.fromisoformat(sorted_events[idx+1]["timestamp"].replace("Z", "+00:00"))
                        stats["delay_days"].append((t2 - t1).total_seconds() / 86400)
                    except (ValueError, KeyError):
                        stats["delay_days"].append(2.0)
                try:
                    month = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")).month
                    stats["monthly_delays"][month] += 1
                except (ValueError, KeyError):
                    pass

            if "rework" in act or "powtórz" in act or "korekta" in act:
                stats["rework_count"] += 1

    # Build profiles
    profiles = {}
    for sid, stats in supplier_stats.items():
        n = stats["orders"]
        delays = stats["delay_days"]
        lts = stats["lead_times"]

        # Seasonal risk
        seasonal = {}
        for month in range(1, 13):
            orders = stats["monthly_orders"].get(month, 0)
            delay_count = stats["monthly_delays"].get(month, 0)
            if orders > 0:
                seasonal[month] = round(delay_count / orders, 2)

        # Trend (compare first half vs second half of delays)
        trend = "stable"
        if len(delays) >= 4:
            mid = len(delays) // 2
            first_avg = sum(delays[:mid]) / mid
            second_avg = sum(delays[mid:]) / (len(delays) - mid)
            if second_avg > first_avg * 1.2:
                trend = "declining"
            elif second_avg < first_avg * 0.8:
                trend = "improving"

        profiles[sid] = SupplierPerformanceProfile(
            supplier_id=sid,
            total_orders=n,
            on_time_rate=round(1 - stats["delays"] / n, 3) if n > 0 else 1.0,
            avg_delay_days=round(sum(delays) / len(delays), 1) if delays else 0.0,
            delay_std_days=round(_std(delays), 1) if len(delays) > 1 else 0.0,
            avg_lead_time_days=round(sum(lts) / len(lts), 1) if lts else 0.0,
            quality_score=round(1 - stats["rework_count"] / n, 3) if n > 0 else 1.0,
            seasonal_risk=seasonal,
            trend=trend,
        )

    return profiles


def predict_delay(
    inp: PredictionInput,
    profiles: dict[str, SupplierPerformanceProfile],
    all_suppliers: list[dict] = None,
) -> DelayPrediction:
    """Przewiduje prawdopodobieństwo opóźnienia dla zamówienia."""
    profile = profiles.get(inp.supplier_id)
    factors = []

    if not profile:
        # Unknown supplier — high uncertainty
        return DelayPrediction(
            supplier_id=inp.supplier_id,
            product_id=inp.product_id,
            probability_delay=0.5,
            predicted_delay_days=3.0,
            confidence=0.2,
            risk_level="medium",
            factors=[{"factor": "Brak danych historycznych", "weight": 1.0, "detail": "Nowy dostawca bez historii"}],
            recommendation="Brak danych historycznych — zalecana ostrożność i monitoring.",
        )

    # Base probability from historical on-time rate
    base_prob = 1 - profile.on_time_rate
    factors.append({
        "factor": "Historyczna terminowość",
        "weight": 0.35,
        "detail": f"On-time rate: {profile.on_time_rate*100:.0f}%",
        "value": base_prob,
    })

    # Seasonal adjustment
    current_month = datetime.now(timezone.utc).month
    seasonal_risk = profile.seasonal_risk.get(current_month, 0)
    if seasonal_risk > 0.2:
        factors.append({
            "factor": "Ryzyko sezonowe",
            "weight": 0.20,
            "detail": f"Miesiąc {current_month}: historyczny wskaźnik opóźnień {seasonal_risk*100:.0f}%",
            "value": seasonal_risk,
        })
    else:
        seasonal_risk = 0

    # Trend adjustment
    trend_adj = 0
    if profile.trend == "declining":
        trend_adj = 0.15
        factors.append({
            "factor": "Trend spadkowy",
            "weight": 0.15,
            "detail": "Pogorszenie terminowości w ostatnim okresie",
            "value": trend_adj,
        })
    elif profile.trend == "improving":
        trend_adj = -0.10
        factors.append({
            "factor": "Trend wzrostowy",
            "weight": 0.10,
            "detail": "Poprawa terminowości w ostatnim okresie",
            "value": trend_adj,
        })

    # Order size risk
    size_adj = 0
    if inp.quantity > 500:
        size_adj = 0.05
        factors.append({
            "factor": "Duże zamówienie",
            "weight": 0.10,
            "detail": f"Ilość: {inp.quantity} — większe ryzyko logistyczne",
            "value": size_adj,
        })

    # Quality risk from rework rate
    quality_adj = 0
    if profile.quality_score < 0.90:
        quality_adj = (1 - profile.quality_score) * 0.5
        factors.append({
            "factor": "Ryzyko jakościowe",
            "weight": 0.15,
            "detail": f"Quality score: {profile.quality_score*100:.0f}% (rework history)",
            "value": quality_adj,
        })

    # Composite probability
    prob = min(0.99, max(0.01,
        base_prob * 0.35 +
        seasonal_risk * 0.20 +
        trend_adj * 0.15 +
        size_adj * 0.10 +
        quality_adj * 0.15 +
        0.05  # base uncertainty
    ))

    # Predicted delay
    pred_delay = profile.avg_delay_days * (1 + seasonal_risk) if prob > 0.3 else profile.avg_delay_days * 0.5

    # Confidence based on data volume
    confidence = min(0.95, profile.total_orders / 50)

    # Risk level
    if prob >= 0.70:
        risk = "critical"
    elif prob >= 0.50:
        risk = "high"
    elif prob >= 0.25:
        risk = "medium"
    else:
        risk = "low"

    # Recommendation
    rec = _generate_recommendation(prob, pred_delay, profile, inp)

    # Alternative suppliers
    alternatives = []
    if all_suppliers and prob > 0.3:
        for s in all_suppliers:
            sid = s.get("supplier_id", "")
            if sid == inp.supplier_id:
                continue
            alt_profile = profiles.get(sid)
            if alt_profile and alt_profile.on_time_rate > profile.on_time_rate:
                alternatives.append({
                    "supplier_id": sid,
                    "supplier_name": s.get("name", sid),
                    "on_time_rate": alt_profile.on_time_rate,
                    "avg_lead_time": alt_profile.avg_lead_time_days,
                    "suggested_allocation_pct": 30 if prob > 0.5 else 15,
                })
        alternatives = sorted(alternatives, key=lambda x: -x["on_time_rate"])[:3]

    return DelayPrediction(
        supplier_id=inp.supplier_id,
        product_id=inp.product_id,
        probability_delay=round(prob, 3),
        predicted_delay_days=round(pred_delay, 1),
        confidence=round(confidence, 2),
        risk_level=risk,
        factors=factors,
        recommendation=rec,
        alternative_suppliers=alternatives,
    )


def generate_predictive_alerts(
    profiles: dict[str, SupplierPerformanceProfile],
    active_orders: list[dict] = None,
) -> list[PredictiveAlert]:
    """Generuje alerty predykcyjne na bazie profili dostawców."""
    alerts = []
    now = datetime.now(timezone.utc)
    current_month = now.month

    for sid, p in profiles.items():
        # Alert: wysoka częstotliwość opóźnień
        if p.on_time_rate < 0.70:
            alerts.append(PredictiveAlert(
                alert_id=f"PA-{len(alerts)+1:04d}",
                severity="critical" if p.on_time_rate < 0.50 else "high",
                alert_type="delay_risk",
                title=f"Wysokie ryzyko opóźnień — {sid}",
                description=f"Dostawca {sid} ma on-time rate {p.on_time_rate*100:.0f}% "
                           f"(avg opóźnienie: {p.avg_delay_days:.1f} dni). "
                           f"Trend: {p.trend}.",
                supplier_id=sid,
                probability=round(1 - p.on_time_rate, 2),
                recommendation="Sugerujemy ograniczenie alokacji do max 30% i dywersyfikację "
                              "na alternatywnych dostawców.",
                created_at=now.isoformat(),
            ))

        # Alert: sezonowość
        seasonal = p.seasonal_risk.get(current_month, 0)
        if seasonal > 0.3:
            alerts.append(PredictiveAlert(
                alert_id=f"PA-{len(alerts)+1:04d}",
                severity="high" if seasonal > 0.5 else "medium",
                alert_type="seasonal_risk",
                title=f"Ryzyko sezonowe — {sid} (miesiąc {current_month})",
                description=f"W miesiącu {current_month} historyczny wskaźnik opóźnień "
                           f"wynosi {seasonal*100:.0f}% dla dostawcy {sid}.",
                supplier_id=sid,
                probability=round(seasonal, 2),
                recommendation="Zalecamy złożenie zamówień z wyprzedzeniem 2 tygodni "
                              "lub przerzucenie części wolumenu na dostawców bez ryzyka sezonowego.",
                created_at=now.isoformat(),
            ))

        # Alert: trend spadkowy
        if p.trend == "declining" and p.total_orders >= 5:
            alerts.append(PredictiveAlert(
                alert_id=f"PA-{len(alerts)+1:04d}",
                severity="medium",
                alert_type="quality_risk",
                title=f"Pogorszenie wydajności — {sid}",
                description=f"Dostawca {sid} wykazuje trend spadkowy w terminowości dostaw. "
                           f"Quality score: {p.quality_score*100:.0f}%.",
                supplier_id=sid,
                probability=0.4,
                recommendation="Zalecamy spotkanie z dostawcą w celu przeglądu KPI "
                              "i ustalenia planu naprawczego.",
                created_at=now.isoformat(),
            ))

    return sorted(alerts, key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.severity, 4))


def _generate_recommendation(prob: float, delay: float, profile: SupplierPerformanceProfile, inp: PredictionInput) -> str:
    if prob >= 0.7:
        return (
            f"WYSOKIE RYZYKO: Istnieje {prob*100:.0f}% prawdopodobieństwo opóźnienia o ~{delay:.0f} dni. "
            f"Sugerujemy przerzucenie 30-50% alokacji na alternatywnego dostawcę "
            f"lub złożenie zamówienia z {max(3, int(delay)+2)}-dniowym wyprzedzeniem."
        )
    elif prob >= 0.4:
        return (
            f"UMIARKOWANE RYZYKO: Prawdopodobieństwo opóźnienia {prob*100:.0f}% (~{delay:.0f} dni). "
            f"Zalecamy monitoring statusu dostawy i przygotowanie planu awaryjnego."
        )
    elif prob >= 0.2:
        return (
            f"NISKIE RYZYKO: Prawdopodobieństwo opóźnienia {prob*100:.0f}%. "
            f"Dostawca {inp.supplier_id} jest generalnie terminowy."
        )
    else:
        return f"MINIMALNIE RYZYKO: Dostawca {inp.supplier_id} ma doskonałą terminowość ({profile.on_time_rate*100:.0f}%)."


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


# ── Demo data ────────────────────────────────────────────────────

def generate_demo_events() -> list[dict]:
    """Generuje realistyczne demo zdarzenia P2P z opóźnieniami i wzorcami sezonowymi."""
    events = []
    random.seed(42)

    suppliers = [
        ("TRW-001", "TRW Automotive", 0.88, 7),
        ("BOSCH-001", "Bosch Aftermarket", 0.92, 10),
        ("BREMBO-001", "Brembo Poland", 0.75, 8),  # problematic
        ("KRAFT-001", "KraftPol", 0.95, 5),
        ("LUMAG-001", "LuMag Parts", 0.60, 12),   # very problematic
        ("CASTROL-001", "Castrol Polska", 0.85, 6),
    ]

    activities = [
        "Utworzenie Zapotrzebowania",
        "Zatwierdzenie Zapotrzebowania",
        "Wysłanie RFQ",
        "Otrzymanie Oferty",
        "Wybór Dostawcy",
        "Złożenie Zamówienia",
        "Potwierdzenie Zamówienia",
        "Wysyłka Towaru",
        "Przyjęcie Towaru",
        "Weryfikacja Jakości",
        "Zamknięcie Zamówienia",
    ]

    case_num = 0
    for month in range(1, 13):
        orders_this_month = random.randint(8, 15)
        for _ in range(orders_this_month):
            case_num += 1
            sid, sname, on_time_rate, base_lt = random.choice(suppliers)

            # Seasonal delay risk (Q4 = higher)
            seasonal_mult = 1.3 if month in (10, 11, 12) else 1.0
            is_delayed = random.random() > on_time_rate * (1 / seasonal_mult)

            base_date = datetime(2025, month, random.randint(1, 28), 9, 0)
            case_id = f"REQ-2025-{case_num:04d}"

            for i, act in enumerate(activities):
                hours_offset = i * (base_lt / len(activities) * 24)
                if is_delayed and i >= 7:  # delay after "Wysyłka Towaru"
                    delay = random.uniform(1, 6) * 24
                    hours_offset += delay
                    if i == 7:
                        # Add delay event
                        events.append({
                            "case_id": case_id,
                            "activity": "Opóźnienie Dostawy",
                            "timestamp": (base_date + timedelta(hours=hours_offset - delay/2)).isoformat() + "Z",
                            "resource": sid,
                            "cost": 0,
                        })

                # Add rework for problematic suppliers
                if act == "Weryfikacja Jakości" and random.random() > on_time_rate + 0.05:
                    events.append({
                        "case_id": case_id,
                        "activity": "Korekta Jakościowa / Rework",
                        "timestamp": (base_date + timedelta(hours=hours_offset + 12)).isoformat() + "Z",
                        "resource": sid,
                        "cost": random.uniform(50, 500),
                    })

                events.append({
                    "case_id": case_id,
                    "activity": act,
                    "timestamp": (base_date + timedelta(hours=hours_offset)).isoformat() + "Z",
                    "resource": sid if i >= 5 else f"buyer_{random.randint(1,3)}",
                    "cost": random.uniform(10, 200) if i == 5 else 0,
                })

    return events


def generate_demo_profiles() -> dict[str, SupplierPerformanceProfile]:
    """Generuje demo profile z demo zdarzeń."""
    events = generate_demo_events()
    return build_supplier_profiles(events)


def generate_demo_predictions() -> list[DelayPrediction]:
    """Generuje demo predykcje dla aktywnych zamówień."""
    profiles = generate_demo_profiles()

    test_orders = [
        PredictionInput(supplier_id="BREMBO-001", product_id="BRK-001", domain="parts", quantity=800),
        PredictionInput(supplier_id="LUMAG-001", product_id="FLT-002", domain="parts", quantity=1200),
        PredictionInput(supplier_id="TRW-001", product_id="BRK-003", domain="parts", quantity=200),
        PredictionInput(supplier_id="BOSCH-001", product_id="ELC-001", domain="oe_components", quantity=500),
        PredictionInput(supplier_id="KRAFT-001", product_id="BDY-001", domain="bodywork", quantity=100),
    ]

    suppliers_list = [
        {"supplier_id": "TRW-001", "name": "TRW Automotive"},
        {"supplier_id": "BOSCH-001", "name": "Bosch Aftermarket"},
        {"supplier_id": "BREMBO-001", "name": "Brembo Poland"},
        {"supplier_id": "KRAFT-001", "name": "KraftPol"},
        {"supplier_id": "LUMAG-001", "name": "LuMag Parts"},
        {"supplier_id": "CASTROL-001", "name": "Castrol Polska"},
    ]

    return [predict_delay(inp, profiles, suppliers_list) for inp in test_orders]
