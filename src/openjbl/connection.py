"""Persistent BLE link ownership, ported from JBL Portable 6.9.12.

The Android app holds one GATT link per MAC open for its whole process lifetime
(GattControllerImpl.java:92-95 keeps live BluetoothGatt objects in a MAC-keyed
map; connect() short-circuits with "was connected already" at :178-186 and
writes only ever fetch the cached handle at :996). It subscribes to
notifications once at service discovery and never unsubscribes (:774-778), runs
one command at a time (:321-327), and recovers from an unexpected drop with a
flat 1 s retry straight to the cached address (:939, :1101-1112).

It sends no keepalive of any kind: there is no ping, nop or heartbeat among the
94 command classes under sdk/command/, and no periodic timer in
sdk/impl/connect/. The link survives because Android simply keeps the GATT open.
So this module holds the link open and does not invent a heartbeat.

Whether the speaker itself drops an idle link is NOT answerable from the APK --
it would need an on-air capture against real hardware. The app's reactive
reconnect is equally consistent with "the speaker never drops idle links" and
with "it does, and the app just tolerates it".
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .protocol import IDENTIFIER, LegacyStreamDecoder, hex_bytes, reply_completes, reply_matches
from .transport import RX_UUID, SERVICE_UUID, TX_UUID

# Flat delay, no backoff, no jitter -- GattControllerImpl.java:939 posts a plain
# postDelayed(..., 1000L). Exponential backoff would diverge from the app.
RECONNECT_DELAY_SECONDS = 1.0
# maxReconnectCount -- AppConfig.json:2, enforced at GattControllerImpl.java:926.
MAX_RECONNECT_ATTEMPTS = 3
# maxRewriteCount / re-write delay -- AppConfig.json:4, GattControllerImpl.java:1084, :1092-1097.
MAX_WRITE_ATTEMPTS = 3
REWRITE_DELAY_SECONDS = 0.8
# commandTimeout -- AppConfig.json:12. The JSON asset overwrites the Java field
# default of 1500 at JBLConnectBaseApplication.java:170-179, so 2000 is live.
COMMAND_TIMEOUT_SECONDS = 2.0
# Quiet period allowed for follow-on frames of a single answer. Ours, not the
# app's: it is the drain window the previous transport already used.
REPLY_DRAIN_SECONDS = 0.12


class LinkError(RuntimeError):
    """The link is down and could not be recovered."""


@dataclass(frozen=True)
class TransactionResult:
    """A completed exchange, including the recovery it needed to get there.

    `attempts` and `reconnects` are surfaced rather than hidden: a caller that
    reports "already matched" for a write that silently succeeded on a retry
    would put a false record in the audit trail.
    """

    replies: list[bytes]
    attempts: int
    reconnects: int
    generation: int


@dataclass
class Link:
    """One BLE link, held open until released.

    `generation` increments on every connect and every drop, so anything bound
    to a specific generation can tell that the link it was authorised against no
    longer exists.
    """

    address: str
    service_uuid: str = SERVICE_UUID
    rx_uuid: str = RX_UUID
    tx_uuid: str = TX_UUID
    on_event: Callable[[str], None] = lambda message: None

    _client: Any = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _inbound: asyncio.Queue[bytes] = field(default_factory=asyncio.Queue, init=False, repr=False)
    _decoder: LegacyStreamDecoder = field(default_factory=LegacyStreamDecoder, init=False, repr=False)
    _generation: int = field(default=0, init=False)
    _reconnects: int = field(default=0, init=False)
    _releasing: bool = field(default=False, init=False)
    _reconnect_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    unsolicited: list[bytes] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.rx_uuid = self.rx_uuid.lower()
        self.tx_uuid = self.tx_uuid.lower()
        self.service_uuid = self.service_uuid.lower()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def reconnects(self) -> int:
        return self._reconnects

    @property
    def connected(self) -> bool:
        return self._client is not None and bool(self._client.is_connected)

    async def connect(self) -> None:
        from bleak import BleakClient

        self._releasing = False
        client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
        await client.connect()
        if not bool(client.is_connected):
            with contextlib.suppress(Exception):
                await client.disconnect()
            raise ConnectionError(f"BLE client did not reach connected state for {self.address}")
        self._client = client
        self._generation += 1
        # Reassembly is per-connection: a partial frame left over from a dropped
        # link would corrupt the next decode.
        self._decoder = LegacyStreamDecoder()
        # Drain rather than replace the queue: a _collect() parked on the old
        # object would never see a new one, and would sit there until it timed out.
        while not self._inbound.empty():
            self._inbound.get_nowait()
        await self._subscribe()

    async def _subscribe(self) -> None:
        """Subscribe once and stay subscribed for the life of the link.

        GattControllerImpl.java:774-778 enables the CCCD at service discovery and
        never unsubscribes -- unsolicited pushes at :427 depend on it. The app
        does not gate its send queue on the descriptor write (onDescriptorWrite
        is not even overridden), so neither do we.
        """

        def on_notify(_characteristic: object, data: bytearray) -> None:
            for frame in self._ingest(bytes(data)):
                self._inbound.put_nowait(frame)

        await self._client.start_notify(self.rx_uuid, on_notify)

    def _ingest(self, data: bytes) -> list[bytes]:
        """Reassemble inbound notifications into whole frames.

        Legacy frames are split across notifications and must be rebuilt;
        Protocol 4 frames carry their own length and arrive whole.
        """
        if (data[:1] and data[0] == IDENTIFIER) or self._decoder.pending:
            return [frame.encode() for frame in self._decoder.feed(data)]
        return [data]

    def _on_disconnect(self, client: Any) -> None:
        """Bleak's drop callback -- the signal the previous transport never had.

        Without this a drop stayed invisible until the next write failed.
        """
        if client is not self._client:
            # A client we no longer own: every BleakClient keeps this callback
            # bound for life, so an orphan's late drop must not tear down the
            # live link or revoke a generation that is still good.
            return
        self._client = None
        self._generation += 1
        if self._releasing:
            return
        self.on_event(f"LINK    |  Unexpected disconnect from {self.address}; reconnecting")
        with contextlib.suppress(RuntimeError):  # no running loop, e.g. during teardown
            self._reconnect_task = asyncio.get_running_loop().create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Flat 1 s retry, three attempts, straight to the cached address.

        Mirrors attemptReconnect (GattControllerImpl.java:925-941). The scanner
        is never consulted on the recovery path (:1101-1112), so we do not scan
        either. The app additionally gates retries on Android GATT status codes
        (133/0x22/257 at :868), which WinRT does not surface at all -- and that
        predicate sits in a JADX-flagged mis-decompiled region -- so we retry on
        any unexpected drop instead and cap it at the same 3.
        """
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            if self._releasing:
                return
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
            if self._releasing:
                return
            try:
                await self.connect()
            except Exception as exc:
                self.on_event(f"LINK    |  Reconnect {attempt}/{MAX_RECONNECT_ATTEMPTS} failed  |  {exc}")
                continue
            self._reconnects += 1
            self.on_event(f"LINK    |  Reconnected to {self.address} on attempt {attempt}")
            return
        self.on_event(f"LINK    |  Gave up after {MAX_RECONNECT_ATTEMPTS} reconnect attempts")

    async def _recover(self) -> None:
        """Bring the link back before a transaction, reusing the reconnect budget."""
        task = self._reconnect_task
        if task is not None and not task.done():
            await task  # a drop callback already started recovery; do not race it
        if not self.connected:
            await self.connect()

    async def _write(self, data: bytes) -> None:
        client = self._client
        if client is None or not bool(client.is_connected):
            raise LinkError(f"link to {self.address} is down")
        characteristic = client.services.get_characteristic(self.tx_uuid)
        if characteristic is None:
            raise LinkError(f"TX characteristic {self.tx_uuid} not found; run 'services' and override --tx")
        # The app forces WRITE_TYPE_NO_RESPONSE (setWriteType(1)) only for
        # PROTOCOL_GATT_BR_EDR at GattControllerImpl.java:784-786; plain BLE is
        # left at the characteristic default, i.e. write-with-response, which is
        # what the properties select here.
        response = "write" in characteristic.properties
        await client.write_gatt_char(characteristic, data, response=response)

    async def _collect(self, request: bytes, timeout: float) -> list[bytes]:
        """Gather the frames that answer `request`, routing pushes aside.

        Frames that do not answer the request -- NOTIFY_EQ_CHANGE above all --
        are recorded as unsolicited instead of being handed back as replies.
        Counting one of those as a write acknowledgement is how an unverified
        write used to look verified.
        """
        replies: list[bytes] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                data = await asyncio.wait_for(self._inbound.get(), remaining)
            except (asyncio.TimeoutError, TimeoutError):
                break
            if reply_matches(request, data):
                replies.append(data)
                if reply_completes(request, data):
                    break
                # An interim Protocol 4 status frame: keep waiting for the frame
                # that carries the data rather than reporting the status as the answer.
                continue
            self.unsolicited.append(data)
            self.on_event(f"LINK    |  Unsolicited frame, not a reply  |  {hex_bytes(data)}")
        if not replies:
            raise TimeoutError(f"no reply to {hex_bytes(request)} within {timeout:g}s")
        await asyncio.sleep(REPLY_DRAIN_SECONDS)
        while not self._inbound.empty():
            data = self._inbound.get_nowait()
            if reply_matches(request, data):
                replies.append(data)
            else:
                self.unsolicited.append(data)
        return replies

    async def transact(self, frame: bytes, timeout: float = COMMAND_TIMEOUT_SECONDS) -> TransactionResult:
        """Send one frame and return its replies, recovering the link if needed.

        Serialised per link, mirroring the app's one-command-at-a-time queue
        (GattControllerImpl.java:321-327). A failed *write* is retried up to
        maxRewriteCount; a *response timeout* is not, because the app does not
        retry those either -- its watchdog flushes the queue with TIMEOUT_STATUS
        and leaves the link alone (:113-152).

        We retry a failed write for ANY frame. The app is narrower: :1015 only
        re-writes a whitelist of command bytes (0x47, 0x11, 0xB1, 0x98, 0x41,
        0x4A, 0x44, 0x4D, 0xDD) that notably excludes all three EQ setters, so it
        gives up on a failed EQ write immediately. Retrying them is safe here
        because every EQ encoder emits absolute state -- a full category plus
        band list, no deltas or counters -- so re-sending converges rather than
        compounding. This is a deliberate divergence, not a port.
        """
        async with self._lock:
            reconnects_before = self._reconnects
            last_error: Exception | None = None
            for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
                try:
                    if not self.connected:
                        await self._recover()
                    await self._write(frame)
                except Exception as exc:
                    last_error = exc
                    self.on_event(f"LINK    |  Write attempt {attempt}/{MAX_WRITE_ATTEMPTS} failed  |  {exc}")
                    if attempt < MAX_WRITE_ATTEMPTS:
                        await asyncio.sleep(REWRITE_DELAY_SECONDS)
                    continue
                replies = await self._collect(frame, timeout)
                return TransactionResult(
                    replies=replies,
                    attempts=attempt,
                    reconnects=self._reconnects - reconnects_before,
                    generation=self._generation,
                )
            raise LinkError(f"write to {self.address} failed after {MAX_WRITE_ATTEMPTS} attempts: {last_error}")

    async def poll_unsolicited(self) -> list[bytes]:
        """Collect pushes that arrived while no transaction was in flight.

        Taking the lock is what makes this safe: it guarantees no transact() is
        mid-flight, so nothing queued can be somebody's pending reply. Without
        this, pushes are only ever noticed as a side effect of a transaction and
        an idle listener would sit silent while frames piled up unread.
        """
        async with self._lock:
            frames: list[bytes] = []
            while not self._inbound.empty():
                frames.append(self._inbound.get_nowait())
            self.unsolicited.extend(frames)
            return frames

    async def services(self) -> list[dict[str, Any]]:
        client = self._client
        if client is None or not bool(client.is_connected):
            raise LinkError(f"link to {self.address} is down")
        return [
            {
                "uuid": str(service.uuid),
                "description": service.description,
                "characteristics": [
                    {"uuid": str(char.uuid), "description": char.description, "properties": list(char.properties)}
                    for char in service.characteristics
                ],
            }
            for service in client.services
        ]

    async def release(self) -> None:
        """Close deliberately, suppressing the reconnect the drop would trigger.

        Mirrors isManualDisconnect (GattControllerImpl.java:194, cleared :864).
        """
        self._releasing = True
        task, self._reconnect_task = self._reconnect_task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()
        self._generation += 1


