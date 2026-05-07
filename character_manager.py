"""Character card management for role-playing."""

import json
from pathlib import Path
from typing import Optional

CHARACTERS_DIR = Path(__file__).parent / "characters"


class CharacterCard:
    def __init__(self, data: dict):
        self.name = data.get("name", "未知角色")
        self.description = data.get("description", "")
        self.personality = data.get("personality", "")
        self.backstory = data.get("backstory", "")
        self.speaking_style = data.get("speaking_style", "")
        self.greeting = data.get("greeting", "")
        self.avatar = data.get("avatar", "🎭")

    @classmethod
    def load(cls, path: Path) -> Optional["CharacterCard"]:
        try:
            with open(path, encoding="utf-8") as f:
                return cls(json.load(f))
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "personality": self.personality,
            "backstory": self.backstory,
            "speaking_style": self.speaking_style,
            "greeting": self.greeting,
            "avatar": self.avatar,
        }

    def build_system_prompt(self) -> str:
        """Build the system prompt injection for this character."""
        lines = []
        lines.append("【当前角色设定】")
        lines.append("请完全以该角色的身份进行对话，不要跳出角色设定。\n")
        lines.append(f"{self.avatar} 角色：{self.name}")
        if self.description:
            lines.append(f"📝 简介：{self.description}")
        if self.personality:
            lines.append(f"🧠 性格：{self.personality}")
        if self.backstory:
            lines.append(f"📖 背景：{self.backstory}")
        if self.speaking_style:
            lines.append(f"💬 说话风格：{self.speaking_style}")
        lines.append(f"\n请以{self.name}的身份与用户对话，保持角色一致性。")
        lines.append("【角色设定结束】")
        return "\n".join(lines)

    def display_card(self) -> str:
        """Format character card for display."""
        lines = []
        lines.append(f"{self.avatar} [bold cyan]{self.name}[/]")
        if self.description:
            lines.append(f"  [dim]简介：[/]{self.description}")
        if self.personality:
            lines.append(f"  [dim]性格：[/]{self.personality}")
        if self.backstory:
            lines.append(f"  [dim]背景：[/]{self.backstory}")
        if self.speaking_style:
            lines.append(f"  [dim]风格：[/]{self.speaking_style}")
        if self.greeting:
            lines.append(f"  [dim]开场白：[/][italic]{self.greeting}[/]")
        return "\n".join(lines)


class CharacterManager:
    def __init__(self):
        self.characters: dict[str, CharacterCard] = {}
        self.active_name: Optional[str] = None
        self._load_characters()

    def _load_characters(self):
        CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        for f in sorted(CHARACTERS_DIR.iterdir()):
            if f.suffix == ".json":
                card = CharacterCard.load(f)
                if card:
                    self.characters[card.name] = card

    def reload(self):
        self.characters.clear()
        self._load_characters()

    @property
    def active(self) -> Optional[CharacterCard]:
        if self.active_name and self.active_name in self.characters:
            return self.characters[self.active_name]
        return None

    def set_active(self, name: str) -> bool:
        if name in self.characters:
            self.active_name = name
            return True
        return False

    def clear_active(self):
        self.active_name = None

    def get_system_prompt_extra(self) -> str:
        card = self.active
        if card:
            return card.build_system_prompt()
        return ""

    def get_greeting(self) -> str:
        card = self.active
        if card and card.greeting:
            return card.greeting
        return ""

    def list_characters(self) -> list[tuple[str, str]]:
        """Return list of (name, description) tuples."""
        return [(c.name, c.description) for c in self.characters.values()]

    def add_character(self, data: dict) -> CharacterCard:
        """Create a new character card and save to file."""
        card = CharacterCard(data)
        self.characters[card.name] = card
        self._save_card(card)
        return card

    def update_character(self, name: str, data: dict) -> Optional[CharacterCard]:
        """Update an existing character card."""
        if name not in self.characters:
            return None
        # Remove old file
        old_path = CHARACTERS_DIR / f"{name}.json"
        old_path.unlink(missing_ok=True)
        # If name changed, remove old entry
        new_name = data.get("name", name)
        if new_name != name and name in self.characters:
            del self.characters[name]
        card = CharacterCard(data)
        self.characters[card.name] = card
        self._save_card(card)
        return card

    def delete_character(self, name: str) -> bool:
        """Delete a character card."""
        if name not in self.characters:
            return False
        path = CHARACTERS_DIR / f"{name}.json"
        path.unlink(missing_ok=True)
        # Also try alternate filename
        for f in CHARACTERS_DIR.iterdir():
            if f.suffix == ".json":
                try:
                    with open(f, encoding="utf-8") as fh:
                        if json.load(fh).get("name") == name:
                            f.unlink(missing_ok=True)
                except (json.JSONDecodeError, OSError):
                    pass
        del self.characters[name]
        if self.active_name == name:
            self.active_name = None
        return True

    def _save_card(self, card: CharacterCard):
        """Save a character card to a JSON file."""
        CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        path = CHARACTERS_DIR / f"{card.name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card.to_dict(), f, indent=2, ensure_ascii=False)
