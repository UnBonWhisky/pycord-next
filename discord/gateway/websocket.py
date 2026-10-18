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

"""The Discord gateway websocket implementing the gateway protocol."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import aiohttp

from .. import utils
from ..errors import ConnectionClosed
from .base import BaseWebSocket, KeepAliveHandler
from .compression import create_inflater
from .models import NEW_SESSION_CLOSE_CODES, NO_RECONNECT_CLOSE_CODES, GatewayEvent
from .ratelimiter import GatewayRatelimiter

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from ..client import Client
    from ..state import ConnectionState
    from .compression import GatewayCompression, Inflater

_log = logging.getLogger(__name__)

__all__ = (
    "DiscordWebSocket",
    "KeepAliveHandler",
    "ReconnectWebSocket",
)


class ReconnectWebSocket(Exception):
    """Signals to safely reconnect the WebSocket."""

    def __init__(self, shard_id: int | None, *, resume: bool = True) -> None:
        self.shard_id: int | None = shard_id
        self.resume: bool = resume
        self.op: str = "RESUME" if resume else "IDENTIFY"


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""


class EventListener(NamedTuple):
    """A pending :meth:`DiscordWebSocket.wait_for`."""

    predicate: Callable[[dict[str, Any]], bool]
    event: str
    result: Callable[[dict[str, Any]], Any] | None
    future: asyncio.Future[Any]


class DiscordClientWebSocketResponse(aiohttp.ClientWebSocketResponse):
    """A websocket response closing with the code 4000 by default."""

    async def close(self, *, code: int = 4000, message: bytes = b"") -> bool:
        """Close the websocket."""
        return await super().close(code=code, message=message)


def _ignore_event(_: GatewayEvent, /) -> None:
    return None


def _ignore_dispatch(*_: Any) -> None:
    return None


class DiscordWebSocket(BaseWebSocket):
    """Implements a WebSocket for Discord's gateway v6.

    Attributes
    ----------
    DISPATCH
        Receive only. Denotes an event to be sent to Discord, such as READY.
    HEARTBEAT
        When received tells Discord to keep the connection alive.
        When sent asks if your connection is currently alive.
    IDENTIFY
        Send only. Starts a new session.
    PRESENCE
        Send only. Updates your presence.
    VOICE_STATE
        Send only. Starts a new connection to a voice guild.
    VOICE_PING
        Send only. Checks ping time to a voice guild, do not use.
    RESUME
        Send only. Resumes an existing connection.
    RECONNECT
        Receive only. Tells the client to reconnect to a new gateway.
    REQUEST_MEMBERS
        Send only. Asks for the full member list of a guild.
    INVALIDATE_SESSION
        Receive only. Tells the client to optionally invalidate the session
        and IDENTIFY again.
    HELLO
        Receive only. Tells the client the heartbeat interval.
    HEARTBEAT_ACK
        Receive only. Confirms receiving of a heartbeat. Not having one implies
        a connection issue.
    GUILD_SYNC
        Send only. Requests a guild sync.
    REQUEST_SOUNDBOARD_SOUNDS
        Send only. Asks for the soundboard sounds of guilds.
    REQUEST_CHANNEL_INFO
        Send only. Asks for the status and voice start time of the channels of a guild.
    gateway
        The gateway we are currently connected to.
    token
        The authentication token for discord.
    """

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE = 3
    VOICE_STATE = 4
    VOICE_PING = 5
    RESUME = 6
    RECONNECT = 7
    REQUEST_MEMBERS = 8
    INVALIDATE_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    GUILD_SYNC = 12
    REQUEST_SOUNDBOARD_SOUNDS = 31
    REQUEST_CHANNEL_INFO = 43

    if TYPE_CHECKING:
        token: str | None
        _connection: ConnectionState
        call_hooks: Callable[..., Any]
        gateway: str
        _initial_identify: bool
        shard_id: int | None
        shard_count: int | None
        capabilities: int

    def __init__(
        self,
        socket: aiohttp.ClientWebSocketResponse,
        *,
        loop: asyncio.AbstractEventLoop,
        compression: GatewayCompression | None = "zlib-stream",
    ) -> None:
        super().__init__(socket, loop=loop)

        # an empty dispatcher to prevent crashes
        self._dispatch: Callable[..., Any] = _ignore_dispatch
        self._event_sink: Callable[[GatewayEvent], None] = _ignore_event
        # generic event listeners
        self._dispatch_listeners: list[EventListener] = []

        # ws related stuff
        self.session_id: str | None = None
        self.resume_gateway_url: str | None = None
        self.compression: GatewayCompression | None = compression
        self.large_threshold: int = 250
        self._inflater: Inflater | None = create_inflater(compression)
        self._rate_limiter: GatewayRatelimiter = GatewayRatelimiter()

    def is_ratelimited(self) -> bool:
        """Whether the outbound rate limit is currently exhausted."""
        return self._rate_limiter.is_ratelimited()

    def debug_log_receive(self, data: dict[str, Any], /) -> None:
        """Dispatch ``socket_raw_receive``."""
        self._dispatch("socket_raw_receive", data)

    def log_receive(self, _: dict[str, Any], /) -> None:
        """Hook called with every received message, enabled by ``enable_debug_events``."""

    @classmethod
    async def from_client(
        cls,
        client: Client,
        *,
        initial: bool = False,
        gateway: str | None = None,
        shard_id: int | None = None,
        shard_count: int | None = None,
        session: str | None = None,
        sequence: int | None = None,
        resume: bool = False,
        resume_gateway_url: str | None = None,
        event_sink: Callable[[GatewayEvent], None] | None = None,
    ) -> Self:
        """Creates a main websocket for Discord from a :class:`Client`.

        This is for internal use only.
        """
        compression = client._gateway_compression
        gateway = gateway or await client.http.get_gateway(compress=compression)
        socket = await client.http.ws_connect(gateway)
        ws = cls(socket, loop=client.loop, compression=compression)

        # dynamically add attributes needed
        ws.token = client.http.token
        ws._connection = client._connection
        ws._event_sink = event_sink or _ignore_event
        ws._dispatch = client.dispatch
        ws.gateway = gateway
        ws.call_hooks = client._connection.call_hooks
        ws._initial_identify = initial
        ws.shard_id = shard_id
        ws._rate_limiter.shard_id = shard_id
        ws.shard_count = (
            client._connection.shard_count if shard_count is None else shard_count
        )
        ws.session_id = session
        ws.sequence = sequence
        ws.resume_gateway_url = resume_gateway_url
        ws.large_threshold = client._large_threshold
        ws._max_heartbeat_timeout = client._connection.heartbeat_timeout
        ws.capabilities = client._connection.capabilities.value

        if client._enable_debug_events:
            patched = cast("Any", ws)
            patched.send = ws.debug_send
            patched.log_receive = ws.debug_log_receive

        client._connection._update_references(ws)

        _log.debug("Created websocket connected to %s", gateway)

        try:
            # poll event for OP Hello
            await ws.poll_event()

            if not resume:
                await ws.identify()
                return ws

            await ws.resume()
        except BaseException:
            ws._stop_keep_alive()
            await socket.close()
            raise
        return ws

    def wait_for(
        self,
        event: str,
        predicate: Callable[[dict[str, Any]], bool],
        result: Callable[[dict[str, Any]], Any] | None = None,
    ) -> asyncio.Future[Any]:
        """Waits for a DISPATCH'd event that meets the predicate.

        Parameters
        ----------
        event: :class:`str`
            The event name in all upper case to wait for.
        predicate
            A function that takes a data parameter to check for event
            properties. The data parameter is the 'd' key in the JSON message.
        result
            A function that takes the same data parameter and executes to send
            the result to the future. If ``None``, returns the data.

        Returns
        -------
        asyncio.Future
            A future to wait for.
        """
        future = self.loop.create_future()
        entry = EventListener(
            event=event, predicate=predicate, result=result, future=future
        )
        self._dispatch_listeners.append(entry)
        return future

    async def identify(self) -> None:
        """Sends the IDENTIFY packet."""
        payload: dict[str, Any] = {
            "op": self.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": {
                    "os": sys.platform,
                    "browser": "pycord",
                    "device": "pycord",
                },
                "large_threshold": self.large_threshold,
                "capabilities": (
                    self.capabilities if hasattr(self, "capabilities") else 0
                ),
            },
        }

        if self.shard_id is not None and self.shard_count is not None:
            payload["d"]["shard"] = [self.shard_id, self.shard_count]

        state = self._connection
        if state._activity is not None or state._status is not None:
            payload["d"]["presence"] = {
                "status": state._status,
                "game": state._activity,
                "since": 0,
                "afk": False,
            }

        payload["d"]["intents"] = state._intents.value

        await self.call_hooks(
            "before_identify", self.shard_id, initial=self._initial_identify
        )
        await self.send_as_json(payload)
        _log.info("Shard ID %s has sent the IDENTIFY payload.", self.shard_id)

    async def resume(self) -> None:
        """Sends the RESUME packet."""
        payload = {
            "op": self.RESUME,
            "d": {
                "seq": self.sequence,
                "session_id": self.session_id,
                "token": self.token,
            },
        }

        await self.send_as_json(payload)
        _log.info("Shard ID %s has sent the RESUME payload.", self.shard_id)

    async def received_message(self, msg: Any, /) -> None:
        """Handle one frame received from the gateway."""
        if type(msg) is bytes:
            if self._inflater is None:
                msg = msg.decode("utf-8")
            else:
                msg = self._inflater.feed(msg)
                if msg is None:
                    return

        self.log_receive(msg)
        msg = utils._from_json(msg)

        _log.debug("For Shard ID %s: WebSocket Event: %s", self.shard_id, msg)
        event = msg.get("t")

        op = msg.get("op")
        data = msg.get("d")
        seq = msg.get("s")
        if seq is not None:
            self.sequence = seq

        if self._keep_alive:
            self._keep_alive.tick()

        if op != self.DISPATCH:
            if op == self.RECONNECT:
                # "reconnect" can only be handled by the Client, so we
                # terminate our connection and raise an
                # internal exception signalling to reconnect.
                _log.debug("Received RECONNECT opcode.")
                await self.close()
                raise ReconnectWebSocket(self.shard_id)

            if op == self.HEARTBEAT_ACK:
                if self._keep_alive:
                    self._keep_alive.ack()
                return

            if op == self.HEARTBEAT:
                if self._keep_alive:
                    beat = self._keep_alive.get_payload()
                    await self.send_as_json(beat)
                return

            if op == self.HELLO:
                interval = data["heartbeat_interval"] / 1000.0
                self._keep_alive = KeepAliveHandler(
                    ws=self, interval=interval, shard_id=self.shard_id
                )
                # send a heartbeat immediately
                await self.send_as_json(self._keep_alive.get_payload())
                self._keep_alive.start()
                return

            if op == self.INVALIDATE_SESSION:
                if data is True:
                    await self.close()
                    raise ReconnectWebSocket(self.shard_id)

                self.sequence = None
                self.session_id = None
                _log.info("Shard ID %s session has been invalidated.", self.shard_id)
                await self.close(code=1000)
                raise ReconnectWebSocket(self.shard_id, resume=False)

            _log.warning("Unknown OP code %s.", op)
            return

        if event == "READY":
            self._trace = trace = data.get("_trace", [])
            self.sequence = msg["s"]
            self.session_id = data["session_id"]
            self.resume_gateway_url = data["resume_gateway_url"]
            _log.info(
                "Shard ID %s has connected to Gateway: %s (Session ID: %s).",
                self.shard_id,
                ", ".join(trace),
                self.session_id,
            )

        elif event == "RESUMED":
            self._trace = trace = data.get("_trace", [])
            _log.info(
                "Shard ID %s has successfully RESUMED session %s under trace %s.",
                self.shard_id,
                self.session_id,
                ", ".join(trace),
            )

        self._event_sink(
            GatewayEvent(op=op, t=event, s=seq, d=data, shard_id=self.shard_id)
        )

        # remove the dispatched listeners
        removed: list[int] = []
        for index, entry in enumerate(self._dispatch_listeners):
            if entry.event != event:
                continue

            future = entry.future
            if future.cancelled():
                removed.append(index)
                continue

            try:
                valid = entry.predicate(data)
            except Exception as exc:
                future.set_exception(exc)
                removed.append(index)
            else:
                if valid:
                    ret = data if entry.result is None else entry.result(data)
                    future.set_result(ret)
                    removed.append(index)

        for index in reversed(removed):
            del self._dispatch_listeners[index]

    def _can_handle_close(self) -> bool:
        code = self._close_code or self.socket.close_code
        is_improper_close = self._close_code is None and self.socket.close_code == 1000
        return is_improper_close or code not in NO_RECONNECT_CLOSE_CODES

    async def poll_event(self) -> None:
        """Polls for a DISPATCH event and handles the general gateway loop.

        Raises
        ------
        ConnectionClosed
            The websocket connection was terminated for unhandled reasons.
        """
        try:
            msg = await self.socket.receive(timeout=self._max_heartbeat_timeout)
            if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                await self.received_message(msg.data)
            elif msg.type is aiohttp.WSMsgType.ERROR:
                _log.debug("Received an error %s", msg)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSE,
            ):
                _log.debug("Received %s", msg)
                raise WebSocketClosure
        except (asyncio.TimeoutError, WebSocketClosure) as e:
            # Ensure the keep alive handler is closed
            self._stop_keep_alive()

            if isinstance(e, asyncio.TimeoutError):
                _log.info("Timed out receiving packet. Attempting a reconnect.")
                raise ReconnectWebSocket(self.shard_id) from None

            code = self._close_code or self.socket.close_code
            if self._can_handle_close():
                _log.info("Websocket closed with %s, attempting a reconnect.", code)
                raise ReconnectWebSocket(
                    self.shard_id, resume=code not in NEW_SESSION_CLOSE_CODES
                ) from None
            _log.info("Websocket closed with %s, cannot reconnect.", code)
            raise ConnectionClosed(
                self.socket, shard_id=self.shard_id, code=code
            ) from None

    async def debug_send(self, data: str, /) -> None:
        """Send a raw string and dispatch ``socket_raw_send``."""
        await self._rate_limiter.block()
        self._dispatch("socket_raw_send", data)
        await self.socket.send_str(data)

    async def send(self, data: str, /) -> None:
        """Send a raw string, waiting for the outbound rate limit."""
        await self._rate_limiter.block()
        await self.socket.send_str(data)

    async def send_as_json(self, data: Any) -> None:
        """Serialize and send a payload."""
        try:
            await self.send(utils._to_json(data))
        except RuntimeError as exc:
            if not self._can_handle_close():
                raise ConnectionClosed(self.socket, shard_id=self.shard_id) from exc

    async def send_heartbeat(self, data: Any) -> None:
        """Send a heartbeat, bypassing the rate limit as it has a higher priority."""
        try:
            await self.socket.send_str(utils._to_json(data))
        except RuntimeError as exc:
            if not self._can_handle_close():
                raise ConnectionClosed(self.socket, shard_id=self.shard_id) from exc

    async def close(self, code: int = 4000) -> None:
        """Close the websocket with a close code."""
        self._stop_keep_alive()

        self._close_code = code
        await self.socket.close(code=code)
