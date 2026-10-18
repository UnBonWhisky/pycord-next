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

"""Rate limit handling for the HTTP client."""

from __future__ import annotations

import asyncio
import errno
import logging
import weakref
from typing import TYPE_CHECKING, Any

from .. import utils
from ..errors import RateLimited

if TYPE_CHECKING:
    from types import TracebackType

    import aiohttp
    from typing_extensions import Self

    from .route import Route

__all__ = (
    "CONNECTION_RESET",
    "MAX_TRIES",
    "MaybeUnlock",
    "RateLimiter",
    "backoff",
    "exhausted_delay",
    "is_connection_reset",
)

_log = logging.getLogger(__name__)

MAX_TRIES = 5
CONNECTION_RESET = frozenset({errno.ECONNRESET, 54, 10054})


def backoff(attempt: int) -> float:
    """Return the seconds to wait before retrying after ``attempt`` failures."""
    return 1 + attempt * 2


def exhausted_delay(
    response: Any, status: int, *, use_clock: bool = False
) -> float | None:
    """Return how long a bucket stays empty, or ``None`` if it still has room."""
    if status == 429 or response.headers.get("X-Ratelimit-Remaining") != "0":
        return None
    return utils._parse_ratelimit_header(response, use_clock=use_clock)


def is_connection_reset(exc: BaseException) -> bool:
    """Return whether ``exc``, or anything it wraps, is a connection reset."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, OSError) and current.errno in CONNECTION_RESET:
            return True
        pending.extend(
            wrapped
            for wrapped in (current.__cause__, current.__context__, *current.args)
            if isinstance(wrapped, BaseException)
        )
    return False


class _BucketLock(asyncio.Lock):
    def __init__(self) -> None:
        super().__init__()
        self.reset_at: float = 0.0


class MaybeUnlock:
    """Context manager releasing a lock on exit unless deferred."""

    def __init__(self, lock: asyncio.Lock) -> None:
        self.lock: asyncio.Lock = lock
        self._unlock: bool = True

    def __enter__(self) -> Self:
        return self

    def defer(self) -> None:
        """Keep the lock held after the context exits."""
        self._unlock = False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._unlock:
            self.lock.release()


class RateLimiter:
    """Serialises requests per Discord rate limit bucket.

    Routes are first grouped by their major parameters and path. Once Discord
    reports a bucket hash for a route, every route sharing that hash and the same
    major parameters shares one lock.

    Parameters
    ----------
    use_clock: :class:`bool`
        Whether to compute reset times from the ``X-RateLimit-Reset`` header
        instead of ``X-RateLimit-Reset-After``.
    max_timeout: Optional[:class:`float`]
        The longest rate limit, in seconds, the limiter is allowed to wait for.
        A longer one raises :exc:`~discord.RateLimited` instead. ``None`` waits
        for every rate limit.
    """

    def __init__(
        self, *, use_clock: bool = False, max_timeout: float | None = None
    ) -> None:
        self.use_clock: bool = use_clock
        self.max_timeout: float | None = max_timeout
        self._locks: weakref.WeakValueDictionary[str, _BucketLock] = (
            weakref.WeakValueDictionary()
        )
        self._hashes: dict[str, str] = {}
        self._global_over: asyncio.Event = asyncio.Event()
        self._global_over.set()
        self._global_reset_at: float = 0.0

    def _key(self, route: Route) -> str:
        bucket_hash = self._hashes.get(route.bucket)
        if bucket_hash is None:
            return route.bucket
        return f"{bucket_hash}:{route.major_parameters}"

    def _lock_for(self, route: Route) -> _BucketLock:
        key = self._key(route)
        lock = self._locks.get(key)
        if lock is None:
            lock = _BucketLock()
            self._locks[key] = lock
        return lock

    def _check_timeout(
        self, route: Route, retry_after: float, *, is_global: bool
    ) -> None:
        if self.max_timeout is not None and retry_after > self.max_timeout:
            raise RateLimited(retry_after, route, is_global=is_global)

    async def acquire(self, route: Route) -> MaybeUnlock:
        """Wait until a request to ``route`` may be sent.

        Returns
        -------
        :class:`MaybeUnlock`
            The held bucket lock, released when its context manager exits.

        Raises
        ------
        RateLimited
            A rate limit longer than ``max_timeout`` is in effect.
        """
        loop = asyncio.get_running_loop()
        if not self._global_over.is_set():
            self._check_timeout(
                route, self._global_reset_at - loop.time(), is_global=True
            )
            await self._global_over.wait()

        lock = self._lock_for(route)
        if lock.locked():
            self._check_timeout(route, lock.reset_at - loop.time(), is_global=False)
        await lock.acquire()
        return MaybeUnlock(lock)

    async def observe(
        self, route: Route, response: aiohttp.ClientResponse, held: MaybeUnlock
    ) -> None:
        """Update the limiter with the rate limit headers of a response."""
        bucket_hash = response.headers.get("X-Ratelimit-Bucket")
        if bucket_hash is not None:
            self._hashes[route.bucket] = bucket_hash

        delta = exhausted_delay(response, response.status, use_clock=self.use_clock)
        if delta is not None:
            _log.debug(
                "A rate limit bucket has been exhausted (bucket: %s, retry: %s).",
                route.bucket,
                delta,
            )
            await self._hold(route, held, delta)

    async def _hold(self, route: Route, held: MaybeUnlock, delta: float) -> None:
        loop = asyncio.get_running_loop()
        lock = self._lock_for(route)
        if lock is held.lock:
            held.defer()
        elif lock.locked():
            return
        else:
            await lock.acquire()
        lock.reset_at = loop.time() + delta
        loop.call_later(delta, lock.release)

    async def wait(self, route: Route, retry_after: float, *, is_global: bool) -> None:
        """Sleep through a ``429`` response.

        Raises
        ------
        RateLimited
            ``retry_after`` is longer than ``max_timeout``.
        """
        self._check_timeout(route, retry_after, is_global=is_global)
        _log.warning(
            'We are being rate limited. Retrying in %.2f seconds. Handled under the bucket "%s"',
            retry_after,
            route.bucket,
        )
        if is_global:
            _log.warning(
                "Global rate limit has been hit. Retrying in %.2f seconds.",
                retry_after,
            )
            self._global_reset_at = asyncio.get_running_loop().time() + retry_after
            self._global_over.clear()

        try:
            await asyncio.sleep(retry_after)
        finally:
            if is_global:
                self._global_over.set()
        _log.debug("Done sleeping for the rate limit. Retrying...")
