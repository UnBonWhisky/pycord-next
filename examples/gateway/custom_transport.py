"""A minimal gateway transport, the skeleton to read the events from somewhere else.

The client does not talk to a websocket, it reads ``GatewayEvent``s from one
``GatewayTransport`` per shard. The default transport connects to Discord; this
one is the shape of a transport fed by a broker, a proxy or a test.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import discord
from discord.gateway import GatewayEvent, GatewayTransport


class QueueTransport(GatewayTransport):
    def __init__(self, shard_id: int | None, shard_count: int | None) -> None:
        super().__init__(shard_id, shard_count)
        self._events: asyncio.Queue[GatewayEvent | None] = asyncio.Queue()
        self._closed = True

    async def connect(self) -> None:
        # Open the connection to your broker here.
        self._closed = False

    async def events(self) -> AsyncIterator[GatewayEvent]:
        # Yield the DISPATCH events, READY first. Stop when the transport is closed.
        while not self._closed:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def send(self, op: int, d: Any) -> None:
        # Commands (presence, voice state, request guild members...) go through here,
        # forward them to whatever holds the connection to Discord.
        print(f"command {op}: {d}")

    async def close(self, code: int = 1000) -> None:
        self._closed = True
        await self._events.put(None)

    @property
    def latency(self) -> float:
        return float("nan")

    def is_ratelimited(self) -> bool:
        return False

    def is_closed(self) -> bool:
        return self._closed


def factory(shard_id: int | None, shard_count: int | None) -> QueueTransport:
    return QueueTransport(shard_id, shard_count)


bot = discord.Bot(gateway=factory)

bot.run(os.environ.get("DISCORD_TOKEN", "TOKEN"))
