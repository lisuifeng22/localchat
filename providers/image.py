"""Image generation provider — connects to Stable Diffusion WebUI (AUTOMATIC1111)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64decode
from typing import Any

import httpx


class ImageProvider(ABC):
    """Abstract base for image generation backends."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> bytes:
        """Generate an image from a text prompt. Returns raw PNG bytes."""
        raise NotImplementedError


class SDWebUIProvider(ImageProvider):
    """Generates images via AUTOMATIC1111's Stable Diffusion WebUI API."""

    TXT2IMG_KEYS = {
        "negative_prompt",
        "steps",
        "width",
        "height",
        "cfg_scale",
        "sampler_name",
        "scheduler",
        "n_iter",
        "batch_size",
        "enable_hr",
        "hr_scale",
        "hr_upscaler",
        "hr_second_pass_steps",
        "denoising_strength",
        "refiner_checkpoint",
        "refiner_switch_at",
    }

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://127.0.0.1:7860").rstrip("/")
        self.default_params = {
            "default_prompt": config.get("default_prompt", ""),
            "negative_prompt": config.get(
                "default_negative_prompt", config.get("negative_prompt", "")
            ),
            "steps": config.get("steps", 20),
            "width": config.get("width", 512),
            "height": config.get("height", 512),
            "cfg_scale": config.get("cfg_scale", 7.0),
            "sampler_name": config.get("sampler_name", "DPM++ 2M"),
            "scheduler": config.get("scheduler", "Automatic"),
            "n_iter": config.get("n_iter", 1),
            "batch_size": config.get("batch_size", 1),
            "enable_hr": config.get("enable_hr", False),
            "hr_scale": config.get("hr_scale", 2.0),
            "hr_upscaler": config.get("hr_upscaler", "Latent"),
            "hr_second_pass_steps": config.get("hr_second_pass_steps", 0),
            "denoising_strength": config.get("denoising_strength", 0.7),
            "enable_refiner": config.get("enable_refiner", False),
            "refiner_checkpoint": config.get("refiner_checkpoint", ""),
            "refiner_switch_at": config.get("refiner_switch_at", 0.8),
        }
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    @staticmethod
    def _keep_payload_value(key: str, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and value.strip() == "":
            return False
        if key == "scheduler" and value == "Automatic":
            return False
        return True

    async def generate(self, prompt: str, **kwargs) -> bytes:
        # Merge default prompt into positive prompt if not overridden.
        default_prompt = kwargs.pop(
            "default_prompt", self.default_params.get("default_prompt", "")
        )
        if default_prompt and default_prompt not in prompt:
            prompt = f"{default_prompt}, {prompt}"

        params = {**self.default_params, "prompt": prompt}
        params.update(kwargs)

        enable_refiner = bool(params.pop("enable_refiner", False))
        if not enable_refiner:
            params.pop("refiner_checkpoint", None)
            params.pop("refiner_switch_at", None)

        payload = {"prompt": params["prompt"]}
        for key in self.TXT2IMG_KEYS:
            value = params.get(key)
            if self._keep_payload_value(key, value):
                payload[key] = value

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
            raise TimeoutError(
                "Image generation timed out after 120s. Try reducing steps or resolution."
            )

    async def close(self):
        await self.client.aclose()
