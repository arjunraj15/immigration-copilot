"""App settings read from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # The app connects as a limited role. Migrations connect as the database owner.
    database_url: str = "postgresql+psycopg://casedesk_app:casedesk_app@db:5432/casedesk"
    migration_database_url: str = "postgresql+psycopg://casedesk:casedesk@db:5432/casedesk"
    anthropic_api_key: str = ""
    analysis_model: str = "claude-opus-5-5"
    reading_model: str = "claude-sonnet-5-5"
    ai_run_capture: str = "full"
    ai_timeout_seconds: float = 120.0
    ai_max_attempts: int = 3
    ai_retry_base_seconds: float = 1.0
    storage_dir: str = "/app/storage"
    audit_checkpoint_file: str = "/app/storage/audit_checkpoint.json"
    starter_kit_dir: str = "/data/starter-kit"
    auto_read: bool = True
    home_cache_seconds: float = 10.0  # 0 turns the home queue cache off
    ocr_url: str = "http://docling:5001"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    duplicate_review_threshold: float = 90.0
    duplicate_similarity_excluded_categories: list[str] = ["PAY_STATEMENT"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
