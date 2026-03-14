"""
AI Copilot Engine — v4.1

Inteligentny asystent zakupowy zintegrowany z guided procurement wizard.
Obsługuje zapytania w języku naturalnym i tłumaczy je na akcje systemowe.

Tryby:
1. Query → parametry optymalizacji (NLP → solver config)
2. Explain → tłumaczenie wyników analiz na prosty tekst
3. Recommend → rekomendacje na bazie danych i profili dostawców
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Models ───────────────────────────────────────────────────────

class CopilotMessage(BaseModel):
    role: str = "user"  # user, assistant, system
    content: str
    timestamp: str = ""
    context: dict = {}   # metadata (step, domain, etc.)


class CopilotRequest(BaseModel):
    message: str
    context: dict = {}   # current state: step, domain, selected_suppliers, etc.
    history: list[CopilotMessage] = []  # conversation history (last N)


class CopilotAction(BaseModel):
    action_type: str = ""  # navigate, optimize, filter, explain, recommend, none
    params: dict = {}      # action-specific parameters
    confidence: float = 0.0


class CopilotResponse(BaseModel):
    reply: str
    actions: list[CopilotAction] = []
    suggestions: list[str] = []  # follow-up suggestions
    data: dict = {}              # any structured data to display


# ── Intent patterns (rule-based NLP) ────────────────────────────

_INTENT_PATTERNS = [
    # Optimization intents
    (r"optymali(zuj|zacja|zować).*filtr", "optimize_category", {"domain": "parts", "unspsc": "25101500"}),
    (r"optymali(zuj|zacja|zować).*hamulc", "optimize_category", {"domain": "parts", "unspsc": "25101500"}),
    (r"optymali(zuj|zacja|zować).*olej", "optimize_category", {"domain": "oils", "unspsc": "15121500"}),
    (r"optymali(zuj|zacja|zować).*opon", "optimize_category", {"domain": "tires", "unspsc": "25171500"}),
    (r"optymali(zuj|zacja|zować).*akumulator", "optimize_category", {"domain": "batteries", "unspsc": "25172000"}),
    (r"optymali(zuj|zacja|zować).*IT", "optimize_category", {"domain": "it_services", "unspsc": "43211500"}),

    # Filter intents
    (r"(tylko|filtruj|ogranicz).*(zielon|ESG|ekolog)", "filter_esg", {"min_esg": 0.80}),
    (r"(tylko|filtruj|ogranicz).*(certyfik|ISO|IATF)", "filter_certified", {}),
    (r"(tylko|filtruj|ogranicz).*(polsk|PL|krajow)", "filter_region", {"region": "PL"}),
    (r"(tylko|filtruj|ogranicz).*(niemieck|DE)", "filter_region", {"region": "DE"}),
    (r"SLA\s*[>>=]\s*(\d+)", "filter_sla", {}),

    # Navigation intents
    (r"(pokaż|przejdź|otwórz).*(dostawc|krok\s*2)", "navigate", {"step": 2}),
    (r"(pokaż|przejdź|otwórz).*(optymalizacj|solver|krok\s*3)", "navigate", {"step": 3}),
    (r"(pokaż|przejdź|otwórz).*(zamówien|koszyk|krok\s*4)", "navigate", {"step": 4}),
    (r"(pokaż|przejdź|otwórz).*(monitor|proces|mining|krok\s*5)", "navigate", {"step": 5}),
    (r"(pokaż|przejdź|otwórz).*(aukcj|licytacj)", "navigate", {"tab": "auctions"}),
    (r"(pokaż|przejdź|otwórz).*(predyk|prognoz|ML)", "navigate", {"tab": "predictions"}),

    # Query intents
    (r"(ile|który|jaki).*dostawc.*najlepszy", "query_best_supplier", {}),
    (r"(ile|który|jaki).*najtańsz", "query_cheapest", {}),
    (r"(ile|który|jaki).*najszybsz", "query_fastest", {}),
    (r"(ile|który|jaki).*ryzyko", "query_risk", {}),
    (r"(ile|jaka).*oszczędnoś", "query_savings", {}),

    # Explain intents
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*pareto", "explain", {"topic": "pareto"}),
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*monte\s*carlo", "explain", {"topic": "monte_carlo"}),
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*DFG", "explain", {"topic": "dfg"}),
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*alokacj", "explain", {"topic": "allocation"}),
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*lambda", "explain", {"topic": "lambda"}),
    (r"(wyjaśnij|wytłumacz|co\s+to|co\s+znaczy).*constraint", "explain", {"topic": "constraints"}),

    # Koszyk intent
    (r"(przygotuj|zrób|stwórz).*(koszyk|zamówienie).*filtr.*olej", "build_cart", {"products": ["FLT-001", "FLT-002"]}),
    (r"(przygotuj|zrób|stwórz).*(koszyk|zamówienie)", "build_cart", {}),

    # Auction intent
    (r"(utwórz|stwórz|nowa).*(aukcj|licytacj)", "create_auction", {}),
]

# ── Explanation templates ────────────────────────────────────────

_EXPLANATIONS = {
    "pareto": (
        "**Front Pareto** to zbiór optymalnych rozwiązań, gdzie nie można poprawić jednego "
        "kryterium bez pogorszenia innego. W naszym przypadku:\n\n"
        "- Oś X: parametr **lambda** (λ) — balans koszt vs jakość\n"
        "- λ=0: pełna optymalizacja jakości (compliance + ESG)\n"
        "- λ=1: pełna optymalizacja kosztu\n\n"
        "Każdy punkt na krzywej to inna alokacja dostawców. Krzywa pozwala kupcowi wybrać "
        "kompromis, który najlepiej pasuje do strategii zakupowej."
    ),
    "monte_carlo": (
        "**Symulacja Monte Carlo** to metoda oceny ryzyka cenowego. System uruchamia "
        "solver **1000 razy** z losowymi zaburzeniami kosztów i czasów dostawy.\n\n"
        "Wyniki:\n"
        "- **P5/P95** — 90% szans, że koszt będzie w tym przedziale\n"
        "- **Robustness score** — % symulacji, w których solver znalazł rozwiązanie\n"
        "- **Supplier stability** — jak często dany dostawca jest wybierany\n\n"
        "Im wyższy robustness score, tym bardziej odporna jest alokacja na wahania rynkowe."
    ),
    "dfg": (
        "**DFG (Directly-Follows Graph)** to mapa przepływu procesu P2P. Każdy węzeł to "
        "aktywność (np. 'Złożenie Zamówienia'), a strzałki pokazują kolejność i częstotliwość.\n\n"
        "Grube strzałki = częste przejścia. Czerwone węzły = wąskie gardła (bottlenecki).\n\n"
        "DFG pozwala zidentyfikować, gdzie proces 'się zatyka' i które kroki zajmują najwięcej czasu."
    ),
    "allocation": (
        "**Alokacja** to wynik optymalizacji — mówi ile procent zamówienia na dany produkt "
        "powinno trafić do którego dostawcy.\n\n"
        "Np. 'TRW: 60%, Bosch: 40%' oznacza split zamówienia między dwóch dostawców. "
        "Solver dzieli zamówienia tak, aby zminimalizować łączny koszt przy zachowaniu "
        "dywersyfikacji i spełnieniu wszystkich constraintów."
    ),
    "lambda": (
        "**Lambda (λ)** to parametr trade-off między kosztem a jakością:\n\n"
        "- **λ = 1.0** → solver minimalizuje tylko koszt (najtańsza opcja)\n"
        "- **λ = 0.0** → solver maksymalizuje compliance i ESG (najlepsza jakość)\n"
        "- **λ = 0.5** → balans 50/50 między kosztem a jakością\n\n"
        "Przesuwanie suwaka λ zmienia kształt krzywej Pareto i alokację dostawców."
    ),
    "constraints": (
        "**Constrainty (C1-C15)** to ograniczenia nałożone na solver:\n\n"
        "- **C1**: Każdy produkt musi być w 100% pokryty\n"
        "- **C5**: Max udział dostawcy (domyślnie 60%)\n"
        "- **C10**: Min 2 aktywnych dostawców\n"
        "- **C12**: Min ESG score ≥ 0.70\n"
        "- **C13**: Max warunki płatności ≤ 60 dni\n\n"
        "Constrainty zapewniają dywersyfikację i compliance. Można je dostosować w kroku 3."
    ),
}


# ── Main copilot logic ───────────────────────────────────────────

def process_message(req: CopilotRequest) -> CopilotResponse:
    """Przetwarza wiadomość użytkownika i generuje odpowiedź + akcje."""
    msg = req.message.strip().lower()
    context = req.context or {}

    # Match intent
    intent, params = _match_intent(msg)

    if intent == "optimize_category":
        return _handle_optimize(msg, params, context)
    elif intent.startswith("filter_"):
        return _handle_filter(intent, msg, params, context)
    elif intent == "navigate":
        return _handle_navigate(params, context)
    elif intent.startswith("query_"):
        return _handle_query(intent, msg, context)
    elif intent == "explain":
        return _handle_explain(params)
    elif intent == "build_cart":
        return _handle_build_cart(msg, params, context)
    elif intent == "create_auction":
        return _handle_create_auction(msg, context)
    else:
        return _handle_general(msg, context)


def _match_intent(msg: str) -> tuple[str, dict]:
    """Dopasowuje intencję z wzorców regex."""
    for pattern, intent, params in _INTENT_PATTERNS:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            # Extract dynamic params
            resolved = dict(params)
            if intent == "filter_sla":
                sla_match = re.search(r"SLA\s*[>>=]\s*(\d+)", msg, re.IGNORECASE)
                if sla_match:
                    resolved["min_sla"] = int(sla_match.group(1))
            return intent, resolved
    return "general", {}


def _handle_optimize(msg: str, params: dict, context: dict) -> CopilotResponse:
    domain = params.get("domain", "parts")
    unspsc = params.get("unspsc", "")

    # Check for region filter
    region = ""
    if "CEE" in msg.upper() or "europa środk" in msg.lower():
        region = "CEE"
    elif "PL" in msg.upper() or "polsk" in msg.lower():
        region = "PL"

    # Check for ESG filter
    esg_filter = ""
    if "zielon" in msg or "ESG" in msg or "ekolog" in msg:
        esg_filter = "high_esg"

    actions = [
        CopilotAction(action_type="navigate", params={"step": 1}, confidence=0.9),
        CopilotAction(action_type="select_category", params={"domain": domain, "unspsc": unspsc}, confidence=0.9),
    ]
    if esg_filter:
        actions.append(CopilotAction(action_type="set_weights", params={"w_esg": 0.50}, confidence=0.8))
    if region:
        actions.append(CopilotAction(action_type="filter_region", params={"region": region}, confidence=0.8))

    reply = f"Przygotowuję optymalizację dla domeny **{domain}**"
    if unspsc:
        reply += f" (UNSPSC: {unspsc})"
    if region:
        reply += f", region **{region}**"
    if esg_filter:
        reply += ", priorytet **ESG/zieloni dostawcy** (waga ESG: 50%)"
    reply += ".\n\nPrzechodzę do kroku 1 — wybierz sposób budowania zapotrzebowania."

    return CopilotResponse(
        reply=reply,
        actions=actions,
        suggestions=[
            "Pokaż ranking dostawców dla tej kategorii",
            "Uruchom symulację Monte Carlo",
            "Jakie constrainty są aktywne?",
        ],
    )


def _handle_filter(intent: str, msg: str, params: dict, context: dict) -> CopilotResponse:
    actions = []
    reply = ""

    if intent == "filter_esg":
        min_esg = params.get("min_esg", 0.80)
        actions.append(CopilotAction(action_type="set_constraint", params={"min_esg": min_esg}, confidence=0.9))
        reply = f"Ustawiam filtr ESG ≥ {min_esg*100:.0f}%. Dostawcy z niskim ESG score zostaną wykluczeni z optymalizacji."

    elif intent == "filter_certified":
        actions.append(CopilotAction(action_type="filter_certified", params={"require_iso": True}, confidence=0.8))
        reply = "Filtruję dostawców — tylko z aktywnymi certyfikatami (ISO 9001, IATF 16949)."

    elif intent == "filter_region":
        region = params.get("region", "PL")
        actions.append(CopilotAction(action_type="filter_region", params={"region": region}, confidence=0.9))
        reply = f"Filtruję dostawców obsługujących region **{region}**."

    elif intent == "filter_sla":
        min_sla = params.get("min_sla", 95)
        actions.append(CopilotAction(action_type="set_constraint", params={"min_compliance": min_sla / 100}, confidence=0.85))
        reply = f"Ustawiam minimalny SLA na **{min_sla}%**. Dostawcy poniżej tego progu będą pominięci."

    return CopilotResponse(
        reply=reply,
        actions=actions,
        suggestions=["Uruchom optymalizację z tymi filtrami", "Ilu dostawców spełnia kryteria?"],
    )


def _handle_navigate(params: dict, context: dict) -> CopilotResponse:
    step = params.get("step")
    tab = params.get("tab")

    if step:
        step_names = {1: "Zapotrzebowanie", 2: "Dostawcy", 3: "Optymalizacja", 4: "Zamówienie", 5: "Monitoring"}
        return CopilotResponse(
            reply=f"Przechodzę do **Krok {step}: {step_names.get(step, '')}**.",
            actions=[CopilotAction(action_type="navigate", params={"step": step}, confidence=0.95)],
        )
    elif tab:
        return CopilotResponse(
            reply=f"Otwieram panel **{tab}**.",
            actions=[CopilotAction(action_type="navigate", params={"tab": tab}, confidence=0.9)],
        )

    return CopilotResponse(reply="Nie rozumiem, gdzie chcesz przejść. Powiedz np. 'przejdź do kroku 3'.")


def _handle_query(intent: str, msg: str, context: dict) -> CopilotResponse:
    domain = context.get("domain", "parts")

    if intent == "query_best_supplier":
        return CopilotResponse(
            reply="Uruchamiam optymalizację z domyślnymi wagami, aby znaleźć najlepszego dostawcę.\n\n"
                  "Najlepszy dostawca to ten z najwyższą alokacją — uwzględnia koszt, czas, compliance i ESG.",
            actions=[CopilotAction(action_type="optimize", params={"domain": domain, "lambda": 0.5}, confidence=0.8)],
            suggestions=["Pokaż szczegóły alokacji", "Porównaj LP vs MIP"],
        )
    elif intent == "query_cheapest":
        return CopilotResponse(
            reply="Ustawiam λ=1.0 (pełna optymalizacja kosztu) — solver znajdzie najtańszą alokację.",
            actions=[CopilotAction(action_type="optimize", params={"domain": domain, "lambda": 1.0}, confidence=0.9)],
            suggestions=["A jaka jest różnica cenowa vs λ=0.5?", "Pokaż ryzyko tej alokacji"],
        )
    elif intent == "query_fastest":
        return CopilotResponse(
            reply="Ustawiam wagę czasu na 60% — solver priorytetyzuje najkrótszy lead time.",
            actions=[CopilotAction(action_type="set_weights", params={"w_time": 0.60, "w_cost": 0.20}, confidence=0.85)],
            suggestions=["Uruchom optymalizację", "Jaki jest najkrótszy lead time?"],
        )
    elif intent == "query_risk":
        return CopilotResponse(
            reply="Przechodzę do analizy ryzyka. Uruchamiam Monte Carlo (1000 symulacji) "
                  "i predykcję ML dla aktywnych dostawców.",
            actions=[
                CopilotAction(action_type="navigate", params={"step": 5}, confidence=0.9),
                CopilotAction(action_type="run_monte_carlo", params={}, confidence=0.8),
            ],
            suggestions=["Pokaż risk heatmap", "Którzy dostawcy mają najwyższe ryzyko?"],
        )
    elif intent == "query_savings":
        return CopilotResponse(
            reply="Porównuję scenariusze What-If aby obliczyć potencjalne oszczędności:\n\n"
                  "1. **Baseline** — obecne wagi\n"
                  "2. **Tight Budget** — priorytet koszt (λ=0.9)\n"
                  "3. **Green Focus** — priorytet ESG (w_esg=0.50)\n\n"
                  "Różnica między scenariuszami pokaże potencjał oszczędności.",
            actions=[CopilotAction(action_type="run_whatif", params={}, confidence=0.8)],
            suggestions=["Jakie są koszty per dostawca?", "Pokaż trend oszczędności"],
        )

    return CopilotResponse(reply="Nie mam wystarczających danych, aby odpowiedzieć. Spróbuj bardziej szczegółowe pytanie.")


def _handle_explain(params: dict) -> CopilotResponse:
    topic = params.get("topic", "")
    explanation = _EXPLANATIONS.get(topic, "")

    if explanation:
        return CopilotResponse(
            reply=explanation,
            suggestions=["Pokaż przykład", "Wyjaśnij kolejne pojęcie"],
        )

    return CopilotResponse(
        reply="O które pojęcie chodzi? Mogę wyjaśnić:\n"
              "- Front Pareto\n- Symulację Monte Carlo\n- DFG (graf przepływu procesu)\n"
              "- Alokację dostawców\n- Parametr Lambda\n- Constrainty solvera",
    )


def _handle_build_cart(msg: str, params: dict, context: dict) -> CopilotResponse:
    return CopilotResponse(
        reply="Przygotowuję koszyk zakupowy. Przechodzę do kroku 1 — wybierz produkty "
              "z katalogu lub wpisz pozycje ad hoc.\n\n"
              "Po zbudowaniu koszyka automatycznie uruchomię optymalizację w kroku 3.",
        actions=[CopilotAction(action_type="navigate", params={"step": 1}, confidence=0.9)],
        suggestions=["Dodaj filtry olejowe do koszyka", "Pokaż katalog produktów"],
    )


def _handle_create_auction(msg: str, context: dict) -> CopilotResponse:
    return CopilotResponse(
        reply="Tworzę nową aukcję odwróconą. Potrzebuję:\n\n"
              "1. **Tytuł** aukcji\n"
              "2. **Pozycje** (produkty, ilości, ceny startowe)\n"
              "3. **Zaproszeni dostawcy**\n"
              "4. **Czas trwania** (domyślnie 48h)\n\n"
              "Możesz też użyć przycisku 'Nowa aukcja' w panelu Aukcje.",
        actions=[CopilotAction(action_type="navigate", params={"tab": "auctions"}, confidence=0.85)],
        suggestions=["Utwórz aukcję na klocki hamulcowe", "Pokaż aktywne aukcje"],
    )


def _handle_general(msg: str, context: dict) -> CopilotResponse:
    """Fallback dla nierozpoznanych intencji."""
    step = context.get("step", 1)
    step_hints = {
        1: "Jesteś w kroku 1 (Zapotrzebowanie). Mogę pomóc:\n"
           "- Wybrać kategorię UNSPSC\n"
           "- Załadować produkty z katalogu\n"
           "- Wgrać plik CIF/CSV\n"
           "- Wpisać pozycje ad hoc",
        2: "Jesteś w kroku 2 (Dostawcy). Mogę pomóc:\n"
           "- Filtrować dostawców (region, certyfikaty, ESG)\n"
           "- Sprawdzić VAT w systemie VIES\n"
           "- Porównać profile dostawców",
        3: "Jesteś w kroku 3 (Optymalizacja). Mogę pomóc:\n"
           "- Ustawić wagi i parametry solvera\n"
           "- Wyjaśnić wyniki (Pareto, alokacja, radar)\n"
           "- Porównać scenariusze What-If",
        4: "Jesteś w kroku 4 (Zamówienie). Mogę pomóc:\n"
           "- Przejrzeć koszyk i zamówienia\n"
           "- Sprawdzić status PO\n"
           "- Utworzyć nową aukcję",
        5: "Jesteś w kroku 5 (Monitoring). Mogę pomóc:\n"
           "- Wyjaśnić DFG i process mining\n"
           "- Pokazać alerty predykcyjne\n"
           "- Uruchomić symulację Monte Carlo",
    }

    hint = step_hints.get(step, "Jak mogę pomóc? Powiedz co chcesz zrobić.")

    return CopilotResponse(
        reply=f"Nie do końca rozumiem — spróbuj inaczej sformułować.\n\n{hint}",
        suggestions=[
            "Optymalizuj klocki hamulcowe dla regionu PL",
            "Wyjaśnij front Pareto",
            "Pokaż ryzyko dostawców",
            "Utwórz nową aukcję",
        ],
    )
