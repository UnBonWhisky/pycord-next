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
import json
import zlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

import aiohttp
import fakeredis
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

import discord
from discord.gateway import (
    DiscordGatewayTransport,
    GatewayEvent,
    GatewayTransport,
    IdentifyLimiter,
)
from discord.gateway.brokers import (
    RedisStreamsConfig,
    RedisStreamsPublisher,
    RedisStreamsTransport,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

REDIS_READY: dict[str, Any] = {
    "v": 10,
    "user": {"id": "42", "username": "bot", "discriminator": "0", "bot": True},
    "guilds": [],
    "session_id": "redis-session",
    "resume_gateway_url": "wss://resume.example",
    "application": {"id": "42", "flags": 0},
}

USER = {
    "id": "42",
    "username": "bot",
    "discriminator": "0",
    "avatar": None,
    "bot": True,
}


async def eventually(
    predicate: Callable[[], object], timeout: float = 3.0, interval: float = 0.01
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise TimeoutError
        await asyncio.sleep(interval)


async def next_event(
    events: AsyncIterator[GatewayEvent], timeout: float = 3.0
) -> GatewayEvent:
    return await asyncio.wait_for(anext(events), timeout)


@dataclass
class Connection:
    ws: web.WebSocketResponse
    path: str
    query: dict[str, str]
    received: list[dict[str, Any]] = field(default_factory=list)
    sequence: int = 0
    session_id: str | None = None
    _deflater: Any = None

    def __post_init__(self) -> None:
        compress = self.query.get("compress")
        if compress == "zlib-stream":
            self._deflater = ("zlib", zlib.compressobj())
        elif compress == "zstd-stream":
            zstandard = pytest.importorskip("zstandard")
            self._deflater = ("zstd", zstandard.ZstdCompressor().compressobj())

    async def send(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload)
        if self._deflater is None:
            await self.ws.send_str(text)
            return
        kind, deflater = self._deflater
        if kind == "zlib":
            data = deflater.compress(text.encode()) + deflater.flush(zlib.Z_SYNC_FLUSH)
        else:
            zstandard = pytest.importorskip("zstandard")
            data = deflater.compress(text.encode()) + deflater.flush(
                zstandard.COMPRESSOBJ_FLUSH_BLOCK
            )
        await self.ws.send_bytes(data)

    async def dispatch(self, event: str, data: Any) -> None:
        self.sequence += 1
        await self.send({"op": 0, "t": event, "s": self.sequence, "d": data})

    async def close(self, code: int) -> None:
        await self.ws.close(code=code)

    def ops(self, *ops: int) -> list[dict[str, Any]]:
        return [p for p in self.received if p["op"] in ops]

    @property
    def identify(self) -> dict[str, Any]:
        return self.ops(2)[0]["d"]


Responder = "Callable[[Connection, dict[str, Any]], Awaitable[None]]"


class FakeGateway:
    def __init__(self) -> None:
        self.connections: list[Connection] = []
        self.sessions = 0
        self.on_identify: Callable[[Connection, dict[str, Any]], Awaitable[None]] = (
            self.ready
        )
        self.on_resume: Callable[[Connection, dict[str, Any]], Awaitable[None]] = (
            self.resumed
        )
        self.on_connect: Callable[[Connection], Awaitable[None]] | None = None
        self.identify_times: list[tuple[int | None, float]] = []
        self.heartbeat_interval = 30000
        self._server: TestServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"ws://{self._server.host}:{self._server.port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle)
        app.router.add_get("/resume", self._handle)
        self._server = TestServer(app)
        await self._server.start_server()

    async def stop(self) -> None:
        assert self._server is not None
        await self._server.close()

    def gateway_url(self, compress: str | None = None) -> str:
        url = f"{self.url}/?encoding=json&v=10"
        return url if compress is None else f"{url}&compress={compress}"

    async def ready(self, conn: Connection, _payload: dict[str, Any]) -> None:
        self.sessions += 1
        conn.session_id = f"session-{self.sessions}"
        await conn.dispatch(
            "READY",
            {
                "v": 10,
                "user": USER,
                "guilds": [],
                "session_id": conn.session_id,
                "resume_gateway_url": f"{self.url}/resume",
                "application": {"id": "42", "flags": 0},
                "_trace": ["fake"],
            },
        )

    async def resumed(self, conn: Connection, payload: dict[str, Any]) -> None:
        conn.session_id = payload["d"]["session_id"]
        conn.sequence = payload["d"]["seq"]
        await conn.dispatch("RESUMED", {"_trace": ["fake"]})

    async def _handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        conn = Connection(ws, request.path, dict(request.query))
        self.connections.append(conn)
        if self.on_connect is not None:
            await self.on_connect(conn)
        await conn.send(
            {"op": 10, "d": {"heartbeat_interval": self.heartbeat_interval}}
        )
        async for msg in ws:
            if msg.type is not aiohttp.WSMsgType.TEXT:
                continue
            payload = json.loads(msg.data)
            conn.received.append(payload)
            op = payload["op"]
            if op == 1:
                await conn.send({"op": 11, "d": None})
            elif op == 2:
                loop = asyncio.get_running_loop()
                shard = payload["d"].get("shard")
                self.identify_times.append(
                    (None if shard is None else shard[0], loop.time())
                )
                await self.on_identify(conn, payload)
            elif op == 6:
                await self.on_resume(conn, payload)
        return ws


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeGateway]:
    gateway = FakeGateway()
    await gateway.start()
    yield gateway
    await gateway.stop()


def make_client(
    server: FakeGateway, cls: type[discord.Client] = discord.Client, **options: Any
) -> discord.Client:
    options.setdefault("intents", discord.Intents.none())
    options.setdefault("guild_ready_timeout", 0.05)
    options.setdefault("cache_default_sounds", False)
    client = cls(**options)
    client.http.token = "token"
    client.http.recreate()
    client._identify_limiter.per = 0.05
    compression = client._gateway_compression

    async def get_gateway(**_: Any) -> str:
        return server.gateway_url(compression)

    async def get_bot_gateway_info(**_: Any) -> discord.gateway.GatewayInfo:
        return discord.gateway.GatewayInfo(
            url=server.gateway_url(compression),
            shards=options.get("shard_count") or 1,
            session_start_limit=discord.gateway.SessionStartLimit(
                total=1000,
                remaining=999,
                reset_after=1000,
                max_concurrency=options.get("max_concurrency", 1),
            ),
        )

    client.http.get_gateway = get_gateway  # type: ignore[method-assign]
    client.http.get_bot_gateway_info = get_bot_gateway_info  # type: ignore[method-assign]
    return client


class TransportHarness(Protocol):
    transport: GatewayTransport

    async def start(self) -> None: ...

    async def remote_dispatch(self, event: str, data: Any) -> None: ...

    async def remote_commands(self) -> list[tuple[int, Any]]: ...

    async def stop(self) -> None: ...


class DirectHarness:
    def __init__(self, server: FakeGateway, **options: Any) -> None:
        self.server = server
        self.client = make_client(server, **options)
        self.transport: GatewayTransport = DiscordGatewayTransport(
            self.client,
            identify_limiter=self.client._identify_limiter,
        )
        self.transport.reconnect = False

    async def start(self) -> None:
        await self.transport.connect()

    async def remote_dispatch(self, event: str, data: Any) -> None:
        await self.server.connections[-1].dispatch(event, data)

    async def remote_commands(self) -> list[tuple[int, Any]]:
        conn = self.server.connections[-1]
        return [(p["op"], p["d"]) for p in conn.received if p["op"] not in (1, 2, 6)]

    async def stop(self) -> None:
        await self.transport.close()
        await self.client.http.close()


class RedisHarness:
    def __init__(self, _server: FakeGateway, **options: Any) -> None:
        self.redis = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer())
        self.config = RedisStreamsConfig(
            client=self.redis, block_ms=20, claim_idle_ms=50, **options
        )
        self.publisher = RedisStreamsPublisher(self.config)
        self.transport: GatewayTransport = RedisStreamsTransport(self.config, 0, 1)
        self.transport.reconnect = False
        self.sequence = 0

    async def start(self) -> None:
        await self.publisher.start()
        await self.remote_dispatch("READY", REDIS_READY)
        await self.transport.connect()

    async def remote_dispatch(self, event: str, data: Any) -> None:
        self.sequence += 1
        await self.publisher.publish(GatewayEvent(0, event, self.sequence, data, 0))

    async def remote_commands(self) -> list[tuple[int, Any]]:
        entries = cast("list[Any]", await self.redis.xrange(self.config.commands(0)))
        return [(int(fields[b"op"]), json.loads(fields[b"d"])) for _, fields in entries]

    async def stop(self) -> None:
        await self.transport.close()
        await self.publisher.close()
        await self.redis.aclose()


HARNESS_BUILDERS: dict[str, Callable[[FakeGateway], TransportHarness]] = {
    "direct": DirectHarness,
    "redis": RedisHarness,
}


@pytest_asyncio.fixture(params=sorted(HARNESS_BUILDERS))
async def transport_factory(
    request: pytest.FixtureRequest, server: FakeGateway
) -> AsyncIterator[Callable[[], Awaitable[TransportHarness]]]:
    created: list[TransportHarness] = []

    async def make() -> TransportHarness:
        harness = HARNESS_BUILDERS[request.param](server)
        created.append(harness)
        await harness.start()
        return harness

    yield make
    for harness in created:
        await harness.stop()


@pytest.fixture
def identify_limiter() -> IdentifyLimiter:
    return IdentifyLimiter(per=0.05)
