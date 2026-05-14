"""只修改前端设置界面：删除火山引擎旧版控制台入口，保留新版控制台 API Key。

用法：
    1. 把本文件放到项目根目录 localchat/ 下。
    2. 运行：python patch_frontend_new_console_only.py

它只会改：web/static/index.html
会自动生成备份：web/static/index.html.bak
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "web" / "static" / "index.html"


def backup_once(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak")
    if path.exists() and not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"找不到文件：{INDEX_PATH}")

    html = INDEX_PATH.read_text(encoding="utf-8")
    original = html

    # 删除设置界面中的旧版控制台输入区：
    # App ID（旧版控制台） / Access Key（旧版控制台） / — 或者 —
    old_console_block_patterns = [
        r'''\s*<label>\s*App\s*ID（旧版控制台）\s*</label>\s*\n?\s*<input[^>]*id=["']inputVolcAppId["'][^>]*>\s*\n?\s*<label>\s*Access\s*Key（旧版控制台）\s*</label>\s*\n?\s*<input[^>]*id=["']inputVolcToken["'][^>]*>\s*\n?\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*\n?''',
        r'''\s*<label>\s*App\s*ID[^<]*旧版控制台[^<]*</label>\s*\n?\s*<input[^>]*(?:id=["']inputVolcAppId["']|inputVolcAppId)[^>]*>\s*\n?\s*<label>\s*Access\s*Key[^<]*旧版控制台[^<]*</label>\s*\n?\s*<input[^>]*(?:id=["']inputVolcToken["']|inputVolcToken)[^>]*>\s*\n?\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*\n?''',
    ]
    for pattern in old_console_block_patterns:
        html = re.sub(pattern, "\n", html, flags=re.S)

    # 兜底：如果格式被压缩或手工改过，逐项删除旧输入控件和分隔线。
    html = re.sub(r'''\s*<label>\s*App\s*ID[^<]*旧版控制台[^<]*</label>\s*''', "\n", html, flags=re.S)
    html = re.sub(r'''\s*<input[^>]*id=["']inputVolcAppId["'][^>]*>\s*''', "\n", html, flags=re.S)
    html = re.sub(r'''\s*<label>\s*Access\s*Key[^<]*旧版控制台[^<]*</label>\s*''', "\n", html, flags=re.S)
    html = re.sub(r'''\s*<input[^>]*id=["']inputVolcToken["'][^>]*>\s*''', "\n", html, flags=re.S)
    html = re.sub(r'''\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*''', "\n", html, flags=re.S)

    # 如果前端 JS 里有旧字段读写，也一起删除，避免保存时报错。
    html = re.sub(r"^.*(?:inputVolcAppId|inputVolcToken).*(?:\r?\n|$)", "", html, flags=re.M)
    html = re.sub(r"^\s*(?:volcengine_)?(?:app_id|access_token)\s*:\s*[^\n]+,?\s*(?:\r?\n|$)", "", html, flags=re.M)

    # 保留新版控制台，并把提示文字改得更明确。
    html = html.replace("API Key（新版控制台）", "API Key（新版控制台）")
    html = re.sub(
        r'''(<input[^>]*id=["']inputVolcApiKey["'][^>]*placeholder=["'])[^"']*(["'][^>]*>)''',
        r"\1输入新版控制台 API Key\2",
        html,
        flags=re.S,
    )

    # 收尾：去掉可能残留的旧版字样。
    html = html.replace("（旧版控制台）", "")

    if html == original:
        print("前端界面里没有发现旧版控制台内容，可能已经删过。")
        return

    backup_once(INDEX_PATH)
    INDEX_PATH.write_text(html, encoding="utf-8")

    # 校验旧 UI 是否还残留。
    leftovers = [
        "App ID（旧版控制台）",
        "Access Key（旧版控制台）",
        "inputVolcAppId",
        "inputVolcToken",
        "— 或者 —",
    ]
    after = INDEX_PATH.read_text(encoding="utf-8")
    remains = [x for x in leftovers if x in after]

    print("已修改：web/static/index.html")
    print("已备份：web/static/index.html.bak")
    if remains:
        print("警告：仍检测到残留内容：" + ", ".join(remains))
    else:
        print("检查通过：旧版控制台前端入口已删除，只保留新版控制台 API Key。")


if __name__ == "__main__":
    main()
