from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()


def backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + ".sd-settings-v6.bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件: {path}")


def insert_once(text: str, marker: str, insert: str, before: bool = True) -> str:
    if insert.strip() in text:
        return text
    if marker not in text:
        raise RuntimeError(f"找不到插入位置: {marker[:80]}")
    return text.replace(marker, insert + marker if before else marker + insert, 1)


def patch_config_py() -> None:
    path = ROOT / "config.py"
    require(path)
    backup(path)
    text = read(path)

    if '"sampler_name"' not in text:
        text = text.replace(
            '"cfg_scale": 7.0,',
            '"cfg_scale": 7.0,\n                "sampler_name": "DPM++ 2M",\n                "scheduler": "Automatic",\n                "batch_size": 1,\n                "n_iter": 1,\n                "enable_hr": False,\n                "hr_scale": 2.0,\n                "hr_upscaler": "Latent",\n                "hr_second_pass_steps": 0,\n                "denoising_strength": 0.7,\n                "refiner_checkpoint": "",\n                "refiner_switch_at": 0.8,',
            1,
        )
    write(path, text)


def patch_config_example() -> None:
    path = ROOT / "config.example.json"
    if not path.exists():
        return
    backup(path)
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError:
        return

    sd = data.setdefault("image", {}).setdefault("sd_webui", {})
    sd.setdefault("base_url", "http://127.0.0.1:7860")
    sd.setdefault("default_prompt", "masterpiece, best quality, highly detailed")
    sd.setdefault("default_negative_prompt", "nsfw, low quality, distorted, deformed, blurry, bad anatomy")
    sd.setdefault("negative_prompt", "")
    sd.setdefault("steps", 9)
    sd.setdefault("width", 720)
    sd.setdefault("height", 1280)
    sd.setdefault("cfg_scale", 7.0)
    sd.setdefault("sampler_name", "DPM++ 2M")
    sd.setdefault("scheduler", "Automatic")
    sd.setdefault("batch_size", 1)
    sd.setdefault("n_iter", 1)
    sd.setdefault("enable_hr", False)
    sd.setdefault("hr_scale", 2.0)
    sd.setdefault("hr_upscaler", "Latent")
    sd.setdefault("hr_second_pass_steps", 0)
    sd.setdefault("denoising_strength", 0.7)
    sd.setdefault("refiner_checkpoint", "")
    sd.setdefault("refiner_switch_at", 0.8)

    write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def patch_image_provider() -> None:
    path = ROOT / "providers" / "image.py"
    require(path)
    backup(path)
    text = read(path)

    if '"sampler_name"' not in text:
        text = text.replace(
            '"cfg_scale": config.get("cfg_scale", 7.0),',
            '"cfg_scale": config.get("cfg_scale", 7.0),\n            "sampler_name": config.get("sampler_name", "DPM++ 2M"),\n            "scheduler": config.get("scheduler", "Automatic"),\n            "batch_size": config.get("batch_size", 1),\n            "n_iter": config.get("n_iter", 1),\n            "enable_hr": config.get("enable_hr", False),\n            "hr_scale": config.get("hr_scale", 2.0),\n            "hr_upscaler": config.get("hr_upscaler", "Latent"),\n            "hr_second_pass_steps": config.get("hr_second_pass_steps", 0),\n            "denoising_strength": config.get("denoising_strength", 0.7),\n            "refiner_checkpoint": config.get("refiner_checkpoint", ""),\n            "refiner_switch_at": config.get("refiner_switch_at", 0.8),',
            1,
        )

    if '"sampler_name": params.get("sampler_name"' not in text:
        payload_pattern = re.compile(
            r'payload\s*=\s*\{\s*'
            r'"prompt"\s*:\s*params\["prompt"\]\s*,\s*'
            r'"negative_prompt"\s*:\s*params\["negative_prompt"\]\s*,\s*'
            r'"steps"\s*:\s*params\["steps"\]\s*,\s*'
            r'"width"\s*:\s*params\["width"\]\s*,\s*'
            r'"height"\s*:\s*params\["height"\]\s*,\s*'
            r'"cfg_scale"\s*:\s*params\["cfg_scale"\]\s*,?\s*\}',
            re.S,
        )
        replacement = '''payload = {
            "prompt": params["prompt"],
            "negative_prompt": params["negative_prompt"],
            "steps": params["steps"],
            "width": params["width"],
            "height": params["height"],
            "cfg_scale": params["cfg_scale"],
            "sampler_name": params.get("sampler_name", "DPM++ 2M"),
            "scheduler": params.get("scheduler", "Automatic"),
            "batch_size": params.get("batch_size", 1),
            "n_iter": params.get("n_iter", 1),
            "enable_hr": params.get("enable_hr", False),
            "hr_scale": params.get("hr_scale", 2.0),
            "hr_upscaler": params.get("hr_upscaler", "Latent"),
            "hr_second_pass_steps": params.get("hr_second_pass_steps", 0),
            "denoising_strength": params.get("denoising_strength", 0.7),
        }

        refiner_checkpoint = params.get("refiner_checkpoint", "")
        if refiner_checkpoint:
            payload["refiner_checkpoint"] = refiner_checkpoint
            payload["refiner_switch_at"] = params.get("refiner_switch_at", 0.8)'''
        text, n = payload_pattern.subn(replacement, text, count=1)
        if n == 0:
            raise RuntimeError("providers/image.py 里没有找到 txt2img payload 代码块，未修改。")

    write(path, text)


