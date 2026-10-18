"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
# ruff: noqa: E731, N817, S106

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.errors import ConnectionClosed
from discord.voice import state as vs
from discord.voice.enums import ConnectionFlowState as CFS, OpCodes
from discord.voice.state import SocketEventReader, SocketReader, VoiceConnectionState


class FakeDaveSession:
    def __init__(self, *args):
        self.args = args
        self.calls = []

    def reinit(self, *args):
        self.calls.append(("reinit", args))

    def get_serialized_key_package(self):
        return b"kp"

    def reset(self):
        self.calls.append(("reset",))

    def set_passthrough_mode(self, *args):
        self.calls.append(("passthrough", args))


def make_closed(code):
    return ConnectionClosed(SimpleNamespace(close_code=code), shard_id=None, code=code)


@pytest_asyncio.fixture
async def vstate(monkeypatch):
    loop = asyncio.get_running_loop()
    guild = SimpleNamespace(id=10, change_voice_state=AsyncMock())
    channel = SimpleNamespace(id=20, guild=guild)
    bucket = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(id=21, self_deaf=False, self_mute=False)
        )
    )
    client = SimpleNamespace(
        loop=loop,
        channel=channel,
        guild=guild,
        user=SimpleNamespace(id=99),
        supported_modes=("a", "b"),
        _id_to_ssrc={1: 2},
        _ssrc_to_id={2: 1},
        stop=MagicMock(),
        cleanup=MagicMock(),
        _state=SimpleNamespace(
            self_id=99, _guild_bucket=MagicMock(return_value=bucket)
        ),
    )
    client._bucket = bucket
    st = VoiceConnectionState(client)
    yield st
    st._socket_reader.stop()
    for t in (st._runner, st._connector):
        if t:
            t.cancel()


class FakeSock:
    def __init__(self):
        self.closed = False
        self.sent = []
        self.blocking = None
        self.recvs = []

    def close(self):
        self.closed = True

    def sendall(self, data):
        self.sent.append(data)

    def setblocking(self, flag):
        self.blocking = flag

    def recv(self, n):
        item = self.recvs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeWS:
    def __init__(self):
        self.closed_with = []
        self.sent_bytes = []
        self.sent_json = []
        self.secret_key = None
        self.seq_ack = 5
        self.polls = []

    def __bool__(self):
        return True

    async def close(self, code=1000):
        self.closed_with.append(code)

    async def send_as_bytes(self, op, data):
        self.sent_bytes.append((op, data))

    async def send_as_json(self, data):
        self.sent_json.append(data)

    async def poll_event(self):
        item = self.polls.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item()


# -- SocketReader -----------------------------------------------------------


def make_reader(**kwargs):
    state = SimpleNamespace(socket=FakeSock(), loop=None, _dispatch_task_set=set())
    return SocketReader(state, "reader", 16, **kwargs), state


def test_reader_register_pause_resume_stop():
    reader, _ = make_reader()
    assert reader.is_paused()
    assert not reader.is_running()
    cb = lambda data: None
    reader.register(cb)
    assert reader._running.is_set()
    assert not reader._idle_paused
    assert not reader.is_paused()
    reader.resume()
    reader.unregister(cb)
    assert reader._idle_paused
    assert not reader._running.is_set()
    reader.unregister(cb)
    reader.resume()
    assert reader._idle_paused
    assert not reader._running.is_set()
    reader.resume(force=True)
    assert reader._running.is_set()
    reader.pause()
    assert reader.is_paused()
    reader.stop()
    assert reader._end.is_set()
    assert reader._running.is_set()
    assert not reader.is_paused()
    reader._callbacks.append(cb)
    reader.pause()
    reader.resume()
    assert reader._running.is_set()


def test_event_reader_defaults():
    st = SimpleNamespace()
    reader = SocketEventReader(st)
    assert reader.buffer_size == 2048
    assert reader.name.startswith("voice-socket-event-reader:")
    assert reader.start_paused is True


def test_reader_run_lifecycle(monkeypatch):
    reader, _ = make_reader()
    seen = {}

    def fake_do_run():
        seen["started"] = reader.is_running()
        seen["paused"] = reader.is_paused()

    monkeypatch.setattr(reader, "_do_run", fake_do_run)
    reader._callbacks.append(lambda d: None)
    reader.run()
    assert seen == {"started": True, "paused": True}
    assert not reader.is_running()
    assert reader._callbacks == []
    assert reader._end.is_set()


