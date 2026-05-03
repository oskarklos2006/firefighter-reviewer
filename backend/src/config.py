from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-2.0-flash-exp:free"
    llm_max_tokens: int = 1000

    # Rule thresholds — tunable without touching rule code
    max_session_minutes: int = 120
    max_changes_single_table: int = 5
    business_hours_start: int = 7
    business_hours_end: int = 18


settings = Settings()