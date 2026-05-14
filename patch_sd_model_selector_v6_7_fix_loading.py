from __future__ import annotations

"""
patch_sd_model_selector_v6_7_fix_loading.py

修复 Stable Diffusion 模型下拉框一直停在“加载中”的问题。

这版重点修两件事：
1. 后端接口强制注册在 app = FastAPI(...) 之后、app.mount 静态路由之前，避免 /api/sd/models 被静态页面拦截。
2. 前端不再只依赖 showSettings() 包装；会在页面加载、设置弹窗打开、点击刷新按钮时主动加载模型列表。

运行：
    python patch_sd_model_selector_v6_7_fix_loading.py

运行后：
    python web/server.py
    浏览器 Ctrl + F5

如果还有问题，打开：
    http://127.0.0.1:8000/api/sd/models
应该返回 localchat 后端转发出的 JSON。
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SERVER = ROOT / "web" / "server.py"
INDEX = ROOT / "web" / "static" / "index.html"
BACKUP_SUFFIX = ".sd_model_selector_v6_7.bak"

SERVER_REMOVE_PATTERNS = [
    r"\n?# ── Stable Diffusion Model Selector v6\.7[\s\S]*?# ── end Stable Diffusion Model Selector v6\.7[\s\S]*?\n",
    r"\n?# ── Stable Diffusion Model Selector v6\.6[\s\S]*?# ── end Stable Diffusion Model Selector v6\.6[\s\S]*?\n",
    r"\n?# ── Stable Diffusion Model Selector \(added by patch_sd_model_only_v6_5\.py\)[\s\S]*?# ── end Stable Diffusion Model Selector ─+\n?",
]

FRONTEND_REMOVE_PATTERNS = [
    r"\n?// ── Stable Diffusion model selector v6\.7[\s\S]*?// ── end Stable Diffusion model selector v6\.7[\s\S]*?\n",
    r"\n?// ── Stable Diffusion model selector v6\.6[\s\S]*?// ── end Stable Diffusion model selector v6\.6[\s\S]*?\n",
    r"\n?// ── Stable Diffusion model selector \(added by patch_sd_model_only_v6_5\.py\)[\s\S]*?// ── end Stable Diffusion model selector ─+\n?",
]

SERVER_SNIPPET = """
# ── Stable Diffusion Model Selector v6.7 ────────────────────────────────────
# Added by patch_sd_model_selector_v6_7_fix_loading.py
try:
    import httpx as _sd_model_httpx
except Exception:
    _sd_model_httpx = None


class SDModelSettingUpdate(BaseModel):
    model_checkpoint: Optional[str] = None


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
    url = f"{_sd_model_base_url()}{path}"
    async with _sd_model_httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _sd_model_post_json(path: str, payload: dict):
    if _sd_model_httpx is None:
        raise RuntimeError("缺少 httpx 依赖，请执行 pip install httpx")
    url = f"{_sd_model_base_url()}{path}"
    async with _sd_model_httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            return resp.json()
        return {"ok": True, "text": resp.text}


@app.get("/api/sd/models")
async def api_sd_model_selector_list_models():
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
            "count": len(models),
        }
    except Exception as e:
        return {
            "ok": False,
            "base_url": _sd_model_base_url(),
            "models": [],
            "count": 0,
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
# ── end Stable Diffusion Model Selector v6.7 ────────────────────────────────
"""

HTML_BLOCK = """
<!-- Stable Diffusion model selector v6.7 -->
<div class="form-row sd-model-selector-v67" style="display:grid;grid-template-columns:1fr;gap:12px;margin:12px 0;">
  <div class="form-group">
    <label>Stable Diffusion 模型</label>
    <div style="display:flex;gap:8px;align-items:center;">
      <select id="selSdModel" style="flex:1;min-width:0;">
        <option value="">等待加载模型列表...</option>
      </select>
      <button type="button" onclick="loadSdModelListV67()" title="刷新模型列表">刷新</button>
    </div>
    <small id="sdModelHint" style="opacity:.75;display:block;margin-top:6px;">会从本项目后端 /api/sd/models 读取 SD WebUI 模型列表。</small>
  </div>
</div>
<!-- end Stable Diffusion model selector v6.7 -->
"""

FRONTEND_JS = """
// ── Stable Diffusion model selector v6.7 ───────────────────────────────────
async function fetchJsonV67(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`${url} 没有返回 JSON，前 120 字：${text.slice(0, 120)}`);
  }
}

