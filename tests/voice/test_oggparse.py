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
import struct

import pytest

from discord.oggparse import OggError, OggPage, OggStream


def page_bytes(segments, *, flag=0, gran=0, serial=1, pagenum=0):
    table = bytes(segments)
    body = b"".join(bytes([i % 256]) * s for i, s in enumerate(segments))
    header = struct.pack("<BBQIIIB", 0, flag, gran, serial, pagenum, 0, len(table))
    return b"OggS" + header + table + body


def test_page_parsing_and_packets():
    stream = io.BytesIO(page_bytes([3, 2], flag=2, gran=99, serial=5, pagenum=4)[4:])
    page = OggPage(stream)
    assert (page.flag, page.gran_pos, page.serial, page.pagenum) == (2, 99, 5, 4)
    assert page.segnum == 2
    assert list(page.iter_packets()) == [(b"\x00\x00\x00", True), (b"\x01\x01", True)]


def test_page_bad_stream():
    with pytest.raises(OggError, match="bad data stream"):
        OggPage(io.BytesIO(b"\x00\x01"))


def test_page_partial_packet_flagged():
    page = OggPage(io.BytesIO(page_bytes([255, 255])[4:]))
    assert list(page.iter_packets()) == [(b"\x00" * 255 + b"\x01" * 255, False)]


def test_stream_reassembles_across_pages():
    data = page_bytes([255]) + page_bytes([10, 4])
    packets = list(OggStream(io.BytesIO(data)).iter_packets())
    assert packets == [b"\x00" * 255 + b"\x00" * 10, b"\x01" * 4]


def test_stream_empty_and_invalid():
    assert list(OggStream(io.BytesIO(b"")).iter_packets()) == []
    with pytest.raises(OggError, match="invalid header magic"):
        list(OggStream(io.BytesIO(b"nope")).iter_packets())
