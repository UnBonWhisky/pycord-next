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

import asyncio

import pytest
from aiocache import SimpleMemoryCache

from discord.cache import CacheBucket, CacheStore
from tests.cache.conftest import Harness


async def test_basic_operations(store: CacheStore) -> None:
    bucket = store.bucket("things")
    assert await bucket.get(1) is None
    assert await bucket.get(1, "missing") == "missing"
    assert not await bucket.contains(1)
    assert await bucket.count() == 0
    assert await bucket.keys() == []

    assert not await bucket.set(1, "one")
    await bucket.set(2, "two")
    await bucket.set(3, "three")

    assert await bucket.get(2) == "two"
    assert await bucket.contains(3)
    assert await bucket.count() == 3
    assert await bucket.keys() == [1, 2, 3]
    assert await bucket.values() == ["one", "two", "three"]
    assert await bucket.items() == [(1, "one"), (2, "two"), (3, "three")]

    assert await bucket.pop(2) == "two"
    assert await bucket.pop(2) is None
    assert await bucket.pop(2, "gone") == "gone"
    assert not await bucket.contains(2)
    assert await bucket.keys() == [1, 3]
    assert await bucket.count() == 2

    await bucket.clear()
    assert await bucket.count() == 0
    assert await bucket.keys() == []
    assert await bucket.get(1) is None


async def test_overwrite_keeps_position(store: CacheStore) -> None:
    bucket = store.bucket("things")
    await bucket.set(1, "a")
    await bucket.set(2, "b")
    await bucket.set(1, "c")
    assert await bucket.items() == [(1, "c"), (2, "b")]
    assert await bucket.count() == 2


async def test_pop_then_set_moves_to_end(store: CacheStore) -> None:
    bucket = store.bucket("things")
    await bucket.set(1, "a")
    await bucket.set(2, "b")
    await bucket.pop(1)
    await bucket.set(1, "a")
    assert await bucket.keys() == [2, 1]


async def test_bucket_is_memoised(store: CacheStore) -> None:
    assert store.bucket("things", maxlen=3) is store.bucket("things", maxlen=3)
    with pytest.raises(ValueError, match="different options"):
        store.bucket("things", maxlen=4)
    with pytest.raises(ValueError, match="different options"):
        store.bucket("things", maxlen=3, lru=True)


async def test_invalid_arguments(store: CacheStore) -> None:
    with pytest.raises(ValueError, match="kind"):
        store.bucket("a:b")
    with pytest.raises(ValueError, match="maxlen"):
        store.bucket("x", maxlen=0)
    with pytest.raises(ValueError, match="namespace"):
        CacheStore(None, namespace="a:b", state=None)  # type: ignore[arg-type]


async def test_scope_isolation(store: CacheStore) -> None:
    first = store.bucket("members", scope=1)
    second = store.bucket("members", scope=2)
    unscoped = store.bucket("members")
    await first.set(10, "a")
    await second.set(10, "b")
    await second.set(11, "c")

    assert await first.get(10) == "a"
    assert await second.get(10) == "b"
    assert await unscoped.get(10) is None
    assert await first.keys() == [10]
    assert await second.keys() == [10, 11]
    assert await unscoped.count() == 0

    await second.clear()
    assert await first.get(10) == "a"
    assert await second.count() == 0


async def test_namespace_isolation(harness: Harness) -> None:
    shared = harness.backend()
    if shared is None:
        shared = SimpleMemoryCache(timeout=None)
    one = CacheStore(shared, namespace="one", state=harness.state)  # type: ignore[arg-type]
    two = CacheStore(shared, namespace="two", state=harness.state)  # type: ignore[arg-type]
    await one.bucket("things").set(1, "from one")
    await two.bucket("things").set(1, "from two")
    await two.bucket("things").set(2, "extra")

    assert await one.bucket("things").get(1) == "from one"
    assert await two.bucket("things").get(1) == "from two"
    assert await one.bucket("things").count() == 1
    assert await two.bucket("things").count() == 2

    await one.clear()
    assert await one.bucket("things").get(1) is None
    assert await two.bucket("things").get(1) == "from two"
    assert await two.bucket("things").count() == 2


