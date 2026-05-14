"""Telegram bot — 连接 LocalChat API，在 Telegram 上聊天"""

import json
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

LOCALCHAT_URL = "http://localhost:8000/api/chat"
BOT_TOKEN = "8631006863:AAH5Rm1MYXZP09WlHuYbuzmj02G7LbvZaDI"


async def chat_with_localchat(message: str) -> str:
    """调用 LocalChat API，解析 SSE 流，返回完整回复文本"""
    async with httpx.AsyncClient(timeout=120.0) as cli:
        async with cli.stream("POST", LOCALCHAT_URL, json={"message": message}) as resp:
            full = ""
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if "text" in chunk:
                        full += chunk["text"]
                except json.JSONDecodeError:
                    continue
            return full or "（没有收到回复）"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_text = update.message.text
    reply = await chat_with_localchat(user_text)
    await update.message.reply_text(reply)


PROXY = "http://127.0.0.1:7897"


def main():
    app = Application.builder().token(BOT_TOKEN).proxy(PROXY).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Telegram Bot 已启动，去 Telegram 发消息试试吧")
    
    app.run_polling()
    




if __name__ == "__main__":
    main()
