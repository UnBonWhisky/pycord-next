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
# ruff: noqa: S105

from __future__ import annotations

import asyncio
import datetime as dt
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

import nacl.secret

from discord.enums import SpeakingState
from discord.errors import ClientException
from discord.player import AudioSource
from discord.sinks.core import Sink
from discord.sinks.errors import RecordingException
from discord.utils import MISSING
from discord.voice import client as vclient
from discord.voice._types import VoiceProtocol
from discord.voice.client import VoiceClient
from discord.voice.enums import ConnectionFlowState, OpCodes


class FakeConn:
    def __init__(self):
        self.connected = True
        self.dave_session = None
        self.session_id = "sess"
        self.token = "tok"
        self.endpoint = "ep"
        self.ssrc = 1234
        self.mode = "xsalsa20_poly1305"
        self.secret_key = list(range(32))
        self.timeout = 12.0
        self.ws = SimpleNamespace(latency=0.5, average_latency=0.4)
        self.sent = []
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()
        self.move_to = AsyncMock()
        self.voice_state_update = AsyncMock()
        self.voice_server_update = AsyncMock()
        self.waited = []
        self.send_error = None

    def is_connected(self):
        return self.connected

    def wait_for(self, timeout=None):
        self.waited.append(timeout)

    def send_packet(self, packet):
        if self.send_error:
            raise self.send_error
        self.sent.append(packet)


class Reader:
    def __init__(self):
        self.packet_router = MagicMock()
        self.event_router = MagicMock()
        self.speaking_timer = MagicMock()
        self.stopped = False
        self.listening = True

    def __bool__(self):
        return True

    def stop(self):
        self.stopped = True

    def is_listening(self):
        return self.listening


@pytest_asyncio.fixture
async def vc(monkeypatch):
    loop = asyncio.get_running_loop()
    conn = FakeConn()
    removed = []
    state = SimpleNamespace(
        loop=loop,
        user=SimpleNamespace(id=7),
        _remove_voice_client=removed.append,
    )
    guild = SimpleNamespace(id=10)
    channel = SimpleNamespace(
        id=20, guild=guild, _get_voice_client_key=lambda: (10, "guild_id")
    )
    dispatched = []
    client = SimpleNamespace(
        _connection=state,
        loop=loop,
        dispatch=lambda *a, **k: dispatched.append((a, k)),
    )
    monkeypatch.setattr(VoiceClient, "create_connection_state", lambda self: conn)
    v = VoiceClient(client, channel)
    v._test = SimpleNamespace(conn=conn, removed=removed, dispatched=dispatched)
    return v


def test_missing_dependencies(monkeypatch):
    monkeypatch.setattr(vclient, "get_missing_voice_dependencies", lambda: ["nacl"])
    with pytest.raises(RuntimeError, match="nacl library is needed"):
        VoiceClient(SimpleNamespace(), SimpleNamespace())
    monkeypatch.setattr(
        vclient, "get_missing_voice_dependencies", lambda: ["nacl", "davey"]
    )
    with pytest.raises(RuntimeError, match="nacl, davey libraries are needed"):
        VoiceClient(SimpleNamespace(), SimpleNamespace())


async def test_properties_proxy_connection(vc):
    conn = vc._test.conn
    assert vc.guild.id == 10
    assert vc.user.id == 7
    assert (vc.session_id, vc.token, vc.endpoint) == ("sess", "tok", "ep")
    assert (vc.ssrc, vc.mode, vc.timeout) == (1234, "xsalsa20_poly1305", 12.0)
    assert vc.secret_key == conn.secret_key
    assert vc.ws is conn.ws
    assert vc.latency == 0.5
    assert vc.average_latency == 0.4
    conn.ws = None
    assert vc.latency == float("inf")
    assert vc.average_latency == float("inf")
    assert vc.is_dave_connection() is False
    assert vc.privacy_code is None
    conn.dave_session = SimpleNamespace(voice_privacy_code="123")
    assert vc.is_dave_connection() is True
    assert vc.privacy_code == "123"
    assert vc.is_connected()
    assert vc.wait_until_connected(3) is True
    assert conn.waited == [3]


async def test_checked_add_wraps(vc):
    vc.sequence = 65535
    vc.checked_add("sequence", 1, 65535)
    assert vc.sequence == 0
    vc.checked_add("sequence", 5, 65535)
    assert vc.sequence == 5