def patch_server_py() -> None:
    path = ROOT / "web" / "server.py"
    require(path)
    backup(path)
    text = read(path)

    if "sampler_name: Optional[str]" not in text:
        pattern = re.compile(
            r'class DrawRequest\(BaseModel\):\s*'
            r'prompt: str\s*'
            r'negative_prompt: Optional\[str\] = None\s*'
            r'width: Optional\[int\] = None\s*'
            r'height: Optional\[int\] = None\s*'
            r'steps: Optional\[int\] = None\s*'
            r'cfg_scale: Optional\[float\] = None',
            re.S,
        )
        replacement = '''class DrawRequest(BaseModel):
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
    hr_scale: Optional[float] = None
    hr_upscaler: Optional[str] = None
    hr_second_pass_steps: Optional[int] = None
    denoising_strength: Optional[float] = None
    refiner_checkpoint: Optional[str] = None
    refiner_switch_at: Optional[float] = None'''
        text, n = pattern.subn(replacement, text, count=1)
        if n == 0:
            raise RuntimeError("web/server.py 里没有找到 DrawRequest，未修改。")

    if "sd_sampler_name: Optional[str]" not in text:
        text = text.replace(
            "default_negative_prompt: Optional[str] = None",
            '''default_negative_prompt: Optional[str] = None
    sd_sampler_name: Optional[str] = None
    sd_scheduler: Optional[str] = None
    sd_steps: Optional[int] = None
    sd_width: Optional[int] = None
    sd_height: Optional[int] = None
    sd_cfg_scale: Optional[float] = None
    sd_batch_size: Optional[int] = None
    sd_n_iter: Optional[int] = None
    sd_enable_hr: Optional[bool] = None
    sd_hr_scale: Optional[float] = None
    sd_hr_upscaler: Optional[str] = None
    sd_hr_second_pass_steps: Optional[int] = None
    sd_denoising_strength: Optional[float] = None
    sd_refiner_checkpoint: Optional[str] = None
    sd_refiner_switch_at: Optional[float] = None''',
            1,
        )

    if "img_cfg = config.get_image_provider_config()" not in text:
        text = text.replace(
            "vol = config.volcengine_config",
            "vol = config.volcengine_config\n    img_cfg = config.get_image_provider_config()",
            1,
        )

    if '"image": {' not in text:
        text = text.replace(
            '"default_negative_prompt": config.image_default_negative_prompt,',
            '''"default_negative_prompt": config.image_default_negative_prompt,
        "image": {
            "base_url": img_cfg.get("base_url", "http://127.0.0.1:7860"),
            "default_prompt": img_cfg.get("default_prompt", ""),
            "default_negative_prompt": img_cfg.get("default_negative_prompt", ""),
            "sampler_name": img_cfg.get("sampler_name", "DPM++ 2M"),
            "scheduler": img_cfg.get("scheduler", "Automatic"),
            "steps": img_cfg.get("steps", 9),
            "width": img_cfg.get("width", 720),
            "height": img_cfg.get("height", 1280),
            "cfg_scale": img_cfg.get("cfg_scale", 7.0),
            "batch_size": img_cfg.get("batch_size", 1),
            "n_iter": img_cfg.get("n_iter", 1),
            "enable_hr": img_cfg.get("enable_hr", False),
            "hr_scale": img_cfg.get("hr_scale", 2.0),
            "hr_upscaler": img_cfg.get("hr_upscaler", "Latent"),
            "hr_second_pass_steps": img_cfg.get("hr_second_pass_steps", 0),
            "denoising_strength": img_cfg.get("denoising_strength", 0.7),
            "refiner_checkpoint": img_cfg.get("refiner_checkpoint", ""),
            "refiner_switch_at": img_cfg.get("refiner_switch_at", 0.8),
        },''',
            1,
        )

    if "sd_sampler_name" in text and 'image_cfg["sampler_name"]' not in text:
        marker = 'if update.default_negative_prompt is not None:\n        config.data.setdefault("image", {}).setdefault("sd_webui", {})["default_negative_prompt"] = update.default_negative_prompt'
        if marker not in text:
            # tolerate compressed/odd spacing
            marker_pattern = re.compile(
                r'if update\.default_negative_prompt is not None:\s*'
                r'config\.data\.setdefault\("image", \{\}\)\.setdefault\("sd_webui", \{\}\)\["default_negative_prompt"\] = update\.default_negative_prompt',
                re.S,
            )
            block = '''if update.default_negative_prompt is not None:
        config.data.setdefault("image", {}).setdefault("sd_webui", {})["default_negative_prompt"] = update.default_negative_prompt'''
            text, n = marker_pattern.subn(block, text, count=1)
            if n == 0:
                raise RuntimeError("web/server.py 里没有找到 default_negative_prompt 保存逻辑，未修改。")
            marker = block

        image_save_block = '''

    image_cfg = config.data.setdefault("image", {}).setdefault("sd_webui", {})
    if update.sd_sampler_name is not None:
        image_cfg["sampler_name"] = update.sd_sampler_name
    if update.sd_scheduler is not None:
        image_cfg["scheduler"] = update.sd_scheduler
    if update.sd_steps is not None:
        image_cfg["steps"] = update.sd_steps
    if update.sd_width is not None:
        image_cfg["width"] = update.sd_width
    if update.sd_height is not None:
        image_cfg["height"] = update.sd_height
    if update.sd_cfg_scale is not None:
        image_cfg["cfg_scale"] = update.sd_cfg_scale
    if update.sd_batch_size is not None:
        image_cfg["batch_size"] = update.sd_batch_size
    if update.sd_n_iter is not None:
        image_cfg["n_iter"] = update.sd_n_iter
    if update.sd_enable_hr is not None:
        image_cfg["enable_hr"] = update.sd_enable_hr
    if update.sd_hr_scale is not None:
        image_cfg["hr_scale"] = update.sd_hr_scale
    if update.sd_hr_upscaler is not None:
        image_cfg["hr_upscaler"] = update.sd_hr_upscaler
    if update.sd_hr_second_pass_steps is not None:
        image_cfg["hr_second_pass_steps"] = update.sd_hr_second_pass_steps
    if update.sd_denoising_strength is not None:
        image_cfg["denoising_strength"] = update.sd_denoising_strength
    if update.sd_refiner_checkpoint is not None:
        image_cfg["refiner_checkpoint"] = update.sd_refiner_checkpoint
    if update.sd_refiner_switch_at is not None:
        image_cfg["refiner_switch_at"] = update.sd_refiner_switch_at'''
        text = text.replace(marker, marker + image_save_block, 1)

    if "global provider, image_provider, audio_processor" not in text:
        text = text.replace("global provider, audio_processor", "global provider, image_provider, audio_processor", 1)
        text = text.replace("provider = None\n    get_provider()", "provider = None\n    image_provider = None\n    get_provider()", 1)

    if "body.sampler_name is not None" not in text:
        add_after = '''if body.cfg_scale is not None:
        kwargs["cfg_scale"] = body.cfg_scale'''
        block = '''if body.cfg_scale is not None:
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
    if body.hr_scale is not None:
        kwargs["hr_scale"] = body.hr_scale
    if body.hr_upscaler is not None:
        kwargs["hr_upscaler"] = body.hr_upscaler
    if body.hr_second_pass_steps is not None:
        kwargs["hr_second_pass_steps"] = body.hr_second_pass_steps
    if body.denoising_strength is not None:
        kwargs["denoising_strength"] = body.denoising_strength
    if body.refiner_checkpoint is not None:
        kwargs["refiner_checkpoint"] = body.refiner_checkpoint
    if body.refiner_switch_at is not None:
        kwargs["refiner_switch_at"] = body.refiner_switch_at'''
        if add_after in text:
            text = text.replace(add_after, block, 1)
        else:
            pattern = re.compile(r'if body\.cfg_scale is not None:\s*kwargs\["cfg_scale"\] = body\.cfg_scale', re.S)
            text, n = pattern.subn(block, text, count=1)
            if n == 0:
                raise RuntimeError("web/server.py 里没有找到 /api/draw 参数转发代码，未修改。")

    write(path, text)


