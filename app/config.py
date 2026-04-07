"""Decision Memo Service — configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration with env-var overrides."""

    APP_NAME: str = "decision-memo-service"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8600

    # Upstream services
    SCORING_SERVICE_URL: str = "http://localhost:8003"
    DEMAND_LAYER_URL: str = "http://localhost:8090"
    TCS_URL: str = "http://localhost:8400"

    # API keys
    SCORING_API_KEY: str = ""
    TCS_API_KEY: str = ""

    # Timeouts (seconds)
    UPSTREAM_TIMEOUT: float = 10.0
    UPSTREAM_RETRIES: int = 2

    # Rule engine version
    RULE_ENGINE_VERSION: str = "1.0.0"

    # Database (Phase 5+)
    DATABASE_URL: str = "sqlite:///./decision_memo.db"

    class Config:
        env_prefix = "DMS_"


settings = Settings()
