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

"""Outbound gateway rate limiting and identify concurrency control."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

__all__ = ("GatewayRatelimiter", "IdentifyLimiter")

_log = logging.getLogger(__name__)


class GatewayRatelimiter:
    """Limits the commands sent on one gateway connection."""

    def __init__(self, count: int = 110, per: float = 60.0) -> None:
        # The default is 110 to give room for at least 10 heartbeats per minute
        self.max: int = count
        self.remaining: int = count
        self.window: float = 0.0
        self.per: float = per
        self.lock: asyncio.Lock = asyncio.Lock()
        self.shard_id: int | None = None

    def is_ratelimited(self) -> bool:
        """Whether no command can be sent right now."""
        current = time.time()
        if current > self.window + self.per:
            return False
        return self.remaining == 0

    def get_delay(self) -> float:
        """Reserve a send and return how long to wait before doing it."""
        current = time.time()

        if current > self.window + self.per:
            self.remaining = self.max

        if self.remaining == self.max:
            self.window = current

        if self.remaining == 0:
            return self.per - (current - self.window)

        self.remaining -= 1
        if self.remaining == 0:
            self.window = current

        return 0.0

    async def block(self) -> None:
        """Wait until a command can be sent."""
        async with self.lock:
            delta = self.get_delay()
            if delta:
                _log.warning(
                    "WebSocket in shard ID %s is ratelimited, waiting %.2f seconds",
                    self.shard_id,
                    delta,
                )
                await asyncio.sleep(delta)


class IdentifyLimiter:
    """Spaces the IDENTIFY payloads according to ``max_concurrency``.

    Shards are split in buckets by ``shard_id % max_concurrency``. A bucket can
    identify once every ``per`` seconds, different buckets do not wait for each other.
    """

    def __init__(self, max_concurrency: int = 1, *, per: float = 5.0) -> None:
        self._max_concurrency: int = 1
        self.max_concurrency = max_concurrency
        self.per: float = per
        self._locks: dict[int, asyncio.Lock] = {}
        self._last: dict[int, float] = {}

    @property
    def max_concurrency(self) -> int:
        """How many shards can identify at the same time."""
        return self._max_concurrency

    @max_concurrency.setter
    def max_concurrency(self, value: int) -> None:
        if value < 1:
            msg = "max_concurrency must be at least 1"
            raise ValueError(msg)
        self._max_concurrency = value

    def bucket(self, shard_id: int | None) -> int:
        """The rate limit key of a shard."""
        return (shard_id or 0) % self._max_concurrency

    @asynccontextmanager
    async def slot(self, shard_id: int | None) -> AsyncGenerator[None]:
        """Reserve the identify slot of the bucket of a shard until the context exits."""
        bucket = self.bucket(shard_id)
        lock = self._locks.setdefault(bucket, asyncio.Lock())
        async with lock:
            last = self._last.get(bucket)
            if last is not None:
                delay = last + self.per - time.monotonic()
                if delay > 0:
                    _log.info(
                        "Shard ID %s waits %.2f seconds for the identify slot of bucket %s",
                        shard_id,
                        delay,
                        bucket,
                    )
                    await asyncio.sleep(delay)
            try:
                yield
            finally:
                self._last[bucket] = time.monotonic()
