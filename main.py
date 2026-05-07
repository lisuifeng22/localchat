#!/usr/bin/env python3
"""Local AI Chat Client - A beautiful terminal chat client for multiple AI providers."""

import asyncio
import sys
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich import box
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PtStyle
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from config import Config, GENERATED_DIR
from session_manager import SessionManager
from character_manager import CharacterManager
from providers.base import ChatMessage
from providers.openai import OpenAIProvider
from providers.anthropic import AnthropicProvider
from providers.image import SDWebUIProvider

# ── App State ──────────────────────────────────────────────────────────────

console = Console()
config = Config()
sessions = SessionManager()
char_mgr = CharacterManager()
provider: Optional[OpenAIProvider | AnthropicProvider] = None
image_provider: Optional[SDWebUIProvider] = None

CMD_HELP = """\
[bold yellow]Available Commands:[/]

  [green]/model <name>[/]     Switch model (e.g. /model gpt-4o)
  [green]/models[/]           List available models
  [green]/provider <type>[/]  Switch provider: openai / anthropic
  [green]/key <key>[/]        Set API key for current provider
  [green]/endpoint <url>[/]   Set API endpoint (OpenAI-compatible only)
  [green]/new[/]              New conversation
  [green]/list[/]             List all conversations
  [green]/switch <n>[/]       Switch to conversation #n
  [green]/rename <name>[/]    Rename current conversation
  [green]/delete <n>[/]       Delete conversation #n
  [green]/system <text>[/]    Set system prompt
  [green]/temp <n.n>[/]       Set temperature (0-2)
  [green]/draw <prompt>[/]    Generate image via Stable Diffusion\n
  [dim]    Flags: --w --h --steps --cfg --neg (e.g. /draw cat --w 1024 --h 768)[/]
  [green]/clear[/]            Clear current conversation
  [green]/export[/]           Export conversation to markdown file
  [green]/info[/]             Show current session info
  [green]/help[/]             Show this help
  [green]/exit[/]             Quit

[bold yellow]Character Cards:[/]
  [green]/characters[/]        List all available character cards
  [green]/character <name>[/]  Load a character card
  [green]/character_stop[/]    Remove active character (return to normal mode)
  [green]/character_show[/]    Show active character card details

[dim]Tip: Type your message and press Enter to send.[/]
"""

# ── Provider Helpers ───────────────────────────────────────────────────────

def create_provider(p_type: str = None) -> Optional[OpenAIProvider | AnthropicProvider]:
    global provider
    p_type = p_type or config.provider
    cfg = config.get_provider_config()
    try:
        if p_type == "anthropic":
            provider = AnthropicProvider(cfg)
        else:
            provider = OpenAIProvider(cfg)
        return provider
    except Exception as e:
        console.print(f"[red]Failed to create provider: {e}[/]")
        return None


def get_provider() -> Optional[OpenAIProvider | AnthropicProvider]:
    global provider
    if provider is None:
        create_provider()
    return provider

# ── Display Helpers ────────────────────────────────────────────────────────

def print_header():
    p = get_provider()
    model_name = p.model if p else "N/A"
    prov_name = config.provider.capitalize()
    info = Text()
    info.append(f" {prov_name} · {model_name}  ", style="bold cyan")
    info.append(f"| temp={config.temperature}  ", style="dim")
    s = sessions.current
    if sessions.character:
        info.append(f"  {char_mgr.active.avatar if char_mgr.active else ''} {sessions.character}", style="bold yellow")
    else:
        info.append(f"| 💬 普通模式", style="dim")
    if s:
        info.append(f"  |  {s.name}", style="italic green")
    info.append(f"  |  {len(sessions.sessions)} 会话", style="dim")
    console.print(Panel(info, box=box.ROUNDED, border_style="blue"))


def render_markdown(text: str) -> str:
    """Render markdown text, returns a rich renderable string."""
    return Markdown(text, code_theme=config.theme)


