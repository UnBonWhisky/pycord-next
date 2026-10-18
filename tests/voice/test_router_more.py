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
# ruff: noqa: RUF012

from __future__ import annotations

import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.sinks.errors import RecordingException
from discord.voice.receive.router import PacketRouter, SinkEventRouter

from .receive_helpers import RecordingSink, make_client, make_rtp


@pytest.fixture
def setup(loop):
    client = make_client(loop)
    sink = RecordingSink(opus=True)
    sink.vc = client
    reader = SimpleNamespace(
        client=client,
        error=None,
        event_router=MagicMock(),
    )
    client._reader = reader
    router = PacketRouter(sink, reader)
    reader.packet_router = router
    return router, sink, reader, client


def test_feed_rtp_opus_sink_buffers_until_ready(setup):
    router, sink, _reader, _client = setup
    for seq in (1, 2, 3):
        router.feed_rtp(make_rtp(seq))
    assert router.get_decoder(1) is router.decoders[1]
    assert router.waiter.is_ready()
    assert sink.writes == []


def test_feed_rtp_pcm_sink_decodes_and_writes(setup, monkeypatch):
    router, sink, _reader, _client = setup
    sink.opus = False
    fake_decoder = MagicMock()
    data = SimpleNamespace(source="who")
    fake_decoder.process_packet.return_value = data
    monkeypatch.setattr(
        "discord.voice.receive.router.PacketDecoder", lambda r, ssrc: fake_decoder
    )
    packet = make_rtp(1)
    router.feed_rtp(packet)
    assert sink.writes == [(data, "who")]


def test_feed_rtp_dropped_ssrc_ignored_and_restored_by_set_user_id(setup):
    router, _sink, _reader, _client = setup
    router.feed_rtp(make_rtp(1))
    router.destroy_decoder(1)
    assert 1 not in router.decoders
    router.feed_rtp(make_rtp(2))
    assert 1 not in router.decoders
    router.set_user_id(1, 42)
    router.feed_rtp(make_rtp(3))
    assert 1 in router.decoders
    router.set_user_id(1, 43)
    assert router.decoders[1]._cached_id == 43
    router.set_user_id(99, 1)
    router.destroy_decoder(99)


def test_destroy_all_decoders(setup):
    router, *_ = setup
    router.feed_rtp(make_rtp(1, ssrc=1))
    router.feed_rtp(make_rtp(1, ssrc=2))
    router.destroy_all_decoders()
    assert router.decoders == {}


def test_feed_rtcp_dispatches_with_guild(setup):
    router, sink, reader, client = setup
    client.guild = "guild"
    router.feed_rtcp("packet")
    reader.event_router.dispatch.assert_called_once_with(
        "rtcp_packet", "packet", "guild"
    )
    sink.vc = None
    router.feed_rtcp("p2")
    reader.event_router.dispatch.assert_called_with("rtcp_packet", "p2", None)


def test_set_sink(setup):
    router, *_ = setup
    new = RecordingSink()
    router.set_sink(new)
    assert router.sink is new


def test_do_run_writes_ready_data_and_drains_on_stop(setup):
    router, sink, _reader, _client = setup
    for seq in range(1, 5):
        router.feed_rtp(make_rtp(seq))
    router._poll_interval = 0.01
    router.start()
    deadline = time.monotonic() + 2
    while not sink.writes and time.monotonic() < deadline:
        time.sleep(0.005)
    router.stop()
    router.join(2)
    assert sink.writes
    assert not router.is_alive()
    assert len(sink.writes) == 4
    assert router.waiter.items == []


def test_run_failure_sets_reader_error_and_stops_recording(setup):
    router, _sink, reader, client = setup
    stopped = []
    client.stop_recording = lambda: stopped.append(1)
    router._do_run = MagicMock(side_effect=RuntimeError("loop"))
    router.run()
    assert isinstance(reader.error, RuntimeError)
    assert stopped == [1]


def test_run_ignores_not_recording(setup):
    router, _sink, _reader, client = setup

    def not_recording():
        raise RecordingException("You are not recording")

    client.stop_recording = not_recording
    router._do_run = MagicMock()
    router.run()


def test_drain_logs_decoder_errors(setup, caplog):
    router, _sink, _reader, _client = setup
    bad = MagicMock()
    bad.ssrc = 9
    bad._buffer.flush.side_effect = RuntimeError("x")
    router.decoders[9] = bad
    router._drain_all_decoders()
    assert "Error draining decoder" in caplog.text


# -- SinkEventRouter -------------------------------------------------------------


class ListeningSink(RecordingSink):
    __sink_listeners__ = [("on_ping", "on_ping"), ("on_boom", "on_boom")]

    def __init__(self):
        super().__init__()
        self.pings = []

    def on_ping(self, *args, **kwargs):
        self.pings.append((args, kwargs))

    def on_boom(self):
        raise RuntimeError("listener")


def make_event_router():
    sink = ListeningSink()
    reader = SimpleNamespace(
        error=None,
        client=SimpleNamespace(stop_recording=MagicMock()),
        packet_router=SimpleNamespace(_lock=threading.RLock()),
    )
    return SinkEventRouter(sink, reader), sink, reader


def test_event_router_registers_children_and_sink_switch():
    router, sink, _reader = make_event_router()
    assert set(router._event_listeners) == {"on_ping", "on_boom"}
    child = ListeningSink()
    sink.walk_children = lambda: iter([child])
    router.register_events()
    assert len(router._event_listeners["on_ping"]) == 3
    router.unregister_events()
    new = ListeningSink()
    router.set_sink(new)
    assert router.sink is new
    router._dispatch_to_listeners("ping", 1, k=2)
    assert new.pings == [((1,), {"k": 2})]
    assert sink.pings == []
    router._event_listeners.clear()
    router._unregister_listeners(new)


def test_event_router_thread_dispatches_and_logs_errors(caplog):
    router, sink, _reader = make_event_router()
    router.start()
    router.dispatch("ping", 5)
    router.dispatch("boom")
    router.dispatch("unknown")
    deadline = time.monotonic() + 3
    while not sink.pings and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)
    router.stop()
    router.join(3)
    assert sink.pings == [((5,), {})]
    assert "Unhandled exception while dispatching event boom" in caplog.text


def test_event_router_run_failure_stops_recording():
    router, _sink, reader = make_event_router()
    router._buffer = MagicMock()
    router._buffer.get.side_effect = ValueError("x")
    router.run()
    assert isinstance(reader.error, ValueError)
    reader.client.stop_recording.assert_called_once()


def test_event_router_do_run_survives_empty_queue():
    router, _sink, _reader = make_event_router()
    calls = []

    class Q:
        def get(self, timeout):
            calls.append(timeout)
            router._end_thread.set()
            raise queue.Empty

    router._buffer = Q()
    router._do_run()
    assert calls == [0.5]
