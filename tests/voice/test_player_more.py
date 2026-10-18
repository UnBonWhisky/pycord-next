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
# ruff: noqa: PT030, RUF043

from __future__ import annotations

import asyncio
import io
import json
import struct
import subprocess
import threading
from types import SimpleNamespace

import pytest

from discord import player as pl
from discord.enums import SpeakingState
from discord.errors import ClientException
from discord.opus import OPUS_SILENCE
from discord.player import (
    AudioPlayer,
    AudioSource,
    FFmpegAudio,
    FFmpegOpusAudio,
    FFmpegPCMAudio,
    PCMAudio,
    PCMVolumeTransformer,
)

FRAME = pl.OpusEncoder.FRAME_SIZE


class FakeProc:
    def __init__(self, stdout=b"", *, stdin=None, stderr=None, alive=False):
        self.pid = 42
        self.stdout = io.BytesIO(stdout)
        self.stdin = stdin
        self.stderr = stderr
        self.alive = alive
        self.killed = False
        self.terminated = False
        self.communicated = False
        self.returncode = 0
        self.kill_error = False

    def kill(self):
        if self.kill_error:
            raise OSError("no")
        self.killed = True

    def terminate(self):
        self.terminated = True

    def poll(self):
        return None if self.alive else 0

    def communicate(self, *a, **k):
        self.communicated = True
        return b"", None


@pytest.fixture
def popen(monkeypatch):
    made = []

    def factory(args, **kwargs):
        proc = FakeProc()
        proc.args, proc.kwargs = args, kwargs
        made.append(proc)
        return proc

    monkeypatch.setattr(pl.subprocess, "Popen", factory)
    return made


class Silent(AudioSource):
    def read(self):
        return b""


def test_audio_source_defaults():
    src = AudioSource()
    with pytest.raises(NotImplementedError):
        src.read()
    assert src.is_opus() is False
    assert src.cleanup() is None


def test_pcm_audio_reads_whole_frames_only():
    audio = PCMAudio(io.BytesIO(b"\x01" * (FRAME + 10)))
    assert audio.read() == b"\x01" * FRAME
    assert audio.read() == b""


