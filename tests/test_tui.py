import pytest
from textual.widgets import DataTable, Input, Select, Static, Switch

from jbl_pc.config import Settings
from jbl_pc.tui import JblControlApp


@pytest.mark.asyncio
async def test_tui_mounts_and_write_is_locked():
    app = JblControlApp(Settings(last_address="", last_pid="20e3"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert len(app.query_one("#devices", DataTable).columns) == 4
        assert app.query_one("#guard", Switch).value is False
        assert "WRITE LOCKED" in str(app.query_one("#status-safety", Static).render())
        app.query_one("#profile", Select).value = "bass"
        await pilot.pause()
        assert app.query_one("#gains", Input).value == "6, 4, 1, -1, -1, 0, 1"
        assert "BASS HEAVY" in str(app.query_one("#profile-info", Static).render())
        app.apply_eq()
        assert app.query_one("#confirm", Input).value == ""
