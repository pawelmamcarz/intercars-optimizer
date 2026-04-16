"""
Prediction & AI Copilot API Routes — v4.1
"""

from fastapi import APIRouter, HTTPException

from app.prediction_engine import (
    PredictionInput,
    build_supplier_profiles,
    predict_delay,
    generate_predictive_alerts,
    generate_demo_events,
    generate_demo_profiles,
    generate_demo_predictions,
)
from app.copilot_engine import CopilotRequest, get_recommendations, process_message

prediction_router = APIRouter(tags=["Predictive Analytics & AI Copilot"])


# ── Predictive Analytics ─────────────────────────────────────────

@prediction_router.get("/predictions/demo", response_model=dict)
async def api_demo_predictions():
    """Demo predykcje opóźnień dla przykładowych zamówień."""
    predictions = generate_demo_predictions()
    profiles = generate_demo_profiles()
    alerts = generate_predictive_alerts(profiles)
    return {
        "predictions": [p.model_dump() for p in predictions],
        "alerts": [a.model_dump() for a in alerts],
        "profiles": {k: v.model_dump() for k, v in profiles.items()},
        "event_count": len(generate_demo_events()),
    }


@prediction_router.post("/predictions/predict", response_model=dict)
async def api_predict_delay(inp: PredictionInput):
    """Predykcja opóźnienia dla konkretnego zamówienia."""
    profiles = generate_demo_profiles()  # In production: load from DB
    prediction = predict_delay(inp, profiles)
    return {"prediction": prediction.model_dump()}


@prediction_router.post("/predictions/train", response_model=dict)
async def api_train_model(events: list[dict] = None):
    """Trenuj model na danych zdarzeń P2P. Zwraca profile dostawców."""
    if not events:
        events = generate_demo_events()
    profiles = build_supplier_profiles(events)
    return {
        "success": True,
        "profiles_count": len(profiles),
        "profiles": {k: v.model_dump() for k, v in profiles.items()},
        "events_processed": len(events),
    }


@prediction_router.get("/predictions/alerts", response_model=dict)
async def api_predictive_alerts():
    """Alerty predykcyjne na bazie profili dostawców."""
    profiles = generate_demo_profiles()
    alerts = generate_predictive_alerts(profiles)
    return {
        "alerts": [a.model_dump() for a in alerts],
        "total": len(alerts),
        "by_severity": {
            "critical": len([a for a in alerts if a.severity == "critical"]),
            "high": len([a for a in alerts if a.severity == "high"]),
            "medium": len([a for a in alerts if a.severity == "medium"]),
            "low": len([a for a in alerts if a.severity == "low"]),
        },
    }


@prediction_router.get("/predictions/profiles", response_model=dict)
async def api_supplier_profiles():
    """Profile wydajności dostawców zbudowane z historii P2P."""
    profiles = generate_demo_profiles()
    return {
        "profiles": {k: v.model_dump() for k, v in profiles.items()},
        "total": len(profiles),
    }


# ── AI Copilot ───────────────────────────────────────────────────

@prediction_router.post("/copilot/chat", response_model=dict)
async def api_copilot_chat(req: CopilotRequest):
    """AI Copilot — asystent zakupowy w języku naturalnym."""
    response = await process_message(req)
    return response.model_dump()


@prediction_router.get("/copilot/recommendations", response_model=dict)
async def api_copilot_recommendations(step: int = 0, domain: str = ""):
    """Proactive action cards for the assistant dashboard (Step 0).

    Mixes real signals (pending approvals from buying_engine) with static
    demo stubs for contract expiry, spend trends, and single-source risk.
    MVP-4 will swap internals for RecommendationEngine with contracts + BI.
    """
    return {
        "step": step,
        "domain": domain,
        "cards": get_recommendations({"step": step, "domain": domain}),
    }


@prediction_router.get("/copilot/suggestions", response_model=dict)
async def api_copilot_suggestions(step: int = 1, domain: str = "parts"):
    """Kontekstowe sugestie AI Copilot dla danego kroku."""
    suggestions_map = {
        1: [
            "Szukaj na Allegro: laptop, wiertarka, papier A4",
            "Pokaż katalog hamulców",
            "Jak dodać produkt do koszyka?",
            "Szukaj kategorii UNSPSC",
        ],
        2: [
            "Filtruj dostawców z certyfikatem ISO 9001",
            "Pokaż tylko dostawców z regionu PL",
            "Który dostawca ma najlepsze ESG?",
            "Sprawdź VAT dostawcy w systemie VIES",
        ],
        3: [
            "Uruchom optymalizację z lambda=0.6",
            "Porównaj scenariusze: tani vs jakościowy",
            "Wyjaśnij front Pareto",
            "Jakie constrainty są aktywne?",
        ],
        4: [
            "Pokaż status zamówień",
            "Utwórz nową aukcję odwróconą",
            "Ile wynoszą oszczędności vs ceny katalogowe?",
        ],
        5: [
            "Pokaż alerty predykcyjne ML",
            "Uruchom symulację Monte Carlo",
            "Wyjaśnij graf DFG",
            "Którzy dostawcy mają trend spadkowy?",
        ],
    }
    return {
        "step": step,
        "domain": domain,
        "suggestions": suggestions_map.get(step, suggestions_map[1]),
    }
