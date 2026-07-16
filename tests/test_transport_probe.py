from types import SimpleNamespace

import pytest

from vantadsp import probe, protocol, transport
from vantadsp.transport import BleTransport, scan_ble


class FakeClient:
    def __init__(self):
        self.writes = []
        self.callback = None
        characteristic = SimpleNamespace(properties=["write"], uuid="tx")
        self.services = SimpleNamespace(get_characteristic=lambda _uuid: characteristic)

    async def start_notify(self, _uuid, callback):
        self.callback = callback

    async def stop_notify(self, _uuid):
        self.callback = None

    async def write_gatt_char(self, characteristic, data, response):
        self.writes.append((characteristic.uuid, data, response))


@pytest.mark.asyncio
async def test_ble_transport_write_chooses_response():
    transport = BleTransport("fake")
    transport.client = FakeClient()
    await transport.write(b"abc")
    assert transport.client.writes == [("tx", b"abc", True)]


@pytest.mark.asyncio
async def test_scan_enriches_and_prioritizes_detected_jbl(monkeypatch):
    import bleak

    class FakeScanner:
        @staticmethod
        async def discover(*, timeout, return_adv):
            assert timeout == 0.01 and return_adv is True
            return {
                "mouse": (
                    SimpleNamespace(name="Wireless Mouse"),
                    SimpleNamespace(
                        local_name=None,
                        rssi=-20,
                        service_uuids=[],
                        service_data={},
                        manufacturer_data={},
                    ),
                ),
                "speaker": (
                    SimpleNamespace(name="JBL Charge6"),
                    SimpleNamespace(
                        local_name=None,
                        rssi=-50,
                        service_uuids=[],
                        service_data={},
                        manufacturer_data={87: bytes.fromhex("e3200100")},
                    ),
                ),
            }

    monkeypatch.setattr(bleak, "BleakScanner", FakeScanner)

    async def no_paired_devices():
        return []

    monkeypatch.setattr(transport, "windows_paired_jbl", no_paired_devices)
    rows = await scan_ble(0.01)
    assert [row["address"] for row in rows] == ["speaker", "mouse"]
    assert rows[0]["jbl_detection"]["pid"] == "20e3"
    assert rows[0]["service_data"] == {}


class FakeProbeTransport:
    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def services(self):
        return [{"uuid": "fake"}]

    async def transact(self, request, _timeout):
        if request == protocol.request_firmware_version():
            return [bytes.fromhex("AA 42 04 03 00 07 01")]
        if request == protocol.request_advanced_eq():
            return [bytes.fromhex("AA EE 01 98")]
        return [bytes((0xAA, 0xEE, 1, request[1] if request.startswith(b"\xaa") else 0))]


@pytest.mark.asyncio
async def test_probe_classifies_unsupported(monkeypatch):
    monkeypatch.setattr(probe, "BleTransport", FakeProbeTransport)
    result = await probe.probe_ble(
        "fake",
        pid="20e3",
        service_uuid="service",
        rx_uuid="rx",
        tx_uuid="tx",
        timeout=0.01,
    )
    assert result["services"] == [{"uuid": "fake"}]
    assert result["probes"]["firmware"]["status"] == "supported-response"
    assert result["probes"]["advanced_eq"]["status"] == "unsupported"