SD_SETTINGS_HTML = r'''

  <div id="sdTxt2ImgSettings" style="margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:8px;background:rgba(255,255,255,.02)">
    <h3 style="font-size:14px;color:var(--text);margin:0 0 10px 0">文生图参数</h3>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div>
        <label>采样方法 (Sampler)</label>
        <select id="inputSdSamplerName">
          <option value="DPM++ 2M">DPM++ 2M</option>
          <option value="DPM++ SDE">DPM++ SDE</option>
          <option value="DPM++ 2M SDE">DPM++ 2M SDE</option>
          <option value="Euler">Euler</option>
          <option value="Euler a">Euler a</option>
          <option value="DDIM">DDIM</option>
          <option value="UniPC">UniPC</option>
        </select>
      </div>
      <div>
        <label>调度类型 (Schedule type)</label>
        <select id="inputSdScheduler">
          <option value="Automatic">Automatic</option>
          <option value="Karras">Karras</option>
          <option value="Exponential">Exponential</option>
          <option value="Polyexponential">Polyexponential</option>
          <option value="SGM Uniform">SGM Uniform</option>
          <option value="Simple">Simple</option>
          <option value="Normal">Normal</option>
          <option value="DDIM">DDIM</option>
        </select>
      </div>
    </div>

    <label>迭代步数 (Steps)</label>
    <input type="number" id="inputSdSteps" min="1" max="150" step="1" placeholder="9">

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px">
      <label style="display:flex;align-items:center;gap:8px;margin:0">
        <input type="checkbox" id="inputSdHiresFix" style="width:auto"> 高分辨率修复 (Hires. fix)
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:0">
        <input type="checkbox" id="inputSdRefiner" style="width:auto"> Refiner
      </label>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">
      <div>
        <label>宽度</label>
        <input type="number" id="inputSdWidth" min="64" max="4096" step="8" placeholder="720">
      </div>
      <div>
        <label>高度</label>
        <input type="number" id="inputSdHeight" min="64" max="4096" step="8" placeholder="1280">
      </div>
      <div>
        <label>总批次数</label>
        <input type="number" id="inputSdBatchCount" min="1" max="20" step="1" placeholder="1">
      </div>
      <div>
        <label>单批数量</label>
        <input type="number" id="inputSdBatchSize" min="1" max="8" step="1" placeholder="1">
      </div>
    </div>

    <label>提示词引导系数 (CFG Scale)</label>
    <input type="number" id="inputSdCfgScale" min="1" max="30" step="0.5" placeholder="7">

    <details style="margin-top:10px;color:var(--text-dim);font-size:12px">
      <summary style="cursor:pointer;color:var(--text)">高级参数</summary>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px">
        <div>
          <label>Hires 放大倍数</label>
          <input type="number" id="inputSdHrScale" min="1" max="4" step="0.1" placeholder="2">
        </div>
        <div>
          <label>Hires Upscaler</label>
          <input type="text" id="inputSdHrUpscaler" placeholder="Latent">
        </div>
        <div>
          <label>Hires 二次步数</label>
          <input type="number" id="inputSdHrSecondPassSteps" min="0" max="150" step="1" placeholder="0">
        </div>
        <div>
          <label>重绘幅度</label>
          <input type="number" id="inputSdDenoisingStrength" min="0" max="1" step="0.05" placeholder="0.7">
        </div>
        <div>
          <label>Refiner 模型名</label>
          <input type="text" id="inputSdRefinerCheckpoint" placeholder="留空则不启用 Refiner 模型">
        </div>
        <div>
          <label>Refiner 切换点</label>
          <input type="number" id="inputSdRefinerSwitchAt" min="0" max="1" step="0.05" placeholder="0.8">
        </div>
      </div>
    </details>
  </div>
'''

