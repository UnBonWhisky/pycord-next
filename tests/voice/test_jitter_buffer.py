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

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.voice.utils.buffer import JitterBuffer

from .receive_helpers import make_rtp


def drain(buffer: JitterBuffer) -> list[int]:
    out = []
    while (packet := buffer.pop()) is not None:
        out.append(packet.sequence)
    return out


def test_empty_buffer_is_not_ready():
    buffer = JitterBuffer()

    assert len(buffer) == 0
    assert buffer.is_ready() is False
    assert buffer.pop() is None


def test_buffer_prefills_before_it_is_ready():
    buffer = JitterBuffer(prefill=2, pref_size=0)

    buffer.push(make_rtp(1))
    assert buffer.is_ready() is False
    assert buffer.pop() is None

    buffer.push(make_rtp(2))
    assert buffer.is_ready() is True
    assert len(buffer) == 2


def test_packets_are_released_in_order():
    buffer = JitterBuffer(pref_size=0, prefill=1)

    for sequence in (1, 3, 2, 5, 4):
        buffer.push(make_rtp(sequence))

    assert drain(buffer) == [1, 2, 3, 4, 5]
    assert len(buffer) == 0
    assert buffer.is_ready() is False


def test_buffer_keeps_pref_size_packets_back():
    buffer = JitterBuffer(pref_size=1, prefill=1)

    for sequence in (1, 2, 3):
        buffer.push(make_rtp(sequence))

    assert drain(buffer) == [1, 2]
    assert len(buffer) == 1


def test_buffer_waits_for_a_missing_packet_until_full():
    buffer = JitterBuffer(max_size=4, pref_size=0, prefill=1)

    buffer.push(make_rtp(1))
    assert buffer.pop().sequence == 1  # type: ignore

    buffer.push(make_rtp(3))
    assert buffer.is_ready() is False
    assert buffer.pop() is None

    buffer.push(make_rtp(2))
    assert drain(buffer) == [2, 3]


def test_lost_packet_is_skipped_once_the_buffer_is_full():
    buffer = JitterBuffer(max_size=3, pref_size=0, prefill=1)

    buffer.push(make_rtp(1))
    assert buffer.pop().sequence == 1  # type: ignore

    for sequence in (3, 4, 5):
        buffer.push(make_rtp(sequence))

    assert buffer.is_ready() is True
    assert drain(buffer) == [3, 4, 5]


def test_flush_returns_the_remaining_packets_sorted_and_empties_the_buffer():
    buffer = JitterBuffer(pref_size=5, prefill=1)

    for sequence in (4, 2, 3):
        buffer.push(make_rtp(sequence))

    assert [p.sequence for p in buffer.flush()] == [2, 3, 4]
    assert len(buffer) == 0
    assert buffer.is_ready() is False
    assert buffer.flush() == []


def test_reset_clears_everything():
    buffer = JitterBuffer(pref_size=0)
    buffer.push(make_rtp(1))
    buffer.push(make_rtp(2))
    buffer.pop()

    buffer.reset()

    assert len(buffer) == 0
    assert buffer.is_ready() is False
    buffer.push(make_rtp(1))
    assert buffer.pop().sequence == 1  # type: ignore


def test_buffer_never_grows_past_max_size():
    buffer = JitterBuffer(max_size=3, pref_size=1)

    for sequence in range(1, 10):
        buffer.push(make_rtp(sequence))

    assert len(buffer) <= 3


def test_very_old_packets_are_dropped():
    buffer = JitterBuffer(pref_size=0, prefill=1)
    buffer.push(make_rtp(20000, timestamp=20000 * 960))
    assert buffer.pop().sequence == 20000  # type: ignore

    assert buffer.push(make_rtp(5, timestamp=5 * 960)) is False
    assert len(buffer) == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_size": 0}, "max_size"),
        ({"max_size": 2, "pref_size": 3}, "pref_size"),
    ],
)
def test_invalid_sizes_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        JitterBuffer(**kwargs)
