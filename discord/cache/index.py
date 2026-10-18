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

"""Ordered key indexes used by cache buckets to list and evict keys."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

K = TypeVar("K")

__all__ = ("InProcessIndex", "KeyIndex", "RedisIndex")

_NO_KEYS: tuple[Any, ...] = ()


class KeyIndex(Protocol[K]):
    """Insertion-ordered set of keys, oldest first."""

    async def add(self, key: K, maxlen: int | None) -> Sequence[K]:
        """Append ``key`` if absent and return the keys evicted by ``maxlen``."""
        ...

    async def touch(self, key: K) -> None:
        """Move ``key`` to the newest position if present."""
        ...

    async def discard(self, key: K) -> None:
        """Remove ``key`` if present."""
        ...

    async def keys(self) -> list[K]:
        """Return every key, oldest first."""
        ...

    async def count(self) -> int:
        """Return the number of keys."""
        ...

    async def clear(self) -> list[K]:
        """Remove and return every key."""
        ...


class InProcessIndex(Generic[K]):
    """:class:`KeyIndex` kept in an :class:`~collections.OrderedDict`."""

    __slots__ = ("_keys",)

    def __init__(self) -> None:
        self._keys: OrderedDict[K, None] = OrderedDict()

    async def add(self, key: K, maxlen: int | None) -> Sequence[K]:
        """Append ``key`` if absent and return the keys evicted by ``maxlen``."""
        keys = self._keys
        if key in keys:
            return _NO_KEYS
        keys[key] = None
        if maxlen is None or len(keys) <= maxlen:
            return _NO_KEYS
        evicted: list[K] = []
        while len(keys) > maxlen:
            evicted.append(keys.popitem(last=False)[0])
        return evicted

    async def touch(self, key: K) -> None:
        """Move ``key`` to the newest position if present."""
        if key in self._keys:
            self._keys.move_to_end(key)

    async def discard(self, key: K) -> None:
        """Remove ``key`` if present."""
        self._keys.pop(key, None)

    async def keys(self) -> list[K]:
        """Return every key, oldest first."""
        return list(self._keys)

    async def count(self) -> int:
        """Return the number of keys."""
        return len(self._keys)

    async def clear(self) -> list[K]:
        """Remove and return every key."""
        keys = list(self._keys)
        self._keys.clear()
        return keys

    def touch_nowait(self, key: K) -> None:
        """Move ``key`` to the newest position if present, synchronously."""
        if key in self._keys:
            self._keys.move_to_end(key)

    def keys_nowait(self) -> list[K]:
        """Return every key, oldest first, synchronously."""
        return list(self._keys)


class RedisIndex(Generic[K]):
    """:class:`KeyIndex` stored in a Redis sorted set, safe across processes.

    Each key is scored with a value from a shared counter, so the sorted set
    orders keys by insertion (or last touch). Eviction runs in the same
    transaction as the insertion.
    """

    __slots__ = ("_client", "_index_key", "_key_type", "_seq_key")

    def __init__(self, client: Any, prefix: str, key_type: Callable[[str], K]) -> None:
        self._client = client
        self._index_key = f"{prefix}:__index__"
        self._seq_key = f"{prefix}:__seq__"
        self._key_type = key_type

    def _decode(self, members: Sequence[bytes | str]) -> list[K]:
        key_type = self._key_type
        return [key_type(m.decode() if isinstance(m, bytes) else m) for m in members]

    async def add(self, key: K, maxlen: int | None) -> Sequence[K]:
        """Append ``key`` if absent and return the keys evicted by ``maxlen``."""
        client = self._client
        score = await client.incr(self._seq_key)
        member = str(key)
        if maxlen is None:
            await client.zadd(self._index_key, {member: score}, nx=True)
            return _NO_KEYS
        async with client.pipeline(transaction=True) as pipe:
            pipe.zadd(self._index_key, {member: score}, nx=True)
            pipe.zrange(self._index_key, 0, -(maxlen + 1))
            pipe.zremrangebyrank(self._index_key, 0, -(maxlen + 1))
            _, evicted, _ = await pipe.execute()
        return self._decode(evicted) if evicted else _NO_KEYS

    async def touch(self, key: K) -> None:
        """Move ``key`` to the newest position if present."""
        score = await self._client.incr(self._seq_key)
        await self._client.zadd(self._index_key, {str(key): score}, xx=True)

    async def discard(self, key: K) -> None:
        """Remove ``key`` if present."""
        await self._client.zrem(self._index_key, str(key))

    async def keys(self) -> list[K]:
        """Return every key, oldest first."""
        return self._decode(await self._client.zrange(self._index_key, 0, -1))

    async def count(self) -> int:
        """Return the number of keys."""
        return int(await self._client.zcard(self._index_key))

    async def clear(self) -> list[K]:
        """Remove and return every key."""
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.zrange(self._index_key, 0, -1)
            pipe.delete(self._index_key, self._seq_key)
            members, _ = await pipe.execute()
        return self._decode(members)