SETTINGS_JS = r'''

// ── Settings Modal ─────────────────────────────────────────────────────────
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('show');
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('show');
}

function setValue(id, value, fallback = '') {
  const el = document.getElementById(id);
  if (!el) return;
  el.value = (value === undefined || value === null) ? fallback : value;
}

function setChecked(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.checked = !!value;
}

function getValue(id, fallback = '') {
  const el = document.getElementById(id);
  if (!el) return fallback;
  return el.value;
}

function getNumber(id, fallback = null) {
  const el = document.getElementById(id);
  if (!el || el.value === '') return fallback;
  const n = Number(el.value);
  return Number.isFinite(n) ? n : fallback;
}

function getChecked(id) {
  const el = document.getElementById(id);
  return !!(el && el.checked);
}

function onProviderChange() {
  const provider = getValue('selProvider', 'openai');
  const openai = document.getElementById('openaiSettings');
  const anthropic = document.getElementById('anthropicSettings');
  if (openai) openai.style.display = provider === 'openai' ? 'block' : 'none';
  if (anthropic) anthropic.style.display = provider === 'anthropic' ? 'block' : 'none';
}

function onTtsProviderChange() {
  const provider = getValue('selTtsProvider', 'local');
  const panel = document.getElementById('volcengineSettings');
  if (panel) panel.style.display = provider === 'volcengine' ? 'block' : 'none';
}

async function showSettings() {
  try {
    const cfg = await api('GET', '/api/config');
    const openai = cfg.openai || {};
    const anthropic = cfg.anthropic || {};
    const voice = cfg.voice || {};
    const volc = voice.volcengine || {};
    const image = cfg.image || {};

    setValue('selProvider', cfg.provider || 'openai');
    setValue('inputKey', openai.api_key || '');
    setValue('inputEndpoint', openai.base_url || '');
    setValue('inputModel', openai.model || '');
    setValue('inputAnthropicKey', anthropic.api_key || '');
    setValue('inputAnthropicModel', anthropic.model || '');
    setValue('inputTemp', cfg.temperature ?? 0.7);
    setValue('inputDefaultPrompt', cfg.default_prompt || image.default_prompt || '');
    setValue('inputDefaultNegPrompt', cfg.default_negative_prompt || image.default_negative_prompt || '');

    setValue('inputSdSamplerName', image.sampler_name || 'DPM++ 2M');
    setValue('inputSdScheduler', image.scheduler || 'Automatic');
    setValue('inputSdSteps', image.steps ?? 9);
    setValue('inputSdWidth', image.width ?? 720);
    setValue('inputSdHeight', image.height ?? 1280);
    setValue('inputSdBatchCount', image.n_iter ?? 1);
    setValue('inputSdBatchSize', image.batch_size ?? 1);
    setValue('inputSdCfgScale', image.cfg_scale ?? 7);
    setChecked('inputSdHiresFix', image.enable_hr || false);
    setValue('inputSdHrScale', image.hr_scale ?? 2);
    setValue('inputSdHrUpscaler', image.hr_upscaler || 'Latent');
    setValue('inputSdHrSecondPassSteps', image.hr_second_pass_steps ?? 0);
    setValue('inputSdDenoisingStrength', image.denoising_strength ?? 0.7);
    setValue('inputSdRefinerCheckpoint', image.refiner_checkpoint || '');
    setChecked('inputSdRefiner', !!image.refiner_checkpoint);
    setValue('inputSdRefinerSwitchAt', image.refiner_switch_at ?? 0.8);

    setValue('selTtsProvider', voice.tts_provider || 'local');
    setValue('selSttProvider', voice.stt_provider || 'local');
    setValue('inputVolcApiKey', volc.api_key || '');
    setValue('inputVolcResourceId', volc.resource_id || 'auto');
    setValue('inputVolcVoiceType', volc.voice_type || 'zh_female_vv_uranus_bigtts');

    onProviderChange();
    onTtsProviderChange();
    openModal('settingsModal');
  } catch (e) {
    alert('读取设置失败：' + e.message);
  }
}

async function saveSettings() {
  const refinerEnabled = getChecked('inputSdRefiner');
  const refinerCheckpoint = refinerEnabled ? getValue('inputSdRefinerCheckpoint', '').trim() : '';

  const body = {
    provider: getValue('selProvider', 'openai'),
    api_key: getValue('selProvider', 'openai') === 'anthropic' ? getValue('inputAnthropicKey') : getValue('inputKey'),
    base_url: getValue('inputEndpoint'),
    model: getValue('selProvider', 'openai') === 'anthropic' ? getValue('inputAnthropicModel') : getValue('inputModel'),
    temperature: getNumber('inputTemp', 0.7),
    default_prompt: getValue('inputDefaultPrompt'),
    default_negative_prompt: getValue('inputDefaultNegPrompt'),

    sd_sampler_name: getValue('inputSdSamplerName', 'DPM++ 2M'),
    sd_scheduler: getValue('inputSdScheduler', 'Automatic'),
    sd_steps: getNumber('inputSdSteps', 9),
    sd_width: getNumber('inputSdWidth', 720),
    sd_height: getNumber('inputSdHeight', 1280),
    sd_cfg_scale: getNumber('inputSdCfgScale', 7),
    sd_batch_size: getNumber('inputSdBatchSize', 1),
    sd_n_iter: getNumber('inputSdBatchCount', 1),
    sd_enable_hr: getChecked('inputSdHiresFix'),
    sd_hr_scale: getNumber('inputSdHrScale', 2),
    sd_hr_upscaler: getValue('inputSdHrUpscaler', 'Latent'),
    sd_hr_second_pass_steps: getNumber('inputSdHrSecondPassSteps', 0),
    sd_denoising_strength: getNumber('inputSdDenoisingStrength', 0.7),
    sd_refiner_checkpoint: refinerCheckpoint,
    sd_refiner_switch_at: getNumber('inputSdRefinerSwitchAt', 0.8),

    tts_provider: getValue('selTtsProvider', 'local'),
    stt_provider: getValue('selSttProvider', 'local'),
    volcengine_api_key: getValue('inputVolcApiKey'),
    volcengine_resource_id: getValue('inputVolcResourceId', 'auto'),
    volcengine_voice_type: getValue('inputVolcVoiceType', 'zh_female_vv_uranus_bigtts'),
    volcengine_audio_format: 'mp3',
    volcengine_model: '',
  };

  try {
    await api('POST', '/api/config', body);
    closeModal('settingsModal');
    await loadStatus();
    alert('设置已保存');
  } catch (e) {
    alert('保存设置失败：' + e.message);
  }
}
'''

