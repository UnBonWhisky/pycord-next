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

import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

import davey

import discord.voice.client as voice_client_module
from discord.sinks import WaveSink
from discord.sinks.errors import RecordingException
from discord.utils import MISSING
from discord.voice.packets import VoiceData
from discord.voice.receive.reader import AudioReader, PacketDecryptor

from .receive_helpers import RecordingSink, make_client, make_rtp, make_rtp_bytes


@pytest.fixture
def client(loop):
    return make_client(loop)


def make_reader(client, sink, **kwargs) -> AudioReader[Any]:
    reader = AudioReader(sink, client, **kwargs)
    reader.keep_alive.stop()
    return reader


class BlockingBuffer:
    def __init__(self, release: threading.Event) -> None:
        self.release = release
        self.entered = threading.Event()

    def flush(self):
        self.entered.set()
        self.release.wait(10)
        return []


class BlockingDecoder:
    ssrc = 1

    def __init__(self, release: threading.Event) -> None:
        self._buffer = BlockingBuffer(release)

    def destroy(self) -> None:
        pass


def test_sink_is_initialised_with_the_client(client):
    sink = RecordingSink()

    make_reader(client, sink)

    assert sink.client is client


def test_after_callback_is_called_without_extra_args(client):
    sink = RecordingSink()
    calls: list[tuple[Any, ...]] = []
    reader = make_reader(client, sink, on_finish=lambda *a: calls.append(a), args=())
    reader.start()

    reader.stop()

    assert calls == [(sink,)]
    assert sink.cleaned.is_set()


def test_after_callback_receives_sink_and_args(client):
    sink = RecordingSink()
    calls: list[tuple[Any, ...]] = []
    reader = make_reader(
        client, sink, on_finish=lambda *a: calls.append(a), args=("channel", 3)
    )
    reader.start()

    reader.stop()

    assert calls == [(sink, "channel", 3)]


def test_after_callback_is_called_once_when_stopped_twice(client):
    sink = RecordingSink()
    calls: list[tuple[Any, ...]] = []
    reader = make_reader(client, sink, on_finish=lambda *a: calls.append(a), args=())
    reader.start()

    reader.stop()
    reader.stop()

    assert len(calls) == 1


def test_after_callback_runs_after_cleanup(client):
    sink = RecordingSink()
    seen: list[bool] = []
    reader = make_reader(
        client, sink, on_finish=lambda s: seen.append(s.cleaned.is_set()), args=()
    )
    reader.start()

    reader.stop()

    assert seen == [True]


def test_after_callback_exception_does_not_propagate(client):
    def boom(_sink):
        raise RuntimeError("boom")

    reader = make_reader(client, RecordingSink(), on_finish=boom, args=())
    reader.start()

    reader.stop()

    assert not reader.is_listening()


def test_reader_rejects_non_callable_after(client):
    with pytest.raises(TypeError):
        AudioReader(RecordingSink(), client, on_finish=1, args=())  # type: ignore


async def test_async_after_callback_is_scheduled_on_the_loop():
    loop = asyncio.get_running_loop()
    client = make_client(loop)
    sink = RecordingSink()
    done = asyncio.Event()
    calls: list[tuple[Any, ...]] = []

    async def finished(*args):
        calls.append(args)
        done.set()

    reader = make_reader(client, sink, on_finish=finished, args=("x",))
    reader.start()

    await loop.run_in_executor(None, reader.stop)
    await asyncio.wait_for(done.wait(), 2)

    assert calls == [(sink, "x")]


def test_stop_returns_promptly_when_a_decoder_blocks(client):
    sink = RecordingSink(opus=True)
    calls: list[tuple[Any, ...]] = []
    reader = make_reader(client, sink, on_finish=lambda *a: calls.append(a), args=())
    reader.stop_timeout = 0.3
    release = threading.Event()
    decoder = BlockingDecoder(release)
    reader.packet_router.decoders[1] = decoder  # type: ignore
    reader.start()

    try:
        started = time.perf_counter()
        thread = threading.Thread(target=reader.stop)
        thread.start()
        assert decoder._buffer.entered.wait(2)
        thread.join(timeout=3)
        elapsed = time.perf_counter() - started

        assert not thread.is_alive()
        assert elapsed < 2
        assert calls == [(sink,)]
        assert sink.cleaned.is_set()
    finally:
        release.set()
        reader.packet_router.join(timeout=2)

    assert not reader.packet_router.is_alive()


def test_stop_stops_every_thread(client):
    reader = make_reader(client, RecordingSink())
    reader.start()

    reader.stop()
    reader.speaking_timer.join(timeout=2)
    reader.packet_router.join(timeout=2)

    assert not reader.speaking_timer.is_alive()
    assert not reader.packet_router.is_alive()
    assert client._connection.listeners == []


