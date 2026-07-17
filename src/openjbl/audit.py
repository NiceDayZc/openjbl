"""JSONL audit records for device mutations.

The target is recorded as a salted pseudonym. Hashing the address alone does not
hide it: a Bluetooth address is 48 bits, the vendor OUI is public, and the
remaining 24 bits fall to a brute-force search in about two seconds of ordinary
Python. The per-install salt makes the log meaningless to anyone who does not
also have the salt file, which is what makes it safe to paste into a bug report.

It is not anonymisation. Anyone holding the whole state directory can still link
records to a device -- config.json keeps the last address in plaintext by design,
because the tool has to reconnect to it.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import default_state_dir


def _salt(path: Path | None = None) -> bytes:
    """A random per-install salt, created once and kept next to the log."""
    target = path or default_state_dir() / "audit-salt"
    if target.exists():
        return target.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(32)
    target.write_bytes(salt)
    return salt


def target_fingerprint(address: str, *, salt_path: Path | None = None) -> str:
    """A stable pseudonym for an address, scoped to this installation."""
    return hashlib.sha256(_salt(salt_path) + address.strip().casefold().encode()).hexdigest()[:16]


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
