"""Non-mutating capability probe across JBL protocol generations."""

from __future__ import annotations

import asyncio
from typing import Any

from . import protocol
from .models import find_models
from .protocol import describe_frame, hex_bytes
from .transport import BleTransport


async def probe_ble(
    address: str,
    *,
    pid: str | None = None,
    service_uuid: str,
    rx_uuid: str,
    tx_uuid: str,
    timeout: float = 2.5,
) -> dict[str, Any]:
    result: dict[str, Any] = {"address": address, "model": find_models(pid)[0] if pid and find_models(pid) else None}
    requests = [
        ("firmware", protocol.request_firmware_version()),
        ("eq_mode", protocol.request_eq_mode()),
        ("simple_eq", protocol.request_simple_eq()),
        ("advanced_eq", protocol.request_advanced_eq()),
        ("protocol4_eq", protocol.p4_request_eq()[0]),
    ]
    async with BleTransport(address, service_uuid=service_uuid, rx_uuid=rx_uuid, tx_uuid=tx_uuid) as transport:
        result["services"] = await transport.services()
        probes = {}
        for name, request in requests:
            entry: dict[str, Any] = {"tx": hex_bytes(request)}
            try:
                replies = await transport.transact(request, timeout)
                entry["rx"] = [hex_bytes(reply) for reply in replies]
                decoded = []
                for reply in replies:
                    try:
                        decoded.append(describe_frame(reply))
                    except ValueError as exc:
                        decoded.append({"raw": hex_bytes(reply), "decode_error": str(exc)})
                entry["decoded"] = decoded
                if any(item.get("command") == 0xEE for item in decoded):
                    entry["status"] = "unsupported"
                else:
                    entry["status"] = "supported-response"
            except (asyncio.TimeoutError, TimeoutError):
                entry["status"] = "timeout/no-response"
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            probes[name] = entry
            await asyncio.sleep(0.15)
        result["probes"] = probes
    advanced = result["probes"]["advanced_eq"]
    p4 = result["probes"]["protocol4_eq"]
    simple = result["probes"]["simple_eq"]
    if advanced["status"] == "supported-response":
        result["detected_eq_path"] = "legacy-parametric-or-advanced"
    elif p4["status"] == "supported-response":
        result["detected_eq_path"] = "protocol4"
    elif simple["status"] == "supported-response":
        result["detected_eq_path"] = "legacy-simple"
    else:
        result["detected_eq_path"] = "no-supported-eq-response"
    return result
