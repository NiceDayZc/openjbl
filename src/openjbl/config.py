"""Persistent, non-secret user configuration."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .transport import RX_UUID, SERVICE_UUID, TX_UUID


def default_state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "openjbl") if base else (Path.cwd() / ".openjbl")


@dataclass
class Settings:
    last_address: str = ""
    last_pid: str = "20e3"
    service_uuid: str = SERVICE_UUID
    rx_uuid: str = RX_UUID
    tx_uuid: str = TX_UUID
    timeout: float = 3.0
    scan_seconds: float = 8.0
    # Check for updates, but never install one behind the user's back. Installing
    # unpinned code from PyPI at launch would make a single compromise of one
    # account into code execution on every machine running this, and pip would be
    # rewriting site-packages under a process that is about to drive a radio and
    # write EQ to hardware. `openjbl update` installs, deliberately, when asked.
    auto_update: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target = path or default_state_dir() / "config.json"
        if not target.exists():
            return cls()
        data: Any = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("configuration root must be an object")
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def save(self, path: Path | None = None) -> Path:
        target = path or default_state_dir() / "config.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        return target
