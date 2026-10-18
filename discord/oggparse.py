"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
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

import struct
from typing import IO, TYPE_CHECKING, ClassVar

from .errors import DiscordException

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = (
    "OggError",
    "OggPage",
    "OggStream",
)


class OggError(DiscordException):
    """An exception that is thrown for Ogg stream parsing errors."""


# https://tools.ietf.org/html/rfc3533
# https://tools.ietf.org/html/rfc7845


class OggPage:
    """A single page of an Ogg bitstream.

    Parameters
    ----------
    stream: IO[:class:`bytes`]
        The stream to read the page from, positioned right after the
        ``OggS`` capture pattern.

    Raises
    ------
    OggError
        The page could not be parsed from the stream.
    """

    _header: ClassVar[struct.Struct] = struct.Struct("<xBQIIIB")
    if TYPE_CHECKING:
        flag: int
        gran_pos: int
        serial: int
        pagenum: int
        crc: int
        segnum: int

    def __init__(self, stream: IO[bytes]) -> None:
        try:
            header = stream.read(struct.calcsize(self._header.format))

            (
                self.flag,
                self.gran_pos,
                self.serial,
                self.pagenum,
                self.crc,
                self.segnum,
            ) = self._header.unpack(header)

            self.segtable: bytes = stream.read(self.segnum)
            bodylen = sum(struct.unpack("B" * self.segnum, self.segtable))
            self.data: bytes = stream.read(bodylen)
        except Exception:
            raise OggError("bad data stream") from None

    def iter_packets(self) -> Generator[tuple[bytes, bool]]:
        """Iterate over the packet segments contained in this page.

        Yields
        ------
        tuple[:class:`bytes`, :class:`bool`]
            The packet data and whether it is complete (``False`` when it
            continues on the next page).
        """
        packetlen = offset = 0
        partial = True

        for seg in self.segtable:
            if seg == 255:
                packetlen += 255
                partial = True
            else:
                packetlen += seg
                yield self.data[offset : offset + packetlen], True
                offset += packetlen
                packetlen = 0
                partial = False

        if partial:
            yield self.data[offset:], False


class OggStream:
    """A stream of Ogg pages that can be iterated as whole packets.

    Parameters
    ----------
    stream: IO[:class:`bytes`]
        The binary stream containing the Ogg data.
    """

    def __init__(self, stream: IO[bytes]) -> None:
        self.stream: IO[bytes] = stream

    def _next_page(self) -> OggPage | None:
        head = self.stream.read(4)
        if head == b"OggS":
            return OggPage(self.stream)
        if not head:
            return None
        raise OggError("invalid header magic")

    def _iter_pages(self) -> Generator[OggPage]:
        page = self._next_page()
        while page:
            yield page
            page = self._next_page()

    def iter_packets(self) -> Generator[bytes]:
        """Iterate over every complete packet in the stream.

        Yields
        ------
        :class:`bytes`
            The data of one packet, reassembled across pages if needed.

        Raises
        ------
        OggError
            The stream contains invalid data.
        """
        partial = b""
        for page in self._iter_pages():
            for data, complete in page.iter_packets():
                partial += data
                if complete:
                    yield partial
                    partial = b""
