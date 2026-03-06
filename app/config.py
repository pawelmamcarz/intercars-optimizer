"""
Application configuration — fully parameterisable via env vars.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = "INTERCARS Order Portfolio Optimizer"
    app_version: str = "1.0.0"

    # Default solver
    default_solver_mode: str = "continuous"

    # Pareto front default resolution
    default_pareto_steps: int = 11

    # Default criteria weights
    default_lambda: float = 0.5
    default_w_cost: float = 0.40
    default_w_time: float = 0.30
    default_w_compliance: float = 0.15
    default_w_esg: float = 0.15

    # EWM connection (placeholder for real integration)
    ewm_base_url: str = "http://localhost:9000/ewm"
    ewm_api_key: str = ""

    # Solver limits
    solver_time_limit_seconds: float = 60.0
    mip_gap_tolerance: float = 1e-4

    model_config = {"env_prefix": "INTERCARS_"}


settings = Settings()
