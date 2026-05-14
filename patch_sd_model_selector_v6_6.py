from __future__ import annotations

"""
patch_sd_model_selector_v6_6.py

修复/集成 localchat 的 Stable Diffusion 模型选择功能。

解决的问题：
1. 把“Stable Diffusion 模型”放到设置页的【正反提示词】和【采样方法】之间。
2. 修复之前脚本可能把 /api/sd/models 加在 app.mount('/', StaticFiles...) 后面导致接口被前端静态页拦截的问题。
3. 后端真正读取 SD WebUI 模型列表：GET /sdapi/v1/sd-models。
4. 保存设置时真正切换 SD WebUI 当前模型：POST /sdapi/v1/options。
5. 自动备份 web/server.py 和 web/static/index.html。

用法：
    python patch_sd_model_selector_v6_6.py

前提：
    Stable Diffusion WebUI 必须用 --api 启动。
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SERVER = ROOT / "web" / "server.py"
INDEX = ROOT / "web" / "static" / "index.html"
BACKUP_SUFFIX = ".sd_model_selector_v6_6.bak"

SERVER_START = "# ── Stable Diffusion Model Selector v6.6"
SERVER_END = "# ── end Stable Diffusion Model Selector v6.6"
FRONTEND_START = "// ── Stable Diffusion model selector v6.6"
FRONTEND_END = "// ── end Stable Diffusion model selector v6.6"

OLD_SERVER_START_PATTERNS = [
    r"\n?# ── Stable Diffusion Model Selector \(added by patch_sd_model_only_v6_5\.py\)[\s\S]*?# ── end Stable Diffusion Model Selector ─+\n?",
    r"\n?# ── Stable Diffusion Model Selector[\s\S]*?# ── end Stable Diffusion Model Selector[\s\S]*?\n",
]
OLD_FRONTEND_PATTERNS = [
    r"\n?// ── Stable Diffusion model selector \(added by patch_sd_model_only_v6_5\.py\)[\s\S]*?// ── end Stable Diffusion model selector ─+\n?",
    r"\n?// ── Stable Diffusion model selector[\s\S]*?// ── end Stable Diffusion model selector[\s\S]*?\n",
]

SERVER_SNIPPET = r'''
# ── Stable Diffusion Model Selector v6.6 ────────────────────────────────────
# Added by patch_sd_model_selector_v6_6.py
try:
    import httpx as _sd_model_httpx
except Exception:
    _sd_model_httpx = None

try:
    from pydantic import BaseModel as _SDBaseModel
except Exception:
    _SDBaseModel = BaseModel

try:
    from typing import Optional as _SDOptional
except Exception:
    _SDOptional = Optional


class SDModelSettingUpdate(_SDBaseModel):
    model_checkpoint: _SDOptional[str] = None


def _sd_model_cfg_dict():
    return config.data.setdefault("image", {}).setdefault("sd_webui", {})


def _sd_model_base_url() -> str:
    try:
        img_cfg = config.get_image_provider_config()
    except Exception:
        img_cfg = _sd_model_cfg_dict()
    return (
        img_cfg.get("base_url")
        or img_cfg.get("api_url")
        or img_cfg.get("url")
        or "http://127.0.0.1:7860"
    ).rstrip("/")


async def _sd_model_get_json(path: str):
    if _sd_model_httpx is None:
        raise RuntimeError("缺少 httpx 依赖，请执行 pip install httpx")
    async with _sd_model_httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{_sd_model_base_url()}{path}")
        resp.raise_for_status()
        return resp.json()


async def _sd_model_post_json(path: str, payload: dict):
    if _sd_model_httpx is None:
        raise RuntimeError("缺少 httpx 依赖，请执行 pip install httpx")
    async with _sd_model_httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{_sd_model_base_url()}{path}", json=payload)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            return resp.json()
        return {"ok": True, "text": resp.text}


@app.get("/api/sd/models")
async def api_sd_model_selector_list_models():
    """读取 A1111 / Forge / SD WebUI 的 checkpoint 列表。"""
    try:
        data = await _sd_model_get_json("/sdapi/v1/sd-models")
        models = []
        for item in data or []:
            title = item.get("title") or item.get("model_name") or item.get("filename")
            if title and title not in models:
                models.append(title)
        return {
            "ok": True,
            "base_url": _sd_model_base_url(),
            "models": models,
        }
    except Exception as e:
        return {
            "ok": False,
            "base_url": _sd_model_base_url(),
            "models": [],
            "error": str(e),
        }


@app.get("/api/sd/model-setting")
async def api_sd_model_selector_get_setting():
    img_cfg = _sd_model_cfg_dict()
    current = img_cfg.get("model_checkpoint", "") or img_cfg.get("sd_model_checkpoint", "")

    if not current:
        try:
            opts = await _sd_model_get_json("/sdapi/v1/options")
            current = opts.get("sd_model_checkpoint", "") or current
        except Exception:
            pass

    return {
        "ok": True,
        "base_url": _sd_model_base_url(),
        "model_checkpoint": current,
    }


@app.post("/api/sd/model-setting")
async def api_sd_model_selector_update_setting(update: SDModelSettingUpdate):
    global image_provider

    img_cfg = _sd_model_cfg_dict()
    selected = (update.model_checkpoint or "").strip()
    img_cfg["model_checkpoint"] = selected
    config.save()

    try:
        image_provider = None
    except Exception:
        pass

    applied = False
    error = None
    if selected:
        try:
            await _sd_model_post_json("/sdapi/v1/options", {"sd_model_checkpoint": selected})
            applied = True
        except Exception as e:
            error = str(e)

    return {
        "ok": True,
        "base_url": _sd_model_base_url(),
        "model_checkpoint": selected,
        "applied": applied,
        "error": error,
    }
# ── end Stable Diffusion Model Selector v6.6 ────────────────────────────────
'''

HTML_BLOCK = r'''
<!-- Stable Diffusion model selector v6.6 -->
<div class="form-row sd-model-selector-v66" style="display:grid;grid-template-columns:1fr;gap:12px;margin:12px 0;">
  <div class="form-group">
    <label>Stable Diffusion 模型</label>
    <div style="display:flex;gap:8px;align-items:center;">
      <select id="selSdModel" style="flex:1;min-width:0;">
        <option value="">加载中...</option>
      </select>
      <button type="button" onclick="loadSdModelListV66()" title="刷新模型列表">🔄</button>
    </div>
    <small id="sdModelHint" style="opacity:.75;display:block;margin-top:6px;">保存设置后会同步切换 SD WebUI 当前模型。</small>
  </div>
</div>
<!-- end Stable Diffusion model selector v6.6 -->
'''

FRONTEND_JS = r'''

// ── Stable Diffusion model selector v6.6 ───────────────────────────────────
async function loadSdModelListV66(selectedValue) {
  const sel = document.getElementById('selSdModel');
  const hint = document.getElementById('sdModelHint');
  if (!sel) return;

  const selected = selectedValue ?? sel.value ?? '';
  sel.innerHTML = '<option value="">加载中...</option>';
  if (hint) hint.textContent = '正在从 SD WebUI 读取模型列表...';

  try {
    const res = await fetch('/api/sd/models');
    const data = await res.json();
    const models = data.models || [];

    sel.innerHTML = '';

    if (!data.ok) {
      const opt = document.createElement('option');
      opt.value = selected || '';
      opt.textContent = selected || '获取失败';
      opt.selected = true;
      sel.appendChild(opt);
      if (hint) hint.textContent = `获取模型列表失败：${data.error || '请确认 SD WebUI 已用 --api 启动'}；当前地址：${data.base_url || ''}`;
      return;
    }

    if (models.length === 0) {
      const opt = document.createElement('option');
      opt.value = selected || '';
      opt.textContent = selected || '未获取到模型';
      opt.selected = true;
      sel.appendChild(opt);
      if (hint) hint.textContent = `没有获取到模型列表，请确认 SD WebUI 地址是否正确：${data.base_url || ''}`;
      return;
    }

    for (const item of models) {
      const opt = document.createElement('option');
      opt.value = item;
      opt.textContent = item;
      if (item === selected) opt.selected = true;
      sel.appendChild(opt);
    }

    if (selected && !models.includes(selected)) {
      const opt = document.createElement('option');
      opt.value = selected;
      opt.textContent = selected;
      opt.selected = true;
      sel.appendChild(opt);
    }

    if (!selected && sel.options.length > 0) {
      sel.selectedIndex = 0;
    }

    if (hint) hint.textContent = `已读取 ${models.length} 个模型；保存设置后会同步切换 SD WebUI 当前模型。`;
  } catch (e) {
    sel.innerHTML = '';
    const opt = document.createElement('option');
    opt.value = selected || '';
    opt.textContent = selected || '获取失败';
    opt.selected = true;
    sel.appendChild(opt);
    if (hint) hint.textContent = `获取模型列表失败：${e}`;
  }
}

async function loadSdModelSettingV66() {
  let selected = '';
  try {
    const res = await fetch('/api/sd/model-setting');
    const data = await res.json();
    selected = data.model_checkpoint || '';
  } catch (e) {
    selected = '';
  }
  await loadSdModelListV66(selected);
}

async function saveSdModelSettingV66() {
  const sel = document.getElementById('selSdModel');
  const hint = document.getElementById('sdModelHint');
  if (!sel) return;

  try {
    const res = await fetch('/api/sd/model-setting', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_checkpoint: sel.value || '' }),
    });
    const data = await res.json();
    if (hint) {
      if (data.applied) {
        hint.textContent = '模型已保存，并已同步切换到 SD WebUI。';
      } else if (data.error) {
        hint.textContent = `模型已保存到本项目配置，但同步切换 SD WebUI 失败：${data.error}`;
      } else {
        hint.textContent = '模型已保存。';
      }
    }
  } catch (e) {
    if (hint) hint.textContent = `保存 Stable Diffusion 模型失败：${e}`;
    console.warn('保存 Stable Diffusion 模型失败', e);
  }
}

(function wrapSdModelSettingsHooksV66() {
  if (typeof window.showSettings === 'function' && !window.showSettings.__sdModelV66Wrapped) {
    const oldShowSettings = window.showSettings;
    const wrappedShowSettings = async function(...args) {
      const ret = await oldShowSettings.apply(this, args);
      try { await loadSdModelSettingV66(); } catch (e) { console.warn(e); }
      return ret;
    };
    wrappedShowSettings.__sdModelV66Wrapped = true;
    window.showSettings = wrappedShowSettings;
  }

  if (typeof window.saveSettings === 'function' && !window.saveSettings.__sdModelV66Wrapped) {
    const oldSaveSettings = window.saveSettings;
    const wrappedSaveSettings = async function(...args) {
      try { await saveSdModelSettingV66(); } catch (e) { console.warn(e); }
      return await oldSaveSettings.apply(this, args);
    };
    wrappedSaveSettings.__sdModelV66Wrapped = true;
    window.saveSettings = wrappedSaveSettings;
  }
})();
// ── end Stable Diffusion model selector v6.6 ───────────────────────────────
'''


def fail(message: str) -> None:
    print(f"[失败] {message}")
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def backup(path: Path) -> None:
    if not path.exists():
        fail(f"找不到文件：{path}")
    bak = path.with_name(path.name + BACKUP_SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"[备份] {path} -> {bak}")


def compile_python(path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"Python 语法检查失败：{path}\n{result.stdout}\n{result.stderr}")


def remove_between_markers(text: str, start: str, end: str) -> str:
    while start in text and end in text:
        s = text.find(start)
        e = text.find(end, s)
        if e == -1:
            break
        e2 = text.find("\n", e)
        if e2 == -1:
            e2 = len(text)
        text = text[:s].rstrip() + "\n" + text[e2:].lstrip()
    return text


def patch_server() -> None:
    backup(SERVER)
    text = read_text(SERVER)
    compile_python(SERVER)

    text = remove_between_markers(text, SERVER_START, SERVER_END)
    for pat in OLD_SERVER_START_PATTERNS:
        text = re.sub(pat, "\n", text, flags=re.MULTILINE)

    mount_patterns = [
        'app.mount("/", StaticFiles',
        "app.mount('/', StaticFiles",
        'app.mount("/",',
        "app.mount('/',",
    ]
    insert_at = -1
    for marker in mount_patterns:
        pos = text.find(marker)
        if pos != -1:
            insert_at = text.rfind("\n", 0, pos) + 1
            break

    if insert_at == -1:
        for marker in ['if __name__ == "__main__"', "if __name__ == '__main__'"]:
            pos = text.find(marker)
            if pos != -1:
                insert_at = pos
                break

    if insert_at == -1:
        text = text.rstrip() + "\n\n" + SERVER_SNIPPET.strip() + "\n"
    else:
        text = text[:insert_at].rstrip() + "\n\n" + SERVER_SNIPPET.strip() + "\n\n" + text[insert_at:].lstrip()

    write_text(SERVER, text)
    compile_python(SERVER)
    print("[完成] 后端已加入 /api/sd/models 和 /api/sd/model-setting，并确保在静态挂载之前注册")


def remove_old_html_blocks(html: str) -> str:
    html = re.sub(
        r"\n?<!-- Stable Diffusion model selector v6\.6 -->[\s\S]*?<!-- end Stable Diffusion model selector v6\.6 -->\n?",
        "\n",
        html,
        flags=re.MULTILINE,
    )

    while "sd-model-setting-block" in html:
        p = html.find("sd-model-setting-block")
        start = html.rfind("<div", 0, p)
        small_end = html.find("</small>", p)
        if start == -1 or small_end == -1:
            break
        end = html.find("</div>", small_end)
        if end == -1:
            break
        html = html[:start].rstrip() + "\n" + html[end + len("</div>"):].lstrip()

    while "sd-model-selector-v66" in html:
        p = html.find("sd-model-selector-v66")
        start = html.rfind("<div", 0, p)
        marker_end = html.find("<!-- end Stable Diffusion model selector", p)
        if start != -1 and marker_end != -1:
            end = html.find("-->", marker_end)
            if end != -1:
                html = html[:start].rstrip() + "\n" + html[end + 3:].lstrip()
                continue
        break

    return html


def find_sampler_insert_position(html: str) -> int:
    sampler_keywords = ["采样方法", "Sampler", "selSdSampler", "inputSdSampler", "sd_sampler"]
    for key in sampler_keywords:
        pos = html.find(key)
        if pos == -1:
            continue
        candidates = []
        for marker in [
            '<div class="form-row"',
            "<div class='form-row'",
            '<div class="form-group"',
            "<div class='form-group'",
            '<section',
        ]:
            idx = html.rfind(marker, 0, pos)
            if idx != -1:
                candidates.append(idx)
        if candidates:
            return max(candidates)
        div_pos = html.rfind("<div", 0, pos)
        if div_pos != -1:
            return div_pos
        return pos

    voice_pos = html.find("语音设置")
    if voice_pos != -1:
        insert_at = html.rfind("<", 0, voice_pos)
        if insert_at != -1:
            return insert_at

    neg_pos = html.find("默认反向提示词")
    if neg_pos != -1:
        end = html.find("</div>", neg_pos)
        if end != -1:
            return end + len("</div>")

    fail("找不到插入位置：没有发现‘采样方法’或‘默认反向提示词’区域")


def remove_old_frontend_js(html: str) -> str:
    html = remove_between_markers(html, FRONTEND_START, FRONTEND_END)
    for pat in OLD_FRONTEND_PATTERNS:
        html = re.sub(pat, "\n", html, flags=re.MULTILINE)
    return html


def append_frontend_js(html: str) -> str:
    if "loadSdModelListV66" in html:
        return html
    script_close = html.rfind("</script>")
    if script_close != -1:
        return html[:script_close].rstrip() + "\n" + FRONTEND_JS + "\n" + html[script_close:]
    body_close = html.rfind("</body>")
    script = "\n<script>\n" + FRONTEND_JS.strip() + "\n</script>\n"
    if body_close != -1:
        return html[:body_close].rstrip() + script + "\n" + html[body_close:]
    return html.rstrip() + script


def patch_index() -> None:
    backup(INDEX)
    html = read_text(INDEX)
    html = remove_old_html_blocks(html)
    html = remove_old_frontend_js(html)

    insert_at = find_sampler_insert_position(html)
    html = html[:insert_at].rstrip() + "\n" + HTML_BLOCK.strip() + "\n" + html[insert_at:].lstrip()
    html = append_frontend_js(html)

    write_text(INDEX, html)
    print("[完成] 前端已把 Stable Diffusion 模型放到正反提示词和采样方法之间")


def main() -> None:
    if not SERVER.exists() or not INDEX.exists():
        fail("请把脚本放到 localchat 项目根目录运行，当前目录缺少 web/server.py 或 web/static/index.html")

    print("[开始] 修复 Stable Diffusion 模型选择功能 v6.6")
    patch_server()
    patch_index()
    print("\n[成功] 已完成。")
    print("\n下一步：")
    print("1. 启动 SD WebUI，确保带 --api")
    print("2. 启动项目：python web/server.py")
    print("3. 浏览器 Ctrl + F5 强制刷新")
    print("4. 打开设置，Stable Diffusion 模型应位于正反提示词和采样方法之间")
    print("\n如果下拉框仍然获取不到模型列表，直接打开这个地址测试：")
    print("http://127.0.0.1:7860/sdapi/v1/sd-models")
    print("能看到 JSON 才说明 SD WebUI 的 API 是正常开的。")


if __name__ == "__main__":
    main()
