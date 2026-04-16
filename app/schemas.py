"""
Flow Procurement Platform — Pydantic schemas.

All request/response models for the three-layer pipeline:
  Data (EWM) → Optimization (HiGHS) → Decision (REST JSON).

Supports two demo domains:
  1. Auto-parts procurement (cost, lead-time, compliance, ESG)
  2. IT services procurement (cost, delivery, SLA, reliability)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SolverMode(str, Enum):
    continuous = "continuous"  # scipy linprog (HiGHS)
    mip = "mip"               # PuLP / highspy binary


class DemoDomain(str, Enum):
    # ── DIRECT (wchodzą w produkt/usługę końcową) ──
    parts = "parts"                     # Części zamienne aftermarket
    oe_components = "oe_components"     # Komponenty OE (Original Equipment)
    oils = "oils"                       # Oleje i płyny eksploatacyjne
    batteries = "batteries"             # Akumulatory i elektro
    tires = "tires"                     # Opony (letnie/zimowe/całoroczne)
    bodywork = "bodywork"               # Elementy nadwozia (blacharstwo, oświetlenie, szyby)
    # ── INDIRECT (wspierają operacje) ──
    it_services = "it_services"         # Usługi IT / integratorzy
    logistics = "logistics"             # Logistyka i transport
    packaging = "packaging"             # Opakowania i materiały
    facility_management = "facility_management"  # FM (ex-MRO: utrzymanie, BHP, czystość)
    mro_supplies = "mro"                # backward-compat alias → facility_management


class SubDomain(str, Enum):
    """Subdomeny zakupowe — po 2-4 na domenę główną."""
    # parts
    brake_systems = "brake_systems"
    filters = "filters"
    suspension = "suspension"
    # oe_components
    engine_parts = "engine_parts"
    electrical = "electrical"
    transmission = "transmission"
    # oils
    engine_oils = "engine_oils"
    transmission_fluids = "transmission_fluids"
    # batteries
    starter_batteries = "starter_batteries"
    agm_efb = "agm_efb"
    # tires
    summer_tires = "summer_tires"
    winter_tires = "winter_tires"
    all_season = "all_season"
    # bodywork
    body_panels = "body_panels"
    lighting = "lighting"
    glass = "glass"
    # it_services
    development = "development"
    cloud_infra = "cloud_infra"
    data_analytics = "data_analytics"
    # logistics
    domestic = "domestic"
    international = "international"
    last_mile = "last_mile"
    # packaging
    cardboard = "cardboard"
    plastics = "plastics"
    # facility_management
    maintenance = "maintenance"
    safety_equipment = "safety_equipment"
    cleaning = "cleaning"


# ---------------------------------------------------------------------------
# Input: Supplier (unified for both domains)
# ---------------------------------------------------------------------------

class SupplierInput(BaseModel):
    """
    Pre-selected supplier with its raw (non-normalised) parameters.

    For auto-parts:
      compliance_score → reliability/compliance index
      esg_score        → ecological/ESG index

    For IT services:
      compliance_score → guaranteed SLA (%)  mapped to 0..1
      esg_score        → historical reliability index
    """

    supplier_id: str = Field(..., examples=["SUP-001"])
    name: str = Field(..., examples=["AutoParts Kraków"])

    # Costs
    unit_cost: float = Field(..., ge=0, description="PLN per unit (material or hourly rate)")
    logistics_cost: float = Field(0.0, ge=0, description="PLN per unit (transport / overhead)")

    # Time
    lead_time_days: float = Field(..., ge=0, description="Expected lead-time / delivery in days")

    # Quality / compliance / SLA
    compliance_score: float = Field(
        ..., ge=0, le=1,
        description="Reliability / compliance / SLA index 0..1 (1 = perfect)",
    )

    # ESG / Green / Reliability
    esg_score: float = Field(
        ..., ge=0, le=1,
        description="ESG / reliability index 0..1 (1 = best)",
    )

    # Capacity
    min_order_qty: float = Field(0.0, ge=0, description="Minimum order quantity")
    max_capacity: float = Field(..., gt=0, description="Maximum supply capacity (units / hours)")

    # Regional availability — list of region codes this supplier can serve
    served_regions: list[str] = Field(
        ...,
        min_length=1,
        description="Region codes the supplier covers, e.g. ['PL-MA', 'PL-SL']",
    )

    # ── v3.0 — new constraint support fields ──
    payment_terms_days: float = Field(30.0, ge=0, description="Days to payment (Net30=30, Net60=60)")
    contract_min_allocation: float = Field(
        0.0, ge=0, le=1,
        description="C14: mandatory minimum allocation fraction from existing contract (0 = none)",
    )
    is_preferred: bool = Field(False, description="C15: strategic preferred partner flag")
    region_code: Optional[str] = Field(
        None, description="ISO region code for C11 geographic diversity (e.g. 'PL', 'DE', 'CEE')",
    )


# ---------------------------------------------------------------------------
# Input: Product demand
# ---------------------------------------------------------------------------

class DemandItem(BaseModel):
    """Single product/index demand from the EWM system."""

    product_id: str = Field(..., examples=["IDX-10042"])
    demand_qty: float = Field(..., gt=0, description="Required quantity (units / hours)")
    destination_region: str = Field(
        ...,
        description="Region code where the product must be delivered",
        examples=["PL-MA"],
    )


# ---------------------------------------------------------------------------
# Input: Optimisation request
# ---------------------------------------------------------------------------

class CriteriaWeights(BaseModel):
    """
    Weights for normalised criteria.

    The `lambda_param` controls the cost ↔ time trade-off:
        effective_cost_weight  = lambda_param * w_cost
        effective_time_weight  = (1 - lambda_param) * w_time

    Compliance and ESG weights are applied directly.
    All four base weights (w_cost, w_time, w_compliance, w_esg) should sum to 1.
    """

    lambda_param: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Cost ↔ time trade-off coefficient (1 = pure cost, 0 = pure time)",
    )
    w_cost: float = Field(0.4, ge=0.0, le=1.0)
    w_time: float = Field(0.3, ge=0.0, le=1.0)
    w_compliance: float = Field(0.15, ge=0.0, le=1.0)
    w_esg: float = Field(0.15, ge=0.0, le=1.0)

    @field_validator("w_esg")
    @classmethod
    def weights_must_sum_to_one(cls, v, info):
        total = (
            info.data.get("w_cost", 0)
            + info.data.get("w_time", 0)
            + info.data.get("w_compliance", 0)
            + v
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Base weights must sum to 1.0, got {total:.6f}"
            )
        return v


class ConstraintConfig(BaseModel):
    """C10–C15: optional advanced constraints for solver."""

    min_supplier_count: Optional[int] = Field(
        None, ge=2, description="C10: minimum number of active suppliers in solution",
    )
    min_geographic_regions: Optional[int] = Field(
        None, ge=1, description="C11: minimum distinct supplier regions required",
    )
    min_esg_score: Optional[float] = Field(
        None, ge=0, le=1, description="C12: minimum weighted-average ESG score across portfolio",
    )
    max_payment_terms_days: Optional[float] = Field(
        None, ge=0, description="C13: max weighted-average payment terms (days)",
    )
    preferred_supplier_bonus: float = Field(
        0.05, ge=0, le=0.5, description="C15a: soft objective reduction factor for preferred suppliers",
    )
    min_preferred_share: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="C15b: hard lower bound — min fraction of portfolio volume allocated to preferred suppliers",
    )


class OptimizationRequest(BaseModel):
    """Full payload sent to /optimize."""

    suppliers: list[SupplierInput] = Field(..., min_length=1)
    demand: list[DemandItem] = Field(..., min_length=1)
    weights: CriteriaWeights = Field(default_factory=CriteriaWeights)
    mode: SolverMode = Field(SolverMode.continuous)
    max_vendor_share: float = Field(
        0.60, ge=0.0, le=1.0,
        description=(
            "Vendor Diversification Policy — maximum fraction of total volume "
            "any single supplier can receive (0.6 = 60%). Set to 1.0 to disable."
        ),
    )
    constraints: Optional[ConstraintConfig] = Field(
        None, description="Advanced constraints C10-C15 (optional)",
    )


# ---------------------------------------------------------------------------
# Output: Allocation result
# ---------------------------------------------------------------------------

class AllocationRow(BaseModel):
    """Resulting allocation for one (supplier, product) pair."""

    supplier_id: str
    supplier_name: str
    product_id: str
    allocated_qty: float = Field(..., description="Units allocated")
    allocated_fraction: float = Field(
        ..., ge=0, le=1,
        description="Fraction of total product demand",
    )
    unit_cost: float
    logistics_cost: float
    lead_time_days: float
    compliance_score: float
    esg_score: float


class ObjectiveBreakdown(BaseModel):
    """Breakdown of the objective function value."""

    total: float
    cost_component: float
    time_component: float
    compliance_component: float
    esg_component: float


class SolverStats(BaseModel):
    """Basic solver statistics."""

    status: str
    iterations: int = 0
    solve_time_ms: float = 0.0
    mode: SolverMode
    diversification_active: bool = False
    max_vendor_share: float = 1.0


class ShadowPrice(BaseModel):
    """Dual value for one solver constraint (LP sensitivity analysis, B1).

    A positive `value` for an inequality (≤) constraint means tightening
    the bound by 1 unit would worsen the objective by `value`. Negative on
    a ≥ constraint means the same. The UI surfaces the biggest |value| so
    buyers see which constraint is costliest to keep active.
    """
    constraint_id: str      # e.g. "C12_esg_floor"
    label: str              # human-readable
    kind: str               # "demand" | "capacity" | "diversification" | "esg" | "payment" | "preferred" | "region"
    value: float            # shadow price (PLN per unit of slack)
    slack: float = 0.0      # how much room is left (0 = binding)


class OptimizationResponse(BaseModel):
    """Standard response from /optimize."""

    success: bool
    message: str = ""
    solver_stats: SolverStats
    objective: ObjectiveBreakdown
    allocations: list[AllocationRow] = []
    weights_used: CriteriaWeights
    shadow_prices: list[ShadowPrice] = []


# ---------------------------------------------------------------------------
# Dashboard (Pareto front)
# ---------------------------------------------------------------------------

class ParetoPoint(BaseModel):
    """One point on the Pareto front (one lambda value)."""

    lambda_param: float
    objective_total: float
    cost_component: float
    time_component: float
    compliance_component: float
    esg_component: float


class ParetoPointXY(BaseModel):
    """Enhanced Pareto point for XY scatter chart (v3.0)."""

    lambda_param: float
    total_cost_pln: float = Field(..., description="X-axis: actual cost in PLN")
    weighted_quality: float = Field(..., description="Y-axis: (compliance+esg)/2 weighted by qty")
    objective_total: float
    cost_component: float
    time_component: float
    compliance_component: float
    esg_component: float
    suppliers_used: int


class SupplierRadarProfile(BaseModel):
    """Radar-chart data for a single supplier (normalised 0..1)."""

    supplier_id: str
    supplier_name: str
    cost_norm: float
    time_norm: float
    compliance_norm: float
    esg_norm: float
    total_allocated_fraction: float = Field(
        ..., description="Total fraction of demand allocated to this supplier",
    )


class DashboardRequest(BaseModel):
    """Request for the dashboard / Pareto-front endpoint."""

    suppliers: list[SupplierInput]
    demand: list[DemandItem]
    weights: CriteriaWeights = Field(default_factory=CriteriaWeights)
    mode: SolverMode = Field(SolverMode.continuous)
    pareto_steps: int = Field(
        11, ge=2, le=101,
        description="Number of lambda values to sample for the Pareto front (incl. 0 and 1)",
    )
    max_vendor_share: float = Field(0.60, ge=0.0, le=1.0)


class DashboardResponse(BaseModel):
    """Response from the dashboard endpoint."""

    pareto_front: list[ParetoPoint]
    supplier_profiles: list[SupplierRadarProfile]
    current_allocation: OptimizationResponse


# ---------------------------------------------------------------------------
# Stealth mode — raw solver output
# ---------------------------------------------------------------------------

class ConstraintLog(BaseModel):
    name: str
    expression: str
    bound: str
    slack: Optional[float] = None


class VariableLog(BaseModel):
    name: str
    value: float
    reduced_cost: Optional[float] = None


class IterationLog(BaseModel):
    iteration: int
    objective_value: float
    primal_infeasibility: Optional[float] = None


class StealthRequest(BaseModel):
    """Same input as OptimizationRequest but returns raw diagnostics."""

    suppliers: list[SupplierInput]
    demand: list[DemandItem]
    weights: CriteriaWeights = Field(default_factory=CriteriaWeights)
    mode: SolverMode = Field(SolverMode.continuous)
    max_vendor_share: float = Field(0.60, ge=0.0, le=1.0)


class StealthResponse(BaseModel):
    """Raw solver diagnostics for analysts."""

    success: bool
    solver_name: str
    solver_status: str
    solve_time_ms: float
    objective_value: float
    objective_equation: str = Field(
        ..., description="Human-readable objective function string",
    )
    variables: list[VariableLog]
    constraints: list[ConstraintLog]
    iterations: list[IterationLog]
    raw_log: str = Field("", description="Full HiGHS solver output")
    allocation_result: OptimizationResponse


# ---------------------------------------------------------------------------
# Process Mining — Procure-to-Pay (P2P) analysis
# ---------------------------------------------------------------------------

class EventLogEntry(BaseModel):
    """Single event in a P2P process log."""

    case_id: str = Field(..., description="Process instance ID (e.g., 'REQ-001')")
    activity: str = Field(..., description="Activity name (e.g., 'Utworzenie Zapotrzebowania')")
    timestamp: str = Field(..., description="ISO datetime (e.g., '2026-03-01T10:00:00')")
    resource: Optional[str] = Field(None, description="User/system who executed the activity")
    cost: Optional[float] = Field(None, ge=0, description="Cost associated with this event")


class ProcessMiningRequest(BaseModel):
    """Input for Process Mining endpoints."""

    events: list[EventLogEntry] = Field(..., min_length=2, description="Event log entries")
    top_n: int = Field(5, ge=1, le=50, description="Number of top bottlenecks to return")


class DFGEdge(BaseModel):
    source: str
    target: str
    frequency: int


class DFGResponse(BaseModel):
    """Directly-Follows Graph for BI visualisation."""

    nodes: list[str]
    edges: list[DFGEdge]
    start_activities: dict[str, int]
    end_activities: dict[str, int]
    total_cases: int
    total_events: int


class TransitionStat(BaseModel):
    """Lead time statistics for one transition (activity → activity)."""

    source: str
    target: str
    count: int
    avg_hours: float
    median_hours: float
    p95_hours: float
    min_hours: float
    max_hours: float


class CaseDurationStats(BaseModel):
    total_cases: int = 0
    avg_hours: float = 0.0
    median_hours: float = 0.0
    min_hours: float = 0.0
    max_hours: float = 0.0


class LeadTimeResponse(BaseModel):
    """Lead time analysis between activities."""

    transitions: list[TransitionStat]
    case_durations: CaseDurationStats


class BottleneckTransition(BaseModel):
    source: str
    target: str
    count: int
    avg_hours: float
    median_hours: float
    p95_hours: float
    min_hours: float
    max_hours: float


class ActivityBottleneck(BaseModel):
    activity: str
    total_wait_hours: float
    incoming_transitions: int


class SlowCase(BaseModel):
    case_id: str
    duration_hours: float
    num_events: int
    trace: str


class BottleneckSummary(BaseModel):
    total_transitions_analyzed: int
    total_activities: int
    total_cases: int
    avg_case_duration_hours: float


class BottleneckResponse(BaseModel):
    """Bottleneck analysis results for BI."""

    bottleneck_transitions: list[BottleneckTransition]
    activity_bottlenecks: list[ActivityBottleneck]
    slowest_cases: list[SlowCase]
    summary: BottleneckSummary


class VariantInfo(BaseModel):
    variant: str
    frequency: int
    percentage: float
    avg_duration_hours: float
    min_duration_hours: float
    max_duration_hours: float
    case_ids: list[str]


class VariantResponse(BaseModel):
    """Process variant analysis."""

    variants: list[VariantInfo]
    total_variants: int
    total_cases: int


# ---------------------------------------------------------------------------
# Process Digging — advanced P2P analysis (extends basic process mining)
# ---------------------------------------------------------------------------

class PerformanceDFGEdge(BaseModel):
    """Edge in the performance DFG — weighted by transition time."""

    source: str
    target: str
    count: int
    avg_hours: float
    median_hours: float
    p95_hours: float
    min_hours: float
    max_hours: float


class PerformanceDFGResponse(BaseModel):
    """Performance DFG — edges weighted by avg transition time (hours)."""

    type: str = "performance"
    nodes: list[str]
    edges: list[PerformanceDFGEdge]
    total_cases: int
    total_events: int


class ConformanceCaseResult(BaseModel):
    """Per-case conformance check result."""

    case_id: str
    fitness: float = Field(..., ge=0, le=1, description="Fraction of reference activities present")
    is_conforming: bool
    activities_present: int
    activities_missing: list[str]
    activities_extra: list[str]
    order_correct: bool
    trace: str


class ConformanceResponse(BaseModel):
    """Conformance checking — discovered process vs reference path."""

    reference_path: str
    total_cases: int
    conforming_cases: int
    conformance_rate: float = Field(..., ge=0, le=1)
    avg_fitness: float = Field(..., ge=0, le=1)
    cases: list[ConformanceCaseResult]


class HandoverNode(BaseModel):
    """Resource node in the social network."""

    resource: str
    activities: list[str]
    cases_involved: int


class HandoverEdge(BaseModel):
    """Edge in the resource handover graph."""

    from_resource: str
    to_resource: str
    handover_count: int


class HandoverResponse(BaseModel):
    """Resource handover / social network analysis."""

    available: bool
    message: str = ""
    nodes: list[HandoverNode] = []
    edges: list[HandoverEdge] = []
    total_handovers: int = 0
    unique_resources: int = 0


# ---------------------------------------------------------------------------
# Process Digging — v2.5 extensions (Rework, SLA, Anomalies)
# ---------------------------------------------------------------------------

class ReworkCase(BaseModel):
    """Case with repeated activities (rework/loops)."""

    case_id: str
    repeated_activities: list[str]
    rework_count: int
    extra_cost: float = 0.0


class ReworkActivityStat(BaseModel):
    """Activity frequently involved in rework."""

    activity: str
    rework_count: int
    case_count: int = 0


class ReworkResponse(BaseModel):
    """Rework detection analysis."""

    rework_cases: list[ReworkCase]
    rework_rate: float = Field(..., ge=0, le=1)
    total_rework_cost: float = 0.0
    most_reworked_activities: list[ReworkActivityStat]
    total_cases: int
    cases_with_rework: int


class SLACase(BaseModel):
    """SLA monitoring per case."""

    case_id: str
    duration_hours: float
    target_hours: float
    within_sla: bool
    excess_hours: float = 0.0


class SLAMonitorResponse(BaseModel):
    """SLA monitoring results."""

    target_hours: float
    total_cases: int
    cases_within_sla: int
    breach_count: int
    breach_rate: float = Field(..., ge=0, le=1)
    breaches: list[SLACase]
    avg_duration_hours: float = 0.0
    median_duration_hours: float = 0.0


class AnomalyCase(BaseModel):
    """Statistical anomaly case."""

    case_id: str
    duration_hours: float
    z_score: float
    deviation_hours: float
    trace: str = ""
    num_events: int = 0


class AnomalyResponse(BaseModel):
    """Anomaly detection results."""

    mean_hours: float
    std_hours: float
    threshold_hours: float
    z_threshold: float = 2.0
    anomalies: list[AnomalyCase]
    anomaly_rate: float = Field(..., ge=0, le=1)
    total_cases: int


class FullProcessDiggingReport(BaseModel):
    """Aggregated process digging report — all analyses in one call."""

    dfg_frequency: DFGResponse
    dfg_performance: PerformanceDFGResponse
    lead_times: LeadTimeResponse
    bottlenecks: BottleneckResponse
    variants: VariantResponse
    conformance: ConformanceResponse
    handovers: HandoverResponse
    rework: ReworkResponse
    sla_monitor: SLAMonitorResponse
    anomalies: AnomalyResponse


# ---------------------------------------------------------------------------
# What-If Scenario Engine (v2.5)
# ---------------------------------------------------------------------------

class ScenarioSpec(BaseModel):
    """Parameters for one what-if scenario."""

    label: str = Field(..., min_length=1, max_length=50)
    lambda_param: float = Field(0.5, ge=0.0, le=1.0)
    w_cost: float = Field(0.40, ge=0.0, le=1.0)
    w_time: float = Field(0.30, ge=0.0, le=1.0)
    w_compliance: float = Field(0.15, ge=0.0, le=1.0)
    w_esg: float = Field(0.15, ge=0.0, le=1.0)
    mode: SolverMode = SolverMode.continuous
    max_vendor_share: float = Field(1.0, ge=0.0, le=1.0)
    sla_floor: Optional[float] = Field(None, ge=0.0, le=1.0)
    total_budget: Optional[float] = Field(None, gt=0)
    max_products_per_supplier: Optional[int] = Field(None, ge=1)


class ScenarioResultSchema(BaseModel):
    """Result of a single scenario."""

    label: str
    mode: str
    success: bool
    message: str = ""
    objective_total: float = 0.0
    cost_component: float = 0.0
    time_component: float = 0.0
    compliance_component: float = 0.0
    esg_component: float = 0.0
    total_cost_pln: float = 0.0
    suppliers_used: int = 0
    products_covered: int = 0
    solve_time_ms: float = 0.0
    allocations_count: int = 0


class ComparisonRow(BaseModel):
    """One row of the comparison matrix."""

    metric: str
    values: dict[str, float]
    best: str


class WhatIfRequest(BaseModel):
    """Request for what-if scenario comparison."""

    suppliers: list[SupplierInput] = Field(..., min_length=1)
    demand: list[DemandItem] = Field(..., min_length=1)
    scenarios: list[ScenarioSpec] = Field(..., min_length=2, max_length=10)


class WhatIfResponse(BaseModel):
    """Response from what-if scenario engine."""

    scenarios: list[ScenarioResultSchema]
    comparison: list[ComparisonRow]
    best_scenario: Optional[str] = None
    total_scenarios: int
    total_time_ms: float


# ---------------------------------------------------------------------------
# Alerts (v2.5)
# ---------------------------------------------------------------------------

class AlertSchema(BaseModel):
    """Single alert."""

    id: str
    severity: str  # info, warning, critical
    category: str  # optimization, process, compliance
    title: str
    description: str
    metric_value: float = 0.0
    threshold: float = 0.0
    entity_id: Optional[str] = None
    timestamp: str


class AlertSummary(BaseModel):
    """Alert counts by severity."""

    total: int
    critical: int
    warning: int
    info: int


class AlertsResponse(BaseModel):
    """Response from alerts engine."""

    alerts: list[AlertSchema]
    summary: AlertSummary


class AlertThresholds(BaseModel):
    """Configurable alert thresholds."""

    budget_warning_pct: float = Field(95.0, ge=0, le=100)
    max_supplier_share_warn: float = Field(0.80, ge=0, le=1)
    cost_component_warn: float = Field(0.70, ge=0, le=1)
    sla_target_hours: float = Field(120.0, gt=0)
    conformance_warn: float = Field(0.50, ge=0, le=1)
    bottleneck_p95_hours: float = Field(48.0, gt=0)
    rework_rate_warn: float = Field(0.30, ge=0, le=1)
    anomaly_z_threshold: float = Field(2.0, gt=0)


# ---------------------------------------------------------------------------
# MIP Dedicated Engine — IT-specific binary optimisation
# ---------------------------------------------------------------------------

class MipAllocationRow(BaseModel):
    """Single allocation in MIP result (binary = full demand to one supplier)."""

    supplier_id: str
    supplier_name: str
    product_id: str
    allocated_qty: float
    allocated_fraction: float = 1.0
    unit_cost: float
    logistics_cost: float
    lead_time_days: float
    compliance_score: float
    esg_score: float
    total_line_cost: float = 0.0


class MipDiagnostics(BaseModel):
    """Diagnostics from the dedicated MIP engine."""

    total_cost_pln: float = 0.0
    budget_used_pct: float = 0.0
    suppliers_selected: int = 0
    products_covered: int = 0
    infeasible_products: list[str] = []
    sla_floor_active: bool = False
    budget_ceiling_active: bool = False
    max_products_per_supplier_active: bool = False


class MipObjectiveBreakdown(BaseModel):
    """Objective function breakdown for MIP."""

    total: float
    cost_component: float
    time_component: float
    compliance_component: float
    esg_component: float


class MipOptimizationRequest(BaseModel):
    """Request for the dedicated MIP endpoint with IT-specific constraints."""

    suppliers: list[SupplierInput] = Field(..., min_length=1)
    demand: list[DemandItem] = Field(..., min_length=1)
    weights: CriteriaWeights = Field(default_factory=CriteriaWeights)
    max_vendor_share: float = Field(1.0, ge=0.0, le=1.0, description="Max fraction per supplier (1.0 = no limit)")
    sla_floor: Optional[float] = Field(None, ge=0.0, le=1.0, description="Min compliance/SLA score to be eligible")
    total_budget: Optional[float] = Field(None, gt=0, description="Budget ceiling in PLN")
    max_products_per_supplier: Optional[int] = Field(None, ge=1, description="Max products one supplier can serve")
    constraints: Optional[ConstraintConfig] = Field(
        None, description="Advanced constraints C10-C15 (optional)",
    )


class MipOptimizationResponse(BaseModel):
    """Response from the dedicated MIP engine."""

    success: bool
    message: str = ""
    status: str = "unknown"
    solve_time_ms: float = 0.0
    objective: MipObjectiveBreakdown
    allocations: list[MipAllocationRow] = []
    diagnostics: MipDiagnostics
    weights_used: CriteriaWeights


# ---------------------------------------------------------------------------
# Domain / Subdomain metadata (v3.0)
# ---------------------------------------------------------------------------

class SubDomainInfo(BaseModel):
    """Metadata for one subdomain."""

    subdomain: str
    label: str
    label_pl: str
    suppliers_count: int
    demand_items: int


class DomainInfoExtended(BaseModel):
    """Extended domain info with subdomains."""

    domain: str
    label: str
    label_pl: str
    icon: str
    category: str  # direct / indirect
    subdomains: list[SubDomainInfo]
    total_suppliers: int
    total_demand_items: int
    default_weights: dict


# ---------------------------------------------------------------------------
# Dashboard — Sankey / Donut / Trend (v3.0)
# ---------------------------------------------------------------------------

class SankeyNode(BaseModel):
    id: str
    label: str
    type: str  # "supplier" | "product"


class SankeyLink(BaseModel):
    source: str
    target: str
    value: float
    label: str = ""


class SankeyResponse(BaseModel):
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    total_flow: float


class DonutSegment(BaseModel):
    supplier_id: str
    supplier_name: str
    total_cost_pln: float
    fraction: float


class DonutResponse(BaseModel):
    segments: list[DonutSegment]
    total_cost_pln: float


class DomainTrendPoint(BaseModel):
    domain: str
    label: str
    objective_total: float
    cost_component: float
    time_component: float
    compliance_component: float
    esg_component: float
    total_cost_pln: float
    suppliers_used: int


class DomainTrendResponse(BaseModel):
    points: list[DomainTrendPoint]
    total_domains: int


# ---------------------------------------------------------------------------
# RFQ Integration — Generic Open API (v3.1)
# ---------------------------------------------------------------------------

class RfqLineItem(BaseModel):
    """Single line item in an RFQ."""

    line_item_id: str = Field(..., examples=["LI-001"])
    material_number: str = Field(..., examples=["BRK-PAD-0041"])
    description: str = ""
    quantity: float = Field(..., gt=0)
    unit_of_measure: str = Field("PC", examples=["PC", "KG", "L"])
    required_delivery_date: str = Field(..., description="ISO date YYYY-MM-DD")
    destination_plant: str = Field("PL01", description="Plant / warehouse code")
    destination_region: str = Field(..., description="Region code e.g. 'PL-MA'")
    estimated_unit_price: Optional[float] = Field(None, ge=0)
    currency: str = "PLN"


class RfqSupplierBid(BaseModel):
    """Supplier's bid response to an RFQ line item."""

    supplier_id: str
    supplier_name: str
    line_item_id: str
    bid_unit_price: float = Field(..., ge=0)
    bid_logistics_cost: float = Field(0.0, ge=0)
    lead_time_days: float = Field(..., ge=0)
    compliance_score: float = Field(..., ge=0, le=1)
    esg_score: float = Field(..., ge=0, le=1)
    payment_terms_days: float = Field(30.0, ge=0)
    capacity: float = Field(..., gt=0)
    regions_served: list[str] = Field(..., min_length=1)
    valid_until: Optional[str] = None