async def test_connect_disconnect_move(vc):
    conn = vc._test.conn
    await vc.connect(reconnect=True, timeout=3.0, self_deaf=True)
    conn.connect.assert_awaited_once_with(
        reconnect=True, timeout=3.0, self_deaf=True, self_mute=False, resume=False
    )
    reader = Reader()
    vc._reader = reader
    await vc.disconnect(force=True)
    conn.disconnect.assert_awaited_once_with(force=True, wait=True)
    assert reader.stopped
    assert vc._test.removed == [10]
    await vc.move_to(None, timeout=4)
    conn.move_to.assert_awaited_once_with(None, 4)


async def test_state_update_destroys_decoders_on_move(vc):
    reader = Reader()
    vc._reader = reader
    await vc.on_voice_state_update(SimpleNamespace(channel_id=None))
    reader.packet_router.destroy_all_decoders.assert_not_called()
    await vc.on_voice_state_update(SimpleNamespace(channel_id=20))
    reader.packet_router.destroy_all_decoders.assert_not_called()
    await vc.on_voice_state_update(SimpleNamespace(channel_id=21))
    reader.packet_router.destroy_all_decoders.assert_called_once()
    await vc.on_voice_server_update(SimpleNamespace())
    vc._test.conn.voice_server_update.assert_awaited_once()


async def test_ssrc_tracking(vc):
    reader = Reader()
    vc._reader = reader
    vc._add_ssrc(5, 50)
    assert vc._ssrc_to_id == {50: 5}
    assert vc._id_to_ssrc == {5: 50}
    reader.packet_router.set_user_id.assert_called_once_with(50, 5)
    vc._remove_ssrc(user_id=5)
    reader.speaking_timer.drop_ssrc.assert_called_once_with(50)
    assert vc._ssrc_to_id == {}
    assert vc._id_to_ssrc == {}
    vc._remove_ssrc(user_id=5)


async def test_recv_hook_ready_and_disconnect_destroys_decoder(vc):
    await vc._recv_hook(None, {"op": OpCodes.ready, "d": {"ssrc": 99}})
    assert vc._id_to_ssrc == {7: 99}
    reader = Reader()
    vc._reader = reader
    vc._add_ssrc(8, 80)
    vc._resolve_member = AsyncMock(return_value="m")
    vc._member_cache[8] = "m"
    events = []
    vc.dispatch = lambda *a: events.append(a)
    await vc._recv_hook(None, {"op": OpCodes.client_disconnect, "d": {"user_id": "8"}})
    reader.packet_router.destroy_decoder.assert_called_once_with(80)
    assert events == [("member_disconnect", "m", 80)]
    assert 8 not in vc._member_cache


async def test_resolve_member_and_peek(vc):
    users = SimpleNamespace(get=AsyncMock(return_value="user"))
    bucket = SimpleNamespace(get=AsyncMock(return_value=None))
    vc._state._users = users
    vc._state._guild_bucket = MagicMock(return_value=bucket)
    assert await vc._resolve_member(3) is None
    assert vc._member_cache[3] == "user"
    assert vc._peek_member(3) == "user"
    assert vc._peek_member(4) is None
    assert 4 in vc._members_resolving
    await asyncio.sleep(0.01)
    await asyncio.gather(*vc._resolve_tasks)
    assert vc._member_cache[4] == "user"
    assert 4 not in vc._members_resolving


async def test_peek_member_failures(vc):
    bucket = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("x")))
    vc._state._guild_bucket = MagicMock(return_value=bucket)
    assert vc._peek_member(1) is None
    await asyncio.sleep(0.01)
    assert 1 not in vc._members_resolving
    assert 1 not in vc._member_cache

    def closed(*a):
        raise RuntimeError("loop closed")

    vc.loop = SimpleNamespace(call_soon_threadsafe=closed)
    assert vc._peek_member(2) is None
    assert 2 not in vc._members_resolving


async def test_dispatch_to_listeners_sink_and_client(vc):
    seen = []

    async def good(*args, **kwargs):
        seen.append((args, kwargs))

    async def bad(*args, **kwargs):
        raise ValueError("x")

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    vc._event_listeners = {"on_thing": [good, bad, cancelled]}
    reader = Reader()
    vc._reader = reader
    vc.dispatch("thing", 1, a=2)
    await asyncio.gather(*vc._dispatch_task_set)
    assert seen == [((1,), {"a": 2})]
    reader.event_router.dispatch.assert_called_once_with("thing", 1, a=2)
    assert vc._test.dispatched == [(("thing", 1), {"a": 2})]
    vc._reader = MISSING
    vc.dispatch("none")


