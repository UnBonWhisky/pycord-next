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

import subprocess
from typing import Any

import pytest

import discord
from discord import player as player_module
from discord.player import (
    RECOMMENDED_PROTOCOL_WHITELIST,
    FFmpegOpusAudio,
    FFmpegPCMAudio,
)


class _FakeProcess:
    pid = 1
    stdout = None
    stdin = None
    stderr = None
    returncode = 0

    def kill(self) -> None:
        pass

    def poll(self) -> int:
        return 0

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        return b"", None


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def spawn(self: Any, args: Any, **kwargs: Any) -> _FakeProcess:
        calls.append(list(args))
        return _FakeProcess()

    monkeypatch.setattr(player_module.FFmpegAudio, "_spawn_process", spawn)
    monkeypatch.setattr(player_module, "OggStream", lambda stdout: _FakeOgg())
    return calls


class _FakeOgg:
    def iter_packets(self) -> Any:
        return iter(())


CLASSES = [FFmpegPCMAudio, FFmpegOpusAudio]


@pytest.mark.parametrize("cls", CLASSES)
def test_default_is_unchanged(cls: Any, spawned: list[list[str]]) -> None:
    cls("song.mp3")
    args = spawned[0]
    assert "-protocol_whitelist" not in args
    assert args[1:3] == ["-i", "song.mp3"]


@pytest.mark.parametrize("cls", CLASSES)
def test_whitelist_is_passed_before_input(cls: Any, spawned: list[list[str]]) -> None:
    cls("song.mp3", protocol_whitelist=["file", "https"])
    args = spawned[0]
    index = args.index("-protocol_whitelist")
    assert args[index + 1] == "file,https"
    assert index < args.index("-i")


@pytest.mark.parametrize("cls", CLASSES)
def test_recommended_value(cls: Any, spawned: list[list[str]]) -> None:
    cls("song.mp3", protocol_whitelist=RECOMMENDED_PROTOCOL_WHITELIST)
    args = spawned[0]
    value = args[args.index("-protocol_whitelist") + 1].split(",")
    assert value == [
        "file",
        "http",
        "https",
        "tcp",
        "tls",
        "crypto",
        "pipe",
        "fd",
        "cache",
    ]
    assert not {"concat", "subfile", "data", "gopher"} & set(value)


@pytest.mark.parametrize("cls", CLASSES)
def test_before_options_whitelist_wins_with_warning(
    cls: Any, spawned: list[list[str]]
) -> None:
    with pytest.warns(UserWarning, match="protocol_whitelist"):
        cls(
            "song.mp3",
            before_options="-protocol_whitelist file",
            protocol_whitelist=["https"],
        )
    args = spawned[0]
    assert args.count("-protocol_whitelist") == 1
    assert args[args.index("-protocol_whitelist") + 1] == "file"


@pytest.mark.parametrize("cls", CLASSES)
def test_str_whitelist_is_rejected(cls: Any, spawned: list[list[str]]) -> None:
    with pytest.raises(TypeError):
        cls("song.mp3", protocol_whitelist="file,http")


@pytest.mark.parametrize("cls", CLASSES)
def test_whitelist_is_keyword_only(cls: Any, spawned: list[list[str]]) -> None:
    with pytest.raises(TypeError):
        cls("song.mp3", "ffmpeg", False, None, None, None, ["file"])


def test_probe_native_uses_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def check_output(args: list[str], timeout: int) -> bytes:
        seen.append(args)
        return b""

    monkeypatch.setattr(subprocess, "check_output", check_output)
    FFmpegOpusAudio._probe_codec_native("song.mp3")
    FFmpegOpusAudio._probe_codec_native("song.mp3", protocol_whitelist=["file"])
    assert "-protocol_whitelist" not in seen[0]
    assert seen[1][seen[1].index("-protocol_whitelist") + 1] == "file"
    assert seen[1][-1] == "song.mp3"


def test_probe_fallback_uses_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def popen(args: list[str], **kwargs: Any) -> _FakeProcess:
        seen.append(args)
        return _FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", popen)
    FFmpegOpusAudio._probe_codec_fallback("song.mp3", protocol_whitelist=["file"])
    args = seen[0]
    assert args.index("-protocol_whitelist") < args.index("-i")


@pytest.mark.asyncio
async def test_from_probe_forwards_whitelist(
    monkeypatch: pytest.MonkeyPatch, spawned: list[list[str]]
) -> None:
    probed: dict[str, Any] = {}

    def native(source: str, executable: str = "ffmpeg", *, protocol_whitelist=None):
        probed["whitelist"] = protocol_whitelist
        return "opus", 128

    monkeypatch.setattr(FFmpegOpusAudio, "_probe_codec_native", staticmethod(native))
    await FFmpegOpusAudio.from_probe("song.mp3", protocol_whitelist=["file"])
    assert probed["whitelist"] == ["file"]
    assert "-protocol_whitelist" in spawned[0]


@pytest.mark.asyncio
async def test_custom_probe_signature_is_unchanged(
    spawned: list[list[str]],
) -> None:
    def custom(source: str, executable: str) -> tuple[str, int]:
        return "opus", 96

    await FFmpegOpusAudio.from_probe(
        "song.mp3", method=custom, protocol_whitelist=["file"]
    )
    assert discord.FFmpegOpusAudio is FFmpegOpusAudio
