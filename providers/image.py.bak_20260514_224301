"""Image generation provider — connects to Stable Diffusion WebUI (AUTOMATIC1111)."""

from abc import ABC, abstractmethod
from base64 import b64decode

import httpx


class ImageProvider(ABC):
    """Abstract base for image generation backends."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> bytes:
        """Generate an image from a text prompt. Returns raw PNG bytes."""
        ...


class SDWebUIProvider(ImageProvider):
    """Generates images via AUTOMATIC1111's Stable Diffusion WebUI API."""

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://127.0.0.1:7860").rstrip("/")
        self.default_params = {
            "default_prompt": config.get("default_prompt", ""),
            "negative_prompt": config.get("negative_prompt", ""),
            "steps": config.get("steps", 20),
            "width": config.get("width", 512),
            "height": config.get("height", 512),
            "cfg_scale": config.get("cfg_scale", 7.0),
        }
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def generate(self, prompt: str, **kwargs) -> bytes:
        # Merge default prompt into positive prompt if not overridden
        default_prompt = kwargs.pop("default_prompt", self.default_params.get("default_prompt", ""))
        if default_prompt and default_prompt not in prompt:
            prompt = f"{default_prompt}, {prompt}"

        params = {**self.default_params, "prompt": prompt}
        params.update(kwargs)
        payload = {
            "prompt": params["prompt"],
            "negative_prompt": params["negative_prompt"],
            "steps": params["steps"],
            "width": params["width"],
            "height": params["height"],
            "cfg_scale": params["cfg_scale"],
        }
        try:
            resp = await self.client.post("/sdapi/v1/txt2img", json=payload)
            resp.raise_for_status()
            data = resp.json()
            images = data.get("images", [])
            if not images:
                raise RuntimeError("SD WebUI returned no images")
            raw = images[0]
            if isinstance(raw, dict):
                raw = raw.get("data", "")
            return b64decode(raw)
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Stable Diffusion WebUI at {self.base_url}. "
                "Make sure AUTOMATIC1111 is running with --api flag."
            )
        except httpx.TimeoutException:
            raise TimeoutError("Image generation timed out after 120s. "
                               "Try reducing steps or resolution.")

    async def close(self):
        await self.client.aclose()
