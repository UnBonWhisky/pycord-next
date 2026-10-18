"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from .client import Client
from .enums import Status
from .errors import ClientException
from .gateway import ShardManager
from .state import AutoShardedConnectionState

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Sequence

    from .activity import ActivityTypes, BaseActivity
    from .gateway import GatewayInfo, GatewayTransport

__all__ = (
    "AutoShardedClient",
    "ShardInfo",
)

_log = logging.getLogger(__name__)


class ShardInfo:
    """A class that gives information and control over a specific shard.

    You can retrieve this object via :meth:`AutoShardedClient.get_shard`
    or :attr:`AutoShardedClient.shards`.

    .. versionadded:: 1.4

    Attributes
    ----------
    id: :class:`int`
        The shard ID for this shard.
    shard_count: Optional[:class:`int`]
        The shard count for this cluster. If this is ``None`` then the bot has not started yet.
    """

    __slots__ = ("_manager", "_parent", "id", "shard_count")

    def __init__(
        self,
        manager: ShardManager,
        parent: GatewayTransport,
        shard_count: int | None,
    ) -> None:
        self._manager: ShardManager = manager
        self._parent: GatewayTransport = parent
        self.id: int = cast("int", parent.shard_id)
        self.shard_count: int | None = shard_count

    def is_closed(self) -> bool:
        """Whether the shard connection is currently closed."""
        return self._parent.is_closed()

    async def disconnect(self) -> None:
        """|coro|

        Disconnects a shard. When this is called, the shard connection will no
        longer be open.

        If the shard is already disconnected this does nothing.
        """
        if self.is_closed():
            return

        await self._manager.disconnect_shard(self.id)

    async def reconnect(self) -> None:
        """|coro|

        Disconnects and then connects the shard again.
        """
        await self._manager.reconnect_shard(self.id)

    async def connect(self) -> None:
        """|coro|

        Connects a shard. If the shard is already connected this does nothing.
        """
        if not self.is_closed():
            return

        await self._manager.connect_shard(self.id)

    @property
    def latency(self) -> float:
        """Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds for this shard.

        If no heartbeat has been received yet this returns ``float('inf')``.
        """
        return self._parent.latency

    def is_ws_ratelimited(self) -> bool:
        """Whether the websocket is currently rate limited.

        This can be useful to know when deciding whether you should query members
        using HTTP or via the gateway.

        .. versionadded:: 1.6
        """
        return self._parent.is_ratelimited()