async function loadSdModelListV67(selectedValue) {
  const sel = document.getElementById('selSdModel');
  const hint = document.getElementById('sdModelHint');
  if (!sel) return;

  const selected = selectedValue ?? sel.value ?? '';
  sel.innerHTML = '<option value="">加载中...</option>';
  if (hint) hint.textContent = '正在请求 /api/sd/models ...';

  try {
    const data = await fetchJsonV67('/api/sd/models?_=' + Date.now());
    const models = data.models || [];

    sel.innerHTML = '';

    if (!data.ok) {
      const opt = document.createElement('option');
      opt.value = selected || '';
      opt.textContent = selected || '获取失败';
      opt.selected = true;
      sel.appendChild(opt);
      if (hint) hint.textContent = `获取失败：${data.error || '未知错误'}；SD 地址：${data.base_url || ''}`;
      return;
    }

    if (!models.length) {
      const opt = document.createElement('option');
      opt.value = selected || '';
      opt.textContent = selected || '没有模型';
      opt.selected = true;
      sel.appendChild(opt);
      if (hint) hint.textContent = `后端正常返回，但模型数量为 0；SD 地址：${data.base_url || ''}`;
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

    if (!selected && sel.options.length > 0) sel.selectedIndex = 0;
    if (hint) hint.textContent = `已读取 ${models.length} 个模型；数据来自 ${data.base_url || 'SD WebUI'}。`;
  } catch (e) {
    sel.innerHTML = '';
    const opt = document.createElement('option');
    opt.value = selected || '';
    opt.textContent = selected || '加载失败';
    opt.selected = true;
    sel.appendChild(opt);
    if (hint) hint.textContent = `模型列表加载失败：${e.message || e}`;
    console.error(e);
  }
}

async function loadSdModelSettingV67() {
  let selected = '';
  try {
    const data = await fetchJsonV67('/api/sd/model-setting?_=' + Date.now());
    selected = data.model_checkpoint || '';
  } catch (e) {
    console.warn('读取 SD 模型设置失败', e);
  }
  await loadSdModelListV67(selected);
}

async function saveSdModelSettingV67() {
  const sel = document.getElementById('selSdModel');
  const hint = document.getElementById('sdModelHint');
  if (!sel) return;

  try {
    const data = await fetchJsonV67('/api/sd/model-setting', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_checkpoint: sel.value || '' }),
    });
    if (hint) {
      if (data.applied) {
        hint.textContent = '模型已保存，并已同步切换 SD WebUI 当前模型。';
      } else if (data.error) {
        hint.textContent = `模型已保存到本项目，但同步切换 SD WebUI 失败：${data.error}`;
      } else {
        hint.textContent = '模型已保存。';
      }
    }
  } catch (e) {
    if (hint) hint.textContent = `保存模型失败：${e.message || e}`;
    console.error(e);
  }
}

