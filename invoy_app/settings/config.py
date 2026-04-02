"""
Invoy App — persistent configuration.

Config is stored as JSON at ~/.invoy/config.json.
All fields have safe defaults so the app works on first launch.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

_CONFIG_DIR  = Path.home() / ".invoy"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    # Claude API key (set via Settings window; never committed to source)
    claude_api_key: str = ""

    # SQLite database path
    db_path: str = field(
        default_factory=lambda: str(Path.home() / ".invoy" / "activity.db")
    )

    # Screenshot output directory
    screenshot_dir: str = field(
        default_factory=lambda: str(Path.home() / ".invoy" / "screenshots")
    )

    # Capture interval in seconds (20 for live use)
    interval_seconds: float = 20.0

    # HuggingFace model ID — hardcoded to 2B for the app
    model_id: str = "Qwen/Qwen2-VL-2B-Instruct"

    # customtkinter appearance mode: "dark" | "light" | "System"
    appearance_mode: str = "dark"

    # Whether to show Windows toast notifications
    notifications_enabled: bool = True

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from disk, creating defaults if missing."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not _CONFIG_FILE.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Filter out unknown keys so old configs don't break new fields
            known = {k for k in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in data.items() if k in known})
        except Exception:
            return cls()

    def save(self) -> None:
        """Persist config to disk."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def ensure_dirs(self) -> None:
        """Create screenshot_dir and parent of db_path if they don't exist."""
        Path(self.screenshot_dir).mkdir(parents=True, exist_ok=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
