"""Configuration management for the AI chat client."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
GENERATED_DIR = CONFIG_DIR / "generated"

DEFAULT_CONFIG = {
    "provider": "openai",
    "openai": {
        "api_key": "sk-b0eb079f469b4972ad6620ef64c6aad2",
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
        }
    },
    "voice": {
        "tts_provider": "local",
        "stt_provider": "local",
        "volcengine": {
            "app_id": "",
            "access_token": "",
            "api_key": "",
            "resource_id": "seed-tts-2.0",
            "audio_format": "mp3",
            "voice_type": "zh_female_cancan_mars_bigtts",
        }
    },
}


class Config:
    CONFIG_DIR = CONFIG_DIR  # expose module-level constant as class attribute

    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    saved = json.load(f)
                # deep merge
                self._merge(self.data, saved)
            except (json.JSONDecodeError, OSError):
                pass
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _merge(base, update):
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_provider_config(self):
        provider = self.data["provider"]
        return self.data.get(provider, {})

    def get_image_provider_config(self) -> dict:
        img_cfg = self.data.get("image", {})
        provider_name = img_cfg.get("provider", "sd_webui")
        return img_cfg.get(provider_name, {})

    @property
    def image_default_prompt(self) -> str:
        return self.get_image_provider_config().get("default_prompt", "")

    @property
    def image_default_negative_prompt(self) -> str:
        return self.get_image_provider_config().get("default_negative_prompt", "")

    @property
    def image_provider(self) -> str:
        return self.data.get("image", {}).get("provider", "sd_webui")

    @property
    def provider(self):
        return self.data["provider"]

    @provider.setter
    def provider(self, value):
        self.data["provider"] = value
        self.save()

    def get_voice_config(self) -> dict:
        return self.data.get("voice", {})

    @property
    def voice_tts_provider(self) -> str:
        return self.get_voice_config().get("tts_provider", "local")

    @voice_tts_provider.setter
    def voice_tts_provider(self, value: str):
        self.data.setdefault("voice", {})["tts_provider"] = value
        self.save()

    @property
    def voice_stt_provider(self) -> str:
        return self.get_voice_config().get("stt_provider", "local")

    @voice_stt_provider.setter
    def voice_stt_provider(self, value: str):
        self.data.setdefault("voice", {})["stt_provider"] = value
        self.save()

    @property
    def volcengine_config(self) -> dict:
        return self.get_voice_config().get("volcengine", {})

    @property
    def theme(self):
        return self.data.get("ui", {}).get("theme", "dracula")

    @property
    def temperature(self):
        return self.data.get("ui", {}).get("temperature", 0.7)

    @property
    def max_tokens(self):
        return self.data.get("ui", {}).get("max_tokens", 4096)
