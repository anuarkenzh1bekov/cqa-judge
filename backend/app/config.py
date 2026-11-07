from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    google_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # USD per 1M tokens, Gemini 3.8 Flash paid Standard tier (ai.google.dev pricing, valid through 2026-12-31;
    # doubles to 1.50 / 7.50 from 2027-01-01). Output price includes thinking tokens.
    # reasoning effort for Gemini: "" = model default, or minimal / low / medium / high
    gemini_thinking: str = ""
    gemini_price_in_per_m: float = 0.75
    gemini_price_out_per_m: float = 3.75

    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_enabled: bool = True
    jev_price_in_per_m: float = 0.042
    # Jev disagreement with probability >= this triggers a Gemini re-check (adjudication).
    jev_adjudicate_threshold: float = 0.8

    # Client mood: a separate Gemini call on the transcript (does not affect the score). For calls with a
    # recording, the audio itself is also sent so the tone of voice is heard, not guessed from the text.
    # No separate audio price is listed for 3.8 Flash, so audio tokens are billed at the input price.
    mood_enabled: bool = True
    mood_audio: bool = True
    audio_max_mb: int = 15
    # Uploaded call recordings (transcription). In Docker: /data/audio on the volume.
    audio_dir: str = str(ROOT / "backend" / "audio")

    dataset_api_url: str = ""
    database_url: str = f"sqlite:///{(ROOT / 'backend' / 'cqa.db').as_posix()}"

    # On startup with an empty DB, load datasets/<SEED_DATASET>.json (dialogs only). Empty string disables it.
    seed_dataset: str = "DEV"

    # Corrections that reviewers made through appeals are fed back into the prompt (per criterion, newest first).
    calibration_enabled: bool = True
    calibration_examples: int = 3

    max_concurrency: int = 4
    cors_origins: str = "*"


settings = Settings()
