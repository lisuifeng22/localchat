"""Remove old Volcengine console fields from LocalChat settings UI.

Usage:
    Copy this file to the repository root, then run:
        python patch_remove_old_console.py

It only edits the local files in place and creates *.bak backups once.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def backup_once(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak")
    if path.exists() and not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8")
    if old == content:
        return False
    backup_once(path)
    path.write_text(content, encoding="utf-8")
    return True


def remove_old_console_from_index() -> bool:
    path = ROOT / "web" / "static" / "index.html"
    if not path.exists():
        print(f"[跳过] 找不到 {path}")
        return False

    s = path.read_text(encoding="utf-8")
    original = s

    # Remove the old-console credential block in the Volcengine settings panel.
    # Keeps the new-console API Key input and everything after it.
    patterns = [
        r'''\s*<label>\s*App\s*ID（旧版控制台）\s*</label>\s*\n?\s*<input[^>]*id=["']inputVolcAppId["'][^>]*>\s*\n?\s*<label>\s*Access\s*Key（旧版控制台）\s*</label>\s*\n?\s*<input[^>]*id=["']inputVolcToken["'][^>]*>\s*\n?\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*\n?''',
        r'''\s*<label>\s*App\s*ID[^<]*旧版控制台[^<]*</label>\s*\n?\s*<input[^>]*inputVolcAppId[^>]*>\s*\n?\s*<label>\s*Access\s*Key[^<]*旧版控制台[^<]*</label>\s*\n?\s*<input[^>]*inputVolcToken[^>]*>\s*\n?\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*\n?''',
    ]
    for pat in patterns:
        s = re.sub(pat, "\n", s, flags=re.S)

    # Tidy the remaining new-console label/placeholder.
    s = s.replace("API Key（新版控制台）", "API Key（新版控制台）")
    s = re.sub(
        r'''(<input[^>]*id=["']inputVolcApiKey["'][^>]*placeholder=["'])[^"']*(["'][^>]*>)''',
        r"\1输入新版控制台 API Key\2",
        s,
    )

    # Remove any JavaScript lines that still read/write removed DOM nodes.
    s = re.sub(r"^.*(?:inputVolcAppId|inputVolcToken).*(?:\n|$)", "", s, flags=re.M)

    # Remove any payload keys for old-console credentials if the frontend had them.
    s = re.sub(r"^\s*volcengine_app_id\s*:\s*[^\n]+,?\s*\n", "", s, flags=re.M)
    s = re.sub(r"^\s*volcengine_access_token\s*:\s*[^\n]+,?\s*\n", "", s, flags=re.M)

    # Last cleanup: remove any leftover old-console separator/wording.
    s = re.sub(r"\s*<div[^>]*>\s*—\s*或者\s*—\s*</div>\s*", "\n", s, flags=re.S)
    s = s.replace("（旧版控制台）", "")

    changed = s != original
    if changed:
        write_if_changed(path, s)
    return changed


def remove_old_console_from_config_py() -> bool:
    path = ROOT / "config.py"
    if not path.exists():
        print(f"[跳过] 找不到 {path}")
        return False
    s = path.read_text(encoding="utf-8")
    original = s
    s = re.sub(r'^\s*["\']app_id["\']\s*:\s*["\'][^"\']*["\']\s*,\s*\n', "", s, flags=re.M)
    s = re.sub(r'^\s*["\']access_token["\']\s*:\s*["\'][^"\']*["\']\s*,\s*\n', "", s, flags=re.M)
    if s != original:
        write_if_changed(path, s)
    return s != original


def remove_old_console_from_config_example() -> bool:
    path = ROOT / "config.example.json"
    if not path.exists():
        print(f"[跳过] 找不到 {path}")
        return False
    s = path.read_text(encoding="utf-8")
    original = s
    s = re.sub(r'^\s*"app_id"\s*:\s*"[^"]*"\s*,\s*\n', "", s, flags=re.M)
    s = re.sub(r'^\s*"access_token"\s*:\s*"[^"]*"\s*,\s*\n', "", s, flags=re.M)
    if s != original:
        write_if_changed(path, s)
    return s != original


def remove_old_console_from_server() -> bool:
    path = ROOT / "web" / "server.py"
    if not path.exists():
        print(f"[跳过] 找不到 {path}")
        return False
    s = path.read_text(encoding="utf-8")
    original = s

    out: list[str] = []
    skip_next = 0
    for line in s.splitlines(keepends=True):
        if skip_next:
            skip_next -= 1
            continue

        # Pydantic request fields.
        if re.search(r'\bvolcengine_(app_id|access_token)\s*:\s*Optional\[str\]', line):
            continue

        # GET /api/config response keys.
        if '"app_id"' in line and 'vol.get("app_id"' in line:
            continue
        if '"access_token"' in line and 'vol.get("access_token"' in line:
            continue

        # POST /api/config update blocks are two-line if-blocks in this project.
        if 'if update.volcengine_app_id' in line:
            skip_next = 1
            continue
        if 'if update.volcengine_access_token' in line:
            skip_next = 1
            continue

        out.append(line)

    s = "".join(out)
    if s != original:
        write_if_changed(path, s)
    return s != original


def main() -> None:
    changed = []
    for name, func in [
        ("web/static/index.html", remove_old_console_from_index),
        ("config.py", remove_old_console_from_config_py),
        ("config.example.json", remove_old_console_from_config_example),
        ("web/server.py", remove_old_console_from_server),
    ]:
        try:
            if func():
                changed.append(name)
        except Exception as exc:
            print(f"[失败] {name}: {exc}")
            raise

    if changed:
        print("已删除旧版控制台相关设置：")
        for item in changed:
            print(f"  - {item}")
        print("已自动生成 .bak 备份文件。")
    else:
        print("没有发现需要修改的旧版控制台内容，或已经处理过。")


if __name__ == "__main__":
    main()
