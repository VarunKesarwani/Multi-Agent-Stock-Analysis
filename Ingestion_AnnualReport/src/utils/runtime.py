"""Validated retrieval and answer generation settings."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.utils.settings import env_path, env_values


class RuntimeSettings(BaseModel):
    """Non-embedding settings; embedding configuration stays shared with ingestion."""

    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)
    llm_provider: Literal["ollama", "openai"] = "ollama"
    llm_model: str = Field(default="llama3.2:3b", min_length=1)
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr = SecretStr("")
    timeout: float = Field(default=120, gt=0)
    max_tokens: int = Field(default=1024, ge=1, le=16384)
    top_k: int = Field(default=5, ge=1, le=20)
    context_chars: int = Field(default=16000, ge=100, le=100000)
    log_file: Path = Path("logs/app.log")

    @classmethod
    def from_env(cls, env_file: Path | str | None = None) -> "RuntimeSettings":
        """Load the same YAML/.env/environment precedence as ingestion."""
        v, root = env_values(env_file)
        provider = v.get("LLM_PROVIDER", "ollama").lower()
        return cls(
            llm_provider=provider,
            llm_model=v.get(
                "LLM_MODEL", "llama3.2:3b" if provider == "ollama" else "gpt-4o-mini"
            ),
            ollama_url=v.get("OLLAMA_URL", "http://localhost:11434"),
            openai_base_url=v.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_api_key=SecretStr(v.get("OPENAI_API_KEY", "")),
            timeout=v.get("LLM_TIMEOUT_SECONDS", 120),
            max_tokens=v.get("LLM_MAX_TOKENS", 1024),
            top_k=v.get("RAG_TOP_K", 5),
            context_chars=v.get("RAG_CONTEXT_CHARS", 16000),
            log_file=env_path(v.get("LOG_FILE", "logs/app.log"), root),
        )