def make_voice_client(loop):
    vc = voice_client_module.VoiceClient.__new__(voice_client_module.VoiceClient)
    vc.loop = loop
    vc._reader = MISSING
    vc.is_connected = lambda: True
    vc.channel = SimpleNamespace(guild=None)
    vc._connection = make_client(loop)._connection
    vc._connection.mode = "xsalsa20_poly1305"
    vc._connection.secret_key = list(range(32))
    return vc


def test_start_recording_without_extra_args_still_calls_on_finish(loop):
    vc = make_voice_client(loop)
    sink = RecordingSink()
    calls: list[tuple[Any, ...]] = []

    vc.start_recording(sink, on_finish=lambda *a: calls.append(a))
    assert vc.is_recording()
    vc.stop_recording()

    assert not vc.is_recording()
    assert calls == [(sink,)]


def test_start_recording_passes_extra_args_to_on_finish(loop):
    vc = make_voice_client(loop)
    sink = RecordingSink()
    calls: list[tuple[Any, ...]] = []

    vc.start_recording(sink, None, "channel", 1, on_finish=lambda *a: calls.append(a))
    vc.stop_recording()

    assert calls == [(sink, "channel", 1)]


def test_callback_keeps_the_2_7_exception_contract(client):
    sink = RecordingSink()
    seen: list[Any] = []
    reader = make_reader(client, sink, after=seen.append)
    reader.start()
    error = RuntimeError("boom")
    reader.error = error

    reader.stop()

    assert seen == [error]


def test_callback_receives_none_without_error(client):
    seen: list[Any] = []
    reader = make_reader(client, RecordingSink(), after=seen.append)
    reader.start()

    reader.stop()

    assert seen == [None]


def test_callback_is_called_before_on_finish(client):
    order: list[str] = []
    reader = make_reader(
        client,
        RecordingSink(),
        after=lambda exc: order.append("callback"),
        on_finish=lambda sink: order.append("on_finish"),
        args=(),
    )
    reader.start()

    reader.stop()

    assert order == ["callback", "on_finish"]


def test_failing_callback_does_not_prevent_on_finish(client):
    def boom(exc):
        raise RuntimeError("boom")

    calls: list[Any] = []
    reader = make_reader(
        client, RecordingSink(), after=boom, on_finish=calls.append, args=()
    )
    reader.start()

    reader.stop()

    assert len(calls) == 1


def test_start_recording_callback_gets_the_exception_only(loop):
    vc = make_voice_client(loop)
    seen: list[Any] = []

    vc.start_recording(RecordingSink(), seen.append)
    vc.stop_recording()

    assert seen == [None]


def test_start_recording_args_without_on_finish_are_deprecated_and_ignored(loop):
    vc = make_voice_client(loop)
    seen: list[Any] = []

    with pytest.warns(UserWarning, match="'args' parameter is deprecated"):
        vc.start_recording(RecordingSink(), seen.append, "ignored")
    vc.stop_recording()

    assert seen == [None]


def test_start_recording_runs_callback_then_on_finish(loop):
    vc = make_voice_client(loop)
    sink = RecordingSink()
    calls: list[Any] = []

    vc.start_recording(
        sink,
        lambda exc: calls.append(("callback", exc)),
        "channel",
        on_finish=lambda s, *a: calls.append(("on_finish", s, a)),
    )
    vc.stop_recording()

    assert calls == [("callback", None), ("on_finish", sink, ("channel",))]


def test_start_recording_without_callback(loop):
    vc = make_voice_client(loop)

    vc.start_recording(RecordingSink())
    vc.stop_recording()

    assert not vc.is_recording()


def test_start_recording_does_not_warn_about_broken_reception(loop, recwarn):
    vc = make_voice_client(loop)

    vc.start_recording(RecordingSink())
    vc.stop_recording()

    assert not [w for w in recwarn if issubclass(w.category, RuntimeWarning)]


def test_stop_recording_when_not_recording_raises(loop):
    vc = make_voice_client(loop)

    with pytest.raises(RecordingException):
        vc.stop_recording()


def test_wave_sink_records_pcm_into_a_valid_wave_file(loop):
    import io
    import wave

    vc = make_voice_client(loop)
    sink = WaveSink()
    calls: list[Any] = []
    pcm = b"\x01\x00\x02\x00" * 960

    vc.start_recording(sink, on_finish=calls.append)
    sink.write(VoiceData(SimpleNamespace(), "user", pcm=pcm), "user")  # type: ignore
    vc.stop_recording()

    assert calls == [sink]
    audio = sink.audio_data["user"]
    with wave.open(io.BytesIO(audio.file.read()), "rb") as f:
        assert f.getnchannels() == 2
        assert f.getframerate() == 48000
        assert f.readframes(f.getnframes()) == pcm


def test_sink_write_accepts_raw_bytes_and_voice_data():
    from discord.sinks import Sink

    sink = Sink()

    sink.write(b"ab", "user")  # type: ignore
    sink.write(VoiceData(SimpleNamespace(), "user", pcm=b"cd"), "user")  # type: ignore

    assert sink.audio_data["user"].file.getvalue() == b"abcd"


