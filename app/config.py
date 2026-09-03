from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://connector:connector_pass@localhost:5432/security_connector"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://connector:connector_pass@localhost:5432/security_connector"
    )

    # JWT  (algorithm is hardcoded in app/auth/jwt.py — not configurable via env)
    jwt_secret_key: str = "change-this-to-a-strong-secret-in-production"
    jwt_expiry_minutes: int = 60

    # Email-to-role mapping: "email:ROLE,email:ROLE"
    user_role_map: str = ""

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"  # nosec B104 — required for Cloud Run and Docker
    app_port: int = 8000
    log_level: str = "INFO"
    # Comma-separated list of allowed CORS origins; "*" only for development
    cors_allowed_origins: str = "*"

    # Gemini — local dev only (not used on Cloud Run)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # GCP — Cloud Run / Vertex AI
    # Set GCP_PROJECT_ID on Cloud Run; ADK uses Vertex AI automatically
    # Set CONNECTOR_URL to point gemini_agent.py at the deployed /mcp endpoint
    gcp_project_id: str = ""
    connector_url: str = ""  # e.g. https://enterprise-security-connector-xxx.run.app


@lru_cache
def get_settings() -> Settings:
    return Settings()