class AutoShardedClient(Client):
    """A client similar to :class:`Client` except it handles the complications of sharding.

    It turns the sharding of a bot into a more manageable and transparent single
    process bot.

    When using this client, you will be able to use it as-if it was a regular
    :class:`Client` with a single shard when implementation wise internally it
    is split up into multiple shards. This allows you to not have to deal with
    IPC or other complicated infrastructure.

    It is recommended to use this client only if you have surpassed at least
    1000 guilds.

    If no :attr:`Client.shard_count` is provided, then the library will use the
    Bot Gateway endpoint call to figure out how many shards to use.

    If a ``shard_ids`` parameter is given, then those shard IDs will be used
    to launch the internal shards. Note that :attr:`Client.shard_count` must be provided
    if this is used. By default, when omitted, the client will launch shards from
    0 to ``shard_count - 1``.

    Attributes
    ----------
    shard_ids: Optional[List[:class:`int`]]
        An optional list of shard_ids to launch the shards with.
    """

    if TYPE_CHECKING:
        _connection: AutoShardedConnectionState  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(
        self,
        *args: Any,
        loop: asyncio.AbstractEventLoop | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("shard_id", None)
        self.shard_ids: list[int] | None = kwargs.pop("shard_ids", None)
        super().__init__(*args, loop=loop, **kwargs)

        if self.shard_ids is not None:
            if self.shard_count is None:
                raise ClientException(
                    "When passing manual shard_ids, you must provide a shard_count."
                )
            if not isinstance(self.shard_ids, (list, tuple)):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ClientException("shard_ids parameter must be a list or a tuple.")

    def _get_state(self, **options: Any) -> AutoShardedConnectionState:
        return AutoShardedConnectionState(
            dispatch=self.dispatch,
            handlers=self._handlers,
            hooks=self._hooks,
            http=self.http,
            loop=self.loop,
            **options,
        )

    @property
    def latency(self) -> float:
        """Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds.

        This operates similarly to :meth:`Client.latency` except it uses the average
        latency of every shard's latency. To get a list of shard latency, check the
        :attr:`latencies` property. Returns ``nan`` if there are no shards ready.
        """
        latencies = self.latencies
        if not latencies:
            return float("nan")
        return sum(latency for _, latency in latencies) / len(latencies)

    @property
    def latencies(self) -> list[tuple[int, float]]:
        """A list of latencies between a HEARTBEAT and a HEARTBEAT_ACK in seconds.

        This returns a list of tuples with elements ``(shard_id, latency)``.
        """
        manager = self._shard_manager
        return [] if manager is None else manager.latencies

    def get_shard(self, shard_id: int) -> ShardInfo | None:
        """Gets the shard information at a given shard ID or ``None`` if not found."""
        manager = self._shard_manager
        if manager is None:
            return None
        try:
            parent = manager.transports[shard_id]
        except KeyError:
            return None
        else:
            return ShardInfo(manager, parent, self.shard_count)

    @property
    def shards(self) -> dict[int, ShardInfo]:
        """Returns a mapping of shard IDs to their respective info object."""
        manager = self._shard_manager
        if manager is None:
            return {}
        return {
            shard_id: ShardInfo(manager, parent, self.shard_count)
            for shard_id, parent in manager.transports.items()
        }

    def _gateway_shards(
        self, info: GatewayInfo | None
    ) -> tuple[int | None, Sequence[int | None]]:
        if self.shard_count is None:
            if info is None:
                raise ClientException("shard_count is required with a custom gateway.")
            self.shard_count = info.shards

        self._connection.shard_count = self.shard_count

        shard_ids = self.shard_ids or range(self.shard_count)
        self._connection.shard_ids = shard_ids
        return self.shard_count, list(shard_ids)

    def _create_shard_manager(
        self, shard_count: int | None, shard_ids: Sequence[int | None]
    ) -> ShardManager:
        return ShardManager(
            self._gateway_factory or self._default_transport,
            shard_ids=shard_ids,
            shard_count=shard_count,
            identify_limiter=self._identify_limiter,
            dispatch=self.dispatch,
            sharded=True,
            on_launched=self._connection.shards_launched.set,
        )

    async def change_presence(
        self,
        *,
        activity: BaseActivity | None = None,
        status: Status | None = None,
        shard_id: int | None = None,
    ) -> None:
        """|coro|

        Changes the client's presence.

        Example: ::

            game = discord.Game("with the API")
            await client.change_presence(status=discord.Status.idle, activity=game)

        .. versionchanged:: 2.0
            Removed the ``afk`` keyword-only parameter.

        Parameters
        ----------
        activity: Optional[:class:`BaseActivity`]
            The activity being done. ``None`` if no currently active activity is done.
        status: Optional[:class:`Status`]
            Indicates what status to change to. If ``None``, then
            :attr:`Status.online` is used.
        shard_id: Optional[:class:`int`]
            The shard_id to change the presence to. If not specified
            or ``None``, then it will change the presence of every
            shard the bot can see.

        Raises
        ------
        InvalidArgument
            If the ``activity`` parameter is not of proper type.
        """
        if status is None:
            status_value = "online"
            status_enum = Status.online
        elif status is Status.offline:
            status_value = "invisible"
            status_enum = Status.offline
        else:
            status_enum = status
            status_value = str(status)

        if shard_id is None:
            manager = self._shard_manager
            transports: list[GatewayTransport] = (
                [] if manager is None else list(manager.transports.values())
            )
            for transport in transports:
                await transport.change_presence(activity=activity, status=status_value)

            guilds = await self._connection.get_guilds()
        else:
            await self._get_websocket(shard_id=shard_id).change_presence(
                activity=activity, status=status_value
            )
            guilds = [
                g for g in await self._connection.get_guilds() if g.shard_id == shard_id
            ]

        activities: tuple[ActivityTypes, ...] = (
            () if activity is None else (cast("ActivityTypes", activity),)
        )
        for guild in guilds:
            me = await guild.get_me()
            if me is None:
                continue

            # Member.activities is typehinted as Tuple[ActivityType, ...],
            # we may be setting it as Tuple[BaseActivity, ...]
            me.activities = activities
            me.status = status_enum
            await guild._add_member(me)

    def is_ws_ratelimited(self) -> bool:
        """Whether the websocket is currently rate limited.

        This can be useful to know when deciding whether you should query members
        using HTTP or via the gateway.

        This implementation checks if any of the shards are rate limited.
        For more granular control, consider :meth:`ShardInfo.is_ws_ratelimited`.

        .. versionadded:: 1.6
        """
        return super().is_ws_ratelimited()
