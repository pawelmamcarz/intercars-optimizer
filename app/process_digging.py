"""
Process Digging Engine — dedicated P2P process analysis service.

Goes beyond basic process mining by adding:
  1. Performance DFG     — edge weights = avg transition time (not just frequency)
  2. Conformance check   — compare discovered process vs reference BPMN path
  3. Social network       — resource handover analysis
  4. Full BI-ready JSON   — structured output for 5 local BI systems

Uses pm4py underneath but exposes a clean OOP interface.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import pm4py
    from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
    PM4PY_AVAILABLE = True
except ImportError:
    PM4PY_AVAILABLE = False


# ── Reference P2P process (INTERCARS standard) ──────────────────────────

REFERENCE_P2P_PATH = [
    "Utworzenie Zapotrzebowania",
    "Sprawdzenie Budżetu",
    "Zatwierdzenie Zapotrzebowania",
    "Wystawienie Zamówienia",
    "Potwierdzenie Zamówienia",
    "Przyjęcie Dostawy",
    "Weryfikacja 3-Way Match",
    "Zaksięgowanie Faktury",
]


class ProcessDiggingEngine:
    """
    Dedicated P2P process analysis service.

    Accepts event logs and produces structured JSON insights
    ready for Power BI, Tableau, Qlik, Looker, and Metabase.
    """

    def __init__(self, events: list[dict]):
        if not PM4PY_AVAILABLE:
            raise RuntimeError("pm4py is not installed — cannot run process digging")
        self.raw_events = events
        self.df = self._prepare(events)

    # ── Data preparation ─────────────────────────────────────────────

    @staticmethod
    def _prepare(events: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(events)
        col_map = {}
        for col in df.columns:
            low = col.lower().replace(" ", "_")
            if "case" in low:
                col_map[col] = "case:concept:name"
            elif "activity" in low or "event" in low:
                col_map[col] = "concept:name"
            elif "timestamp" in low or "time" in low:
                col_map[col] = "time:timestamp"
            elif "resource" in low or "user" in low:
                col_map[col] = "org:resource"
            elif "cost" in low:
                col_map[col] = "cost"
        df = df.rename(columns=col_map)
        df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
        df = df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)
        return df

    # ── 1. Frequency DFG ─────────────────────────────────────────────

    def discover_dfg(self) -> dict:
        """Directly-Follows Graph weighted by transition FREQUENCY."""
        dfg_freq = dfg_discovery.apply(self.df, variant=dfg_discovery.Variants.FREQUENCY)
        start_acts = pm4py.get_start_activities(self.df)
        end_acts = pm4py.get_end_activities(self.df)

        nodes = set()
        for (a, b) in dfg_freq:
            nodes.add(a)
            nodes.add(b)
        for a in list(start_acts) + list(end_acts):
            nodes.add(a)

        edges = [
            {"source": a, "target": b, "frequency": int(freq)}
            for (a, b), freq in sorted(dfg_freq.items(), key=lambda x: -x[1])
        ]
        return {
            "type": "frequency",
            "nodes": sorted(nodes),
            "edges": edges,
            "start_activities": {k: int(v) for k, v in start_acts.items()},
            "end_activities": {k: int(v) for k, v in end_acts.items()},
            "total_cases": self.df["case:concept:name"].nunique(),
            "total_events": len(self.df),
        }

    # ── 2. Performance DFG (NEW — times on edges) ────────────────────

    def discover_performance_dfg(self) -> dict:
        """
        Directly-Follows Graph weighted by avg TRANSITION TIME (hours).

        Each edge carries: avg_hours, median_hours, p95_hours, count.
        This is what BI dashboards need to visualise bottlenecks on the graph.
        """
        transition_times: dict[tuple[str, str], list[float]] = defaultdict(list)

        for _case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp").reset_index(drop=True)
            for i in range(len(rows) - 1):
                src = rows["concept:name"].iloc[i]
                tgt = rows["concept:name"].iloc[i + 1]
                delta_h = (rows["time:timestamp"].iloc[i + 1] - rows["time:timestamp"].iloc[i]).total_seconds() / 3600
                transition_times[(src, tgt)].append(delta_h)

        nodes = set()
        edges = []
        for (src, tgt), times in sorted(transition_times.items(), key=lambda x: -statistics.mean(x[1])):
            nodes.add(src)
            nodes.add(tgt)
            sorted_times = sorted(times)
            edges.append({
                "source": src,
                "target": tgt,
                "count": len(times),
                "avg_hours": round(statistics.mean(times), 2),
                "median_hours": round(statistics.median(times), 2),
                "p95_hours": round(sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) >= 2 else sorted_times[0], 2),
                "min_hours": round(min(times), 2),
                "max_hours": round(max(times), 2),
            })

        return {
            "type": "performance",
            "nodes": sorted(nodes),
            "edges": edges,
            "total_cases": self.df["case:concept:name"].nunique(),
            "total_events": len(self.df),
        }

    # ── 3. Lead Times ────────────────────────────────────────────────

    def compute_lead_times(self) -> dict:
        """Per-transition and per-case lead time statistics."""
        transition_times: dict[tuple[str, str], list[float]] = defaultdict(list)
        case_durations: list[float] = []

        for _case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp").reset_index(drop=True)
            if len(rows) < 2:
                continue
            case_dur_h = (rows["time:timestamp"].iloc[-1] - rows["time:timestamp"].iloc[0]).total_seconds() / 3600
            case_durations.append(case_dur_h)
            for i in range(len(rows) - 1):
                src = rows["concept:name"].iloc[i]
                tgt = rows["concept:name"].iloc[i + 1]
                delta_h = (rows["time:timestamp"].iloc[i + 1] - rows["time:timestamp"].iloc[i]).total_seconds() / 3600
                transition_times[(src, tgt)].append(delta_h)

        transitions = []
        for (src, tgt), times in sorted(transition_times.items(), key=lambda x: -statistics.mean(x[1])):
            sorted_t = sorted(times)
            transitions.append({
                "source": src, "target": tgt, "count": len(times),
                "avg_hours": round(statistics.mean(times), 2),
                "median_hours": round(statistics.median(times), 2),
                "p95_hours": round(sorted_t[int(len(sorted_t) * 0.95)] if len(sorted_t) >= 2 else sorted_t[0], 2),
                "min_hours": round(min(times), 2),
                "max_hours": round(max(times), 2),
            })

        case_stats = {}
        if case_durations:
            case_stats = {
                "total_cases": len(case_durations),
                "avg_hours": round(statistics.mean(case_durations), 2),
                "median_hours": round(statistics.median(case_durations), 2),
                "min_hours": round(min(case_durations), 2),
                "max_hours": round(max(case_durations), 2),
            }
        return {"transitions": transitions, "case_durations": case_stats}

    # ── 4. Bottleneck Detection ──────────────────────────────────────

    def detect_bottlenecks(self, top_n: int = 5) -> dict:
        """
        Multi-layer bottleneck detection:
          - Transition level: slowest A→B edges
          - Activity level: activities with highest cumulative incoming wait
          - Case level: slowest end-to-end cases
        """
        lead = self.compute_lead_times()
        transitions = lead["transitions"]

        # Top-N slowest transitions
        bottleneck_transitions = transitions[:top_n]

        # Activity-level bottlenecks
        activity_wait: dict[str, list[float]] = defaultdict(list)
        for t in transitions:
            activity_wait[t["target"]].append(t["avg_hours"] * t["count"])

        activity_bottlenecks = [
            {"activity": act, "total_wait_hours": round(sum(waits), 2), "incoming_transitions": len(waits)}
            for act, waits in sorted(activity_wait.items(), key=lambda x: -sum(x[1]))
        ][:top_n]

        # Slowest cases
        slow_cases = []
        for case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp")
            dur_h = (rows["time:timestamp"].iloc[-1] - rows["time:timestamp"].iloc[0]).total_seconds() / 3600
            slow_cases.append({
                "case_id": case_id,
                "duration_hours": round(dur_h, 2),
                "num_events": len(rows),
                "trace": " → ".join(rows["concept:name"].tolist()),
            })
        slow_cases.sort(key=lambda x: -x["duration_hours"])

        return {
            "bottleneck_transitions": bottleneck_transitions,
            "activity_bottlenecks": activity_bottlenecks,
            "slowest_cases": slow_cases[:top_n],
            "summary": {
                "total_transitions_analyzed": len(transitions),
                "total_activities": len(activity_wait),
                "total_cases": lead["case_durations"].get("total_cases", 0),
                "avg_case_duration_hours": lead["case_durations"].get("avg_hours", 0),
            },
        }

    # ── 5. Variant Analysis ──────────────────────────────────────────

    def analyze_variants(self) -> dict:
        """Group cases by unique activity trace, with frequency and duration stats."""
        variants: dict[tuple, list[dict]] = defaultdict(list)

        for case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp")
            trace = tuple(rows["concept:name"].tolist())
            dur_h = (rows["time:timestamp"].iloc[-1] - rows["time:timestamp"].iloc[0]).total_seconds() / 3600
            variants[trace].append({"case_id": case_id, "duration_hours": dur_h})

        total_cases = sum(len(v) for v in variants.values())
        result = []
        for trace, cases in sorted(variants.items(), key=lambda x: -len(x[1])):
            durations = [c["duration_hours"] for c in cases]
            result.append({
                "variant": " → ".join(trace),
                "frequency": len(cases),
                "percentage": round(len(cases) / total_cases * 100, 1) if total_cases else 0,
                "avg_duration_hours": round(statistics.mean(durations), 2),
                "min_duration_hours": round(min(durations), 2),
                "max_duration_hours": round(max(durations), 2),
                "case_ids": [c["case_id"] for c in cases],
            })
        return {"variants": result, "total_variants": len(result), "total_cases": total_cases}

    # ── 6. Conformance Check (NEW) ───────────────────────────────────

    def check_conformance(self, reference_path: list[str] | None = None) -> dict:
        """
        Compare discovered traces against a reference (ideal) P2P path.

        Returns per-case conformance:
          - fitness (0..1): fraction of reference activities present
          - deviations: missing/extra/out-of-order activities
        """
        ref = reference_path or REFERENCE_P2P_PATH
        ref_set = set(ref)

        cases = []
        conforming_count = 0

        for case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp")
            trace = rows["concept:name"].tolist()
            trace_set = set(trace)

            # Activities analysis
            present = [a for a in ref if a in trace_set]
            missing = [a for a in ref if a not in trace_set]
            extra = [a for a in trace if a not in ref_set]

            # Order analysis — are present activities in correct relative order?
            ref_indices = {a: i for i, a in enumerate(ref)}
            present_order = [ref_indices[a] for a in trace if a in ref_indices]
            is_ordered = present_order == sorted(present_order)

            fitness = len(present) / len(ref) if ref else 0
            is_conforming = fitness == 1.0 and is_ordered and len(extra) == 0

            if is_conforming:
                conforming_count += 1

            cases.append({
                "case_id": case_id,
                "fitness": round(fitness, 3),
                "is_conforming": is_conforming,
                "activities_present": len(present),
                "activities_missing": missing,
                "activities_extra": extra,
                "order_correct": is_ordered,
                "trace": " → ".join(trace),
            })

        total = len(cases)
        return {
            "reference_path": " → ".join(ref),
            "total_cases": total,
            "conforming_cases": conforming_count,
            "conformance_rate": round(conforming_count / total, 3) if total else 0,
            "avg_fitness": round(statistics.mean([c["fitness"] for c in cases]), 3) if cases else 0,
            "cases": sorted(cases, key=lambda c: c["fitness"]),
        }

    # ── 7. Social Network / Resource Handover (NEW) ──────────────────

    def analyze_handovers(self) -> dict:
        """
        Resource handover analysis — who passes work to whom.

        Returns a social network graph of resource interactions,
        useful for understanding organisational bottlenecks.
        """
        has_resource = "org:resource" in self.df.columns
        if not has_resource:
            return {
                "available": False,
                "message": "No resource data in event log — add 'resource' field to events.",
                "nodes": [],
                "edges": [],
            }

        handover_counts: dict[tuple[str, str], int] = defaultdict(int)
        resource_activity: dict[str, set] = defaultdict(set)
        resource_cases: dict[str, set] = defaultdict(set)

        for _case_id, group in self.df.groupby("case:concept:name"):
            rows = group.sort_values("time:timestamp").reset_index(drop=True)
            for i in range(len(rows) - 1):
                r_from = rows.get("org:resource", pd.Series()).iloc[i] if "org:resource" in rows.columns else None
                r_to = rows.get("org:resource", pd.Series()).iloc[i + 1] if "org:resource" in rows.columns else None
                if r_from and r_to and r_from != r_to:
                    handover_counts[(str(r_from), str(r_to))] += 1
                if r_from:
                    resource_activity[str(r_from)].add(rows["concept:name"].iloc[i])
                    resource_cases[str(r_from)].add(_case_id)
                if r_to:
                    resource_activity[str(r_to)].add(rows["concept:name"].iloc[i + 1])
                    resource_cases[str(r_to)].add(_case_id)

        nodes = []
        all_resources = set()
        for (r1, r2) in handover_counts:
            all_resources.add(r1)
            all_resources.add(r2)

        for r in sorted(all_resources):
            nodes.append({
                "resource": r,
                "activities": sorted(resource_activity.get(r, set())),
                "cases_involved": len(resource_cases.get(r, set())),
            })

        edges = [
            {"from_resource": r1, "to_resource": r2, "handover_count": cnt}
            for (r1, r2), cnt in sorted(handover_counts.items(), key=lambda x: -x[1])
        ]

        return {
            "available": True,
            "nodes": nodes,
            "edges": edges,
            "total_handovers": sum(handover_counts.values()),
            "unique_resources": len(all_resources),
        }

    # ── 8. Full BI Report (aggregated) ───────────────────────────────

    def full_report(self, top_n: int = 5) -> dict:
        """
        Complete P2P process analysis in one call.

        Returns all analyses combined — ideal for BI dashboard initial load.
        """
        return {
            "dfg_frequency": self.discover_dfg(),
            "dfg_performance": self.discover_performance_dfg(),
            "lead_times": self.compute_lead_times(),
            "bottlenecks": self.detect_bottlenecks(top_n=top_n),
            "variants": self.analyze_variants(),
            "conformance": self.check_conformance(),
            "handovers": self.analyze_handovers(),
        }
