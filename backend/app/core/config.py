from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = BACKEND_ROOT / "app" / "data" / "seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    provider: str = "mock"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ai_latency: float = 1.0  # 1 = simulated latency on, 0 = off
    log_level: str = "INFO"

    # Azure OpenAI (used when PROVIDER=azure_openai). The key is read from the environment or backend/.env only.
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment: str = "gpt-5-mini"
    azure_openai_api_version: str = "2025-04-01-preview"
    llm_timeout: float = 45.0  # seconds per call before falling back to the built-in narrator
    llm_max_tokens: int = 1500  # completion budget; reasoning models spend part of it on thinking
    llm_reasoning_effort: str = "low"  # minimal | low | medium | high ("" to leave the model default)
    llm_concurrency: int = 4  # simultaneous calls; pages request several summaries at once
    llm_verify_numbers: bool = True  # reject answers that contain figures not present in the facts
    app_name: str = "ArchIQ API"
    version: str = "0.1.0"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