class RfqHeader(BaseModel):
    """Generic RFQ header — compatible with any sourcing system."""

    rfq_id: str = Field(..., examples=["RFQ-2026-001"])
    title: str = ""
    procurement_domain: str = Field("parts")
    buyer_org: str = "Flow Procurement SA"
    created_at: str = ""
    deadline: str = ""
    currency: str = "PLN"
    line_items: list[RfqLineItem] = Field(..., min_length=1)
    bids: list[RfqSupplierBid] = Field(default_factory=list)
    status: str = Field("draft", description="draft|active|closed|awarded")


class RfqImportRequest(BaseModel):
    rfq: RfqHeader
    auto_optimize: bool = Field(False, description="Run optimizer immediately after import")
    optimization_mode: SolverMode = Field(SolverMode.continuous)


class RfqResponse(BaseModel):
    success: bool
    rfq_id: str
    message: str = ""
    imported_line_items: int = 0
    imported_bids: int = 0
    optimization_result: Optional[OptimizationResponse] = None


class RfqExportRow(BaseModel):
    """Single row in an RFQ export (generic — works with any ERP/sourcing system)."""

    rfq_id: str
    line_item_id: str
    awarded_supplier_id: str
    awarded_supplier_name: str
    material_number: str
    awarded_quantity: float
    unit_price: float
    logistics_cost: float
    total_line_value_pln: float
    lead_time_days: float
    purchase_order_type: str = "STANDARD"
    plant: str = "PL01"


