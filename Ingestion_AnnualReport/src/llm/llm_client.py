"""Answer generation using local Ollama by default or OpenAI."""

import requests

from src.utils.runtime import RuntimeSettings


class LLMClient:
    """Own an HTTP session unless one is injected by a caller."""

    def __init__(self, settings: RuntimeSettings, session=None):
        self.settings = settings
        self.session = session or requests.Session()
        self._owned = session is None

    def generate(self, messages: list[dict]) -> str:
        """Generate a bounded non-streaming answer; propagate provider failures."""
        s = self.settings
        if s.llm_provider == "ollama":
            response = self.session.post(
                s.ollama_url.rstrip("/") + "/api/chat",
                json={
                    "model": s.llm_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": s.max_tokens},
                },
                timeout=(5, s.timeout),
            )
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content")
        else:
            key = s.openai_api_key.get_secret_value()
            if not key:
                raise ValueError(
                    "OPENAI_API_KEY is required for OpenAI answer generation"
                )
            response = self.session.post(
                s.openai_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": s.llm_model,
                    "messages": messages,
                    "max_completion_tokens": s.max_tokens,
                },
                timeout=(5, s.timeout),
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            answer = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("LLM returned an empty answer")
        return answer.strip()

    def close(self) -> None:
        """Release owned connections."""
        if self._owned:
            self.session.close()
