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

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.sinks import Sink
from discord.voice.receive import router as router_module
from discord.voice.receive.reader import SpeakingTimer

from .receive_helpers import RecordingSink


class DummySink(Sink):
    def __init__(self, *, opus=False):
        super().__init__()
        self.opus = opus
        self.writes = []
        self.vc = SimpleNamespace(guild=None)

    def is_opus(self):
        return self.opus

    def write(self, data, user):
        self.writes.append((data, user))


class DummyBuffer:
    def __init__(self, packets=()):
        self.packets = list(packets)

    def flush(self):
        packets, self.packets = self.packets, []
        return packets


class DummyDecoder:
    def __init__(self, router, ssrc):
        self.router = router
        self.ssrc = ssrc
        self.pushed = []
        self.processed = []
        self._buffer = DummyBuffer()

    def push_packet(self, packet):
        self.pushed.append(packet)

    def process_packet(self, packet):
        self.processed.append(packet)
        return SimpleNamespace(source="user", packet=packet)

    def set_user_id(self, user_id):
        self.user_id = user_id

    def destroy(self):
        self.destroyed = True


class DummyPacket:
    def __init__(self, ssrc=1):
        self.ssrc = ssrc


def test_sink_is_opus_defaults_to_false():
    assert Sink().is_opus() is False


def test_packet_router_writes_pcm_packets_inline(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = DummySink(opus=False)
    packet_router = router_module.PacketRouter(sink, SimpleNamespace())
    packet = DummyPacket()

    packet_router.feed_rtp(packet)

    decoder = packet_router.decoders[packet.ssrc]
    assert decoder.processed == [packet]
    assert decoder.pushed == []
    assert len(sink.writes) == 1
    data, user = sink.writes[0]
    assert data.packet is packet
    assert user == "user"


def test_packet_router_buffers_opus_packets(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = DummySink(opus=True)
    packet_router = router_module.PacketRouter(sink, SimpleNamespace())
    packet = DummyPacket()

    packet_router.feed_rtp(packet)

    decoder = packet_router.decoders[packet.ssrc]
    assert decoder.pushed == [packet]
    assert decoder.processed == []
    assert sink.writes == []


def test_packet_router_ignores_dropped_ssrc(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = DummySink(opus=False)
    packet_router = router_module.PacketRouter(sink, SimpleNamespace())
    packet_router._dropped_ssrcs.append(7)

    packet_router.feed_rtp(DummyPacket(ssrc=7))

    assert packet_router.decoders == {}
    assert sink.writes == []


def test_packet_router_destroy_all_decoders(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    packet_router = router_module.PacketRouter(DummySink(opus=True), SimpleNamespace())
    for ssrc in (1, 2, 3):
        packet_router.get_decoder(ssrc)

    packet_router.destroy_all_decoders()

    assert packet_router.decoders == {}


def test_drain_all_decoders_flushes_buffered_packets_to_sink(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = DummySink(opus=True)
    packet_router = router_module.PacketRouter(sink, SimpleNamespace())
    first, second = DummyPacket(1), DummyPacket(2)
    packet_router.get_decoder(1)._buffer = DummyBuffer([first])
    packet_router.get_decoder(2)._buffer = DummyBuffer([second])

    packet_router._drain_all_decoders()

    assert [data.packet for data, _ in sink.writes] == [first, second]


def test_drain_all_decoders_survives_a_failing_decoder(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = DummySink(opus=True)
    packet_router = router_module.PacketRouter(sink, SimpleNamespace())
    packet = DummyPacket(2)

    class Broken(DummyBuffer):
        def flush(self):
            raise RuntimeError("boom")

    packet_router.get_decoder(1)._buffer = Broken()
    packet_router.get_decoder(2)._buffer = DummyBuffer([packet])

    packet_router._drain_all_decoders()

    assert [data.packet for data, _ in sink.writes] == [packet]


def test_packet_router_thread_drains_and_stops_promptly(monkeypatch):
    monkeypatch.setattr(router_module, "PacketDecoder", DummyDecoder)
    sink = RecordingSink(opus=True)
    reader = SimpleNamespace(client=SimpleNamespace(_reader=None))
    packet_router = router_module.PacketRouter(sink, reader)
    packet = DummyPacket()
    packet_router.get_decoder(1)._buffer = DummyBuffer([packet])
    packet_router.start()

    started = time.perf_counter()
    packet_router.stop()
    packet_router.join(timeout=2)

    assert not packet_router.is_alive()
    assert time.perf_counter() - started < 1
    assert [data.packet for data, _ in sink.writes] == [packet]


class DummyClient:
    member = SimpleNamespace(id=42)

    def __init__(self):
        self._connection = SimpleNamespace(ssrc_user_map={1: 42})
        self.dispatched = []

    def _peek_member(self, member_id):
        if member_id == self.member.id:
            return self.member
        return None

    def _dispatch_sink(self, event, member):
        self.dispatched.append((event, member))


def test_speaking_timer_handles_notify_before_thread_waits():
    client = DummyClient()
    timer = SpeakingTimer(SimpleNamespace(client=client))
    timer.speaking_timeout_delay = 0.01

    timer.notify(1)
    timer.start()

    deadline = time.perf_counter() + 1
    while time.perf_counter() < deadline:
        if ("member_speaking_stop", client.member) in client.dispatched:
            break
        time.sleep(0.01)

    timer.stop()
    timer.join(timeout=1)

    assert ("member_speaking_start", client.member) in client.dispatched
    assert ("member_speaking_stop", client.member) in client.dispatched


def test_speaking_timer_stops_even_when_idle():
    client = DummyClient()
    timer = SpeakingTimer(SimpleNamespace(client=client))
    timer.start()
    time.sleep(0.05)

    timer.stop()
    timer.join(timeout=1)

    assert not timer.is_alive()


def test_speaking_timer_stop_before_start_does_not_hang():
    client = DummyClient()
    timer = SpeakingTimer(SimpleNamespace(client=client))

    timer.stop()
    timer.start()
    timer.join(timeout=1)

    assert not timer.is_alive()
