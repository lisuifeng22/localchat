#!/usr/bin/env python3
"""读取聊天记录 → AI分析 → 生成角色卡 (JSON)"""

import json
import sys
import asyncio
from pathlib import Path

# 复用项目已有模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from providers.base import ChatMessage
from providers.openai import OpenAIProvider

SYSTEM_PROMPT = """你是一个专业的人物分析专家。我会给你一份聊天记录，请你分析聊天对象的性格特征、说话风格等，然后生成一个角色卡JSON。

请输出严格的JSON格式，不要包含markdown代码块标记，只输出纯JSON：

{
  "name": "角色名称（从聊天记录推断）",
  "avatar": "适合该角色的emoji",
  "description": "角色简介（30字以内）",
  "personality": "性格特征描述",
  "backstory": "根据聊天内容推断的背景故事（50字以内）",
  "speaking_style": "说话风格分析，包括常用词汇、句式特点、语气、口头禅等",
  "greeting": "以该角色的身份说一句开场白"
}"""

USER_PROMPT_TEMPLATE = """请分析以下聊天记录，提取出聊天对象的性格特征和说话风格，生成角色卡JSON：

---
{content}
---"""


def analyze(file_path: str) -> dict | None:
    path = Path(file_path)
    if not path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return None

    content = path.read_text(encoding="utf-8")
    name = path.stem  # 用文件名作为角色名

    if len(content) > 6000:
        print("⚠️ 聊天记录较长，已截取前6000字符")
        content = content[:6000]

    config = Config()
    cfg = config.get_provider_config()
    provider = OpenAIProvider(cfg)

    messages = [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage("user", USER_PROMPT_TEMPLATE.format(content=content)),
    ]

    async def _run():
        full = ""
        async for chunk in provider.chat_stream(messages, temperature=0.3, max_tokens=1024):
            if chunk.startswith("\n[ERROR]"):
                print(f"❌ API错误: {chunk}")
                return None
            full += chunk
            print(chunk, end="", flush=True)
        print()

        # 清理可能的 markdown 包裹
        full = full.strip()
        if full.startswith("```"):
            full = full.split("\n", 1)[-1]
            if "```" in full:
                full = full.split("```")[0]
        full = full.strip()

        try:
            return json.loads(full)
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON解析失败: {e}")
            print(f"原始输出: {full}")
            return None

    return asyncio.run(_run())


def save_card(data: dict):
    from character_manager import CHARACTERS_DIR
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARACTERS_DIR / f"{data['name']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 角色卡已保存: {path}")
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tools/chat_to_character.py <聊天记录.txt>")
        print("示例: python tools/chat_to_character.py 张三.txt")
        sys.exit(1)

    result = analyze(sys.argv[1])
    if result:
        print("\n📋 生成的角色卡:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        save_card(result)
