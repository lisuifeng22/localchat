"""FastAPI web server for Local AI Chat."""

import json
import sys
import asyncio
from pathlib import Path
from typing import Optional

# Add parent dir to path so we can import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import Config, GENERATED_DIR
from session_manager import SessionManager
from character_manager import CharacterManager
from providers.openai import OpenAIProvider
from providers.anthropic import AnthropicProvider
from providers.image import SDWebUIProvider
from providers.base import ChatMessage
from hashlib import md5 as hash_md5
from datetime import datetime

# ── App State ──────────────────────────────────────────────────────────────

config = Config()
sessions = SessionManager()
char_mgr = CharacterManager()
provider: Optional[OpenAIProvider | AnthropicProvider] = None
image_provider: Optional[SDWebUIProvider] = None

app = FastAPI(title="Local AI Chat")


def get_provider():
    global provider
    if provider is not None:
        return provider
    p_type = config.provider
    cfg = config.get_provider_config()
    if p_type == "anthropic":
        provider = AnthropicProvider(cfg)
    else:
        provider = OpenAIProvider(cfg)
    return provider


def get_image_provider() -> SDWebUIProvider:
    global image_provider
    if image_provider is not None:
        return image_provider
    img_cfg = config.get_image_provider_config()
    image_provider = SDWebUIProvider(img_cfg)
    return image_provider


# ── Request Models ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

class DrawRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None

class ConfigUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    default_prompt: Optional[str] = None
    default_negative_prompt: Optional[str] = None

class SessionRename(BaseModel):
    name: str

class SystemPromptUpdate(BaseModel):
    prompt: str


class CharacterData(BaseModel):
    name: str
    avatar: str = "🎭"
    description: str = ""
    personality: str = ""
    backstory: str = ""
    speaking_style: str = ""
    greeting: str = ""


# ── API Routes ─────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    p = get_provider()
    s = sessions.current
    return {
        "provider": config.provider,
        "model": p.model if p else "N/A",
        "temperature": config.temperature,
        "character": sessions.character or None,
        "character_card": char_mgr.active.name if char_mgr.active else None,
        "session_name": s.name if s else None,
        "session_count": len(sessions.sessions),
        "message_count": s.message_count if s else 0,
    }


@app.get("/api/config")
async def get_config():
    pcfg = config.get_provider_config()
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
    }


def mask_key(key: str) -> str:
    if len(key) > 8:
        return key[:5] + "****" + key[-4:]
    return "****" if key else ""


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    if update.provider:
        config.provider = update.provider
    if update.api_key:
        cfg = config.get_provider_config()
        cfg["api_key"] = update.api_key
    if update.base_url:
        cfg = config.get_provider_config()
        cfg["base_url"] = update.base_url
    if update.model:
        cfg = config.get_provider_config()
        cfg["model"] = update.model
        p = get_provider()
        if p:
            p.model = update.model
    if update.temperature is not None:
        config.data["ui"]["temperature"] = update.temperature
    if update.default_prompt is not None:
        config.data.setdefault("image", {})["default_prompt"] = update.default_prompt
    if update.default_negative_prompt is not None:
        config.data.setdefault("image", {})["default_negative_prompt"] = update.default_negative_prompt
    config.save()

    # Recreate provider on config change
    global provider
    provider = None
    get_provider()

    return {"ok": True}


@app.post("/api/restart")
async def restart_server():
    """Restart the server process."""
    import os, sys, subprocess
    # Spawn a new process and exit the current one
    subprocess.Popen([sys.executable, *sys.argv])
    os._exit(0)


@app.get("/api/models")
async def list_models():
    p = get_provider()
    if not p:
        return {"models": []}
    try:
        models = await p.list_models()
        return {"models": models}
    except Exception as e:
        return {"models": [p.model], "error": str(e)}


# ── Session Routes ─────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions():
    result = []
    for i, s in enumerate(sessions.sessions):
        result.append({
            "index": i,
            "name": s.name,
            "message_count": s.message_count,
            "active": i == sessions.current_idx,
        })
    return {"sessions": result, "current": sessions.current_idx}


@app.post("/api/sessions/new")
async def new_session():
    sessions.save_current()
    sessions.new_session()
    sessions.save_current()
    return {"ok": True, "index": sessions.current_idx}


@app.get("/api/sessions/current")
async def get_current_session():
    s = sessions.current
    if not s:
        return {"messages": []}
    return {
        "name": s.name,
        "system_prompt": s.system_prompt,
        "messages": [
            {"role": m.role, "content": m.content}
            for m in s.messages
        ],
    }


@app.post("/api/sessions/switch/{idx}")
async def switch_session(idx: int):
    if sessions.switch_to(idx):
        return {"ok": True}
    raise HTTPException(404, "Session not found")


@app.post("/api/sessions/delete/{idx}")
async def delete_session(idx: int):
    if sessions.delete_session(idx):
        return {"ok": True}
    raise HTTPException(404, "Session not found")


