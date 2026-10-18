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

"""Data types shared by the gateway transports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..types.gateway import SessionStartLimit as SessionStartLimitPayload

__all__ = (
    "NEW_SESSION_CLOSE_CODES",
    "NO_RECONNECT_CLOSE_CODES",
    "GatewayEvent",
    "GatewayInfo",
    "Opcode",
    "SessionStartLimit",
    "resume_url",
)


class Opcode(IntEnum):
    """The gateway opcodes defined by Discord."""

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE = 3
    VOICE_STATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_MEMBERS = 8
    INVALIDATE_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    REQUEST_SOUNDBOARD_SOUNDS = 31
    REQUEST_CHANNEL_INFO = 43


NO_RECONNECT_CLOSE_CODES: frozenset[int] = frozenset(
    {1000, 4004, 4010, 4011, 4012, 4013, 4014}
)

NEW_SESSION_CLOSE_CODES: frozenset[int] = frozenset({4007, 4009})


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    """A payload received from the gateway.

    Transports only yield ``DISPATCH`` events, so ``op`` is ``0`` and ``t`` is set.
    """

    op: int
    t: str | None
    s: int | None
    d: Any
    shard_id: int | None = None


@dataclass(frozen=True, slots=True)
class SessionStartLimit:
    """The session start limit of the application.

    Attributes
    ----------
    total: :class:`int`
        The number of sessions the application can start in a reset period.
    remaining: :class:`int`
        The number of sessions that can still be started.
    reset_after: :class:`int`
        The number of milliseconds until the limit resets.
    max_concurrency: :class:`int`
        The number of IDENTIFY payloads that can be sent every 5 seconds.
    """

    total: int = 1000
    remaining: int = 1000
    reset_after: int = 0
    max_concurrency: int = 1

    @classmethod
    def from_payload(cls, data: SessionStartLimitPayload) -> SessionStartLimit:
        """Create the limit from the payload of Get Gateway Bot."""
        return cls(
            total=int(data["total"]),
            remaining=int(data["remaining"]),
            reset_after=int(data["reset_after"]),
            max_concurrency=int(data["max_concurrency"]),
        )


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """The response of Get Gateway Bot."""

    url: str
    shards: int
    session_start_limit: SessionStartLimit


def resume_url(gateway: str, resume_gateway_url: str) -> str:
    """Build the URL to resume a session on.

    The host comes from the ``resume_gateway_url`` of the READY event and the
    query parameters (version, encoding, compression) from the original gateway URL.
    """
    base = urlsplit(gateway)
    resume = urlsplit(resume_gateway_url)
    return urlunsplit(
        (
            resume.scheme or base.scheme,
            resume.netloc or base.netloc,
            resume.path or base.path,
            base.query,
            "",
        )
    )
