from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Finance Tracker API"
    database_url: str = "sqlite:///./finance_tracker.db"
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    encryption_key: str = ""
    enable_remote_llm: bool = True
    llm_provider: str = "ollama"  # ollama | openai | openai_compatible
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b"
    llm_api_key: str = ""
    ollama_model: str = "qwen2.5:7b"
    # backward-compatible aliases
    openai_api_key: str = ""
    openai_model: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.openai_model:
            return self.openai_model
        return self.ollama_model or "qwen2.5:7b"

    @property
    def effective_llm_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        if self.openai_api_key:
            return self.openai_api_key
        return "ollama"


settings = Settings()
