from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.anthropic.com/v1"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 1000

    max_session_minutes: int = 120
    max_changes_single_table: int = 5
    business_hours_start: int = 7
    business_hours_end: int = 18


settings = Settings()