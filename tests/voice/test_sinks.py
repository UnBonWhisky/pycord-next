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

import io
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from discord.sinks import core as sink_core, errors as sink_errors
from discord.sinks.core import AudioData, Filters, Sink
from discord.sinks.m4a import M4ASink
from discord.sinks.mka import MKASink
from discord.sinks.mkv import MKVSink
from discord.sinks.mp3 import MP3Sink
from discord.sinks.mp4 import MP4Sink
from discord.sinks.ogg import OGGSink

PIPE_SINKS = [
    (MP3Sink, sink_errors.MP3SinkError, "mp3"),
    (OGGSink, sink_errors.OGGSinkError, "ogg"),
    (MKASink, sink_errors.MKASinkError, "mka"),
    (MKVSink, sink_errors.MKVSinkError, "mkv"),
]
FILE_SINKS = [
    (M4ASink, sink_errors.M4ASinkError, "m4a"),
    (MP4Sink, sink_errors.MP4SinkError, "mp4"),
]


class FakeProcess:
    def __init__(self, args, output=b"encoded"):
        self.args = args
        self.output = output
        self.received = None

    def communicate(self, data):
        self.received = data
        if self.args[-1] != "pipe:1":
            Path(self.args[-1]).write_bytes(self.output)
        return (self.output, None)


def patch_popen(monkeypatch, *, raises=None):
    created = []

    def popen(args, **kwargs):
        if raises is not None:
            raise raises
        proc = FakeProcess(args)
        created.append((proc, kwargs))
        return proc

    monkeypatch.setattr(subprocess, "Popen", popen)
    return created


def finished_audio(payload=b"pcm"):
    audio = AudioData(io.BytesIO(payload))
    audio.cleanup()
    return audio


@pytest.mark.parametrize(("cls", "error", "encoding"), PIPE_SINKS + FILE_SINKS)
class TestFfmpegSinks:
    def test_recording_blocks_formatting(self, cls, error, encoding):
        sink = cls()
        sink.vc = SimpleNamespace(is_recording=lambda: True)
        with pytest.raises(error, match="after recording is finished"):
            sink.format_audio(finished_audio())

    def test_ffmpeg_missing(self, cls, error, encoding, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        patch_popen(monkeypatch, raises=FileNotFoundError())
        with pytest.raises(error, match="ffmpeg was not found"):
            cls().format_audio(finished_audio())

    def test_popen_failure(self, cls, error, encoding, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        patch_popen(monkeypatch, raises=subprocess.SubprocessError("boom"))
        with pytest.raises(error, match="Popen failed: SubprocessError: boom"):
            cls().format_audio(finished_audio())

    def test_format_replaces_file(self, cls, error, encoding, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        created = patch_popen(monkeypatch)
        sink = cls()
        audio = finished_audio(b"raw-pcm")
        sink.format_audio(audio)
        proc, _ = created[0]
        assert proc.received == b"raw-pcm"
        assert proc.args[0] == "ffmpeg"
        assert audio.file.read() == b"encoded"
        assert sink.encoding == encoding
        assert list(tmp_path.iterdir()) == []


def test_file_sinks_remove_stale_temp_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("discord.sinks.m4a.time.time", lambda: 1.5)
    stale = tmp_path / "1.5.tmp"
    stale.write_bytes(b"stale")
    patch_popen(monkeypatch)
    audio = finished_audio()
    M4ASink().format_audio(audio)
    assert audio.file.read() == b"encoded"


def test_filters_container_and_init(monkeypatch):
    class Dummy(Filters):
        @Filters.container
        def write(self, data, user):
            return (data, user)

    f = Dummy(users=["a"])
    assert f.write(b"x", "a") == (b"x", "a")
    assert f.write(b"x", "b") is None
    assert Dummy().write(b"x", "z") == (b"x", "z")


def test_filters_wait_and_stop(monkeypatch):
    monkeypatch.setattr(sink_core.time, "sleep", lambda _s: None)
    stopped = []
    f = Filters(time=1)
    f.vc = SimpleNamespace(stop_recording=lambda: stopped.append(1))
    f.wait_and_stop()
    assert stopped == [1]
    f.finished = True
    f.wait_and_stop()
    assert stopped == [1]
    f.finished = False
    f.vc = None
    f.wait_and_stop()


def test_filters_init_starts_thread(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(sink_core.threading, "Thread", FakeThread)
    f = Filters(time=2)
    f.init()
    assert started == [f.wait_and_stop]
    started.clear()
    Filters().init()
    assert started == []


def test_audio_data_lifecycle():
    audio = AudioData(io.BytesIO())
    with pytest.raises(sink_errors.SinkException):
        audio.on_format("wav")
    audio.write(b"abc")
    audio.cleanup()
    assert audio.file.read() == b"abc"
    with pytest.raises(sink_errors.SinkException):
        audio.write(b"x")
    with pytest.raises(sink_errors.SinkException):
        audio.cleanup()
    audio.on_format("wav")


def test_audio_data_write_ignores_closed_file():
    f = io.BytesIO()
    audio = AudioData(f)
    f.close()
    audio.write(b"abc")


def test_sink_write_and_accessors():
    sink = Sink()
    assert sink.client is None
    assert sink.recording is False
    assert sink.is_opus() is False
    assert list(sink.walk_children()) == []
    sink.write(b"ab", "u1")
    sink.write(SimpleNamespace(pcm=b"cd"), "u1")
    sink.write(bytearray(b"ef"), "u2")
    files = sink.get_all_audio()
    assert len(files) == 2
    assert files[0].getvalue() == b"abcd"
    assert files[1].getvalue() == b"ef"


def test_sink_init_recording_and_format():
    sink = Sink()
    vc = SimpleNamespace(is_recording=lambda: True)
    sink.init(vc)
    assert sink.client is vc
    assert sink.recording is True
    with pytest.raises(NotImplementedError):
        sink.format_audio(finished_audio())
    sink.write(b"a", "u")
    with pytest.raises(NotImplementedError):
        sink.cleanup()
    assert sink.finished is True


def test_sink_get_user_audio_pops(monkeypatch):
    sink = Sink()
    monkeypatch.setattr(sink_core.os.path, "realpath", lambda p: ("real", p))
    sink.audio_data["u"] = "data"
    assert sink.get_user_audio("u") == ("real", "data")
    assert "u" not in sink.audio_data


def test_raw_data_parses_rtp_header():
    packet = bytes([0x80, 0x78]) + (7).to_bytes(2, "big") + (960).to_bytes(4, "big")
    packet += (1234).to_bytes(4, "big") + b"payload"
    client = SimpleNamespace(
        mode="xsalsa20_poly1305",
        _decrypt_xsalsa20_poly1305=lambda header, data: (bytes(header), bytes(data)),
    )
    raw = sink_core.RawData(packet, client)
    assert (raw.sequence, raw.timestamp, raw.ssrc) == (7, 960, 1234)
    assert raw.decrypted_data == (packet[:12], b"payload")
    assert raw.decoded_data is None
    assert raw.user_id is None


def test_raw_data_rtpsize_extension_and_csrc():
    head = bytes([0x80 | 0x10 | 0x02, 0x78]) + (1).to_bytes(2, "big")
    head += (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
    packet = head + b"\x00" * 8 + b"\x00" * 4 + b"body"
    client = SimpleNamespace(
        mode="aead_xchacha20_poly1305_rtpsize",
        _decrypt_aead_xchacha20_poly1305_rtpsize=lambda h, d: (len(h), bytes(d)),
    )
    raw = sink_core.RawData(packet, client)
    assert raw.decrypted_data == (12 + 8 + 4, b"body")