function installSdModelHooksV67() {
  if (window.__sdModelHooksV67Installed) return;
  window.__sdModelHooksV67Installed = true;

  setTimeout(() => {
    if (document.getElementById('selSdModel')) loadSdModelSettingV67();
  }, 300);

  if (typeof window.showSettings === 'function' && !window.showSettings.__sdModelV67Wrapped) {
    const oldShowSettings = window.showSettings;
    const wrappedShowSettings = async function(...args) {
      const ret = await oldShowSettings.apply(this, args);
      setTimeout(() => loadSdModelSettingV67(), 50);
      return ret;
    };
    wrappedShowSettings.__sdModelV67Wrapped = true;
    window.showSettings = wrappedShowSettings;
  }

  if (typeof window.saveSettings === 'function' && !window.saveSettings.__sdModelV67Wrapped) {
    const oldSaveSettings = window.saveSettings;
    const wrappedSaveSettings = async function(...args) {
      await saveSdModelSettingV67();
      return await oldSaveSettings.apply(this, args);
    };
    wrappedSaveSettings.__sdModelV67Wrapped = true;
    window.saveSettings = wrappedSaveSettings;
  }

  const obs = new MutationObserver(() => {
    const sel = document.getElementById('selSdModel');
    if (sel && sel.options.length === 1 && /加载|等待/.test(sel.options[0].textContent || '')) {
      loadSdModelSettingV67();
    }
  });
  obs.observe(document.documentElement, {childList: true, subtree: true, attributes: true});
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installSdModelHooksV67);
} else {
  installSdModelHooksV67();
}
// ── end Stable Diffusion model selector v6.7 ───────────────────────────────
"""


def fail(msg: str) -> None:
    print(f"[失败] {msg}")
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


def remove_patterns(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        text = re.sub(pat, "\n", text, flags=re.MULTILINE)
    return text


def patch_server() -> None:
    backup(SERVER)
    text = read_text(SERVER)
    compile_python(SERVER)

    text = remove_patterns(text, SERVER_REMOVE_PATTERNS)

    app_markers = [
        'app = FastAPI(title="Local AI Chat")',
        "app = FastAPI(title='Local AI Chat')",
        "app = FastAPI(",
    ]
    insert_at = -1
    for marker in app_markers:
        pos = text.find(marker)
        if pos != -1:
            line_end = text.find("\n", pos)
            if line_end == -1:
                line_end = pos + len(marker)
            insert_at = line_end + 1
            break

    if insert_at == -1:
        pos = text.find("app.mount(")
        if pos != -1:
            insert_at = text.rfind("\n", 0, pos) + 1

    if insert_at == -1:
        fail("没有找到 app = FastAPI(...) 或 app.mount(...)，无法安全插入后端接口")

    text = text[:insert_at].rstrip() + "\n\n" + SERVER_SNIPPET.strip() + "\n\n" + text[insert_at:].lstrip()
    write_text(SERVER, text)
    compile_python(SERVER)
    print("[完成] 后端接口已注册到 app 初始化之后，避免被静态路由拦截")


def remove_old_html_blocks(html: str) -> str:
    html = re.sub(
        r"\n?<!-- Stable Diffusion model selector v6\.7 -->[\s\S]*?<!-- end Stable Diffusion model selector v6\.7 -->\n?",
        "\n",
        html,
        flags=re.MULTILINE,
    )
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
        end = html.find("</div>", small_end if small_end != -1 else p)
        if start == -1 or end == -1:
            break
        html = html[:start].rstrip() + "\n" + html[end + len("</div>"):].lstrip()

    for cls in ["sd-model-selector-v66", "sd-model-selector-v67"]:
        while cls in html:
            p = html.find(cls)
            start = html.rfind("<div", 0, p)
            end_comment = html.find("<!-- end Stable Diffusion model selector", p)
            if start != -1 and end_comment != -1:
                end = html.find("-->", end_comment)
                if end != -1:
                    html = html[:start].rstrip() + "\n" + html[end + 3:].lstrip()
                    continue
            break
    return html


def find_insert_before_sampler(html: str) -> int:
    for key in ["采样方法", "Sampler", "selSdSampler", "inputSdSteps", "迭代步数", "Steps"]:
        pos = html.find(key)
        if pos == -1:
            continue
        candidates = []
        for marker in [
            '<div class="form-row"',
            "<div class='form-row'",
            '<div class="form-group"',
            "<div class='form-group'",
            "<section",
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

    fail("没有找到采样方法/Sampler/Steps 区域，无法放到它前面")


def append_frontend_js(html: str) -> str:
    html = remove_patterns(html, FRONTEND_REMOVE_PATTERNS)
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
    insert_at = find_insert_before_sampler(html)
    html = html[:insert_at].rstrip() + "\n" + HTML_BLOCK.strip() + "\n" + html[insert_at:].lstrip()
    html = append_frontend_js(html)
    write_text(INDEX, html)
    print("[完成] 前端位置已修正：正反提示词和采样方法之间")


def main() -> None:
    if not SERVER.exists() or not INDEX.exists():
        fail("请把脚本放到 localchat 项目根目录运行，当前目录缺少 web/server.py 或 web/static/index.html")

    print("[开始] 修复模型下拉框一直加载中 v6.7")
    patch_server()
    patch_index()
    print("\n[成功] v6.7 修复完成。")
    print("\n请现在执行：")
    print("1. 重启 localchat：python web/server.py")
    print("2. 浏览器 Ctrl + F5")
    print("3. 先打开 http://127.0.0.1:8000/api/sd/models 测试 localchat 后端是否返回 JSON")
    print("4. 再打开设置页查看下拉框")


if __name__ == "__main__":
    main()
