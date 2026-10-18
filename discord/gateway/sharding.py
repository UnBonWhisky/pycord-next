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

"""The shard manager owning the transports of a client."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING

from .models import GatewayEvent
from .ratelimiter import IdentifyLimiter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from .transport import GatewayTransport, GatewayTransportFactory

__all__ = ("ShardManager",)

_log = logging.getLogger(__name__)


class _Stop:
    pass


class _Ended:
    pass


_STOP = _Stop()


class ShardManager:
    """Owns the transports of the shards of a client.

    Shards are launched in buckets of ``shard_id % max_concurrency``, the buckets in
    parallel and the shards of a bucket one after the other. The events of every
    transport are merged in a single stream, the events of one shard stay in order.

    Parameters
    ----------
    factory
        Creates the transport of a shard from its ``shard_id`` and the ``shard_count``.
    shard_ids
        The shards to launch, ``[None]`` for a client that is not sharded.
    shard_count
        The total number of shards.
    identify_limiter
        The limiter of the transports, its ``max_concurrency`` defines the buckets.
    dispatch
        Dispatches the events of the client.
    sharded
        Whether the shard events are dispatched and guilds are routed by shard.
    on_launched
        Called once every shard is connected.
    """

    def __init__(
        self,
        factory: GatewayTransportFactory,
        *,
        shard_ids: Sequence[int | None],
        shard_count: int | None,
        identify_limiter: IdentifyLimiter | None = None,
        dispatch: Callable[..., None],
        sharded: bool = False,
        on_launched: Callable[[], None] | None = None,
    ) -> None:
        self._factory: GatewayTransportFactory = factory
        self._shard_ids: Sequence[int | None] = shard_ids
        self.shard_count: int | None = shard_count
        self.identify_limiter: IdentifyLimiter = identify_limiter or IdentifyLimiter()
        self._dispatch: Callable[..., None] = dispatch
        self.sharded: bool = sharded
        self._on_launched: Callable[[], None] | None = on_launched
        self.transports: dict[int, GatewayTransport] = {}
        self.launched: asyncio.Event = asyncio.Event()
        self._reconnect: bool = True
        self._closed: bool = False
        self._launcher: asyncio.Task[None] | None = None
        self._pumps: dict[int, asyncio.Task[None]] = {}
        self._queue: asyncio.Queue[GatewayEvent | BaseException | _Ended | _Stop] = (
            asyncio.Queue()
        )

    @staticmethod
    def _key(shard_id: int | None) -> int:
        return 0 if shard_id is None else shard_id

    @property
    def buckets(self) -> list[list[int | None]]:
        """The shards grouped by identify rate limit key, in launch order."""
        grouped: dict[int, list[int | None]] = {}
        for shard_id in self._shard_ids:
            grouped.setdefault(self.identify_limiter.bucket(shard_id), []).append(
                shard_id
            )
        return list(grouped.values())

    def get_transport(
        self, guild_id: int | None = None, *, shard_id: int | None = None
    ) -> GatewayTransport:
        """Get the transport serving a shard, or the shard of a guild."""
        if shard_id is None:
            if self.sharded and guild_id is not None and self.shard_count:
                shard_id = (guild_id >> 22) % self.shard_count
            else:
                shard_id = self._shard_ids[0] if self._shard_ids else None
        return self.transports[self._key(shard_id)]

    @property
    def latencies(self) -> list[tuple[int, float]]:
        """The ``(shard_id, latency)`` of every launched shard."""
        return [
            (shard_id, transport.latency)
            for shard_id, transport in self.transports.items()
        ]

    def is_ratelimited(self) -> bool:
        """Whether any shard cannot send a command right now."""
        return any(t.is_ratelimited() for t in self.transports.values())

    async def start(self, *, reconnect: bool = True) -> None:
        """Start launching the shards in the background."""
        self._reconnect = reconnect
        self._launcher = asyncio.create_task(self._launch())

    async def events(self) -> AsyncIterator[GatewayEvent]:
        """Iterate over the events of every shard until the manager is closed.

        A fatal error of a transport is raised from the iteration.
        """
        while True:
            item = await self._queue.get()
            if isinstance(item, _Stop):
                return
            if isinstance(item, GatewayEvent):
                yield item
            elif isinstance(item, _Ended):
                await self.close()
            else:
                raise item

    async def close(self) -> None:
        """Close every transport and end the iteration of :meth:`events`."""
        if self._closed:
            return
        self._closed = True

        if self._launcher is not None:
            self._launcher.cancel()

        await asyncio.gather(
            *(transport.close(1000) for transport in self.transports.values()),
            return_exceptions=True,
        )

        pumps = [pump for pump in self._pumps.values() if not pump.done()]
        if pumps:
            await asyncio.wait(pumps, timeout=5.0)
            for pump in pumps:
                pump.cancel()

        self._queue.put_nowait(_STOP)

    async def disconnect_shard(self, shard_id: int | None) -> None:
        """Close the connection of a shard, without starting it again."""
        key = self._key(shard_id)
        self._cancel_pump(key)
        await self.transports[key].close(1000)
        self._dispatch("shard_disconnect", shard_id)

    async def connect_shard(self, shard_id: int | None) -> None:
        """Start a new session on a shard."""
        key = self._key(shard_id)
        transport = self.transports[key]
        self._cancel_pump(key)
        await transport.connect()
        self._start_pump(key, transport)

    async def reconnect_shard(self, shard_id: int | None) -> None:
        """Close the connection of a shard and start a new session."""
        transport = self.transports[self._key(shard_id)]
        if not transport.is_closed():
            await self.disconnect_shard(shard_id)
        await self.connect_shard(shard_id)

    def _create(self, shard_id: int | None) -> GatewayTransport:
        transport = self._factory(shard_id, self.shard_count)
        transport.reconnect = self._reconnect
        transport.on_disconnect = partial(self._on_disconnect, shard_id)
        self.transports[self._key(shard_id)] = transport
        return transport

    def _on_disconnect(self, shard_id: int | None) -> None:
        self._dispatch("disconnect")
        if self.sharded:
            self._dispatch("shard_disconnect", shard_id)

    async def _launch_bucket(self, bucket: Sequence[int | None]) -> None:
        for shard_id in bucket:
            transport = self._create(shard_id)
            await transport.connect()
            self._start_pump(self._key(shard_id), transport)

    async def _launch(self) -> None:
        tasks = [
            asyncio.create_task(self._launch_bucket(bucket)) for bucket in self.buckets
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise
        except Exception as exc:
            for task in tasks:
                task.cancel()
            self._queue.put_nowait(exc)
            return
        self.launched.set()
        if self._on_launched is not None:
            self._on_launched()

    def _start_pump(self, key: int, transport: GatewayTransport) -> None:
        self._pumps[key] = asyncio.create_task(self._pump(transport))

    def _cancel_pump(self, key: int) -> None:
        pump = self._pumps.pop(key, None)
        if pump is not None and not pump.done():
            pump.cancel()

    async def _pump(self, transport: GatewayTransport) -> None:
        try:
            async for event in transport.events():
                self._queue.put_nowait(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._queue.put_nowait(exc)
        else:
            self._queue.put_nowait(_Ended())
