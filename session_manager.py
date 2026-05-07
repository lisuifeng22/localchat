"""Conversation session management with per-character isolation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import SESSIONS_DIR
from providers.base import ChatMessage


class Session:
    def __init__(self, name: str = "", system_prompt: str = "", character: str = ""):
        self.character = character
        self.name = name or self._default_name()
        self.system_prompt = system_prompt
        self.messages: list[ChatMessage] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    def _default_name(self) -> str:
        if self.character:
            return f"{self.character} {datetime.now().strftime('%m-%d %H:%M')}"
        return datetime.now().strftime("会话 %m-%d %H:%M")

    def add_message(self, role: str, content: str):
        self.messages.append(ChatMessage(role, content))
        self.updated_at = datetime.now().isoformat()

    def clear(self):
        self.messages.clear()
        self.updated_at = datetime.now().isoformat()

    def delete_message(self, index: int) -> bool:
        if 0 <= index < len(self.messages):
            self.messages.pop(index)
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "character": self.character,
            "system_prompt": self.system_prompt,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(
            name=d.get("name", ""),
            system_prompt=d.get("system_prompt", ""),
            character=d.get("character", ""),
        )
        s.messages = [ChatMessage.from_dict(m) for m in d.get("messages", [])]
        s.created_at = d.get("created_at", s.created_at)
        s.updated_at = d.get("updated_at", s.updated_at)
        return s

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def context_length(self) -> int:
        return sum(len(m.content) for m in self.messages)

    @property
    def filename(self) -> str:
        """Generate filename: {character}_{date}.json or {name}.json."""
        if self.character:
            ts = self.created_at[:19].replace(":", "-").replace("T", "_")
            safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.character)
            return f"{safe}_{ts}.json"
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.name)
        return f"{safe[:50]}.json"


class SessionManager:
    def __init__(self):
        self.sessions: list[Session] = []
        self.current_idx = 0
        self._character = ""
        self._load_sessions()

    @property
    def _sessions_dir(self) -> Path:
        """Character-isolated session directory."""
        if self._character:
            return SESSIONS_DIR / f"char_{self._character}"
        return SESSIONS_DIR / "default"

    @property
    def character(self) -> str:
        return self._character

    def _load_sessions(self):
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(self._sessions_dir.iterdir()):
            if f.suffix == ".json":
                try:
                    with open(f, encoding="utf-8") as fh:
                        s = Session.from_dict(json.load(fh))
                    # Patch old sessions (no character field) loaded in character mode
                    if self._character and not s.character:
                        s.character = self._character
                        if s.name.startswith("会话"):
                            s.name = s.name.replace("会话", self._character, 1)
                        # Delete old-format file — session will be saved with
                        # correct name/filename on next save_current, preventing
                        # duplicate session files on every character switch.
                        try:
                            f.unlink(missing_ok=True)
                        except OSError:
                            pass
                    self.sessions.append(s)
                except (json.JSONDecodeError, OSError):
                    pass

    def set_character(self, name: str):
        """Switch to a character's isolated session storage."""
        self.save_current()
        self._character = name
        self.sessions.clear()
        self.current_idx = 0
        self._load_sessions()
        if not self.sessions:
            self.new_session()
            self.save_current()

    def clear_character(self):
        """Return to default (no character) session storage."""
        if self._character:
            self.set_character("")

    def new_session(self, system_prompt: str = "") -> Session:
        s = Session(system_prompt=system_prompt, character=self._character)
        self.sessions.append(s)
        self.current_idx = len(self.sessions) - 1
        return s

    @property
    def current(self) -> Optional[Session]:
        if not self.sessions:
            return None
        return self.sessions[self.current_idx]

    def switch_to(self, index: int) -> Optional[Session]:
        if 0 <= index < len(self.sessions):
            self.current_idx = index
            return self.sessions[index]
        return None

    def delete_session(self, index: int) -> bool:
        if 0 <= index < len(self.sessions):
            path = self._sessions_dir / self.sessions[index].filename
            path.unlink(missing_ok=True)
            self.sessions.pop(index)
            if self.current_idx >= len(self.sessions):
                self.current_idx = max(0, len(self.sessions) - 1)
            return True
        return False

    def save_current(self):
        s = self.current
        if s is None:
            return
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        # Remove stale files for this session: either by (name+character) match
        # or by created_at match (handles old-format files patched in-memory).
        for f in self._sessions_dir.iterdir():
            if f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                same_id = (
                    data.get("name") == s.name and data.get("character") == s.character
                ) or (
                    data.get("created_at") == s.created_at
                )
                if same_id and f.name != s.filename:
                    f.unlink(missing_ok=True)
            except (json.JSONDecodeError, OSError):
                pass
        path = self._sessions_dir / s.filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(s.to_dict(), f, indent=2, ensure_ascii=False)

    def rename_current(self, name: str):
        if self.current:
            # Remove old file (name changed → filename may change)
            old_path = self._sessions_dir / self.current.filename
            old_path.unlink(missing_ok=True)
            self.current.name = name

    def get_context_messages(self, character_prompt: str = "") -> list[ChatMessage]:
        s = self.current
        if s is None:
            return []
        msgs = []
        if character_prompt:
            msgs.append(ChatMessage("system", character_prompt))
        if s.system_prompt:
            msgs.append(ChatMessage("system", s.system_prompt))
        msgs.extend(s.messages)
        return msgs
