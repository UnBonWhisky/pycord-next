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

"""Transport compression of the gateway: zlib-stream and zstd-stream."""

from __future__ import annotations

import abc
import importlib
import zlib
from typing import Any, ClassVar, Literal, cast

__all__ = (
    "GatewayCompression",
    "Inflater",
    "ZlibStreamInflater",
    "ZstdStreamInflater",
    "create_inflater",
)

GatewayCompression = Literal["zlib-stream", "zstd-stream"]

ZLIB_SUFFIX = b"\x00\x00\xff\xff"


class Inflater(abc.ABC):
    """Decompresses the websocket frames of one gateway connection."""

    name: ClassVar[GatewayCompression]

    @abc.abstractmethod
    def feed(self, data: bytes) -> str | None:
        """Feed one frame, returning the decoded payload once a message is complete."""


class ZlibStreamInflater(Inflater):
    """Inflater for ``zlib-stream``, sharing one zlib context for the connection."""

    name: ClassVar[GatewayCompression] = "zlib-stream"

    def __init__(self) -> None:
        self._inflater = zlib.decompressobj()
        self._buffer = bytearray()

    def feed(self, data: bytes) -> str | None:
        """Buffer the frame until the ``Z_SYNC_FLUSH`` suffix, then inflate it."""
        self._buffer.extend(data)
        if len(data) < 4 or data[-4:] != ZLIB_SUFFIX:
            return None
        payload = self._inflater.decompress(self._buffer).decode("utf-8")
        self._buffer.clear()
        return payload


class ZstdStreamInflater(Inflater):
    """Inflater for ``zstd-stream``, needing the optional ``zstandard`` package."""

    name: ClassVar[GatewayCompression] = "zstd-stream"

    def __init__(self) -> None:
        try:
            zstandard = importlib.import_module("zstandard")
        except ImportError as exc:
            msg = (
                "gateway_compression='zstd-stream' requires the 'zstandard' package,"
                " install it with: pip install py-cord[zstd]"
            )
            raise ImportError(msg) from exc
        self._inflater: Any = zstandard.ZstdDecompressor().decompressobj()

    def feed(self, data: bytes) -> str | None:
        """Decompress the frame, each frame holds exactly one payload."""
        return bytes(self._inflater.decompress(data)).decode("utf-8")


def create_inflater(name: GatewayCompression | None) -> Inflater | None:
    """Create the inflater of a transport compression, ``None`` for no compression."""
    value = cast("str | None", name)
    if value is None:
        return None
    if value == "zlib-stream":
        return ZlibStreamInflater()
    if value == "zstd-stream":
        return ZstdStreamInflater()
    msg = f"gateway_compression must be 'zlib-stream', 'zstd-stream' or None, not {value!r}"
    raise ValueError(msg)
