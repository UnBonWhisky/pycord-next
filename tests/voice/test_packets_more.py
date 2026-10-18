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
# ruff: noqa: B015

from __future__ import annotations

import struct

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.sinks import PCMSink
from discord.sinks.core import AudioData
from discord.voice.packets import (
    FakePacket,
    Packet,
    ReceiverReportPacket,
    RTCPPacket,
    RTPPacket,
    SenderReportPacket,
    SilencePacket,
    VoiceData,
)
from discord.voice.packets.core import OPUS_SILENCE
from discord.voice.packets.rtp import decode
from discord.voice.utils.buffer import JitterBuffer
from discord.voice.utils.multidataevent import MultiDataEvent


def rtp(first=0x80, seq=1, ts=960, ssrc=7, body=b"body"):
    return struct.pack(">BBHII", first, 120, seq, ts, ssrc) + body


def test_base_packet_behaviour():
    p = Packet(b"abc")
    assert repr(p) == "<Packet data=3 bytes>"
    assert bool(p)
    assert not bool(Packet(b""))
    assert hash(p) == hash(b"abc")
    assert p.is_silence() is False
    p.decrypted_data = OPUS_SILENCE
    assert p.is_silence() is True


def test_packet_comparisons():
    a, b = FakePacket(1, 1, 10), FakePacket(1, 2, 20)
    assert a < b
    assert b > a
    assert not a > b
    assert a == FakePacket(1, 1, 10)
    assert a != b
    assert (a == 3) is False
    with pytest.raises(TypeError):
        a < FakePacket(2, 1, 1)
    with pytest.raises(TypeError):
        a > FakePacket(2, 1, 1)
    with pytest.raises(TypeError):
        a == FakePacket(2, 1, 1)
    with pytest.raises(TypeError):
        a < 3
    with pytest.raises(TypeError):
        a > 3


def test_fake_and_silence_packets():
    fake = FakePacket(1, 2, 3)
    assert not fake
    assert fake.data == b""
    assert fake.decrypted_data == b""
    silence = SilencePacket(4, 5)
    assert silence.is_silence()
    assert silence.sequence == -1
    assert silence.decrypted_data == OPUS_SILENCE


def test_voice_data():
    p = RTPPacket(rtp())
    p.decrypted_data = b"opus"
    vd = VoiceData(p, None)
    assert vd.opus == b"opus"
    assert vd.pcm == b""
    assert VoiceData(p, None, pcm=b"pcm").pcm == b"pcm"


def test_decode_dispatch():
    assert isinstance(decode(rtp()), RTPPacket)
    with pytest.raises(ValueError, match="Invalid packet header"):
        decode(b"\x00\x78")
    sr = struct.pack(">BBHI5I", 0x80, 200, 6, 5, 1, 2, 3, 4, 5)
    assert isinstance(decode(sr), SenderReportPacket)
    assert isinstance(RTCPPacket.from_data(sr), SenderReportPacket)


def test_rtp_basic_fields_and_repr():
    p = RTPPacket(
        rtp(first=0xA0 | 0x10 | 0x02, seq=9, ts=5, ssrc=3, body=b"\0" * 8 + b"xyz")
    )
    assert (p.version, p.padding, p.extended, p.cc) == (2, True, True, 2)
    assert (p.sequence, p.timestamp, p.ssrc) == (9, 5, 3)
    assert p.csrcs == (0, 0)
    assert p.header == p.header[:20]
    assert len(p.header) == 20
    assert p.data == b"xyz"
    assert "ssrc=3 sequence=9" in repr(p)


def test_rtp_adjust_rtpsize_without_extension():
    p = RTPPacket(rtp(body=b"payloadNONC"))
    p.adjust_rtpsize()
    assert p.nonce == b"NONC"
    assert p.data == b"payload"
    assert p.update_extended_header(b"anything") == 0


def test_rtp_adjust_rtpsize_with_extension_and_bede():
    ext_words = 1
    ext = b"\xbe\xde" + struct.pack(">H", ext_words) + b"\x00" + b"\x11ab"
    body = ext[:4] + b"payload"
    p = RTPPacket(rtp(first=0x90, body=body + b"NONC"))
    p.adjust_rtpsize()
    assert p.header[-4:] == ext[:4]
    assert p.data == b"payload"
    decrypted = ext[4:] + b"audio"
    offset = p.update_extended_header(decrypted)
    assert decrypted[offset:] == b"audio"
    assert p.extension.profile == b"\xbe\xde"
    assert p.extension.length == 1
    assert p.extension_data == {1: b"ab"}


def test_rtp_update_extended_header_non_rtpsize():
    values = struct.pack(">2I", 1, 2)
    data = b"\x10\x00" + struct.pack(">H", 2) + values + b"audio"
    p = RTPPacket(rtp(first=0x90))
    offset = p.update_extended_header(data)
    assert data[offset:] == b"audio"
    assert p.extension.values == (1, 2)
    assert p.update_extended_header(b"ab") == 0


