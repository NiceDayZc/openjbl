"""The built GUI page, driven in a real browser against a simulated speaker.

The API tests prove the server; these prove the page. The bug that shipped was
entirely on the page side -- a speaker that advertised only Fast Pair data got a
disabled Connect button -- and no server test could have seen it.

Needs `pip install playwright` and Google Chrome; skipped otherwise.
"""

import re

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestServer, unused_port
from test_gui import successful_probe
from test_tui import ClampingSpeaker, FakeLink, FakeManager

import openjbl.gui as gui_module
from openjbl.config import Settings
from openjbl.discovery import detect_jbl_device
from openjbl.gui import GuiSession, create_app

async_api = pytest.importorskip("playwright.async_api")
expect = async_api.expect

if not gui_module.files("openjbl").joinpath("web/index.html").is_file():
    pytest.skip("front end not built", allow_module_level=True)


def advertised(name, address, rssi, **advertisement):
    row = {
        "name": name,
        "address": address,
        "rssi": rssi,
        "live": True,
        "service_uuids": [],
        "service_data": {},
        "manufacturer_data": {},
        **advertisement,
    }
    row["jbl_detection"] = detect_jbl_device(row)
    return row


# The shape a Charge 6 really sent while paired to a phone: a Fast Pair frame and
# a name, and nothing that says which model it is. The bytes are made up.
FAST_PAIR_ONLY = advertised(
    "JBLSBIC",
    "00000000-0000-4000-8000-00000000C6C6",
    -56,
    service_data={"0000fe2c-0000-1000-8000-00805f9b34fb": "00112233445566778899aabb"},
)
PHONE = advertised("Phone", "00000000-0000-4000-8000-000000000001", -50)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(gui_module, "probe_link", successful_probe)


@pytest_asyncio.fixture
async def gui(monkeypatch):
    """Start the real server on a simulated speaker and open the page in Chrome."""
    state = {"rows": [FAST_PAIR_ONLY, PHONE], "speaker": ClampingSpeaker(99)}

    async def fake_scan(_seconds):
        return state["rows"]

    monkeypatch.setattr(gui_module, "scan_ble", fake_scan)
    session = GuiSession(
        settings=Settings(last_pid="20e3"),
        manager=FakeManager(FakeLink(lambda data: state["speaker"](data))),
    )
    port = unused_port()
    server = TestServer(create_app(session, token="e2e-token", port=port), host="127.0.0.1", port=port)
    await server.start_server()
    async with async_api.async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # no Chrome on this machine
            await server.close()
            pytest.skip(f"Chrome is not available: {exc}")
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(f"http://127.0.0.1:{port}/")
        state["page"] = page
        yield state
        await browser.close()
    await server.close()


async def connect_through_model_picker(page):
    await page.get_by_role("button", name="Scan & connect").click()
    await expect(page.get_by_text("Choose the speaker's model")).to_be_visible()
    row = page.get_by_test_id("device-row").filter(has_text="JBLSBIC")
    await expect(row.get_by_role("combobox", name="Speaker model")).to_have_text(re.compile("JBL Charge 6"))
    await row.get_by_role("button", name="Connect").click()
    await expect(page.get_by_text("Connected over Bluetooth LE")).to_be_visible()


@pytest.mark.asyncio
async def test_a_speaker_that_hides_its_model_can_still_be_connected(gui):
    page = gui["page"]
    await expect(page.get_by_role("button", name="Apply to speaker")).to_be_disabled()
    await expect(page.get_by_text("Browse only")).to_be_visible()
    await connect_through_model_picker(page)
    # The phone in the scan is not a JBL and stays out of the list.
    await expect(page.get_by_test_id("device-row")).to_have_count(0)
    await expect(page.get_by_text("Browse only")).to_be_hidden()
    await expect(page.get_by_role("button", name="Apply to speaker")).to_be_enabled()


@pytest.mark.asyncio
async def test_apply_writes_and_shows_the_band_by_band_readback(gui):
    page = gui["page"]
    await connect_through_model_picker(page)
    await page.get_by_role("button", name=re.compile("^Late Night")).click()
    await page.get_by_role("button", name="Apply to speaker").click()
    await expect(page.get_by_text("Write verified", exact=True)).to_be_visible()
    table = page.get_by_role("table")
    await expect(table.get_by_role("row")).to_have_count(8)
    await expect(table.get_by_role("row").nth(1)).to_contain_text("\u221219")  # the page prints a true minus sign
    await page.get_by_role("button", name="Read current").click()
    await expect(page.get_by_text("On the speaker now")).to_be_visible()


@pytest.mark.asyncio
async def test_a_boost_asks_before_it_is_written_and_a_clamp_is_caught(gui):
    gui["speaker"] = ClampingSpeaker(clamp_to=6.0)
    page = gui["page"]
    await connect_through_model_picker(page)
    await page.get_by_role("slider").first.press("End")  # 125 Hz to the LAB ceiling, +12 dB
    await expect(page.get_by_text("Boost > +6 dB")).to_be_visible()
    await page.get_by_role("button", name="Apply to speaker").click()
    dialog = page.get_by_role("alertdialog")
    await expect(dialog).to_contain_text("Write a boost past +6 dB?")
    assert gui["speaker"].state is None, "nothing may reach the speaker before the confirmation"
    await dialog.get_by_role("button", name="Write anyway").click()
    await expect(page.get_by_text("Write verification failed")).to_be_visible()
    await expect(page.get_by_text("Mismatch", exact=True)).to_be_visible()


@pytest.mark.asyncio
async def test_a_saved_profile_shows_up_under_my_profiles(gui):
    page = gui["page"]
    await page.get_by_role("button", name=re.compile("^Vocal Bloom Room")).click()
    await page.get_by_role("button", name="Save as").click()
    await page.get_by_label("Name").fill("Living Room")
    await page.get_by_role("button", name="Save", exact=True).click()
    await expect(page.get_by_text("Saved “Living Room”")).to_be_visible()
    await expect(page.get_by_role("radio", name=re.compile("My profiles"))).to_have_attribute("aria-checked", "true")
    await expect(page.get_by_role("button", name=re.compile("^Living Room"))).to_be_visible()