DRAW_JS = r'''

async function drawImage() {
  const input = document.getElementById('chatInput');
  const prompt = input.value.trim();
  if (!prompt || streaming) return;

  input.value = '';
  input.style.height = 'auto';
  appendMessage('user', `/draw ${prompt}`, false);
  appendMessage('assistant', '正在生成图片...', true);

  const drawBtn = document.getElementById('drawBtn');
  drawBtn.disabled = true;
  streaming = true;

  try {
    const result = await api('POST', '/api/draw', { prompt });
    let content = `![Generated Image](${result.url})\n\n**Prompt:** ${result.prompt || prompt}`;
    if (result.enhanced_prompt && result.enhanced_prompt !== result.prompt) {
      content += `\n\n> ✨ ${result.enhanced_prompt}`;
    }
    appendMessage('assistant', content, true);
    finalizeStreaming();
  } catch (e) {
    appendMessage('assistant', '生图失败：' + e.message, true);
    finalizeStreaming();
  } finally {
    streaming = false;
    drawBtn.disabled = false;
    await loadSessions();
    await loadStatus();
  }
}
'''


def _insert_sd_panel_before_voice_settings(text: str) -> str:
    """Insert SD panel before the Voice Settings block using tolerant anchors."""
    if "sdTxt2ImgSettings" in text:
        return text

    # Preferred: insert before the whole voice settings separator/heading block.
    voice_idx = text.find("语音设置")
    if voice_idx != -1:
        heading_candidates = [
            text.rfind("<h2", 0, voice_idx),
            text.rfind("<h3", 0, voice_idx),
            text.rfind("<h4", 0, voice_idx),
            text.rfind("<div", 0, voice_idx),
        ]
        heading_start = max(heading_candidates)
        insert_at = heading_start if heading_start != -1 else voice_idx

        # If there is an <hr> immediately before the voice heading, insert before it.
        hr_start = text.rfind("<hr", 0, insert_at)
        if hr_start != -1 and insert_at - hr_start < 500:
            insert_at = hr_start

        return text[:insert_at] + SD_SETTINGS_HTML + "\n" + text[insert_at:]

    # Fallback: insert after the negative prompt input/textarea.
    neg_id = text.find('id="inputDefaultNegPrompt"')
    if neg_id == -1:
        neg_id = text.find("id='inputDefaultNegPrompt'")
    if neg_id != -1:
        textarea_end = text.find("</textarea>", neg_id)
        if textarea_end != -1:
            insert_at = textarea_end + len("</textarea>")
            return text[:insert_at] + SD_SETTINGS_HTML + "\n" + text[insert_at:]

        tag_end = text.find(">", neg_id)
        if tag_end != -1:
            # Insert after the containing row/div when possible.
            div_end = text.find("</div>", tag_end)
            insert_at = (div_end + len("</div>")) if div_end != -1 and div_end - tag_end < 1500 else tag_end + 1
            return text[:insert_at] + SD_SETTINGS_HTML + "\n" + text[insert_at:]

    # Fallback: insert before common voice setting field ids.
    for anchor in ['id="selTtsProvider"', "id='selTtsProvider'", 'id="volcengineSettings"', "id='volcengineSettings'"]:
        idx = text.find(anchor)
        if idx != -1:
            insert_at = text.rfind("<div", 0, idx)
            if insert_at == -1:
                insert_at = idx
            return text[:insert_at] + SD_SETTINGS_HTML + "\n" + text[insert_at:]

    raise RuntimeError(
        "web/static/index.html 里没有找到可用插入点。请确认页面里有“语音设置”或 inputDefaultNegPrompt。"
    )


