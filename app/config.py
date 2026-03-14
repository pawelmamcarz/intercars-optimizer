"""
Application configuration — fully parameterisable via env vars.
"""
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = "Flow Procurement Platform"
    app_version: str = "4.1.1"

    # Default solver
    default_solver_mode: str = "continuous"

    # Pareto front default resolution
    default_pareto_steps: int = 11

    # Default criteria weights (Parts domain — baseline)
    default_lambda: float = 0.5
    default_w_cost: float = 0.40
    default_w_time: float = 0.30
    default_w_compliance: float = 0.15
    default_w_esg: float = 0.15

    # Per-domain default weights (dict-style — used by routes)
    # Format: {domain: (w_cost, w_time, w_compliance, w_esg)}
    # Stored as individual env-overridable fields for IT (legacy)
    default_it_w_cost: float = 0.35
    default_it_w_time: float = 0.25
    default_it_w_compliance: float = 0.20   # SLA
    default_it_w_esg: float = 0.20          # Niezawodność / Reliability

    # Vendor Diversification Policy
    diversification_enabled: bool = True
    default_max_vendor_share: float = 0.60  # max 60% of total volume per supplier

    # Turso / libsql database (optional — app works without it)
    turso_database_url: Optional[str] = None
    turso_auth_token: Optional[str] = None

    # EWM connection (placeholder for real integration)
    ewm_base_url: str = "http://localhost:9000/ewm"
    ewm_api_key: str = ""

    # Process Mining — SLA & anomaly defaults
    default_sla_target_hours: float = 120.0       # 5 days default SLA target
    default_anomaly_z_threshold: float = 2.0      # z-score threshold for anomalies

    # Constraint defaults (C10–C15)
    default_min_supplier_count: int = 2
    default_min_esg_score: float = 0.70
    default_max_payment_terms_days: float = 60.0
    default_preferred_supplier_bonus: float = 0.05

    # Integration — Generic RFQ API (vendor-agnostic, no SAP/Ariba lock-in)
    rfq_import_url: str = "https://rfq.flowproc.eu/api/v1/import"
    rfq_export_url: str = "https://rfq.flowproc.eu/api/v1/export"
    rfq_import_api_key: str = ""
    rfq_export_api_key: str = ""
    webhook_secret: str = ""

    # Monte Carlo simulation
    monte_carlo_iterations: int = 1000
    monte_carlo_cost_std_pct: float = 0.10
    monte_carlo_time_std_pct: float = 0.15

    # JWT Authentication
    jwt_secret: str = ""  # set via FLOW_JWT_SECRET env var
    jwt_access_expire_minutes: int = 480
    jwt_refresh_expire_days: int = 30

    # AI Copilot — LLM backend (Claude primary, Gemini fallback)
    llm_provider: str = "claude"  # primary: "claude" or "gemini"
    llm_api_key: str = ""         # set via FLOW_LLM_API_KEY env var
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 512
    llm_temperature: float = 0.3

    # Gemini fallback
    gemini_api_key: str = ""      # set via FLOW_GEMINI_API_KEY env var
    gemini_model: str = "gemini-2.0-flash"

    # Solver limits
    solver_time_limit_seconds: float = 60.0
    mip_gap_tolerance: float = 1e-4

    model_config = {"env_prefix": "FLOW_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