def test_reader_run_logs_errors(monkeypatch, caplog):
    reader, _ = make_reader(start_paused=False)

    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(reader, "_do_run", boom)
    reader.run()
    assert "An error occurred while running the socket reader" in caplog.text
    assert not reader.is_running()


def test_reader_do_run_dispatch(monkeypatch):
    reader, state = make_reader()
    created = []

    class FakeTask:
        def __init__(self):
            self.cbs = []

        def add_done_callback(self, cb):
            self.cbs.append(cb)

    state.loop = SimpleNamespace(create_task=lambda coro: (coro.close(), "t")[1])
    monkeypatch.setattr(
        vs.asyncio, "ensure_future", lambda t, loop: created.append(t) or FakeTask()
    )
    reader._callbacks.append(lambda data: None)

    def bad_ensure(*a, **k):
        raise RuntimeError("nope")

    sock = state.socket
    sock.recvs = [OSError("x"), b"hello"]
    steps = iter(
        [
            lambda: (_ for _ in ()).throw(ValueError("bad fd")),
            lambda: ([], [], []),
            lambda: ([sock], [], []),
            lambda: ([sock], [], []),
        ]
    )
    calls = {"n": 0}

    def fake_select(r, w, x, t):
        calls["n"] += 1
        try:
            result = next(steps)()
        finally:
            if calls["n"] == 4:
                reader._end.set()
        return result

    monkeypatch.setattr(vs.select, "select", fake_select)
    reader._running.set()
    reader._do_run()
    assert created == ["t"]
    assert len(state._dispatch_task_set) == 1

    reader._end.clear()
    monkeypatch.setattr(vs.asyncio, "ensure_future", bad_ensure)
    sock.recvs = [b"x"]
    steps2 = iter([lambda: ([sock], [], [])])

    def select2(*a):
        reader._end.set()
        return next(steps2)()

    monkeypatch.setattr(vs.select, "select", select2)
    reader._do_run()


def test_reader_do_run_waits_when_paused():
    reader, _ = make_reader()

    class FakeEvent:
        def __init__(self):
            self.flag = False
            self.waits = 0

        def is_set(self):
            return self.flag

        def wait(self):
            self.waits += 1
            reader._end.set()

    reader._running = FakeEvent()
    reader._do_run()
    assert reader._running.waits == 1
    assert reader._warned_wait is True


# -- VoiceConnectionState ---------------------------------------------------


def test_state_requires_self_id_and_channel():
    loop = asyncio.new_event_loop()
    try:
        base = {
            "loop": loop,
            "channel": SimpleNamespace(id=1),
            "guild": SimpleNamespace(id=2),
        }
        with pytest.raises(RuntimeError, match="self ID"):
            VoiceConnectionState(
                SimpleNamespace(**base, _state=SimpleNamespace(self_id=None))
            )
        base["channel"] = None
        with pytest.raises(RuntimeError, match="channel"):
            VoiceConnectionState(
                SimpleNamespace(**base, _state=SimpleNamespace(self_id=1))
            )
        assert threading.active_count() >= 1
    finally:
        loop.close()


async def test_state_properties_and_setter(vstate):
    st = vstate
    assert st.user_ssrc_map == {1: 2}
    assert st.ssrc_user_map == {2: 1}
    assert st.max_dave_proto_version >= 1
    assert st.channel_id == 20
    assert st.guild_id == 10
    assert st.user.id == 99
    assert st.guild.id == 10
    assert st.supported_modes == ("a", "b")
    assert not st.is_connected()
    assert st.wait_for(timeout=0) is False
    st.state = CFS.connected
    assert st.is_connected()
    assert st.state is CFS.connected
    assert st.wait_for(timeout=0) is True
    st.state = CFS.disconnected
    assert not st._connected.is_set()
    st.state = CFS.disconnected
    assert (await st.get_self_voice_state()).id == 21
    flags = await st._self_voice_flags()
    assert flags == {"self_deaf": False, "self_mute": False}
    st.client._state.self_id = None
    assert await st.get_self_voice_state() is None
    st.client._state.self_id = 99
    st.client._bucket.get.return_value = None
    st.self_deaf = True
    assert (await st._self_voice_flags())["self_deaf"] is True


