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

import dataclasses

import pytest

from discord.gateway import (
    NEW_SESSION_CLOSE_CODES,
    NO_RECONNECT_CLOSE_CODES,
    GatewayEvent,
    Opcode,
    resume_url,
)


def test_opcodes_match_the_documentation() -> None:
    assert Opcode.DISPATCH == 0
    assert Opcode.RESUME == 6
    assert Opcode.REQUEST_MEMBERS == 8
    assert Opcode.REQUEST_SOUNDBOARD_SOUNDS == 31
    assert Opcode.REQUEST_CHANNEL_INFO == 43


def test_close_code_groups() -> None:
    assert {4004, 4014, 1000} <= NO_RECONNECT_CLOSE_CODES
    assert {4007, 4009} == NEW_SESSION_CLOSE_CODES
    assert not NEW_SESSION_CLOSE_CODES & NO_RECONNECT_CLOSE_CODES


def test_gateway_event_is_immutable() -> None:
    event = GatewayEvent(op=0, t="READY", s=1, d={})
    assert event.shard_id is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.t = "x"  # type: ignore[misc]


def test_resume_url_keeps_the_query_of_the_gateway() -> None:
    gateway = "wss://gateway.discord.gg?encoding=json&v=10&compress=zstd-stream"

    assert (
        resume_url(gateway, "wss://gateway-us-east1-b.discord.gg")
        == "wss://gateway-us-east1-b.discord.gg?encoding=json&v=10&compress=zstd-stream"
    )


def test_resume_url_of_a_resume_url() -> None:
    first = resume_url("ws://a/?v=10", "ws://b/resume")
    assert first == "ws://b/resume?v=10"
    assert resume_url(first, "ws://b/resume") == first
