"""Monochrome Textual workstation for discovery, inspection, and EQ control."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from . import __build_id__, __version__
from .audit import append_audit, target_fingerprint
from .config import Settings
from .connection import ConnectionManager, Link
from .models import all_models, auto_eq_frames, auto_read_frames, gain_count_for_pid, get_model, summarize_model
from .presets import (
    STANDARD_MAX_BOOST_DB,
    SoundProfile,
    curve_from_model_gains,
    curve_summary,
    get_profile,
    profile_options,
    resolve_curve,
    sparkline,
)
from .probe import probe_link
from .protocol import describe_frame, hex_bytes
from .transport import scan_ble
from .updater import auto_update
from .userprofiles import (
    ProfileStoreError,
    delete_user_profile,
    load_user_profiles,
    save_user_profile,
    user_profile_options,
)
from .verification import verify_eq_readback

MODEL_OPTIONS = [(f"{model.get('deviceName')} / {model.get('pid')}", str(model.get("pid"))) for model in all_models()]
# Below this the link is too weak to verify reliably, so auto-setup asks rather
# than picking a speaker the user then cannot diagnose. Ours: the app has no
# auto-select and therefore no floor to copy.
AUTO_SELECT_RSSI_FLOOR = -85
# Two speakers within this margin are a coin toss; show the table instead.
AUTO_SELECT_MARGIN_DB = 6
# No standard profile resolves above this on any model in the APK database, so a
# value beyond it was hand-entered and gets the extended-gain confirmation --
# whichever profile happens to be selected in the dropdown. On dB models only a
# boost counts, because a cut costs level rather than headroom; on level-index
# models magnitude in either direction counts, because there the number is a
# table entry and out-of-range is undefined rather than quiet.
STANDARD_MAX_GAIN_DB = STANDARD_MAX_BOOST_DB
# The stand-in shown when MY PROFILES is empty. Select cannot hold no options,
# so this occupies the dropdown -- but it is not a profile, and every consumer
# has to know that.
EMPTY_TIER_KEY = "none"
EMPTY_TIER_LABEL = "No saved profiles yet"
TIER_LABELS = {
    "standard": "STANDARD / MODEL UI RANGE",
    "lab": "LAB / EXTENDED +/-24 dB",
    "user": "MY PROFILES / SAVED",
}


class NamePrompt(ModalScreen[str | None]):
    """Asks for a profile name without permanently adding a field to the EQ tab."""

    CSS = """
    NamePrompt { align: center middle; }
    #prompt-box { width: 60; height: 11; border: ascii #eeeeee; background: #111111; padding: 1 2; }
    #prompt-title { height: 1; color: #eeeeee; text-style: bold; }
    #prompt-hint { height: 2; color: #999999; }
    #prompt-name { margin-top: 1; }
    #prompt-actions { height: 3; align-horizontal: right; }
    #prompt-actions Button { min-width: 12; margin-left: 1; }
    """
    BINDINGS: ClassVar = [("escape", "cancel", "Cancel")]

    def __init__(self, hint: str) -> None:
        super().__init__()
        self._hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-box"):
            yield Static("SAVE PROFILE", id="prompt-title")
            yield Static(self._hint, id="prompt-hint")
            yield Input(placeholder="Name this profile", id="prompt-name")
            with Horizontal(id="prompt-actions", classes="actions"):
                yield Button("CANCEL", id="prompt-cancel")
                yield Button("SAVE", id="prompt-save")

    def on_mount(self) -> None:
        self.query_one("#prompt-name", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prompt-save":
            self.dismiss(self.query_one("#prompt-name", Input).value.strip() or None)
        else:
            self.dismiss(None)


@dataclass(frozen=True)
class WriteRequest:
    """Identity and gains resolved once, before any widget can change under us.

    Reading #pid and #gains separately on the write path is unsafe: Select.Changed
    is posted, not called, so a programmatically selected PID can pair with the
    previous model's gains and write the wrong shape to real hardware.
    """

    address: str
    pid: str
    profile: str
    gains: list[float]
    # Opting in to the LAB encoder and needing confirmation are different things:
    # a hand-typed 24 dB on a STANDARD profile needs the confirmation but must
    # still meet the model's own step and range limits.
    allow_extended: bool
    dangerous: bool


class OpenJBLApp(App[None]):
    TITLE = "OPENJBL"
    SUB_TITLE = f"BLUETOOTH EQ CONTROL  /  v{__version__}  /  BUILD {__build_id__}"
    CSS = """
    Screen { background: #000000; color: #eeeeee; }
    Header, #mono-footer { background: #eeeeee; color: #000000; }
    #mono-footer { dock: bottom; height: 1; padding: 0 1; }
    #status-strip { height: 3; background: #111111; padding: 0 1; }
    .metric { width: 1fr; height: 3; padding: 0 1; border-left: ascii #555555; }
    #status-system { border-left: none; }
    #main-tabs { height: 1fr; }
    TabbedContent { background: #000000; }
    TabPane { padding: 0 1 1 1; background: #000000; }
    Tabs { background: #000000; color: #aaaaaa; }
    Tabs .underline--bar { background: #eeeeee; }
    Tab.-active { background: #eeeeee; color: #000000; text-style: bold; }
    .guide { height: 2; color: #bbbbbb; padding: 0 1; background: #111111; }
    #setup { height: 5; margin-top: 1; }
    #setup > Vertical { width: 1fr; margin-right: 1; }
    #setup > Vertical:last-of-type { margin-right: 0; }
    .field-label { color: #999999; }
    Input, Select { background: #090909; color: #eeeeee; border: ascii #555555; }
    Input:focus, Select:focus { border: ascii #ffffff; }
    Select > SelectCurrent { border: ascii #555555; padding: 0 1; }
    Select:focus > SelectCurrent { border: ascii #ffffff; }
    SelectCurrent .arrow { display: none; }
    Select > SelectOverlay { border: ascii #ffffff; }
    Toast, Toast.-information, Toast.-warning, Toast.-error {
        width: 42; max-width: 40%; padding: 0 1; margin-top: 0;
        background: #111111; color: #eeeeee; border: ascii #eeeeee;
    }
    Toast .toast--title { color: #eeeeee; }
    #devices {
        height: 1fr; border: ascii #555555; background: #000000;
        scrollbar-color: #777777; scrollbar-background: #000000;
    }
    #devices > .datatable--header { background: #111111; color: #eeeeee; }
    #devices > .datatable--cursor,
    #devices:focus > .datatable--cursor,
    #devices > .datatable--fixed-cursor,
    #devices:focus > .datatable--fixed-cursor {
        background: #eeeeee; color: #000000; text-style: bold;
    }
    #profile-panel { height: 13; padding: 1; background: #090909; }
    #profile-row { height: 3; }
    #profile-tier { width: 1fr; margin-right: 1; }
    #profile { width: 2fr; }
    #gains { width: 1fr; height: 3; }
    #curve { height: 2; color: #ffffff; text-style: bold; }
    #profile-info { height: 2; color: #aaaaaa; }
    .actions { height: 3; align-vertical: middle; }
    .actions Button { min-width: 18; margin-right: 1; background: #111111; color: #eeeeee; border: ascii #555555; }
    .actions Button:hover, .actions Button:focus { background: #eeeeee; color: #000000; border: ascii #ffffff; }
    #apply { min-width: 22; background: #eeeeee; color: #000000; text-style: bold; }
    #log {
        height: 1fr; border: ascii #555555; background: #000000; color: #dddddd;
        scrollbar-color: #777777; scrollbar-background: #000000;
    }
    """
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("s", "scan", "Scan"),
        ("p", "probe", "Probe"),
        ("r", "read", "Read EQ"),
        ("v", "preview", "Preview"),
        ("w", "save_profile", "Save profile"),
        ("1", "device_tab", "Device"),
        ("2", "eq_tab", "EQ"),
        ("3", "activity_tab", "Activity"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings.load()
        self._scan_rows: dict[str, dict[str, Any]] = {}
        # (address, pid, link generation) -- the generation is what makes this an
        # authorisation over a live link rather than a memory of a past one.
        self._verified_target: tuple[str, str, int] | None = None
        self._danger_armed_until = 0.0
        self._danger_arm_profile: str | None = None
        self._programmatic_edit = False
        self._user_profiles: list[SoundProfile] = []
        self.manager = ConnectionManager(
            service_uuid=self.settings.service_uuid,
            rx_uuid=self.settings.rx_uuid,
            tx_uuid=self.settings.tx_uuid,
            on_event=self._link_event,
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="status-strip"):
            yield Static("SYSTEM\nREADY", id="status-system", classes="metric")
            yield Static("DEVICE\nNOT SELECTED", id="status-device", classes="metric")
            yield Static("PROTOCOL\nUNKNOWN", id="status-protocol", classes="metric")
        with TabbedContent(initial="device-tab", id="main-tabs"):
            with TabPane("01  DEVICE", id="device-tab"):
                yield Static(
                    "AUTO SETUP  Scan selects the strongest LIVE JBL, verifies firmware/EQ, then opens Equalizer.",
                    id="detect-guide",
                    classes="guide",
                )
                with Horizontal(id="setup"):
                    with Vertical():
                        yield Label("BLE ADDRESS / DEVICE ID", classes="field-label")
                        yield Input(
                            value=self.settings.last_address,
                            placeholder="Select a scan result or enter a device ID",
                            id="address",
                        )
                    with Vertical():
                        yield Label("MODEL PROFILE", classes="field-label")
                        yield Select(MODEL_OPTIONS, value=self.settings.last_pid, allow_blank=False, id="pid")
                yield DataTable(id="devices", cursor_type="row", zebra_stripes=False)
                with Horizontal(classes="actions"):
                    yield Button("S  SCAN + AUTO VERIFY", id="scan")
                    yield Button("P  RE-VERIFY SELECTED", id="probe")
            with TabPane("02  EQUALIZER", id="eq-tab"):
                yield Static(
                    "LOCKED  Connect and verify the selected speaker on the Device tab before editing EQ.",
                    id="eq-guide",
                    classes="guide",
                )
                with Vertical(id="profile-panel"):
                    yield Label("SOUND PROFILE", classes="field-label")
                    with Horizontal(id="profile-row"):
                        yield Select(
                            [
                                ("STANDARD / UI RANGE", "standard"),
                                ("LAB / EXTENDED +/-24 dB", "lab"),
                                ("MY PROFILES / SAVED", "user"),
                            ],
                            value="standard",
                            allow_blank=False,
                            id="profile-tier",
                        )
                        yield Select(profile_options(), value="balanced", allow_blank=False, id="profile")
                    yield Label("GAIN VALUES (dB)", classes="field-label")
                    yield Input(id="gains", placeholder="Comma-separated model-aware gains")
                    yield Static(id="curve")
                    yield Static(id="profile-info")
                yield Static(
                    "DIRECT APPLY  The button writes the selected profile immediately.",
                    id="apply-guide",
                    classes="guide",
                )
                with Horizontal(classes="actions"):
                    yield Button("R  READ CURRENT", id="read")
                    yield Button("V  PREVIEW PACKET", id="preview")
                    yield Button("W  SAVE AS...", id="save-profile")
                    yield Button("DELETE", id="delete-profile")
                    yield Button("APPLY TO SPEAKER", id="apply")
            with TabPane("03  ACTIVITY", id="activity-tab"):
                yield Static(
                    "Connection details, packet previews, replies, and errors appear below.",
                    classes="guide",
                )
                yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Static(
            "q Quit  s Auto Setup  p Re-verify  r Read EQ  v Preview  w Save profile  1 Device  2 EQ  3 Activity",
            id="mono-footer",
        )

    def on_mount(self) -> None:
        table = self.query_one("#devices", DataTable)
        table.add_columns("NAME", "DETECTED MODEL", "PID", "STATUS", "RSSI", "ADDRESS")
        self._load_profile("balanced")
        self.log_message(f"START  |  OpenJBL v{__version__}  |  build={__build_id__}")
        self._set_eq_access(False, "No verified speaker session")
        self.log_message("READY  |  Press SCAN to set up automatically, or pick a row and press RE-VERIFY.")
        if self.settings.auto_update:
            self.update_worker()

    @work(exclusive=False, group="update")
    async def update_worker(self) -> None:
        """Report that a newer release exists. Nothing is installed from here.

        Its own group because exclusive cancellation targets a whole group, and
        this must not be cancelled by the user pressing SCAN.
        """
        self.log_message("UPDATE  |  Checking PyPI in the background...")
        result = await asyncio.to_thread(auto_update)
        self.log_message(
            f"UPDATE  |  status={result.status}  |  current={result.current}  |  latest={result.latest}  |  "
            f"{result.message}"
        )
        if result.status == "update-available":
            self.notify(result.message, title="Update available", severity="information", timeout=10)
        elif result.status == "check-failed":
            self.notify(result.message, title="Update check unavailable", severity="warning")

    def log_message(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _show_tab(self, tab_id: str) -> None:
        self.query_one("#main-tabs", TabbedContent).active = tab_id

    def _report_error(self, operation: str, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"
        self.log_message(f"ERROR   |  {operation}  |  {message}")
        self.notify(message, title=f"{operation} failed", severity="error", timeout=7)

    def _status(
        self,
        *,
        system: str | None = None,
        device: str | None = None,
        protocol: str | None = None,
    ) -> None:
        values = {"system": system, "device": device, "protocol": protocol}
        for name, value in values.items():
            if value is not None:
                self.query_one(f"#status-{name}", Static).update(f"{name.upper()}\n{value}")

    def _current_target(self) -> tuple[str, str] | None:
        address = self.query_one("#address", Input).value.strip()
        value = self.query_one("#pid", Select).value
        if not address or value is Select.BLANK:
            return None
        return address, str(value)

    def _link_event(self, message: str) -> None:
        """Relay link lifecycle messages, and revoke EQ access if the link died.

        The manager reports drops the moment they happen, so the lock no longer
        waits for the next write to discover the speaker is gone.
        """
        with contextlib.suppress(Exception):  # events can arrive before mount
            self.log_message(message)
            if self._verified_target is not None and not self._eq_access_allowed():
                self._invalidate_connection("The verified link dropped")

    def _eq_access_allowed(self) -> bool:
        """True only while the exact link that was verified is still up.

        Matching the address alone would authorise a write over a link opened
        after the probe, which is not the link anything was verified against.
        """
        if self._verified_target is None:
            return False
        address, pid, generation = self._verified_target
        if (address, pid) != self._current_target():
            return False
        return self.manager.holds_generation(address, generation)

    def _set_eq_access(self, allowed: bool, reason: str) -> None:
        if not allowed:
            self._verified_target = None
        content = self.query_one("#main-tabs", TabbedContent)
        if allowed:
            content.enable_tab("eq-tab")
        else:
            content.disable_tab("eq-tab")
            if content.active == "eq-tab":
                content.active = "device-tab"
        for selector in (
            "#profile-tier",
            "#profile",
            "#gains",
            "#read",
            "#preview",
            "#save-profile",
            "#delete-profile",
            "#apply",
        ):
            self.query_one(selector).disabled = not allowed
        if not allowed:
            self._reset_danger_arm()
        self._update_eq_guide(allowed, reason)

    # Actions that need a verified speaker. Disabling the buttons is not enough:
    # a key binding does not consult widget.disabled, so 'r' and 'w' reached the
    # EQ path with the controls greyed out and the tab locked.
    EQ_ACTIONS: ClassVar = frozenset({"read", "preview", "save_profile", "delete_profile"})

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return not (action in self.EQ_ACTIONS and not self._eq_access_allowed())

    def _reload_user_profiles(self) -> None:
        try:
            self._user_profiles = load_user_profiles()
        except ProfileStoreError as exc:
            self._user_profiles = []
            self.log_message(f"ERROR   |  Saved profiles  |  {exc}")
            self.notify(str(exc), title="Saved profiles unavailable", severity="error")

    def _profile(self, key: str) -> SoundProfile:
        """Look a profile up across every tier.

        User profiles cannot live in the built-in registry -- the store imports
        the presets, so the presets cannot import the store -- so the lookup is
        joined here instead.
        """
        try:
            return get_profile(key)
        except ValueError:
            for profile in self._user_profiles:
                if profile.key == key:
                    return profile
            raise

    def _lab_profile(self) -> bool:
        """Whether the selected profile opts in to the extended-gain encoder.

        This alone gates allow_extended, so a hand-typed 24 on a STANDARD
        profile still gets rejected by the model's own step/range validation
        rather than being silently routed through the LAB encoder.
        """
        try:
            return self._profile(self._profile_key()).dangerous
        except ValueError:
            return False

    def _dangerous_profile(self) -> bool:
        """Whether what is on screen needs the extended-gain confirmation.

        Keyed on the actual gains, not on LAB membership: the gain field is free
        text, so typing +24 dB under a STANDARD profile must still be confirmed,
        while a LAB profile that only cuts must not be -- labelling a deep cut
        "DANGER" is crying wolf, and that is what makes people stop reading the
        real warnings.

        The cuts-are-free exemption only applies where a gain is a dB value the
        DSP applies. On the level-index encoders it is an index into a firmware
        table, so -100 is not "very quiet", it is a table entry that does not
        exist -- there, magnitude in either direction is what matters.
        """
        try:
            if self._profile(self._profile_key()).boosts_past_standard:
                return True
        except ValueError:
            pass
        try:
            gains = self._gains()
        except ValueError:
            return False
        if not self._gains_are_decibels():
            return any(abs(gain) > STANDARD_MAX_GAIN_DB for gain in gains)
        return any(gain > STANDARD_MAX_GAIN_DB for gain in gains)

    def _gains_are_decibels(self) -> bool:
        """Whether this model's wire value is a dB gain rather than a table index.

        Only the float-parametric encoders carry a real dB value; EQ_BALANCE and
        PRESET_EQ models send a level index, and reasoning about clipping does not
        transfer to those.
        """
        try:
            features = set(get_model(self._pid()).get("features", []))
        except (ValueError, KeyError):
            return False
        return "7_BANDS_EQ" in features or "PROTOCOL_4" in features

    def _update_eq_guide(self, allowed: bool | None = None, reason: str = "") -> None:
        permitted = self._eq_access_allowed() if allowed is None else allowed
        if not permitted:
            message = f"LOCKED  {reason}. Press SCAN, or RE-VERIFY SELECTED, on the Device tab."
        elif self._dangerous_profile():
            message = "DANGER / LAB +/-24 dB  Extended float gains; use very low volume and confirm Apply twice."
        else:
            message = "CONNECTED + VERIFIED  Standard profiles stay inside the model's APK UI range."
        self.query_one("#eq-guide", Static).update(message)

    def _arm_signature(self) -> tuple[str, str]:
        """What an arm is armed *for*: the exact profile and gains on screen."""
        return (
            str(self.query_one("#profile", Select).value),
            self.query_one("#gains", Input).value.strip(),
        )

    def _danger_armed(self) -> bool:
        """True only if the arm still refers to what is currently on screen.

        Keying the arm to its contents rather than to wall-clock alone means any
        edit between the two clicks -- including one the app makes itself while
        loading a profile -- invalidates it, instead of a queued event silently
        clearing the arm and letting a single click through.
        """
        return (
            self._danger_arm_profile == repr(self._arm_signature())
            and time.monotonic() <= self._danger_armed_until
        )

    def _reset_danger_arm(self) -> None:
        self._danger_armed_until = 0.0
        self._danger_arm_profile = None
        self.query_one("#apply", Button).label = (
            "APPLY DANGEROUS PROFILE" if self._dangerous_profile() else "APPLY TO SPEAKER"
        )

    def _update_profile_mode(self) -> None:
        dangerous = self._dangerous_profile()
        self._reset_danger_arm()
        self.query_one("#apply-guide", Static).update(
            "DANGER  Extended gain can cause clipping or hardware damage. First click arms; second click writes."
            if dangerous
            else "DIRECT APPLY  Standard profiles stay within the model's APK UI gain range."
        )
        self._update_eq_guide()

    def _invalidate_connection(self, reason: str) -> None:
        was_verified = self._verified_target is not None
        self._set_eq_access(False, reason)
        if was_verified:
            self._status(device="NOT VERIFIED")
            self.log_message(f"LOCK    |  EQ controls disabled  |  {reason}")

    def _require_eq_access(self) -> None:
        if not self._eq_access_allowed():
            self._set_eq_access(False, "Speaker connection has not been verified")
            raise RuntimeError("connect and verify the selected speaker before using EQ")

    def _address(self) -> str:
        value = self.query_one("#address", Input).value.strip()
        if not value:
            raise ValueError("select or enter a BLE address first")
        return value

    def _pid(self) -> str:
        value = self.query_one("#pid", Select).value
        if value is Select.BLANK:
            raise ValueError("select a model PID")
        return str(value)

    def _profile_key(self) -> str:
        value = self.query_one("#profile", Select).value
        if value is Select.BLANK or value == EMPTY_TIER_KEY:
            # Guarded here, where it is consumed. Producing the sentinel is fine;
            # letting it escape as a profile key is what raised ValueError out of
            # the Textual message pump and killed the app on the next PID change.
            raise ValueError("no sound profile is selected; save one or switch tier")
        return str(value)

    def _gains(self) -> list[float]:
        raw = self.query_one("#gains", Input).value.replace(",", " ")
        values = [float(item) for item in raw.split()]
        if not values:
            raise ValueError("enter at least one gain")
        return values

    def _save_context(self) -> None:
        self.settings.last_address = self.query_one("#address", Input).value.strip()
        self.settings.last_pid = self._pid()
        self.settings.save()

    def _reload_current_profile(self) -> None:
        """Re-resolve whatever profile is selected, if one actually is.

        An empty MY PROFILES tier parks the dropdown on a sentinel that is not a
        profile. Callers on the PID-change path have no profile to reload then,
        and must not raise out of the Textual message pump for it.
        """
        try:
            key = self._profile_key()
        except ValueError:
            return
        self._load_profile(key)

    def _load_profile(self, key: str) -> None:
        pid = self._pid()
        profile = self._profile(key)
        count = gain_count_for_pid(pid)
        if count:
            try:
                gains = resolve_curve(pid, profile)
                self.query_one("#gains", Input).value = ", ".join(f"{gain:g}" for gain in gains)
                self.query_one("#curve", Static).update(
                    f"CURVE  {sparkline(gains)}  /  RANGE {min(gains):+g} .. {max(gains):+g} dB"
                )
            except ValueError as exc:
                self.query_one("#gains", Input).value = ""
                self.query_one("#curve", Static).update(f"UNSUPPORTED  {exc}")
        else:
            self.query_one("#gains", Input).value = ""
            self.query_one("#curve", Static).update("CURVE  -  This APK declares no EQ controls for the selected PID")
        self.query_one("#profile-info", Static).update(
            f"{'[DANGER]  ' if profile.boosts_past_standard else ''}{profile.name.upper()}  /  {profile.description}"
        )
        self._update_profile_mode()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        address = str(event.row_key.value)
        row = self._scan_rows.get(address)
        if row:
            self._select_scan_row(row, automatic=False)

    def _select_scan_row(self, row: dict[str, Any], *, automatic: bool) -> None:
        self._invalidate_connection("Device selection changed")
        address = str(row["address"])
        name = str(row["name"] or "UNNAMED")
        detection = row.get("jbl_detection", {})
        pid = detection.get("pid")
        live = bool(row.get("live", row.get("rssi") is not None))
        signal = "LIVE / NOT VERIFIED" if live else "PAIRED CACHE / OFFLINE"
        self.query_one("#address", Input).value = address
        if pid:
            self.query_one("#pid", Select).value = str(pid)
            # Refresh the gains for the new PID now, synchronously. Select.Changed
            # is posted, so waiting for it would leave the previous model's gains
            # paired with this PID -- and it posts nothing at all when the value
            # is unchanged, which would leave the curve stale forever.
            self._reload_current_profile()
            model = str(detection["model"])
            confidence = str(detection["confidence"]).upper()
            reason = str(detection["reason"])
            mode = "AUTO" if automatic else "SELECTED"
            self._status(device=f"{mode}  {model}  {signal}")
            self.query_one("#detect-guide", Static).update(
                f"AUTO-DETECTED  {model} / PID {pid} / {confidence} confidence / {reason}"
            )
            self.log_message(f"DETECT  |  {model}  |  PID {pid}  |  {confidence}  |  {reason}  |  {address}")
            self.notify(
                (
                    f"{model} / PID {pid} ({confidence} confidence). Press RE-VERIFY SELECTED."
                    if live
                    else f"{model} is known to Windows but was not seen over BLE. Wake it and scan again."
                ),
                title="JBL auto-detected",
                severity="information" if live else "warning",
            )
            return
        self._status(device=f"SELECTED  {name}  {signal}")
        self.query_one("#detect-guide", Static).update(
            "JBL signature found, but PID is unresolved. Select the model manually before probing."
            if detection.get("is_jbl")
            else "No JBL signature in this advertisement. Select another result or choose the model manually."
        )
        self.log_message(f"SELECT  |  {name}  |  PID unresolved  |  {address}")
        self.notify(f"Selected {name}; model was not auto-detected.", title="Manual model selection required")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        if event.select.id == "pid":
            if self._verified_target is not None and not self._eq_access_allowed():
                self._invalidate_connection("Model profile changed")
            pid = str(event.value)
            model = summarize_model(next(model for model in all_models() if str(model.get("pid")) == pid))
            self._status(protocol=f"PROFILE  {model['eq_path']}")
            self._reload_current_profile()
            self.log_message(f"MODEL   |  {model['name']}  |  PID {pid}  |  {model['eq_path']}")
        elif event.select.id == "profile-tier":
            tier = str(event.value)
            self._show_tier(tier)
            self.log_message(f"MODE    |  {TIER_LABELS[tier]}")
        elif event.select.id == "profile":
            if str(event.value) != EMPTY_TIER_KEY:
                self._load_profile(str(event.value))

    def _tier(self) -> str:
        value = self.query_one("#profile-tier", Select).value
        return "standard" if value is Select.BLANK else str(value)

    def _tier_options(self, tier: str) -> list[tuple[str, str]]:
        if tier == "user":
            self._reload_user_profiles()
            return user_profile_options()
        return profile_options(dangerous=tier == "lab")

    def _show_tier(self, tier: str, *, select: str | None = None) -> None:
        """Repopulate the profile dropdown for a tier and load a profile from it.

        Everything here is synchronous on purpose. Select.Changed is posted rather
        than called, so a caller that set the tier and then set a profile from the
        new tier in the next line would be assigning a value the dropdown does not
        yet offer.
        """
        options = self._tier_options(tier)
        profile_select = self.query_one("#profile", Select)
        self.query_one("#delete-profile", Button).display = tier == "user"
        if not options:
            # An empty saved list would leave Select with nothing to show, so say
            # how to fill it rather than presenting a dead dropdown.
            profile_select.set_options([(EMPTY_TIER_LABEL, EMPTY_TIER_KEY)])
            profile_select.value = EMPTY_TIER_KEY
            self.query_one("#gains", Input).value = ""
            self.query_one("#curve", Static).update("CURVE  -  Build a curve, then press SAVE AS to keep it here")
            self.query_one("#profile-info", Static).update(
                "MY PROFILES  /  Empty. Pick any profile, edit the gains, then SAVE AS to store it."
            )
            # Not just the arm: the apply guide is whatever the previous tier left
            # there, so an empty tier used to keep a DANGER warning on screen for
            # a dropdown holding nothing at all.
            self._update_profile_mode()
            return
        keys = [key for _, key in options]
        if select in keys:
            wanted = str(select)
        elif profile_select.value in keys:
            # Keep the current profile when it survives the switch: Select posts a
            # Changed for its initial value too, so resetting unconditionally
            # silently replaced the Balanced default at startup.
            wanted = str(profile_select.value)
        else:
            wanted = options[0][1]
        profile_select.set_options(options)
        profile_select.value = wanted
        self._load_profile(wanted)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "address":
            if self._verified_target is not None and not self._eq_access_allowed():
                self._invalidate_connection("Device address changed")
            return
        if event.input.id != "gains" or not event.value.strip():
            return
        try:
            gains = self._gains()
            self.query_one("#curve", Static).update(
                f"CUSTOM  {sparkline(gains)}  /  RANGE {min(gains):+g} .. {max(gains):+g} dB"
            )
            # Not just the arm: an edit past the standard range flips the whole
            # apply surface to its extended-gain wording, so the button and the
            # guide have to agree about what the next click will do.
            self._update_profile_mode()
        except ValueError:
            self.query_one("#curve", Static).update("CUSTOM - invalid numeric gain list")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "scan": self.action_scan,
            "probe": self.action_probe,
            "read": self.action_read,
            "preview": self.action_preview,
            "save-profile": self.action_save_profile,
            "delete-profile": self.action_delete_profile,
        }
        if event.button.id in actions:
            actions[event.button.id]()
        elif event.button.id == "apply":
            self.apply_eq()

    def action_scan(self) -> None:
        self.scan_worker()

    def action_device_tab(self) -> None:
        self._show_tab("device-tab")

    def action_eq_tab(self) -> None:
        if self._eq_access_allowed():
            self._show_tab("eq-tab")
        else:
            self._show_tab("device-tab")
            self.notify(
                "Press SCAN, or select a speaker and press RE-VERIFY SELECTED, first.",
                title="Equalizer locked",
                severity="warning",
            )

    def action_activity_tab(self) -> None:
        self._show_tab("activity-tab")

    async def _scan(self) -> list[dict[str, Any]]:
        """Scan and fill the table. A plain coroutine so it can be chained.

        Calling one @work method from inside another cancels the caller, because
        they share the default exclusive group -- so the auto-setup chain drives
        these bodies directly instead.
        """
        self._invalidate_connection("A new device scan started")
        self._status(system="SCANNING BLE...")
        self.log_message("SCAN    |  Listening for BLE advertisements...")
        rows = await scan_ble(self.settings.scan_seconds)
        table = self.query_one("#devices", DataTable)
        table.clear()
        self._scan_rows = {str(row["address"]): row for row in rows}
        for row in rows:
            detection = row["jbl_detection"]
            table.add_row(
                row["name"] or "<unnamed>",
                detection["model"] or ("JBL / unresolved" if detection["is_jbl"] else "-"),
                detection["pid"] or "-",
                "LIVE" if row.get("live", row["rssi"] is not None) else "PAIRED CACHE",
                "-" if row["rssi"] is None else f"{row['rssi']} dBm",
                row["address"],
                key=row["address"],
            )
        signal_rows = [row for row in rows if row["rssi"] is not None]
        strongest = f"  |  strongest {max(row['rssi'] for row in signal_rows)} dBm" if signal_rows else ""
        self.log_message(f"SCAN    |  Complete  |  {len(rows)} devices{strongest}")
        return rows

    def _auto_candidate(self, rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
        """Pick the speaker to set up automatically, or decline and say why.

        Auto-setup that picks the wrong speaker is worse than one that asks, so
        a weak signal or a near-tie declines rather than guessing.
        """
        live = [
            row
            for row in rows
            if row["jbl_detection"]["pid"] and row.get("live", row["rssi"] is not None) and row["rssi"] is not None
        ]
        if not live:
            return None, "no live JBL with a resolved PID was advertising"
        ranked = sorted(live, key=lambda row: -int(row["rssi"]))
        best = ranked[0]
        if int(best["rssi"]) < AUTO_SELECT_RSSI_FLOOR:
            return None, f"the strongest JBL is only {best['rssi']} dBm, too weak to verify reliably"
        if len(ranked) > 1 and int(best["rssi"]) - int(ranked[1]["rssi"]) < AUTO_SELECT_MARGIN_DB:
            return None, f"{len(ranked)} JBL speakers are within {AUTO_SELECT_MARGIN_DB} dB; pick one from the table"
        return best, f"{best['rssi']} dBm, clear of the runner-up"

    async def _verify(self, address: str, pid: str) -> dict[str, Any]:
        """Connect, hold the link open, and verify the EQ route over it.

        The link stays in the manager afterwards, so the write path uses the very
        link that was verified rather than opening a fresh, unverified one.
        """
        selected_row = self._scan_rows.get(address)
        if selected_row is not None and not selected_row.get("live", selected_row.get("rssi") is not None):
            raise RuntimeError(
                "this is cached Windows pairing metadata, not a live BLE advertisement; "
                "wake the speaker and scan again"
            )
        self._save_context()
        self._status(system="CONNECTING...", device="CONNECTING")
        link = await self.manager.acquire(address)
        self._status(system="VERIFYING...", device="CONNECTED")
        self.log_message(f"PROBE   |  PID {pid}  |  Read-only multi-generation capability check")
        result = await probe_link(link, pid=pid, timeout=self.settings.timeout)
        firmware = "unknown"
        decoded = result["probes"]["firmware"].get("decoded", [])
        if decoded:
            firmware = decoded[0].get("firmware_version", "unknown")
        services = len(result.get("services", []))
        supported = [name for name, item in result["probes"].items() if item["status"] == "supported-response"]
        eq_path = str(result["detected_eq_path"])
        if eq_path == "no-supported-eq-response":
            raise RuntimeError("connection succeeded, but no supported EQ response was detected")
        self._verified_target = (address, pid, link.generation)
        self._set_eq_access(True, "Connection and EQ route verified")
        self._status(
            system="READY - VERIFIED",
            device=f"VERIFIED  FW {firmware}  {services} SERVICES",
            protocol=f"{eq_path}  [{', '.join(supported) or 'none'}]",
        )
        self.log_message(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    @work(exclusive=True, group="setup")
    async def scan_worker(self) -> None:
        """One press: scan, pick, connect, verify, open the Equalizer.

        It stops at the Equalizer and never writes -- an automatic EQ write to
        real hardware is not something a scan button should be able to cause.
        """
        try:
            rows = await self._scan()
            candidate, reason = self._auto_candidate(rows)
            if candidate is None:
                self._status(system=f"READY - {len(rows)} DEVICES")
                self.log_message(f"AUTO    |  Declined to auto-select  |  {reason}")
                self.notify(
                    f"Found {len(rows)} device(s), but auto-setup stopped: {reason}.",
                    title="Pick a speaker",
                    severity="warning",
                )
                return
            self.log_message(f"AUTO    |  Selected {candidate['address']}  |  {reason}")
            self._select_scan_row(candidate, automatic=True)
            address, pid = str(candidate["address"]), str(candidate["jbl_detection"]["pid"])
            result = await self._verify(address, pid)
            self._show_tab("eq-tab")
            self.notify(
                f"{result['detected_eq_path']} verified. The Equalizer is unlocked; nothing has been written.",
                title="Ready",
            )
        except asyncio.CancelledError:
            self._status(system="CANCELLED")
            self.log_message("AUTO    |  Cancelled")
            raise
        except Exception as exc:
            self._set_eq_access(False, "Automatic setup failed")
            self._status(system="AUTO SETUP FAILED", device="OFFLINE / ERROR")
            self._report_error("Auto setup", exc)

    def action_probe(self) -> None:
        self.probe_worker()

    @work(exclusive=True, group="setup")
    async def probe_worker(self) -> None:
        try:
            result = await self._verify(self._address(), self._pid())
            self.notify(f"EQ path {result['detected_eq_path']} verified.", title="Verify complete")
        except asyncio.CancelledError:
            self._status(system="CANCELLED")
            raise
        except Exception as exc:
            self._set_eq_access(False, "Connection or EQ verification failed")
            self._status(system="VERIFY FAILED", device="OFFLINE / ERROR")
            self._report_error("Verify", exc)

    def action_read(self) -> None:
        self.read_worker()

    def _verified_link(self) -> Link:
        """The live link this session was verified against."""
        self._require_eq_access()
        address, _pid, _generation = self._verified_target  # type: ignore[misc]
        link = self.manager.live(address)
        if link is None:
            self._set_eq_access(False, "The verified link is gone")
            raise RuntimeError("the verified link is no longer up; re-verify the speaker")
        return link

    @work(exclusive=True, group="read")
    async def read_worker(self) -> None:
        """Its own group, not the write group.

        Sharing "eq" with apply_worker meant pressing 'r' cancelled an apply that
        already had a frame on the wire but had not read back yet -- one keystroke
        defeating the readback evidence the whole apply path exists to produce.
        """
        try:
            link = self._verified_link()
            path, frames = auto_read_frames(self._pid())
            self._status(system="READING EQ...", protocol=path)
            self.log_message(f"READ    |  {path}  |  {len(frames)} frame(s)")
            replies: list[bytes] = []
            for frame in frames:
                replies.extend((await link.transact(frame, self.settings.timeout)).replies)
            for reply in replies:
                self.log_message(json.dumps(describe_frame(reply), ensure_ascii=False, indent=2))
            self._status(system=f"READY - {len(replies)} REPLY")
            self.notify(f"Received {len(replies)} reply frame(s).", title="EQ read complete")
        except asyncio.CancelledError:
            self._status(system="CANCELLED")
            raise
        except Exception as exc:
            self._status(system="READ FAILED")
            self._report_error("Read", exc)

    def action_preview(self) -> None:
        try:
            self._require_eq_access()
            request = self._resolve_write_request()
            pid, gains, dangerous = request.pid, request.gains, request.dangerous
            path, frames = auto_eq_frames(pid, gains, allow_extended=request.allow_extended)
            self._status(system="PREVIEW READY", protocol=path)
            self.log_message(
                f"PREVIEW |  {path}  |  profile={request.profile}  |  "
                f"dangerous={dangerous}  |  gains={gains}\n"
                + "\n".join(f"TX      |  {hex_bytes(frame)}" for frame in frames)
            )
            append_audit(
                "eq-preview",
                address=request.address,
                pid=pid,
                applied=False,
                details={
                    "profile": request.profile,
                    "path": path,
                    "gains": gains,
                    "dangerous": dangerous,
                },
            )
            self.notify("Packet is ready. Review it in Activity before applying.", title="Preview complete")
        except Exception as exc:
            self._status(system="PREVIEW REJECTED")
            self.log_message(f"REJECT  |  Preview  |  {exc}")
            self.notify(str(exc), title="Preview rejected", severity="warning")

    def _resolve_write_request(self) -> WriteRequest:
        """Freeze the whole write identity in one synchronous pass.

        Everything downstream reads this instead of the widgets, so nothing the
        UI does mid-write can change what gets sent.
        """
        return WriteRequest(
            address=self._address(),
            pid=self._pid(),
            profile=self._profile_key(),
            gains=self._gains(),
            allow_extended=self._lab_profile(),
            dangerous=self._dangerous_profile(),
        )

    def action_save_profile(self) -> None:
        """Save whatever curve is on screen under a name of the user's choosing.

        The curve is stored on the reference grid rather than as this model's band
        values, so a profile saved on one speaker still means something on the next.
        """
        try:
            pid, gains = self._pid(), self._gains()
            curve = curve_from_model_gains(pid, gains)
        except ValueError as exc:
            self.notify(str(exc), title="Nothing to save", severity="warning")
            return

        def store(name: str | None) -> None:
            if not name:
                return
            try:
                profile = save_user_profile(name, curve, description=curve_summary(curve), overwrite=True)
            except (ValueError, ProfileStoreError) as exc:
                self.log_message(f"REJECT  |  Save profile  |  {exc}")
                self.notify(str(exc), title="Could not save", severity="error")
                return
            self.log_message(f"SAVE    |  {profile.name}  |  {profile.key}  |  {list(profile.gains)}")
            self.query_one("#profile-tier", Select).value = "user"
            # Directly, not via the posted Changed the line above will raise: the
            # dropdown has to be holding the new profile before it can be selected.
            self._show_tier("user", select=profile.key)
            self.notify(f"Saved as {profile.name}; find it under MY PROFILES.", title="Profile saved")

        self.push_screen(NamePrompt(f"Curve on screen: {curve_summary(curve)}"), store)

    def action_delete_profile(self) -> None:
        key = self._profile_key()
        if not key.startswith("user-"):
            self.notify("Only your own saved profiles can be deleted.", title="Not a saved profile", severity="warning")
            return
        try:
            removed = delete_user_profile(key)
        except ProfileStoreError as exc:
            self.notify(str(exc), title="Could not delete", severity="error")
            return
        if not removed:
            return
        self.log_message(f"DELETE  |  {key}")
        self._reload_user_profiles()
        self._show_tier("user")
        self.notify("Profile deleted.", title="Saved profiles")

    def apply_eq(self) -> None:
        try:
            self._require_eq_access()
            request = self._resolve_write_request()
        except Exception as exc:
            self._show_tab("device-tab")
            self._status(system="EQ LOCKED")
            self.log_message(f"BLOCK   |  Apply  |  {exc}")
            self.notify(str(exc), title="Equalizer locked", severity="warning")
            return
        if request.dangerous and not self._danger_armed():
            self._danger_armed_until = time.monotonic() + 8.0
            self._danger_arm_profile = repr(self._arm_signature())
            self.query_one("#apply", Button).label = "CONFIRM DANGER APPLY"
            self._status(system="DANGER ARMED", protocol="LAB +/-24 dB | CLICK APPLY AGAIN")
            self.log_message("ARM     |  Extended-gain write armed for 8 seconds; no packet sent")
            self.notify(
                "No packet sent. Click Apply again within 8 seconds to write the extended profile.",
                title="Dangerous profile armed",
                severity="warning",
                timeout=8,
            )
            return
        self._reset_danger_arm()
        self._show_tab("activity-tab")
        self.apply_worker(request)

    @work(exclusive=True, group="eq")
    async def apply_worker(self, request: WriteRequest) -> None:
        transaction_id = uuid.uuid4().hex[:8].upper()
        started = time.perf_counter()
        address, pid, gains = request.address, request.pid, request.gains
        path = "unknown"
        frames: list[bytes] = []
        write_replies: list[bytes] = []
        read_frames: list[bytes] = []
        precheck_replies: list[bytes] = []
        read_replies: list[bytes] = []
        frames_written = 0
        reconnects = 0
        try:
            link = self._verified_link()
            path, frames = auto_eq_frames(pid, gains, allow_extended=request.allow_extended)
            read_path, read_frames = auto_read_frames(pid)
            self._save_context()
            target = target_fingerprint(address)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self._status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
            self.log_message(
                f"\nTXN     |  {transaction_id}  |  BEGIN {timestamp}\n"
                f"TARGET  |  hash={target}  |  PID={pid}  |  profile={request.profile}  |  "
                f"dangerous={request.dangerous}\n"
                f"ROUTE   |  write={path}  |  readback={read_path}\n"
                f"REQUEST |  gains={gains}  |  frames={len(frames)}"
            )
            self._status(system=f"PRECHECK {transaction_id}", protocol=f"{read_path} | READING BEFORE")
            for index, frame in enumerate(read_frames, 1):
                self.log_message(f"PRECHECK|  TX {index}/{len(read_frames)}  |  {hex_bytes(frame)}")
                transaction = await link.transact(frame, self.settings.timeout)
                precheck_replies.extend(transaction.replies)
                self.log_message(f"PRECHECK|  RX {index}/{len(read_frames)}  |  {len(transaction.replies)} frame(s)")
            # Snapshot taken before the first write is issued, and never recomputed.
            # Re-reading it after an attempt that already landed would report the
            # write as "already matched" when it was this write that changed things.
            precheck = verify_eq_readback(gains, precheck_replies)
            self.log_message(
                f"BEFORE  |  status={precheck.status}  |  actual={precheck.actual}  |  delta={precheck.deltas}"
            )
            self._status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
            ack_error = False
            authorised_generation = link.generation
            for index, frame in enumerate(frames, 1):
                # Re-checked per frame, not once at the top. Authorisation is
                # against a specific link; if it dropped and came back mid-write
                # the revocation has already happened, and continuing to write
                # would defeat the mechanism that exists to stop exactly this.
                if link.generation != authorised_generation:
                    raise RuntimeError(
                        f"the link was rebuilt after frame {index - 1}/{len(frames)}; "
                        "the write was not completed over the link it was verified against"
                    )
                self.log_message(f"WRITE   |  TX {index}/{len(frames)}  |  {hex_bytes(frame)}")
                # Counted before the await, not after. transact() puts the frame
                # on the wire and only then waits for a reply, so counting on
                # return meant a timeout or a cancellation recorded applied=false
                # for bytes the speaker had already received.
                frames_written += 1
                transaction = await link.transact(frame, self.settings.timeout)
                reconnects += transaction.reconnects
                write_replies.extend(transaction.replies)
                self.log_message(
                    f"WRITE   |  RX {index}/{len(frames)}  |  {len(transaction.replies)} frame(s)  |  "
                    f"attempts={transaction.attempts}  reconnects={transaction.reconnects}"
                )
                for reply in transaction.replies:
                    self.log_message(f"ACK RAW |  {hex_bytes(reply)}")
                    try:
                        decoded = describe_frame(reply)
                        ack_error = ack_error or decoded.get("command") == 0xEE
                        self.log_message("ACK DEC |  " + json.dumps(decoded, ensure_ascii=False))
                    except ValueError as exc:
                        self.log_message(f"ACK DEC |  undecodable: {exc}")
            ack = "REJECTED" if ack_error else ("RECEIVED" if write_replies else "MISSING")
            self._status(system=f"VERIFYING {transaction_id}", protocol=f"{path} | ACK {ack}")
            self.log_message(f"ACK     |  {ack}  |  total={len(write_replies)} frame(s)")
            for index, frame in enumerate(read_frames, 1):
                self.log_message(f"READBACK|  TX {index}/{len(read_frames)}  |  {hex_bytes(frame)}")
                transaction = await link.transact(frame, self.settings.timeout)
                read_replies.extend(transaction.replies)
                self.log_message(f"READBACK|  RX {index}/{len(read_frames)}  |  {len(transaction.replies)} frame(s)")
                for reply in transaction.replies:
                    self.log_message(f"STATE   |  RAW {hex_bytes(reply)}")
                    try:
                        self.log_message("STATE   |  DEC " + json.dumps(describe_frame(reply), ensure_ascii=False))
                    except ValueError as exc:
                        self.log_message(f"STATE   |  undecodable: {exc}")
            verification = verify_eq_readback(gains, read_replies)
            # Three states, not two. "mismatch" means we decoded the pre-state and
            # it differed; "verified" means it already matched; anything else means
            # we never decoded it and know nothing -- which must not be reported as
            # having matched.
            changed = precheck.status == "mismatch" and verification.verified
            already_matched = precheck.verified and verification.verified
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.log_message(
                f"VERIFY  |  {verification.status.upper()}  |  source={verification.source}\n"
                f"EXPECT  |  {verification.expected}\n"
                f"ACTUAL  |  {verification.actual}\n"
                f"DELTA   |  {verification.deltas}\n"
                f"RESULT  |  {verification.message}\n"
                f"PROOF   |  ack={ack}  |  state_changed={changed}  |  before={precheck.status}  |  "
                f"reconnects={reconnects}\n"
                f"TXN     |  {transaction_id}  |  END  |  {elapsed_ms} ms"
            )
            append_audit(
                "eq-apply",
                address=address,
                pid=pid,
                applied=True,
                details={
                    "transaction_id": transaction_id,
                    "profile": request.profile,
                    "dangerous": request.dangerous,
                    "path": path,
                    "gains": gains,
                    "tx": [hex_bytes(frame) for frame in frames],
                    "write_rx": [hex_bytes(reply) for reply in write_replies],
                    "ack": ack,
                    "reconnects": reconnects,
                    "precheck_rx": [hex_bytes(reply) for reply in precheck_replies],
                    "precheck": precheck.as_dict(),
                    "readback_tx": [hex_bytes(frame) for frame in read_frames],
                    "readback_rx": [hex_bytes(reply) for reply in read_replies],
                    "verification": verification.as_dict(),
                    "elapsed_ms": elapsed_ms,
                },
            )
            if verification.verified and ack == "RECEIVED":
                # A write delivered across a reconnect cannot claim "already
                # matched": the link was rebuilt underneath it, so the pre-write
                # snapshot no longer describes what the speaker saw.
                if reconnects:
                    outcome = "WROTE (after reconnect) + VERIFIED"
                    detail = f"The link dropped and recovered {reconnects} time(s) during this write."
                elif changed:
                    outcome = "CHANGED + VERIFIED"
                    detail = "The pre-write state was different."
                elif already_matched:
                    outcome = "ALREADY MATCHED + VERIFIED"
                    detail = "The requested state already matched."
                else:
                    # The readback proves where the speaker ended up, but the
                    # pre-state never decoded, so whether this write changed
                    # anything is simply unknown. Say that instead of guessing.
                    outcome = "WROTE + VERIFIED (prior state unknown)"
                    detail = f"The pre-write state could not be read ({precheck.status}), so the change is unconfirmed."
                self._status(system="WRITE VERIFIED", protocol=f"{path} | {outcome}")
                self.notify(
                    f"Write response received; every EQ band matched read-back. {detail}",
                    title="Write verified",
                )
            elif verification.verified:
                self._status(system="STATE MATCH / ACK ISSUE", protocol=f"{path} | ACK {ack}")
                self.notify(
                    f"Read-back matches, but the write acknowledgement is {ack.lower()}.",
                    title="Write not fully verified",
                    severity="warning",
                )
            elif verification.status == "mismatch":
                self._status(system="WRITE MISMATCH", protocol=f"{path} | READBACK DIFFERS")
                self.notify(verification.message, title="Write verification failed", severity="error")
            else:
                self._status(system="WRITE UNVERIFIED", protocol=f"{path} | NO DECODABLE READBACK")
                self.notify(verification.message, title="Write not verified", severity="warning")
        except BaseException as exc:
            # BaseException, not Exception: a cancelled apply that already put
            # frames on the wire must still leave a record of what it sent.
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.log_message(
                f"TXN     |  {transaction_id}  |  FAILED  |  frames_written={frames_written}/{len(frames)}  |  "
                f"{type(exc).__name__}: {exc}  |  {elapsed_ms} ms"
            )
            if address:
                append_audit(
                    "eq-apply-failed",
                    address=address,
                    pid=pid or None,
                    applied=frames_written > 0,
                    details={
                        "transaction_id": transaction_id,
                        "path": path,
                        "gains": gains,
                        "frames_written": frames_written,
                        "frame_count": len(frames),
                        "reconnects": reconnects,
                        "write_rx": [hex_bytes(reply) for reply in write_replies],
                        "precheck_rx": [hex_bytes(reply) for reply in precheck_replies],
                        "readback_rx": [hex_bytes(reply) for reply in read_replies],
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": elapsed_ms,
                    },
                )
            if not isinstance(exc, Exception):  # cancellation, KeyboardInterrupt
                self._status(system="WRITE CANCELLED")
                raise
            self._status(system="WRITE FAILED")
            self._report_error("Apply", exc)


def main() -> None:
    OpenJBLApp().run()


if __name__ == "__main__":
    main()