def test_ffmpeg_audio_spawn_errors(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(pl.subprocess, "Popen", missing)
    with pytest.raises(ClientException, match="myffmpeg was not found"):
        FFmpegPCMAudio("x", executable="myffmpeg")

    def broken(*a, **k):
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(pl.subprocess, "Popen", broken)
    with pytest.raises(ClientException, match="Popen failed: SubprocessError: boom"):
        FFmpegPCMAudio("x")
    monkeypatch.setattr(pl.subprocess, "Popen", missing)
    with pytest.raises(ClientException, match="^ffmpeg was not found"):
        object.__new__(FFmpegAudio)._spawn_process("ffmpeg -x")


def test_pcm_audio_args_and_read(popen):
    src = FFmpegPCMAudio(
        "song.mp3", before_options="-re", options="-af volume=2", executable="ff"
    )
    proc = popen[0]
    assert proc.args[0] == "ff"
    assert proc.args[1:4] == ["-re", "-i", "song.mp3"]
    assert proc.args[-3:-1] == ["-af", "volume=2"]
    assert proc.args[-1] == "pipe:1"
    assert proc.kwargs["stdin"] == subprocess.DEVNULL
    assert src.is_opus() is False
    proc.stdout = src._stdout = io.BytesIO(b"\x02" * FRAME + b"short")
    assert src.read() == b"\x02" * FRAME
    assert src.read() == b""


def test_piped_stdin_and_stderr_threads(popen, monkeypatch):
    stdin = io.BytesIO()
    stderr_dest = io.BytesIO()

    def factory(args, **kwargs):
        proc = FakeProc(stdin=stdin, stderr=io.BytesIO(b"warn"))
        proc.args = args
        popen.append(proc)
        return proc

    monkeypatch.setattr(pl.subprocess, "Popen", factory)
    src = FFmpegPCMAudio(io.BytesIO(b"data"), pipe=True, stderr=_NoFileno(stderr_dest))
    src._pipe_writer_thread.join(1)
    src._pipe_reader_thread.join(1)
    assert stderr_dest.getvalue() == b"warn"
    assert popen[0].args[1:3] == ["-i", "-"]


class _NoFileno:
    def __init__(self, inner):
        self.inner = inner

    def fileno(self):
        raise io.UnsupportedOperation

    def write(self, data):
        return self.inner.write(data)


def test_ffmpeg_audio_argument_validation(popen):
    with pytest.raises(TypeError, match="parameter conflict"):
        FFmpegAudio("path", args=[], stdin=subprocess.PIPE)
    with pytest.warns(DeprecationWarning):
        FFmpegAudio("path", args=[], stderr=subprocess.PIPE)
    assert popen[-1].kwargs["stderr"] is None


def test_cleanup_kills_process(popen):
    src = FFmpegPCMAudio("x")
    proc = popen[0]
    proc.alive = True
    src.cleanup()
    assert proc.killed
    assert proc.communicated
    assert src._process is pl.MISSING
    src._kill_process()
    object.__new__(FFmpegAudio)._kill_process()


def test_kill_process_error_and_dead(popen):
    src = FFmpegPCMAudio("x")
    proc = popen[0]
    proc.kill_error = True
    src._kill_process()
    assert not proc.communicated


def test_pipe_writer_branches(popen):
    src = FFmpegPCMAudio("x")

    class Stdin:
        def __init__(self, fail=False):
            self.fail = fail
            self.closed = False
            self.data = b""

        def write(self, d):
            if self.fail:
                raise BrokenPipeError
            self.data += d

        def close(self):
            self.closed = True

    src._stdin = Stdin()
    src._pipe_writer(io.BytesIO(b"abc"))
    assert src._stdin.data == b"abc"
    assert src._stdin.closed
    src._stdin = Stdin(fail=True)
    src._pipe_writer(io.BytesIO(b"abc"))
    assert src._process.terminated
    src._stdin = None
    src._pipe_writer(io.BytesIO(b"abc"))


def test_pipe_reader_branches(popen):
    src = FFmpegPCMAudio("x")
    dest = io.BytesIO()
    src._stderr = None
    src._pipe_reader(dest)

    class Err:
        def __init__(self, items):
            self.items = list(items)
            self.closed = False

        def read(self, n):
            item = self.items.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        def close(self):
            self.closed = True

    src._stderr = Err([OSError()])
    src._pipe_reader(dest)
    src._stderr = Err([None])
    src._pipe_reader(dest)
    src._stderr = Err([b""])
    src._pipe_reader(dest)
    src._stderr = Err([b"a", None])
    src._pipe_reader(dest)
    assert dest.getvalue() == b"a"

    class BadDest:
        def write(self, d):
            raise ValueError

    src._stderr = Err([b"a"])
    src._pipe_reader(BadDest())
    assert src._stderr.closed


def ogg_page(payload: bytes) -> bytes:
    header = struct.pack("<BBQIIIB", 0, 0, 0, 1, 0, 0, 1)
    return b"OggS" + header + bytes([len(payload)]) + payload


def test_opus_audio_args_and_read(monkeypatch):
    made = []

    def factory(args, **kwargs):
        proc = FakeProc(ogg_page(b"pkt1") + ogg_page(b"pkt2"))
        proc.args = args
        made.append(proc)
        return proc

    monkeypatch.setattr(pl.subprocess, "Popen", factory)
    src = FFmpegOpusAudio("x.ogg", bitrate=96, codec="opus", options="-vn")
    args = made[0].args
    assert args[args.index("-c:a") + 1] == "copy"
    assert args[args.index("-b:a") + 1] == "96k"
    assert "-vn" in args
    assert src.is_opus() is True
    assert src.read() == b"pkt1"
    assert src.read() == b"pkt2"
    assert src.read() == b""
    FFmpegOpusAudio("x", before_options="-re", codec="mp3")
    args = made[1].args
    assert args[args.index("-c:a") + 1] == "libopus"
    assert args[args.index("-b:a") + 1] == "128k"
    assert args[0] == "ffmpeg"
    assert "-re" in args


async def test_from_probe(monkeypatch, popen):
    async def fake_probe(source, *, method, executable, protocol_whitelist):
        return "opus", 64

    monkeypatch.setattr(FFmpegOpusAudio, "probe", fake_probe)
    src = await FFmpegOpusAudio.from_probe("x.ogg")
    assert isinstance(src, FFmpegOpusAudio)
    args = popen[0].args
    assert args[args.index("-c:a") + 1] == "copy"
    assert args[args.index("-b:a") + 1] == "64k"


async def test_probe_method_selection(monkeypatch):
    with pytest.raises(AttributeError, match="Invalid probe method"):
        await FFmpegOpusAudio.probe("x", method="nope")
    with pytest.raises(TypeError, match="Expected str or callable"):
        await FFmpegOpusAudio.probe("x", method=5)

    assert await FFmpegOpusAudio.probe("x", method=lambda s, e: ("c", 7)) == ("c", 7)
    seen = []

    def custom(source, exe):
        seen.append((source, exe))
        return ("a", 1)

    assert await FFmpegOpusAudio.probe("s", method=custom, executable="e") == ("a", 1)
    assert seen == [("s", "e")]


async def test_probe_fallbacks(monkeypatch):
    calls = []

    def native(source, exe, *, protocol_whitelist=None):
        calls.append("native")
        raise RuntimeError("bad")

    def fallback(source, exe, *, protocol_whitelist=None):
        calls.append("fallback")
        return ("opus", 600)

    monkeypatch.setattr(FFmpegOpusAudio, "_probe_codec_native", staticmethod(native))
    monkeypatch.setattr(
        FFmpegOpusAudio, "_probe_codec_fallback", staticmethod(fallback)
    )
    assert await FFmpegOpusAudio.probe("x") == ("opus", 600)
    assert calls == ["native", "fallback"]

    def bad_fallback(source, exe, *, protocol_whitelist=None):
        raise RuntimeError("worse")

    monkeypatch.setattr(
        FFmpegOpusAudio, "_probe_codec_fallback", staticmethod(bad_fallback)
    )
    assert await FFmpegOpusAudio.probe("x") == (None, None)
    assert await FFmpegOpusAudio.probe("x", method="fallback") == (None, None)

    def interrupted(source, exe, *, protocol_whitelist=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        FFmpegOpusAudio, "_probe_codec_native", staticmethod(interrupted)
    )
    with pytest.raises(KeyboardInterrupt):
        await FFmpegOpusAudio.probe("x")


def test_probe_native_parsing(monkeypatch):
    seen = []

    def check_output(args, timeout):
        seen.append(args)
        return json.dumps(
            {"streams": [{"codec_name": "opus", "bit_rate": "64000"}]}
        ).encode()

    monkeypatch.setattr(pl.subprocess, "check_output", check_output)
    codec, bitrate = FFmpegOpusAudio._probe_codec_native("x")
    assert (codec, bitrate) == ("opus", 512)
    assert seen[0][0] == "ffprobe"
    FFmpegOpusAudio._probe_codec_native("x", "custom")
    assert seen[1][0] == "custom"
    monkeypatch.setattr(pl.subprocess, "check_output", lambda a, timeout: b"")
    assert FFmpegOpusAudio._probe_codec_native("x") == (None, None)


def test_probe_fallback_parsing(monkeypatch):
    class P:
        def __init__(self, out):
            self.out = out

        def communicate(self, timeout):
            return self.out, None

    text = b"Stream #0:0: Audio: opus, 48000 Hz\n  bitrate: 128 kb/s"
    monkeypatch.setattr(pl.subprocess, "Popen", lambda *a, **k: P(text))
    assert FFmpegOpusAudio._probe_codec_fallback("x") == ("opus", 512)
    monkeypatch.setattr(pl.subprocess, "Popen", lambda *a, **k: P(b"nothing"))
    assert FFmpegOpusAudio._probe_codec_fallback("x") == (None, None)


def test_volume_transformer():
    with pytest.raises(TypeError):
        PCMVolumeTransformer(object())
    opus = FFmpegOpusAudio.__new__(FFmpegOpusAudio)
    with pytest.raises(ClientException):
        PCMVolumeTransformer(opus)

    class Src(AudioSource):
        cleaned = False

        def read(self):
            return struct.pack("<4h", 1000, -1000, 30000, -30000)

        def cleanup(self):
            Src.cleaned = True

    t = PCMVolumeTransformer(Src(), volume=0.5)
    assert struct.unpack("<4h", t.read()) == (500, -500, 15000, -15000)
    t.volume = 5
    assert t.volume == 5
    assert struct.unpack("<4h", t.read()) == (2000, -2000, 32767, -32768)
    t.volume = -1
    assert t.volume == 0.0
    t.cleanup()
    assert Src.cleaned


# -- AudioPlayer -------------------------------------------------------------


class FakeVC:
    def __init__(self, connected=True):
        self.connected = connected
        self.timeout = 0.01
        self.packets = []
        self.spoken = []
        self.reconnect_result = True
        self.client = SimpleNamespace(loop=None)
        self.ws = SimpleNamespace(speak=self.spoken.append)

    def is_connected(self):
        return self.connected

    def wait_until_connected(self, timeout):
        self.connected = self.reconnect_result
        return self.reconnect_result

    def send_audio_packet(self, data, *, encode):
        self.packets.append((data, encode))


class ListSource(AudioSource):
    def __init__(self, frames, opus=False):
        self.frames = list(frames)
        self.opus = opus
        self.cleaned = False

    def read(self):
        return self.frames.pop(0) if self.frames else b""

    def is_opus(self):
        return self.opus

    def cleanup(self):
        self.cleaned = True


@pytest.fixture
def fast_player(monkeypatch):
    monkeypatch.setattr(AudioPlayer, "DELAY", 0.0)
    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        pl.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: coro.close() if hasattr(coro, "close") else None,
    )


