from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    elasticsearch_url: str
    index: str
    username: str | None
    password: str | None
    api_key: str | None
    verify_certs: bool
    host: str
    port: int
    path: str
    allowed_hosts: tuple[str, ...]
    log_level: str
    max_results: int

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
            index=os.getenv("ELASTICSEARCH_INDEX", "news-enriched-*"),
            username=os.getenv("ELASTICSEARCH_USERNAME") or None,
            password=os.getenv("ELASTICSEARCH_PASSWORD") or None,
            api_key=os.getenv("ELASTICSEARCH_API_KEY") or None,
            verify_certs=_bool("ELASTICSEARCH_VERIFY_CERTS", True),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8002")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allowed_hosts=_csv(
                "MCP_ALLOWED_HOSTS",
                "localhost,localhost:*,127.0.0.1,127.0.0.1:*,newsdata-mcp,newsdata-mcp:*",
            ),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
            max_results=int(os.getenv("MCP_MAX_RESULTS", "200")),
        )
        if bool(settings.username) != bool(settings.password):
            raise ValueError("ELASTICSEARCH_USERNAME and ELASTICSEARCH_PASSWORD must be provided together.")
        if settings.api_key and settings.username:
            raise ValueError("Use either ELASTICSEARCH_API_KEY or username/password, not both.")
        if not settings.path.startswith("/"):
            raise ValueError("MCP_PATH must start with '/'.")
        return settings

