#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v6.2 修复：让 SD WebUI 文生图参数真正生效。

用法：
    python patch_sd_txt2img_settings_v6_2.py
    python web/server.py
    浏览器 Ctrl+F5
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

SD_DEFAULTS: dict[str, Any] = {
    "sampler_name": "DPM++ 2M",
    "scheduler": "Automatic",
    "steps": 9,
    "width": 720,
    "height": 1280,
    "cfg_scale": 7.0,
    "n_iter": 1,
    "batch_size": 1,
    "enable_hr": False,
    "hr_scale": 2.0,
    "hr_upscaler": "Latent",
    "hr_second_pass_steps": 0,
    "denoising_strength": 0.7,
    "enable_refiner": False,
    "refiner_checkpoint": "",
    "refiner_switch_at": 0.8,
}


def backup(path: Path) -> None:
    if not path.exists():
        return
    bak = path.with_suffix(path.suffix + ".v6_2.bak")
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"[backup] {path} -> {bak}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"[write] {path}")


def ensure_json_config(path: Path) -> None:
    if not path.exists():
        return
    backup(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[skip] {path} 不是可解析 JSON：{e}")
        return
    sd = data.setdefault("image", {}).setdefault("sd_webui", {})
    changed = False
    for k, v in SD_DEFAULTS.items():
        if k not in sd:
            sd[k] = v
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[json] 已补齐 {path}")


def patch_config_py() -> None:
    path = ROOT / "config.py"
    if not path.exists():
        print("[skip] config.py 不存在")
        return
    text = read_text(path)
    if all(k in text for k in ("sampler_name", "enable_hr", "refiner_checkpoint")):
        print("[ok] config.py 已包含 SD 文生图参数")
        return
    backup(path)
    marker = '"cfg_scale": 7.0,'
    extra = "\n".join(
        f'                "{k}": {json.dumps(v, ensure_ascii=False)},'
        for k, v in SD_DEFAULTS.items()
        if k != "cfg_scale"
    )
    if marker in text:
        text = text.replace(marker, marker + "\n" + extra, 1)
        write_text(path, text)
        return
    print("[warn] config.py 没找到 cfg_scale 插入点，跳过默认配置补丁。")


IMAGE_PROVIDER_CODE = '''# Image generation provider — connects to Stable Diffusion WebUI (AUTOMATIC1111).

from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64decode
from typing import Any

import httpx


class ImageProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> bytes:
        pass


class SDWebUIProvider(ImageProvider):
    SD_PAYLOAD_KEYS = {
        "prompt",
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
                "negative_prompt",
                config.get("default_negative_prompt", ""),
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
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=180.0)

    @staticmethod
    def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            if key == "scheduler" and value == "Automatic":
                # 旧版 A1111 可能不支持 scheduler；Automatic 不传最稳。
                continue
            cleaned[key] = value
        return cleaned

    async def generate(self, prompt: str, **kwargs) -> bytes:
        default_prompt = kwargs.pop(
            "default_prompt",
            self.default_params.get("default_prompt", ""),
        )
        if default_prompt and default_prompt not in prompt:
            prompt = f"{default_prompt}, {prompt}"

        params = {**self.default_params, "prompt": prompt}
        params.update(kwargs)

        if not params.get("enable_refiner", False):
            params.pop("refiner_checkpoint", None)
            params.pop("refiner_switch_at", None)

        payload = {
            key: params.get(key)
            for key in self.SD_PAYLOAD_KEYS
            if key in params
        }
        payload = self._clean_payload(payload)

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
            if isinstance(raw, str) and "," in raw and raw.lstrip().startswith("data:"):
                raw = raw.split(",", 1)[1]
            return b64decode(raw)
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Stable Diffusion WebUI at {self.base_url}. "
                "Make sure AUTOMATIC1111 is running with --api flag."
            )
        except httpx.TimeoutException:
            raise TimeoutError(
                "Image generation timed out after 180s. "
                "Try reducing steps, resolution, hires.fix, or batch size."
            )
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:800] if e.response is not None else ""
            raise RuntimeError(f"SD WebUI HTTP error: {e}. {detail}")

    async def close(self):
        await self.client.aclose()
'''


def patch_image_provider() -> None:
    path = ROOT / "providers" / "image.py"
    if not path.exists():
        print("[skip] providers/image.py 不存在")
        return
    backup(path)
    write_text(path, IMAGE_PROVIDER_CODE)


SERVER_HELPER_CODE = r'''
SD_TXT2IMG_CONFIG_KEYS = (
    "sampler_name",
    "scheduler",
    "steps",
    "width",
    "height",
    "cfg_scale",
    "n_iter",
    "batch_size",
    "enable_hr",
    "hr_scale",
    "hr_upscaler",
    "hr_second_pass_steps",
    "denoising_strength",
    "enable_refiner",
    "refiner_checkpoint",
    "refiner_switch_at",
)


def _coerce_sd_config_value(key: str, value):
    if value is None:
        return None
    if key in {"steps", "width", "height", "n_iter", "batch_size", "hr_second_pass_steps"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in {"cfg_scale", "hr_scale", "denoising_strength", "refiner_switch_at"}:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if key in {"enable_hr", "enable_refiner"}:
        return bool(value)
    return value


def _sd_kwargs_from_config() -> dict:
    image_cfg = config.get_image_provider_config()
    kwargs = {}
    for key in SD_TXT2IMG_CONFIG_KEYS:
        if key not in image_cfg:
            continue
        value = _coerce_sd_config_value(key, image_cfg.get(key))
        if value is not None:
            kwargs[key] = value
    return kwargs


def _sd_kwargs_from_request(body) -> dict:
    kwargs = {}
    for key in SD_TXT2IMG_CONFIG_KEYS:
        if not hasattr(body, key):
            continue
        value = getattr(body, key)
        value = _coerce_sd_config_value(key, value)
        if value is not None:
            kwargs[key] = value
    return kwargs
'''

DRAW_REQUEST_CODE = '''class DrawRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    n_iter: Optional[int] = None
    batch_size: Optional[int] = None
    enable_hr: Optional[bool] = None
    hr_scale: Optional[float] = None
    hr_upscaler: Optional[str] = None
    hr_second_pass_steps: Optional[int] = None
    denoising_strength: Optional[float] = None
    enable_refiner: Optional[bool] = None
    refiner_checkpoint: Optional[str] = None
    refiner_switch_at: Optional[float] = None

'''

CONFIG_UPDATE_FIELDS = '''
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    sd_steps: Optional[int] = None
    sd_width: Optional[int] = None
    sd_height: Optional[int] = None
    sd_cfg_scale: Optional[float] = None
    n_iter: Optional[int] = None
    batch_size: Optional[int] = None
    enable_hr: Optional[bool] = None
    hr_scale: Optional[float] = None
    hr_upscaler: Optional[str] = None
    hr_second_pass_steps: Optional[int] = None
    denoising_strength: Optional[float] = None
    enable_refiner: Optional[bool] = None
    refiner_checkpoint: Optional[str] = None
    refiner_switch_at: Optional[float] = None
'''

DRAW_IMAGE_ROUTE_CODE = '''@app.post("/api/draw")
async def draw_image(body: DrawRequest):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Empty prompt")

    kwargs = _sd_kwargs_from_request(body)
    if body.negative_prompt is not None:
        kwargs["negative_prompt"] = body.negative_prompt
    if body.width is not None:
        kwargs["width"] = body.width
    if body.height is not None:
        kwargs["height"] = body.height
    if body.steps is not None:
        kwargs["steps"] = body.steps
    if body.cfg_scale is not None:
        kwargs["cfg_scale"] = body.cfg_scale

    return await _generate_image(prompt, **kwargs)

'''


def patch_server_py() -> None:
    path = ROOT / "web" / "server.py"
    if not path.exists():
        print("[skip] web/server.py 不存在")
        return

    text = read_text(path)
    backup(path)
    changed = False

    if "SD_TXT2IMG_CONFIG_KEYS" not in text:
        marker = 'app = FastAPI(title="Local AI Chat")'
        if marker in text:
            text = text.replace(marker, marker + "\n" + SERVER_HELPER_CODE, 1)
            changed = True
        else:
            print("[warn] server.py 未找到 app = FastAPI 插入点")

    m = re.search(r"class DrawRequest\(BaseModel\):.*?class ConfigUpdate\(BaseModel\):", text, flags=re.S)
    if m and "sampler_name" not in m.group(0):
        text = text[:m.start()] + DRAW_REQUEST_CODE + "class ConfigUpdate(BaseModel):" + text[m.end():]
        changed = True
    elif not m:
        print("[warn] server.py 未找到 DrawRequest 模型")

    m = re.search(r"class ConfigUpdate\(BaseModel\):(?P<body>.*?)class SessionRename\(BaseModel\):", text, flags=re.S)
    if m and "sd_width" not in m.group("body"):
        text = text[:m.end("body")] + CONFIG_UPDATE_FIELDS + text[m.end("body"):]
        changed = True
    elif not m:
        print("[warn] server.py 未找到 ConfigUpdate 模型")

    if '"image": config.get_image_provider_config()' not in text:
        old = '"default_negative_prompt": config.image_default_negative_prompt,'
        if old in text:
            text = text.replace(old, old + '\n        "image": config.get_image_provider_config(),', 1)
            changed = True
        else:
            print("[warn] server.py 未找到 get_config 中 default_negative_prompt 返回位置")

    if "sd_field_map" not in text:
        old_inline = ('if update.default_negative_prompt is not None: '
                      'config.data.setdefault("image", {}).setdefault("sd_webui", {})["default_negative_prompt"] = update.default_negative_prompt')
        block = r'''
    image_cfg = config.data.setdefault("image", {}).setdefault("sd_webui", {})
    sd_field_map = {
        "sampler_name": "sampler_name",
        "scheduler": "scheduler",
        "sd_steps": "steps",
        "sd_width": "width",
        "sd_height": "height",
        "sd_cfg_scale": "cfg_scale",
        "n_iter": "n_iter",
        "batch_size": "batch_size",
        "enable_hr": "enable_hr",
        "hr_scale": "hr_scale",
        "hr_upscaler": "hr_upscaler",
        "hr_second_pass_steps": "hr_second_pass_steps",
        "denoising_strength": "denoising_strength",
        "enable_refiner": "enable_refiner",
        "refiner_checkpoint": "refiner_checkpoint",
        "refiner_switch_at": "refiner_switch_at",
    }
    for update_field, config_key in sd_field_map.items():
        if hasattr(update, update_field):
            value = getattr(update, update_field)
            if value is not None:
                image_cfg[config_key] = value
'''
        if old_inline in text:
            text = text.replace(old_inline, old_inline + block, 1)
            changed = True
        else:
            pattern = r'(if update\.default_negative_prompt is not None:\s*\n\s*config\.data\.setdefault\("image", \{\}\)\.setdefault\("sd_webui", \{\}\)\["default_negative_prompt"\]\s*=\s*update\.default_negative_prompt\s*)'
            if re.search(pattern, text, flags=re.S):
                text = re.sub(pattern, r'\1' + block, text, count=1, flags=re.S)
                changed = True
            else:
                print("[warn] server.py 未找到 update_config 保存 default_negative_prompt 的位置")

    if "global provider, image_provider, audio_processor" not in text:
        text2 = text.replace("global provider, audio_processor", "global provider, image_provider, audio_processor", 1)
        if text2 != text:
            text = text2
            changed = True

    if "image_provider = None" not in text:
        old = "provider = None get_provider() audio_processor = AudioProcessor(voice_config=config.get_voice_config())"
        new = "provider = None image_provider = None get_provider() audio_processor = AudioProcessor(voice_config=config.get_voice_config())"
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        else:
            old2 = "provider = None\n    get_provider()\n    audio_processor = AudioProcessor(voice_config=config.get_voice_config())"
            new2 = "provider = None\n    image_provider = None\n    get_provider()\n    audio_processor = AudioProcessor(voice_config=config.get_voice_config())"
            if old2 in text:
                text = text.replace(old2, new2, 1)
                changed = True

    if "_sd_kwargs_from_config().items()" not in text:
        old = ('if config.image_default_negative_prompt: '
               'kwargs.setdefault("negative_prompt", config.image_default_negative_prompt) '
               'enhanced = await _enhance_prompt(prompt)')
        new = ('if config.image_default_negative_prompt: '
               'kwargs.setdefault("negative_prompt", config.image_default_negative_prompt) '
               'kwargs.update({k: v for k, v in _sd_kwargs_from_config().items() if k not in kwargs}) '
               'enhanced = await _enhance_prompt(prompt)')
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        else:
            old2 = 'enhanced = await _enhance_prompt(prompt)'
            new2 = 'kwargs.update({k: v for k, v in _sd_kwargs_from_config().items() if k not in kwargs})\n    enhanced = await _enhance_prompt(prompt)'
            if old2 in text:
                text = text.replace(old2, new2, 1)
                changed = True
            else:
                print("[warn] server.py 未找到 _generate_image 插入点")

    pattern = r'@app\.post\("/api/draw"\)\s*async def draw_image\(body: DrawRequest\):.*?# ── Voice Routes'
    if re.search(pattern, text, flags=re.S):
        text = re.sub(pattern, DRAW_IMAGE_ROUTE_CODE + "# ── Voice Routes", text, count=1, flags=re.S)
        changed = True
    else:
        print("[warn] server.py 未找到 /api/draw 路由替换位置")

    if changed:
        write_text(path, text)
    else:
        print("[ok] server.py 看起来已经打过补丁")


FRONTEND_BRIDGE = r'''
<script id="sd-txt2img-settings-bridge-v6-2">
(function () {
  const SD_FIELDS = {
    sampler_name: ["inputSdSampler", "selSdSampler", "inputSamplerName", "txt2imgSampler", "sdSampler"],
    scheduler: ["inputSdScheduler", "selSdScheduler", "inputScheduleType", "txt2imgScheduler", "sdScheduler"],
    sd_steps: ["inputSdSteps", "inputSteps", "txt2imgSteps", "sdSteps"],
    sd_width: ["inputSdWidth", "inputWidth", "txt2imgWidth", "sdWidth"],
    sd_height: ["inputSdHeight", "inputHeight", "txt2imgHeight", "sdHeight"],
    sd_cfg_scale: ["inputSdCfgScale", "inputCfgScale", "txt2imgCfgScale", "sdCfgScale"],
    n_iter: ["inputSdBatchCount", "inputBatchCount", "txt2imgBatchCount", "sdBatchCount"],
    batch_size: ["inputSdBatchSize", "inputBatchSize", "txt2imgBatchSize", "sdBatchSize"],
    enable_hr: ["chkSdHiresFix", "chkHiresFix", "txt2imgHiresFix", "sdHiresFix"],
    hr_scale: ["inputSdHrScale", "inputHrScale", "txt2imgHrScale", "sdHrScale"],
    hr_upscaler: ["inputSdHrUpscaler", "selSdHrUpscaler", "inputHrUpscaler", "sdHrUpscaler"],
    hr_second_pass_steps: ["inputSdHrSecondPassSteps", "inputHrSecondPassSteps", "sdHrSecondPassSteps"],
    denoising_strength: ["inputSdDenoisingStrength", "inputDenoisingStrength", "sdDenoisingStrength"],
    enable_refiner: ["chkSdRefiner", "chkRefiner", "txt2imgRefiner", "sdRefiner"],
    refiner_checkpoint: ["inputSdRefinerCheckpoint", "inputRefinerCheckpoint", "sdRefinerCheckpoint"],
    refiner_switch_at: ["inputSdRefinerSwitchAt", "inputRefinerSwitchAt", "sdRefinerSwitchAt"]
  };

  function findEl(ids) {
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) return el;
    }
    return null;
  }

  function readValue(name, ids) {
    const el = findEl(ids);
    if (!el) return undefined;
    if (el.type === "checkbox") return !!el.checked;
    const raw = el.value;
    if (raw === undefined || raw === null || raw === "") return undefined;
    if (["sd_steps", "sd_width", "sd_height", "n_iter", "batch_size", "hr_second_pass_steps"].includes(name)) {
      const n = parseInt(raw, 10);
      return Number.isFinite(n) ? n : undefined;
    }
    if (["sd_cfg_scale", "hr_scale", "denoising_strength", "refiner_switch_at"].includes(name)) {
      const n = parseFloat(raw);
      return Number.isFinite(n) ? n : undefined;
    }
    return raw;
  }

  function writeValue(name, ids, imageCfg) {
    const el = findEl(ids);
    if (!el || !imageCfg) return;
    const configKeyMap = {
      sd_steps: "steps",
      sd_width: "width",
      sd_height: "height",
      sd_cfg_scale: "cfg_scale"
    };
    const key = configKeyMap[name] || name;
    const value = imageCfg[key];
    if (value === undefined || value === null) return;
    if (el.type === "checkbox") {
      el.checked = !!value;
    } else {
      el.value = value;
    }
  }

  function collectSDSettings() {
    const data = {};
    for (const [name, ids] of Object.entries(SD_FIELDS)) {
      const value = readValue(name, ids);
      if (value !== undefined) data[name] = value;
    }
    return data;
  }

  async function applySDSettingsFromServer() {
    try {
      const resp = await fetch("/api/config");
      if (!resp.ok) return;
      const cfg = await resp.json();
      const imageCfg = cfg.image || {};
      for (const [name, ids] of Object.entries(SD_FIELDS)) {
        writeValue(name, ids, imageCfg);
      }
    } catch (err) {
      console.warn("[SD settings] load skipped:", err);
    }
  }

  async function postSDSettings() {
    const data = collectSDSettings();
    if (!Object.keys(data).length) return;
    try {
      const resp = await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
      });
      if (!resp.ok) console.warn("[SD settings] save failed:", await resp.text());
    } catch (err) {
      console.warn("[SD settings] save skipped:", err);
    }
  }

  const oldShowSettings = window.showSettings;
  if (typeof oldShowSettings === "function" && !oldShowSettings.__sdBridgeWrapped) {
    const wrappedShow = async function () {
      const result = await oldShowSettings.apply(this, arguments);
      await applySDSettingsFromServer();
      return result;
    };
    wrappedShow.__sdBridgeWrapped = true;
    window.showSettings = wrappedShow;
  } else {
    document.addEventListener("DOMContentLoaded", applySDSettingsFromServer);
  }

  const oldSaveSettings = window.saveSettings;
  if (typeof oldSaveSettings === "function" && !oldSaveSettings.__sdBridgeWrapped) {
    const wrappedSave = async function () {
      const result = await oldSaveSettings.apply(this, arguments);
      await postSDSettings();
      return result;
    };
    wrappedSave.__sdBridgeWrapped = true;
    window.saveSettings = wrappedSave;
  }

  window.collectSDSettingsV62 = collectSDSettings;
})();
</script>
'''


def patch_frontend_bridge() -> None:
    path = ROOT / "web" / "static" / "index.html"
    if not path.exists():
        print("[skip] web/static/index.html 不存在")
        return
    text = read_text(path)
    if "sd-txt2img-settings-bridge-v6-2" in text:
        print("[ok] 前端 bridge 已存在")
        return
    backup(path)
    if "</body>" in text:
        text = text.replace("</body>", FRONTEND_BRIDGE + "\n</body>", 1)
    else:
        text += "\n" + FRONTEND_BRIDGE + "\n"
    write_text(path, text)


def main() -> None:
    print("[v6.2] 开始修复 SD 文生图设置保存/生效链路...")
    patch_config_py()
    ensure_json_config(ROOT / "config.example.json")
    ensure_json_config(ROOT / "config.json")
    patch_image_provider()
    patch_server_py()
    patch_frontend_bridge()
    print("\n[v6.2] 完成。请重启：python web/server.py，然后浏览器 Ctrl+F5。")
    print("[v6.2] 验证：保存设置后打开 config.json，确认 image.sd_webui 下有 sampler_name/width/height 等字段。")


if __name__ == "__main__":
    main()
