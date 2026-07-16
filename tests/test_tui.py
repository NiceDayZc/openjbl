from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Select, Static

import vantadsp.tui as tui_module
from vantadsp import __build_id__, __version__, protocol
from vantadsp.config import Settings
from vantadsp.tui import VantaDSPApp


@pytest.mark.asyncio
async def test_tui_mounts_with_direct_apply():
    app = VantaDSPApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert f"v{__version__}" in app.SUB_TITLE
        assert f"BUILD {__build_id__}" in app.SUB_TITLE
        assert len(app.query_one("#devices", DataTable).columns) == 5
        assert app.query_one("#devices", DataTable).region.height > 3
        assert not app.query("#guard")
        assert not app.query("#confirm")
        assert not app.query("#status-safety")
        app.query_one("#profile", Select).value = "bass"
        await pilot.pause()
        assert app.query_one("#gains", Input).value == "6, 4, 1, -1, -1, 0, 1"
        assert "BASS HEAVY" in str(app.query_one("#profile-info", Static).render())
        app._select_scan_row(
            {
                "name": "JBL Charge6",
                "address": "device-id",
                "rssi": -40,
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
        app.action_eq_tab()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "eq-tab"


def test_tui_source_is_legacy_console_safe():
    source = Path(tui_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert "border: tall" not in source
    assert "border: ascii" in source


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
        app.query_one("#gains", Input).value = "0, 0, 0, 0, 0, 0, 0"
        app.apply_eq()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "activity-tab"
        assert "WRITE VERIFIED" in str(app.query_one("#status-system", Static).render())
        assert "CHANGED + VERIFIED" in str(app.query_one("#status-protocol", Static).render())
