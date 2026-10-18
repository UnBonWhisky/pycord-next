# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import importlib
import json
import zlib
from typing import Any

import pytest

from discord.gateway import (
    Inflater,
    ZlibStreamInflater,
    ZstdStreamInflater,
    create_inflater,
)

MESSAGES = [
    json.dumps({"op": 0, "t": "X", "d": {"n": n, "pad": "a" * 300}}) for n in range(4)
]


def zlib_frames() -> list[bytes]:
    deflater = zlib.compressobj()
    return [
        deflater.compress(m.encode()) + deflater.flush(zlib.Z_SYNC_FLUSH)
        for m in MESSAGES
    ]


def test_zlib_stream_inflates_a_shared_context() -> None:
    inflater = ZlibStreamInflater()
    assert [inflater.feed(frame) for frame in zlib_frames()] == MESSAGES


def test_zlib_stream_buffers_until_the_flush_suffix() -> None:
    inflater = ZlibStreamInflater()
    frame = zlib_frames()[0]
    middle = len(frame) // 2

    assert inflater.feed(frame[:middle]) is None
    assert inflater.feed(frame[middle:]) == MESSAGES[0]


def test_zlib_stream_keeps_its_context_after_a_split_message() -> None:
    inflater = ZlibStreamInflater()
    first, second = zlib_frames()[:2]
    assert inflater.feed(first[:5]) is None
    assert inflater.feed(first[5:]) == MESSAGES[0]
    assert inflater.feed(second) == MESSAGES[1]


def test_short_frames_are_buffered() -> None:
    assert ZlibStreamInflater().feed(b"\x00") is None


def test_each_connection_has_its_own_context() -> None:
    frames = zlib_frames()
    first, second = ZlibStreamInflater(), ZlibStreamInflater()
    assert first.feed(frames[0]) == MESSAGES[0]
    with pytest.raises(zlib.error):
        second.feed(frames[1])


def test_zstd_stream_inflates_a_shared_context() -> None:
    zstandard = pytest.importorskip("zstandard")
    compressor = zstandard.ZstdCompressor().compressobj()
    inflater = ZstdStreamInflater()
    for message in MESSAGES:
        frame = compressor.compress(message.encode()) + compressor.flush(
            zstandard.COMPRESSOBJ_FLUSH_BLOCK
        )
        assert inflater.feed(frame) == message


def test_zstd_stream_without_the_package(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.import_module

    def import_module(name: str, *args: Any) -> Any:
        if name == "zstandard":
            raise ImportError(name)
        return real(name, *args)

    monkeypatch.setattr(importlib, "import_module", import_module)
    with pytest.raises(ImportError, match=r"py-cord\[zstd\]"):
        ZstdStreamInflater()


def test_create_inflater() -> None:
    assert create_inflater(None) is None
    inflater = create_inflater("zlib-stream")
    assert isinstance(inflater, Inflater)
    assert inflater.name == "zlib-stream"
    with pytest.raises(ValueError, match="gateway_compression"):
        create_inflater("gzip")  # type: ignore[arg-type]
