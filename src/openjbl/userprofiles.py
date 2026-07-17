"""Sound profiles the user creates and keeps, stored next to the config.

A saved profile is a seven-point tonal curve, not one speaker's band values, so
it survives being loaded on a different model -- the same reason the built-in
profiles are stored that way.

Whether a saved curve needs the extended encoder, and whether it needs the
extended-gain confirmation, are both derived from the gains themselves rather
than trusted from the file: a hand-edited profiles.json must not be able to talk
its way past the confirmation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import default_state_dir
from .presets import STANDARD_MAX_BOOST_DB, SoundProfile

STORE_VERSION = 1
MAX_ABS_GAIN_DB = 24.0
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ProfileStoreError(RuntimeError):
    """The profile store could not be read or written."""


def user_profiles_path(path: Path | None = None) -> Path:
    return path or default_state_dir() / "profiles.json"


def slugify(name: str) -> str:
    """A stable key for a saved profile.

    The prefix keeps user keys in their own namespace so one can never shadow a
    built-in, whatever the user calls it.
    """
    slug = _SLUG_RE.sub("-", name.strip().casefold()).strip("-")
    if not slug:
        raise ValueError("give the profile a name with at least one letter or digit")
    return f"user-{slug}"


def needs_extended_encoder(gains: Sequence[float]) -> bool:
    """Whether the curve leaves the range every model's own UI offers."""
    return any(abs(gain) > STANDARD_MAX_BOOST_DB for gain in gains)


def _validate(name: str, gains: Sequence[float]) -> tuple[str, tuple[float, ...]]:
    if len(gains) != 7:
        raise ValueError(f"a profile is a seven-point curve; got {len(gains)}")
    values = tuple(float(gain) for gain in gains)
    for gain in values:
        if gain != gain or gain in (float("inf"), float("-inf")):  # NaN or infinity
            raise ValueError("gains must be real numbers")
        if abs(gain) > MAX_ABS_GAIN_DB:
            raise ValueError(f"gain {gain:g} dB is outside the protocol's +/-{MAX_ABS_GAIN_DB:g} dB bound")
    return slugify(name), values


def _to_profile(row: dict[str, Any]) -> SoundProfile:
    gains = tuple(float(gain) for gain in row["gains"])
    return SoundProfile(
        key=str(row["key"]),
        name=str(row["name"]),
        description=str(row.get("description") or "Saved profile"),
        gains=gains,  # type: ignore[arg-type]
        tags=("user",),
        # Recomputed, never read from the file: the flag decides which encoder
        # runs and whether a write must be confirmed.
        dangerous=needs_extended_encoder(gains),
    )


def load_user_profiles(path: Path | None = None) -> list[SoundProfile]:
    """Every saved profile, or an empty list if none have been saved yet.

    A corrupt or unreadable store raises rather than silently returning nothing:
    quietly losing someone's saved profiles is worse than saying so.
    """
    target = user_profiles_path(path)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileStoreError(f"cannot read {target}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        raise ProfileStoreError(f"{target} is not a profile store")
    profiles = []
    for row in data["profiles"]:
        try:
            profiles.append(_to_profile(row))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProfileStoreError(f"{target} contains an unusable profile: {exc}") from exc
    return profiles


def _write(profiles: Sequence[SoundProfile], path: Path | None = None) -> Path:
    target = user_profiles_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STORE_VERSION,
        "profiles": [
            {
                "key": profile.key,
                "name": profile.name,
                "description": profile.description,
                "gains": list(profile.gains),
            }
            for profile in profiles
        ],
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def save_user_profile(
    name: str,
    gains: Sequence[float],
    *,
    description: str = "",
    path: Path | None = None,
    overwrite: bool = False,
) -> SoundProfile:
    """Save a curve under `name`, replacing an existing one only if asked."""
    key, values = _validate(name, gains)
    existing = load_user_profiles(path)
    if any(profile.key == key for profile in existing) and not overwrite:
        raise ValueError(f"a saved profile named {name!r} already exists; pass overwrite to replace it")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    profile = SoundProfile(
        key=key,
        name=name.strip(),
        description=description.strip() or f"Saved {stamp}",
        gains=values,  # type: ignore[arg-type]
        tags=("user",),
        dangerous=needs_extended_encoder(values),
    )
    kept = [item for item in existing if item.key != key]
    _write([*kept, profile], path)
    return profile


def delete_user_profile(key: str, path: Path | None = None) -> bool:
    """Remove a saved profile. Returns False if there was nothing to remove."""
    existing = load_user_profiles(path)
    kept = [profile for profile in existing if profile.key != key]
    if len(kept) == len(existing):
        return False
    _write(kept, path)
    return True


def user_profile_options(path: Path | None = None) -> list[tuple[str, str]]:
    return [(profile.name, profile.key) for profile in load_user_profiles(path)]