async def test_wait_for_state_paths(vstate):
    st = vstate
    with pytest.raises(ValueError):
        await st._wait_for_state()
    st.state = CFS.connected
    await st._wait_for_state(CFS.connected)
    with pytest.raises(asyncio.TimeoutError):
        await st._wait_for_state(CFS.disconnected, timeout=0.01)

    async def later():
        await asyncio.sleep(0.01)
        st.state = CFS.disconnected

    task = asyncio.create_task(later())
    await st._wait_for_state(CFS.disconnected, timeout=1)
    await task
    waiter = st.wait_for(CFS.disconnected, timeout=0.1)
    await waiter


async def test_socket_helpers(vstate, monkeypatch):
    st = vstate
    fake = FakeSock()
    monkeypatch.setattr(vs.socket, "socket", lambda *a: fake)
    st._create_socket()
    assert st.socket is fake
    assert fake.blocking is False
    st.send_packet(b"x")
    assert fake.sent == [b"x"]
    cb = lambda d: None
    st.add_socket_listener(cb)
    assert cb in st._socket_reader._callbacks
    st.remove_socket_listener(cb)
    assert cb not in st._socket_reader._callbacks


async def test_voice_state_update_disconnects(vstate, monkeypatch):
    st = vstate
    st.disconnect = AsyncMock()
    data = SimpleNamespace(channel_id=None, session_id="s")
    await st.voice_state_update(data)
    st.disconnect.assert_awaited_once()
    assert st._disconnected.is_set()
    st._expecting_disconnect = True
    await st.voice_state_update(data)
    assert st._expecting_disconnect is False
    st.disconnect.assert_awaited_once()


async def test_voice_state_update_handshake(vstate):
    st = vstate
    st._update_voice_channel = AsyncMock()
    st.state = CFS.set_guild_voice_state
    await st.voice_state_update(SimpleNamespace(channel_id=20, session_id="s"))
    assert st.state is CFS.got_voice_state_update
    assert st.session_id == "s"
    st._update_voice_channel.assert_not_awaited()

    st.state = CFS.set_guild_voice_state
    await st.voice_state_update(SimpleNamespace(channel_id=30, session_id="s"))
    st._update_voice_channel.assert_awaited_once_with(30)

    st.state = CFS.got_voice_server_update
    await st.voice_state_update(SimpleNamespace(channel_id=20, session_id="s"))
    assert st.state is CFS.got_both_voice_updates

    st.state = CFS.connected
    st._update_voice_channel.reset_mock()
    await st.voice_state_update(SimpleNamespace(channel_id=31, session_id="s"))
    st._update_voice_channel.assert_awaited_once_with(31)


async def test_voice_state_update_moved_while_connecting(vstate):
    st = vstate
    st._update_voice_channel = AsyncMock()
    st.soft_disconnect = AsyncMock()
    st.connect = AsyncMock()
    st.state = CFS.websocket_connected
    await st.voice_state_update(SimpleNamespace(channel_id=20, session_id="s"))
    st.soft_disconnect.assert_not_awaited()
    await st.voice_state_update(SimpleNamespace(channel_id=40, session_id="s"))
    st._update_voice_channel.assert_awaited_once_with(40)
    st.soft_disconnect.assert_awaited_once_with(with_state=CFS.got_voice_state_update)
    kwargs = st.connect.await_args.kwargs
    assert kwargs["resume"] is False
    assert kwargs["wait"] is False
    st.state = CFS.disconnected
    st.connect.reset_mock()
    await st.voice_state_update(SimpleNamespace(channel_id=40, session_id="s"))
    st.connect.assert_not_awaited()


async def test_voice_server_update(vstate, monkeypatch):
    st = vstate
    fake = FakeSock()
    monkeypatch.setattr(vs.socket, "socket", lambda *a: fake)
    ev = SimpleNamespace(token=None, guild_id=10, endpoint="x")
    await st.voice_server_update(ev)
    assert st.endpoint is None

    ev = SimpleNamespace(token="t", guild_id=10, endpoint="wss://host:80")  # nosec B106
    st.state = CFS.set_guild_voice_state
    await st.voice_server_update(ev)
    assert st.endpoint == "host:80"
    assert st.state is CFS.got_voice_server_update
    assert st.socket is fake

    st.state = CFS.got_voice_state_update
    await st.voice_server_update(ev)
    assert st.state is CFS.got_both_voice_updates

    st.ws = FakeWS()
    st.state = CFS.connected
    await st.voice_server_update(ev)
    assert st.ws.closed_with == [4014]
    assert st.state is CFS.got_voice_server_update