async def test_maxlen_evicts_oldest_in_insertion_order(store: CacheStore) -> None:
    bucket = store.bucket("messages", maxlen=3)
    for i in range(1, 4):
        assert not await bucket.set(i, f"m{i}")
    assert await bucket.keys() == [1, 2, 3]

    assert await bucket.set(4, "m4") == [(1, "m1")]
    assert await bucket.keys() == [2, 3, 4]
    assert await bucket.get(1) is None
    assert not await bucket.contains(1)

    assert await bucket.set(5, "m5") == [(2, "m2")]
    assert await bucket.values() == ["m3", "m4", "m5"]
    assert await bucket.count() == 3


async def test_maxlen_reads_do_not_reorder(store: CacheStore) -> None:
    bucket = store.bucket("messages", maxlen=2)
    await bucket.set(1, "a")
    await bucket.set(2, "b")
    await bucket.get(1)
    await bucket.set(3, "c")
    assert await bucket.keys() == [2, 3]


async def test_maxlen_overwrite_does_not_evict(store: CacheStore) -> None:
    bucket = store.bucket("messages", maxlen=2)
    await bucket.set(1, "a")
    await bucket.set(2, "b")
    assert not await bucket.set(1, "a2")
    assert await bucket.items() == [(1, "a2"), (2, "b")]


async def test_maxlen_none_is_unbounded(store: CacheStore) -> None:
    bucket = store.bucket("things")
    assert bucket.maxlen is None
    await bucket.set_many({i: i for i in range(1500)})
    assert await bucket.count() == 1500
    assert (await bucket.keys())[0] == 0


async def test_lru_get_touches(store: CacheStore) -> None:
    bucket = store.bucket("private_channels", maxlen=3, lru=True)
    for i in range(1, 4):
        await bucket.set(i, f"c{i}")
    assert await bucket.get(1) == "c1"
    assert await bucket.keys() == [2, 3, 1]

    assert await bucket.set(4, "c4") == [(2, "c2")]
    assert await bucket.keys() == [3, 1, 4]


async def test_lru_only_hits_touch(store: CacheStore) -> None:
    bucket = store.bucket("private_channels", maxlen=3, lru=True)
    for i in range(1, 4):
        await bucket.set(i, f"c{i}")
    assert await bucket.get(99) is None
    await bucket.contains(1)
    await bucket.values()
    await bucket.items()
    await bucket.keys()
    assert await bucket.keys() == [1, 2, 3]


async def test_lru_overwrite_keeps_position(store: CacheStore) -> None:
    bucket = store.bucket("private_channels", maxlen=3, lru=True)
    for i in range(1, 4):
        await bucket.set(i, f"c{i}")
    await bucket.set(1, "again")
    assert await bucket.keys() == [1, 2, 3]
    assert await bucket.set(4, "c4") == [(1, "again")]


async def test_non_lru_get_does_not_touch(store: CacheStore) -> None:
    bucket = store.bucket("things", maxlen=3)
    for i in range(1, 4):
        await bucket.set(i, i)
    await bucket.get(1)
    assert await bucket.keys() == [1, 2, 3]


async def test_no_ttl(harness: Harness) -> None:
    store = harness.store(ttl=1)
    bucket = store.bucket("things", maxlen=5)
    await bucket.set(1, "a")
    await bucket.set_many({2: "b", 3: "c"})
    for key in (1, 2, 3):
        assert await harness.ttl(store, "things", key) == -1
    await asyncio.sleep(1.2)
    assert await bucket.items() == [(1, "a"), (2, "b"), (3, "c")]


async def test_set_many_and_get_many(store: CacheStore) -> None:
    bucket = store.bucket("things")
    assert await bucket.get_many([]) == {}
    assert not await bucket.set_many([])
    assert not await bucket.set_many({1: "a", 2: "b"})
    assert not await bucket.set_many([(3, "c"), (1, "a2")])

    assert await bucket.get_many([1, 2, 3, 4]) == {1: "a2", 2: "b", 3: "c"}
    assert await bucket.keys() == [1, 2, 3]


