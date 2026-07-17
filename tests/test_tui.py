import asyncio
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Select, Static

import openjbl.tui as tui_module
from openjbl import __build_id__, __version__, protocol
from openjbl.config import Settings
from openjbl.connection import TransactionResult
from openjbl.tui import OpenJBLApp
from openjbl.userprofiles import load_user_profiles


class FakeLink:
    """A link that is already up, so the TUI's held-link path can be exercised."""

    def __init__(self, responder=None, address="device-id"):
        self.address = address
        self.generation = 1
        self.connected = True
        self.reconnects = 0
        self._responder = responder

    async def services(self):
        return [{"uuid": "service"}]

    async def transact(self, data, _timeout=None):
        return TransactionResult(
            replies=self._responder(data),
            attempts=1,
            reconnects=self.reconnects,
            generation=self.generation,
        )


class FakeManager:
    def __init__(self, link=None):
        self.link = link
        self.acquired: list[str] = []

    async def acquire(self, address):
        self.acquired.append(address)
        if self.link is None:
            raise ConnectionError("no speaker")
        self.link.address = address
        return self.link

    def live(self, address):
        return self.link if self.link is not None and self.link.connected else None

    def holds_generation(self, address, generation):
        link = self.live(address)
        return link is not None and link.generation == generation

    async def release(self, address):
        return None

    async def release_all(self):
        return None


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

    monkeypatch.setattr(tui_module, "probe_link", successful_probe)
    app = OpenJBLApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
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
        assert app.query_one("#gains", Input).region.y >= app.query_one("#profile", Select).region.bottom
        assert "VERIFIED" in str(app.query_one("#status-device", Static).render())
        app.action_eq_tab()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "eq-tab"
        app.query_one("#profile", Select).value = "bass"
        await pilot.pause()
        assert app.query_one("#gains", Input).value == "6, 4, 1, -1, -1, 0, 1"
        assert "BASS HEAVY" in str(app.query_one("#profile-info", Static).render())
        app.query_one("#profile-tier", Select).value = "lab"
        await pilot.pause()
        assert app.query_one("#profile", Select).value == "lab-max-bass"
        assert app.query_one("#gains", Input).value == "24, 16, 4, -8, -12, -8, -2"
        assert "DANGER" in str(app.query_one("#profile-info", Static).render())
        assert str(app.query_one("#apply").label) == "APPLY DANGEROUS PROFILE"
        app.apply_eq()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "eq-tab"
        assert app._danger_armed_until > 0
        assert str(app.query_one("#apply").label) == "CONFIRM DANGER APPLY"
        app.query_one("#address", Input).value = "different-device"
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "device-tab"
        assert app.query_one("#apply").disabled


@pytest.mark.asyncio
async def test_startup_keeps_the_balanced_default_profile():
    """Select posts a Changed for its initial value, so the tier handler used to
    silently replace the Balanced default with the first option in the list."""
    app = OpenJBLApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.query_one("#profile", Select).value == "balanced"
        assert "BALANCED" in str(app.query_one("#profile-info", Static).render())


@pytest.mark.asyncio
async def test_my_profiles_tier_saves_edits_and_offers_them_back(monkeypatch, tmp_path):
    store = tmp_path / "profiles.json"
    monkeypatch.setattr(tui_module, "user_profiles_path", lambda path=None: store, raising=False)
    for name in ("load_user_profiles", "user_profile_options", "save_user_profile", "delete_user_profile"):
        original = getattr(tui_module, name)
        monkeypatch.setattr(tui_module, name, (lambda fn: lambda *a, **k: fn(*a, **{**k, "path": store}))(original))

    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "20e3", app.manager.link.generation)
        app._set_eq_access(True, "test connection verified")

        app.query_one("#profile-tier", Select).value = "user"
        await pilot.pause()
        assert "Empty" in str(app.query_one("#profile-info", Static).render()), "an empty tier must say how to fill it"

        app.query_one("#profile-tier", Select).value = "standard"
        await pilot.pause()
        app.query_one("#gains", Input).value = "5, 2, 0, -1, -2, 0, 3"
        await pilot.pause()
        app.action_save_profile()
        await pilot.pause()
        await app.screen.dismiss("Living Room")  # the name prompt
        await pilot.pause()

        assert [p.key for p in load_user_profiles(store)] == ["user-living-room"]
        assert app.query_one("#profile-tier", Select).value == "user", "it should switch to the tier it saved into"
        assert app.query_one("#profile", Select).value == "user-living-room"
        assert app.query_one("#gains", Input).value == "5, 2, 0, -1, -2, 0, 3", "the saved curve must load back"

        app.action_delete_profile()
        await pilot.pause()
        assert load_user_profiles(store) == []