def format_message(role: str, content: str, stream: bool = False):
    if role == "user":
        console.print(Panel(
            Text(content, style="white"),
            title="[bold green]You[/]",
            box=box.MINIMAL,
            border_style="green",
            padding=(0, 1),
        ))
    else:
        md = Markdown(content, code_theme=config.theme)
        console.print(Panel(
            md,
            title="[bold blue]AI[/]",
            box=box.MINIMAL,
            border_style="blue",
            padding=(0, 1),
        ))


async def stream_response(messages: list[ChatMessage]) -> str:
    """Stream AI response and display it live. Returns full response text."""
    p = get_provider()
    if p is None:
        return "No provider configured."

    full = ""
    with Live(Spinner("dots", "Waiting for response..."), refresh_per_second=10, console=console) as live:
        async for chunk in p.chat_stream(
            messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ):
            if chunk.startswith("\n[ERROR]"):
                live.update(Text(chunk, style="red"))
                return full
            full += chunk
            md = Markdown(full + "▍", code_theme=config.theme)
            live.update(Panel(
                md,
                title="[bold blue]AI[/]",
                box=box.MINIMAL,
                border_style="blue",
                padding=(0, 1),
            ))

    # Final render without cursor
    if full:
        md = Markdown(full, code_theme=config.theme)
        console.print(Panel(
            md,
            title="[bold blue]AI[/]",
            box=box.MINIMAL,
            border_style="blue",
            padding=(0, 1),
        ))
    return full


# ── Commands ───────────────────────────────────────────────────────────────

