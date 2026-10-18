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

"""Connection state for automatically sharded clients."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
from typing import TYPE_CHECKING, Any, cast

from .. import utils
from ..flags import ApplicationFlags
from ..user import ClientUser
from .state import ConnectionState

if TYPE_CHECKING:
    from ..guild import Guild
    from ..user import User

_log = logging.getLogger(__name__)


class AutoShardedConnectionState(ConnectionState):
    """Connection state shared by every shard of an auto sharded client."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.shard_ids: list[int] | range = []
        self.shards_launched: asyncio.Event = asyncio.Event()

    async def chunker(
        self,
        guild_id: int,
        query: str = "",
        limit: int = 0,
        presences: bool = False,
        *,
        shard_id: int | None = None,
        nonce: str | None = None,
    ) -> None:
        """Send a member chunk request for a guild."""
        ws = self._get_websocket(guild_id, shard_id=shard_id)
        await ws.request_chunks(
            guild_id, query=query, limit=limit, presences=presences, nonce=nonce
        )

    async def _wait_for_bucket(
        self,
        guild: Guild,
        current_bucket: list[asyncio.Future[Any]],
        max_chunk_requests: int,
    ) -> None:
        try:
            await utils.sane_wait_for(current_bucket, timeout=max_chunk_requests * 70.0)
        except asyncio.TimeoutError:
            fmt = (
                "Shard ID %s failed to wait for chunks from a sub-bucket with length %d"
            )
            _log.warning(fmt, guild.shard_id, len(current_bucket))

    async def _wait_for_shard_chunks(
        self,
        shard_id: int,
        futures: tuple[asyncio.Future[Any], ...],
        timeout: float,
        guild_count: int,
    ) -> None:
        try:
            done = await utils.sane_wait_for(futures, timeout=timeout)
            for future in done:
                if not future.cancelled():
                    future.exception()
        except asyncio.TimeoutError:
            _log.warning(
                ("Shard ID %s failed to wait for chunks (timeout=%.2f) for %d guilds"),
                shard_id,
                timeout,
                guild_count,
            )

    async def _get_ready_guild(self) -> Guild | None:
        try:
            return await asyncio.wait_for(
                self._ready_state.get(), timeout=self.guild_ready_timeout
            )
        except asyncio.TimeoutError:
            return None

    async def _delay_ready(self) -> None:
        await self.shards_launched.wait()
        processed: list[tuple[Guild, asyncio.Future[Any]]] = []
        max_chunk_requests = len(self.shard_ids) * 2
        current_bucket: list[asyncio.Future[Any]] = []
        while True:
            # this snippet of code is basically waiting N seconds
            # until the last GUILD_CREATE was sent
            guild = await self._get_ready_guild()
            if guild is None:
                break

            if await self._guild_needs_chunking(guild):
                _log.debug(
                    ("Guild ID %d requires chunking, will be done in the background."),
                    guild.id,
                )
                if len(current_bucket) >= max_chunk_requests:
                    await self._wait_for_bucket(
                        guild, current_bucket, max_chunk_requests
                    )
                    current_bucket = []

                # Chunk the guild in the background while we wait for GUILD_CREATE streaming
                future: asyncio.Future[Any] = asyncio.ensure_future(
                    self.chunk_guild(guild)
                )
                current_bucket.append(future)
            else:
                future = self.loop.create_future()
                future.set_result([])

            if self.cache_channel_info:
                info_task = asyncio.ensure_future(
                    self.request_guild_channel_info(guild)
                )
                future = asyncio.gather(future, info_task, return_exceptions=True)

            processed.append((guild, future))

        guilds = sorted(processed, key=lambda g: g[0].shard_id)
        for shard_id, info in itertools.groupby(guilds, key=lambda g: g[0].shard_id):
            children, futures = zip(*info, strict=True)
            # 110 reqs/minute w/ 1 req/guild plus some buffer
            timeout = 61 * (len(children) / 110)
            await self._wait_for_shard_chunks(shard_id, futures, timeout, len(guilds))
            for guild in children:
                if guild.unavailable is False:
                    self.dispatch("guild_available", guild)
                else:
                    self.dispatch("guild_join", guild)

            self.dispatch("shard_ready", shard_id)

        if self.cache_app_emojis and self.application_id:
            data = await self.http.get_all_application_emojis(self.application_id)
            for e in data.get("items", []):
                await self.maybe_store_app_emoji(self.application_id, e)

        # remove the state
        with contextlib.suppress(AttributeError):
            del self._ready_state  # already been deleted somehow

        # clear the current task
        self._ready_task = None

        # dispatch the event
        self.call_handlers("ready")
        self.dispatch("ready")

    async def parse_ready(self, data: dict[str, Any]) -> None:
        """Handle the ``READY`` gateway event for a shard."""
        if not hasattr(self, "_ready_state"):
            self._ready_state = asyncio.Queue()

        self.user = user = ClientUser(state=self, data=data["user"])
        # self._users is a list of Users, we're setting a ClientUser
        await self._users.set(user.id, cast("User", user))

        if self.application_id is None:
            try:
                application = data["application"]
            except KeyError:
                pass
            else:
                self.application_id = utils._get_as_snowflake(application, "id")
                self.application_flags = ApplicationFlags._from_value(
                    application["flags"]
                )

        for guild_data in data["guilds"]:
            await self._add_guild_from_data(guild_data)

        self.dispatch("connect")
        self.dispatch("shard_connect", data["__shard_id__"])

        if self._ready_task is None:
            self._ready_task = asyncio.create_task(self._delay_ready())

    async def parse_resumed(self, data: dict[str, Any]) -> None:
        """Handle the ``RESUMED`` gateway event for a shard."""
        self.dispatch("resumed")
        self.dispatch("shard_resumed", data["__shard_id__"])