def test_rtp_extension_truncated():
    p = RTPPacket(rtp(first=0x90))
    data = b"\x10\x00" + struct.pack(">H", 5) + b"ab"
    offset = p.update_extended_header(data)
    assert offset == len(data)
    assert p.extension is None


def test_rtp_bede_skips_and_stops():
    p = RTPPacket(rtp(first=0x90))
    data = b"\xbe\xde" + struct.pack(">H", 2) + b"\x00\x00\x10a\x21bc"
    p.update_extended_header(data)
    assert p.extension_data == {1: b"a", 2: b"bc"}
    q = RTPPacket(rtp(first=0x90))
    q.update_extended_header(b"\xbe\xde" + struct.pack(">H", 3) + b"\x10a")
    assert q.extension_data == {1: b"a"}


def test_strip_padding():
    p = RTPPacket(rtp(first=0xA0))
    assert p.strip_padding(b"abcd\x02") == b"abc"
    assert p.strip_padding(b"abc\x09") == b"abc\x09"
    assert p.strip_padding(b"") == b""
    assert p.strip_padding(b"ab\x00") == b"ab\x00"
    assert RTPPacket(rtp()).strip_padding(b"abc\x01") == b"abc\x01"


def sender_report(count=1, extra=b""):
    head = struct.pack(">BBH", 0x80 | count, 200, 6 + 6 * count)
    body = struct.pack(">I", 11) + struct.pack(">5I", 2, 1 << 31, 100, 3, 4)
    report = struct.pack(">IB3B4I", 22, 5, 0, 0, 7, 8, 9, 10, 11)[:24]
    return head + body + report * count + extra


def test_sender_report_parsing():
    data = sender_report(extra=b"ext")
    p = SenderReportPacket(data)
    assert p.ssrc == 11
    assert p.report_count == 1
    assert p.type == 200
    assert p.info.ntp_ts == 2.5
    assert p.info.rtp_ts == 100
    assert (p.info.packet_count, p.info.octet_count) == (3, 4)
    assert len(p.reports) == 1
    assert p.reports[0].ssrc == 22
    assert p.extension == b"ext"
    assert "SenderReportPacket" in repr(p)
    assert SenderReportPacket(sender_report(0)).extension is None


def test_receiver_report_parsing():
    report = struct.pack(">IB3x4I", 22, 5, 7, 8, 9, 10)
    head = struct.pack(">BBHI", 0x81, 201, 7, 5)
    p = ReceiverReportPacket(head + report + b"x")
    assert p.ssrc == 5
    assert p.report_count == 1
    assert p.reports[0].ssrc == 22
    assert p.reports[0].perc_loss == 5
    assert p.extension == b"x"
    q = ReceiverReportPacket(struct.pack(">BBHI", 0x80, 201, 1, 5))
    assert q.reports == ()
    assert q.extension is None
    assert isinstance(decode(head + report), ReceiverReportPacket)


# -- jitter buffer / utils ---------------------------------------------------


def seq_packet(seq):
    return FakePacket(1, seq, seq * 960)


def test_buffer_peek_gap_and_next():
    buf = JitterBuffer(max_size=5, pref_size=0, prefill=0)
    assert buf.peek() is None
    assert buf.peek_next() is None
    assert buf.gap() == 0
    assert len(buf) == 0
    buf.push(seq_packet(1))
    assert buf.peek(all=True).sequence == 1
    assert buf.peek().sequence == 1
    assert buf.peek_next().sequence == 1
    assert buf.pop(timeout=None).sequence == 1
    buf.push(seq_packet(4))
    assert buf.peek_next() is None
    assert buf.gap() == 2


def test_buffer_pop_returns_none_during_prefill_and_timeouts():
    buf = JitterBuffer(prefill=2, pref_size=0)
    assert buf.pop(timeout=0) is None
    buf.push(seq_packet(1))
    assert buf._has_item.is_set() is False
    buf.push(seq_packet(2))
    assert buf.pop().sequence == 1


def test_multi_data_event():
    ev = MultiDataEvent[int]()
    assert not ev.is_ready()
    assert ev.wait(0) is False
    ev.notify()
    assert not ev.is_ready()
    ev.register(1)
    ev.register(2)
    assert ev.is_ready()
    assert ev.items == [1, 2]
    assert len(ev.items) == 2
    assert ev.wait(0) is True
    ev.unregister(1)
    ev.unregister(99)
    assert ev.items == [2]
    assert ev.is_ready()
    ev.notify()
    assert ev.is_ready()
    ev.unregister(2)
    assert not ev.is_ready()
    ev.register(3)
    ev.clear()
    assert ev.items == []
    assert not ev.is_ready()


def test_pcm_sink_format_is_noop():
    audio = AudioData(__import__("io").BytesIO(b"x"))
    assert PCMSink().format_audio(audio) is None
    assert PCMSink().encoding == "pcm"