async def test_voice_server_update_unexpected(vstate, monkeypatch):
    st = vstate
    monkeypatch.setattr(vs.socket, "socket", lambda *a: FakeSock())
    st.soft_disconnect = AsyncMock()
    st.connect = AsyncMock()
    st.state = CFS.websocket_connected
    st.token, st.server_id, st.endpoint = "t", 10, "host"
    ev = SimpleNamespace(token="t", guild_id=10, endpoint="host")  # nosec B106
    await st.voice_server_update(ev)
    st.soft_disconnect.assert_not_awaited()
    ev = SimpleNamespace(token="t2", guild_id=10, endpoint="host")  # nosec B106
    await st.voice_server_update(ev)
    st.soft_disconnect.assert_awaited_once_with(with_state=CFS.got_voice_server_update)
    st.connect.assert_awaited_once()
    st.state = CFS.disconnected
    st.soft_disconnect.reset_mock()
    await st.voice_server_update(SimpleNamespace(token="t3", guild_id=1, endpoint="h"))  # nosec B106
    st.soft_disconnect.assert_not_awaited()


async def test_connect_and_wrap_connect(vstate):
    st = vstate
    done = []

    async def fake_connect(*args):
        done.append(args)

    st._connect = fake_connect
    old_connector = asyncio.create_task(asyncio.sleep(10))
    old_runner = asyncio.create_task(asyncio.sleep(10))
    st._connector, st._runner = old_connector, old_runner
    await st.connect(
        reconnect=False, timeout=3, self_deaf=True, self_mute=False, resume=True
    )
    await asyncio.sleep(0)
    assert old_connector.cancelled() or old_connector.cancelling()
    assert st._runner is None
    assert done == [(False, 3, True, False, True)]
    assert (st.timeout, st.reconnect) == (3, False)
    await st.connect(
        reconnect=True,
        timeout=4,
        self_deaf=False,
        self_mute=False,
        resume=False,
        wait=False,
    )
    await st._connector


@pytest.mark.parametrize(
    ("exc", "expect_soft", "expect_disc"),
    [
        (asyncio.CancelledError(), True, False),
        (asyncio.TimeoutError(), False, True),
        (RuntimeError("x"), False, True),
    ],
)
async def test_wrap_connect_errors(vstate, exc, expect_soft, expect_disc):
    st = vstate
    st.soft_disconnect = AsyncMock()
    st.disconnect = AsyncMock()
    st._connect = AsyncMock(side_effect=exc)
    with pytest.raises(type(exc)):
        await st._wrap_connect(True, 1, False, False, False)
    assert st.soft_disconnect.await_count == int(expect_soft)
    assert st.disconnect.await_count == int(expect_disc)


async def test_inner_connect_success_and_retry(vstate, monkeypatch):
    st = vstate
    sleeps = []

    async def fake_sleep(t):
        sleeps.append(t)

    monkeypatch.setattr(vs.asyncio, "sleep", fake_sleep)
    st._voice_connect = AsyncMock()
    st._wait_for_state = AsyncMock()
    st.disconnect = AsyncMock()
    ws = FakeWS()
    st._connect_websocket = AsyncMock(side_effect=[make_closed(4000), ws])
    st._handshake_websocket = AsyncMock()
    await st._inner_connect(True, False, False, False)
    assert st.state is CFS.set_guild_voice_state
    assert sleeps == [1]
    assert st.ws is ws
    assert st._voice_connect.await_count == 2
    st.disconnect.assert_awaited_once_with(cleanup=False)


async def test_inner_connect_no_reconnect_raises(vstate):
    st = vstate
    st._voice_connect = AsyncMock()
    st._wait_for_state = AsyncMock()
    st.disconnect = AsyncMock()
    st._connect_websocket = AsyncMock(side_effect=make_closed(4000))
    with pytest.raises(ConnectionClosed):
        await st._inner_connect(False, False, False, False)
    st.disconnect.assert_awaited_once_with()