def _append_sd_settings_js_override(text: str) -> str:
    """Append JS overrides for showSettings/saveSettings after existing scripts."""
    marker = "SD_TXT2IMG_SETTINGS_PATCH_V61"
    if marker in text:
        return text

    block = f"""
\n<script>
/* {marker}: appended by patch_sd_txt2img_settings_v6_1.py */
{SETTINGS_JS}
</script>
"""

    # Most HTML files already have a main script. Put the override at the very end
    # so function declarations here replace older showSettings/saveSettings.
    body_end = text.rfind("</body>")
    if body_end != -1:
        return text[:body_end] + block + "\n" + text[body_end:]

    return text + block


def patch_index_html() -> None:
    path = ROOT / "web" / "static" / "index.html"
    require(path)
    backup(path)
    text = read(path)

    text = _insert_sd_panel_before_voice_settings(text)
    text = _append_sd_settings_js_override(text)

    # Keep the draw button working on projects where drawImage was lost.
    if "async function drawImage()" not in text:
        marker = "// ── Send Message (SSE Streaming) ──────────────────────────────────────────"
        if marker in text:
            text = insert_once(text, marker, DRAW_JS + "\n", before=True)
        else:
            script_end = text.rfind("</script>")
            if script_end != -1:
                text = text[:script_end] + DRAW_JS + "\n" + text[script_end:]

    write(path, text)

def main() -> None:
    patch_config_py()
    patch_config_example()
    patch_image_provider()
    patch_server_py()
    patch_index_html()
    print("已完成：SD 文生图参数设置面板已集成。")
    print("已备份原文件为 *.sd-settings-v6.bak")
    print("请重启：python web/server.py，然后浏览器 Ctrl+F5 强制刷新。")


if __name__ == "__main__":
    main()
