from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Select, Static

import vantadsp.tui as tui_module
from vantadsp.config import Settings
from vantadsp.tui import VantaDSPApp


@pytest.mark.asyncio
async def test_tui_mounts_with_direct_apply():
    app = VantaDSPApp(Settings(last_address="", last_pid="20e3"))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
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