@app.post("/api/sessions/rename")
async def rename_session(body: SessionRename):
    sessions.rename_current(body.name)
    sessions.save_current()
    return {"ok": True}


@app.post("/api/sessions/clear")
async def clear_session():
    if sessions.current:
        sessions.current.clear()
        sessions.save_current()
    return {"ok": True}


@app.delete("/api/sessions/message/{idx}")
async def delete_message(idx: int):
    if not sessions.current:
        raise HTTPException(400, "No active session")
    if not sessions.current.delete_message(idx):
        raise HTTPException(404, "Message index out of range")
    sessions.save_current()
    return {"ok": True}


class MessageEdit(BaseModel):
    content: str


@app.put("/api/sessions/message/{idx}")
async def edit_message(idx: int, body: MessageEdit):
    """Edit message at index, truncate all messages after it."""
    if not sessions.current:
        raise HTTPException(400, "No active session")
    s = sessions.current
    if idx < 0 or idx >= len(s.messages):
        raise HTTPException(404, "Message index out of range")
    # Replace content
    s.messages[idx].content = body.content
    # Truncate everything after
    del s.messages[idx + 1:]
    s.updated_at = datetime.now().isoformat()
    sessions.save_current()
    return {"ok": True}


@app.post("/api/sessions/regenerate")
async def regenerate_last():
    """Remove the last assistant message and re-stream the response."""
    if not sessions.current:
        raise HTTPException(400, "No active session")
    s = sessions.current
    if not s.messages:
        raise HTTPException(400, "No messages to regenerate from")
    # Remove last message if it's from assistant (regenerate previous AI reply)
    if s.messages[-1].role == "assistant":
        s.messages.pop()
        s.updated_at = datetime.now().isoformat()
        sessions.save_current()
    # Now stream the response for the remaining context
    p = get_provider()
    if not p:
        raise HTTPException(500, "No provider configured")
    context = sessions.get_context_messages(char_mgr.get_system_prompt_extra())

    async def event_stream():
        full_response = ""
        try:
            async for chunk in p.chat_stream(
                context,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            ):
                if chunk.startswith("\n[ERROR]"):
                    yield f"data: {json.dumps({'error': chunk[7:]})}\n\n"
                    return
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"

            if full_response and sessions.current:
                sessions.current.add_message("assistant", full_response)
                sessions.save_current()

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/sessions/system")
async def update_system_prompt(body: SystemPromptUpdate):
    if sessions.current:
        sessions.current.system_prompt = body.prompt
        sessions.save_current()
    return {"ok": True}


@app.post("/api/sessions/export")
async def export_session():
    s = sessions.current
    if not s or not s.messages:
        raise HTTPException(400, "No messages to export")
    lines = [f"# {s.name}\n"]
    for m in s.messages:
        lines.append(f"\n## {m.role.capitalize()}\n\n{m.content}\n")
    return {"content": "".join(lines)}


# ── Character Routes ───────────────────────────────────────────────────────

@app.get("/api/characters")
async def list_characters():
    chars = []
    for name, card in char_mgr.characters.items():
        chars.append({
            "name": name,
            "description": card.description,
            "avatar": card.avatar,
            "active": name == char_mgr.active_name,
            "details": {
                "personality": card.personality,
                "backstory": card.backstory,
                "speaking_style": card.speaking_style,
                "greeting": card.greeting,
            }
        })
    return {"characters": chars, "active": char_mgr.active_name}


@app.post("/api/characters")
async def create_character(data: CharacterData):
    card = char_mgr.add_character(data.model_dump())
    return {"ok": True, "name": card.name}


@app.put("/api/characters/{name}")
async def update_character(name: str, data: CharacterData):
    card = char_mgr.update_character(name, data.model_dump())
    if not card:
        raise HTTPException(404, f"Character '{name}' not found")
    return {"ok": True, "name": card.name}


@app.delete("/api/characters/{name}")
async def delete_character(name: str):
    if not char_mgr.delete_character(name):
        raise HTTPException(404, f"Character '{name}' not found")
    return {"ok": True}


@app.post("/api/characters/{name}/load")
async def load_character(name: str):
    if name not in char_mgr.characters:
        raise HTTPException(404, f"Character '{name}' not found")

    # Switch session storage and character card
    sessions.set_character(name)
    char_mgr.set_active(name)
    card = char_mgr.active

    greeting = None
    is_new = sessions.current and sessions.current.message_count == 0
    if is_new and card and card.greeting:
        greeting = card.greeting
        sessions.current.add_message("assistant", greeting)
        sessions.save_current()

    return {
        "ok": True,
        "name": name,
        "avatar": card.avatar if card else "🎭",
        "description": card.description if card else "",
        "greeting": greeting,
        "is_new": is_new,
        "session_count": len(sessions.sessions),
    }


@app.post("/api/characters/stop")
async def stop_character():
    name = sessions.character
    sessions.clear_character()
    char_mgr.clear_active()
    return {"ok": True, "previous_character": name}


class CharacterImport(BaseModel):
    name: str
    avatar: str = "🎭"
    description: str = ""
    personality: str = ""
    backstory: str = ""
    speaking_style: str = ""
    greeting: str = ""


