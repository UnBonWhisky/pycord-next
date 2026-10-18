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
# ruff: noqa: S105, S106

from __future__ import annotations

import asyncio
import struct
from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest
import pytest_asyncio

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

import davey

from discord.enums import SpeakingState
from discord.errors import ConnectionClosed
from discord.voice import gateway as vg
from discord.voice.enums import OpCodes
from discord.voice.gateway import KeepAliveHandler, VoiceWebSocket


class FakeSocket:
    def __init__(self, incoming=()):
        self.sent: list[tuple[str, Any]] = []
        self.incoming = list(incoming)
        self.closed = False
        self.close_code = None

    async def send_str(self, data):
        self.sent.append(("str", data))

    async def send_bytes(self, data):
        self.sent.append(("bytes", data))

    async def receive(self):
        return self.incoming.pop(0)

    async def close(self, code=1000):
        self.close_code = code
        self.closed = True


class FakeDave:
    def __init__(self):
        self.calls = []
        self.process_proposals_result = None
        self.fail = False

    def set_passthrough_mode(self, *args):
        self.calls.append(("passthrough", args))

    def set_external_sender(self, data):
        self.calls.append(("external", data))

    def get_user_ids(self):
        return [1]

    def process_proposals(self, op, data):
        self.calls.append(("proposals", op, data))
        return self.process_proposals_result

    def process_commit(self, data):
        if self.fail:
            raise RuntimeError("bad")
        self.calls.append(("commit", data))

    def process_welcome(self, data):
        if self.fail:
            raise RuntimeError("bad")
        self.calls.append(("welcome", data))


def make_state(dave=None):
    state = SimpleNamespace(
        token="tok",  # nosec B106
        session_id="sess",
        server_id=10,
        channel_id=20,
        guild_id=10,
        user=SimpleNamespace(id=99),
        max_dave_proto_version=1,
        dave_session=dave,
        dave_protocol_version=0,
        dave_pending_transition=None,
        mode=None,
        secret_key=None,
        supported_modes=("aead_xchacha20_poly1305_rtpsize", "xsalsa20_poly1305"),
        executed=[],
        reinits=0,
        recovered=[],
        listeners=[],
        socket=object(),
    )

    async def execute(tid):
        state.executed.append(tid)

    async def reinit():
        state.reinits += 1

    async def recover(tid):
        state.recovered.append(tid)

    state.execute_dave_transition = execute
    state.reinit_dave_session = reinit
    state.recover_dave_from_invalid_commit = recover
    state.add_socket_listener = state.listeners.append
    state.remove_socket_listener = state.listeners.remove
    return state


@pytest_asyncio.fixture
async def ws():
    loop = asyncio.get_running_loop()
    return VoiceWebSocket(FakeSocket(), loop, make_state(FakeDave()))


def decode_json(ws_, idx=-1):
    import json

    return json.loads(ws_.ws.sent[idx][1])


async def test_properties_and_setters(ws):
    ws.token = "new"
    ws.session_id = "s2"
    assert (ws.state.token, ws.state.session_id) == ("new", "s2")
    assert (ws.token, ws.session_id) == ("new", "s2")
    ws._connection = SimpleNamespace(self_id=5)
    assert ws.self_id == 5
    assert await ws._default_hook(1, 2) is None


async def test_senders(ws):
    await ws.send_as_bytes(OpCodes.mls_key_package, b"xy")
    assert ws.ws.sent[-1] == ("bytes", bytes([26]) + b"xy")
    await ws.send_as_json({"op": int(OpCodes.identify), "d": {}})
    assert decode_json(ws)["op"] == 0
    await ws.send_heartbeat({"op": 3})
    await ws.speak()
    assert decode_json(ws) == {"op": 5, "d": {"speaking": 1, "delay": 0}}
    await ws.send_dave_transition_ready(7)
    assert decode_json(ws) == {"op": 23, "d": {"transition_id": 7}}
    await ws.select_protocol("1.2.3.4", 5, "m")
    assert decode_json(ws)["d"]["data"] == {
        "address": "1.2.3.4",
        "port": 5,
        "mode": "m",
    }


