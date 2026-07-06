"""Provider-based AI service layer for DENZ.

The Flask app builds DENZ-specific prompts and context. This module only knows
how to send those prompts to the configured AI provider.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from dataclasses import dataclass
from typing import Any

import requests


logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Raised when the configured AI provider cannot complete a request."""


@dataclass(frozen=True)
class AIConfig:
    provider: str
    ollama_url: str
    ollama_model: str
    ollama_vision_model: str
    ollama_timeout: float
    groq_api_key: str
    groq_model: str
    groq_vision_model: str
    groq_timeout: float

    @classmethod
    def from_env(cls) -> "AIConfig":
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:8b").strip()
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        return cls(
            provider=os.getenv("AI_PROVIDER", "ollama").strip().lower(),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            ollama_model=ollama_model,
            ollama_vision_model=os.getenv("OLLAMA_VISION_MODEL", ollama_model).strip(),
            ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT", "15")),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=groq_model,
            groq_vision_model=os.getenv("GROQ_VISION_MODEL", groq_model).strip(),
            groq_timeout=float(os.getenv("GROQ_TIMEOUT", "45")),
        )


class BaseAIProvider:
    name = "base"

    def __init__(self, config: AIConfig):
        self.config = config

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: float | None = None,
    ) -> str:
        raise NotImplementedError

    def analyze_image(self, image_path: str, prompt: str, *, timeout: float | None = None) -> str:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def warmup(self) -> bool:
        return self.health().get("ready", False)


class OllamaProvider(BaseAIProvider):
    name = "ollama"

    @property
    def model_name(self) -> str:
        return self.config.ollama_model

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: float | None = None,
    ) -> str:
        response = requests.post(
            f"{self.config.ollama_url}/api/generate",
            json={
                "model": self.config.ollama_model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": 8192 if max_tokens > 128 else 1024,
                },
            },
            timeout=timeout or self.config.ollama_timeout,
        )
        response.raise_for_status()
        return (response.json().get("response") or "").strip()

    def analyze_image(self, image_path: str, prompt: str, *, timeout: float | None = None) -> str:
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")

        response = requests.post(
            f"{self.config.ollama_url}/api/generate",
            json={
                "model": self.config.ollama_vision_model,
                "prompt": prompt,
                "images": [encoded],
                "stream": False,
                "think": False,
            },
            timeout=timeout or max(self.config.ollama_timeout, 30),
        )
        response.raise_for_status()
        return (response.json().get("response") or "").strip()

    def health(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "provider": self.name,
            "connected": False,
            "ready": False,
            "url": self.config.ollama_url,
            "model": self.config.ollama_model,
            "models": [],
        }
        try:
            response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=3)
            status["connected"] = response.status_code == 200
            if status["connected"]:
                models = [model.get("name") for model in response.json().get("models", [])]
                status["models"] = models
                status["model_available"] = self.config.ollama_model in models
                status["ready"] = status["model_available"]
        except Exception as error:
            status["error"] = str(error)
        return status

    def warmup(self) -> bool:
        health = self.health()
        if not health.get("connected"):
            return False

        if not health.get("model_available"):
            response = requests.post(
                f"{self.config.ollama_url}/api/pull",
                json={"name": self.config.ollama_model},
                timeout=120,
            )
            response.raise_for_status()

        answer = self.generate_text(
            "Hello, respond with 'Ready' only.",
            temperature=0.1,
            max_tokens=10,
            timeout=60,
        )
        return bool(answer)


class GroqProvider(BaseAIProvider):
    name = "groq"
    api_url = "https://api.groq.com/openai/v1/chat/completions"

    @property
    def model_name(self) -> str:
        return self.config.groq_model

    def _headers(self) -> dict[str, str]:
        if not self.config.groq_api_key:
            raise AIServiceError("GROQ_API_KEY is not configured.")
        return {
            "Authorization": f"Bearer {self.config.groq_api_key}",
            "Content-Type": "application/json",
        }

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: float | None = None,
    ) -> str:
        response = requests.post(
            self.api_url,
            headers=self._headers(),
            json={
                "model": self.config.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout or self.config.groq_timeout,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message", {}).get("content") or "").strip()

    def analyze_image(self, image_path: str, prompt: str, *, timeout: float | None = None) -> str:
        mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")

        response = requests.post(
            self.api_url,
            headers=self._headers(),
            json={
                "model": self.config.groq_vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                            },
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=timeout or max(self.config.groq_timeout, 45),
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message", {}).get("content") or "").strip()

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "connected": bool(self.config.groq_api_key),
            "ready": bool(self.config.groq_api_key),
            "model": self.config.groq_model,
            "vision_model": self.config.groq_vision_model,
            "api_key_configured": bool(self.config.groq_api_key),
        }


class AIService:
    """Facade used by Flask routes and helpers."""

    def __init__(self, config: AIConfig | None = None):
        self.config = config or AIConfig.from_env()
        self.provider = self._build_provider()

    def _build_provider(self) -> BaseAIProvider:
        if self.config.provider == "groq":
            return GroqProvider(self.config)
        if self.config.provider == "ollama":
            return OllamaProvider(self.config)
        logger.warning("Unknown AI_PROVIDER=%s; falling back to Ollama", self.config.provider)
        return OllamaProvider(self.config)

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        try:
            return self.provider.generate_text(prompt, **kwargs)
        except AIServiceError:
            raise
        except Exception as error:
            logger.exception("%s text generation failed", self.provider.name)
            raise AIServiceError(str(error)) from error

    def analyze_image(self, image_path: str, prompt: str, **kwargs: Any) -> str:
        try:
            return self.provider.analyze_image(image_path, prompt, **kwargs)
        except AIServiceError:
            raise
        except Exception as error:
            logger.exception("%s image analysis failed", self.provider.name)
            raise AIServiceError(str(error)) from error

    def health(self) -> dict[str, Any]:
        return self.provider.health()

    def warmup(self) -> bool:
        try:
            return self.provider.warmup()
        except Exception as error:
            logger.warning("%s warmup failed: %s", self.provider.name, error)
            return False


ai_service = AIService()
