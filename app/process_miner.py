"""
Process Mining Engine — Procure-to-Pay (P2P) analysis.

Capabilities:
  1. DFG Discovery  — Directly-Follows Graph from event logs
  2. Lead Times     — average/median/p95 transition times between activities
  3. Bottlenecks    — identify slowest transitions and activities
  4. Variant stats  — trace variants with frequency and avg duration
  5. Case durations — end-to-end case statistics

Pure-Python implementation with optional pm4py acceleration.
All outputs are structured JSON, ready for BI dashboards (Power BI, Tableau, Qlik).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

# pm4py imports — optional acceleration
try:
    import pm4py
    from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
    from pm4py.statistics.variants.log import get as variants_get
    PM4PY_AVAILABLE = True
except ImportError:
    PM4PY_AVAILABLE = False


# ── Pure-Python DFG fallback ─────────────────────────────────────────

def _pure_python_dfg(df: pd.DataFrame) -> tuple[dict, dict, dict]:
    """
    Compute DFG frequency, start activities, and end activities
    using only pandas — no pm4py required.
    """
    dfg_freq: dict[tuple[str, str], int] = defaultdict(int)
    start_acts: dict[str, int] = defaultdict(int)
    end_acts: dict[str, int] = defaultdict(int)

    for _case_id, group in df.groupby("case:concept:name"):
        rows = group.sort_values("time:timestamp").reset_index(drop=True)
        activities = rows["concept:name"].tolist()
        if not activities:
            continue
        start_acts[activities[0]] += 1
        end_acts[activities[-1]] += 1
        for i in range(len(activities) - 1):
            dfg_freq[(activities[i], activities[i + 1])] += 1

    return dict(dfg_freq), dict(start_acts), dict(end_acts)


# -----------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------

def _prepare_event_log(events: list[dict]) -> pd.DataFrame:
    """
    Convert raw event dicts to a pm4py-compatible DataFrame.

    Expected keys per event: case_id, activity, timestamp
    Optional: resource, cost
    """
    df = pd.DataFrame(events)

    # Normalise column names
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

    df = df.rename(columns=col_map)

    # Ensure timestamp is datetime
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)

    # Sort by case then timestamp
    df = df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)

    return df


# -----------------------------------------------------------------------
# DFG Discovery
# -----------------------------------------------------------------------

def discover_dfg(events: list[dict]) -> dict:
    """
    Build a Directly-Follows Graph and return JSON-serialisable structure.

    Returns:
        nodes: list of activity names
        edges: list of {source, target, frequency}
        start_activities: dict activity → count
        end_activities: dict activity → count
    """
    df = _prepare_event_log(events)

    # Discover DFG (frequency-based) — pm4py or pure-Python fallback
    if PM4PY_AVAILABLE:
        dfg_freq = dfg_discovery.apply(df, variant=dfg_discovery.Variants.FREQUENCY)
        start_acts = pm4py.get_start_activities(df)
        end_acts = pm4py.get_end_activities(df)
    else:
        dfg_freq, start_acts, end_acts = _pure_python_dfg(df)

    # Collect unique nodes
    nodes = set()
    for (a, b) in dfg_freq:
        nodes.add(a)
        nodes.add(b)
    for a in start_acts:
        nodes.add(a)
    for a in end_acts:
        nodes.add(a)

    edges = [
        {"source": a, "target": b, "frequency": int(freq)}
        for (a, b), freq in sorted(dfg_freq.items(), key=lambda x: -x[1])
    ]

    return {
        "nodes": sorted(nodes),
        "edges": edges,
        "start_activities": {k: int(v) for k, v in start_acts.items()},
        "end_activities": {k: int(v) for k, v in end_acts.items()},
        "total_cases": df["case:concept:name"].nunique(),
        "total_events": len(df),
    }


# -----------------------------------------------------------------------
# Lead-time analysis (transition times between activities)
# -----------------------------------------------------------------------

def compute_lead_times(events: list[dict]) -> dict:
    """
    Calculate lead times between consecutive activities per case.

    Returns per-transition statistics:
        transitions: list of {source, target, count, avg_hours, median_hours, p95_hours, min_hours, max_hours}
        case_durations: {avg_hours, median_hours, min_hours, max_hours, total_cases}
    """
    df = _prepare_event_log(events)

    # Group by case and compute transitions
    transition_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    case_durations: list[float] = []

    for case_id, group in df.groupby("case:concept:name"):
        rows = group.sort_values("time:timestamp").reset_index(drop=True)
        if len(rows) < 2:
            continue

        # Case duration (first → last event)
        case_start = rows["time:timestamp"].iloc[0]
        case_end = rows["time:timestamp"].iloc[-1]
        case_dur_h = (case_end - case_start).total_seconds() / 3600
        case_durations.append(case_dur_h)

        # Transition times
        for i in range(len(rows) - 1):
            act_from = rows["concept:name"].iloc[i]
            act_to = rows["concept:name"].iloc[i + 1]
            t_from = rows["time:timestamp"].iloc[i]
            t_to = rows["time:timestamp"].iloc[i + 1]
            delta_h = (t_to - t_from).total_seconds() / 3600
            transition_times[(act_from, act_to)].append(delta_h)

    transitions = []
    for (src, tgt), times in sorted(transition_times.items(), key=lambda x: -statistics.mean(x[1])):
        transitions.append({
            "source": src,
            "target": tgt,
            "count": len(times),
            "avg_hours": round(statistics.mean(times), 2),
            "median_hours": round(statistics.median(times), 2),
            "p95_hours": round(sorted(times)[int(len(times) * 0.95)] if len(times) >= 2 else times[0], 2),
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

    return {
        "transitions": transitions,
        "case_durations": case_stats,
    }


# -----------------------------------------------------------------------
# Bottleneck detection
# -----------------------------------------------------------------------

def detect_bottlenecks(events: list[dict], top_n: int = 5) -> dict:
    """
    Identify the top-N bottleneck transitions (longest average lead time).

    Also identifies:
    - Activity-level bottlenecks (activities with longest cumulative wait time)
    - Cases with the longest duration
    """
    lead = compute_lead_times(events)
    transitions = lead["transitions"]

    # Top-N slowest transitions
    bottleneck_transitions = transitions[:top_n]

    # Activity-level: accumulate incoming wait time per activity
    activity_wait: dict[str, list[float]] = defaultdict(list)
    for t in transitions:
        activity_wait[t["target"]].append(t["avg_hours"] * t["count"])

    activity_bottlenecks = []
    for act, waits in sorted(activity_wait.items(), key=lambda x: -sum(x[1])):
        activity_bottlenecks.append({
            "activity": act,
            "total_wait_hours": round(sum(waits), 2),
            "incoming_transitions": len(waits),
        })

    # Slow cases
    df = _prepare_event_log(events)
    slow_cases = []
    for case_id, group in df.groupby("case:concept:name"):
        rows = group.sort_values("time:timestamp")
        dur_h = (rows["time:timestamp"].iloc[-1] - rows["time:timestamp"].iloc[0]).total_seconds() / 3600
        activities = rows["concept:name"].tolist()
        slow_cases.append({
            "case_id": case_id,
            "duration_hours": round(dur_h, 2),
            "num_events": len(rows),
            "trace": " → ".join(activities),
        })
    slow_cases.sort(key=lambda x: -x["duration_hours"])

    return {
        "bottleneck_transitions": bottleneck_transitions,
        "activity_bottlenecks": activity_bottlenecks[:top_n],
        "slowest_cases": slow_cases[:top_n],
        "summary": {
            "total_transitions_analyzed": len(transitions),
            "total_activities": len(activity_wait),
            "total_cases": lead["case_durations"].get("total_cases", 0),
            "avg_case_duration_hours": lead["case_durations"].get("avg_hours", 0),
        },
    }


# -----------------------------------------------------------------------
# Variant analysis
# -----------------------------------------------------------------------

def analyze_variants(events: list[dict]) -> dict:
    """
    Identify process variants (unique traces) with frequency and duration stats.
    """
    df = _prepare_event_log(events)

    variants: dict[str, list[dict]] = defaultdict(list)

    for case_id, group in df.groupby("case:concept:name"):
        rows = group.sort_values("time:timestamp")
        trace = tuple(rows["concept:name"].tolist())
        dur_h = (rows["time:timestamp"].iloc[-1] - rows["time:timestamp"].iloc[0]).total_seconds() / 3600
        variants[trace].append({"case_id": case_id, "duration_hours": dur_h})

    result = []
    total_cases = sum(len(v) for v in variants.values())

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

    return {
        "variants": result,
        "total_variants": len(result),
        "total_cases": total_cases,
    }