class RfqExportRequest(BaseModel):
    rfq_id: str
    allocations: list[AllocationRow]
    line_items: list[RfqLineItem]


class RfqExportResponse(BaseModel):
    success: bool
    rfq_id: str
    export_format: str = "GENERIC-RFQ-JSON"
    rows: list[RfqExportRow]
    total_value_pln: float


class IntegrationStatusResponse(BaseModel):
    rfq_import_configured: bool
    rfq_export_configured: bool
    import_url: str = ""
    export_url: str = ""
    pending_rfqs: int = 0


class WebhookPayload(BaseModel):
    event_type: str = Field(..., description="rfq.created|rfq.updated|bid.received|rfq.closed")
    rfq_id: str
    timestamp: str = ""
    payload: dict = Field(default_factory=dict)


class WebhookResponse(BaseModel):
    success: bool
    event_type: str
    processed: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Risk Engine — Heatmap, Monte Carlo, Negotiation (v3.0)
# ---------------------------------------------------------------------------

class RiskCellSchema(BaseModel):
    supplier_id: str
    supplier_name: str
    product_id: str
    risk_score: float
    single_source_risk: float
    capacity_utilization: float
    esg_risk: float
    risk_label: str  # low | medium | high | critical


class RiskHeatmapResponse(BaseModel):
    cells: list[RiskCellSchema]
    suppliers: list[str]
    products: list[str]
    critical_count: int = 0
    high_count: int = 0
    overall_risk_score: float = 0.0


