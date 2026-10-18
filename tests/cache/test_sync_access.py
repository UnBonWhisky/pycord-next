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

"""Synchronous cache accessors (decision D11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiocache import SimpleMemoryCache

from discord import SyncCacheAccessError
from discord.cache import CacheStore

if TYPE_CHECKING:
    from .conftest import Harness


async def test_sync_accessors_match_async(harness: Harness) -> None:
    store = harness.store()
    bucket = store.bucket("users", maxlen=3, lru=True)
    for key in (1, 2, 3):
        await bucket.set(key, f"v{key}")
    if harness.kind == "redis":
        assert not store.supports_sync
        assert not bucket.supports_sync
        for call in (
            lambda: bucket.get_nowait(1),
            bucket.values_nowait,
            bucket.keys_nowait,
            bucket.items_nowait,
            bucket.count_nowait,
            lambda: bucket.contains_nowait(1),
        ):
            with pytest.raises(SyncCacheAccessError):
                call()
        return
    assert store.supports_sync
    assert bucket.get_nowait(2) == "v2"
    assert bucket.get_nowait(9, "x") == "x"
    assert bucket.contains_nowait(3)
    assert not bucket.contains_nowait(9)
    assert bucket.keys_nowait() == await bucket.keys() == [1, 3, 2]
    assert bucket.values_nowait() == await bucket.values()
    assert bucket.items_nowait() == await bucket.items()
    assert bucket.count_nowait() == await bucket.count() == 3
    await bucket.set(4, "v4")
    assert bucket.keys_nowait() == [3, 2, 4]


async def test_sync_accessors_with_namespaced_memory_backend() -> None:
    store = CacheStore(SimpleMemoryCache(timeout=None, namespace="ns-"), state=object())  # type: ignore[arg-type]
    bucket = store.bucket("guilds")
    await bucket.set(1, "g")
    assert bucket.get_nowait(1) == "g"
    assert bucket.values_nowait() == ["g"]
