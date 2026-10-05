import pytest
from aiohttp.test_utils import TestClient, TestServer, unused_port
from test_tui import ClampingSpeaker, FakeLink, FakeManager

import openjbl.gui as gui_module
from openjbl import protocol
from openjbl.config import Settings
from openjbl.gui import TOKEN_HEADER, GuiSession, create_app

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """Config, audit log and saved profiles all resolve under LOCALAPPDATA."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


async def successful_probe(*_args, **_kwargs):
    return {
        "services": [{"uuid": "service"}],
        "detected_eq_path": "legacy-parametric-or-advanced",
        "probes": {
            "firmware": {"status": "supported-response", "decoded": [{"firmware_version": "3.0.7.1"}]},
            "advanced_eq": {"status": "supported-response"},
        },
    }


async def client_for(session: GuiSession) -> TestClient:
    port = unused_port()
    client = TestClient(TestServer(create_app(session, token=TOKEN, port=port), host="127.0.0.1", port=port))
    await client.start_server()
    return client


def session_with(link) -> GuiSession:
    return GuiSession(settings=Settings(last_address="device-id", last_pid="20e3"), manager=FakeManager(link))


async def call(client: TestClient, method: str, path: str, body=None):
    response = await client.request(method, path, json=body, headers={TOKEN_HEADER: TOKEN})
    return response.status, await response.json()


@pytest.mark.asyncio
async def test_api_refuses_requests_without_the_session_token():
    """Loopback is reachable from any page in the browser; the token is what keeps them out."""
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        assert (await client.get("/api/state")).status == 403
        assert (await client.get("/api/state", headers={TOKEN_HEADER: "wrong"})).status == 403
        assert (await client.post("/api/apply", json={"profile": "flat", "gains": [0] * 7})).status == 403
        status, state = await call(client, "GET", "/api/state")
        assert status == 200 and state["verified"] is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_a_rebound_hostname_is_refused():
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        response = await client.get("/api/state", headers={TOKEN_HEADER: TOKEN, "Host": "evil.example:80"})
        assert response.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_the_page_carries_its_token_and_a_strict_csp():
    if not gui_module.files("openjbl").joinpath("web/index.html").is_file():
        pytest.skip("front end not built")
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        response = await client.get("/")
        html = await response.text()
        assert TOKEN in html and gui_module.TOKEN_PLACEHOLDER not in html
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_eq_stays_locked_until_the_link_is_verified(monkeypatch):
    monkeypatch.setattr(gui_module, "probe_link", successful_probe)
    link = FakeLink(ClampingSpeaker(99))
    client = await client_for(session_with(link))
    try:
        status, body = await call(client, "POST", "/api/apply", {"profile": "flat", "gains": [0] * 7})
        assert status == 409 and "verify" in body["error"]
        status, target = await call(client, "POST", "/api/connect", {"address": "device-id", "pid": "20e3"})
        assert status == 200 and target["firmware"] == "3.0.7.1"
        status, state = await call(client, "GET", "/api/state")
        assert state["verified"] is True and state["target"]["pid"] == "20e3"

        # The authorisation is for that exact link: a rebuilt one is not it.
        link.generation += 1
        status, body = await call(client, "POST", "/api/apply", {"profile": "flat", "gains": [0] * 7})
        assert status == 409
        assert (await call(client, "GET", "/api/state"))[1]["verified"] is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_apply_reads_back_and_reports_a_verified_write(monkeypatch):
    monkeypatch.setattr(gui_module, "probe_link", successful_probe)
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        await call(client, "POST", "/api/connect", {"address": "device-id", "pid": "20e3"})
        gains = [-19, -1, -0.5, 0, 0, 0, -1]
        # A deep cut is LAB but cannot clip, so it is written without a confirmation.
        status, outcome = await call(client, "POST", "/api/apply", {"profile": "lab-night", "gains": gains})
        assert status == 200
        assert outcome["result"] == "verified"
        assert outcome["verification"]["actual"] == gains
        status, read = await call(client, "POST", "/api/read")
        assert status == 200 and read["gains"] == gains
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_a_boost_needs_confirmation_and_a_clamped_write_is_a_mismatch(monkeypatch):
    monkeypatch.setattr(gui_module, "probe_link", successful_probe)
    speaker = ClampingSpeaker(clamp_to=6.0)
    client = await client_for(session_with(FakeLink(speaker)))
    try:
        await call(client, "POST", "/api/connect", {"address": "device-id", "pid": "20e3"})
        body = {"profile": "lab-harman-room", "gains": [12, 0, 0, 0, 0, 0, 0]}
        status, refused = await call(client, "POST", "/api/apply", body)
        assert status == 428 and refused["needs_confirmation"] is True
        assert speaker.state is None, "nothing may reach the speaker before the confirmation"
        status, outcome = await call(client, "POST", "/api/apply", {**body, "confirm_danger": True})
        assert status == 200 and outcome["result"] == "mismatch"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_standard_profiles_cannot_smuggle_extended_gains(monkeypatch):
    monkeypatch.setattr(gui_module, "probe_link", successful_probe)
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        await call(client, "POST", "/api/connect", {"address": "device-id", "pid": "20e3"})
        status, body = await call(client, "POST", "/api/preview", {"profile": "flat", "gains": [0, -12, 0, 0, 0, 0, 0]})
        assert status == 400 and "range" in body["error"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_model_and_profile_endpoints_describe_the_charge6():
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        status, model = await call(client, "GET", "/api/model/20e3")
        assert status == 200 and model["count"] == 7
        assert [band["type"] for band in model["shape"]] == ["low_shelf"] + ["peaking"] * 5 + ["high_shelf"]
        assert model["bands"][0]["neg_step"] == 0.75 and model["bands"][0]["min"] == -9
        status, tiers = await call(client, "GET", "/api/profiles?pid=20e3")
        assert status == 200
        assert {p["key"] for p in tiers["lab"]} >= {"lab-harman-room", "lab-bk-house"}
        assert all(p["gains"] is not None for p in tiers["lab"])
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_profiles_save_and_delete():
    client = await client_for(session_with(FakeLink(ClampingSpeaker(99))))
    try:
        status, saved = await call(
            client, "POST", "/api/profiles", {"name": "Living Room", "pid": "20e3", "gains": [5, 2, 0, -1, -2, 0, 3]}
        )
        assert status == 200 and saved["key"] == "user-living-room"
        tiers = (await call(client, "GET", "/api/profiles?pid=20e3"))[1]
        assert [p["key"] for p in tiers["user"]] == ["user-living-room"]
        assert (await call(client, "DELETE", "/api/profiles/user-living-room"))[1]["deleted"] is True
        assert (await call(client, "DELETE", "/api/profiles/lab-night"))[0] == 400
    finally:
        await client.close()


def test_charge6_shape_matches_the_frames_the_speaker_receives():
    """The chart draws the filters the page is told about; they must be the ones on the wire."""
    controls = gui_module.model_controls("20e3")
    bands = protocol.charge6_bands([0] * 7)
    assert [(b["frequency"], b["q"]) for b in controls["shape"]] == [(band.frequency, band.q) for band in bands]
