import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest

from openjbl import protocol
from openjbl.connection import ConnectionManager, Link, LinkError


class FakeBleakClient:
    """Stands in for BleakClient, including its disconnected_callback contract."""

    instances: ClassVar[list["FakeBleakClient"]] = []

    def __init__(self, address, disconnected_callback=None):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.notify_callback = None
        self.writes: list[bytes] = []
        self.disconnect_calls = 0
        self.write_error: Exception | None = None
        self.fail_writes = 0
        characteristic = SimpleNamespace(properties=["write"], uuid="tx", description="tx")
        self.services = SimpleNamespace(
            get_characteristic=lambda _uuid: characteristic,
            __iter__=lambda _self: iter(()),
        )
        FakeBleakClient.instances.append(self)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    async def start_notify(self, _uuid, callback):
        self.notify_callback = callback

    async def stop_notify(self, _uuid):
        self.notify_callback = None

    async def write_gatt_char(self, _characteristic, data, response):
        if self.write_error is not None:
            raise self.write_error
        if self.fail_writes > 0:
            self.fail_writes -= 1
            raise OSError("radio busy")
        self.writes.append(bytes(data))

    def push(self, data: bytes) -> None:
        """Simulate an inbound notification."""
        self.notify_callback(None, bytearray(data))

    def drop(self) -> None:
        """Simulate an unexpected link loss."""
        self.is_connected = False
        if self.disconnected_callback is not None:
            self.disconnected_callback(self)


@pytest.fixture(autouse=True)
def fake_bleak(monkeypatch):
    import bleak

    FakeBleakClient.instances = []
    monkeypatch.setattr(bleak, "BleakClient", FakeBleakClient)
    return FakeBleakClient