class MonteCarloRequest(BaseModel):
    suppliers: list[SupplierInput] = Field(..., min_length=1)
    demand: list[DemandItem] = Field(..., min_length=1)
    weights: CriteriaWeights = Field(default_factory=CriteriaWeights)
    n_iterations: int = Field(500, ge=50, le=5000)
    cost_std_pct: float = Field(0.10, ge=0.01, le=0.50)
    time_std_pct: float = Field(0.15, ge=0.01, le=0.50)
    max_vendor_share: float = Field(1.0, ge=0, le=1)
    seed: Optional[int] = 42


class SupplierStability(BaseModel):
    supplier_id: str
    supplier_name: str
    selection_rate: float


class MonteCarloResponse(BaseModel):
    n_iterations: int
    feasible_rate: float
    cost_mean_pln: float
    cost_std_pln: float
    cost_p5_pln: float
    cost_p95_pln: float
    objective_mean: float
    objective_std: float
    robustness_score: float
    supplier_stability: list[SupplierStability]
    cost_histogram: list[float] = Field(default_factory=list, description="Binned cost distribution")


class NegotiationTargetSchema(BaseModel):
    supplier_id: str
    supplier_name: str
    current_share_pct: float
    current_total_cost_pln: float
    estimated_saving_pln: float
    target_reduction_pct: float
    negotiation_priority: str  # high | medium | low
    rationale: str