@pytest.mark.asyncio
async def test_a_saved_profile_that_boosts_still_has_to_be_confirmed(monkeypatch, tmp_path):
    """Saving a curve must not be a way to launder it past the confirmation."""
    store = tmp_path / "profiles.json"
    for name in ("load_user_profiles", "user_profile_options", "save_user_profile"):
        original = getattr(tui_module, name)
        monkeypatch.setattr(tui_module, name, (lambda fn: lambda *a, **k: fn(*a, **{**k, "path": store}))(original))

    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "20e3", app.manager.link.generation)
        app._set_eq_access(True, "test connection verified")
        app.query_one("#gains", Input).value = "20, 12, 0, 0, 0, 0, 0"
        await pilot.pause()
        app.action_save_profile()
        await pilot.pause()
        await app.screen.dismiss("Loud One")
        await pilot.pause()

        assert app.query_one("#profile", Select).value == "user-loud-one"
        assert app._dangerous_profile() is True
        assert str(app.query_one("#apply").label) == "APPLY DANGEROUS PROFILE"
        app.apply_eq()
        await pilot.pause()
        assert str(app.query_one("#apply").label) == "CONFIRM DANGER APPLY", "first click must only arm"


class ClampingSpeaker:
    """A speaker that acknowledges the write and then does something else.

    The existing apply test uses a fake that echoes back exactly what it was
    handed, which makes verification.verified structurally always True -- the
    readback gate could be deleted and the suite would stay green. Real firmware
    is free to clamp, ignore or round; that is the whole reason the gate exists.
    """

    def __init__(self, clamp_to: float = 6.0):
        self.clamp_to = clamp_to
        self.state: bytes | None = None

    def __call__(self, data):
        frame = protocol.LegacyFrame.decode(data)
        if frame.command == protocol.SET_ADVANCED_EQ:
            parsed = protocol.parse_parametric_eq(frame.payload)
            clamped = [min(self.clamp_to, band["gain"]) for band in parsed["bands"]]
            bands = protocol.charge6_extended_bands(clamped)
            self.state = protocol.LegacyFrame.decode(
                protocol.set_parametric_eq(protocol.EQ_CATEGORIES["custom_c2"], bands), force_long=True
            ).payload
            return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, frame.payload, long_length=True).encode()]
        if frame.command == protocol.REQ_ADVANCED_EQ:
            payload = self.state if self.state is not None else frame.payload
            return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()]
        raise AssertionError(frame.command)


@pytest.mark.asyncio
async def test_a_speaker_that_clamps_the_gains_is_reported_as_a_mismatch():
    """The speaker ACKs, so the ACK proves nothing; only the readback catches it."""
    link = FakeLink(ClampingSpeaker(clamp_to=6.0))
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        app.query_one("#profile-tier", Select).value = "lab"
        await pilot.pause()
        app.query_one("#profile", Select).value = "lab-max-bass"  # asks for +24 at 125 Hz
        await pilot.pause()
        app.apply_eq()  # arms
        await pilot.pause()
        app.apply_eq()  # confirms
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "WRITE MISMATCH" in str(app.query_one("#status-system", Static).render())


@pytest.mark.asyncio
async def test_a_read_cannot_cancel_an_apply_that_is_already_writing():
    """Sharing a worker group meant 'r' cancelled an apply after the frame was on
    the wire and before the readback -- one keystroke defeating the evidence."""
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowSpeaker(ClampingSpeaker):
        pass

    speaker = SlowSpeaker(clamp_to=99.0)

    class SlowLink(FakeLink):
        async def transact(self, data, _timeout=None):
            frame = protocol.LegacyFrame.decode(data)
            if frame.command == protocol.SET_ADVANCED_EQ:
                started.set()
                await release.wait()  # hold the write open
            return await FakeLink.transact(self, data, _timeout)

    link = SlowLink(speaker)
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        app.query_one("#gains", Input).value = "0, 0, 0, 0, 0, 0, 0"
        await pilot.pause()
        app.apply_eq()
        await asyncio.wait_for(started.wait(), timeout=2)
        app.action_read()  # the keystroke that used to kill the apply
        await pilot.pause()
        apply_workers = [w for w in app.workers if w.name == "apply_worker"]
        assert apply_workers and all(not w.is_cancelled for w in apply_workers), "the write must survive a read"
        release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()


