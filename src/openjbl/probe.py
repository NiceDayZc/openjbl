"""Non-mutating capability probe across JBL protocol generations."""

from __future__ import annotations

import asyncio
from typing import Any

from . import protocol
from .connection import COMMAND_TIMEOUT_SECONDS, ConnectionManager, Link, LinkError
from .models import find_models
from .protocol import describe_frame, hex_bytes

PROBE_REQUESTS = [
    ("firmware", protocol.request_firmware_version),
    ("eq_mode", protocol.request_eq_mode),
    ("simple_eq", protocol.request_simple_eq),
    ("advanced_eq", protocol.request_advanced_eq),
    ("protocol4_eq", lambda: protocol.p4_request_eq()[0]),
]


def detect_eq_path(probes: dict[str, dict[str, Any]]) -> str:
    if probes["advanced_eq"]["status"] == "supported-response":
        return "legacy-parametric-or-advanced"
    if probes["protocol4_eq"]["status"] == "supported-response":
        return "protocol4"
    if probes["simple_eq"]["status"] == "supported-response":
        return "legacy-simple"
    return "no-supported-eq-response"


async def probe_link(link: Link, *, pid: str | None = None, timeout: float = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Probe over an already-open link, leaving it open for the caller.

    A device that answers "unsupported" and a link that has died look identical
    if you only count missing replies, so a dropped link aborts the sequence
    rather than being reported as a missing capability.
    """
    result: dict[str, Any] = {
        "address": link.address,
        "model": find_models(pid)[0] if pid and find_models(pid) else None,
        "services": await link.services(),
    }
    probes: dict[str, dict[str, Any]] = {}
    for name, build in PROBE_REQUESTS:
        request = build()
        entry: dict[str, Any] = {"tx": hex_bytes(request)}
        try:
            transaction = await link.transact(request, timeout)
        except (asyncio.TimeoutError, TimeoutError):
            entry["status"] = "timeout/no-response"
        except LinkError as exc:
            entry["status"] = "link-lost"
            entry["error"] = str(exc)
            probes[name] = entry
            result["probes"] = probes
            result["detected_eq_path"] = "link-lost"
            raise LinkError(f"link dropped during the {name} probe; capabilities are unknown ({exc})") from exc
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        else:
            entry["rx"] = [hex_bytes(reply) for reply in transaction.replies]
            decoded: list[dict[str, Any]] = []
            for reply in transaction.replies:
                try:
                    decoded.append(describe_frame(reply))
                except ValueError as exc:
                    decoded.append({"raw": hex_bytes(reply), "decode_error": str(exc)})
            entry["decoded"] = decoded
            entry["attempts"] = transaction.attempts
            entry["status"] = (
                "unsupported"
                if any(item.get("command") == protocol.DEV_ERROR for item in decoded)
                else "supported-response"
            )
        probes[name] = entry
        await asyncio.sleep(0.15)
    result["probes"] = probes
    result["detected_eq_path"] = detect_eq_path(probes)
    return result


async def probe_ble(
    address: str,
    *,
    pid: str | None = None,
    service_uuid: str,
    rx_uuid: str,
    tx_uuid: str,
    timeout: float = COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe end to end for callers that own no link of their own."""
    manager = ConnectionManager(service_uuid=service_uuid, rx_uuid=rx_uuid, tx_uuid=tx_uuid)
    link = await manager.acquire(address)
    try:
        return await probe_link(link, pid=pid, timeout=timeout)
    finally:
        await manager.release(address)
