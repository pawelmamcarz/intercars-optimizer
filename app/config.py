"""
Application configuration — fully parameterisable via env vars.
"""
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = "INTERCARS Order Portfolio Optimizer"
    app_version: str = "2.3.0"

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

    # Solver limits
    solver_time_limit_seconds: float = 60.0
    mip_gap_tolerance: float = 1e-4

    model_config = {"env_prefix": "INTERCARS_"}


settings = Settings()