def test_player_plays_until_exhausted(fast_player):
    vc = FakeVC()
    after = []
    src = ListSource([b"a", b"b"], opus=True)
    player = AudioPlayer(src, vc, after=after.append)
    player.run()
    data = [p for p in vc.packets if p[0] != OPUS_SILENCE]
    assert data == [(b"a", False), (b"b", False)]
    assert vc.packets[-5:] == [(OPUS_SILENCE, False)] * 5
    assert after == [None]
    assert src.cleaned
    assert player.played_frames() == 2
    assert not player.is_playing()


def test_player_encodes_pcm(fast_player):
    vc = FakeVC()
    player = AudioPlayer(ListSource([b"a"]), vc)
    player.run()
    assert vc.packets[0] == (b"a", True)


def test_player_requires_callable_after():
    with pytest.raises(TypeError):
        AudioPlayer(ListSource([]), FakeVC(), after=3)


def test_player_records_error_and_calls_after(fast_player):
    class Boom(ListSource):
        def read(self):
            raise ValueError("boom")

    errors = []
    player = AudioPlayer(Boom([]), FakeVC(), after=errors.append)
    player.run()
    assert isinstance(errors[0], ValueError)


def test_player_after_failure_is_logged(fast_player, caplog):
    def after(err):
        raise RuntimeError("after")

    AudioPlayer(ListSource([]), FakeVC(), after=after).run()
    assert "Calling the after function failed" in caplog.text