def test_sink_recording_property(loop):
    sink = RecordingSink()

    assert sink.recording is False

    sink.vc = SimpleNamespace(is_recording=lambda: True)  # type: ignore
    assert sink.recording is True


class FakeDave:
    def __init__(self, *, ready: bool = True, error: Exception | None = None) -> None:
        self.ready = ready
        self.error = error
        self.calls: list[tuple[int, Any, bytes]] = []

    def decrypt(self, user_id: int, media_type: Any, packet: bytes) -> bytes:
        self.calls.append((user_id, media_type, packet))
        if self.error is not None:
            raise self.error
        return b"decrypted:" + packet


def make_decryptor(client) -> PacketDecryptor:
    return PacketDecryptor(client.mode, bytes(client.secret_key), client)


def test_decrypt_rtp_without_dave_passes_the_payload_through(client):
    decryptor = make_decryptor(client)
    packet = make_rtp(1, payload=b"frame")

    assert decryptor.decrypt_rtp(packet) == b"frame"
    assert packet.decrypted_data == b"frame"


def test_decrypt_rtp_with_a_session_that_is_not_ready_passes_through(client):
    client._connection.dave_session = FakeDave(ready=False)
    decryptor = make_decryptor(client)
    packet = make_rtp(1, payload=b"frame")

    assert decryptor.decrypt_rtp(packet) == b"frame"


def test_decrypt_rtp_with_dave_decrypts_for_the_mapped_user(client):
    dave = FakeDave()
    client._connection.dave_session = dave
    client._connection.ssrc_user_map[1] = 42
    decryptor = make_decryptor(client)
    packet = make_rtp(1, ssrc=1, payload=b"frame")

    assert decryptor.decrypt_rtp(packet) == b"decrypted:frame"
    assert dave.calls == [(42, davey.MediaType.audio, b"frame")]


def test_decrypt_rtp_drops_the_packet_when_dave_decryption_fails(client):
    client._connection.dave_session = FakeDave(error=ValueError("no decryptor"))
    client._connection.ssrc_user_map[1] = 42
    decryptor = make_decryptor(client)
    packet = make_rtp(1, ssrc=1, payload=b"frame")

    assert decryptor.decrypt_rtp(packet) == b""
    assert packet.decrypted_data == b""


def test_decrypt_rtp_drops_the_packet_for_an_unmapped_ssrc(client):
    dave = FakeDave()
    client._connection.dave_session = dave
    decryptor = make_decryptor(client)
    packet = make_rtp(1, ssrc=9, payload=b"frame")

    assert decryptor.decrypt_rtp(packet) == b""
    assert dave.calls == []


def test_decrypt_rtp_strips_rtp_padding(client):
    decryptor = make_decryptor(client)
    payload = b"frame" + b"\x00\x00\x00\x04"
    packet = make_rtp(1, payload=payload, padding=True)

    assert decryptor.decrypt_rtp(packet) == b"frame"


def test_decrypt_rtp_keeps_the_payload_without_the_padding_flag(client):
    decryptor = make_decryptor(client)
    payload = b"frame" + b"\x00\x00\x00\x04"

    assert decryptor.decrypt_rtp(make_rtp(1, payload=payload)) == payload


def test_decrypt_rtcp_tolerates_dave_failure(client):
    import struct

    client._connection.dave_session = FakeDave(error=ValueError("not a dave frame"))
    client._connection.ssrc_user_map[5] = 42
    decryptor = make_decryptor(client)
    header = struct.pack(">BBHI", 0x80, 201, 1, 5)
    import nacl.secret

    body = b"\x00" * 16
    nonce = bytearray(24)
    nonce[:8] = header
    encrypted = nacl.secret.SecretBox(bytes(client.secret_key)).encrypt(
        body, nonce=bytes(nonce)
    )

    assert decryptor.decrypt_rtcp(header + encrypted.ciphertext) == header + body


def feed(reader: AudioReader[Any], data: bytes) -> None:
    reader.callback(data)


def test_reader_callback_feeds_decrypted_packets_to_the_router(client):
    sink = RecordingSink(opus=True)
    reader = make_reader(client, sink)
    client._connection.ssrc_user_map[1] = 42
    fed: list[Any] = []
    reader.packet_router.feed_rtp = fed.append  # type: ignore

    feed(reader, make_rtp_bytes(1, payload=b"frame"))

    assert len(fed) == 1
    assert fed[0].decrypted_data == b"frame"
    reader.speaking_timer.stop()


def test_reader_callback_drops_packets_whose_dave_decryption_failed(client):
    sink = RecordingSink(opus=True)
    reader = make_reader(client, sink)
    client._connection.dave_session = FakeDave(error=ValueError("nope"))
    client._connection.ssrc_user_map[1] = 42
    fed: list[Any] = []
    reader.packet_router.feed_rtp = fed.append  # type: ignore

    feed(reader, make_rtp_bytes(1, payload=b"frame"))

    assert fed == []
    reader.speaking_timer.stop()
