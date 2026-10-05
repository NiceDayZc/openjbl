"""Local web GUI: a shadcn/ui front end over the same verified EQ path as the TUI.

The server listens on 127.0.0.1 only and the page talks to it over a small JSON
API. Binding to loopback is not enough on its own: any web page open in the same
browser can send requests to 127.0.0.1, so every API call must also carry a
random per-launch token that only the page this server rendered can read, and
the Host header must name loopback so a DNS-rebinding page cannot pose as it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hmac
import os
import secrets
import time
import webbrowser
from collections import deque
from importlib.resources import files
from typing import Any

from aiohttp import web

from . import __build_id__, __version__
from .audit import append_audit
from .config import Settings
from .connection import ConnectionManager, Link
from .discovery import pick_auto_candidate
from .eqwrite import WriteRequest, apply_verified_write
from .models import (
    GRIP_STYLE_P4_PIDS,
    _standard_floor,
    all_models,
    auto_eq_frames,
    auto_read_frames,
    gain_count_for_pid,
    get_model,
    presets_for_pid,
    summarize_model,
)
from .presets import (
    LAB_PROFILES,
    PROFILES,
    STANDARD_MAX_BOOST_DB,
    SoundProfile,
    _model_frequencies,
    curve_from_model_gains,
    curve_summary,
    get_profile,
    resolve_curve,
)
from .probe import probe_link
from .protocol import FILTER_TYPES, custom_c2_shape, hex_bytes
from .transport import scan_ble
from .userprofiles import ProfileStoreError, delete_user_profile, load_user_profiles, save_user_profile
from .verification import verify_eq_readback

TOKEN_HEADER = "X-OpenJBL-Token"
TOKEN_PLACEHOLDER = "__OPENJBL_TOKEN__"
DEFAULT_PORT = 47800
FILTER_NAMES = {value: key for key, value in FILTER_TYPES.items()}


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.extra = extra


class GuiSession:
    """Everything one GUI process knows about the speaker it is driving.

    One hardware operation runs at a time. The TUI keeps reads and writes in
    separate worker groups so a keystroke cannot cancel a write; here nothing can
    cancel anything, so a single lock is the simpler guarantee that a scan, a
    read and a write never share the radio.
    """

    def __init__(self, settings: Settings | None = None, manager: ConnectionManager | None = None) -> None:
        self.settings = settings or Settings.load()
        self.manager = manager or ConnectionManager(
            service_uuid=self.settings.service_uuid,
            rx_uuid=self.settings.rx_uuid,
            tx_uuid=self.settings.tx_uuid,
            on_event=self.log,
        )
        # (address, pid, link generation), exactly as in the TUI: the generation
        # is what makes this an authorisation over a live link rather than a
        # memory of a past one.
        self.verified: tuple[str, str, int] | None = None
        self.target: dict[str, Any] | None = None
        self.scan_rows: dict[str, dict[str, Any]] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=2000)
        self._sequence = 0
        self.lock = asyncio.Lock()
        self.busy: str | None = None

    # -- activity ---------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        self._sequence += 1
        self.events.append({"seq": self._sequence, "time": time.time(), "level": level, "message": message})

    # -- authorisation ----------------------------------------------------

    def eq_access(self) -> bool:
        if self.verified is None:
            return False
        address, _pid, generation = self.verified
        if self.manager.holds_generation(address, generation):
            return True
        # The link it was verified over is gone; the authorisation goes with it.
        self.verified = None
        self.log("LOCK    |  EQ locked  |  The verified link dropped", "warning")
        return False

    def invalidate(self, reason: str) -> None:
        if self.verified is not None:
            self.log(f"LOCK    |  EQ locked  |  {reason}", "warning")
        self.verified = None

    def verified_link(self) -> tuple[Link, str, str]:
        if not self.eq_access():
            raise ApiError(409, "Connect and verify the speaker before using the equalizer.")
        address, pid, _generation = self.verified  # type: ignore[misc]
        link = self.manager.live(address)
        if link is None:
            self.invalidate("The verified link is gone")
            raise ApiError(409, "The verified link is no longer up; reconnect the speaker.")
        return link, address, pid

    async def run(self, label: str, operation: Any) -> Any:
        if self.lock.locked():
            operation.close()
            raise ApiError(409, f"Busy: {self.busy or 'another operation'} is still running.")
        async with self.lock:
            self.busy = label
            try:
                return await operation
            finally:
                self.busy = None

    # -- state ------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        verified = self.eq_access()
        return {
            "version": __version__,
            "build": __build_id__,
            "address": self.settings.last_address,
            "pid": self.settings.last_pid,
            "verified": verified,
            "target": self.target if verified else None,
            "busy": self.busy,
            "event_seq": self._sequence,
        }

    # -- discovery and verification --------------------------------------

    async def scan(self) -> dict[str, Any]:
        self.invalidate("A new device scan started")
        self.log("SCAN    |  Listening for BLE advertisements...")
        rows = await scan_ble(self.settings.scan_seconds)
        self.scan_rows = {str(row["address"]): row for row in rows}
        candidate, reason = pick_auto_candidate(rows)
        self.log(f"SCAN    |  Complete  |  {len(rows)} devices")
        return {
            "devices": [_device_row(row) for row in rows],
            "candidate": None if candidate is None else str(candidate["address"]),
            "reason": reason,
        }

    async def connect(self, address: str, pid: str) -> dict[str, Any]:
        """Connect, hold the link open, and verify the EQ route over it."""
        try:
            get_model(pid)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from None
        row = self.scan_rows.get(address)
        if row is not None and not row.get("live", row.get("rssi") is not None):
            raise ApiError(
                409,
                "This is cached Windows pairing metadata, not a live BLE advertisement; "
                "wake the speaker and scan again.",
            )
        self.invalidate("Connecting to a speaker")
        self.settings.last_address, self.settings.last_pid = address, pid
        self.settings.save()
        link = await self.manager.acquire(address)
        self.log(f"PROBE   |  PID {pid}  |  Read-only multi-generation capability check")
        result = await probe_link(link, pid=pid, timeout=self.settings.timeout)
        decoded = result["probes"]["firmware"].get("decoded", [])
        firmware = decoded[0].get("firmware_version", "unknown") if decoded else "unknown"
        supported = [name for name, item in result["probes"].items() if item["status"] == "supported-response"]
        eq_path = str(result["detected_eq_path"])
        if eq_path == "no-supported-eq-response":
            raise ApiError(502, "Connected, but the speaker gave no supported EQ response.")
        self.verified = (address, pid, link.generation)
        model = get_model(pid)
        detection = (row or {}).get("jbl_detection", {})
        self.target = {
            "address": address,
            "pid": pid,
            "name": (row or {}).get("name") or model.get("deviceName"),
            "model": detection.get("model") or model.get("deviceName"),
            "firmware": firmware,
            "eq_path": eq_path,
            "supported": supported,
            "services": len(result.get("services", [])),
        }
        self.log(f"VERIFY  |  {self.target['model']}  |  FW {firmware}  |  {eq_path}", "success")
        return self.target

    async def setup(self) -> dict[str, Any]:
        """One press: scan, pick, connect, verify. It never writes."""
        found = await self.scan()
        candidate = found["candidate"]
        if candidate is None:
            self.log(f"AUTO    |  Declined to auto-select  |  {found['reason']}", "warning")
            return {**found, "target": None}
        pid = str(self.scan_rows[candidate]["jbl_detection"]["pid"])
        self.log(f"AUTO    |  Selected {candidate}  |  {found['reason']}")
        return {**found, "target": await self.connect(candidate, pid)}

    async def disconnect(self) -> None:
        if self.verified is not None:
            address = self.verified[0]
            self.invalidate("Disconnected")
            await self.manager.release(address)

    # -- equalizer --------------------------------------------------------

    def profile(self, key: str) -> SoundProfile:
        try:
            return get_profile(key)
        except ValueError:
            for profile in load_user_profiles():
                if profile.key == key:
                    return profile
            raise ApiError(400, f"Unknown sound profile {key!r}.") from None

    def write_request(self, body: dict[str, Any]) -> WriteRequest:
        """Freeze the write identity once. The target is the verified link, never the page's say-so."""
        _link, address, pid = self.verified_link()
        profile = self.profile(str(body.get("profile", "")))
        try:
            gains = [float(value) for value in body.get("gains", [])]
        except (TypeError, ValueError):
            raise ApiError(400, "Gains must be numbers.") from None
        if len(gains) != gain_count_for_pid(pid):
            raise ApiError(400, f"PID {pid} takes {gain_count_for_pid(pid)} gains; received {len(gains)}.")
        if _gains_are_decibels(pid):
            hand_boost = any(gain > STANDARD_MAX_BOOST_DB for gain in gains)
        else:
            # On level-index encoders the number is a firmware table entry, so
            # magnitude in either direction is what is out of bounds.
            hand_boost = any(abs(gain) > STANDARD_MAX_BOOST_DB for gain in gains)
        return WriteRequest(
            address=address,
            pid=pid,
            profile=profile.key,
            gains=gains,
            allow_extended=profile.dangerous,
            dangerous=profile.boosts_past_standard or hand_boost,
        )

    async def read(self) -> dict[str, Any]:
        link, _address, pid = self.verified_link()
        path, frames = auto_read_frames(pid)
        self.log(f"READ    |  {path}  |  {len(frames)} frame(s)")
        replies: list[bytes] = []
        for frame in frames:
            replies.extend((await link.transact(frame, self.settings.timeout)).replies)
        decoded = verify_eq_readback([0.0] * gain_count_for_pid(pid), replies)
        for reply in replies:
            self.log(f"STATE   |  RAW {hex_bytes(reply)}")
        self.log(f"READ    |  {len(replies)} reply  |  gains={decoded.actual}")
        return {"path": path, "gains": decoded.actual, "source": decoded.source, "replies": len(replies)}

    def preview(self, body: dict[str, Any]) -> dict[str, Any]:
        request = self.write_request(body)
        try:
            path, frames = auto_eq_frames(request.pid, request.gains, allow_extended=request.allow_extended)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from None
        hexes = [hex_bytes(frame) for frame in frames]
        self.log(
            f"PREVIEW |  {path}  |  profile={request.profile}  |  dangerous={request.dangerous}  |  "
            f"gains={request.gains}\n" + "\n".join(f"TX      |  {frame}" for frame in hexes)
        )
        append_audit(
            "eq-preview",
            address=request.address,
            pid=request.pid,
            applied=False,
            details={"profile": request.profile, "path": path, "gains": request.gains, "dangerous": request.dangerous},
        )
        return {"path": path, "frames": hexes, "gains": request.gains, "dangerous": request.dangerous}

    async def apply(self, body: dict[str, Any]) -> dict[str, Any]:
        request = self.write_request(body)
        if request.dangerous and body.get("confirm_danger") is not True:
            # The page asks the user in a dialog and resends with the flag. A
            # boost is what earns this, never LAB membership: a deep cut cannot clip.
            raise ApiError(
                428,
                "This curve boosts past the model's own range and can clip. Confirm to write it.",
                needs_confirmation=True,
            )
        try:
            auto_eq_frames(request.pid, request.gains, allow_extended=request.allow_extended)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from None
        link, _address, _pid = self.verified_link()
        outcome = await apply_verified_write(link, request, timeout=self.settings.timeout, log=self.log)
        level = {"information": "success", "warning": "warning", "error": "error"}[outcome.severity]
        self.log(f"RESULT  |  {outcome.title}  |  {outcome.outcome}", level)
        return outcome.as_dict()