async def handle_command(cmd: str) -> bool:
    """Handle a command. Returns False if should exit."""
    parts = cmd.strip().split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb == "/exit" or verb == "/quit":
        sessions.save_current()
        console.print("[yellow]Goodbye![/]")
        return False

    elif verb == "/help":
        console.print(CMD_HELP)

    elif verb == "/model":
        if not arg:
            console.print("[yellow]Usage: /model <name> (e.g. /model gpt-4o)[/]")
        else:
            p = get_provider()
            if p:
                p.model = arg
                config.get_provider_config()["model"] = arg
                config.save()
                console.print(f"[green]Model switched to: {arg}[/]")

    elif verb == "/models":
        p = get_provider()
        if p:
            with console.status("Fetching models..."):
                try:
                    models = await p.list_models()
                    table = Table(title="Available Models", box=box.SIMPLE)
                    table.add_column("#", style="dim")
                    table.add_column("Model", style="cyan")
                    for i, m in enumerate(models, 1):
                        table.add_row(str(i), m)
                    console.print(table)
                except Exception as e:
                    console.print(f"[red]Failed: {e}[/]")

    elif verb == "/provider":
        if arg in ("openai", "anthropic"):
            config.provider = arg
            create_provider(arg)
            console.print(f"[green]Switched to {arg} provider.[/]")
        else:
            console.print("[yellow]Usage: /provider openai | anthropic[/]")

    elif verb == "/key":
        if not arg:
            console.print("[yellow]Usage: /key <your-api-key>[/]")
        else:
            cfg = config.get_provider_config()
            cfg["api_key"] = arg
            config.save()
            create_provider(config.provider)
            console.print("[green]API key updated.[/]")

    elif verb == "/endpoint":
        if not arg:
            console.print("[yellow]Usage: /endpoint <url> (e.g. /endpoint https://api.deepseek.com/v1)[/]")
        else:
            cfg = config.get_provider_config()
            cfg["base_url"] = arg.rstrip("/")
            config.save()
            create_provider(config.provider)
            console.print(f"[green]Endpoint set to: {arg}[/]")

    elif verb == "/new":
        sessions.save_current()
        sessions.new_session()
        sessions.save_current()
        console.print("[green]Started a new conversation.[/]")

    elif verb == "/list":
        if not sessions.sessions:
            console.print("[yellow]No saved conversations.[/]")
        else:
            table = Table(box=box.SIMPLE)
            table.add_column("#", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Messages", justify="right")
            table.add_column("Model")
            for i, s in enumerate(sessions.sessions):
                marker = "→ " if i == sessions.current_idx else "  "
                table.add_row(
                    str(i), f"{marker}{s.name}", str(s.message_count), provider.model if provider else "N/A"
                )
            console.print(table)

    elif verb == "/switch":
        if arg.isdigit():
            idx = int(arg)
            if sessions.switch_to(idx):
                console.print(f"[green]Switched to: {sessions.current.name}[/]")
            else:
                console.print("[red]Invalid session number.[/]")
        else:
            console.print("[yellow]Usage: /switch <n>[/]")

    elif verb == "/delete":
        if arg.isdigit():
            sessions.delete_session(int(arg))
            console.print(f"[green]Deleted session #{arg}.[/]")
        else:
            console.print("[yellow]Usage: /delete <n>[/]")

    elif verb == "/rename":
        if arg:
            sessions.rename_current(arg)
            sessions.save_current()
            console.print(f"[green]Renamed to: {arg}[/]")
        else:
            console.print("[yellow]Usage: /rename <name>[/]")

    elif verb == "/system":
        arg = arg.strip()
        if not arg:
            # Show current system prompt
            s = sessions.current
            if s and s.system_prompt:
                console.print(f"[cyan]Current system prompt:[/]\n{s.system_prompt}")
            else:
                console.print("[yellow]No system prompt set.[/]")
        else:
            if sessions.current:
                sessions.current.system_prompt = arg
                sessions.save_current()
                console.print("[green]System prompt updated.[/]")

    elif verb == "/temp":
        try:
            val = float(arg)
            if 0 <= val <= 2:
                config.data["ui"]["temperature"] = val
                config.save()
                console.print(f"[green]Temperature set to: {val}[/]")
            else:
                console.print("[yellow]Temperature must be between 0 and 2.[/]")
        except ValueError:
            console.print("[yellow]Usage: /temp <n.n> (e.g. /temp 0.7)[/]")

    elif verb == "/draw":
        if not arg:
            console.print("[yellow]Usage: /draw <prompt> [--w 512] [--h 512] [--steps 20] [--cfg 7.0] [--neg \"bad quality\"][/]")
        else:
            # Parse optional flags from the argument string
            prompt = arg
            kwargs = {}
            import shlex
            tokens = shlex.split(arg)
            parsed_tokens = []
            i = 0
            while i < len(tokens):
                t = tokens[i]
                if t == "--w" and i + 1 < len(tokens):
                    kwargs["width"] = int(tokens[i + 1]); i += 2
                elif t == "--h" and i + 1 < len(tokens):
                    kwargs["height"] = int(tokens[i + 1]); i += 2
                elif t == "--steps" and i + 1 < len(tokens):
                    kwargs["steps"] = int(tokens[i + 1]); i += 2
                elif t == "--cfg" and i + 1 < len(tokens):
                    kwargs["cfg_scale"] = float(tokens[i + 1]); i += 2
                elif t == "--neg" and i + 1 < len(tokens):
                    kwargs["negative_prompt"] = tokens[i + 1]; i += 2
                else:
                    parsed_tokens.append(t); i += 1
            prompt = " ".join(parsed_tokens)

            global image_provider
            if image_provider is None:
                img_cfg = config.get_image_provider_config()
                image_provider = SDWebUIProvider(img_cfg)

            # Enhance prompt using the chat provider
            tp = get_provider()
            enhanced = prompt
            if tp:
                enhance_sys = (
                    "You are an expert at writing prompts for Stable Diffusion. "
                    "Rewrite the user's idea into a high-quality SD prompt following these rules:\n"
                    "1. Use SD-style keyword format (comma-separated, no full sentences)\n"
                    "2. Include: subject details, art style, lighting, colors, composition, atmosphere\n"
                    "3. Add quality boosters like masterpiece, best quality, highly detailed\n"
                    "4. Keep it under 100 words\n"
                    "5. Output ONLY the prompt — no explanations, no markdown"
                )
                msgs = [ChatMessage("system", enhance_sys), ChatMessage("user", prompt)]
                try:
                    enhanced = ""
                    async for chunk in tp.chat_stream(msgs, temperature=0.7, max_tokens=256):
                        if chunk.startswith("\n[ERROR]"):
                            enhanced = prompt
                            break
                        enhanced += chunk
                    enhanced = enhanced.strip() or prompt
                except Exception:
                    enhanced = prompt

            # Apply default prompts from config
            if config.image_default_prompt:
                kwargs.setdefault("default_prompt", config.image_default_prompt)
            if config.image_default_negative_prompt:
                kwargs.setdefault("negative_prompt", config.image_default_negative_prompt)

            with console.status(f"[cyan]Generating image...[/]", spinner="dots"):
                try:
                    img_bytes = await image_provider.generate(enhanced, **kwargs)
                except (ConnectionError, TimeoutError, RuntimeError) as e:
                    console.print(f"[red]Image generation failed: {e}[/]")
                    return True
                except Exception as e:
                    console.print(f"[red]Unexpected error: {e}[/]")
                    return True

            # Save to generated/
            from hashlib import md5 as hash_md5
            from datetime import datetime
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            h = hash_md5(img_bytes).hexdigest()[:8]
            filename = f"gen_{ts}_{h}.png"
            (GENERATED_DIR / filename).write_bytes(img_bytes)

            console.print(f"[green]Image saved:[/] {GENERATED_DIR / filename}")
            if enhanced != prompt:
                console.print(f"[dim]Enhanced prompt:[/] {enhanced}")
            kw_summary = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            if kw_summary:
                console.print(f"[dim]Parameters: {kw_summary}[/]")

            # Insert assistant message with markdown image reference
            if sessions.current:
                md_content = f"![generated image](generated/{filename})\n\nPrompt: {prompt}"
                if enhanced != prompt:
                    md_content += f"\n> ✨ {enhanced}"
                sessions.current.add_message("assistant", md_content)
                sessions.save_current()

    elif verb == "/clear":
        if sessions.current:
            sessions.current.clear()
            sessions.save_current()
            console.print("[green]Conversation cleared.[/]")

    elif verb == "/export":
        s = sessions.current
        if s and s.messages:
            path = f"chat_export_{sessions.current_idx}.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {s.name}\n\n")
                for m in s.messages:
                    f.write(f"## {m.role.capitalize()}\n\n{m.content}\n\n")
            console.print(f"[green]Exported to: {path}[/]")
        else:
            console.print("[yellow]No messages to export.[/]")

    elif verb == "/info":
        s = sessions.current
        if s:
            info = Table(box=box.SIMPLE)
            info.add_column("Property", style="cyan")
            info.add_column("Value")
            info.add_row("Mode", f"{sessions.character or '普通'}")
            info.add_row("Character Card", char_mgr.active.name if char_mgr.active else "(none)")
            info.add_row("Session Name", s.name)
            info.add_row("Total Sessions", str(len(sessions.sessions)))
            info.add_row("Messages", str(s.message_count))
            info.add_row("Context Length", f"{s.context_length} chars")
            info.add_row("System Prompt", s.system_prompt or "(none)")
            info.add_row("Created", s.created_at[:19])
            console.print(info)
        else:
            console.print("[yellow]No active session.[/]")

    # ── Character Card Commands ──────────────────────────────────────────

    elif verb == "/characters":
        chars = char_mgr.list_characters()
        if not chars:
            console.print("[yellow]No character cards found. Add .json files to the characters/ folder.[/]")
        else:
            table = Table(box=box.SIMPLE)
            table.add_column("#", style="dim")
            table.add_column("Character", style="cyan")
            table.add_column("Description")
            for i, (name, desc) in enumerate(chars):
                marker = "→ " if name == char_mgr.active_name else "  "
                table.add_row(str(i), f"{marker}{name}", desc)
            console.print(table)

    elif verb == "/character":
        if not arg:
            console.print("[yellow]Usage: /character <name>[/]")
        else:
            if arg in char_mgr.characters:
                # Switch session storage and character card
                sessions.set_character(arg)
                char_mgr.set_active(arg)
                card = char_mgr.active

                console.print(f"[green]角色卡已加载：[/]")
                console.print(Panel(card.display_card() if card else arg, title="角色卡", border_style="yellow"))

                # Show existing conversations for this character
                if sessions.sessions and len(sessions.sessions) > 1:
                    console.print(f"[dim]该角色有 {len(sessions.sessions)} 个会话记录[/]")
                    for i, s in enumerate(sessions.sessions):
                        marker = "→ " if i == sessions.current_idx else "  "
                        console.print(f"  {marker}[cyan]#{i}[/] {s.name} [dim]({s.message_count} 条消息)[/]")
                elif sessions.current and sessions.current.message_count > 0:
                    console.print(f"[dim]继续之前的对话 ({sessions.current.message_count} 条消息)[/]")
                else:
                    # New character, send greeting
                    greeting = char_mgr.get_greeting()
                    if greeting:
                        sessions.current.add_message("assistant", greeting)
                        sessions.save_current()
                        console.print(f"\n[bold yellow]{card.avatar if card else ''} {arg}:[/]")
                        console.print(Panel(
                            greeting,
                            title=f"[bold yellow]{card.avatar if card else ''} {arg}[/]",
                            box=box.MINIMAL,
                            border_style="yellow",
                            padding=(0, 1),
                        ))
            else:
                console.print(f"[red]Character '{arg}' not found. Use /characters to see available ones.[/]")

    elif verb == "/character_stop":
        if sessions.character:
            name = sessions.character
            sessions.clear_character()
            char_mgr.clear_active()
            console.print(f"[green]角色 '{name}' 已卸载，回到普通模式。[/]")
        else:
            console.print("[yellow]当前没有激活的角色。[/]")

    elif verb == "/character_show":
        card = char_mgr.active
        if card:
            console.print(Panel(card.display_card(), title="当前角色卡", border_style="yellow"))
        else:
            console.print("[yellow]No active character.[/]")

    else:
        console.print(f"[red]Unknown command: {verb}. Type /help for commands.[/]")

    return True