def test_tui_source_is_legacy_console_safe():
    source = Path(tui_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert "border: tall" not in source
    assert "border: ascii" in source


@pytest.mark.asyncio
async def test_cached_windows_device_cannot_unlock_eq(monkeypatch):
    async def probe_must_not_run(*_args, **_kwargs):
        raise AssertionError("cached metadata must be rejected before BLE probing")

    monkeypatch.setattr(tui_module, "probe_link", probe_must_not_run)
    app = OpenJBLApp(Settings(last_address="cached-address", last_pid="20e3", auto_update=False))
    manager = FakeManager(FakeLink())
    app.manager = manager
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
        assert manager.acquired == [], "cached metadata must be rejected before a link is opened"
        assert app.query_one("#main-tabs").get_tab("eq-tab").disabled
        assert app.query_one("#apply").disabled
        assert "VERIFY FAILED" in str(app.query_one("#status-system", Static).render())
        assert "OFFLINE / ERROR" in str(app.query_one("#status-device", Static).render())


@pytest.mark.asyncio
async def test_direct_apply_requires_ack_and_matching_readback(monkeypatch):
    before_gains = [-0.75, -1, -1, 3, 4, 2, 0]
    before_request = protocol.set_parametric_eq(
        protocol.EQ_CATEGORIES["custom_c2"], protocol.charge6_bands(before_gains)
    )
    before_payload = protocol.LegacyFrame.decode(before_request, force_long=True).payload

    class Speaker:
        """Answers the advanced-EQ set with a RET frame, as the real one does."""

        written_payload = None

        def __call__(self, data):
            frame = protocol.LegacyFrame.decode(data)
            if frame.command == protocol.SET_ADVANCED_EQ:
                self.written_payload = frame.payload
                return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, frame.payload, long_length=True).encode()]
            if frame.command == protocol.REQ_ADVANCED_EQ:
                payload = self.written_payload or before_payload
                return [protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()]
            raise AssertionError(frame.command)

    link = FakeLink(Speaker())
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(100, 30)) as pilot:
        app.apply_eq()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "device-tab"
        assert "EQ LOCKED" in str(app.query_one("#status-system", Static).render())
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        app.query_one("#gains", Input).value = "0, 0, 0, 0, 0, 0, 0"
        app.apply_eq()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "activity-tab"
        assert "WRITE VERIFIED" in str(app.query_one("#status-system", Static).render())
        assert "CHANGED + VERIFIED" in str(app.query_one("#status-protocol", Static).render())


@pytest.mark.asyncio
async def test_hand_typed_extended_gain_still_needs_confirming_on_a_standard_profile():
    """The gain field is free text, so danger must follow the values, not the
    profile label -- otherwise +24 dB typed under STANDARD writes on one click."""
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()  # let the mount-time profile load settle first
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        assert app.query_one("#profile-tier", Select).value == "standard"
        app.query_one("#gains", Input).value = "24, 24, 24, 24, 24, 24, 24"
        await pilot.pause()
        assert app._dangerous_profile() is True
        assert app._lab_profile() is False, "the LAB encoder must not be enabled by typing a big number"
        assert str(app.query_one("#apply").label) == "APPLY DANGEROUS PROFILE"
        app.apply_eq()
        await pilot.pause()
        assert str(app.query_one("#apply").label) == "CONFIRM DANGER APPLY", "first click must only arm"


@pytest.mark.asyncio
async def test_editing_gains_disarms_a_pending_danger_confirmation():
    """The arm is keyed to what it was armed for, so an edit between the two
    clicks cannot be confirmed by the second."""
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()  # let the mount-time profile load settle first
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        app.query_one("#gains", Input).value = "24, 24, 24, 24, 24, 24, 24"
        await pilot.pause()
        app.apply_eq()
        await pilot.pause()
        assert app._danger_armed() is True
        app.query_one("#gains", Input).value = "20, 20, 20, 20, 20, 20, 20"
        await pilot.pause()
        assert app._danger_armed() is False, "the arm was for a curve that is no longer on screen"


@pytest.mark.asyncio
async def test_eq_access_is_revoked_when_the_verified_link_dies():
    """Verification authorises a live link, not an address: if the link the probe
    ran over is gone, the EQ controls must lock even though nothing else changed."""
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(80, 24)) as pilot:
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        await pilot.pause()
        assert not app.query_one("#apply").disabled
        link.generation += 1  # a drop and recovery: same address, different link
        assert app._eq_access_allowed() is False
        link.connected = False
        assert app._eq_access_allowed() is False


@pytest.mark.asyncio
async def test_auto_setup_declines_rather_than_guessing_between_two_speakers(monkeypatch):
    async def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("auto-setup must not verify anything when it declines to choose")

    def jbl(address, rssi):
        return {
            "name": "JBL Charge6",
            "address": address,
            "rssi": rssi,
            "live": True,
            "jbl_detection": {
                "is_jbl": True,
                "pid": "20e3",
                "model": "JBL Charge 6",
                "confidence": "high",
                "reason": "Harman company data",
            },
        }

    async def two_close_speakers(_seconds):
        return [jbl("speaker-a", -40), jbl("speaker-b", -42)]

    monkeypatch.setattr(tui_module, "scan_ble", two_close_speakers)
    monkeypatch.setattr(tui_module, "probe_link", unexpected_probe)
    app = OpenJBLApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_scan()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.query_one("#main-tabs").active == "device-tab", "it must not open the EQ tab"
        assert app.query_one("#apply").disabled