async def test_recv_hook_speaking_and_connect(vc):
    events = []
    vc.dispatch = lambda *a: events.append(a)
    vc._resolve_member = AsyncMock(
        side_effect=lambda uid: None if uid == 2 else f"m{uid}"
    )
    await vc._recv_hook(
        None, {"op": OpCodes.speaking, "d": {"user_id": "5", "ssrc": 9, "speaking": 1}}
    )
    assert events[0] == ("member_speaking_state_update", "m5", 9, SpeakingState.voice)
    await vc._recv_hook(
        None, {"op": OpCodes.clients_connect, "d": {"user_ids": ["1", "2"]}}
    )
    assert events[1:] == [("member_connect", "m1")]


@pytest.mark.parametrize(
    "mode",
    [
        "xsalsa20_poly1305",
        "xsalsa20_poly1305_suffix",
        "xsalsa20_poly1305_lite",
        "aead_xchacha20_poly1305_rtpsize",
    ],
)
async def test_voice_packet_encryption_roundtrip(vc, mode):
    vc._test.conn.mode = mode
    vc.sequence, vc.timestamp = 3, 960
    packet = bytes(vc._get_voice_packet(b"opus-data"))
    header = bytes(packet[:12])
    assert header[:2] == b"\x80\x78"
    assert struct.unpack(">HII", header[2:]) == (3, 960, 1234)
    key = bytes(vc.secret_key)
    if mode == "xsalsa20_poly1305":
        box = nacl.secret.SecretBox(key)
        assert box.decrypt(packet[12:], header + bytes(12)) == b"opus-data"
    elif mode == "xsalsa20_poly1305_suffix":
        box = nacl.secret.SecretBox(key)
        assert box.decrypt(packet[12:-24], packet[-24:]) == b"opus-data"
    elif mode == "xsalsa20_poly1305_lite":
        box = nacl.secret.SecretBox(key)
        nonce = bytes(packet[-4:]) + bytes(20)
        assert box.decrypt(bytes(packet[12:-4]), nonce) == b"opus-data"
        assert vc._incr_nonce == 1
    else:
        box = nacl.secret.Aead(key)
        nonce = bytes(packet[-4:]) + bytes(20)
        assert box.decrypt(packet[12:-4], header, nonce) == b"opus-data"


async def test_voice_packet_uses_dave_session(vc):
    session = SimpleNamespace(ready=True, encrypt_opus=lambda d: b"dave:" + d)
    vc._test.conn.dave_session = session
    packet = bytes(vc._get_voice_packet(b"x"))
    box = nacl.secret.SecretBox(bytes(vc.secret_key))
    assert box.decrypt(packet[12:], bytes(packet[:12]) + bytes(12)) == b"dave:x"


async def test_send_audio_packet(vc):
    vc.encoder = SimpleNamespace(
        SAMPLES_PER_FRAME=960, encode=lambda data, n: b"enc" + data
    )
    vc.send_audio_packet(b"pcm")
    assert vc.sequence == 1
    assert vc.timestamp == 960
    assert len(vc._test.conn.sent) == 1
    vc.send_audio_packet(b"opus", encode=False)
    vc._test.conn.send_error = OSError("gone")
    vc.send_audio_packet(b"opus", encode=False)
    assert vc.sequence == 3


class Src(AudioSource):
    def __init__(self, opus=False):
        self.opus = opus

    def read(self):
        return b""

    def is_opus(self):
        return self.opus


class FakePlayer:
    def __init__(self, source, client, *, after=None):
        self.source = source
        self.after = after
        self.started = False
        self.events = []

    def start(self):
        self.started = True

    def stop(self):
        self.events.append("stop")

    def pause(self):
        self.events.append("pause")

    def resume(self):
        self.events.append("resume")

    def set_source(self, source):
        self.source = source

    def is_playing(self):
        return not self.events

    def is_paused(self):
        return "pause" in self.events

    def played_frames(self):
        return 50


async def test_play_validation_and_start(vc, monkeypatch):
    monkeypatch.setattr(vclient, "AudioPlayer", FakePlayer)
    created = []
    monkeypatch.setattr(
        vclient.opus, "Encoder", lambda **kw: created.append(kw) or "encoder"
    )
    vc._test.conn.connected = False
    with pytest.raises(ClientException, match="Not connected"):
        vc.play(Src())
    vc._test.conn.connected = True
    with pytest.raises(TypeError, match="AudioSource"):
        vc.play(object())
    assert vc.play(Src(), bitrate=64) is None
    assert created[0]["bitrate"] == 64
    assert vc.encoder == "encoder"
    assert vc._player.started
    with pytest.raises(ClientException, match="Already playing"):
        vc.play(Src())
    assert vc.is_playing()
    assert not vc.is_paused()
    assert vc.elapsed() == dt.timedelta(seconds=1)
    vc.pause()
    assert vc.is_paused()
    vc.resume()
    assert vc._player.events == ["pause", "resume"]
    assert vc.source is vc._player.source
    new = Src()
    vc.source = new
    assert vc._player.source is new
    with pytest.raises(TypeError):
        vc.source = 5


