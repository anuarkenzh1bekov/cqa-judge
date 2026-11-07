from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    google_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # USD per 1M tokens; used only for the cost estimate shown in the UI. Verify against Google's price list.
    gemini_price_in_per_m: float = 0.30
    gemini_price_out_per_m: float = 2.50

    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_enabled: bool = True
    jev_price_in_per_m: float = 0.042
    # Jev disagreement with probability >= this triggers a Gemini re-check (adjudication).
    jev_adjudicate_threshold: float = 0.8

    dataset_api_url: str = ""
    database_url: str = f"sqlite:///{(ROOT / 'backend' / 'cqa.db').as_posix()}"

    max_concurrency: int = 4
    cors_origins: str = "*"


settings = Settings()