class NegotiationResponse(BaseModel):
    targets: list[NegotiationTargetSchema]
    total_estimated_savings_pln: float
    analyzed_suppliers: int


# ---------------------------------------------------------------------------
# Supplier Management — profiles, certificates, contacts, self-assessment
# ---------------------------------------------------------------------------

class CertificationType(str, Enum):
    iso_9001 = "iso_9001"
    iso_14001 = "iso_14001"
    iatf_16949 = "iatf_16949"
    iso_45001 = "iso_45001"
    iso_50001 = "iso_50001"
    emas = "emas"
    other = "other"


class ContactRole(str, Enum):
    sales = "sales"
    key_account = "key_account"
    quality = "quality"
    logistics = "logistics"
    management = "management"
    other = "other"


class SupplierCertificate(BaseModel):
    cert_id: str = ""
    cert_type: CertificationType = CertificationType.iso_9001
    issuer: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    file_url: Optional[str] = None
    notes: str = ""


class ContactPerson(BaseModel):
    contact_id: str = ""
    name: str
    role: ContactRole = ContactRole.sales
    email: str = ""
    phone: str = ""
    is_primary: bool = False


class SelfAssessmentQuestion(BaseModel):
    question_id: str
    category: str  # quality | delivery | sustainability | innovation
    question_text: str
    weight: float = 1.0


