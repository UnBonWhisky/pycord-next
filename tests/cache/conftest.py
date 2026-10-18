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

from types import SimpleNamespace
from typing import Any

import pytest
from aiocache import SimpleMemoryCache
from aiocache.backends.redis import RedisCache
from fakeredis import FakeAsyncRedis, FakeServer

from discord.cache import CacheStore


class Harness:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.server = FakeServer()
        self.state = SimpleNamespace(name="state")

    def backend(self, **kwargs: Any) -> RedisCache | SimpleMemoryCache | None:
        if self.kind == "memory":
            return SimpleMemoryCache(timeout=None, **kwargs) if kwargs else None
        cache = RedisCache(timeout=None, **kwargs)
        cache.client = FakeAsyncRedis(server=self.server, max_connections=2**20)
        return cache

    def store(self, namespace: str = "pycord", **kwargs: Any) -> CacheStore:
        return CacheStore(self.backend(**kwargs), namespace=namespace, state=self.state)

    async def data_keys(self, store: CacheStore) -> set[str]:
        if self.kind == "memory":
            backend: Any = store.backend
            return set(backend._cache)
        client: Any = store.backend.client  # type: ignore[attr-defined]
        keys = {k.decode() async for k in client.scan_iter(match="*")}
        return {k for k in keys if "__" not in k}

    async def ttl(self, store: CacheStore, bucket_prefix: str, key: object) -> Any:
        full_key = f"{store.namespace}:{bucket_prefix}:{key}"
        if self.kind == "memory":
            backend: Any = store.backend
            assert full_key in backend._cache
            return -1 if full_key not in backend._handlers else 1
        client: Any = store.backend.client  # type: ignore[attr-defined]
        return await client.ttl(full_key)


@pytest.fixture(params=["memory", "redis"])
def harness(request: pytest.FixtureRequest) -> Harness:
    return Harness(request.param)


@pytest.fixture
def store(harness: Harness) -> CacheStore:
    return harness.store()
