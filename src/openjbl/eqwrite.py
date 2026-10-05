"""The verified EQ write transaction, shared by every front end that holds a link.

Read the EQ before writing, write, check the acknowledgement, read it again and
compare band by band, and leave an audit record either way. It lives here rather
than in one UI so the TUI and the GUI cannot drift apart on the one path that
changes real hardware.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .audit import append_audit, target_fingerprint
from .connection import Link
from .models import auto_eq_frames, auto_read_frames
from .protocol import describe_frame, hex_bytes
from .verification import EqVerification, verify_eq_readback


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


@dataclass
class WriteOutcome:
    """What a finished transaction proved, worded once for every front end."""

    transaction_id: str
    path: str
    read_path: str
    ack: str
    precheck: EqVerification
    verification: EqVerification
    reconnects: int
    elapsed_ms: int
    # One of: verified, ack-issue, mismatch, unverified.
    result: str
    outcome: str
    title: str
    message: str
    severity: str
    frames: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "path": self.path,
            "read_path": self.read_path,
            "ack": self.ack,
            "precheck": self.precheck.as_dict(),
            "verification": self.verification.as_dict(),
            "reconnects": self.reconnects,
            "elapsed_ms": self.elapsed_ms,
            "result": self.result,
            "outcome": self.outcome,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "frames": self.frames,
        }


Log = Callable[[str], None]
Status = Callable[..., None]


def _ignore_status(**_values: str) -> None:
    return None


async def apply_verified_write(
    link: Link,
    request: WriteRequest,
    *,
    timeout: float,
    log: Log,
    status: Status = _ignore_status,
) -> WriteOutcome:
    """Run one write transaction over a link that has already been verified.

    Raises on any failure after recording what reached the wire; the caller
    decides how to tell the user.
    """
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
        path, frames = auto_eq_frames(pid, gains, allow_extended=request.allow_extended)
        read_path, read_frames = auto_read_frames(pid)
        target = target_fingerprint(address)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
        log(
            f"\nTXN     |  {transaction_id}  |  BEGIN {timestamp}\n"
            f"TARGET  |  hash={target}  |  PID={pid}  |  profile={request.profile}  |  "
            f"dangerous={request.dangerous}\n"
            f"ROUTE   |  write={path}  |  readback={read_path}\n"
            f"REQUEST |  gains={gains}  |  frames={len(frames)}"
        )
        status(system=f"PRECHECK {transaction_id}", protocol=f"{read_path} | READING BEFORE")
        for index, frame in enumerate(read_frames, 1):
            log(f"PRECHECK|  TX {index}/{len(read_frames)}  |  {hex_bytes(frame)}")
            transaction = await link.transact(frame, timeout)
            precheck_replies.extend(transaction.replies)
            log(f"PRECHECK|  RX {index}/{len(read_frames)}  |  {len(transaction.replies)} frame(s)")
        # Snapshot taken before the first write is issued, and never recomputed.
        # Re-reading it after an attempt that already landed would report the
        # write as "already matched" when it was this write that changed things.
        precheck = verify_eq_readback(gains, precheck_replies)
        log(f"BEFORE  |  status={precheck.status}  |  actual={precheck.actual}  |  delta={precheck.deltas}")
        status(system=f"WRITE TX {transaction_id}", protocol=f"{path} | SENDING")
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
            log(f"WRITE   |  TX {index}/{len(frames)}  |  {hex_bytes(frame)}")
            # Counted before the await, not after. transact() puts the frame
            # on the wire and only then waits for a reply, so counting on
            # return meant a timeout or a cancellation recorded applied=false
            # for bytes the speaker had already received.
            frames_written += 1
            transaction = await link.transact(frame, timeout)
            reconnects += transaction.reconnects
            write_replies.extend(transaction.replies)
            log(
                f"WRITE   |  RX {index}/{len(frames)}  |  {len(transaction.replies)} frame(s)  |  "
                f"attempts={transaction.attempts}  reconnects={transaction.reconnects}"
            )
            for reply in transaction.replies:
                log(f"ACK RAW |  {hex_bytes(reply)}")
                try:
                    decoded = describe_frame(reply)
                    ack_error = ack_error or decoded.get("command") == 0xEE
                    log("ACK DEC |  " + json.dumps(decoded, ensure_ascii=False))
                except ValueError as exc:
                    log(f"ACK DEC |  undecodable: {exc}")
        ack = "REJECTED" if ack_error else ("RECEIVED" if write_replies else "MISSING")
        status(system=f"VERIFYING {transaction_id}", protocol=f"{path} | ACK {ack}")
        log(f"ACK     |  {ack}  |  total={len(write_replies)} frame(s)")
        for index, frame in enumerate(read_frames, 1):
            log(f"READBACK|  TX {index}/{len(read_frames)}  |  {hex_bytes(frame)}")
            transaction = await link.transact(frame, timeout)
            read_replies.extend(transaction.replies)
            log(f"READBACK|  RX {index}/{len(read_frames)}  |  {len(transaction.replies)} frame(s)")
            for reply in transaction.replies:
                log(f"STATE   |  RAW {hex_bytes(reply)}")
                try:
                    log("STATE   |  DEC " + json.dumps(describe_frame(reply), ensure_ascii=False))
                except ValueError as exc:
                    log(f"STATE   |  undecodable: {exc}")
        verification = verify_eq_readback(gains, read_replies)
        # Three states, not two. "mismatch" means we decoded the pre-state and
        # it differed; "verified" means it already matched; anything else means
        # we never decoded it and know nothing -- which must not be reported as
        # having matched.
        changed = precheck.status == "mismatch" and verification.verified
        already_matched = precheck.verified and verification.verified
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        log(
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
            status(system="WRITE VERIFIED", protocol=f"{path} | {outcome}")
            result, title, severity = "verified", "Write verified", "information"
            message = f"Write response received; every EQ band matched read-back. {detail}"
        elif verification.verified:
            outcome = f"STATE MATCH / ACK {ack}"
            status(system="STATE MATCH / ACK ISSUE", protocol=f"{path} | ACK {ack}")
            result, title, severity = "ack-issue", "Write not fully verified", "warning"
            message = f"Read-back matches, but the write acknowledgement is {ack.lower()}."
        elif verification.status == "mismatch":
            outcome = "READBACK DIFFERS"
            status(system="WRITE MISMATCH", protocol=f"{path} | READBACK DIFFERS")
            result, title, severity = "mismatch", "Write verification failed", "error"
            message = verification.message
        else:
            outcome = "NO DECODABLE READBACK"
            status(system="WRITE UNVERIFIED", protocol=f"{path} | NO DECODABLE READBACK")
            result, title, severity = "unverified", "Write not verified", "warning"
            message = verification.message
        return WriteOutcome(
            transaction_id=transaction_id,
            path=path,
            read_path=read_path,
            ack=ack,
            precheck=precheck,
            verification=verification,
            reconnects=reconnects,
            elapsed_ms=elapsed_ms,
            result=result,
            outcome=outcome,
            title=title,
            message=message,
            severity=severity,
            frames=[hex_bytes(frame) for frame in frames],
        )
    except BaseException as exc:
        # BaseException, not Exception: a cancelled apply that already put
        # frames on the wire must still leave a record of what it sent.
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        log(
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
        raise