async def test_connect_starts_runner(vstate):
    st = vstate
    st._inner_connect = AsyncMock()
    polled = asyncio.Event()

    async def poll(reconnect):
        polled.set()

    st._poll_ws = poll
    await st._connect(True, 1, False, False, False)
    runner = st._runner
    assert runner is not None
    await polled.wait()
    await st._connect(True, 1, False, False, False)
    assert st._runner is runner
    st._inner_connect.side_effect = asyncio.TimeoutError
    st._inner_connect = AsyncMock(side_effect=asyncio.TimeoutError)
    with pytest.raises(asyncio.TimeoutError):
        await st._connect(True, 0.5, False, False, False)


async def test_voice_connect_disconnect_helpers(vstate):
    st = vstate
    await st._voice_connect(self_deaf=True, self_mute=True)
    st.client.guild.change_voice_state.assert_awaited_with(
        channel=st.client.channel, self_deaf=True, self_mute=True
    )
    await st._voice_disconnect()
    st.client.guild.change_voice_state.assert_awaited_with(channel=None)
    assert st._expecting_disconnect
    assert not st._disconnected.is_set()
    assert st.state is CFS.disconnected
    other = SimpleNamespace(id=77)
    await st._move_to(other)
    assert st.state is CFS.set_guild_voice_state
    st.client._state._guild_bucket.return_value.get.return_value = "chan"
    await st._update_voice_channel(5)
    assert st.client.channel == "chan"
    await st._update_voice_channel(None)
    assert st.client.channel in (None, 0)


async def test_connect_and_handshake_websocket(vstate, monkeypatch):
    st = vstate
    ws = FakeWS()
    from_state = AsyncMock(return_value=ws)
    monkeypatch.setattr(vs.VoiceWebSocket, "from_state", from_state)
    assert await st._connect_websocket(True) is ws
    assert from_state.await_args.kwargs["seq_ack"] == -1
    assert st.state is CFS.websocket_connected
    st.ws = ws
    await st._connect_websocket(False)
    assert from_state.await_args.kwargs["seq_ack"] == 5

    def set_ip():
        st.ip = "1.1.1.1"

    def set_key():
        ws.secret_key = [1]

    ws.polls = [lambda: None, set_ip, set_key]
    st.ip = None
    await st._handshake_websocket()
    assert st.state is CFS.connected


async def test_disconnect_full(vstate):
    st = vstate
    st.ws = FakeWS()
    st.socket = FakeSock()
    st.state = CFS.connected
    st.ip, st.port = "1", 2
    st.timeout = 0.01
    await st.disconnect(wait=True)
    assert st.state is CFS.disconnected
    assert st.ws.closed_with == [1000]
    assert st.socket.closed
    assert st.ip is vs.MISSING
    assert st.port is vs.MISSING
    st.client.stop.assert_called_once()
    st.client.cleanup.assert_called_once()
    assert st._socket_reader._end.is_set()


async def test_disconnect_variants(vstate):
    st = vstate
    st.timeout = 0.01
    st.state = CFS.disconnected
    await st.disconnect(force=False)
    st.client.stop.assert_not_called()
    st.client.guild.change_voice_state.side_effect = RuntimeError("x")
    await st.disconnect(cleanup=False)
    st.client.stop.assert_not_called()
    st.client.guild.change_voice_state.side_effect = None
    st._voice_disconnect = AsyncMock(side_effect=st._disconnected.set)
    await st.disconnect(cleanup=False, wait=True)
    st._disconnected.clear()
    st._voice_disconnect = AsyncMock()
    await st.disconnect(cleanup=False, wait=True)


async def test_disconnect_wait_cancelled_and_timeout(vstate, monkeypatch):
    st = vstate
    st._voice_disconnect = AsyncMock()
    for exc in (asyncio.TimeoutError(), asyncio.CancelledError()):

        async def fake_wait_for(coro, timeout, _exc=exc):
            coro.close()
            raise _exc

        monkeypatch.setattr(vs.asyncio, "wait_for", fake_wait_for)
        await st.disconnect(cleanup=False, wait=True)