# -- serialisation ------------------------------------------------------------


def _device_row(row: dict[str, Any]) -> dict[str, Any]:
    detection = row.get("jbl_detection", {})
    return {
        "address": str(row["address"]),
        "name": row.get("name") or "",
        "rssi": row.get("rssi"),
        "live": bool(row.get("live", row.get("rssi") is not None)),
        "is_jbl": bool(detection.get("is_jbl")),
        "model": detection.get("model"),
        "pid": detection.get("pid"),
        "confidence": detection.get("confidence"),
    }


def _gains_are_decibels(pid: str) -> bool:
    features = set(get_model(pid).get("features", []))
    return "7_BANDS_EQ" in features or "PROTOCOL_4" in features


def model_controls(pid: str) -> dict[str, Any]:
    """What the page needs to draw this model's sliders and response curve."""
    model = get_model(pid)
    normalized = str(model.get("pid", "")).lower()
    features = set(model.get("features", []))
    count = gain_count_for_pid(pid)
    decibels = _gains_are_decibels(pid)
    grip = normalized in GRIP_STYLE_P4_PIDS
    shape: list[dict[str, Any]] | None = None
    if normalized == "20e3":
        shape = [{"type": FILTER_NAMES[kind], "frequency": freq, "q": q} for kind, freq, q in custom_c2_shape()]
    elif decibels and not grip and presets_for_pid(pid):
        params = presets_for_pid(pid)[0].get("params", [])
        if len(params) == count:
            shape = [
                {
                    "type": str(param["type"]).replace("_FILTER", "").replace("PEAKING_EQ", "PEAKING").lower(),
                    "frequency": float(param["frequency"]),
                    "q": float(param["qValue"]),
                }
                for param in params
            ]
    integer = not decibels
    bands = []
    for index in range(1, count + 1):
        floor = _standard_floor(normalized, index)
        bands.append(
            {
                "min": floor if decibels else -6.0,
                "max": 6.0,
                "step": 1.0 if integer else 0.5,
                # Charge 6 and Grip-style band 1 cut in 0.75 dB steps.
                "neg_step": 0.75 if (index == 1 and floor < -6.0) else (1.0 if integer else 0.5),
            }
        )
    return {
        "pid": pid,
        "name": model.get("deviceName"),
        "eq_path": summarize_model(model)["eq_path"],
        "count": count,
        "frequencies": _model_frequencies(pid, count) if count else [],
        "shape": shape,
        "decibels": decibels,
        "extended_allowed": ("7_BANDS_EQ" in features or "PROTOCOL_4" in features) and not grip,
        "bands": bands,
    }