async def test_identify_and_resume(ws):
    ws.seq_ack = 4
    await ws.identify()
    d = decode_json(ws)
    assert d["op"] == 0
    assert d["d"] == {
        "server_id": "10",
        "user_id": "99",
        "session_id": "sess",
        "token": "tok",
        "max_dave_protocol_version": 1,
    }
    await ws.resume()
    d = decode_json(ws)
    assert d["op"] == 7
    assert d["d"]["seq_ack"] == 4
    assert d["d"]["server_id"] == "10"


async def test_keep_alive_payload_and_ack(ws):
    ws.seq_ack = 3
    handler = KeepAliveHandler(ws=ws, interval=1)
    assert handler.daemon is True
    payload = handler.get_payload()
    assert payload["op"] == 3
    assert payload["d"]["seq_ack"] == 3
    assert isinstance(payload["d"]["t"], int)
    handler.ack()
    assert len(handler.recent_ack_latencies) == 1
    assert handler.latency == handler.recent_ack_latencies[0]


async def test_latency_properties(ws):
    assert ws.latency == float("inf")
    assert ws.average_latency == float("inf")
    ws._keep_alive = KeepAliveHandler(ws=ws, interval=1)
    assert ws.average_latency == float("inf")
    ws._keep_alive.recent_ack_latencies.extend([1.0, 3.0])
    ws._keep_alive.latency = 3.0
    assert ws.average_latency == 2.0
    assert ws.latency == 3.0


async def test_hello_starts_keep_alive(ws, monkeypatch):
    started = []
    monkeypatch.setattr(KeepAliveHandler, "start", lambda self: started.append(self))  # noqa: PLW0108
    await ws.received_message({"op": 8, "d": {"heartbeat_interval": 41250}})
    assert started == [ws._keep_alive]
    assert ws._keep_alive.interval == 5


async def test_heartbeat_ack(ws, caplog):
    await ws.received_message({"op": 6, "d": {}, "seq": 12})
    assert ws.seq_ack == 12
    handler = KeepAliveHandler(ws=ws, interval=1)
    ws._keep_alive = handler
    await ws.received_message({"op": 6, "d": {}})
    assert len(handler.recent_ack_latencies) == 1


async def test_hook_receives_messages():
    seen = []

    async def hook(w, msg):
        seen.append(msg)

    w = VoiceWebSocket(
        FakeSocket(), asyncio.get_running_loop(), make_state(), hook=hook
    )
    await w.received_message({"op": 9, "d": {}})
    await w.received_message({"op": 200, "d": {}})
    assert [m["op"] for m in seen] == [9, 200]


async def test_session_description(ws):
    await ws.received_message(
        {
            "op": 4,
            "d": {"mode": "m", "dave_protocol_version": 1, "secret_key": [1, 2]},
        }
    )
    assert ws.state.mode == "m"
    assert ws.state.dave_protocol_version == 1
    assert ws.secret_key == ws.state.secret_key == [1, 2]
    assert ws.state.reinits == 1
    assert decode_json(ws)["d"]["speaking"] == int(SpeakingState.none)


async def test_dave_prepare_transition_zero(ws):
    data = {"transition_id": 0, "protocol_version": 1}
    await ws.received_message({"op": 21, "d": data})
    assert ws.state.dave_pending_transition == data
    assert ws.state.executed == [0]


async def test_dave_prepare_transition_downgrade(ws):
    data = {"transition_id": 3, "protocol_version": 0}
    await ws.received_message({"op": 21, "d": data})
    assert ("passthrough", (True, 10)) in ws.state.dave_session.calls
    assert decode_json(ws) == {"op": 23, "d": {"transition_id": 3}}
    assert ws.state.executed == []


async def test_dave_execute_and_epoch(ws):
    await ws.received_message({"op": 22, "d": {"transition_id": 5}})
    assert ws.state.executed == [5]
    await ws.received_message({"op": 24, "d": {"epoch": 2, "protocol_version": 1}})
    assert ws.state.reinits == 0
    await ws.received_message({"op": 24, "d": {"epoch": 1, "protocol_version": 1}})
    assert ws.state.reinits == 1
    assert ws.state.dave_protocol_version == 1