@pytest.fixture(autouse=True)
def instant_delays(monkeypatch):
    """Collapse the APK's 1 s / 800 ms waits so tests stay fast."""
    from openjbl import connection

    monkeypatch.setattr(connection, "RECONNECT_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(connection, "REWRITE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(connection, "REPLY_DRAIN_SECONDS", 0.0)


async def _answer(link: Link, client: FakeBleakClient, request: bytes, reply: bytes):
    """Run a transaction, feeding `reply` once the request has been written."""

    async def responder():
        while not client.writes:
            await asyncio.sleep(0)
        client.push(reply)

    task = asyncio.ensure_future(responder())
    try:
        return await link.transact(request, timeout=1.0)
    finally:
        task.cancel()


@pytest.mark.asyncio
async def test_acquire_reuses_the_open_link_instead_of_reconnecting():
    manager = ConnectionManager()
    first = await manager.acquire("AA:BB:CC")
    second = await manager.acquire("aabbcc")
    assert first is second
    assert len(FakeBleakClient.instances) == 1, "a second connect would defeat holding the link open"


@pytest.mark.asyncio
async def test_link_stays_subscribed_across_transactions():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    await _answer(link, client, protocol.request_eq_mode(), bytes.fromhex("AA 62 01 06"))
    assert client.notify_callback is not None, "subscription must outlive the transaction"


@pytest.mark.asyncio
async def test_unsolicited_push_is_not_reported_as_a_reply():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    request = protocol.set_eq_mode(6)
    ack = bytes.fromhex("AA 00 02 63 00")
    notify_change = bytes.fromhex("AA 64 01 06")

    async def responder():
        while not client.writes:
            await asyncio.sleep(0)
        client.push(notify_change)  # speaker pushes first
        client.push(ack)

    task = asyncio.ensure_future(responder())
    try:
        result = await link.transact(request, timeout=1.0)
    finally:
        task.cancel()

    assert result.replies == [ack]
    assert link.unsolicited == [notify_change], "the push must be recorded, not returned as an ACK"


def test_advanced_eq_set_is_acknowledged_by_the_ret_frame_not_a_dev_ack():
    """SetAdvancedEQCommand/SetAdvancedNewEQCommand both list RET_ADVANCE_EQ as
    their response command; they are not DEV_ACK-acknowledged."""
    request = protocol.set_advanced_levels(0xC1, [0, 0, 0, 0, 0, 0, 0])
    assert protocol.reply_matches(request, bytes.fromhex("AA 99 00 01 00")) is True
    assert protocol.reply_matches(request, bytes.fromhex("AA 00 02 97 00")) is False, "0x97 is not DEV_ACK-acked"
    assert protocol.reply_matches(request, bytes.fromhex("AA EE 01 97")) is True
    assert protocol.reply_matches(request, bytes.fromhex("AA 64 01 06")) is False
    assert protocol.reply_matches(request, bytes.fromhex("AA 62 01 06")) is False


def test_dev_ack_must_echo_the_command_it_acknowledges():
    """SetEQModeCommand.onReceive checks command 0x00 with payload[0]==0x63 and
    payload[1]==0, so an ACK for a different command must not be accepted."""
    request = protocol.set_eq_mode(6)
    assert protocol.reply_matches(request, bytes.fromhex("AA 00 02 63 00")) is True
    assert protocol.reply_matches(request, bytes.fromhex("AA 00 02 6E 00")) is False, "that ACK is for SET_SIMPLE_EQ"
    assert protocol.reply_matches(request, bytes.fromhex("AA 00 02 63 01")) is False, "non-zero status is not an ACK"
    assert protocol.reply_matches(request, bytes.fromhex("AA 64 01 06")) is False


def test_simple_eq_set_accepts_either_ack_shape():
    """SetSimpleEqCommand.onReceive accepts a DEV_ACK echoing 0x6E or a bare
    RET_SIMPLE_EQ frame."""
    request = protocol.set_simple_eq(0xC1, 1, 2, 3)
    assert protocol.reply_matches(request, bytes.fromhex("AA 00 02 6E 00")) is True
    assert protocol.reply_matches(request, bytes.fromhex("AA 6D 04 06 C1 01 02")) is True
    assert protocol.reply_matches(request, bytes.fromhex("AA 64 01 06")) is False


def test_read_requests_only_accept_their_own_ret_frame():
    assert protocol.reply_matches(protocol.request_firmware_version(), bytes.fromhex("AA 42 01 03")) is True
    assert protocol.reply_matches(protocol.request_firmware_version(), bytes.fromhex("AA 62 01 06")) is False
    assert protocol.reply_matches(protocol.request_eq_mode(), bytes.fromhex("AA 62 01 06")) is True
    assert protocol.reply_matches(protocol.request_advanced_eq(), bytes.fromhex("AA 99 00 01 00")) is True


@pytest.mark.asyncio
async def test_unexpected_drop_triggers_reconnect_and_bumps_generation():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    generation = link.generation
    FakeBleakClient.instances[0].drop()
    assert manager.holds_generation("AA:BB:CC", generation) is False
    assert link._reconnect_task is not None
    await link._reconnect_task
    assert link.connected is True
    assert link.reconnects == 1
    assert link.generation != generation, "a recovered link is not the link that was authorised"


@pytest.mark.asyncio
async def test_reconnect_gives_up_after_three_attempts():
    from openjbl import connection

    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    attempts = 0

    async def failing_connect():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("speaker is off")

    FakeBleakClient.instances[0].drop()
    link.connect = failing_connect  # type: ignore[method-assign]
    await link._reconnect_task
    assert attempts == connection.MAX_RECONNECT_ATTEMPTS
    assert link.connected is False


@pytest.mark.asyncio
async def test_release_does_not_reconnect():
    manager = ConnectionManager()
    await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    await manager.release("AA:BB:CC")
    assert client.disconnect_calls == 1
    assert manager.live("AA:BB:CC") is None
    assert len(FakeBleakClient.instances) == 1, "a deliberate release must not trigger recovery"


@pytest.mark.asyncio
async def test_failed_write_is_retried_and_surfaced():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    client.fail_writes = 1  # the first write fails, the rewrite succeeds

    result = await _answer(link, client, protocol.request_eq_mode(), bytes.fromhex("AA 62 01 06"))
    assert result.attempts == 2, "the retry must be reported, not hidden from the audit record"


@pytest.mark.asyncio
async def test_write_failure_raises_after_max_attempts():
    from openjbl import connection

    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    FakeBleakClient.instances[0].write_error = OSError("radio busy")
    with pytest.raises(LinkError, match=f"after {connection.MAX_WRITE_ATTEMPTS} attempts"):
        await link.transact(protocol.request_eq_mode(), timeout=0.05)


@pytest.mark.asyncio
async def test_response_timeout_is_not_retried():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    with pytest.raises(TimeoutError):
        await link.transact(protocol.request_eq_mode(), timeout=0.02)
    assert len(client.writes) == 1, "the app's watchdog does not resend on a response timeout"


@pytest.mark.asyncio
async def test_transactions_are_serialised_per_link():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    in_flight = 0
    peak = 0
    collect = link._collect

    async def counting_collect(request, timeout):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            return await collect(request, timeout)
        finally:
            in_flight -= 1

    link._collect = counting_collect  # type: ignore[method-assign]

    async def responder():
        while True:
            while not client.writes:
                await asyncio.sleep(0)
            client.writes.clear()
            client.push(bytes.fromhex("AA 62 01 06"))
            await asyncio.sleep(0)

    task = asyncio.ensure_future(responder())
    try:
        await asyncio.gather(
            link.transact(protocol.request_eq_mode(), timeout=1.0),
            link.transact(protocol.request_eq_mode(), timeout=1.0),
        )
    finally:
        task.cancel()
    assert peak == 1, "P4 reassembly and reply matching both assume one exchange at a time"


@pytest.mark.asyncio
async def test_split_legacy_frame_is_reassembled_across_notifications():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    whole = bytes.fromhex("AA 42 04 03 00 07 01")

    async def responder():
        while not client.writes:
            await asyncio.sleep(0)
        client.push(whole[:3])
        client.push(whole[3:])

    task = asyncio.ensure_future(responder())
    try:
        result = await link.transact(protocol.request_firmware_version(), timeout=1.0)
    finally:
        task.cancel()
    assert result.replies == [whole]


def test_p4_replies_are_matched_by_command_id_not_just_the_header():
    """CommandProcessor.java:541-547 reads the command id at offset 2. Matching on
    the 0x00DD header alone lets any P4 frame answer any P4 request."""
    request = protocol.p4_request_eq()[0]  # a SET_DEVICE_INFO_0002 carrying an EQ query
    data = protocol.p4_frame(protocol.P4_GET_DEVICE_INFO, b"\x02\x0e\x01\x00")
    status = protocol.p4_frame(protocol.P4_SET_DEVICE_INFO, b"\x00")
    push = protocol.p4_frame(protocol.P4_NOTIFICATION_TO_APP, b"\x02\x0e")
    analytics = protocol.p4_frame(0x0201, b"\x00")

    assert protocol.reply_matches(request, data) is True
    assert protocol.reply_matches(request, push) is False, "a device push is not a reply"
    assert protocol.reply_matches(request, analytics) is False, "analytics does not answer an EQ query"
    assert protocol.reply_matches(request, status) is True, "the status echo is a reply..."
    assert protocol.reply_completes(request, status) is False, "...but carries no data, so it must not end the wait"
    assert protocol.reply_completes(request, data) is True


@pytest.mark.asyncio
async def test_p4_status_frame_does_not_end_the_wait_for_the_data_frame():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    request = protocol.p4_request_eq()[0]
    status = protocol.p4_frame(protocol.P4_SET_DEVICE_INFO, b"\x00")
    data = protocol.p4_frame(protocol.P4_GET_DEVICE_INFO, b"\x02\x0e\x01\x00")

    async def responder():
        while not client.writes:
            await asyncio.sleep(0)
        client.push(status)  # bare status code first
        await asyncio.sleep(0)
        client.push(data)  # then the frame that actually carries the EQ info

    task = asyncio.ensure_future(responder())
    try:
        result = await link.transact(request, timeout=1.0)
    finally:
        task.cancel()
    assert data in result.replies, "the EQ data frame must not be lost behind the status echo"


@pytest.mark.asyncio
async def test_a_transaction_recovers_a_dropped_link_without_racing_the_reconnect():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    FakeBleakClient.instances[0].drop()

    async def responder():
        while len(FakeBleakClient.instances) < 2 or not FakeBleakClient.instances[-1].writes:
            await asyncio.sleep(0)
        FakeBleakClient.instances[-1].push(bytes.fromhex("AA 62 01 06"))

    task = asyncio.ensure_future(responder())
    try:
        result = await link.transact(protocol.request_eq_mode(), timeout=1.0)
    finally:
        task.cancel()
    assert result.replies == [bytes.fromhex("AA 62 01 06")]
    assert len(FakeBleakClient.instances) == 2, "transact must join the reconnect, not start a rival one"


@pytest.mark.asyncio
async def test_a_stale_clients_drop_does_not_tear_down_the_live_link():
    """Every BleakClient keeps the disconnect callback for life, so an orphan's
    late drop must not revoke a generation that is still good."""
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    orphan = FakeBleakClient.instances[0]
    orphan.drop()
    await link._reconnect_task
    generation = link.generation
    assert link.connected is True
    orphan.drop()  # the old client finally reports its own death
    assert link.connected is True, "the live link must survive an orphan's callback"
    assert link.generation == generation


@pytest.mark.asyncio
async def test_a_link_that_cannot_subscribe_is_not_kept(monkeypatch):
    """A connected but unsubscribed client is deaf: writes reach the speaker and
    the reply has nowhere to arrive, so every later call reports a timeout for a
    write that actually landed. It must not be cached, or even stay connected."""
    manager = ConnectionManager()

    async def no_subscription(_self, _uuid, _callback):
        raise OSError("CCCD write rejected")

    monkeypatch.setattr(FakeBleakClient, "start_notify", no_subscription)
    with pytest.raises(OSError, match="CCCD write rejected"):
        await manager.acquire("AA:BB:CC")

    assert manager.live("AA:BB:CC") is None, "a deaf link must not be handed to the next caller"
    assert FakeBleakClient.instances[0].disconnect_calls == 1, "and must not be left holding a GATT slot"


@pytest.mark.asyncio
async def test_acquire_joins_an_in_flight_reconnect_instead_of_racing_it():
    """Two clients to one speaker orphans the loser: still connected, no longer
    referenced, holding one of the few GATT slots the speaker has."""
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    FakeBleakClient.instances[0].drop()  # starts the reconnect task

    again = await manager.acquire("AA:BB:CC")  # lands inside the reconnect window

    assert again is link
    await link.await_recovery()
    assert len(FakeBleakClient.instances) == 2, "exactly one new client, not two"
    assert link.connected is True
    assert manager.holds_generation("AA:BB:CC", link.generation) is True, "the live link must stay authorised"


@pytest.mark.asyncio
async def test_concurrent_connects_do_not_build_rival_clients():
    manager = ConnectionManager()
    link = Link("AA:BB:CC")
    await asyncio.gather(link.connect(), link.connect(), link.connect())
    assert len(FakeBleakClient.instances) == 1, "connect() must be single-flight"
    assert link.connected is True
    del manager


@pytest.mark.asyncio
async def test_idle_link_still_surfaces_pushes():
    """`listen` has no transaction in flight, so pushes must be reachable
    without one."""
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    push = bytes.fromhex("AA 64 01 06")
    client.push(push)
    assert await link.poll_unsolicited() == [push]
    assert link.unsolicited == [push]
    assert await link.poll_unsolicited() == [], "a push must only be reported once"


@pytest.mark.asyncio
async def test_follow_on_frames_of_one_answer_are_drained(monkeypatch):
    """A multi-frame answer must come back whole, not truncated to its first frame."""
    from openjbl import connection

    monkeypatch.setattr(connection, "REPLY_DRAIN_SECONDS", 0.05)
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    client = FakeBleakClient.instances[0]
    first = bytes.fromhex("AA 99 00 01 00")
    second = bytes.fromhex("AA 99 00 01 01")

    async def responder():
        while not client.writes:
            await asyncio.sleep(0)
        client.push(first)
        await asyncio.sleep(0.01)  # inside the drain window
        client.push(second)

    task = asyncio.ensure_future(responder())
    try:
        result = await link.transact(protocol.request_advanced_eq(), timeout=1.0)
    finally:
        task.cancel()
    assert result.replies == [first, second]


@pytest.mark.asyncio
async def test_reassembly_state_is_reset_on_reconnect():
    manager = ConnectionManager()
    link = await manager.acquire("AA:BB:CC")
    first = FakeBleakClient.instances[0]
    first.push(bytes.fromhex("AA 42 04 03"))  # half a frame, then the link dies
    assert link._decoder.pending is True
    first.drop()
    await link._reconnect_task
    assert link._decoder.pending is False, "a partial frame would corrupt the next decode"
