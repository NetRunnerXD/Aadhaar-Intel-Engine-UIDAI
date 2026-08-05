"""Ollama HTTP client for local LLM insights."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional


DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:latest")


@dataclass
class OllamaStatus:
    available: bool
    host: str
    model: str
    models: List[str]
    error: Optional[str] = None


def strip_model_artifacts(text: str) -> str:
    """Remove chain-of-thought / tool noise some local models emit."""
    if not text:
        return ""
    # Qwen3 / thinking models
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.I)
    text = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.I)
    # Orphaned open tags
    text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.I)
    text = re.sub(r"```(?:markdown|md)?\s*", "", text)
    text = text.replace("```", "")
    return text.strip()


class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL, timeout: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def status(self) -> OllamaStatus:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in payload.get("models", [])]
            # Prefer exact, then prefix match (qwen2.5 matches qwen2.5:latest)
            if self.model not in models:
                base = self.model.split(":")[0]
                match = next((m for m in models if m == self.model or m.startswith(base + ":")), None)
                if match:
                    self.model = match
                elif models:
                    # Prefer instruct/chatty models if present
                    preferred = next(
                        (m for m in models if any(x in m.lower() for x in ("qwen2.5", "llama3", "mistral"))),
                        models[0],
                    )
                    self.model = preferred
            return OllamaStatus(True, self.host, self.model, models)
        except Exception as e:
            return OllamaStatus(False, self.host, self.model, [], str(e))

    def _options(self, temperature: float) -> Dict[str, Any]:
        return {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 700,
        }

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.25) -> str:
        body: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": self._options(temperature),
        }
        if system:
            body["system"] = system
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = strip_model_artifacts((payload.get("response") or "").strip())
            if not text:
                raise RuntimeError("Empty response from Ollama")
            return text
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama generate failed: {e}") from e

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.25) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": self._options(temperature),
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            msg = payload.get("message") or {}
            text = strip_model_artifacts((msg.get("content") or "").strip())
            if not text:
                raise RuntimeError("Empty chat response from Ollama")
            return text
        except Exception:
            system = next((m["content"] for m in messages if m.get("role") == "system"), None)
            user_parts = [m["content"] for m in messages if m.get("role") == "user"]
            return self.generate("\n\n".join(user_parts), system=system, temperature=temperature)


@lru_cache(maxsize=1)
def get_ollama_client() -> OllamaClient:
    return OllamaClient()


def insight_from_stats(
    title: str,
    stats: Dict[str, Any],
    instruction: str,
    client: Optional[OllamaClient] = None,
) -> str:
    """Legacy helper — prefer src.ai.research_insights.research_insight."""
    from src.ai.research_insights import research_insight

    return research_insight(
        title=title,
        evidence=stats,
        method=instruction,
        use_llm=True,
        client=client,
    )
