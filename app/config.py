"""Configuration is read at application creation, with no embedded secrets."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_path: Path
    ollama_enabled: bool = False
    ollama_model: str = "llama3.2:1b"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("STUDENT_DB_PATH", str(PROJECT_ROOT / "data" / "students.db"))).expanduser().resolve(),
            ollama_enabled=os.getenv("OLLAMA_ENABLED", "0").lower() in {"1", "true", "yes"},
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:1b"),
        )
