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

"""The gateway transport interface and the default Discord websocket transport."""

from __future__ import annotations

import abc
import asyncio
import errno
import logging
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, cast

import aiohttp

from ..activity import BaseActivity
from ..backoff import ExponentialBackoff
from ..errors import (
    ClientException,
    ConnectionClosed,
    GatewayNotFound,
    HTTPException,
    InvalidArgument,
    LoginFailure,
    PrivilegedIntentsRequired,
)
from .models import GatewayEvent, Opcode, resume_url
from .ratelimiter import IdentifyLimiter
from .websocket import DiscordWebSocket, ReconnectWebSocket

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from ..client import Client

__all__ = (
    "DiscordGatewayTransport",
    "GatewayTransport",
    "GatewayTransportFactory",
)

_log = logging.getLogger(__name__)

_CONNECTION_RESET_ERRNOS = (errno.ECONNRESET, 54, 10054)

_HANDLED_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    HTTPException,
    GatewayNotFound,
    ConnectionClosed,
    aiohttp.ClientError,
    asyncio.TimeoutError,
)
_POLL_ERRORS: tuple[type[BaseException], ...] = (ReconnectWebSocket, *_HANDLED_ERRORS)


def _ignore() -> None:
    return None


class GatewayTransport(abc.ABC):
    """The connection between the client and the Discord gateway of one shard.

    A transport yields the ``DISPATCH`` events of its shard and sends commands to
    the gateway. :class:`DiscordGatewayTransport` talks to Discord directly, other
    implementations can read the events from a broker fed by a gateway proxy.

    Attributes
    ----------
    shard_id: Optional[:class:`int`]
        The ID of the shard, ``None`` when the client is not sharded.
    shard_count: Optional[:class:`int`]
        The total number of shards, ``None`` when the client is not sharded.
    reconnect: :class:`bool`
        Whether the transport restores a lost connection. Set by the owner before
        :meth:`connect`.
    on_disconnect: Callable[[], None]
        Called each time the connection is lost. Set by the owner before :meth:`connect`.
    """

    def __init__(
        self, shard_id: int | None = None, shard_count: int | None = None
    ) -> None:
        self.shard_id: int | None = shard_id
        self.shard_count: int | None = shard_count
        self.reconnect: bool = True
        self.on_disconnect: Callable[[], None] = _ignore

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish the connection, returning once events can be read."""

    @abc.abstractmethod
    def events(self) -> AsyncIterator[GatewayEvent]:
        """Iterate over the ``DISPATCH`` events, including ``READY`` and ``RESUMED``.

        The iteration ends when the transport is closed. A fatal error is raised
        from the iteration.
        """

    @abc.abstractmethod
    async def send(self, op: int, d: Any) -> None:
        """Send a command to the gateway, waiting for the outbound rate limit."""

    @abc.abstractmethod
    async def close(self, code: int = 1000) -> None:
        """Close the connection."""

    @property
    @abc.abstractmethod
    def latency(self) -> float:
        """The heartbeat latency in seconds, ``inf`` before the first one and ``nan`` when not connected."""

    @abc.abstractmethod
    def is_ratelimited(self) -> bool:
        """Whether no command can be sent right now."""

    @abc.abstractmethod
    def is_closed(self) -> bool:
        """Whether the connection is currently closed."""

    async def change_presence(
        self,
        *,
        activity: BaseActivity | None = None,
        status: str | None = None,
        since: float = 0.0,
    ) -> None:
        """Send a Presence Update."""
        if activity is not None:
            if not isinstance(cast("object", activity), BaseActivity):
                raise InvalidArgument("activity must derive from BaseActivity.")
            activities = [activity.to_dict()]
        else:
            activities = []

        if status == "idle":
            since = int(time.time() * 1000)

        _log.debug("Changing the presence to %s with %s", status, activities)
        await self.send(
            Opcode.PRESENCE,
            {
                "activities": activities,
                "afk": False,
                "since": since,
                "status": status,
            },
        )

    async def request_chunks(
        self,
        guild_id: int,
        query: str | None = None,
        *,
        limit: int,
        user_ids: list[int] | None = None,
        presences: bool = False,
        nonce: str | None = None,
    ) -> None:
        """Send a Request Guild Members."""
        data: dict[str, Any] = {
            "guild_id": guild_id,
            "presences": presences,
            "limit": limit,
        }

        if nonce:
            data["nonce"] = nonce

        if user_ids:
            data["user_ids"] = user_ids

        if query is not None:
            data["query"] = query

        await self.send(Opcode.REQUEST_MEMBERS, data)

    async def voice_state(
        self,
        guild_id: int,
        channel_id: int | None,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> None:
        """Send a Voice State Update."""
        data = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "self_mute": self_mute,
            "self_deaf": self_deaf,
        }

        _log.debug("Updating our voice state to %s.", data)
        await self.send(Opcode.VOICE_STATE, data)

    async def request_soundboard_sounds(self, guild_ids: Sequence[int]) -> None:
        """Send a Request Soundboard Sounds."""
        _log.debug("Requesting soundboard sounds for guilds %s.", guild_ids)
        await self.send(
            Opcode.REQUEST_SOUNDBOARD_SOUNDS, {"guild_ids": list(guild_ids)}
        )

    async def request_channel_info(
        self,
        guild_id: int,
        fields: Sequence[Literal["status", "voice_start_time"]],
    ) -> None:
        """Send a Request Channel Info, Discord answers with a ``CHANNEL_INFO`` event."""
        _log.debug("Requesting %s of the channels of guild %s.", fields, guild_id)
        await self.send(
            Opcode.REQUEST_CHANNEL_INFO,
            {"guild_id": guild_id, "fields": list(fields)},
        )


GatewayTransportFactory = Callable[[int | None, int | None], GatewayTransport]


class _GatewayClosed(Exception):
    """The transport was closed and has nothing more to deliver."""


class DiscordGatewayTransport(GatewayTransport):
    """A transport connected directly to the Discord gateway.

    It identifies, resumes on the ``resume_gateway_url``, restarts a new session
    when Discord asks for it and reconnects with an exponential backoff.
    """

    def __init__(
        self,
        client: Client,
        shard_id: int | None = None,
        shard_count: int | None = None,
        *,
        initial: bool = True,
        gateway_url: str | None = None,
        identify_limiter: IdentifyLimiter | None = None,
    ) -> None:
        super().__init__(shard_id, shard_count)
        self._client: Client = client
        self._initial: bool = initial
        self._gateway_url: str | None = gateway_url
        self._identify_limiter: IdentifyLimiter = identify_limiter or IdentifyLimiter()
        self._ws: DiscordWebSocket | None = None
        self._pending: deque[GatewayEvent] = deque()
        self._backoff: ExponentialBackoff[bool] = ExponentialBackoff()
        self._closed: bool = False
        self._resume: bool = False

    @property
    def ws(self) -> DiscordWebSocket | None:
        """The websocket currently in use."""
        return self._ws

    @property
    def latency(self) -> float:
        """The heartbeat latency in seconds, ``inf`` before the first one and ``nan`` when not connected."""
        ws = self._ws
        return float("nan") if ws is None else ws.latency

    def is_ratelimited(self) -> bool:
        """Whether no command can be sent right now."""
        ws = self._ws
        return False if ws is None else ws.is_ratelimited()

    def is_closed(self) -> bool:
        """Whether the connection is currently closed."""
        ws = self._ws
        return ws is None or not ws.open

    async def send(self, op: int, d: Any) -> None:
        """Send a command to the gateway, waiting for the outbound rate limit."""
        ws = self._ws
        if ws is None:
            raise ClientException("The gateway transport is not connected.")
        await ws.send_as_json({"op": int(op), "d": d})

    async def connect(self) -> None:
        """Connect and identify, starting a new session."""
        self._closed = False
        self._resume = False
        self._ws = None
        try:
            await self._establish(180.0)
        except _GatewayClosed:
            return

    async def close(self, code: int = 1000) -> None:
        """Close the websocket, the iteration of :meth:`events` ends."""
        self._closed = True
        ws = self._ws
        if ws is not None and ws.open:
            await ws.close(code=code)

    async def events(self) -> AsyncIterator[GatewayEvent]:
        """Iterate over the ``DISPATCH`` events, reconnecting when the connection drops."""
        while True:
            ws = self._ws
            if ws is None:
                return
            error: BaseException | None = None
            try:
                await ws.poll_event()
            except _POLL_ERRORS as exc:
                error = exc

            while self._pending:
                yield self._pending.popleft()

            if error is None:
                continue

            try:
                if isinstance(error, ReconnectWebSocket):
                    self._on_reconnect_requested(error)
                else:
                    await self._on_failure(error)
                await self._establish(60.0)
            except _GatewayClosed:
                return

    async def _establish(self, timeout: float) -> None:
        while True:
            if self._is_closing():
                raise _GatewayClosed
            try:
                self._ws = await self._open(timeout)
            except ReconnectWebSocket as exc:
                self._on_reconnect_requested(exc)
            except _HANDLED_ERRORS as exc:
                await self._on_failure(exc)
            else:
                return

    async def _open(self, timeout: float) -> DiscordWebSocket:
        previous = self._ws
        resume_gateway_url = None if previous is None else previous.resume_gateway_url
        if (
            self._resume
            and previous is not None
            and previous.session_id is not None
            and resume_gateway_url is not None
        ):
            _log.info(
                "Shard ID %s resumes its session on %s.",
                self.shard_id,
                resume_gateway_url,
            )
            coro = DiscordWebSocket.from_client(
                self._client,
                gateway=resume_url(previous.gateway, resume_gateway_url),
                shard_id=self.shard_id,
                shard_count=self.shard_count,
                session=previous.session_id,
                sequence=previous.sequence,
                resume=True,
                resume_gateway_url=resume_gateway_url,
                event_sink=self._pending.append,
            )
            return await asyncio.wait_for(coro, timeout=timeout)

        gateway, self._gateway_url = self._gateway_url, None
        if gateway is None:
            gateway = await self._client.http.get_gateway(
                compress=self._client._gateway_compression
            )
        async with self._identify_limiter.slot(self.shard_id):
            coro = DiscordWebSocket.from_client(
                self._client,
                initial=self._initial,
                gateway=gateway,
                shard_id=self.shard_id,
                shard_count=self.shard_count,
                event_sink=self._pending.append,
            )
            ws = await asyncio.wait_for(coro, timeout=timeout)
        self._initial = False
        return ws

    def _is_closing(self) -> bool:
        return self._closed or self._client.is_closed()

    def _stop_heartbeat(self) -> None:
        if self._ws is not None:
            self._ws._stop_keep_alive()

    def _on_reconnect_requested(self, exc: ReconnectWebSocket) -> None:
        _log.info("Got a request to %s the websocket.", exc.op)
        self._stop_heartbeat()
        self.on_disconnect()
        self._resume = exc.resume
        if self._is_closing():
            raise _GatewayClosed

    async def _on_failure(self, exc: BaseException) -> None:
        self._stop_heartbeat()
        self.on_disconnect()

        if self._is_closing():
            raise _GatewayClosed

        if not self.reconnect:
            if isinstance(exc, ConnectionClosed) and exc.code == 1000:
                raise _GatewayClosed
            raise exc

        if isinstance(exc, OSError) and exc.errno in _CONNECTION_RESET_ERRNOS:
            self._resume = True
            return

        if isinstance(exc, ConnectionClosed):
            if exc.code == 4014:
                raise PrivilegedIntentsRequired(exc.shard_id) from None
            if exc.code == 4004:
                raise LoginFailure("Improper token has been passed.") from None
            if exc.code != 1000:
                raise exc

        retry = self._backoff.delay()
        _log.error(
            "Attempting a reconnect for shard ID %s in %.2fs",
            self.shard_id,
            retry,
            exc_info=exc,
        )
        await asyncio.sleep(retry)
        self._resume = True
