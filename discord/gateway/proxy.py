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

"""The gateway proxy: one connection to Discord shared by workers through Redis Streams."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING, Any

from ..flags import Intents, MemberCacheFlags
from ..shard import AutoShardedClient
from .brokers.redis import RedisStreamsPublisher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .brokers.redis import RedisStreamsConfig
    from .compression import GatewayCompression
    from .sharding import ShardManager
    from .transport import GatewayTransport, GatewayTransportFactory

__all__ = ("GatewayProxy",)

_log = logging.getLogger(__name__)

_STOP_TIMEOUT = 5.0


class GatewayProxy:
    """Connects to the Discord gateway and forwards the raw events to Redis Streams.

    The proxy does not cache nor parse anything. Every dispatch event is appended
    to the stream of its shard and the commands the workers append to the command
    streams are executed on the matching shard.

    Parameters
    ----------
    token
        The token of the bot.
    config
        The Redis configuration, use the same ``prefix`` as the workers.
    intents
        The intents to identify with.
    shard_ids
        The shards to run, all of them by default.
    shard_count
        The total number of shards, Discord recommendation by default.
    compression
        The transport compression of the gateway connection.
    gateway
        A factory of the upstream transports, the direct connection to Discord by default.
    status_interval
        How often the latency and rate limit state of the shards are published, in seconds.
    """

    def __init__(
        self,
        token: str,
        *,
        config: RedisStreamsConfig,
        intents: Intents | None = None,
        shard_ids: Sequence[int] | None = None,
        shard_count: int | None = None,
        compression: GatewayCompression | None = "zlib-stream",
        gateway: GatewayTransportFactory | None = None,
        status_interval: float = 5.0,
    ) -> None:
        self.token: str = token
        self.config: RedisStreamsConfig = config
        self.intents: Intents = Intents.default() if intents is None else intents
        self.shard_ids: Sequence[int] | None = shard_ids
        self.shard_count: int | None = shard_count
        self.compression: GatewayCompression | None = compression
        self.gateway: GatewayTransportFactory | None = gateway
        self.status_interval: float = status_interval
        self.publisher: RedisStreamsPublisher = RedisStreamsPublisher(config)
        self.launched: asyncio.Event = asyncio.Event()
        self._stop: asyncio.Event = asyncio.Event()
        self._closing: bool = False

    def stop(self) -> None:
        """Ask :meth:`run` to shut down."""
        self._stop.set()

    async def run(self) -> None:
        """Run until :meth:`stop` is called, SIGINT or SIGTERM is received or a shard fails."""
        loop = asyncio.get_running_loop()
        installed: list[signal.Signals] = []
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except (NotImplementedError, RuntimeError):
                continue
            installed.append(sig)

        client = AutoShardedClient(
            intents=self.intents,
            shard_ids=None if self.shard_ids is None else list(self.shard_ids),
            shard_count=self.shard_count,
            gateway=self.gateway,
            gateway_compression=self.compression,
            max_messages=None,
            chunk_guilds_at_startup=False,
            member_cache_flags=MemberCacheFlags.none(),
            cache_default_sounds=False,
        )
        background: list[asyncio.Task[Any]] = []
        commands: list[asyncio.Task[None]] = []
        forward: asyncio.Task[None] | None = None
        self._closing = False
        try:
            await self.publisher.start()
            await client.login(self.token)
            manager = await client._start_gateway(reconnect=True)
            shards = list(client.shard_ids or range(client.shard_count or 0))
            forward = asyncio.create_task(self._forward(manager))
            stopper = asyncio.create_task(self._stop.wait())
            background = [
                asyncio.create_task(self._publish_status(manager)),
                stopper,
            ]
            commands = [
                asyncio.create_task(self._execute_commands(manager, shard_id))
                for shard_id in shards
            ]
            await asyncio.wait({forward, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if forward.done():
                forward.result()
        finally:
            self._closing = True
            for sig in installed:
                loop.remove_signal_handler(sig)
            self.publisher.stop()
            await client.close()
            for task in background:
                task.cancel()
            if commands:
                if self.launched.is_set():
                    await asyncio.wait(
                        commands, timeout=self.config.block_ms / 1000 + _STOP_TIMEOUT
                    )
                for task in commands:
                    task.cancel()
            if forward is not None:
                background.append(forward)
            await asyncio.gather(*background, *commands, return_exceptions=True)
            await self.publisher.close()

    async def _forward(self, manager: ShardManager) -> None:
        async for event in manager.events():
            await self.publisher.publish(event)

    async def _publish_status(self, manager: ShardManager) -> None:
        await manager.launched.wait()
        self.launched.set()
        while not self._closing:
            for shard_id, transport in list(manager.transports.items()):
                await self._publish_shard_status(shard_id, transport)
            await asyncio.sleep(self.status_interval)

    async def _publish_shard_status(
        self, shard_id: int, transport: GatewayTransport
    ) -> None:
        try:
            await self.publisher.publish_status(
                shard_id,
                latency=transport.latency,
                ratelimited=transport.is_ratelimited(),
            )
        except Exception:
            _log.exception("Could not publish the status of shard %s.", shard_id)

    async def _execute_commands(self, manager: ShardManager, shard_id: int) -> None:
        await manager.launched.wait()

        async def execute(op: int, d: Any) -> None:
            await manager.get_transport(shard_id=shard_id).send(op, d)

        await self.publisher.consume_commands(shard_id, execute)
