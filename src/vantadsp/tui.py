"""Monochrome Textual workstation for discovery, inspection, and EQ control."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
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
    TabbedContent,
    TabPane,
)

from .audit import append_audit, target_fingerprint
from .config import Settings
from .models import all_models, auto_eq_frames, auto_read_frames, gain_count_for_pid, summarize_model
from .presets import get_profile, profile_options, resolve_profile, sparkline
from .probe import probe_ble
from .protocol import describe_frame, hex_bytes
from .transport import BleTransport, scan_ble
from .verification import verify_eq_readback

MODEL_OPTIONS = [(f"{model.get('deviceName')} / {model.get('pid')}", str(model.get("pid"))) for model in all_models()]


class VantaDSPApp(App[None]):
    TITLE = "VANTADSP"
    SUB_TITLE = "BLUETOOTH EQ CONTROL"
    CSS = """
    Screen { background: #000000; color: #eeeeee; }
    Header, Footer { background: #eeeeee; color: #000000; }
    #status-strip { height: 3; background: #111111; padding: 0 1; }
    .metric { width: 1fr; height: 3; padding: 0 1; border-left: ascii #555555; }
    #status-system { border-left: none; }
    #main-tabs { height: 1fr; }
    TabbedContent { background: #000000; }
    TabPane { padding: 0 1 1 1; background: #000000; }
    Tabs { background: #000000; color: #aaaaaa; }
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
    Toast { width: 42; max-width: 40%; padding: 0 1; margin-top: 0; border: ascii #ffffff; }
    #devices { height: 1fr; border: ascii #555555; background: #000000; }
    #profile-panel { height: 9; padding: 1; background: #090909; }
    #profile-row { height: 3; }
    #profile-row Select { width: 2fr; margin-right: 1; }
    #profile-row Input { width: 3fr; }
    #curve { height: 2; color: #ffffff; text-style: bold; }
    #profile-info { color: #aaaaaa; }
    .actions { height: 3; align-vertical: middle; }
    .actions Button { min-width: 18; margin-right: 1; background: #111111; color: #eeeeee; border: ascii #555555; }
    .actions Button:hover, .actions Button:focus { background: #eeeeee; color: #000000; border: ascii #ffffff; }
    #apply { min-width: 22; background: #eeeeee; color: #000000; text-style: bold; }
    #log { height: 1fr; border: ascii #555555; background: #000000; color: #dddddd; }
    """
    BINDINGS: ClassVar = [
        ("q", "quit", "Quit"),
        ("s", "scan", "Scan"),
        ("p", "probe", "Probe"),
        ("r", "read", "Read EQ"),
        ("v", "preview", "Preview"),
        ("1", "device_tab", "Device"),
        ("2", "eq_tab", "EQ"),
        ("3", "activity_tab", "Activity"),
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
        with TabbedContent(initial="device-tab", id="main-tabs"):
            with TabPane("01  DEVICE", id="device-tab"):
                yield Static(
                    "AUTO DETECT  Scan for JBL speakers; the strongest identified model is selected automatically.",
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
                    yield Button("S  SCAN DEVICES", id="scan")
                    yield Button("P  PROBE SELECTED", id="probe")
            with TabPane("02  EQUALIZER", id="eq-tab"):
                yield Static(
                    "Choose a preset or edit gains. Preview is offline; Read and Apply connect to the speaker.",
                    classes="guide",
                )
                with Vertical(id="profile-panel"):
                    yield Label("SOUND PROFILE", classes="field-label")
                    with Horizontal(id="profile-row"):
                        yield Select(profile_options(), value="balanced", allow_blank=False, id="profile")
                        yield Input(id="gains", placeholder="Model-aware gains")
                    yield Static(id="curve")
                    yield Static(id="profile-info")
                yield Static(
                    "DIRECT APPLY  The button writes the selected profile immediately.",
                    classes="guide",
                )
                with Horizontal(classes="actions"):
                    yield Button("R  READ CURRENT", id="read")
                    yield Button("V  PREVIEW PACKET", id="preview")
                    yield Button("APPLY TO SPEAKER", id="apply")
            with TabPane("03  ACTIVITY", id="activity-tab"):
                yield Static(
                    "Connection details, packet previews, replies, and errors appear below.",
                    classes="guide",
                )
                yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#devices", DataTable)
        table.add_columns("NAME", "DETECTED MODEL", "PID", "RSSI", "ADDRESS")
        self._load_profile("balanced")
        self.log_message("READY  |  Direct apply is enabled. Start with SCAN or select a known address.")

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
            self.query_one("#curve", Static).update("CURVE  -  This APK declares no EQ controls for the selected PID")
        self.query_one("#profile-info", Static).update(
            f"{profile.name.upper()}  /  {profile.description}  /  TAGS: {', '.join(profile.tags) or 'general'}"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        address = str(event.row_key.value)
        row = self._scan_rows.get(address)
        if row:
            self._select_scan_row(row, automatic=False)

    def _select_scan_row(self, row: dict[str, Any], *, automatic: bool) -> None:
        address = str(row["address"])
        name = str(row["name"] or "UNNAMED")
        detection = row.get("jbl_detection", {})
        pid = detection.get("pid")
        signal = "PAIRED" if row.get("rssi") is None else f"{row['rssi']} dBm"
        self.query_one("#address", Input).value = address
        if pid:
            self.query_one("#pid", Select).value = str(pid)
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
                f"{model} / PID {pid} ({confidence} confidence). Confirm, then probe.",
                title="JBL auto-detected",
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
            self.query_one("#curve", Static).update("CUSTOM - invalid numeric gain list")

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

    def action_device_tab(self) -> None:
        self._show_tab("device-tab")

    def action_eq_tab(self) -> None:
        self._show_tab("eq-tab")

    def action_activity_tab(self) -> None:
        self._show_tab("activity-tab")

    @work(exclusive=True)
    async def scan_worker(self) -> None:
        self._status(system="SCANNING BLE...")
        self.log_message("SCAN    |  Listening for BLE advertisements...")
        try:
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
                    "PAIRED" if row["rssi"] is None else f"{row['rssi']} dBm",
                    row["address"],
                    key=row["address"],
                )
            detected = next((row for row in rows if row["jbl_detection"]["pid"]), None)
            if detected is not None:
                self._select_scan_row(detected, automatic=True)
            signal_rows = [row for row in rows if row["rssi"] is not None]
            strongest = f"  |  strongest {max(row['rssi'] for row in signal_rows)} dBm" if signal_rows else ""
            self._status(system=f"READY - {len(rows)} DEVICES")
            self.log_message(f"SCAN    |  Complete  |  {len(rows)} devices{strongest}")
            self.notify(
                f"Found {len(rows)} device(s). "
                + ("A JBL model was selected automatically." if detected else "Select a device and model manually."),
                title="Scan complete",
            )
        except Exception as exc:
            self._status(system="SCAN FAILED")
            self._report_error("Scan", exc)

    def action_probe(self) -> None:
        self.probe_worker()

    @work(exclusive=True)
    async def probe_worker(self) -> None:
        try:
            address, pid = self._address(), self._pid()
            self._save_context()
            self._status(system="PROBING...", device="CONNECTING")
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
                system="READY - PROBE COMPLETE",
                device=f"ONLINE  FW {firmware}  {services} SERVICES",
                protocol=f"{result['detected_eq_path']}  [{', '.join(supported) or 'none'}]",
            )
            self.log_message(json.dumps(result, ensure_ascii=False, indent=2))
            self.notify(
                f"Firmware {firmware}; EQ path {result['detected_eq_path']}",
                title="Probe complete",
            )
        except Exception as exc:
            self._status(system="PROBE FAILED", device="OFFLINE / ERROR")
            self._report_error("Probe", exc)

    def action_read(self) -> None:
        self.read_worker()

    @work(exclusive=True)
    async def read_worker(self) -> None:
        try:
            address, pid = self._address(), self._pid()
            path, frames = auto_read_frames(pid)
            self._status(system="READING EQ...", protocol=path)
            self.log_message(f"READ    |  {path}  |  {len(frames)} frame(s)")
            replies: list[bytes] = []
            async with BleTransport(
                address,
                service_uuid=self.settings.service_uuid,
                rx_uuid=self.settings.rx_uuid,
                tx_uuid=self.settings.tx_uuid,
            ) as transport:
                for frame in frames:
                    replies.extend(await transport.transact(frame, self.settings.timeout))
            for reply in replies:
                self.log_message(json.dumps(describe_frame(reply), ensure_ascii=False, indent=2))
            self._status(system=f"READY - {len(replies)} REPLY")
            self.notify(f"Received {len(replies)} reply frame(s).", title="EQ read complete")
        except Exception as exc:
            self._status(system="READ FAILED")
            self._report_error("Read", exc)

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
            self.notify("Packet is ready. Review it in Activity before applying.", title="Preview complete")
        except Exception as exc:
            self._status(system="PREVIEW REJECTED")
            self.log_message(f"REJECT  |  Preview  |  {exc}")
            self.notify(str(exc), title="Preview rejected", severity="warning")

    def apply_eq(self) -> None:
        self._show_tab("activity-tab")
        self.apply_worker()

    @work(exclusive=True)
    async def apply_worker(self) -> None:
        transaction_id = uuid.uuid4().hex[:8].upper()
        started = time.perf_counter()
        address = ""
        pid = ""
        path = "unknown"
        gains: list[float] = []
        frames: list[bytes] = []
        write_replies: list[bytes] = []
        read_frames: list[bytes] = []
        precheck_replies: list[bytes] = []
        read_replies: list[bytes] = []
        frames_written = 0
        try:
            address, pid, gains = self._address(), self._pid(), self._gains()
            path, frames = auto_eq_frames(pid, gains)
            read_path, read_frames = auto_read_frames(pid)
            self._save_context()
            target = target_fingerprint(address)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self._status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
            self.log_message(
                f"\nTXN     |  {transaction_id}  |  BEGIN {timestamp}\n"
                f"TARGET  |  hash={target}  |  PID={pid}  |  profile={self._profile_key()}\n"
                f"ROUTE   |  write={path}  |  readback={read_path}\n"
                f"REQUEST |  gains={gains}  |  frames={len(frames)}"
            )
            async with BleTransport(
                address,
                service_uuid=self.settings.service_uuid,
                rx_uuid=self.settings.rx_uuid,
                tx_uuid=self.settings.tx_uuid,
            ) as transport:
                self.log_message("CONNECT |  BLE connected; notifications ready")
                self._status(system=f"PRECHECK {transaction_id}", protocol=f"{read_path} | READING BEFORE")
                for index, frame in enumerate(read_frames, 1):
                    self.log_message(f"PRECHECK|  TX {index}/{len(read_frames)}  |  {hex_bytes(frame)}")
                    replies = await transport.transact(frame, self.settings.timeout)
                    precheck_replies.extend(replies)
                    self.log_message(f"PRECHECK|  RX {index}/{len(read_frames)}  |  {len(replies)} frame(s)")
                precheck = verify_eq_readback(gains, precheck_replies)
                self.log_message(
                    f"BEFORE  |  status={precheck.status}  |  actual={precheck.actual}  |  delta={precheck.deltas}"
                )
                self._status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
                ack_error = False
                for index, frame in enumerate(frames, 1):
                    self.log_message(f"WRITE   |  TX {index}/{len(frames)}  |  {hex_bytes(frame)}")
                    replies = await transport.transact(frame, self.settings.timeout)
                    frames_written += 1
                    write_replies.extend(replies)
                    self.log_message(f"WRITE   |  RX {index}/{len(frames)}  |  {len(replies)} frame(s)")
                    for reply in replies:
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
                    replies = await transport.transact(frame, self.settings.timeout)
                    read_replies.extend(replies)
                    self.log_message(f"READBACK|  RX {index}/{len(read_frames)}  |  {len(replies)} frame(s)")
                    for reply in replies:
                        self.log_message(f"STATE   |  RAW {hex_bytes(reply)}")
                        try:
                            self.log_message("STATE   |  DEC " + json.dumps(describe_frame(reply), ensure_ascii=False))
                        except ValueError as exc:
                            self.log_message(f"STATE   |  undecodable: {exc}")
            verification = verify_eq_readback(gains, read_replies)
            changed = precheck.status == "mismatch" and verification.verified
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.log_message(
                f"VERIFY  |  {verification.status.upper()}  |  source={verification.source}\n"
                f"EXPECT  |  {verification.expected}\n"
                f"ACTUAL  |  {verification.actual}\n"
                f"DELTA   |  {verification.deltas}\n"
                f"RESULT  |  {verification.message}\n"
                f"PROOF   |  ack={ack}  |  state_changed={changed}  |  before={precheck.status}\n"
                f"TXN     |  {transaction_id}  |  END  |  {elapsed_ms} ms"
            )
            append_audit(
                "eq-apply",
                address=address,
                pid=pid,
                applied=True,
                details={
                    "transaction_id": transaction_id,
                    "profile": self._profile_key(),
                    "path": path,
                    "gains": gains,
                    "tx": [hex_bytes(frame) for frame in frames],
                    "write_rx": [hex_bytes(reply) for reply in write_replies],
                    "ack": ack,
                    "precheck_rx": [hex_bytes(reply) for reply in precheck_replies],
                    "precheck": precheck.as_dict(),
                    "readback_tx": [hex_bytes(frame) for frame in read_frames],
                    "readback_rx": [hex_bytes(reply) for reply in read_replies],
                    "verification": verification.as_dict(),
                    "elapsed_ms": elapsed_ms,
                },
            )
            if verification.verified and ack == "RECEIVED":
                outcome = "CHANGED + VERIFIED" if changed else "ALREADY MATCHED + VERIFIED"
                self._status(system="WRITE VERIFIED", protocol=f"{path} | {outcome}")
                self.notify(
                    "Write response received; every EQ band matched read-back. "
                    + ("The pre-write state was different." if changed else "The requested state already matched."),
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
        except Exception as exc:
            self._status(system="WRITE FAILED")
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
                        "write_rx": [hex_bytes(reply) for reply in write_replies],
                        "precheck_rx": [hex_bytes(reply) for reply in precheck_replies],
                        "readback_rx": [hex_bytes(reply) for reply in read_replies],
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": elapsed_ms,
                    },
                )
            self._report_error("Apply", exc)


def main() -> None:
    VantaDSPApp().run()


if __name__ == "__main__":
    main()
