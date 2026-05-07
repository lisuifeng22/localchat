"""OpenAI-compatible API provider."""

import json
from typing import AsyncGenerator

import httpx

from .base import Provider, ChatMessage


class OpenAIProvider(Provider):
    """Supports OpenAI, DeepSeek, Moonshot, ZhiPu, OpenRouter, etc."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            yield "\n[ERROR] API Key 未设置！使用 /key <your-key> 设置，或直接编辑 config.json"
            return
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with self.client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    error_msg = self._extract_error(resp.status_code, body)
                    yield f"\n[ERROR] {error_msg}"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = (
                            data.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

        except httpx.ConnectError:
            yield f"\n[ERROR] Cannot connect to {self.base_url}. Check your endpoint and network."
        except httpx.TimeoutException:
            yield "\n[ERROR] Request timed out. The model may be overloaded."
        except Exception as e:
            yield f"\n[ERROR] {e}"

    async def list_models(self) -> list[str]:
        """Fetch available models from the /models endpoint."""
        try:
            resp = await self.client.get("/models")
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
            return [self.model]
        except Exception:
            return [self.model]

    def _extract_error(self, status: int, body: bytes) -> str:
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", str(body))
        except (json.JSONDecodeError, AttributeError):
            msg = body.decode(errors="replace")[:200]
        return f"HTTP {status}: {msg}"

    async def close(self):
        await self.client.aclose()