@pytest.mark.asyncio
async def test_auto_setup_verifies_the_strongest_speaker_and_opens_eq(monkeypatch):
    async def successful_probe(*_args, **_kwargs):
        return {
            "services": [{"uuid": "service"}],
            "detected_eq_path": "legacy-parametric-or-advanced",
            "probes": {"firmware": {"status": "supported-response", "decoded": [{"firmware_version": "3.0.7.1"}]}},
        }

    def jbl(address, rssi):
        return {
            "name": "JBL Charge6",
            "address": address,
            "rssi": rssi,
            "live": True,
            "jbl_detection": {
                "is_jbl": True,
                "pid": "20e3",
                "model": "JBL Charge 6",
                "confidence": "high",
                "reason": "Harman company data",
            },
        }

    async def one_clear_winner(_seconds):
        return [jbl("weak", -80), jbl("strong", -40)]

    monkeypatch.setattr(tui_module, "scan_ble", one_clear_winner)
    monkeypatch.setattr(tui_module, "probe_link", successful_probe)
    app = OpenJBLApp(Settings(last_address="", last_pid="20e3", auto_update=False))
    manager = FakeManager(FakeLink())
    app.manager = manager
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_scan()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert manager.acquired == ["strong"]
        assert app.query_one("#address", Input).value == "strong"
        assert app.query_one("#main-tabs").active == "eq-tab", "one press should land on the Equalizer"
        assert not app.query_one("#apply").disabled


@pytest.mark.asyncio
async def test_level_index_models_confirm_on_magnitude_not_only_on_boost():
    """"A cut cannot clip" is a dB argument. On EQ_BALANCE and PRESET_EQ models the
    wire value is an index into a firmware table, so -100 is not "very quiet", it
    is an entry that does not exist -- there, both directions need confirming."""
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="2050", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "2050", link.generation)
        app._set_eq_access(True, "test connection verified")
        assert app._gains_are_decibels() is False, "2050 is a level-index model"
        app.query_one("#gains", Input).value = "-100, 0, 0"
        await pilot.pause()
        assert app._dangerous_profile() is True, "a huge negative index must be confirmed"
        assert str(app.query_one("#apply").label) == "APPLY DANGEROUS PROFILE"


@pytest.mark.asyncio
async def test_decibel_models_keep_the_cuts_are_free_exemption():
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        assert app._gains_are_decibels() is True
        app.query_one("#gains", Input).value = "0, -20, -20, -20, -20, -20, -20"
        await pilot.pause()
        assert app._dangerous_profile() is False, "a deep cut in dB costs level, not headroom"


@pytest.mark.asyncio
async def test_key_bindings_cannot_bypass_the_eq_lock():
    """Disabling the buttons is not enough: a binding never consults
    widget.disabled, so 'r' and 'w' reached the EQ path with the tab locked."""
    link = FakeLink()
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(link)
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        assert app._eq_access_allowed() is False
        for action in ("read", "preview", "save_profile", "delete_profile"):
            assert app.check_action(action, ()) is False, f"{action} must be refused while locked"
        app._verified_target = ("device-id", "20e3", link.generation)
        app._set_eq_access(True, "test connection verified")
        for action in ("read", "preview", "save_profile"):
            assert app.check_action(action, ()) is True


@pytest.mark.asyncio
async def test_an_empty_saved_tier_survives_a_model_change(monkeypatch, tmp_path):
    """The empty tier parks the dropdown on a sentinel that is not a profile;
    the next PID change used to raise ValueError out of the message pump."""
    store = tmp_path / "profiles.json"
    for name in ("load_user_profiles", "user_profile_options"):
        original = getattr(tui_module, name)
        monkeypatch.setattr(tui_module, name, (lambda fn: lambda *a, **k: fn(*a, **{**k, "path": store}))(original))
    app = OpenJBLApp(Settings(last_address="device-id", last_pid="20e3", auto_update=False))
    app.manager = FakeManager(FakeLink())
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        app.query_one("#profile-tier", Select).value = "user"
        await pilot.pause()
        app.query_one("#pid", Select).value = "2107"  # used to crash the app
        await pilot.pause()
        assert app.is_running
        assert "Empty" in str(app.query_one("#profile-info", Static).render())