async def test_unhandled_op_without_dave():
    w = VoiceWebSocket(FakeSocket(), asyncio.get_running_loop(), make_state())
    await w.received_message({"op": 21, "d": {}})
    assert w.state.executed == []


async def test_resumed_logs(ws):
    await ws.received_message({"op": 9, "d": {}})


def binary(seq, op, payload=b""):
    return struct.pack(">HB", seq, op) + payload


async def test_binary_ignored_without_dave():
    w = VoiceWebSocket(FakeSocket(), asyncio.get_running_loop(), make_state())
    await w.received_binary_message(binary(5, 25, b"x"))
    assert w.seq_ack == 5


async def test_binary_external_sender(ws):
    await ws.received_binary_message(binary(1, 25, b"pkg"))
    assert ("external", b"pkg") in ws.state.dave_session.calls


async def test_binary_proposals(ws):
    session = ws.state.dave_session
    await ws.received_binary_message(binary(1, 27, b"\x00abc"))
    await ws.received_binary_message(binary(2, 27, b"\x01abc"))
    ops = [c[1] for c in session.calls if c[0] == "proposals"]
    assert ops == [
        davey.ProposalsOperationType.append,
        davey.ProposalsOperationType.revoke,
    ]
    assert ws.ws.sent == []


@pytest.mark.parametrize("welcome", [b"", b"W"])
async def test_binary_proposals_commit_welcome(ws, monkeypatch, welcome):
    class CW:
        commit = b"C"

    CW.welcome = welcome
    monkeypatch.setattr(vg.davey, "CommitWelcome", CW)
    ws.state.dave_session.process_proposals_result = CW()
    await ws.received_binary_message(binary(1, 27, b"\x00abc"))
    assert ws.ws.sent[-1] == ("bytes", bytes([28]) + b"C" + welcome)


async def test_binary_commit_transition(ws):
    await ws.received_binary_message(binary(1, 29, struct.pack(">H", 4) + b"cm"))
    assert ("commit", b"cm") in ws.state.dave_session.calls
    assert ws.state.dave_pending_transition["transition_id"] == 4
    assert decode_json(ws)["d"]["transition_id"] == 4
    ws.ws.sent.clear()
    await ws.received_binary_message(binary(1, 29, struct.pack(">H", 0) + b"cm"))
    assert ws.ws.sent == []


async def test_binary_welcome(ws):
    await ws.received_binary_message(binary(1, 30, struct.pack(">H", 6) + b"w"))
    assert ("welcome", b"w") in ws.state.dave_session.calls
    assert decode_json(ws)["d"]["transition_id"] == 6
    ws.ws.sent.clear()
    await ws.received_binary_message(binary(1, 30, struct.pack(">H", 0) + b"w"))
    assert ws.ws.sent == []


@pytest.mark.parametrize("op", [29, 30])
async def test_binary_failures_recover(ws, op):
    ws.state.dave_session.fail = True
    await ws.received_binary_message(binary(1, op, struct.pack(">H", 8) + b"x"))
    assert ws.state.recovered == [8]


async def test_get_ip_and_ready(ws):
    loop = asyncio.get_running_loop()
    sent = []

    async def sock_connect(sock, addr):
        sent.append(("connect", addr))

    async def sock_sendall(sock, data):
        sent.append(("send", bytes(data)))
        reply = bytearray(74)
        reply[1] = 2
        reply[8 : 8 + 9] = b"127.0.0.1"
        struct.pack_into(">H", reply, 72, 5555)
        ws.state.listeners[0](bytes(reply))

    loop.sock_connect = sock_connect
    loop.sock_sendall = sock_sendall
    ws.state.ssrc = 77
    ip, port = await ws.get_ip()
    assert (ip, port) == ("127.0.0.1", 5555)
    packet = sent[-1][1]
    assert struct.unpack_from(">HHI", packet) == (1, 70, 77)
    await asyncio.sleep(0)
    assert ws.state.listeners == []

    await ws.ready(
        {
            "ssrc": 3,
            "port": 4000,
            "ip": "9.9.9.9",
            "modes": ["unsupported", "xsalsa20_poly1305"],
        }
    )
    assert ("connect", ("9.9.9.9", 4000)) in sent
    d = decode_json(ws)
    assert d["op"] == 1
    assert d["d"]["data"]["mode"] == "xsalsa20_poly1305"
    assert d["d"]["data"]["address"] == "127.0.0.1"
    await ws.received_message(
        {
            "op": 2,
            "d": {"ssrc": 3, "port": 1, "ip": "i", "modes": ["xsalsa20_poly1305"]},
        }
    )


