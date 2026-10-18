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

import struct

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.voice.packets import ReceiverReportPacket, RTCPPacket, SenderReportPacket
from discord.voice.packets.rtp import decode

from .receive_helpers import make_rtp, make_rtp_bytes


def test_strip_padding_removes_the_padding_declared_by_the_last_byte():
    packet = make_rtp(1, padding=True)

    assert packet.padding is True
    assert packet.strip_padding(b"frame\x00\x00\x03") == b"frame"


def test_strip_padding_is_a_noop_without_the_padding_flag():
    packet = make_rtp(1)

    assert packet.strip_padding(b"frame\x00\x00\x03") == b"frame\x00\x00\x03"


@pytest.mark.parametrize("payload", [b"", b"frame\x00", b"abc\xff"])
def test_strip_padding_ignores_invalid_padding_lengths(payload):
    packet = make_rtp(1, padding=True)

    assert packet.strip_padding(payload) == payload


def test_rtp_header_includes_the_csrc_list():
    csrc_header = struct.pack(">BBHII", 0x82, 120, 7, 960, 3) + struct.pack(
        ">II", 10, 11
    )
    packet = decode(csrc_header + b"payload")

    assert packet.csrcs == (10, 11)  # type: ignore
    assert packet.header == csrc_header  # type: ignore
    assert packet.data == b"payload"


def test_rtp_packets_parse_the_fixed_header():
    packet = decode(make_rtp_bytes(9, ssrc=77, timestamp=1234))

    assert (packet.sequence, packet.timestamp, packet.ssrc) == (9, 1234, 77)
    assert len(packet.header) == 12


def test_sender_report_reports_are_named_tuples():
    header = struct.pack(">BBHI", 0x81, 200, 12, 5)
    info = struct.pack(">5I", 10, 1 << 31, 20, 30, 40)
    report = struct.pack(">IB3B4I", 6, 1, 0, 0, 2, 3, 4, 5, 6)
    packet = decode(header + info + report)

    assert isinstance(packet, SenderReportPacket)
    assert packet.info.rtp_ts == 20
    assert packet.info.ntp_ts == 10.5
    assert packet.reports[0].ssrc == 6
    assert packet.reports[0].perc_loss == 1


def test_receiver_report_reports_are_named_tuples():
    header = struct.pack(">BBHI", 0x81, 201, 7, 5)
    report = struct.pack(">IB3B4I", 6, 2, 0, 0, 9, 3, 4, 5, 6)
    packet = decode(header + report)

    assert isinstance(packet, ReceiverReportPacket)
    assert packet.reports[0].ssrc == 6
    assert packet.reports[0].total_loss == 9
    assert isinstance(packet, RTCPPacket)
