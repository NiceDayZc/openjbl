from __future__ import annotations

import argparse
import asyncio
import json
import time
from contextlib import suppress
from pathlib import Path

from . import protocol
from .audit import append_audit
from .connection import ConnectionManager
from .models import auto_eq_frames, auto_read_frames, find_models, get_model, preset_for_pid, presets_for_pid
from .presets import ALL_PROFILES, curve_from_model_gains, curve_summary, get_profile, resolve_curve, resolve_profile
from .probe import probe_ble
from .protocol import EQ_CATEGORIES, FILTER_TYPES, ParametricBand, describe_frame, hex_bytes, parse_hex
from .transport import RX_UUID, SERVICE_UUID, TX_UUID, SerialTransport, scan_ble
from .updater import check_for_update_safe, update_now
from .userprofiles import delete_user_profile, load_user_profiles, save_user_profile, user_profiles_path
from .verification import verify_eq_readback


def dump(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def category(value: str) -> int:
    key = value.lower()
    if key in EQ_CATEGORIES:
        return EQ_CATEGORIES[key]
    return int(value, 0)


def band(value: str) -> ParametricBand:
    # type,frequency,gain,q -- e.g. peaking,1000,2.5,0.707
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("band format is type,frequency,gain,q")
    kind = FILTER_TYPES.get(parts[0].lower())
    if kind is None:
        try:
            kind = int(parts[0], 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"unknown filter type {parts[0]}") from exc
    result = ParametricBand(kind, float(parts[2]), float(parts[1]), float(parts[3]))
    result.validate()
    return result


def add_connection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--address", help="BLE address/device id")
    parser.add_argument("--port", help="Windows SPP COM port, e.g. COM7")
    parser.add_argument("--service", default=SERVICE_UUID)
    parser.add_argument("--rx", default=RX_UUID)
    parser.add_argument("--tx", default=TX_UUID)
    parser.add_argument("--timeout", type=float, default=2.0)


def _manager(args: argparse.Namespace) -> ConnectionManager:
    if not args.address:
        raise SystemExit("specify --address for BLE or --port for Classic SPP")
    return ConnectionManager(service_uuid=args.service, rx_uuid=args.rx, tx_uuid=args.tx, on_event=print)


async def send_ble(args: argparse.Namespace, frames: list[bytes]) -> list[bytes]:
    """Send every frame over one link, the way the Android app does.

    Reconnecting between the frames of a single EQ write is what made multi-frame
    writes slow and left a partial write behind when the link blipped.
    """
    manager = _manager(args)
    link = await manager.acquire(args.address)
    replies: list[bytes] = []
    try:
        for frame in frames:
            transaction = await link.transact(frame, args.timeout)
            replies.extend(transaction.replies)
            if transaction.attempts > 1 or transaction.reconnects:
                print(f"NOTE: delivered after {transaction.attempts} attempt(s), {transaction.reconnects} reconnect(s)")
    finally:
        await manager.release(args.address)
    return replies


def _report_replies(replies: list[bytes]) -> bool:
    """Print each reply and say whether the device rejected any of them."""
    rejected = False
    for reply in replies:
        if not reply:
            print("RX: <timeout/no data>")
            continue
        print("RX:", hex_bytes(reply))
        with suppress(ValueError):
            decoded = describe_frame(reply)
            rejected = rejected or decoded.get("command") == protocol.DEV_ERROR
            dump(decoded)
    return rejected


def send(args: argparse.Namespace, frames: list[bytes]) -> None:
    """Send frames, and for a mutating command prove what actually happened.

    The TUI has always read the EQ back and compared it band by band before
    claiming a write worked. The CLI printed the reply bytes and exited 0, so
    `--apply` could reject the frame, or land on a speaker that clamped it, and
    the script driving it would never know. The same evidence is now required on
    both paths, because it is the same hardware.
    """
    print("TX:")
    for frame in frames:
        print(hex_bytes(frame))
    mutating = bool(getattr(args, "mutating", False))
    if mutating and not args.apply:
        print("DRY-RUN: nothing was sent; add --apply only after checking the model and packet")
        return
    if args.port:
        transport = SerialTransport(args.port, timeout=args.timeout)
        replies = [transport.transact(frame) for frame in frames]
        if _report_replies(replies):
            raise SystemExit("the device rejected the frame (0xEE)")
        return

    verify_gains = getattr(args, "_verify_gains", None)
    pid = getattr(args, "pid", None)
    if not (mutating and verify_gains and pid):
        if _report_replies(asyncio.run(send_ble(args, frames))):
            raise SystemExit("the device rejected the frame (0xEE)")
        return
    outcome = asyncio.run(_apply_verified(args, frames, verify_gains, pid))
    if outcome:
        raise SystemExit(outcome)


async def _apply_verified(args: argparse.Namespace, frames: list[bytes], gains: list[float], pid: str) -> str | None:
    """Write, then read the EQ back and compare it band by band. Returns an error."""
    read_path, read_frames = auto_read_frames(pid)
    manager = _manager(args)
    link = await manager.acquire(args.address)
    started = time.perf_counter()
    write_replies: list[bytes] = []
    read_replies: list[bytes] = []
    frames_written = 0
    try:
        before: list[bytes] = []
        for frame in read_frames:
            before.extend((await link.transact(frame, args.timeout)).replies)
        precheck = verify_eq_readback(gains, before)
        print(f"BEFORE: {precheck.status}  actual={precheck.actual}")

        for frame in frames:
            frames_written += 1  # counted before the await: transact writes, then waits
            write_replies.extend((await link.transact(frame, args.timeout)).replies)
        rejected = _report_replies(write_replies)

        for frame in read_frames:
            read_replies.extend((await link.transact(frame, args.timeout)).replies)
        verification = verify_eq_readback(gains, read_replies)
        print(f"AFTER:  {verification.status}  actual={verification.actual}  delta={verification.deltas}")
        print(f"VERIFY: {verification.message}  (readback via {read_path})")
    finally:
        append_audit(
            "eq-apply",
            address=args.address,
            pid=pid,
            applied=frames_written > 0,
            details={
                "path": "cli",
                "gains": gains,
                "tx": [hex_bytes(frame) for frame in frames],
                "frames_written": frames_written,
                "write_rx": [hex_bytes(reply) for reply in write_replies],
                "readback_rx": [hex_bytes(reply) for reply in read_replies],
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        await manager.release(args.address)
    if rejected:
        return "the device rejected the write (0xEE)"
    if not verification.verified:
        return f"write NOT verified: {verification.message}"
    return None


async def services(args: argparse.Namespace) -> None:
    manager = _manager(args)
    link = await manager.acquire(args.address)
    try:
        dump(await link.services())
    finally:
        await manager.release(args.address)


async def listen(args: argparse.Namespace) -> None:
    """Watch the speaker's unsolicited pushes over a held link.

    The link stays subscribed for the whole window and reconnects underneath us
    if it drops, so a blip no longer ends the capture.
    """
    manager = _manager(args)
    log = Path(args.log) if args.log else None

    def record(line: str) -> None:
        print(line)
        if log:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    manager.on_event = record
    link = await manager.acquire(args.address)
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(0.2)
            for frame in await link.poll_unsolicited():
                record(f"{time.time():.3f} RX {frame.hex()}")
    finally:
        await manager.release(args.address)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openjbl",
        description="OpenJBL - safe JBL Portable protocol and EQ control",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="scan BLE advertisements")
    p.add_argument("--seconds", type=float, default=8.0)

    p = sub.add_parser("services", help="enumerate GATT services and characteristics")
    add_connection(p)

    p = sub.add_parser("listen", help="capture BLE notifications")
    add_connection(p)
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--log")

    p = sub.add_parser("decode", help="decode one captured frame")
    p.add_argument("hex")

    p = sub.add_parser("models", help="search the APK model/PID capability database")
    p.add_argument("query", nargs="?", help="PID or part of model name")

    p = sub.add_parser("presets", help="list APK EQ presets for a PID")
    p.add_argument("--pid", required=True)

    p = sub.add_parser("profiles", help="list sound profiles, optionally resolved for a PID")
    p.add_argument("--pid")
    p.add_argument("--mine", action="store_true", help="list only your own saved profiles")

    p = sub.add_parser("save-profile", help="save a gain curve as your own reusable profile")
    p.add_argument("--name", required=True)
    p.add_argument("--gains", required=True, type=float, nargs="+", help="gain per band, in dB")
    p.add_argument("--pid", help="resample these gains from this model's bands onto the reference curve")
    p.add_argument("--description", default="")
    p.add_argument("--overwrite", action="store_true", help="replace an existing profile of the same name")

    p = sub.add_parser("delete-profile", help="delete one of your saved profiles")
    p.add_argument("--key", required=True, help="the profile key, e.g. user-my-bass")

    sub.add_parser("check-update", help="check the latest OpenJBL version on PyPI")
    sub.add_parser("update", help="install the latest OpenJBL version from PyPI")

    p = sub.add_parser("probe", help="read-only probe of every EQ protocol generation")
    add_connection(p)
    p.add_argument("--pid", help="known product ID for model-aware reporting")

    p = sub.add_parser("get-auto", help="select the model-specific EQ read command from a PID")
    add_connection(p)
    p.add_argument("--pid", required=True)

    for name, help_text in (
        ("get-firmware", "read firmware version"),
        ("get-mode", "read EQ mode"),
        ("get-simple", "read simple EQ"),
        ("get-advanced", "read advanced EQ"),
        ("get-p4-eq", "read Protocol 4 EQ"),
    ):
        p = sub.add_parser(name, help=help_text)
        add_connection(p)
        if name == "get-p4-eq":
            p.add_argument("--category", type=category, default=0xFF)

    p = sub.add_parser("set-mode", help="set EQ mode byte")
    add_connection(p)
    p.add_argument("mode", type=lambda x: int(x, 0))
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-simple", help="set 3-band simple EQ")
    add_connection(p)
    p.add_argument("--category", type=category, default=EQ_CATEGORIES["custom"])
    p.add_argument("--bass", type=int, required=True)
    p.add_argument("--mid", type=int, required=True)
    p.add_argument("--treble", type=int, required=True)
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-levels", help="set old advanced level EQ (1..7 signed-byte levels)")
    add_connection(p)
    p.add_argument("--category", type=category, default=EQ_CATEGORIES["custom"])
    p.add_argument("levels", nargs="+", type=int)
    p.add_argument("--scope", type=int, default=6)
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-parametric", help="set legacy parametric EQ")
    add_connection(p)
    p.add_argument("--category", type=category, default=EQ_CATEGORIES["custom_c2"])
    p.add_argument("--sample-rate", type=int, default=48000)
    p.add_argument("--band", action="append", type=band, required=True)
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-p4-parametric", help="set Protocol 4 parametric EQ (exactly 7 bands)")
    add_connection(p)
    p.add_argument("--category", type=category, default=EQ_CATEGORIES["custom_c2"])
    p.add_argument("--band", action="append", type=band, required=True)
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-charge6", help="safe Charge 6 custom EQ with fixed frequency/Q")
    add_connection(p)
    p.add_argument("gains", nargs=7, type=float, metavar="GAIN")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-grip", help="Protocol 4 quantized EQ for Grip/GO 5/Essential SE")
    add_connection(p)
    p.add_argument("gains", nargs=7, type=float, metavar="GAIN")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-preset", help="apply an APK preset using the PID-selected protocol")
    add_connection(p)
    p.add_argument("--pid", required=True)
    p.add_argument("--preset", required=True, help="category/display name, e.g. SIGNATURE or VOCAL")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-auto", help="select EQ packet format automatically from a model PID")
    add_connection(p)
    p.add_argument("--pid", required=True)
    p.add_argument("gains", nargs="+", type=float, metavar="GAIN")
    p.add_argument(
        "--allow-extended",
        action="store_true",
        help="allow gains beyond the model's own UI range, on protocols that can carry them",
    )
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("set-profile", help="apply a curated model-aware sound profile")
    add_connection(p)
    p.add_argument("--pid", required=True)
    p.add_argument("profile", choices=[profile.key for profile in ALL_PROFILES])
    p.add_argument(
        "--allow-extended",
        action="store_true",
        help="unlock a DANGER/LAB profile outside the model's normal UI range",
    )
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("raw", help="send an expert-supplied raw frame")
    add_connection(p)
    p.add_argument("hex")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--i-understand", action="store_true", help="confirm raw packets can alter device state")
    return parser


def _main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        dump(asyncio.run(scan_ble(args.seconds)))
        return
    if args.command == "services":
        asyncio.run(services(args))
        return
    if args.command == "listen":
        asyncio.run(listen(args))
        return
    if args.command == "decode":
        dump(describe_frame(parse_hex(args.hex)))
        return
    if args.command == "models":
        dump(find_models(args.query))
        return
    if args.command == "presets":
        dump(presets_for_pid(args.pid))
        return
    if args.command == "profiles":
        catalog = list(ALL_PROFILES) if not args.mine else []
        catalog += load_user_profiles()
        rows = []
        for profile in catalog:
            resolved = None
            resolution_error = None
            if args.pid:
                try:
                    resolved = resolve_curve(args.pid, profile)
                except ValueError as exc:
                    resolution_error = str(exc)
            rows.append(
                {
                    "key": profile.key,
                    "name": profile.name,
                    "description": profile.description,
                    "reference_gains": profile.gains,
                    "resolved_gains": resolved,
                    "resolution_error": resolution_error,
                    "tags": profile.tags,
                    "extended_encoder": profile.dangerous,
                    "needs_confirmation": profile.boosts_past_standard,
                }
            )
        dump(rows)
        return
    if args.command == "save-profile":
        curve = curve_from_model_gains(args.pid, args.gains) if args.pid else tuple(args.gains)
        profile = save_user_profile(
            args.name,
            curve,
            description=args.description or curve_summary(curve),
            overwrite=args.overwrite,
        )
        dump(
            {
                "key": profile.key,
                "name": profile.name,
                "description": profile.description,
                "gains": profile.gains,
                "stored_in": str(user_profiles_path()),
            }
        )
        return
    if args.command == "delete-profile":
        removed = delete_user_profile(args.key)
        dump({"key": args.key, "deleted": removed})
        if not removed:
            raise SystemExit(f"no saved profile with key {args.key!r}")
        return
    if args.command == "check-update":
        dump(check_for_update_safe().as_dict())
        return
    if args.command == "update":
        dump(update_now().as_dict())
        return
    if args.command == "probe":
        if not args.address:
            raise SystemExit("probe currently requires --address (SPP can use individual get commands)")
        dump(
            asyncio.run(
                probe_ble(
                    args.address,
                    pid=args.pid,
                    service_uuid=args.service,
                    rx_uuid=args.rx,
                    tx_uuid=args.tx,
                    timeout=args.timeout,
                )
            )
        )
        return

    args.mutating = args.command.startswith("set-") or args.command == "raw"
    if args.command == "get-firmware":
        frames = [protocol.request_firmware_version()]
    elif args.command == "get-mode":
        frames = [protocol.request_eq_mode()]
    elif args.command == "get-simple":
        frames = [protocol.request_simple_eq()]
    elif args.command == "get-advanced":
        frames = [protocol.request_advanced_eq()]
    elif args.command == "get-p4-eq":
        frames = protocol.p4_request_eq(args.category)
    elif args.command == "get-auto":
        selected_path, frames = auto_read_frames(args.pid)
        print(f"Selected: {selected_path}")
    elif args.command == "set-mode":
        frames = [protocol.set_eq_mode(args.mode)]
    elif args.command == "set-simple":
        frames = [protocol.set_simple_eq(args.category, args.bass, args.mid, args.treble)]
    elif args.command == "set-levels":
        frames = [protocol.set_advanced_levels(args.category, args.levels, args.scope)]
    elif args.command == "set-parametric":
        frames = [protocol.set_parametric_eq(args.category, args.band, args.sample_rate)]
    elif args.command == "set-p4-parametric":
        frames = protocol.p4_set_parametric_eq(args.category, args.band)
    elif args.command == "set-charge6":
        frames = [protocol.set_parametric_eq(EQ_CATEGORIES["custom_c2"], protocol.charge6_bands(args.gains))]
    elif args.command == "set-grip":
        frames = protocol.p4_set_grip_eq(EQ_CATEGORIES["custom_c2"], args.gains)
    elif args.command == "set-preset":
        model = get_model(args.pid)
        preset_category, preset_bands = preset_for_pid(args.pid, args.preset)
        features = set(model.get("features", []))
        if "PROTOCOL_4" in features:
            if str(model.get("pid", "")).lower() in {"2132", "2168", "218a", "2185"}:
                raise SystemExit("Grip-style preset coefficients are model DSP data; use set-grip for custom EQ")
            frames = protocol.p4_set_parametric_eq(preset_category, preset_bands)
        elif "7_BANDS_EQ" in features:
            frames = [protocol.set_parametric_eq(preset_category, preset_bands)]
        else:
            raise SystemExit("this PID uses coefficient/level presets; custom control is available through set-levels")
    elif args.command == "set-auto":
        selected_path, frames = auto_eq_frames(args.pid, args.gains, allow_extended=args.allow_extended)
        args._verify_gains = list(args.gains)
        print(f"Selected: {selected_path}")
    elif args.command == "set-profile":
        profile = get_profile(args.profile)
        if profile.dangerous and not args.allow_extended:
            raise SystemExit("DANGER/LAB profiles require --allow-extended")
        gains = resolve_profile(args.pid, args.profile)
        selected_path, frames = auto_eq_frames(args.pid, gains, allow_extended=profile.dangerous)
        args._verify_gains = list(gains)
        print(f"Profile: {args.profile}  Gains: {' '.join(f'{gain:g}' for gain in gains)}")
        print(f"Selected: {selected_path}")
    elif args.command == "raw":
        if args.apply and not args.i_understand:
            raise SystemExit("raw --apply also requires --i-understand")
        frames = [parse_hex(args.hex)]
    else:
        raise AssertionError(args.command)
    send(args, frames)


def main(argv: list[str] | None = None) -> None:
    try:
        _main(argv)
    except (ValueError, KeyError) as exc:
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
