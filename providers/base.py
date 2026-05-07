"""Abstract base class for AI providers."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        return cls(role=d["role"], content=d.get("content", ""))


class Provider(ABC):
    """Base class for AI model providers."""

    def __init__(self, config: dict):
        self.config = config
        self._model = config.get("model", "unknown")

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, name: str):
        self._model = name

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Send a chat request and stream the response."""
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models."""
        ...

    async def check_connection(self) -> tuple[bool, str]:
        """Check if the provider is reachable. Returns (ok, message)."""
        try:
            models = await self.list_models()
            return True, f"Connected. {len(models)} models available."
        except Exception as e:
            return False, str(e)

    def format_model_list(self, models: list[str]) -> list[str]:
        """Format model list for display."""
        return sorted(models)