async def test_soft_disconnect(vstate):
    st = vstate
    st.ws = FakeWS()
    st.socket = FakeSock()
    st._runner = asyncio.create_task(asyncio.sleep(10))
    runner = st._runner
    await st.soft_disconnect()
    await asyncio.sleep(0)
    assert runner.cancelled() or runner.cancelling()
    assert st._runner is None
    assert st.state is CFS.got_both_voice_updates
    assert st.socket.closed
    assert st.ip is vs.MISSING

    class BadWS(FakeWS):
        async def close(self, code=1000):
            raise RuntimeError("x")

    st.ws = BadWS()
    await st.soft_disconnect(with_state=CFS.disconnected)
    assert st.state is CFS.disconnected


async def test_move_to(vstate):
    st = vstate
    st.disconnect = AsyncMock()
    await st.move_to(None, 1)
    st.disconnect.assert_awaited_once_with(wait=True)
    await st.move_to(SimpleNamespace(id=20), 1)
    st.client.guild.change_voice_state.assert_not_awaited()

    st.state = CFS.connected
    st._wait_for_state = AsyncMock()
    await st.move_to(SimpleNamespace(id=30), 1)
    assert st.state is CFS.set_guild_voice_state

    st.state = CFS.connected
    st._wait_for_state = AsyncMock(side_effect=asyncio.TimeoutError)
    await st.move_to(SimpleNamespace(id=30), 1)
    assert st.state is CFS.connected

    async def timeout_and_change(*a, **k):
        st.state = CFS.got_both_voice_updates
        raise asyncio.TimeoutError

    st._wait_for_state = timeout_and_change
    st.state = CFS.connected
    await st.move_to(SimpleNamespace(id=30), 1)
    assert st.state is CFS.got_both_voice_updates


# -- _poll_ws ----------------------------------------------------------------


@pytest.fixture
def poller(vstate, monkeypatch):
    st = vstate
    st.ws = FakeWS()
    st.disconnect = AsyncMock()
    st.state = CFS.connected

    async def fake_sleep(_t):
        return None

    monkeypatch.setattr(vs.asyncio, "sleep", fake_sleep)
    return st


async def test_poll_ws_cancelled(poller):
    poller.ws.polls = [asyncio.CancelledError()]
    await poller._poll_ws(True)


async def test_poll_ws_code_1000(poller):
    poller.ws.polls = [make_closed(1000)]
    await poller._poll_ws(True)
    poller.disconnect.assert_awaited_once()
    poller.disconnect.reset_mock()
    poller._expecting_disconnect = True
    poller.ws.polls = [make_closed(1000)]
    await poller._poll_ws(True)
    poller.disconnect.assert_not_awaited()


@pytest.mark.parametrize("code", [4014, 4022])
async def test_poll_ws_discord_disconnect(poller, code):
    poller._disconnected.set()
    poller.ws.polls = [make_closed(code)]
    await poller._poll_ws(True)
    poller.disconnect.assert_awaited_once()


async def test_poll_ws_forced_reconnect(poller):
    poller._potential_reconnect = AsyncMock(side_effect=[True, False])
    poller.ws.polls = [make_closed(4014), make_closed(4014)]
    await poller._poll_ws(True)
    assert poller._potential_reconnect.await_count == 2
    poller.disconnect.assert_awaited_once()
    poller.state = CFS.disconnected
    poller.disconnect.reset_mock()
    poller._potential_reconnect = AsyncMock(return_value=False)
    poller.ws.polls = [make_closed(4014)]
    await poller._poll_ws(True)
    poller.disconnect.assert_not_awaited()


async def test_poll_ws_4021(poller):
    poller.ws.polls = [make_closed(4021)]
    await poller._poll_ws(True)
    poller.disconnect.assert_awaited_once()
    poller.state = CFS.disconnected
    poller.disconnect.reset_mock()
    poller.ws.polls = [make_closed(4021)]
    await poller._poll_ws(True)
    poller.disconnect.assert_not_awaited()


async def test_poll_ws_4015_outcomes(poller):
    poller._connect = AsyncMock(
        side_effect=[None, asyncio.TimeoutError(), RuntimeError("x")]
    )
    poller.ws.polls = [make_closed(4015)] * 2
    await poller._poll_ws(True)
    assert poller._connect.await_count == 2
    assert poller._connect.await_args.kwargs["resume"] is True
    poller.disconnect.assert_awaited_once()

    poller.disconnect.reset_mock()
    poller.ws.polls = [make_closed(4015)]
    await poller._poll_ws(True)
    poller.disconnect.assert_awaited_once()

    poller.state = CFS.disconnected
    poller.disconnect.reset_mock()
    poller._connect = AsyncMock(side_effect=asyncio.TimeoutError)
    poller.ws.polls = [make_closed(4015)]
    await poller._poll_ws(True)
    poller.disconnect.assert_not_awaited()


