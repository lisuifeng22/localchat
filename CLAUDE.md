# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local AI Chat — a dual-interface (terminal + web) chat client supporting OpenAI-compatible APIs and Anthropic Claude. Features include session management, character card role-playing, and Stable Diffusion image generation.

## Commands

```bash
# Dependencies (pip, no virtualenv required)
pip install -r requirements.txt

# Run terminal UI
python main.py

# Run web UI (FastAPI, http://localhost:8000)
python web/server.py

# Config lives in config.json (auto-created, gitignored)
```

No build/lint/test setup exists. The project is a single-developer local tool.

## Architecture

### Entry Points
- **`main.py`** — Rich terminal client using `prompt_toolkit` for input and `rich` for rendering. Event loop with `asyncio`. Commands start with `/`.
- **`web/server.py`** — FastAPI server serving a single-page HTML frontend at `/`. SSE streaming for chat responses. Shares same modules via `sys.path` manipulation.

### Core Modules
- **`config.py`** — `Config` class reads/writes `config.json`. Deep-merges saved values with `DEFAULT_CONFIG`. Properties for provider config, image config, UI settings.
- **`session_manager.py`** — `Session` (list of `ChatMessage` + metadata) and `SessionManager` (multi-session, per-character isolation in `sessions/char_X/`). Sessions are JSON files.
- **`character_manager.py`** — `CharacterCard` (name, personality, backstory, greeting, etc.) and `CharacterManager`. Cards are JSON files in `characters/`. `build_system_prompt()` generates a role-playing system prompt.

### Provider Pattern (`providers/`)
- **`base.py`** — `ChatMessage` (role + content), `Provider` abstract class defining `chat_stream()` and `list_models()`.
- **`openai.py`** — `OpenAIProvider`. Works with any OpenAI-compatible API (DeepSeek, OpenRouter, etc.). SSE stream parsing from `/chat/completions`.
- **`anthropic.py`** — `AnthropicProvider`. Strips system messages into the Anthropic `system` parameter. SSE stream parsing from `/messages`.
- **`image.py`** — `SDWebUIProvider`. Sends txt2img requests to AUTOMATIC1111's API at `/sdapi/v1/txt2img`. Supports default prompt merging.

### Web Frontend (`web/static/index.html`)
- Vanilla JS single-page app (no framework). SSE via `ReadableStream` reader.
- Features: chat, draw, settings, character management (CRUD + import/export), message editing and regeneration.

### Data Flow
1. User input → saved to `Session.messages` as `ChatMessage`
2. `SessionManager.get_context_messages()` builds full context (character system prompt + session system prompt + history)
3. Provider's `chat_stream()` sends to API, yields text chunks
4. Response appended to session and saved

### Key Design Details
- Sessions are per-character isolated: `sessions/default/` vs `sessions/char_X/`
- Image generation defaults (positive/negative prompt) are stored in `image.sd_webui` section and merged via `SDWebUIProvider.generate()`
- `/draw` commands are routed to image generation in both terminal and web UI; the chat provider enhances the prompt before sending to SD
- Message edit truncates all subsequent messages (`del s.messages[idx + 1:]`), then re-streams from the new context
- Regenerate removes the last assistant message and re-streams
- Config example template at `config.example.json` (safe for commit)