async def test_get_ip_ignores_other_packets(ws):
    loop = asyncio.get_running_loop()

    async def sock_sendall(sock, data):
        listener = ws.state.listeners[0]
        listener(bytes([0, 1]) + bytes(72))
        reply = bytearray(74)
        reply[1] = 2
        reply[8:11] = b"1.1"
        listener(bytes(reply))

    loop.sock_sendall = sock_sendall
    ws.state.ssrc = 1
    assert (await ws.get_ip())[0] == "1.1"


def msg(type_, data=None):
    return SimpleNamespace(type=type_, data=data)


async def test_poll_event_text_and_binary(ws):
    ws.ws.incoming = [
        msg(aiohttp.WSMsgType.TEXT, '{"op": 9, "d": {}, "seq": 3}'),
        msg(aiohttp.WSMsgType.BINARY, binary(8, 99)),
    ]
    await ws.poll_event()
    assert ws.seq_ack == 3
    await ws.poll_event()
    assert ws.seq_ack == 8


async def test_poll_event_error_and_close(ws):
    err = RuntimeError("x")
    ws.ws.incoming = [msg(aiohttp.WSMsgType.ERROR, err)]
    with pytest.raises(ConnectionClosed) as info:
        await ws.poll_event()
    assert info.value.__cause__ is err
    ws._close_code = 4006
    for t in (
        aiohttp.WSMsgType.CLOSED,
        aiohttp.WSMsgType.CLOSE,
        aiohttp.WSMsgType.CLOSING,
    ):
        ws.ws.incoming = [msg(t)]
        with pytest.raises(ConnectionClosed):
            await ws.poll_event()
    ws.ws.incoming = [msg(aiohttp.WSMsgType.PING)]
    await ws.poll_event()


async def test_poll_event_timeout(ws, monkeypatch):
    async def never():
        await asyncio.sleep(10)

    ws.ws.receive = never
    real = asyncio.wait_for
    monkeypatch.setattr(vg.asyncio, "wait_for", lambda c, timeout: real(c, 0.01))
    with pytest.raises(asyncio.TimeoutError):
        await ws.poll_event()


async def test_close_stops_keep_alive(ws):
    handler = KeepAliveHandler(ws=ws, interval=1)
    ws._keep_alive = handler
    await ws.close(4014)
    assert handler._stop_ev.is_set()
    assert ws.ws.close_code == 4014
    assert ws._close_code == 4014
    ws2 = VoiceWebSocket(FakeSocket(), asyncio.get_running_loop(), make_state())
    await ws2.close()
    assert ws2.ws.close_code == 1000


@pytest.mark.parametrize("resume", [False, True])
async def test_from_state(resume):
    sock = FakeSocket()
    urls = []

    async def ws_connect(url, **kwargs):
        urls.append((url, kwargs))
        return sock

    loop = asyncio.get_running_loop()
    state = make_state()
    state.endpoint = "voice.example"
    state.client = SimpleNamespace(
        loop=loop, _state=SimpleNamespace(http=SimpleNamespace(ws_connect=ws_connect))
    )
    w = await VoiceWebSocket.from_state(state, resume=resume, seq_ack=9)
    assert urls == [("wss://voice.example/?v=8", {"compress": 15})]
    assert w.gateway == "wss://voice.example/?v=8"
    assert w.seq_ack == 9
    assert decode_json(w)["op"] == (7 if resume else 0)
