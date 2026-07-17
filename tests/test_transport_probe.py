from types import SimpleNamespace

import pytest

from openjbl import probe, protocol, transport
from openjbl.connection import LinkError, TransactionResult
from openjbl.transport import BleTransport, scan_ble


class FakeClient:
    def __init__(self):
        self.writes = []
        self.callback = None
        self.is_connected = True
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
async def test_ble_transport_rejects_false_connected_state(monkeypatch):
    import bleak

    class DisconnectedClient:
        is_connected = False

        def __init__(self, _address):
            self.disconnect_called = False

        async def connect(self):
            return None

        async def disconnect(self):
            self.disconnect_called = True

    monkeypatch.setattr(bleak, "BleakClient", DisconnectedClient)
    link = BleTransport("missing-device")
    with pytest.raises(ConnectionError, match="did not reach connected state"):
        await link.__aenter__()
    assert link.client is None


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
    assert rows[0]["live"] is True


class FakeProbeLink:
    address = "fake"

    def __init__(self, drop_on: str | None = None):
        self.drop_on = drop_on

    async def services(self):
        return [{"uuid": "fake"}]

    async def transact(self, request, _timeout):
        if self.drop_on is not None and request == getattr(protocol, self.drop_on)():
            raise LinkError("speaker went away")
        if request == protocol.request_firmware_version():
            replies = [bytes.fromhex("AA 42 04 03 00 07 01")]
        elif request == protocol.request_advanced_eq():
            replies = [bytes.fromhex("AA EE 01 98")]
        else:
            replies = [bytes((0xAA, 0xEE, 1, request[1] if request.startswith(b"\xaa") else 0))]
        return TransactionResult(replies=replies, attempts=1, reconnects=0, generation=1)


@pytest.mark.asyncio
async def test_probe_classifies_unsupported():
    result = await probe.probe_link(FakeProbeLink(), pid="20e3", timeout=0.01)
    assert result["services"] == [{"uuid": "fake"}]
    assert result["probes"]["firmware"]["status"] == "supported-response"
    assert result["probes"]["advanced_eq"]["status"] == "unsupported"
    assert result["detected_eq_path"] == "no-supported-eq-response"


@pytest.mark.asyncio
async def test_probe_reports_a_dropped_link_instead_of_blaming_the_speaker():
    """A dead link must not be reported as a speaker that lacks EQ support."""
    with pytest.raises(LinkError, match="link dropped during the eq_mode probe"):
        await probe.probe_link(FakeProbeLink(drop_on="request_eq_mode"), pid="20e3", timeout=0.01)
