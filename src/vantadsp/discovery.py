"""Model-aware JBL detection from BLE advertisement metadata."""

from __future__ import annotations

import re
import sys
from typing import Any

from .models import all_models

HARMAN_COMPANY_IDS = frozenset({87, 3787})
HARMAN_SERVICE_IDS = frozenset({"dffd", "fddf", "fc69", "0ecb"})
_DERIVED_SERVICE_RE = re.compile(r"657863656c706f696e742e04ff([0-9a-f]{4})([0-9a-f]{2})")
_WINDOWS_JBL_PID_RE = re.compile(r"VID&[0-9a-f]*0ecb_PID&([0-9a-f]{4})", re.IGNORECASE)
_WINDOWS_ADDRESS_RES = (
    re.compile(r"BTHENUM[#\\]Dev_([0-9a-f]{12})", re.IGNORECASE),
    re.compile(r"&0&([0-9a-f]{12})_C", re.IGNORECASE),
)


def _known_models() -> dict[str, dict[str, Any]]:
    return {str(model.get("pid", "")).lower(): model for model in all_models()}


def _hex_bytes(value: object) -> bytes:
    try:
        return bytes.fromhex(str(value))
    except ValueError:
        return b""


def _little_endian_pid(data: bytes, offset: int = 0) -> str | None:
    if len(data) < offset + 2:
        return None
    return data[offset : offset + 2][::-1].hex()


def _short_service_id(uuid: object) -> str:
    compact = str(uuid).lower().replace("-", "")
    if len(compact) == 4:
        return compact
    if compact.startswith("0000") and compact.endswith("00001000800000805f9b34fb"):
        return compact[4:8]
    return ""


def _company_id(value: object) -> int | None:
    text = str(value)
    try:
        return int(text, 0)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return None


def _normalized_name(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _name_candidates(name: object, models: dict[str, dict[str, Any]]) -> list[str]:
    normalized = _normalized_name(name)
    if not normalized:
        return []
    exact = [pid for pid, model in models.items() if _normalized_name(model.get("deviceName")) == normalized]
    if exact:
        return exact
    # Windows may expose compact names such as "JBLCharge6"; normalization handles
    # spacing, while this fallback tolerates a short suffix added by firmware.
    return [
        pid
        for pid, model in models.items()
        if len(_normalized_name(model.get("deviceName"))) >= 6
        and _normalized_name(model.get("deviceName")) in normalized
    ]


def detect_jbl_device(advertisement: dict[str, Any]) -> dict[str, Any]:
    """Identify a catalogued JBL model without connecting to the device.

    PID-bearing service/manufacturer bytes outrank advertising-name matches. A
    name is accepted only when it maps to one PID, avoiding unsafe guesses for
    products that share a retail name across hardware revisions.
    """
    models = _known_models()
    candidates: list[tuple[int, str, str]] = []
    harman_signal = False

    for uuid in advertisement.get("service_uuids", []) or []:
        compact = str(uuid).lower().replace("-", "")
        short_id = _short_service_id(uuid)
        if short_id in HARMAN_SERVICE_IDS or compact.startswith("657863656c706f696e74"):
            harman_signal = True
        match = _DERIVED_SERVICE_RE.search(compact)
        if match:
            encoded = _hex_bytes(match.group(1))
            pid = _little_endian_pid(encoded)
            if pid in models:
                candidates.append((100, pid, "model-specific service UUID"))

    for uuid, encoded in (advertisement.get("service_data", {}) or {}).items():
        short_id = _short_service_id(uuid)
        if short_id not in HARMAN_SERVICE_IDS:
            continue
        harman_signal = True
        data = _hex_bytes(encoded)
        offset = 1 if short_id == "dffd" else 0
        pid = _little_endian_pid(data, offset)
        if pid in models:
            candidates.append((100, pid, f"{short_id.upper()} service data"))

    for company, encoded in (advertisement.get("manufacturer_data", {}) or {}).items():
        if _company_id(company) not in HARMAN_COMPANY_IDS:
            continue
        harman_signal = True
        data = _hex_bytes(encoded)
        for offset, score, reason in (
            (0, 100, "Harman company data"),
            (2, 95, "Harman TWS company data"),
        ):
            pid = _little_endian_pid(data, offset)
            if pid in models:
                candidates.append((score, pid, reason))

    name = advertisement.get("name", "")
    name_matches = _name_candidates(name, models)
    if str(name).casefold().startswith(("jbl", "harman")):
        harman_signal = True
    if len(name_matches) == 1:
        candidates.append((75, name_matches[0], "unique advertising name"))

    if not candidates:
        return {
            "is_jbl": harman_signal,
            "pid": None,
            "model": None,
            "confidence": "unresolved" if harman_signal else "none",
            "reason": "Harman signature without a known PID" if harman_signal else "no JBL signature",
        }

    score, pid, reason = max(candidates, key=lambda item: item[0])
    model = models[pid]
    return {
        "is_jbl": True,
        "pid": pid,
        "model": str(model.get("deviceName") or "Unknown JBL"),
        "confidence": "high" if score >= 90 else "medium",
        "reason": reason,
    }


def _windows_address(device_id: str) -> str | None:
    for pattern in _WINDOWS_ADDRESS_RES:
        match = pattern.search(device_id)
        if match:
            raw = match.group(1).upper()
            return ":".join(raw[index : index + 2] for index in range(0, 12, 2))
    return None


def _windows_jbl_row(device_id: str, interface_name: str) -> dict[str, Any] | None:
    if "BTHENUM" not in device_id.upper():
        return None
    pid_match = _WINDOWS_JBL_PID_RE.search(device_id)
    address = _windows_address(device_id)
    if pid_match is None or address is None:
        return None
    pid = pid_match.group(1).lower()
    model = _known_models().get(pid)
    if model is None:
        return None
    model_name = str(model.get("deviceName") or interface_name or "Unknown JBL")
    return {
        "name": model_name,
        "address": address,
        "rssi": None,
        "paired": True,
        "service_uuids": [],
        "service_data": {},
        "manufacturer_data": {},
        "jbl_detection": {
            "is_jbl": True,
            "pid": pid,
            "model": model_name,
            "confidence": "high",
            "reason": "Windows paired-device metadata",
        },
    }


async def windows_paired_jbl() -> list[dict[str, Any]]:
    """Return deduplicated JBL devices registered in the Windows device store."""
    if sys.platform != "win32":
        return []
    try:
        from winrt.windows.devices.enumeration import DeviceInformation

        interfaces = await DeviceInformation.find_all_async()
    except (ImportError, OSError, RuntimeError, TypeError):
        return []

    found: dict[tuple[str, str], dict[str, Any]] = {}
    for interface in interfaces:
        row = _windows_jbl_row(str(interface.id), str(interface.name))
        if row is not None:
            found[(str(row["address"]), str(row["jbl_detection"]["pid"]))] = row
    return list(found.values())