async def test_poll_ws_unhandled_code_no_reconnect(poller):
    poller.ws.polls = [make_closed(4999)]
    with pytest.raises(ConnectionClosed):
        await poller._poll_ws(False)
    poller.disconnect.assert_awaited_once()


async def test_poll_ws_reconnects_with_backoff(poller):
    poller._connect = AsyncMock(side_effect=[asyncio.TimeoutError(), None])
    poller.ws.polls = [asyncio.TimeoutError(), asyncio.CancelledError()]
    await poller._poll_ws(True)
    poller.disconnect.assert_awaited_with(cleanup=False)
    assert poller._connect.await_count == 1


async def test_poll_ws_timeout_then_cancelled(poller):
    poller._connect = AsyncMock()
    poller.ws.polls = [asyncio.TimeoutError(), asyncio.CancelledError()]
    await poller._poll_ws(True)
    poller._connect.assert_awaited_once()
    assert poller._connect.await_args.kwargs["resume"] is False


async def test_potential_reconnect(vstate):
    st = vstate
    prev = FakeWS()
    st.ws = prev
    st._wait_for_state = AsyncMock(side_effect=asyncio.TimeoutError)
    assert await st._potential_reconnect() is False

    st._wait_for_state = AsyncMock()
    st.state = CFS.disconnected
    assert await st._potential_reconnect() is False

    st.state = CFS.got_voice_server_update
    new_ws = FakeWS()
    st._connect_websocket = AsyncMock(return_value=new_ws)
    st._handshake_websocket = AsyncMock()
    assert await st._potential_reconnect() is True
    assert st.ws is new_ws
    assert prev.closed_with == [1000]

    st._handshake_websocket = AsyncMock(side_effect=asyncio.TimeoutError)
    assert await st._potential_reconnect() is False


# -- DAVE --------------------------------------------------------------------


async def test_reinit_dave_session(vstate, monkeypatch):
    st = vstate
    monkeypatch.setattr(vs.davey, "DaveSession", FakeDaveSession)
    st.ws = FakeWS()
    await st.reinit_dave_session()
    assert st.dave_session is None
    assert st.ws.sent_bytes == []

    st.dave_protocol_version = 1
    await st.reinit_dave_session()
    assert st.dave_session.args == (1, 99, 20)
    assert st.ws.sent_bytes == [(OpCodes.mls_key_package, b"kp")]
    await st.reinit_dave_session()
    assert st.dave_session.calls == [("reinit", (1, 99, 20))]

    st.dave_protocol_version = 0
    await st.reinit_dave_session()
    assert st.dave_session.calls[-2:] == [("reset",), ("passthrough", (True, 10))]


async def test_recover_dave(vstate, monkeypatch):
    st = vstate
    st.ws = FakeWS()
    st.reinit_dave_session = AsyncMock()
    await st.recover_dave_from_invalid_commit(4)
    assert st.ws.sent_json == [{"op": 31, "d": {"transition_id": 4}}]
    st.reinit_dave_session.assert_awaited_once()


async def test_execute_dave_transition(vstate):
    st = vstate
    await st.execute_dave_transition(1)
    assert st.dave_pending_transition is None

    st.dave_session = FakeDaveSession()
    st.dave_protocol_version = 1
    st.dave_pending_transition = {"transition_id": 2, "protocol_version": 0}
    await st.execute_dave_transition(2)
    assert st.dave_protocol_version == 0
    assert st.downgraded_dave is True
    assert st.dave_pending_transition is None

    st.dave_pending_transition = {"transition_id": 3, "protocol_version": 1}
    await st.execute_dave_transition(3)
    assert st.dave_protocol_version == 1
    assert st.downgraded_dave is False
    assert ("passthrough", (True, 10)) in st.dave_session.calls

    st.dave_pending_transition = {"transition_id": 4, "protocol_version": 1}
    await st.execute_dave_transition(9)
    assert st.dave_protocol_version == 1
    assert st.dave_pending_transition is None
