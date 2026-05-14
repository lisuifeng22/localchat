"""Configuration management for the AI chat client."""

from __future__ import annotations

import copy
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
GENERATED_DIR = CONFIG_DIR / "generated"

DEFAULT_CONFIG = {
    "provider": "openai",
    "openai": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "anthropic": {
        "api_key": "",
        "model": "claude-sonnet-4-6",
    },
    "ui": {
        "theme": "dracula",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "image": {
        "provider": "sd_webui",
        "sd_webui": {
            "base_url": "http://127.0.0.1:7860",
            "default_prompt": "masterpiece, best quality, highly detailed",
            "default_negative_prompt": "nsfw, low quality, distorted, deformed, blurry, bad anatomy",
            "negative_prompt": "",
            "steps": 20,
            "width": 512,
            "height": 512,
            "cfg_scale": 7.0,
                "sampler_name": "DPM++ 2M",
                "scheduler": "Automatic",
                "batch_size": 1,
                "n_iter": 1,
                "enable_hr": False,
                "hr_scale": 2.0,
                "hr_upscaler": "Latent",
                "hr_second_pass_steps": 0,
                "denoising_strength": 0.7,
                "refiner_checkpoint": "",
                "refiner_switch_at": 0.8,
        },
    },
    "voice": {
        "tts_provider": "local",
        "stt_provider": "local",
        "volcengine": {
            "api_key": "",
            "resource_id": "auto",
            "audio_format": "mp3",
            "sample_rate": 24000,
            "voice_type": "zh_female_vv_uranus_bigtts",
            "model": "",
        },
    },
}


class Config:
    CONFIG_DIR = CONFIG_DIR

    def __init__(self):
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    saved = json.load(f)
                self._merge(self.data, saved)
            except (json.JSONDecodeError, OSError):
                pass
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _merge(base: dict, update: dict):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Config._merge(base[key], value)
            else:
                base[key] = value

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_provider_config(self) -> dict:
        provider = self.data.get("provider", "openai")
        return self.data.setdefault(provider, {})

    @property
    def provider(self) -> str:
        return self.data.get("provider", "openai")

    @provider.setter
    def provider(self, value: str):
        self.data["provider"] = value
        self.save()

    def get_image_provider_config(self) -> dict:
        image_cfg = self.data.get("image", {})
        provider_name = image_cfg.get("provider", "sd_webui")
        return image_cfg.get(provider_name, {})

    @property
    def image_default_prompt(self) -> str:
        return self.get_image_provider_config().get("default_prompt", "")

    @property
    def image_default_negative_prompt(self) -> str:
        return self.get_image_provider_config().get("default_negative_prompt", "")

    @property
    def image_provider(self) -> str:
        return self.data.get("image", {}).get("provider", "sd_webui")

    def get_voice_config(self) -> dict:
        return self.data.setdefault("voice", copy.deepcopy(DEFAULT_CONFIG["voice"]))

    @property
    def voice_tts_provider(self) -> str:
        return self.get_voice_config().get("tts_provider", "local")

    @voice_tts_provider.setter
    def voice_tts_provider(self, value: str):
        self.get_voice_config()["tts_provider"] = value
        self.save()

    @property
    def voice_stt_provider(self) -> str:
        return self.get_voice_config().get("stt_provider", "local")

    @voice_stt_provider.setter
    def voice_stt_provider(self, value: str):
        self.get_voice_config()["stt_provider"] = value
        self.save()

    @property
    def volcengine_config(self) -> dict:
        return self.get_voice_config().setdefault("volcengine", copy.deepcopy(DEFAULT_CONFIG["voice"]["volcengine"]))

    @property
    def theme(self) -> str:
        return self.data.get("ui", {}).get("theme", "dracula")

    @property
    def temperature(self) -> float:
        return self.data.get("ui", {}).get("temperature", 0.7)

    @property
    def max_tokens(self) -> int:
        return self.data.get("ui", {}).get("max_tokens", 4096)
