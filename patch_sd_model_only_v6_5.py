from __future__ import annotations

"""
给 localchat（v5 及其相近结构）集成“选择 Stable Diffusion 模型”功能。

目标：
- 在设置页中，把“Stable Diffusion 模型”下拉框插入到“默认正向/反向提示词”下面；
- 前端可加载 SD WebUI 的模型列表；
- 保存设置时把所选模型保存到项目 config.json；
- 同时调用 AUTOMATIC1111 的 /sdapi/v1/options 立即切换当前模型；
- 尽量少改动现有代码，避免再次把项目改挂。

只修改两个文件：
- web/server.py
- web/static/index.html

运行方式：
    python patch_sd_model_only_v6_5.py

运行前建议：
- 先确保你项目能正常启动；
- 先提交一版 git 或至少手动备份；
- SD WebUI 已启用 API（webui-user.bat --api）。
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SERVER = ROOT / "web" / "server.py"
INDEX = ROOT / "web" / "static" / "index.html"
BACKUP_SUFFIX = ".sd_model_only_v6_5.bak"


SERVER_SNIPPET = r'''

# ── Stable Diffusion Model Selector (added by patch_sd_model_only_v6_5.py) ──
try:
    import httpx as _sd_model_httpx
except Exception:
    _sd_model_httpx = None

class SDModelSettingUpdate(BaseModel):
    model_checkpoint: Optional[str] = None


def _sd_model_cfg_dict():
    return config.data.setdefault("image", {}).setdefault("sd_webui", {})


def _sd_base_url():
    try:
        img_cfg = config.get_image_provider_config()
    except Exception:
        img_cfg = config.data.get("image", {}).get("sd_webui", {})
    return (img_cfg.get("base_url") or "http://127.0.0.1:7860").rstrip("/")


async def _sd_fetch_json(path: str):
    if _sd_model_httpx is None:
        raise RuntimeError("缺少 httpx 依赖，请先 pip install httpx")
    async with _sd_model_httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(f"{_sd_base_url()}{path}")
        resp.raise_for_status()
        return resp.json()


async def _sd_post_json(path: str, payload: dict):
    if _sd_model_httpx is None:
        raise RuntimeError("缺少 httpx 依赖，请先 pip install httpx")
    async with _sd_model_httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{_sd_base_url()}{path}", json=payload)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            return resp.json()
        return {"ok": True, "text": resp.text}


@app.get("/api/sd/models")
async def api_list_sd_models():
    try:
        data = await _sd_fetch_json("/sdapi/v1/sd-models")
        models = []
        for item in data or []:
            title = item.get("title") or item.get("model_name") or item.get("filename")
            if title:
                models.append(title)
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.get("/api/sd/model-setting")
async def api_get_sd_model_setting():
    img_cfg = _sd_model_cfg_dict()
    current = img_cfg.get("model_checkpoint", "")

    # 如果项目本地还没存过，就尝试读 SD WebUI 当前模型。
    if not current:
        try:
            opts = await _sd_fetch_json("/sdapi/v1/options")
            current = opts.get("sd_model_checkpoint", "") or current
        except Exception:
            pass

    return {"model_checkpoint": current}


@app.post("/api/sd/model-setting")
async def api_update_sd_model_setting(update: SDModelSettingUpdate):
    img_cfg = _sd_model_cfg_dict()
    selected = (update.model_checkpoint or "").strip()
    img_cfg["model_checkpoint"] = selected
    config.save()

    # 立即切换 SD WebUI 当前模型（全局设置）
    applied = False
    error = None
    if selected:
        try:
            await _sd_post_json("/sdapi/v1/options", {"sd_model_checkpoint": selected})
            applied = True
        except Exception as e:
            error = str(e)

    return {
        "ok": True,
        "model_checkpoint": selected,
        "applied": applied,
        "error": error,
    }
# ── end Stable Diffusion Model Selector ─────────────────────────────────────
'''


HTML_BLOCK = r'''
<div class="form-group sd-model-setting-block" style="margin-top:12px;">
  <label>Stable Diffusion 模型</label>
  <div style="display:flex;gap:8px;align-items:center;">
    <select id="selSdModel" style="flex:1;min-width:0;">
      <option value="">加载中...</option>
    </select>
    <button type="button" onclick="loadSdModelList()" title="刷新模型列表">🔄</button>
  </div>
  <small style="opacity:.75;display:block;margin-top:6px;">保存设置后会同步切换 SD WebUI 当前使用的模型。</small>
</div>
'''


FRONTEND_JS = r'''

// ── Stable Diffusion model selector (added by patch_sd_model_only_v6_5.py) ──
async function loadSdModelList(selectedValue) {
  const sel = document.getElementById('selSdModel');
  if (!sel) return;
  const selected = selectedValue ?? sel.value ?? '';
  sel.innerHTML = '<option value="">加载中...</option>';
  try {
    const res = await fetch('/api/sd/models');
    const data = await res.json();
    const models = data.models || [];
    sel.innerHTML = '';
    if (models.length === 0) {
      const opt = document.createElement('option');
      opt.value = selected || '';
      opt.textContent = selected || '未获取到模型列表';
      opt.selected = true;
      sel.appendChild(opt);
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
  } catch (e) {
    sel.innerHTML = '';
    const opt = document.createElement('option');
    opt.value = selected || '';
    opt.textContent = selected || '加载失败';
    opt.selected = true;
    sel.appendChild(opt);
  }
}

async function loadSdModelSetting() {
  let selected = '';
  try {
    const res = await fetch('/api/sd/model-setting');
    const data = await res.json();
    selected = data.model_checkpoint || '';
  } catch (e) {
    selected = '';
  }
  await loadSdModelList(selected);
}

async function saveSdModelSetting() {
  const sel = document.getElementById('selSdModel');
  if (!sel) return;
  try {
    await fetch('/api/sd/model-setting', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model_checkpoint: sel.value || '' }),
    });
  } catch (e) {
    console.warn('保存 Stable Diffusion 模型失败', e);
  }
}

(function wrapSdModelSettingsHooks() {
  if (typeof window.showSettings === 'function' && !window.showSettings.__sdModelWrapped) {
    const oldShowSettings = window.showSettings;
    const wrappedShowSettings = async function(...args) {
      const ret = await oldShowSettings.apply(this, args);
      try { await loadSdModelSetting(); } catch (e) { console.warn(e); }
      return ret;
    };
    wrappedShowSettings.__sdModelWrapped = true;
    window.showSettings = wrappedShowSettings;
  }

  if (typeof window.saveSettings === 'function' && !window.saveSettings.__sdModelWrapped) {
    const oldSaveSettings = window.saveSettings;
    const wrappedSaveSettings = async function(...args) {
      try { await saveSdModelSetting(); } catch (e) { console.warn(e); }
      return await oldSaveSettings.apply(this, args);
    };
    wrappedSaveSettings.__sdModelWrapped = true;
    window.saveSettings = wrappedSaveSettings;
  }
})();
// ── end Stable Diffusion model selector ─────────────────────────────────────
'''


def fail(msg: str):
    print(f"[失败] {msg}")
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8", newline="\n")


def backup(path: Path):
    if not path.exists():
        fail(f"找不到文件：{path}")
    bak = path.with_name(path.name + BACKUP_SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"[备份] {path} -> {bak}")


def compile_python(path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"Python 语法检查失败：{path}\n{result.stdout}\n{result.stderr}")


def patch_server():
    backup(SERVER)
    text = read_text(SERVER)

    if "api_list_sd_models" in text and "api_update_sd_model_setting" in text:
        print("[跳过] web/server.py 已经包含 SD 模型选择接口")
        return

    compile_python(SERVER)

    # 尽量插入到 __main__ 前；没有就直接追加到末尾。
    marker1 = 'if __name__ == "__main__"'
    marker2 = "if __name__ == '__main__'"
    idx = text.find(marker1)
    if idx == -1:
        idx = text.find(marker2)

    if idx != -1:
        new_text = text[:idx].rstrip() + "\n\n" + SERVER_SNIPPET.strip() + "\n\n" + text[idx:]
    else:
        new_text = text.rstrip() + "\n\n" + SERVER_SNIPPET.strip() + "\n"

    write_text(SERVER, new_text)
    compile_python(SERVER)
    print("[完成] 已修改 web/server.py")


def insert_html_block(html: str) -> str:
    if 'id="selSdModel"' in html or "id='selSdModel'" in html:
        return html

    # 优先插在“语音设置”前面，这样自然就是在正反提示词下面。
    voice_pos = html.find("语音设置")
    if voice_pos != -1:
        insert_at = html.rfind("<", 0, voice_pos)
        if insert_at != -1:
            return html[:insert_at] + HTML_BLOCK + "\n" + html[insert_at:]

    # 备用：插在“默认反向提示词”之后。
    neg_pos = html.find("默认反向提示词")
    if neg_pos != -1:
        next_div = html.find("</div>", neg_pos)
        if next_div != -1:
            return html[:next_div + 6] + "\n" + HTML_BLOCK + "\n" + html[next_div + 6:]

    # 再不行就插到设置面板结尾前。
    modal_pos = html.rfind("</body>")
    if modal_pos != -1:
        return html[:modal_pos] + "\n" + HTML_BLOCK + "\n" + html[modal_pos:]

    fail("没有找到合适的前端插入位置，请检查 web/static/index.html")


def insert_frontend_js(html: str) -> str:
    if "loadSdModelSetting" in html and "saveSdModelSetting" in html:
        return html

    script_close = html.rfind("</script>")
    if script_close != -1:
        return html[:script_close] + FRONTEND_JS + "\n" + html[script_close:]

    body_close = html.rfind("</body>")
    script_tag = "\n<script>\n" + FRONTEND_JS.strip() + "\n</script>\n"
    if body_close != -1:
        return html[:body_close] + script_tag + html[body_close:]

    return html + script_tag


def patch_index():
    backup(INDEX)
    html = read_text(INDEX)
    html = insert_html_block(html)
    html = insert_frontend_js(html)
    write_text(INDEX, html)
    print("[完成] 已修改 web/static/index.html")


def main():
    if not SERVER.exists():
        fail("当前目录不像是 localchat 项目根目录：缺少 web/server.py")
    if not INDEX.exists():
        fail("当前目录不像是 localchat 项目根目录：缺少 web/static/index.html")

    print("[开始] 集成 Stable Diffusion 模型选择功能…")
    patch_server()
    patch_index()
    print("\n[成功] 补丁完成。")
    print("\n下一步这样做：")
    print("1) 启动 SD WebUI（建议 webui-user.bat --api）")
    print("2) 启动你的项目：python web/server.py")
    print("3) 浏览器强制刷新：Ctrl + F5")
    print("4) 打开 设置 -> 正反提示词下面，就能看到 Stable Diffusion 模型 下拉框")
    print("\n如果要回滚：")
    print(f"- web/server.py{BACKUP_SUFFIX}")
    print(f"- web/static/index.html{BACKUP_SUFFIX}")


if __name__ == "__main__":
    main()
