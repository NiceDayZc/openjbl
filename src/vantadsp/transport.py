"""BLE and Bluetooth-serial transports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .discovery import detect_jbl_device, windows_paired_jbl

SERVICE_UUID = "65786365-6c70-6f69-6e74-2e636f6d0000"
RX_UUID = "65786365-6c70-6f69-6e74-2e636f6d0001"
TX_UUID = "65786365-6c70-6f69-6e74-2e636f6d0002"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"


async def scan_ble(timeout: float = 8.0) -> list[dict[str, Any]]:
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    rows = []
    for address, pair in found.items():
        device, advertisement = pair
        row = {
            "name": device.name or advertisement.local_name or "",
            "address": address,
            "rssi": advertisement.rssi,
            "service_uuids": list(advertisement.service_uuids or []),
            "service_data": {str(k): bytes(v).hex() for k, v in advertisement.service_data.items()},
            "manufacturer_data": {str(k): bytes(v).hex() for k, v in advertisement.manufacturer_data.items()},
        }
        row["jbl_detection"] = detect_jbl_device(row)
        rows.append(row)
    known_addresses = {str(row["address"]).replace(":", "").casefold() for row in rows}
    for paired in await windows_paired_jbl():
        normalized = str(paired["address"]).replace(":", "").casefold()
        if normalized not in known_addresses:
            rows.append(paired)
            known_addresses.add(normalized)
    return sorted(
        rows,
        key=lambda item: (
            not bool(item["jbl_detection"]["pid"]),
            not bool(item["jbl_detection"]["is_jbl"]),
            -int(item["rssi"] if item["rssi"] is not None else -999),
        ),
    )


class BleTransport:
    def __init__(
        self,
        address: str,
        *,
        service_uuid: str = SERVICE_UUID,
        rx_uuid: str = RX_UUID,
        tx_uuid: str = TX_UUID,
    ):
        self.address = address
        self.service_uuid = service_uuid.lower()
        self.rx_uuid = rx_uuid.lower()
        self.tx_uuid = tx_uuid.lower()
        self.client: Any = None

    async def __aenter__(self) -> BleTransport:
        from bleak import BleakClient

        self.client = BleakClient(self.address)
        await self.client.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.client is not None:
            await self.client.disconnect()

    def _connected_client(self) -> Any:
        if self.client is None:
            raise RuntimeError("transport is not connected; use 'async with BleTransport(...)'")
        return self.client

    async def services(self) -> list[dict[str, Any]]:
        client = self._connected_client()
        rows = []
        for service in client.services:
            rows.append(
                {
                    "uuid": str(service.uuid),
                    "description": service.description,
                    "characteristics": [
                        {"uuid": str(char.uuid), "description": char.description, "properties": list(char.properties)}
                        for char in service.characteristics
                    ],
                }
            )
        return rows

    async def start_notify(self, callback: Callable[[bytes], None]) -> None:
        client = self._connected_client()

        def wrapped(_: object, data: bytearray) -> None:
            callback(bytes(data))

        await client.start_notify(self.rx_uuid, wrapped)

    async def stop_notify(self) -> None:
        client = self._connected_client()
        await client.stop_notify(self.rx_uuid)

    async def write(self, data: bytes) -> None:
        client = self._connected_client()
        characteristic = client.services.get_characteristic(self.tx_uuid)
        if characteristic is None:
            raise RuntimeError(f"TX characteristic {self.tx_uuid} not found; run 'services' and override --tx")
        response = "write" in characteristic.properties
        await client.write_gatt_char(characteristic, data, response=response)

    async def transact(self, data: bytes, timeout: float = 2.0) -> list[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        await self.start_notify(queue.put_nowait)
        try:
            await self.write(data)
            replies = [await asyncio.wait_for(queue.get(), timeout)]
            await asyncio.sleep(0.12)
            while not queue.empty():
                replies.append(queue.get_nowait())
            return replies
        finally:
            await self.stop_notify()


@dataclass
class SerialTransport:
    """Classic SPP through a Windows Bluetooth COM port."""

    port: str
    baudrate: int = 115200
    timeout: float = 2.0

    def transact(self, data: bytes) -> bytes:
        import serial

        with serial.Serial(self.port, self.baudrate, timeout=self.timeout, write_timeout=self.timeout) as stream:
            stream.reset_input_buffer()
            stream.write(data)
            stream.flush()
            return stream.read(4096)
