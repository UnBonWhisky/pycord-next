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

from typing import TYPE_CHECKING, Any

import pytest
from aiocache.backends.redis import RedisCache
from fakeredis import FakeAsyncRedis, FakeServer

from discord.flags import MemberCacheFlags
from discord.state import ConnectionState

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient


def build_state(
    loop: asyncio.AbstractEventLoop,
    http: HTTPClient,
    kind: str = "memory",
    **options: Any,
) -> ConnectionState:
    if kind == "redis":
        backend = RedisCache(timeout=None)
        backend.client = FakeAsyncRedis(server=FakeServer(), max_connections=2**20)
        options["cache_backend"] = backend
    state = ConnectionState(
        dispatch=lambda *_args, **_kwargs: None,
        handlers={},
        hooks={},
        http=http,
        loop=loop,
        **options,
    )
    state.member_cache_flags = MemberCacheFlags.all()
    return state


@pytest.fixture(params=["memory", "redis"])
def backend_kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def cache_state(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> ConnectionState:
    return build_state(loop, http, backend_kind)
