#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LocalChat v5 Stable Diffusion 参数集成脚本
#
# 用法：
# 1. 把本文件放到 localchat 项目根目录，也就是 main.py / config.py 所在目录。
# 2. 运行：python integrate_sd_txt2img_settings.py
#
# 脚本会自动：
# - 备份被修改文件为 .bak_时间戳
# - 增强 providers/image.py，接入 A1111 模型列表、VAE、Sampler、Scheduler、CLIP Skip
# - 增强 web/server.py，新增 /api/sd/meta，并让 /api/draw 支持更多 SD 参数
# - 增强 web/static/index.html，在正反提示词下面加入 SD 文生图参数设置

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def log(msg: str) -> None:
    print(f"[SD-集成] {msg}")


def fail(msg: str) -> None:
    print(f"[SD-集成][失败] {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"找不到文件：{path}")
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup(path: Path) -> None:
    bak = path.with_name(path.name + f".bak_{STAMP}")
    shutil.copy2(path, bak)
    log(f"已备份：{path.relative_to(ROOT)} -> {bak.name}")


def replace_once(text: str, pattern: str, replacement: str, name: str, flags=re.S) -> tuple[str, bool]:
    new_text, n = re.subn(pattern, replacement, text, count=1, flags=flags)
    if n == 0:
        log(f"警告：没有找到替换位置：{name}")
        return text, False
    log(f"已替换：{name}")
    return new_text, True


def insert_before_once(text: str, needle: str, insertion: str, name: str) -> tuple[str, bool]:
    idx = text.find(needle)
    if idx < 0:
        log(f"警告：没有找到插入位置：{name}")
        return text, False
    log(f"已插入：{name}")
    return text[:idx] + insertion + text[idx:], True


def patch_config_py() -> None:
    path = ROOT / "config.py"
    text = read(path)

    if '"sd_model_checkpoint"' in text and '"clip_skip"' in text:
        log("config.py 已包含 SD 扩展默认项，跳过")
        return

    backup(path)

    insert = (
        '\n                "sampler_name": "DPM++ 2M",'
        '\n                "scheduler": "Automatic",'
        '\n                "batch_size": 1,'
        '\n                "n_iter": 1,'
        '\n                "enable_hr": False,'
        '\n                "refiner_checkpoint": "",'
        '\n                "refiner_switch_at": 0.8,'
        '\n                "sd_model_checkpoint": "",'
        '\n                "sd_vae": "None",'
        '\n                "clip_skip": 1,'
    )

    text, ok = replace_once(
        text,
        r'("cfg_scale"\s*:\s*7\.0\s*,)',
        r'\1' + insert,
        "config.py / image.sd_webui 默认参数",
        flags=re.S,
    )

    if ok:
        write(path, text)
    else:
        log("警告：config.py 未能自动插入默认项；后端仍会使用运行时默认值，不影响功能")


def patch_image_provider() -> None:
    path = ROOT / "providers" / "image.py"
    backup(path)

    code = '''# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from base64 import b64decode

import httpx


class ImageProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> bytes:
        ...


class SDWebUIProvider(ImageProvider):
    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://127.0.0.1:7860").rstrip("/")
        self.default_params = {
            "default_prompt": config.get("default_prompt", ""),
            "negative_prompt": config.get("negative_prompt", ""),
            "sampler_name": config.get("sampler_name", "DPM++ 2M"),
            "scheduler": config.get("scheduler", "Automatic"),
            "steps": config.get("steps", 20),
            "width": config.get("width", 512),
            "height": config.get("height", 512),
            "cfg_scale": config.get("cfg_scale", 7.0),
            "batch_size": config.get("batch_size", 1),
            "n_iter": config.get("n_iter", 1),
            "enable_hr": config.get("enable_hr", False),
            "refiner_checkpoint": config.get("refiner_checkpoint", ""),
            "refiner_switch_at": config.get("refiner_switch_at", 0.8),
            "sd_model_checkpoint": config.get("sd_model_checkpoint", ""),
            "sd_vae": config.get("sd_vae", "None"),
            "clip_skip": config.get("clip_skip", 1),
        }
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def _get_json(self, path: str):
        resp = await self.client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def list_models(self):
        data = await self._get_json("/sdapi/v1/sd-models")
        return [
            item.get("title") or item.get("model_name")
            for item in data
            if item.get("title") or item.get("model_name")
        ]

    async def list_vaes(self):
        try:
            data = await self._get_json("/sdapi/v1/sd-vae")
            out = []
            for item in data:
                name = item.get("model_name") or item.get("name")
                if name:
                    out.append(name)
            return out or ["None"]
        except Exception:
            return ["None"]

    async def list_samplers(self):
        try:
            data = await self._get_json("/sdapi/v1/samplers")
            return [item.get("name") for item in data if item.get("name")] or ["DPM++ 2M"]
        except Exception:
            return ["DPM++ 2M"]

    async def list_schedulers(self):
        try:
            data = await self._get_json("/sdapi/v1/schedulers")
            names = [item.get("label") or item.get("name") for item in data]
            names = [x for x in names if x]
            return names or ["Automatic"]
        except Exception:
            return ["Automatic"]

    async def generate(self, prompt: str, **kwargs) -> bytes:
        default_prompt = kwargs.pop("default_prompt", self.default_params.get("default_prompt", ""))
        if default_prompt and default_prompt not in prompt:
            prompt = f"{default_prompt}, {prompt}"

        params = {**self.default_params, "prompt": prompt}
        params.update(kwargs)

        override_settings = {}

        model_name = params.get("sd_model_checkpoint") or ""
        if model_name:
            override_settings["sd_model_checkpoint"] = model_name

        vae_name = params.get("sd_vae") or ""
        if vae_name:
            override_settings["sd_vae"] = vae_name

        if params.get("clip_skip") is not None:
            override_settings["CLIP_stop_at_last_layers"] = int(params["clip_skip"])

        payload = {
            "prompt": params["prompt"],
            "negative_prompt": params["negative_prompt"],
            "sampler_name": params["sampler_name"],
            "steps": int(params["steps"]),
            "width": int(params["width"]),
            "height": int(params["height"]),
            "cfg_scale": float(params["cfg_scale"]),
            "batch_size": int(params["batch_size"]),
            "n_iter": int(params["n_iter"]),
            "enable_hr": bool(params["enable_hr"]),
            "override_settings": override_settings,
            "override_settings_restore_afterwards": True,
        }

        scheduler = params.get("scheduler")
        if scheduler and scheduler != "Automatic":
            payload["scheduler"] = scheduler

        refiner_checkpoint = params.get("refiner_checkpoint") or ""
        if refiner_checkpoint:
            payload["refiner_checkpoint"] = refiner_checkpoint
            payload["refiner_switch_at"] = float(params.get("refiner_switch_at", 0.8))

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
                f"Make sure AUTOMATIC1111 is running with --api flag."
            )
        except httpx.TimeoutException:
            raise TimeoutError("Image generation timed out after 120s. Try reducing steps or resolution.")

    async def close(self):
        await self.client.aclose()
'''
    write(path, code)
    log("已覆盖：providers/image.py")


def patch_server_py() -> None:
    path = ROOT / "web" / "server.py"
    text = read(path)
    backup(path)

    new_models = '''class DrawRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None

    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    batch_size: Optional[int] = None
    n_iter: Optional[int] = None
    enable_hr: Optional[bool] = None
    refiner_checkpoint: Optional[str] = None
    refiner_switch_at: Optional[float] = None
    sd_model_checkpoint: Optional[str] = None
    sd_vae: Optional[str] = None
    clip_skip: Optional[int] = None


class ConfigUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None

    default_prompt: Optional[str] = None
    default_negative_prompt: Optional[str] = None

    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    image_steps: Optional[int] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_cfg_scale: Optional[float] = None
    image_batch_size: Optional[int] = None
    image_n_iter: Optional[int] = None
    image_enable_hr: Optional[bool] = None
    image_refiner_checkpoint: Optional[str] = None
    image_refiner_switch_at: Optional[float] = None
    sd_model_checkpoint: Optional[str] = None
    sd_vae: Optional[str] = None
    clip_skip: Optional[int] = None

    tts_provider: Optional[str] = None
    stt_provider: Optional[str] = None
    volcengine_api_key: Optional[str] = None
    volcengine_resource_id: Optional[str] = None
    volcengine_voice_type: Optional[str] = None
    volcengine_audio_format: Optional[str] = None
    volcengine_model: Optional[str] = None


'''
    text, _ = replace_once(
        text,
        r'class DrawRequest\(BaseModel\):.*?\nclass ConfigUpdate\(BaseModel\):.*?\n(?=class SessionRename\(BaseModel\):)',
        new_models,
        "server.py / DrawRequest + ConfigUpdate",
    )

    new_get_config = '''@app.get("/api/config")
async def get_config():
    pcfg = config.get_provider_config()
    vcfg = config.get_voice_config()
    vol = config.volcengine_config
    img = config.get_image_provider_config()

    return {
        "provider": config.provider,
        "openai": {
            "api_key": mask_key(pcfg.get("api_key", "")),
            "base_url": pcfg.get("base_url", ""),
            "model": pcfg.get("model", ""),
        },
        "anthropic": {
            "api_key": mask_key(config.data.get("anthropic", {}).get("api_key", "")),
            "model": config.data.get("anthropic", {}).get("model", ""),
        },
        "temperature": config.temperature,
        "default_prompt": config.image_default_prompt,
        "default_negative_prompt": config.image_default_negative_prompt,
        "image": {
            "sampler_name": img.get("sampler_name", "DPM++ 2M"),
            "scheduler": img.get("scheduler", "Automatic"),
            "steps": img.get("steps", 20),
            "width": img.get("width", 512),
            "height": img.get("height", 512),
            "cfg_scale": img.get("cfg_scale", 7.0),
            "batch_size": img.get("batch_size", 1),
            "n_iter": img.get("n_iter", 1),
            "enable_hr": img.get("enable_hr", False),
            "refiner_checkpoint": img.get("refiner_checkpoint", ""),
            "refiner_switch_at": img.get("refiner_switch_at", 0.8),
            "sd_model_checkpoint": img.get("sd_model_checkpoint", ""),
            "sd_vae": img.get("sd_vae", "None"),
            "clip_skip": img.get("clip_skip", 1),
        },
        "voice": {
            "tts_provider": vcfg.get("tts_provider", "local"),
            "stt_provider": vcfg.get("stt_provider", "local"),
            "volcengine": {
                "api_key": mask_key(vol.get("api_key", "")),
                "resource_id": vol.get("resource_id", "auto"),
                "audio_format": vol.get("audio_format", "mp3"),
                "voice_type": vol.get("voice_type", "zh_female_vv_uranus_bigtts"),
                "model": vol.get("model", ""),
            },
        },
    }


'''
    text, _ = replace_once(
        text,
        r'@app\.get\("/api/config"\)\s*async def get_config\(\):.*?\n(?=@app\.post\("/api/config"\))',
        new_get_config,
        "server.py / get_config",
    )

    new_update_config = '''@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    if update.provider:
        config.provider = update.provider

    if update.api_key and not _is_masked(update.api_key):
        config.get_provider_config()["api_key"] = update.api_key

    if update.base_url:
        config.get_provider_config()["base_url"] = update.base_url

    if update.model:
        cfg = config.get_provider_config()
        cfg["model"] = update.model
        p = get_provider()
        if p:
            p.model = update.model

    if update.temperature is not None:
        config.data.setdefault("ui", {})["temperature"] = update.temperature

    img_cfg = config.data.setdefault("image", {}).setdefault("sd_webui", {})

    if update.default_prompt is not None:
        img_cfg["default_prompt"] = update.default_prompt
    if update.default_negative_prompt is not None:
        img_cfg["default_negative_prompt"] = update.default_negative_prompt
    if update.sampler_name is not None:
        img_cfg["sampler_name"] = update.sampler_name
    if update.scheduler is not None:
        img_cfg["scheduler"] = update.scheduler
    if update.image_steps is not None:
        img_cfg["steps"] = update.image_steps
    if update.image_width is not None:
        img_cfg["width"] = update.image_width
    if update.image_height is not None:
        img_cfg["height"] = update.image_height
    if update.image_cfg_scale is not None:
        img_cfg["cfg_scale"] = update.image_cfg_scale
    if update.image_batch_size is not None:
        img_cfg["batch_size"] = update.image_batch_size
    if update.image_n_iter is not None:
        img_cfg["n_iter"] = update.image_n_iter
    if update.image_enable_hr is not None:
        img_cfg["enable_hr"] = update.image_enable_hr
    if update.image_refiner_checkpoint is not None:
        img_cfg["refiner_checkpoint"] = update.image_refiner_checkpoint
    if update.image_refiner_switch_at is not None:
        img_cfg["refiner_switch_at"] = update.image_refiner_switch_at
    if update.sd_model_checkpoint is not None:
        img_cfg["sd_model_checkpoint"] = update.sd_model_checkpoint
    if update.sd_vae is not None:
        img_cfg["sd_vae"] = update.sd_vae
    if update.clip_skip is not None:
        img_cfg["clip_skip"] = update.clip_skip

    voice_cfg = config.data.setdefault("voice", {})
    vol_cfg = voice_cfg.setdefault("volcengine", {})

    if update.tts_provider is not None:
        voice_cfg["tts_provider"] = update.tts_provider
    if update.stt_provider is not None:
        voice_cfg["stt_provider"] = update.stt_provider
    if update.volcengine_api_key is not None and not _is_masked(update.volcengine_api_key):
        vol_cfg["api_key"] = update.volcengine_api_key
    if update.volcengine_resource_id is not None:
        vol_cfg["resource_id"] = update.volcengine_resource_id
    if update.volcengine_voice_type is not None:
        vol_cfg["voice_type"] = update.volcengine_voice_type
    if update.volcengine_audio_format is not None:
        vol_cfg["audio_format"] = update.volcengine_audio_format
    if update.volcengine_model is not None:
        vol_cfg["model"] = update.volcengine_model

    config.save()

    global provider, audio_processor, image_provider
    provider = None
    image_provider = None

    get_provider()
    get_image_provider()
    audio_processor = AudioProcessor(voice_config=config.get_voice_config())

    return {"ok": True}


'''
    text, _ = replace_once(
        text,
        r'@app\.post\("/api/config"\)\s*async def update_config\(update: ConfigUpdate\):.*?\n(?=@app\.post\("/api/restart"\))',
        new_update_config,
        "server.py / update_config",
    )

    sd_meta = '''@app.get("/api/sd/meta")
async def get_sd_meta():
    p = get_image_provider()

    try:
        models = await p.list_models()
    except Exception:
        models = []

    try:
        vaes = await p.list_vaes()
    except Exception:
        vaes = ["None"]

    try:
        samplers = await p.list_samplers()
    except Exception:
        samplers = ["DPM++ 2M"]

    try:
        schedulers = await p.list_schedulers()
    except Exception:
        schedulers = ["Automatic"]

    return {
        "models": models,
        "vaes": vaes,
        "samplers": samplers,
        "schedulers": schedulers,
    }


'''
    if '"/api/sd/meta"' not in text:
        text, _ = insert_before_once(text, '@app.get("/api/models")', sd_meta, "server.py / /api/sd/meta")
    else:
        log("server.py 已包含 /api/sd/meta，跳过插入")

    new_draw = '''@app.post("/api/draw")
async def draw_image(body: DrawRequest):
    prompt = body.prompt.strip()

    if not prompt:
        raise HTTPException(400, "Empty prompt")

    kwargs = {}

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
    if body.sampler_name is not None:
        kwargs["sampler_name"] = body.sampler_name
    if body.scheduler is not None:
        kwargs["scheduler"] = body.scheduler
    if body.batch_size is not None:
        kwargs["batch_size"] = body.batch_size
    if body.n_iter is not None:
        kwargs["n_iter"] = body.n_iter
    if body.enable_hr is not None:
        kwargs["enable_hr"] = body.enable_hr
    if body.refiner_checkpoint is not None:
        kwargs["refiner_checkpoint"] = body.refiner_checkpoint
    if body.refiner_switch_at is not None:
        kwargs["refiner_switch_at"] = body.refiner_switch_at
    if body.sd_model_checkpoint is not None:
        kwargs["sd_model_checkpoint"] = body.sd_model_checkpoint
    if body.sd_vae is not None:
        kwargs["sd_vae"] = body.sd_vae
    if body.clip_skip is not None:
        kwargs["clip_skip"] = body.clip_skip

    return await _generate_image(prompt, **kwargs)


'''
    text, _ = replace_once(
        text,
        r'@app\.post\("/api/draw"\)\s*async def draw_image\(body: DrawRequest\):.*?\n(?=# ── Voice Routes)',
        new_draw,
        "server.py / draw_image",
    )

    write(path, text)


def patch_index_html() -> None:
    path = ROOT / "web" / "static" / "index.html"
    text = read(path)
    backup(path)

    css_block = '''
/* SD txt2img settings */
.sd-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.sd-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sd-field-full {
  grid-column: 1 / -1;
}
.sd-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sd-inline input[type="checkbox"] {
  width: auto;
}
'''

    if ".sd-grid" not in text:
        text = text.replace("</style>", css_block + "\n</style>", 1)
        log("已插入：index.html / SD 样式")
    else:
        log("index.html 已包含 SD 样式，跳过")

    html_block = '''
<!-- SD_TXT2IMG_SETTINGS_START -->
<hr style="border-color:var(--border);margin:16px 0">

<h3 style="font-size:14px;color:var(--text);margin-bottom:8px">Stable Diffusion 默认参数</h3>

<div class="sd-grid">
  <div class="sd-field sd-field-full">
    <label>Stable Diffusion 模型</label>
    <select id="selSdModel"></select>
  </div>

  <div class="sd-field">
    <label>外挂 VAE 模型</label>
    <select id="selSdVae"></select>
  </div>

  <div class="sd-field">
    <label>CLIP 终止层数</label>
    <input type="number" id="inputClipSkip" min="1" max="12" step="1" value="1">
  </div>

  <div class="sd-field">
    <label>采样方法 (Sampler)</label>
    <select id="selSampler"></select>
  </div>

  <div class="sd-field">
    <label>调度类型 (Schedule type)</label>
    <select id="selScheduler"></select>
  </div>

  <div class="sd-field">
    <label>迭代步数 (Steps)</label>
    <input type="number" id="inputImageSteps" min="1" step="1" value="20">
  </div>

  <div class="sd-field">
    <label>提示词引导系数 (CFG Scale)</label>
    <input type="number" id="inputImageCfgScale" min="1" step="0.5" value="7">
  </div>

  <div class="sd-field">
    <label>宽度</label>
    <input type="number" id="inputImageWidth" min="64" step="64" value="512">
  </div>

  <div class="sd-field">
    <label>高度</label>
    <input type="number" id="inputImageHeight" min="64" step="64" value="512">
  </div>

  <div class="sd-field">
    <label>总批次数</label>
    <input type="number" id="inputImageBatchCount" min="1" step="1" value="1">
  </div>

  <div class="sd-field">
    <label>单批数量</label>
    <input type="number" id="inputImageBatchSize" min="1" step="1" value="1">
  </div>

  <div class="sd-field sd-field-full">
    <label class="sd-inline">
      <input type="checkbox" id="chkHiresFix">
      <span>高分辨率修复 (Hires. fix)</span>
    </label>
  </div>

  <div class="sd-field">
    <label>Refiner 模型（可留空）</label>
    <input type="text" id="inputRefinerCheckpoint" placeholder="例如：sd_xl_refiner_1.0.safetensors">
  </div>

  <div class="sd-field">
    <label>Refiner 切换点</label>
    <input type="number" id="inputRefinerSwitchAt" min="0" max="1" step="0.05" value="0.8">
  </div>
</div>
<!-- SD_TXT2IMG_SETTINGS_END -->
'''

    if "SD_TXT2IMG_SETTINGS_START" not in text:
        pattern = r'(<textarea[^>]+id=["\']inputDefaultNegPrompt["\'][\s\S]*?</textarea>)'
        text, ok = replace_once(
            text,
            pattern,
            r'\1' + html_block,
            "index.html / SD 设置 UI 插入到反向提示词下面",
            flags=re.S,
        )
        if not ok:
            log("警告：未找到 inputDefaultNegPrompt，无法插入 SD 设置 UI")
    else:
        log("index.html 已包含 SD 设置 UI，跳过")

    js_block = r'''
// SD_TXT2IMG_SCRIPT_START
function sdShowError(msg) {
  if (typeof showError === 'function') showError(msg);
  else alert(msg);
}

function intVal(id, fallback = null) {
  const el = document.getElementById(id);
  const v = el ? el.value : '';
  if (v === '' || v == null) return fallback;
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? fallback : n;
}

function floatVal(id, fallback = null) {
  const el = document.getElementById(id);
  const v = el ? el.value : '';
  if (v === '' || v == null) return fallback;
  const n = parseFloat(v);
  return Number.isNaN(n) ? fallback : n;
}

function setSelectOptions(id, items, selectedValue = '', prependNone = false, noneLabel = 'None') {
  const el = document.getElementById(id);
  if (!el) return;

  let list = Array.isArray(items) ? [...items] : [];

  if (prependNone && !list.includes('None')) {
    list.unshift('None');
  }

  if (selectedValue && !list.includes(selectedValue)) {
    list.unshift(selectedValue);
  }

  el.innerHTML = '';

  if (!list.length) {
    const op = document.createElement('option');
    op.value = '';
    op.textContent = '无可用数据';
    el.appendChild(op);
    return;
  }

  list.forEach(item => {
    const op = document.createElement('option');
    op.value = item;
    op.textContent = item || noneLabel;
    if (item === selectedValue) op.selected = true;
    el.appendChild(op);
  });
}

function onProviderChange() {
  const provider = document.getElementById('selProvider')?.value || 'openai';
  const openai = document.getElementById('openaiSettings');
  const anthropic = document.getElementById('anthropicSettings');
  if (openai) openai.style.display = provider === 'anthropic' ? 'none' : '';
  if (anthropic) anthropic.style.display = provider === 'anthropic' ? '' : 'none';
}

function onTtsProviderChange() {
  const provider = document.getElementById('selTtsProvider')?.value || 'local';
  const volc = document.getElementById('volcengineSettings');
  if (volc) volc.style.display = provider === 'volcengine' ? '' : 'none';
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('show');
}

async function showSettings() {
  try {
    const cfg = await api('GET', '/api/config');
    let meta = { models: [], vaes: ['None'], samplers: ['DPM++ 2M'], schedulers: ['Automatic'] };

    try {
      meta = await api('GET', '/api/sd/meta');
    } catch (e) {
      console.warn('加载 SD 元数据失败：', e);
    }

    const setVal = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value ?? '';
    };

    setVal('selProvider', cfg.provider || 'openai');
    setVal('inputKey', cfg.openai?.api_key || '');
    setVal('inputEndpoint', cfg.openai?.base_url || '');
    setVal('inputModel', cfg.openai?.model || '');
    setVal('inputAnthropicKey', cfg.anthropic?.api_key || '');
    setVal('inputAnthropicModel', cfg.anthropic?.model || '');
    setVal('inputTemp', cfg.temperature ?? 0.7);
    setVal('inputDefaultPrompt', cfg.default_prompt || '');
    setVal('inputDefaultNegPrompt', cfg.default_negative_prompt || '');

    const img = cfg.image || {};
    setSelectOptions('selSdModel', meta.models || [], img.sd_model_checkpoint || '');
    setSelectOptions('selSdVae', meta.vaes || ['None'], img.sd_vae || 'None', true);
    setSelectOptions('selSampler', meta.samplers || ['DPM++ 2M'], img.sampler_name || 'DPM++ 2M');

    const schedulers = ['Automatic', ...((meta.schedulers || []).filter(x => x && x !== 'Automatic'))];
    setSelectOptions('selScheduler', schedulers, img.scheduler || 'Automatic');

    setVal('inputClipSkip', img.clip_skip ?? 1);
    setVal('inputImageSteps', img.steps ?? 20);
    setVal('inputImageCfgScale', img.cfg_scale ?? 7);
    setVal('inputImageWidth', img.width ?? 512);
    setVal('inputImageHeight', img.height ?? 512);
    setVal('inputImageBatchCount', img.n_iter ?? 1);
    setVal('inputImageBatchSize', img.batch_size ?? 1);
    setVal('inputRefinerCheckpoint', img.refiner_checkpoint || '');
    setVal('inputRefinerSwitchAt', img.refiner_switch_at ?? 0.8);

    const hires = document.getElementById('chkHiresFix');
    if (hires) hires.checked = !!img.enable_hr;

    setVal('selTtsProvider', cfg.voice?.tts_provider || 'local');
    setVal('selSttProvider', cfg.voice?.stt_provider || 'local');
    setVal('inputVolcApiKey', cfg.voice?.volcengine?.api_key || '');
    setVal('inputVolcResourceId', cfg.voice?.volcengine?.resource_id || 'auto');
    setVal('inputVolcVoiceType', cfg.voice?.volcengine?.voice_type || 'zh_female_vv_uranus_bigtts');

    onProviderChange();
    onTtsProviderChange();

    document.getElementById('settingsModal')?.classList.add('show');
  } catch (e) {
    sdShowError(`加载设置失败：${e.message}`);
  }
}

async function saveSettings() {
  try {
    const provider = document.getElementById('selProvider')?.value || 'openai';

    const payload = {
      provider,
      temperature: floatVal('inputTemp', 0.7),
      default_prompt: document.getElementById('inputDefaultPrompt')?.value.trim() || '',
      default_negative_prompt: document.getElementById('inputDefaultNegPrompt')?.value.trim() || '',

      sampler_name: document.getElementById('selSampler')?.value || 'DPM++ 2M',
      scheduler: document.getElementById('selScheduler')?.value || 'Automatic',
      image_steps: intVal('inputImageSteps', 20),
      image_width: intVal('inputImageWidth', 512),
      image_height: intVal('inputImageHeight', 512),
      image_cfg_scale: floatVal('inputImageCfgScale', 7),
      image_batch_size: intVal('inputImageBatchSize', 1),
      image_n_iter: intVal('inputImageBatchCount', 1),
      image_enable_hr: !!document.getElementById('chkHiresFix')?.checked,
      image_refiner_checkpoint: document.getElementById('inputRefinerCheckpoint')?.value.trim() || '',
      image_refiner_switch_at: floatVal('inputRefinerSwitchAt', 0.8),
      sd_model_checkpoint: document.getElementById('selSdModel')?.value || '',
      sd_vae: document.getElementById('selSdVae')?.value || 'None',
      clip_skip: intVal('inputClipSkip', 1),

      tts_provider: document.getElementById('selTtsProvider')?.value || 'local',
      stt_provider: document.getElementById('selSttProvider')?.value || 'local',
      volcengine_api_key: document.getElementById('inputVolcApiKey')?.value || '',
      volcengine_resource_id: document.getElementById('inputVolcResourceId')?.value || '',
      volcengine_voice_type: document.getElementById('inputVolcVoiceType')?.value || '',
    };

    if (provider === 'anthropic') {
      payload.api_key = document.getElementById('inputAnthropicKey')?.value || '';
      payload.model = document.getElementById('inputAnthropicModel')?.value.trim() || '';
    } else {
      payload.api_key = document.getElementById('inputKey')?.value || '';
      payload.base_url = document.getElementById('inputEndpoint')?.value.trim() || '';
      payload.model = document.getElementById('inputModel')?.value.trim() || '';
    }

    await api('POST', '/api/config', payload);

    closeModal('settingsModal');
    if (typeof loadStatus === 'function') await loadStatus();
  } catch (e) {
    sdShowError(`保存设置失败：${e.message}`);
  }
}

async function drawImage() {
  const input = document.getElementById('chatInput');
  const drawBtn = document.getElementById('drawBtn');
  const text = input?.value.trim();

  if (!text || streaming) return;

  input.value = '';
  input.style.height = 'auto';

  appendMessage('user', `生图：${text}`, false);
  appendMessage('assistant', '正在生成图片...', true);

  streaming = true;
  if (drawBtn) drawBtn.disabled = true;

  try {
    const data = await api('POST', '/api/draw', { prompt: text });
    const imgUrl = data.url || data.image || '';
    let content = `![Generated Image](${imgUrl})\n\n**Prompt:** ${data.prompt || text}`;
    if (data.enhanced_prompt && data.enhanced_prompt !== data.prompt) {
      content += `\n\n> ✨ ${data.enhanced_prompt}`;
    }
    appendMessage('assistant', content, true);
    finalizeStreaming();
  } catch (e) {
    finalizeStreaming();
    sdShowError(e.message);
  } finally {
    streaming = false;
    if (drawBtn) drawBtn.disabled = false;
    if (typeof loadSessions === 'function') await loadSessions();
    if (typeof loadStatus === 'function') await loadStatus();
    input?.focus();
  }
}
// SD_TXT2IMG_SCRIPT_END
'''

    text = re.sub(
        r'\n?// SD_TXT2IMG_SCRIPT_START[\s\S]*?// SD_TXT2IMG_SCRIPT_END\n?',
        '\n',
        text,
        flags=re.S,
    )

    if "</script>" in text:
        text = text.replace("</script>", js_block + "\n</script>", 1)
        log("已插入：index.html / SD 脚本")
    else:
        log("警告：未找到 </script>，无法插入 SD 脚本")

    write(path, text)


def main() -> None:
    required = [
        ROOT / "config.py",
        ROOT / "providers" / "image.py",
        ROOT / "web" / "server.py",
        ROOT / "web" / "static" / "index.html",
    ]

    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        fail("请把脚本放到 localchat 项目根目录运行。缺少文件：" + ", ".join(missing))

    log(f"项目目录：{ROOT}")

    patch_config_py()
    patch_image_provider()
    patch_server_py()
    patch_index_html()

    log("全部完成。")
    log("下一步：启动 Stable Diffusion WebUI 时请带 --api，例如 webui-user.bat 里加 COMMANDLINE_ARGS=--api")
    log("然后重启 LocalChat Web 服务，打开设置查看 Stable Diffusion 参数。")


if __name__ == "__main__":
    main()