async def test_set_many_evicts(store: CacheStore) -> None:
    bucket = store.bucket("things", maxlen=3)
    await bucket.set_many({1: "a", 2: "b"})
    evicted = await bucket.set_many([(3, "c"), (4, "d"), (5, "e")])
    assert evicted == [(1, "a"), (2, "b")]
    assert await bucket.keys() == [3, 4, 5]
    assert await bucket.get_many([1, 2, 3]) == {3: "c"}


async def test_get_many_touches_lru(store: CacheStore) -> None:
    bucket = store.bucket("things", maxlen=3, lru=True)
    await bucket.set_many({1: "a", 2: "b", 3: "c"})
    await bucket.get_many([1, 2, 9])
    assert await bucket.keys() == [3, 1, 2]


async def test_str_keys(store: CacheStore) -> None:
    bucket = store.bucket("named", key_type=str)
    await bucket.set("alpha", 1)
    await bucket.set("beta", 2)
    assert await bucket.keys() == ["alpha", "beta"]
    assert await bucket.items() == [("alpha", 1), ("beta", 2)]


async def test_concurrent_writers_keep_index_consistent(
    harness: Harness, store: CacheStore
) -> None:
    bucket = store.bucket("messages", maxlen=50)
    await asyncio.gather(*(bucket.set(i, f"v{i}") for i in range(300)))

    keys = await bucket.keys()
    assert len(keys) == len(set(keys)) == 50 == await bucket.count()
    assert dict(await bucket.items()) == {k: f"v{k}" for k in keys}
    assert await harness.data_keys(store) == {f"pycord:messages:{k}" for k in keys}


async def test_concurrent_writers_unbounded(store: CacheStore) -> None:
    bucket = store.bucket("things")
    await asyncio.gather(*(bucket.set(i % 100, i) for i in range(400)))
    assert sorted(await bucket.keys()) == list(range(100))
    assert await bucket.count() == 100


async def test_concurrent_mixed_operations(store: CacheStore) -> None:
    bucket = store.bucket("things", maxlen=40, lru=True)

    async def worker(n: int) -> None:
        for i in range(n * 10, n * 10 + 10):
            await bucket.set(i, i)
            await bucket.get(i - 1)
            if i % 3 == 0:
                await bucket.pop(i)

    await asyncio.gather(*(worker(n) for n in range(10)))
    keys = await bucket.keys()
    assert len(keys) == len(set(keys)) <= 40
    assert [await bucket.get(k) for k in keys] == keys
    assert await bucket.count() == len(keys)


async def test_store_clear_and_drop(store: CacheStore) -> None:
    a = store.bucket("a")
    b = store.bucket("b", scope=7)
    await a.set(1, "x")
    await b.set(1, "y")
    await store.drop("b", scope=7)
    assert await a.get(1) == "x"
    assert await b.get(1) is None
    assert store.bucket("b", scope=7) is not b

    await store.clear()
    assert await a.get(1) is None
    assert await a.count() == 0


async def test_default_memory_backend_is_fast_path() -> None:
    store = CacheStore(None, state=None)  # type: ignore[arg-type]
    backend = store.backend
    assert isinstance(backend, SimpleMemoryCache)
    assert backend.timeout is None
    sentinel = object()
    await store.bucket("objs").set(1, sentinel)
    assert await store.bucket("objs").get(1) is sentinel


async def test_remote_backends_share_index() -> None:
    harness = Harness("redis")
    first = harness.store()
    second = harness.store()
    one: CacheBucket[int, str] = first.bucket("messages", maxlen=3)
    two: CacheBucket[int, str] = second.bucket("messages", maxlen=3)
    await one.set(1, "a")
    await two.set(2, "b")
    await one.set(3, "c")
    assert await two.keys() == [1, 2, 3]
    assert await two.set(4, "d") == [(1, "a")]
    assert await one.keys() == [2, 3, 4]
    assert await one.get(2) == "b"


async def test_remote_backend_roundtrips_containers() -> None:
    store = Harness("redis").store()
    bucket = store.bucket("misc")
    value = {"a": [1, 2, (3, 4)], "b": {1, 2}, 5: None, "c": frozenset({"x"})}
    await bucket.set(1, value)
    assert await bucket.get(1) == value
