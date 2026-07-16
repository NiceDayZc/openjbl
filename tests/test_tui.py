from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Select, Static

import vantadsp.tui as tui_module
from vantadsp import __build_id__, __version__, protocol
from vantadsp.config import Settings
from vantadsp.tui import VantaDSPApp


@pytest.mark.asyncio
async def test_tui_locks_eq_until_connection_is_verified(monkeypatch):
    async def successful_probe(*_args, **_kwargs):
        return {
            "services": [{"uuid": "service"}],
            "detected_eq_path": "legacy-parametric-or-advanced",
            "probes": {
                "firmware": {
                    "status": "supported-response",
                    "decoded": [{"firmware_version": "3.0.7.1"}],
                },
                "eq_mode": {"status": "supported-response"},
                "simple_eq": {"status": "unsupported"},
                "advanced_eq": {"status": "supported-response"},
                "protocol4_eq": {"status": "unsupported"},
            },
        }

    monkeypatch.setattr(tui_module, "probe_ble", successful_probe)
    app = VantaDSPApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert f"v{__version__}" in app.SUB_TITLE
        assert f"BUILD {__build_id__}" in app.SUB_TITLE
        assert len(app.query_one("#devices", DataTable).columns) == 6
        assert app.query_one("#devices", DataTable).region.height > 3
        assert not app.query("#guard")
        assert not app.query("#confirm")
        assert not app.query("#status-safety")
        assert app.query_one("#profile", Select).disabled
        assert app.query_one("#gains", Input).disabled
        assert app.query_one("#apply").disabled
        assert app.query_one("#main-tabs").get_tab("eq-tab").disabled
        app.action_eq_tab()
        assert app.query_one("#main-tabs").active == "device-tab"
        app._select_scan_row(
            {
                "name": "JBL Charge6",
                "address": "device-id",
                "rssi": -40,
                "live": True,
                "jbl_detection": {
                    "is_jbl": True,
                    "pid": "20e3",
                    "model": "JBL Charge 6",
                    "confidence": "high",
                    "reason": "Harman company data",
                },
            },
            automatic=True,
        )
        await pilot.pause()
        assert app.query_one("#address", Input).value == "device-id"
        assert "AUTO-DETECTED" in str(app.query_one("#detect-guide", Static).render())
        assert app.query_one("#apply").disabled
        app.action_probe()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not app.query_one("#main-tabs").get_tab("eq-tab").disabled
        assert not app.query_one("#profile", Select).disabled
        assert not app.query_one("#gains", Input).disabled
        assert not app.query_one("#apply").disabled
        assert "VERIFIED" in str(app.query_one("#status-device", Static).render())
        app.action_eq_tab()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "eq-tab"
        app.query_one("#profile", Select).value = "bass"
        await pilot.pause()
        assert app.query_one("#gains", Input).value == "6, 4, 1, -1, -1, 0, 1"
        assert "BASS HEAVY" in str(app.query_one("#profile-info", Static).render())
        app.query_one("#address", Input).value = "different-device"
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "device-tab"
        assert app.query_one("#apply").disabled


def test_tui_source_is_legacy_console_safe():
    source = Path(tui_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert "border: tall" not in source
    assert "border: ascii" in source


@pytest.mark.asyncio
async def test_cached_windows_device_cannot_unlock_eq(monkeypatch):
    async def probe_must_not_run(*_args, **_kwargs):
        raise AssertionError("cached metadata must be rejected before BLE probing")

    monkeypatch.setattr(tui_module, "probe_ble", probe_must_not_run)
    app = VantaDSPApp(Settings(last_address="cached-address", last_pid="20e3", auto_update=False))
    async with app.run_test(size=(80, 24)) as pilot:
        app._scan_rows = {
            "cached-address": {
                "address": "cached-address",
                "rssi": None,
                "live": False,
                "jbl_detection": {"pid": "20e3"},
            }
        }
        app.action_probe()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#main-tabs").get_tab("eq-tab").disabled
        assert app.query_one("#apply").disabled
        assert "PROBE FAILED" in str(app.query_one("#status-system", Static).render())
        assert "OFFLINE / ERROR" in str(app.query_one("#status-device", Static).render())


@pytest.mark.asyncio
async def test_direct_apply_requires_ack_and_matching_readback(monkeypatch):
    before_gains = [-0.75, -1, -1, 3, 4, 2, 0]
    before_request = protocol.set_parametric_eq(
        protocol.EQ_CATEGORIES["custom_c2"], protocol.charge6_bands(before_gains)
    )
    before_payload = protocol.LegacyFrame.decode(before_request, force_long=True).payload

    class FakeTransport:
        written_payload = None

        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def transact(self, data, _timeout):
            frame = protocol.LegacyFrame.decode(data)
            if frame.command == protocol.SET_ADVANCED_EQ:
                self.written_payload = frame.payload
                return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, frame.payload, long_length=True).encode()]
            if frame.command == protocol.REQ_ADVANCED_EQ:
                payload = self.written_payload or before_payload
                return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()]
            raise AssertionError(frame.command)

    monkeypatch.setattr(tui_module, "BleTransport", FakeTransport)
    app = VantaDSPApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    async with app.run_test(size=(100, 30)) as pilot:
        app.apply_eq()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "device-tab"
        assert "EQ LOCKED" in str(app.query_one("#status-system", Static).render())
        app._verified_target = ("device-id", "20e3")
        app._set_eq_access(True, "test connection verified")
        app.query_one("#gains", Input).value = "0, 0, 0, 0, 0, 0, 0"
        app.apply_eq()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "activity-tab"
        assert "WRITE VERIFIED" in str(app.query_one("#status-system", Static).render())
        assert "CHANGED + VERIFIED" in str(app.query_one("#status-protocol", Static).render())
