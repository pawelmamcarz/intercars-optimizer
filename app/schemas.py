"""
INTERCARS Order Portfolio Optimizer — Pydantic schemas.

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
    # ── INDIRECT (wspierają operacje) ──
    it_services = "it_services"         # Usługi IT / integratorzy
    logistics = "logistics"             # Logistyka i transport
    packaging = "packaging"             # Opakowania i materiały
    mro_supplies = "mro"                 # MRO (Maintenance, Repair, Operations)


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


class OptimizationResponse(BaseModel):
    """Standard response from /optimize."""

    success: bool
    message: str = ""
    solver_stats: SolverStats
    objective: ObjectiveBreakdown
    allocations: list[AllocationRow] = []
    weights_used: CriteriaWeights


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
