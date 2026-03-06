"""
Alerts Engine — generate actionable alerts from optimisation and process mining results.

Two modes:
  1. check_optimization() — alerts from solver results (budget, concentration, infeasibility)
  2. check_process()      — alerts from P2P process analysis (SLA, conformance, rework, anomalies)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Alert data
# ---------------------------------------------------------------------------

class Alert:
    """Single alert with severity, category, and context."""

    __slots__ = (
        "id", "severity", "category", "title", "description",
        "metric_value", "threshold", "entity_id", "timestamp",
    )

    def __init__(
        self,
        severity: str,
        category: str,
        title: str,
        description: str,
        metric_value: float = 0.0,
        threshold: float = 0.0,
        entity_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.severity = severity  # info, warning, critical
        self.category = category  # optimization, process, compliance
        self.title = title
        self.description = description
        self.metric_value = metric_value
        self.threshold = threshold
        self.entity_id = entity_id
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    # Optimization
    "budget_warning_pct": 95.0,        # warn if >95% budget used
    "max_supplier_share_warn": 0.80,   # warn if one supplier >80%
    "cost_component_warn": 0.70,       # info if cost_component > 0.7

    # Process
    "sla_target_hours": 120.0,         # 5 days default SLA target
    "conformance_warn": 0.50,          # warn if conformance_rate < 50%
    "bottleneck_p95_hours": 48.0,      # warn if transition p95 > 48h
    "rework_rate_warn": 0.30,          # warn if rework_rate > 30%
    "anomaly_z_threshold": 2.0,        # cases > mean + 2*std
}


# ---------------------------------------------------------------------------
# Alerts Engine
# ---------------------------------------------------------------------------

class AlertsEngine:
    """Generate alerts from optimisation and process analysis results."""

    def __init__(self, thresholds: Optional[dict] = None):
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    # ── Optimization alerts ───────────────────────────────────────────

    def check_optimization(self, opt_result: dict) -> list[Alert]:
        """
        Generate alerts from an optimisation result dict.

        Expected keys: success, objective (with components), allocations,
        solver_stats, diagnostics (MIP only).
        """
        alerts: list[Alert] = []

        # 1. Check infeasibility
        if not opt_result.get("success", True):
            alerts.append(Alert(
                severity="critical",
                category="optimization",
                title="Optymalizacja niewykonalna",
                description=opt_result.get("message", "Solver nie znalazl rozwiazania."),
            ))

        # 2. Budget overrun (MIP diagnostics)
        diag = opt_result.get("diagnostics", {})
        budget_pct = diag.get("budget_used_pct", 0)
        if budget_pct > self.thresholds["budget_warning_pct"]:
            alerts.append(Alert(
                severity="warning",
                category="optimization",
                title="Przekroczenie budżetu",
                description=f"Wykorzystanie budżetu: {budget_pct}% (próg: {self.thresholds['budget_warning_pct']}%)",
                metric_value=budget_pct,
                threshold=self.thresholds["budget_warning_pct"],
            ))

        # 3. Supplier concentration risk
        allocations = opt_result.get("allocations", [])
        if allocations:
            # Sum allocated qty per supplier
            sup_volume: dict[str, float] = {}
            total_vol = 0.0
            for a in allocations:
                qty = a.get("allocated_qty", 0)
                sid = a.get("supplier_id", "?")
                sup_volume[sid] = sup_volume.get(sid, 0) + qty
                total_vol += qty

            if total_vol > 0:
                for sid, vol in sup_volume.items():
                    share = vol / total_vol
                    if share > self.thresholds["max_supplier_share_warn"]:
                        alerts.append(Alert(
                            severity="warning",
                            category="optimization",
                            title="Ryzyko koncentracji dostawcy",
                            description=f"Dostawca {sid}: {round(share*100, 1)}% wolumenu (próg: {round(self.thresholds['max_supplier_share_warn']*100)}%)",
                            metric_value=round(share, 3),
                            threshold=self.thresholds["max_supplier_share_warn"],
                            entity_id=sid,
                        ))

        # 4. High cost component
        obj = opt_result.get("objective", {})
        cost_comp = obj.get("cost_component", 0) if isinstance(obj, dict) else 0
        if cost_comp > self.thresholds["cost_component_warn"]:
            alerts.append(Alert(
                severity="info",
                category="optimization",
                title="Wysoki komponent kosztowy",
                description=f"Komponent kosztu: {round(cost_comp, 3)} (próg: {self.thresholds['cost_component_warn']})",
                metric_value=cost_comp,
                threshold=self.thresholds["cost_component_warn"],
            ))

        # 5. Infeasible products (MIP)
        infeasible = diag.get("infeasible_products", [])
        if infeasible:
            alerts.append(Alert(
                severity="critical",
                category="optimization",
                title="Produkty bez dostawcy",
                description=f"{len(infeasible)} produktow nie ma kwalifikujacego sie dostawcy: {', '.join(infeasible[:5])}",
                metric_value=len(infeasible),
                threshold=0,
            ))

        return alerts

    # ── Process alerts ────────────────────────────────────────────────

    def check_process(self, report: dict) -> list[Alert]:
        """
        Generate alerts from a full process digging report dict.

        Expected keys: conformance, bottlenecks, lead_times, rework,
        sla_monitor, anomalies (new v2.5.0 sections).
        """
        alerts: list[Alert] = []

        # 1. Conformance rate
        conf = report.get("conformance", {})
        conf_rate = conf.get("conformance_rate", 1.0)
        if conf_rate < self.thresholds["conformance_warn"]:
            alerts.append(Alert(
                severity="warning",
                category="process",
                title="Niska zgodność procesowa",
                description=f"Wskaźnik zgodności: {round(conf_rate*100, 1)}% (próg: {round(self.thresholds['conformance_warn']*100)}%)",
                metric_value=conf_rate,
                threshold=self.thresholds["conformance_warn"],
            ))

        # 2. Bottleneck severity
        bottlenecks = report.get("bottlenecks", {})
        for bt in bottlenecks.get("bottleneck_transitions", []):
            p95 = bt.get("p95_hours", 0)
            if p95 > self.thresholds["bottleneck_p95_hours"]:
                alerts.append(Alert(
                    severity="warning",
                    category="process",
                    title="Wąskie gardło procesowe",
                    description=f"{bt['source']} → {bt['target']}: P95={round(p95, 1)}h (próg: {self.thresholds['bottleneck_p95_hours']}h)",
                    metric_value=p95,
                    threshold=self.thresholds["bottleneck_p95_hours"],
                    entity_id=f"{bt['source']}→{bt['target']}",
                ))

        # 3. SLA breaches (from new sla_monitor section)
        sla = report.get("sla_monitor", {})
        breach_rate = sla.get("breach_rate", 0)
        if breach_rate > 0:
            breach_count = sla.get("breach_count", 0)
            sev = "critical" if breach_rate > 0.3 else "warning"
            alerts.append(Alert(
                severity=sev,
                category="compliance",
                title="Naruszenie SLA",
                description=f"{breach_count} przypadków ({round(breach_rate*100, 1)}%) przekroczyło docelowy SLA",
                metric_value=breach_rate,
                threshold=0,
            ))

            # Individual breach alerts (top 3)
            for b in sla.get("breaches", [])[:3]:
                alerts.append(Alert(
                    severity="critical",
                    category="compliance",
                    title=f"SLA naruszony: {b.get('case_id', '?')}",
                    description=f"Czas: {round(b.get('duration_hours', 0), 1)}h vs cel {round(b.get('target_hours', 0), 1)}h (+{round(b.get('excess_hours', 0), 1)}h)",
                    metric_value=b.get("duration_hours", 0),
                    threshold=b.get("target_hours", 0),
                    entity_id=b.get("case_id"),
                ))

        # 4. Rework rate (from new rework section)
        rework = report.get("rework", {})
        rework_rate = rework.get("rework_rate", 0)
        if rework_rate > self.thresholds["rework_rate_warn"]:
            alerts.append(Alert(
                severity="warning",
                category="process",
                title="Wysoki współczynnik przeróbek",
                description=f"Rework rate: {round(rework_rate*100, 1)}% (próg: {round(self.thresholds['rework_rate_warn']*100)}%)",
                metric_value=rework_rate,
                threshold=self.thresholds["rework_rate_warn"],
            ))

        # 5. Anomalies (from new anomalies section)
        anomalies = report.get("anomalies", {})
        anomaly_rate = anomalies.get("anomaly_rate", 0)
        if anomaly_rate > 0:
            count = len(anomalies.get("anomalies", []))
            alerts.append(Alert(
                severity="info",
                category="process",
                title="Wykryto anomalie procesowe",
                description=f"{count} przypadków odstaje od normy (z-score > {self.thresholds['anomaly_z_threshold']})",
                metric_value=anomaly_rate,
                threshold=0,
            ))

        return alerts

    def format_response(self, alerts: list[Alert]) -> dict:
        """Format alerts into API response."""
        critical = sum(1 for a in alerts if a.severity == "critical")
        warning = sum(1 for a in alerts if a.severity == "warning")
        info = sum(1 for a in alerts if a.severity == "info")

        return {
            "alerts": [a.to_dict() for a in alerts],
            "summary": {
                "total": len(alerts),
                "critical": critical,
                "warning": warning,
                "info": info,
            },
        }
