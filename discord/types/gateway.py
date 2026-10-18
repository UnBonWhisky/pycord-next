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

from typing import Any, TypedDict

from typing_extensions import NotRequired

from .guild import UnavailableGuild
from .snowflake import Snowflake
from .user import User


class SessionStartLimit(TypedDict):
    total: int
    remaining: int
    reset_after: int
    max_concurrency: int


class Gateway(TypedDict):
    url: str


class GatewayBot(Gateway):
    shards: int
    session_start_limit: SessionStartLimit


class GatewayRateLimit(TypedDict):
    opcode: int
    retry_after: float
    meta: NotRequired[dict[str, Any]]


class ReadyApplication(TypedDict):
    id: Snowflake
    flags: int
    flags_new: str


class ReadyEvent(TypedDict):
    v: int
    user: User
    guilds: list[UnavailableGuild]
    session_id: str
    resume_gateway_url: str
    shard: NotRequired[list[int]]
    application: ReadyApplication


class ResumedEvent(TypedDict):
    pass
