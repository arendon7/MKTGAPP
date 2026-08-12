from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def projects(self) -> Path:
        return self.home / "Projects"

    @property
    def app_factory(self) -> Path:
        return self.home / "App Factory"

    @property
    def state(self) -> Path:
        return self.home / "State"


def default_paths() -> Paths:
    configured = os.environ.get("BINARIO_IA_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / "Documents" / "Binario IA"
    return Paths(root)