class ConnectionManager:
    """Owns at most one live link per address.

    The map-keyed-by-address ownership and the "was connected already"
    short-circuit both mirror GattControllerImpl (:92-95, :178-186). Holding the
    link across operations is the whole point: opening and destroying a link per
    frame is what made writes slow and drops unrecoverable.
    """

    def __init__(
        self,
        *,
        service_uuid: str = SERVICE_UUID,
        rx_uuid: str = RX_UUID,
        tx_uuid: str = TX_UUID,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.service_uuid = service_uuid
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.on_event = on_event or (lambda message: None)
        self._links: dict[str, Link] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _key(address: str) -> str:
        return address.replace(":", "").casefold()

    def live(self, address: str) -> Link | None:
        """The live link for `address`, or None if there is not one."""
        link = self._links.get(self._key(address))
        return link if link is not None and link.connected else None

    def holds_generation(self, address: str, generation: int) -> bool:
        """True while the exact link an operation was authorised against is still up."""
        link = self.live(address)
        return link is not None and link.generation == generation

    async def acquire(self, address: str) -> Link:
        key = self._key(address)
        # Held across the existence check AND the connect: acquire() awaits, so
        # without it a second caller arriving mid-connect would see connected ==
        # False and build a rival client for the same speaker.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            existing = self._links.get(key)
            if existing is not None and existing.connected:
                return existing
            link = existing or Link(
                address,
                service_uuid=self.service_uuid,
                rx_uuid=self.rx_uuid,
                tx_uuid=self.tx_uuid,
                on_event=self.on_event,
            )
            self._links[key] = link
            await link.connect()
            self.on_event(f"LINK    |  Connected to {address}; holding open")
            return link

    async def release(self, address: str) -> None:
        link = self._links.pop(self._key(address), None)
        if link is not None:
            await link.release()
            self.on_event(f"LINK    |  Released {address}")

    async def release_all(self) -> None:
        for address in list(self._links):
            await self.release(address)