@app.get("/api/characters/{name}/export")
async def export_character(name: str):
    """Export a single character card as JSON."""
    card = char_mgr.characters.get(name)
    if not card:
        raise HTTPException(404, f"Character '{name}' not found")
    return card.to_dict()


@app.post("/api/characters/import")
async def import_character(data: CharacterImport):
    """Import a character card from JSON data."""
    if not data.name:
        raise HTTPException(400, "Character name is required")
    # Check if character already exists
    if data.name in char_mgr.characters:
        raise HTTPException(409, f"Character '{data.name}' already exists")
    card = char_mgr.add_character(data.model_dump())
    return {"ok": True, "name": card.name}


# ── Chat Route (SSE Streaming) ─────────────────────────────────────────────

ENHANCE_SYSTEM = (
    "You are an expert at writing prompts for Stable Diffusion. "
    "Rewrite the user's idea into a high-quality SD prompt following these rules:\n"
    "1. Use SD-style keyword format (comma-separated, no full sentences)\n"
    "2. Include: subject details, art style (e.g. digital art, concept art, anime, "
    "photorealistic), lighting, colors, composition, and atmosphere\n"
    "3. Add quality boosters like masterpiece, best quality, highly detailed\n"
    "4. Keep it under 100 words\n"
    "5. Output ONLY the prompt — no explanations, no markdown"
)


async def _enhance_prompt(raw: str) -> str:
    """Use the chat provider to expand a brief idea into a detailed SD prompt."""
    tp = get_provider()
    if not tp:
        return raw
    msgs = [
        ChatMessage("system", ENHANCE_SYSTEM),
        ChatMessage("user", raw),
    ]
    try:
        result = ""
        async for chunk in tp.chat_stream(msgs, temperature=0.7, max_tokens=256):
            if chunk.startswith("\n[ERROR]"):
                return raw
            result += chunk
        return result.strip() or raw
    except Exception:
        return raw


async def _generate_image(prompt: str, **kwargs) -> dict:
    """Internal helper: enhance prompt, generate, save, return {url, filename, prompt}."""
    # Apply default prompts from config
    if config.image_default_prompt:
        kwargs.setdefault("default_prompt", config.image_default_prompt)
    if config.image_default_negative_prompt:
        kwargs.setdefault("negative_prompt", config.image_default_negative_prompt)

    # Enhance the raw prompt first
    enhanced = await _enhance_prompt(prompt)
    p = get_image_provider()
    try:
        img_bytes = await p.generate(enhanced, **kwargs)
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except TimeoutError as e:
        raise HTTPException(504, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    h = hash_md5(img_bytes).hexdigest()[:8]
    filename = f"gen_{ts}_{h}.png"
    (GENERATED_DIR / filename).write_bytes(img_bytes)

    url = f"/generated/{filename}"
    return {"url": url, "filename": filename, "prompt": prompt, "enhanced_prompt": enhanced}


@app.post("/api/chat")
async def chat(body: ChatRequest):
    # Route /draw commands to image generation (returns SSE with image event)
    if body.message.startswith("/draw "):
        prompt = body.message[6:].strip()
        if not prompt:
            raise HTTPException(400, "Empty draw prompt")
        result = await _generate_image(prompt)
        async def draw_event_stream():
            yield f"data: {json.dumps({'image': result['url'], 'prompt': result['prompt'], 'enhanced_prompt': result.get('enhanced_prompt', '')})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(draw_event_stream(), media_type="text/event-stream")

    p = get_provider()
    if not p:
        raise HTTPException(500, "No provider configured")

    if not sessions.current:
        raise HTTPException(400, "No active session")

    # Internal flag: re-stream from existing context (used after edit)
    is_reply = body.message == "/_stream_context"
    if not is_reply:
        # Save user message
        sessions.current.add_message("user", body.message)
        sessions.save_current()

    # Build context with character card
    context = sessions.get_context_messages(char_mgr.get_system_prompt_extra())

    async def event_stream():
        full_response = ""
        try:
            async for chunk in p.chat_stream(
                context,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            ):
                if chunk.startswith("\n[ERROR]"):
                    yield f"data: {json.dumps({'error': chunk[7:]})}\n\n"
                    return
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"

            # Save assistant response
            if full_response and sessions.current:
                sessions.current.add_message("assistant", full_response)
                sessions.save_current()

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/draw")
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
    return await _generate_image(prompt, **kwargs)


# ── Static Files ───────────────────────────────────────────────────────────

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

# Serve generated images — MUST be before the catch-all mount
GENERATED_DIR.mkdir(exist_ok=True)
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")

@app.get("/")
async def serve_index():
    return FileResponse(static_dir / "index.html")

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


# ── Entry Point ────────────────────────────────────────────────────────────

def run():
    import uvicorn
    print(f"🌐 Local AI Chat Web UI")
    print(f"   Open http://localhost:8000 in your browser")
    print(f"   Press Ctrl+C to stop")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    run()
