"""Privacy-aware JSONL audit records for device mutations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import default_state_dir


def target_fingerprint(address: str) -> str:
    return hashlib.sha256(address.strip().casefold().encode()).hexdigest()[:16]


def append_audit(
    action: str,
    *,
    address: str,
    pid: str | None = None,
    applied: bool,
    details: dict[str, Any] | None = None,
    path: Path | None = None,
) -> Path:
    target = path or default_state_dir() / "audit.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "target": target_fingerprint(address),
        "pid": pid,
        "applied": applied,
        "details": details or {},
    }
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return target
