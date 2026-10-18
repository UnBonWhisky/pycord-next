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

"""Cache store and buckets on top of an aiocache backend."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, cast, overload

from aiocache import SimpleMemoryCache
from aiocache.backends.memory import SimpleMemoryBackend
from aiocache.serializers import NullSerializer

from ..errors import SyncCacheAccessError
from .index import InProcessIndex, KeyIndex, RedisIndex
from .serializers import ModelSerializer

if TYPE_CHECKING:
    from ..state import ConnectionState

K = TypeVar("K")
V = TypeVar("V")
D = TypeVar("D")

__all__ = ("CacheBucket", "CacheStore")

_NO_ENTRIES: tuple[Any, ...] = ()
_DELETE_BATCH = 500
_GATHER_THRESHOLD = 8
_GLOB_CHARS = frozenset("*?[]\\")


class Backend(Protocol):
    """The subset of :class:`aiocache.BaseCache` used by the cache package."""

    serializer: Any

    async def get(self, key: str) -> Any:
        """Return the value stored at ``key`` or ``None``."""
        ...

    async def multi_get(self, keys: list[str]) -> list[Any]:
        """Return the values stored at ``keys``, ``None`` where missing."""
        ...

    async def set(self, key: str, value: Any, ttl: float | None = None) -> Any:
        """Store ``value`` at ``key``."""
        ...

    async def multi_set(
        self, pairs: list[tuple[str, Any]], ttl: float | None = None
    ) -> Any:
        """Store several ``(key, value)`` pairs."""
        ...

    async def delete(self, key: str) -> Any:
        """Delete ``key``."""
        ...

    async def exists(self, key: str) -> Any:
        """Return whether ``key`` exists."""
        ...

    async def close(self) -> None:
        """Release backend resources."""
        ...


class CacheBucket(Generic[K, V]):
    """A keyed, optionally bounded collection stored in a :class:`CacheStore`.

    Iteration order (:meth:`keys`, :meth:`values`, :meth:`items`) is oldest
    first, like the dicts and deques this replaces. Setting an existing key
    replaces its value and keeps its position. Values must not be ``None``.
    """

    __slots__ = ("_backend", "_index", "_lru", "_maxlen", "_prefix")

    def __init__(
        self,
        backend: Backend,
        prefix: str,
        index: KeyIndex[K],
        *,
        maxlen: int | None = None,
        lru: bool = False,
    ) -> None:
        if maxlen is not None and maxlen < 1:
            raise ValueError("maxlen must be a positive integer or None")
        self._backend = backend
        self._prefix = f"{prefix}:"
        self._index = index
        self._maxlen = maxlen
        self._lru = lru

    @property
    def maxlen(self) -> int | None:
        """Maximum number of entries, or ``None`` if unbounded."""
        return self._maxlen

    @property
    def lru(self) -> bool:
        """Whether a successful :meth:`get` marks the key as most recently used."""
        return self._lru

    @property
    def supports_sync(self) -> bool:
        """Whether the ``*_nowait`` accessors can be used (in-process backend)."""
        return isinstance(self._backend, SimpleMemoryBackend) and isinstance(
            self._index, InProcessIndex
        )

    def _sync_storage(self) -> tuple[dict[str, Any], InProcessIndex[K]]:
        backend = self._backend
        index = self._index
        if not isinstance(backend, SimpleMemoryBackend) or not isinstance(
            index, InProcessIndex
        ):
            raise SyncCacheAccessError(
                "synchronous cache access requires the in-process cache backend; "
                "use the asynchronous getter with a remote backend"
            )
        return cast("dict[str, Any]", backend._cache), index

    def _sync_key(self, key: K) -> str:
        build_key = cast("Callable[[str], str]", cast("Any", self._backend).build_key)
        return build_key(self._prefix + str(key))

    @overload
    def get_nowait(self, key: K) -> V | None: ...

    @overload
    def get_nowait(self, key: K, default: D) -> V | D: ...

    def get_nowait(self, key: K, default: Any = None) -> Any:
        """Return the value for ``key`` synchronously, like :meth:`get`.

        Raises :exc:`~discord.SyncCacheAccessError` on remote backends.
        """
        storage, index = self._sync_storage()
        value = storage.get(self._sync_key(key))
        if value is None:
            return default
        if self._lru:
            index.touch_nowait(key)
        return value

    def contains_nowait(self, key: K) -> bool:
        """Return whether ``key`` is stored, synchronously."""
        storage, _ = self._sync_storage()
        return self._sync_key(key) in storage

    def keys_nowait(self) -> list[K]:
        """Return every key, oldest first, synchronously."""
        _, index = self._sync_storage()
        return index.keys_nowait()

    def values_nowait(self) -> list[V]:
        """Return every value, oldest first, synchronously."""
        return [value for _, value in self.items_nowait()]

    def items_nowait(self) -> list[tuple[K, V]]:
        """Return every ``(key, value)`` pair, oldest first, synchronously."""
        storage, index = self._sync_storage()
        result: list[tuple[K, V]] = []
        for key in index.keys_nowait():
            value = storage.get(self._sync_key(key))
            if value is not None:
                result.append((key, value))
        return result

    def count_nowait(self) -> int:
        """Return the number of entries, synchronously."""
        _, index = self._sync_storage()
        return len(index.keys_nowait())

    @overload
    async def get(self, key: K) -> V | None: ...

    @overload
    async def get(self, key: K, default: D) -> V | D: ...

    async def get(self, key: K, default: Any = None) -> Any:
        """Return the value stored for ``key`` or ``default``."""
        value = await self._backend.get(self._prefix + str(key))
        if value is None:
            return default
        if self._lru:
            await self._index.touch(key)
        return value

    @overload
    async def peek(self, key: K) -> V | None: ...

    @overload
    async def peek(self, key: K, default: D) -> V | D: ...

    async def peek(self, key: K, default: Any = None) -> Any:
        """Return the value stored for ``key`` without refreshing its position."""
        value = await self._backend.get(self._prefix + str(key))
        return default if value is None else value

    async def get_many(self, keys: Iterable[K]) -> dict[K, V]:
        """Return the stored values for the given keys, omitting missing ones."""
        wanted = list(keys)
        if not wanted:
            return {}
        prefix = self._prefix
        values = await self._backend.multi_get([prefix + str(k) for k in wanted])
        found = {k: v for k, v in zip(wanted, values, strict=True) if v is not None}
        if self._lru:
            for key in found:
                await self._index.touch(key)
        return found

    async def set(self, key: K, value: V) -> Sequence[tuple[K, V]]:
        """Store ``value`` and return the pairs evicted to stay within ``maxlen``."""
        await self._backend.set(self._prefix + str(key), value, ttl=None)
        evicted = await self._index.add(key, self._maxlen)
        if evicted:
            return await self._drop(evicted)
        return _NO_ENTRIES

    async def set_many(
        self, items: Mapping[K, V] | Iterable[tuple[K, V]]
    ) -> Sequence[tuple[K, V]]:
        """Store several entries and return the pairs evicted to stay within ``maxlen``."""
        pairs = (
            list(cast("Mapping[K, V]", items).items())
            if isinstance(items, Mapping)
            else list(items)
        )
        if not pairs:
            return _NO_ENTRIES
        prefix = self._prefix
        await self._backend.multi_set(
            [(prefix + str(k), v) for k, v in pairs], ttl=None
        )
        evicted: list[K] = []
        for key, _ in pairs:
            evicted.extend(await self._index.add(key, self._maxlen))
        if evicted:
            return await self._drop(evicted)
        return _NO_ENTRIES

    @overload
    async def pop(self, key: K) -> V | None: ...

    @overload
    async def pop(self, key: K, default: D) -> V | D: ...

    async def pop(self, key: K, default: Any = None) -> Any:
        """Remove ``key`` and return its value or ``default``."""
        full_key = self._prefix + str(key)
        value = await self._backend.get(full_key)
        if value is not None:
            await self._backend.delete(full_key)
        await self._index.discard(key)
        return default if value is None else value

    async def contains(self, key: K) -> bool:
        """Return whether ``key`` is stored."""
        return bool(await self._backend.exists(self._prefix + str(key)))

    async def keys(self) -> list[K]:
        """Return every key, oldest first."""
        return await self._index.keys()

    async def values(self) -> list[V]:
        """Return every value, oldest first."""
        return [value for _, value in await self.items()]

    async def items(self) -> list[tuple[K, V]]:
        """Return every ``(key, value)`` pair, oldest first."""
        keys = await self._index.keys()
        if not keys:
            return []
        prefix = self._prefix
        values = await self._backend.multi_get([prefix + str(k) for k in keys])
        return [(k, v) for k, v in zip(keys, values, strict=True) if v is not None]

    async def count(self) -> int:
        """Return the number of stored entries."""
        return await self._index.count()

    async def clear(self) -> None:
        """Remove every entry."""
        await self._delete_all(await self._index.clear())

    async def _drop(self, keys: Sequence[K]) -> list[tuple[K, V]]:
        prefix = self._prefix
        values = await self._backend.multi_get([prefix + str(k) for k in keys])
        await self._delete_all(keys)
        return [(k, v) for k, v in zip(keys, values, strict=True) if v is not None]

    async def _delete_all(self, keys: Sequence[K]) -> None:
        prefix = self._prefix
        delete = self._backend.delete
        if len(keys) <= _GATHER_THRESHOLD:
            for key in keys:
                await delete(prefix + str(key))
            return
        for start in range(0, len(keys), _DELETE_BATCH):
            batch = keys[start : start + _DELETE_BATCH]
            await asyncio.gather(*(delete(prefix + str(k)) for k in batch))


class CacheStore:
    """Entry point of the cache: owns the aiocache backend and hands out buckets.

    With ``backend=None`` an in-process :class:`aiocache.SimpleMemoryCache` is
    used and live objects are stored as is. Any other backend gets a
    :class:`ModelSerializer`. Nothing written through the store ever expires.
    """

    __slots__ = ("_backend", "_buckets", "_client", "_namespace", "_state")

    def __init__(
        self,
        backend: Backend | None,
        *,
        namespace: str = "pycord",
        state: ConnectionState,
    ) -> None:
        if not namespace or ":" in namespace or _GLOB_CHARS & set(namespace):
            raise ValueError(
                "namespace must be non-empty and contain none of ':*?[]\\'"
            )
        if backend is None:
            backend = cast(
                "Backend",
                SimpleMemoryCache(timeout=None, serializer=NullSerializer()),
            )
        elif isinstance(backend, SimpleMemoryBackend):
            backend.serializer = NullSerializer()
        else:
            backend.serializer = ModelSerializer(state)
        self._backend: Backend = backend
        self._namespace = namespace
        self._state = state
        self._buckets: dict[str, CacheBucket[Any, Any]] = {}
        self._client: Any = (
            getattr(backend, "client", None)
            if getattr(backend, "NAME", None) == "redis"
            else None
        )

    @property
    def supports_sync(self) -> bool:
        """Whether synchronous cache accessors work (default in-process backend)."""
        return isinstance(self._backend, SimpleMemoryBackend)

    @property
    def backend(self) -> Backend:
        """The underlying aiocache backend."""
        return self._backend

    @property
    def namespace(self) -> str:
        """The key prefix shared by every bucket of this store."""
        return self._namespace

    @overload
    def bucket(
        self,
        kind: str,
        *,
        scope: int | None = ...,
        maxlen: int | None = ...,
        lru: bool = ...,
    ) -> CacheBucket[int, Any]: ...

    @overload
    def bucket(
        self,
        kind: str,
        *,
        key_type: Callable[[str], K],
        scope: int | None = ...,
        maxlen: int | None = ...,
        lru: bool = ...,
    ) -> CacheBucket[K, Any]: ...

    def bucket(
        self,
        kind: str,
        *,
        key_type: Callable[[str], Any] = int,
        scope: int | None = None,
        maxlen: int | None = None,
        lru: bool = False,
    ) -> CacheBucket[Any, Any]:
        """Return the bucket for ``kind`` (and ``scope``), creating it on first use.

        ``maxlen`` evicts the oldest entry once exceeded and ``lru`` makes reads
        refresh an entry's position. ``key_type`` converts stored keys back to ``K``.
        """
        if not kind or ":" in kind:
            raise ValueError("kind must be non-empty and must not contain ':'")
        prefix = f"{self._namespace}:{kind}"
        if scope is not None:
            prefix = f"{prefix}:{scope}"
        existing = self._buckets.get(prefix)
        if existing is not None:
            if existing.maxlen != maxlen or existing.lru != lru:
                raise ValueError(
                    f"bucket {prefix!r} already exists with different options"
                )
            return existing
        index: KeyIndex[Any]
        if self._client is not None:
            index = RedisIndex(self._client, prefix, key_type)
        else:
            index = InProcessIndex()
        created = CacheBucket[Any, Any](
            self._backend, prefix, index, maxlen=maxlen, lru=lru
        )
        self._buckets[prefix] = created
        return created

    async def drop(self, kind: str, *, scope: int | None = None) -> None:
        """Clear and forget the bucket for ``kind`` and ``scope``."""
        prefix = f"{self._namespace}:{kind}"
        if scope is not None:
            prefix = f"{prefix}:{scope}"
        existing = self._buckets.pop(prefix, None)
        if existing is not None:
            await existing.clear()

    async def clear(self) -> None:
        """Remove every entry of every bucket in this namespace."""
        client = self._client
        if client is None:
            for existing in list(self._buckets.values()):
                await existing.clear()
            return
        batch: list[Any] = []
        async for key in client.scan_iter(match=f"{self._namespace}:*", count=1000):
            batch.append(key)
            if len(batch) >= 1000:
                await client.unlink(*batch)
                batch.clear()
        if batch:
            await client.unlink(*batch)

    async def close(self) -> None:
        """Close the underlying backend."""
        await self._backend.close()