# ── Main Loop ──────────────────────────────────────────────────────────────

async def main():
    global provider

    # Setup prompt_toolkit
    history_path = config.CONFIG_DIR / ".chat_history"
    pt_session = PromptSession(
        history=FileHistory(str(history_path)),
        auto_suggest=AutoSuggestFromHistory(),
        enable_open_in_editor=True,
        style=PtStyle([
            ("prompt", "bold cyan"),
        ]),
    )

    # Ensure at least one session exists
    if not sessions.sessions:
        sessions.new_session()
        sessions.save_current()

    # Initialize provider
    create_provider()
    p = get_provider()

    # Welcome
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]🤖 Local AI Chat[/]\n"
        f"[dim]Provider: {config.provider.upper()} · Model: {p.model if p else 'N/A'}[/]\n"
        "Type [green]/help[/] for commands, [green]/exit[/] to quit.",
        border_style="cyan",
    ))

    # Show existing messages for current session
    s = sessions.current
    if s and s.messages:
        console.print(f"\n[dim]─── Resuming: {s.name} ───[/]")
        for m in s.messages:
            format_message(m.role, m.content)

    # Main interaction loop
    running = True
    while running:
        try:
            s = sessions.current
            session_name = f" [{s.name}]" if s else ""

            user_input = await pt_session.prompt_async(
                f"\n[bold green]You{session_name}[/] > ",
                multiline=False,
            )

            if not user_input.strip():
                continue

            # Handle commands
            if user_input.startswith("/"):
                running = await handle_command(user_input)
                continue

            # Save user message
            if s:
                s.add_message("user", user_input)
                sessions.save_current()

            # Get context with character card and stream response
            context = sessions.get_context_messages(char_mgr.get_system_prompt_extra())
            console.print(f"\n[bold green]You:[/]")
            console.print(Panel(
                Text(user_input, style="white"),
                box=box.MINIMAL,
                border_style="green",
                padding=(0, 1),
            ))

            response = await stream_response(context)

            if response and s:
                s.add_message("assistant", response)
                sessions.save_current()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type /exit to quit.[/]")
            continue
        except EOFError:
            running = False
            console.print("\n[yellow]Goodbye![/]")

    # Cleanup
    sessions.save_current()
    if provider and hasattr(provider, "close"):
        await provider.close()
    if image_provider and hasattr(image_provider, "close"):
        await image_provider.close()


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/]")
    except Exception as e:
        console.print_exception()
        console.print(f"[red]Fatal error: {e}[/]")


if __name__ == "__main__":
    run()