class SelfAssessmentAnswer(BaseModel):
    question_id: str
    score: int = Field(..., ge=1, le=5)
    comment: str = ""


class SelfAssessmentResponse(BaseModel):
    supplier_id: str
    submitted_at: str
    answers: list[SelfAssessmentAnswer]
    overall_score: float
    category_scores: dict[str, float]


class SupplierProfile(BaseModel):
    supplier_id: str
    name: str
    nip: str = ""
    vat_valid: bool = False
    address: str = ""
    country_code: str = "PL"
    website: str = ""
    founded_year: Optional[int] = None
    employee_count: Optional[int] = None
    annual_revenue_pln: Optional[float] = None
    domains: list[str] = Field(default_factory=list)
    certificates: list[SupplierCertificate] = Field(default_factory=list)
    contacts: list[ContactPerson] = Field(default_factory=list)
    self_assessment: Optional[SelfAssessmentResponse] = None
    optimizer_input: Optional[SupplierInput] = None
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""


class ViesLookupRequest(BaseModel):
    country_code: str = Field("PL", max_length=2)
    vat_number: str = Field(..., min_length=5, max_length=15)


class ViesLookupResponse(BaseModel):
    valid: bool = False
    name: str = ""
    address: str = ""
    country_code: str = ""
    vat_number: str = ""
    request_date: str = ""


class SupplierCreateRequest(BaseModel):
    nip: str = Field(..., min_length=10, max_length=10)
    name_override: Optional[str] = None
    address_override: Optional[str] = None
    domains: list[str] = Field(default_factory=lambda: ["parts"])
