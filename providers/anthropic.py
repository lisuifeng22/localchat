"""Anthropic API provider (Claude)."""

import json
from typing import AsyncGenerator

import httpx

from .base import Provider, ChatMessage


class AnthropicProvider(Provider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.base_url = "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
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
        # Anthropic requires separate system param
        system = None
        anthropic_messages = []
        for m in messages:
            if m.role == "system":
                system = m.content
            elif m.role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": m.content})
            else:
                anthropic_messages.append({"role": "user", "content": m.content})

        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system

        try:
            async with self.client.stream(
                "POST", "/messages", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"\n[ERROR] HTTP {resp.status_code}: {body.decode(errors='replace')[:200]}"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {}).get("text", "")
                            if delta:
                                yield delta
                    except json.JSONDecodeError:
                        continue

        except httpx.ConnectError:
            yield "\n[ERROR] Cannot connect to Anthropic API."
        except httpx.TimeoutException:
            yield "\n[ERROR] Request timed out."
        except Exception as e:
            yield f"\n[ERROR] {e}"

    async def list_models(self) -> list[str]:
        return [
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-haiku-4-5",
            "claude-sonnet-4-6-20250101",
        ]

    async def close(self):
        await self.client.aclose()
