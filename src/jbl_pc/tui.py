"""Monochrome Textual workstation for discovery, inspection, and EQ control."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from .audit import append_audit
from .config import Settings
from .models import all_models, auto_eq_frames, auto_read_frames, gain_count_for_pid, summarize_model
from .presets import get_profile, profile_options, resolve_profile, sparkline
from .probe import probe_ble
from .protocol import describe_frame, hex_bytes
from .transport import BleTransport, scan_ble

MODEL_OPTIONS = [(f"{model.get('deviceName')}  ·  {model.get('pid')}", str(model.get("pid"))) for model in all_models()]


class JblControlApp(App[None]):
    TITLE = "JBL PC CONTROL"
    SUB_TITLE = "MONOCHROME BLUETOOTH / DSP WORKSTATION"
    CSS = """
    Screen { background: #000000; color: #eeeeee; }
    Header, Footer { background: #eeeeee; color: #000000; }
    #status-strip { height: 5; padding: 0 1; }
    .metric { width: 1fr; height: 4; border: tall #666666; padding: 0 1; margin-right: 1; }
    #status-safety { margin-right: 0; }
    #main-tabs { height: 1fr; }
    TabbedContent { background: #000000; }
    TabPane { padding: 0 1; background: #000000; }
    Tabs { background: #000000; color: #aaaaaa; }
    Tab.-active { background: #eeeeee; color: #000000; text-style: bold; }
    #setup { height: 7; }
    #setup > Vertical { width: 1fr; margin-right: 1; }
    #setup > Vertical:last-of-type { margin-right: 0; }
    .field-label { color: #999999; }
    Input, Select { background: #000000; color: #eeeeee; border: tall #666666; }
    Input:focus, Select:focus { border: tall #ffffff; }
    #devices { height: 1fr; border: tall #666666; background: #000000; }
    #profile-panel { height: 9; padding: 0 1; border: tall #888888; }
    #profile-row { height: 3; }
    #profile-row Select { width: 2fr; margin-right: 1; }
    #profile-row Input { width: 3fr; }
    #curve { height: 2; color: #ffffff; text-style: bold; }
    #profile-info { color: #aaaaaa; }
    #interlock { height: 4; padding: 0 1; border: tall #666666; }
    .actions { height: 4; align-vertical: middle; }
    .actions Button { min-width: 15; margin-right: 1; background: #111111; color: #eeeeee; border: tall #666666; }
    .actions Button:hover, .actions Button:focus { background: #eeeeee; color: #000000; border: tall #ffffff; }
    #apply { background: #eeeeee; color: #000000; text-style: bold; }
    #guard { width: 10; margin-left: 1; }
    #confirm { width: 13; }
    #log { height: 1fr; border: tall #666666; background: #000000; color: #dddddd; }
    """
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("s", "scan", "Scan"),
        ("p", "probe", "Probe"),
        ("r", "read", "Read EQ"),
        ("v", "preview", "Preview"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings.load()
        self._scan_rows: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="status-strip"):
            yield Static("SYSTEM\nREADY", id="status-system", classes="metric")
            yield Static("DEVICE\nNOT SELECTED", id="status-device", classes="metric")
            yield Static("PROTOCOL\nUNKNOWN", id="status-protocol", classes="metric")
            yield Static("SAFETY\nWRITE LOCKED", id="status-safety", classes="metric")
        with TabbedContent(initial="device-tab", id="main-tabs"):
            with TabPane("01  DEVICE", id="device-tab"):
                with Horizontal(id="setup"):
                    with Vertical():
                        yield Label("BLE ADDRESS / DEVICE ID", classes="field-label")
                        yield Input(
                            value=self.settings.last_address, placeholder="Scan, then select a row", id="address"
                        )
                    with Vertical():
                        yield Label("MODEL PROFILE", classes="field-label")
                        yield Select(MODEL_OPTIONS, value=self.settings.last_pid, allow_blank=False, id="pid")
                yield DataTable(id="devices", cursor_type="row", zebra_stripes=False)
                with Horizontal(classes="actions"):
                    yield Button("01  SCAN", id="scan")
                    yield Button("02  PROBE", id="probe")
            with TabPane("02  EQUALIZER", id="eq-tab"):
                with Vertical(id="profile-panel"):
                    yield Label("SOUND PROFILE", classes="field-label")
                    with Horizontal(id="profile-row"):
                        yield Select(profile_options(), value="balanced", allow_blank=False, id="profile")
                        yield Input(id="gains", placeholder="Model-aware gains")
                    yield Static(id="curve")
                    yield Static(id="profile-info")
                with Horizontal(id="interlock"):
                    yield Label("WRITE INTERLOCK  ", classes="field-label")
                    yield Switch(value=False, id="guard")
                    yield Input(placeholder="TYPE APPLY", id="confirm")
                with Horizontal(classes="actions"):
                    yield Button("03  READ EQ", id="read")
                    yield Button("04  PREVIEW", id="preview")
                    yield Button("05  APPLY", id="apply")
            with TabPane("03  ACTIVITY", id="activity-tab"):
                yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#devices", DataTable)
        table.add_columns("NAME", "ADDRESS", "RSSI", "MANUFACTURER DATA")
        self._load_profile("balanced")
        self.log_message("READY  |  Hardware writes are locked. Start with SCAN or select a known address.")

    def log_message(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _status(
        self,
        *,
        system: str | None = None,
        device: str | None = None,
        protocol: str | None = None,
        safety: str | None = None,
    ) -> None:
        values = {"system": system, "device": device, "protocol": protocol, "safety": safety}
        for name, value in values.items():
            if value is not None:
                self.query_one(f"#status-{name}", Static).update(f"{name.upper()}\n{value}")

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
        if value is Select.BLANK:
            raise ValueError("select a sound profile")
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

    def _load_profile(self, key: str) -> None:
        pid = self._pid()
        profile = get_profile(key)
        count = gain_count_for_pid(pid)
        if count:
            gains = resolve_profile(pid, key)
            self.query_one("#gains", Input).value = ", ".join(f"{gain:g}" for gain in gains)
            self.query_one("#curve", Static).update(
                f"CURVE  {sparkline(gains)}    "
                + "  ".join(f"B{index + 1} {gain:+g}" for index, gain in enumerate(gains))
            )
        else:
            self.query_one("#gains", Input).value = ""
            self.query_one("#curve", Static).update("CURVE  —  This APK declares no EQ controls for the selected PID")
        self.query_one("#profile-info", Static).update(
            f"{profile.name.upper()}  /  {profile.description}  /  TAGS: {', '.join(profile.tags) or 'general'}"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        address = str(event.row_key.value)
        row = self._scan_rows.get(address)
        if row:
            self.query_one("#address", Input).value = address
            name = row["name"] or "UNNAMED"
            self._status(device=f"SELECTED  {name}  {row['rssi']} dBm")
            self.log_message(f"SELECT  |  {name}  |  {address}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        if event.select.id == "pid":
            pid = str(event.value)
            model = summarize_model(next(model for model in all_models() if str(model.get("pid")) == pid))
            self._status(protocol=f"PROFILE  {model['eq_path']}")
            self._load_profile(self._profile_key())
            self.log_message(f"MODEL   |  {model['name']}  |  PID {pid}  |  {model['eq_path']}")
        elif event.select.id == "profile":
            self._load_profile(str(event.value))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "gains" or not event.value.strip():
            return
        try:
            gains = self._gains()
            self.query_one("#curve", Static).update(
                f"CUSTOM {sparkline(gains)}    "
                + "  ".join(f"B{index + 1} {gain:+g}" for index, gain in enumerate(gains))
            )
        except ValueError:
            self.query_one("#curve", Static).update("CUSTOM — invalid numeric gain list")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "guard":
            self._status(safety="ARMED — TYPE APPLY" if event.value else "WRITE LOCKED")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {"scan": self.action_scan, "probe": self.action_probe, "read": self.action_read}
        if event.button.id in actions:
            actions[event.button.id]()
        elif event.button.id == "preview":
            self.action_preview()
        elif event.button.id == "apply":
            self.apply_eq()

    def action_scan(self) -> None:
        self.scan_worker()

    @work(exclusive=True)
    async def scan_worker(self) -> None:
        self._status(system="SCANNING BLE…")
        self.log_message("SCAN    |  Listening for BLE advertisements…")
        try:
            rows = await scan_ble(self.settings.scan_seconds)
            table = self.query_one("#devices", DataTable)
            table.clear()
            self._scan_rows = {str(row["address"]): row for row in rows}
            for row in rows:
                table.add_row(
                    row["name"] or "<unnamed>",
                    row["address"],
                    f"{row['rssi']} dBm",
                    json.dumps(row["manufacturer_data"], separators=(",", ":")),
                    key=row["address"],
                )
            strongest = f"  |  strongest {rows[0]['rssi']} dBm" if rows else ""
            self._status(system=f"READY — {len(rows)} DEVICES")
            self.log_message(f"SCAN    |  Complete  |  {len(rows)} devices{strongest}")
        except Exception as exc:
            self._status(system="SCAN FAILED")
            self.log_message(f"ERROR   |  Scan  |  {type(exc).__name__}: {exc}")

    def action_probe(self) -> None:
        self.probe_worker()

    @work(exclusive=True)
    async def probe_worker(self) -> None:
        try:
            address, pid = self._address(), self._pid()
            self._save_context()
            self._status(system="PROBING…", device="CONNECTING")
            self.log_message(f"PROBE   |  PID {pid}  |  Read-only multi-generation capability check")
            result = await probe_ble(
                address,
                pid=pid,
                service_uuid=self.settings.service_uuid,
                rx_uuid=self.settings.rx_uuid,
                tx_uuid=self.settings.tx_uuid,
                timeout=self.settings.timeout,
            )
            firmware = "unknown"
            decoded = result["probes"]["firmware"].get("decoded", [])
            if decoded:
                firmware = decoded[0].get("firmware_version", "unknown")
            services = len(result.get("services", []))
            supported = [name for name, item in result["probes"].items() if item["status"] == "supported-response"]
            self._status(
                system="READY — PROBE COMPLETE",
                device=f"ONLINE  FW {firmware}  {services} SERVICES",
                protocol=f"{result['detected_eq_path']}  [{', '.join(supported) or 'none'}]",
            )
            self.log_message(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            self._status(system="PROBE FAILED", device="OFFLINE / ERROR")
            self.log_message(f"ERROR   |  Probe  |  {type(exc).__name__}: {exc}")

    def action_read(self) -> None:
        self.read_worker()

    @work(exclusive=True)
    async def read_worker(self) -> None:
        try:
            address, pid = self._address(), self._pid()
            path, frames = auto_read_frames(pid)
            self._status(system="READING EQ…", protocol=path)
            self.log_message(f"READ    |  {path}  |  {len(frames)} frame(s)")
            replies: list[bytes] = []
            async with BleTransport(address, rx_uuid=self.settings.rx_uuid, tx_uuid=self.settings.tx_uuid) as transport:
                for frame in frames:
                    replies.extend(await transport.transact(frame, self.settings.timeout))
            for reply in replies:
                self.log_message(json.dumps(describe_frame(reply), ensure_ascii=False, indent=2))
            self._status(system=f"READY — {len(replies)} REPLY")
        except Exception as exc:
            self._status(system="READ FAILED")
            self.log_message(f"ERROR   |  Read  |  {type(exc).__name__}: {exc}")

    def action_preview(self) -> None:
        try:
            pid, gains = self._pid(), self._gains()
            path, frames = auto_eq_frames(pid, gains)
            self._status(system="PREVIEW READY", protocol=path)
            self.log_message(
                f"PREVIEW |  {path}  |  profile={self._profile_key()}  |  gains={gains}\n"
                + "\n".join(f"TX      |  {hex_bytes(frame)}" for frame in frames)
            )
            append_audit(
                "eq-preview",
                address=self.query_one("#address", Input).value,
                pid=pid,
                applied=False,
                details={"profile": self._profile_key(), "path": path, "gains": gains},
            )
        except Exception as exc:
            self._status(system="PREVIEW REJECTED")
            self.log_message(f"REJECT  |  Preview  |  {exc}")

    def apply_eq(self) -> None:
        guard = self.query_one("#guard", Switch).value
        phrase = self.query_one("#confirm", Input).value
        if not guard or phrase != "APPLY":
            self._status(safety="BLOCKED — CHECK INTERLOCK")
            self.log_message("BLOCK   |  Enable WRITE INTERLOCK and type APPLY exactly.")
            return
        self.apply_worker()

    @work(exclusive=True)
    async def apply_worker(self) -> None:
        try:
            address, pid, gains = self._address(), self._pid(), self._gains()
            path, frames = auto_eq_frames(pid, gains)
            self._save_context()
            self._status(system="WRITING EQ…", safety="LIVE WRITE IN PROGRESS")
            self.log_message(f"WRITE   |  {path}  |  profile={self._profile_key()}  |  gains={gains}")
            replies: list[bytes] = []
            async with BleTransport(address, rx_uuid=self.settings.rx_uuid, tx_uuid=self.settings.tx_uuid) as transport:
                for frame in frames:
                    replies.extend(await transport.transact(frame, self.settings.timeout))
            append_audit(
                "eq-apply",
                address=address,
                pid=pid,
                applied=True,
                details={
                    "profile": self._profile_key(),
                    "path": path,
                    "gains": gains,
                    "tx": [hex_bytes(frame) for frame in frames],
                    "rx": [hex_bytes(reply) for reply in replies],
                },
            )
            self._status(system="WRITE COMPLETE", safety="WRITE LOCKED")
            self.log_message(f"WRITE   |  Complete  |  {len(replies)} reply frame(s)  |  Audit record saved")
            for reply in replies:
                self.log_message(json.dumps(describe_frame(reply), ensure_ascii=False, indent=2))
        except Exception as exc:
            self._status(system="WRITE FAILED", safety="WRITE LOCKED")
            self.log_message(f"ERROR   |  Apply  |  {type(exc).__name__}: {exc}")
        finally:
            self.query_one("#guard", Switch).value = False
            self.query_one("#confirm", Input).value = ""


def main() -> None:
    JblControlApp().run()


if __name__ == "__main__":
    main()