def _profile_row(profile: SoundProfile, pid: str) -> dict[str, Any]:
    try:
        resolved: list[float] | None = resolve_curve(pid, profile)
        error = None
    except ValueError as exc:
        resolved, error = None, str(exc)
    return {
        "key": profile.key,
        "name": profile.name,
        "description": profile.description,
        "curve": list(profile.gains),
        "gains": resolved,
        "error": error,
        "extended": profile.dangerous,
        "boosts": profile.boosts_past_standard,
        "tags": list(profile.tags),
    }


# -- HTTP ---------------------------------------------------------------------


async def _json_body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise ApiError(400, "The request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise ApiError(400, "The request body must be a JSON object.")
    return body


def create_app(session: GuiSession, *, token: str, port: int) -> web.Application:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    @web.middleware
    async def guard(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.host not in allowed_hosts:
            return web.json_response({"error": "forbidden host"}, status=403)
        if request.path.startswith("/api/"):
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied, token):
                return web.json_response({"error": "missing or invalid session token"}, status=403)
            try:
                return await handler(request)
            except ApiError as exc:
                return web.json_response({"error": str(exc), **exc.extra}, status=exc.status)
            except Exception as exc:
                session.log(f"ERROR   |  {request.path}  |  {type(exc).__name__}: {exc}", "error")
                return web.json_response({"error": f"{type(exc).__name__}: {exc}"}, status=500)
        return await handler(request)

    app = web.Application(middlewares=[guard])
    web_root = files("openjbl").joinpath("web")

    async def index(_request: web.Request) -> web.Response:
        page = web_root.joinpath("index.html")
        if not page.is_file():
            return web.Response(
                text="The GUI has not been built. Run `npm install && npm run build` in gui/.", status=500
            )
        html = page.read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, token)
        return web.Response(
            text=html,
            content_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                    "font-src 'self' data:; frame-ancestors 'none'"
                ),
            },
        )

    async def asset(request: web.Request) -> web.StreamResponse:
        name = request.match_info["name"]
        if "/" in name or "\\" in name or name.startswith("."):
            raise web.HTTPNotFound()
        resource = web_root.joinpath("assets").joinpath(name)
        if not resource.is_file():
            raise web.HTTPNotFound()
        content_type = {
            ".js": "text/javascript",
            ".css": "text/css",
            ".woff2": "font/woff2",
            ".woff": "font/woff",
            ".svg": "image/svg+xml",
        }.get(os.path.splitext(name)[1], "application/octet-stream")
        return web.Response(body=resource.read_bytes(), content_type=content_type)

    async def state(_request: web.Request) -> web.Response:
        return web.json_response(session.state())

    async def models(_request: web.Request) -> web.Response:
        rows = []
        for model in all_models():
            pid = str(model.get("pid"))
            count = gain_count_for_pid(pid)
            if count:
                rows.append({"pid": pid, "name": model.get("deviceName"), "bands": count})
        return web.json_response(sorted(rows, key=lambda row: str(row["name"])))

    async def model(request: web.Request) -> web.Response:
        try:
            return web.json_response(model_controls(request.match_info["pid"]))
        except (ValueError, KeyError) as exc:
            raise ApiError(404, str(exc)) from None

    async def profiles(request: web.Request) -> web.Response:
        pid = request.query.get("pid") or session.settings.last_pid
        try:
            user = load_user_profiles()
        except ProfileStoreError as exc:
            session.log(f"ERROR   |  Saved profiles  |  {exc}", "error")
            user = []
        return web.json_response(
            {
                "standard": [_profile_row(profile, pid) for profile in PROFILES],
                "lab": [_profile_row(profile, pid) for profile in LAB_PROFILES],
                "user": [_profile_row(profile, pid) for profile in user],
            }
        )

    async def save_profile(request: web.Request) -> web.Response:
        body = await _json_body(request)
        try:
            pid = str(body["pid"])
            curve = curve_from_model_gains(pid, [float(value) for value in body["gains"]])
            profile = save_user_profile(
                str(body.get("name", "")), curve, description=curve_summary(curve), overwrite=True
            )
        except (KeyError, TypeError, ValueError, ProfileStoreError) as exc:
            raise ApiError(400, str(exc)) from None
        session.log(f"SAVE    |  {profile.name}  |  {profile.key}  |  {list(profile.gains)}", "success")
        return web.json_response(_profile_row(profile, pid))

    async def delete_profile(request: web.Request) -> web.Response:
        key = request.match_info["key"]
        if not key.startswith("user-"):
            raise ApiError(400, "Only your own saved profiles can be deleted.")
        try:
            removed = delete_user_profile(key)
        except ProfileStoreError as exc:
            raise ApiError(500, str(exc)) from None
        if removed:
            session.log(f"DELETE  |  {key}")
        return web.json_response({"deleted": removed})

    async def events(request: web.Request) -> web.Response:
        after = int(request.query.get("after", "0"))
        return web.json_response([event for event in session.events if event["seq"] > after])

    async def scan(_request: web.Request) -> web.Response:
        return web.json_response(await session.run("Scanning", session.scan()))

    async def setup(_request: web.Request) -> web.Response:
        return web.json_response(await session.run("Auto setup", session.setup()))

    async def connect(request: web.Request) -> web.Response:
        body = await _json_body(request)
        address, pid = str(body.get("address", "")).strip(), str(body.get("pid", "")).strip()
        if not address or not pid:
            raise ApiError(400, "Choose a speaker and its model first.")
        return web.json_response(await session.run("Connecting", session.connect(address, pid)))

    async def disconnect(_request: web.Request) -> web.Response:
        await session.run("Disconnecting", session.disconnect())
        return web.json_response(session.state())

    async def read(_request: web.Request) -> web.Response:
        return web.json_response(await session.run("Reading EQ", session.read()))

    async def preview(request: web.Request) -> web.Response:
        return web.json_response(session.preview(await _json_body(request)))

    async def apply(request: web.Request) -> web.Response:
        body = await _json_body(request)
        return web.json_response(await session.run("Writing EQ", session.apply(body)))

    app.router.add_get("/", index)
    app.router.add_get("/assets/{name}", asset)
    app.router.add_get("/api/state", state)
    app.router.add_get("/api/models", models)
    app.router.add_get("/api/model/{pid}", model)
    app.router.add_get("/api/profiles", profiles)
    app.router.add_post("/api/profiles", save_profile)
    app.router.add_delete("/api/profiles/{key}", delete_profile)
    app.router.add_get("/api/events", events)
    app.router.add_post("/api/scan", scan)
    app.router.add_post("/api/setup", setup)
    app.router.add_post("/api/connect", connect)
    app.router.add_post("/api/disconnect", disconnect)
    app.router.add_post("/api/read", read)
    app.router.add_post("/api/preview", preview)
    app.router.add_post("/api/apply", apply)

    async def release_links(_app: web.Application) -> None:
        with contextlib.suppress(Exception):
            await session.manager.release_all()

    app.on_shutdown.append(release_links)
    return app


async def _serve(port: int, open_browser: bool) -> None:
    session = GuiSession()
    session.log(f"START   |  OpenJBL v{__version__}  |  build={__build_id__}")
    # A fixed token from the environment lets `npm run dev` talk to this server;
    # otherwise every launch gets a fresh one.
    token = os.environ.get("OPENJBL_GUI_TOKEN") or secrets.token_urlsafe(32)
    runner: web.AppRunner | None = None
    for candidate in range(port, port + 20):
        runner = web.AppRunner(create_app(session, token=token, port=candidate))
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", candidate).start()
        except OSError:
            await runner.cleanup()
            runner = None
            continue
        port = candidate
        break
    if runner is None:
        raise SystemExit(f"no free port between {port} and {port + 19}")
    url = f"http://127.0.0.1:{port}/"
    print(f"OpenJBL GUI running at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="openjbl-gui", description="OpenJBL desktop GUI in your browser")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve(args.port, not args.no_browser))


if __name__ == "__main__":
    main()