def test_player_error_without_after_is_logged(fast_player, caplog):
    class Boom(ListSource):
        def read(self):
            raise ValueError("boom")

    AudioPlayer(Boom([]), FakeVC()).run()
    assert "Exception in voice thread" in caplog.text


def test_player_aborts_when_not_reconnected(fast_player):
    vc = FakeVC(connected=False)
    vc.reconnect_result = False
    src = ListSource([b"a"])
    AudioPlayer(src, vc).run()
    assert vc.packets == []


def test_player_resumes_after_reconnect(fast_player):
    vc = FakeVC(connected=False)
    player = AudioPlayer(ListSource([b"a"]), vc)
    player.run()
    assert vc.packets[0] == (b"a", True)


def test_player_pause_resume_set_source(fast_player):
    vc = FakeVC()
    player = AudioPlayer(ListSource([]), vc)
    assert player.is_playing()
    assert not player.is_paused()
    player.pause()
    assert player.is_paused()
    assert not player.is_playing()
    player.loops = 3
    player.resume()
    assert player.played_frames() == 3
    new = ListSource([])
    player.loops = 0
    player.set_source(new)
    assert player.source is new
    player.stop()
    assert not player.is_paused()
    assert not player.is_playing()


def test_player_paused_loop_sends_silence(fast_player):
    vc = FakeVC()
    player = AudioPlayer(ListSource([b"a"]), vc)
    player._resumed.clear()
    original_wait = player._resumed.wait

    def wait():
        player._resumed.set()
        return original_wait()

    player._resumed.wait = wait
    player.run()
    assert vc.packets[0] == (OPUS_SILENCE, False)


def test_speak_failure_is_logged(monkeypatch, caplog):
    vc = FakeVC()

    def boom(coro, loop):
        coro.close()
        raise RuntimeError("no loop")

    monkeypatch.setattr(pl.asyncio, "run_coroutine_threadsafe", boom)
    vc.ws = SimpleNamespace(speak=lambda s: _noop())
    AudioPlayer(ListSource([]), vc)._speak(SpeakingState.voice)
    assert "Speaking call in player failed" in caplog.text


async def _noop():
    return None


def test_send_silence_swallows_errors():
    vc = FakeVC()

    def fail(*a, **k):
        raise RuntimeError

    vc.send_audio_packet = fail
    AudioPlayer(ListSource([]), vc).send_silence()


def test_player_thread_runs(fast_player):
    vc = FakeVC()
    done = threading.Event()
    player = AudioPlayer(ListSource([b"a"]), vc, after=lambda e: done.set())
    player.start()
    assert done.wait(2)
    player.join(2)
    assert asyncio.iscoroutinefunction(_noop)
