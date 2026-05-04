from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-prod"

    database_url: str = "sqlite+aiosqlite:///./helix_srop.db"
    chroma_persist_dir: str = "./chroma_db"

    google_api_key: str = ""
    groq_api_key: str = ""
    hf_token: str = ""
    llm_provider: str = "auto"

    adk_model: str = "gemini-2.0-flash"
    groq_model: str = "llama-3.3-70b-versatile"

    llm_timeout_seconds: int = 30
    tool_timeout_seconds: int = 10


def get_active_llm_provider() -> str:
    """Determine which LLM provider to use based on available keys."""
    if settings.groq_api_key:
        return "groq"
    elif settings.google_api_key:
        return "google"
    return "groq"  # default


settings = Settings()