async def test_play_wait_finish_future(vc, monkeypatch):
    monkeypatch.setattr(vclient, "AudioPlayer", FakePlayer)
    vc.encoder = "enc"
    called = []
    fut = vc.play(Src(opus=True), wait_finish=True, after=called.append)
    assert isinstance(fut, asyncio.Future)
    vc._player.after(None)
    assert await fut is None
    assert called == [None]
    vc._player = None
    fut3 = vc.play(Src(opus=True), wait_finish=True)
    vc._player.after(None)
    await fut3
    vc._player = None
    fut4 = vc.play(Src(opus=True), wait_finish=True)
    reader = Reader()
    vc._reader = reader
    player = vc._player
    vc.stop()
    assert await fut4 is None
    assert "stop" in player.events
    assert reader.stopped
    assert vc._player is None
    assert vc._player_future is None
    assert vc._reader is MISSING
    vc._set_future_result_if_pending(fut4, None)


async def test_idle_controls(vc):
    vc.pause()
    vc.resume()
    vc.stop()
    assert not vc.source
    assert vc.elapsed() == dt.timedelta()
    with pytest.raises(ValueError, match="not playing"):
        vc.source = Src()
    assert not vc.is_playing()
    assert not vc.is_paused()


async def test_recording_lifecycle(vc, monkeypatch):
    built = []

    def make_reader(sink, client, **kwargs):
        reader = Reader()
        built.append((sink, kwargs, reader))
        return reader

    monkeypatch.setattr(vclient, "AudioReader", make_reader)
    sink = Sink()
    vc._test.conn.connected = False
    with pytest.raises(RecordingException):
        vc.start_recording(sink)
    vc._test.conn.connected = True
    with pytest.raises(TypeError, match="Sink"):
        vc.start_recording(object())
    with pytest.warns(UserWarning, match="sync_start"):
        vc.start_recording(sink, sync_start=True)
    assert vc.is_recording()
    with pytest.raises(ClientException, match="Already recording"):
        vc.start_recording(sink)
    vc.stop_recording()
    assert not vc.is_recording()
    with pytest.raises(RecordingException, match="not recording"):
        vc.stop_recording()
    with pytest.warns(UserWarning, match="'args' parameter"):
        vc.start_recording(sink, None, 1, 2)
    assert built[-1][1]["args"] == (1, 2)
    vc._reader.listening = False
    assert not vc.is_recording()


async def test_is_speaking(vc):
    member = SimpleNamespace(id=5)
    assert vc.is_speaking(member) is None
    vc._add_ssrc(5, 50)
    assert vc.is_speaking(member) is None
    reader = Reader()
    reader.speaking_timer.get_speaking.return_value = True
    vc._reader = reader
    assert vc.is_speaking(member) is True


def test_voice_protocol_defaults_and_cleanup():
    removed = []
    channel = SimpleNamespace(_get_voice_client_key=lambda: ("k", "guild_id"))
    client = SimpleNamespace(
        _connection=SimpleNamespace(_remove_voice_client=removed.append)
    )
    proto = VoiceProtocol(client, channel)
    proto.cleanup()
    assert removed == ["k"]


async def test_voice_protocol_abstract_methods():
    proto = VoiceProtocol(SimpleNamespace(), SimpleNamespace())
    with pytest.raises(NotImplementedError):
        await proto.on_voice_state_update(None)
    with pytest.raises(NotImplementedError):
        await proto.on_voice_server_update(None)
    with pytest.raises(NotImplementedError):
        await proto.connect(reconnect=True, timeout=1)


def test_opcodes_equality_and_hash():
    assert OpCodes.ready == 2
    assert OpCodes.ready == OpCodes.ready
    assert (OpCodes.ready == "x") is False
    assert OpCodes.ready != OpCodes.hello
    assert hash(OpCodes.ready) == hash(2)
    assert int(OpCodes.hello) == 8
    assert ConnectionFlowState.connected.value == 8
