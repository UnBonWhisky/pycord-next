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

from typing import TYPE_CHECKING, Any, cast

from .enums import ChannelType, StagePrivacyLevel, try_enum
from .errors import InvalidArgument
from .mixins import Hashable
from .utils import MISSING

__all__ = ("StageInstance",)

if TYPE_CHECKING:
    from .channel import PartialGuildChannel, StageChannel
    from .guild import Guild, PartialGuild
    from .scheduled_events import ScheduledEvent
    from .state import ConnectionState
    from .types.channel import StageInstance as StageInstancePayload


class StageInstance(Hashable):
    """Represents a stage instance of a stage channel in a guild.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: x == y

            Checks if two stage instances are equal.

        .. describe:: x != y

            Checks if two stage instances are not equal.

        .. describe:: hash(x)

            Returns the stage instance's hash.

    Attributes
    ----------
    id: :class:`int`
        The stage instance's ID.
    guild_id: :class:`int`
        The ID of the guild that the stage instance is running in.
    channel_id: :class:`int`
        The ID of the channel that the stage instance is running in.
    topic: :class:`str`
        The topic of the stage instance.
    privacy_level: :class:`StagePrivacyLevel`
        The privacy level of the stage instance.
    discoverable_disabled: :class:`bool`
        Whether discoverability for the stage instance is disabled.
    scheduled_event_id: Optional[:class:`int`]
        The ID of the scheduled event linked with the stage instance, if any.
    """

    __slots__ = (
        "_state",
        "channel_id",
        "discoverable_disabled",
        "guild_id",
        "id",
        "privacy_level",
        "scheduled_event_id",
        "topic",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: StageInstancePayload,
    ) -> None:
        self._state = state
        self.guild_id: int = guild.id
        self._update(data)

    def _update(self, data: StageInstancePayload) -> None:
        self.id: int = int(data["id"])
        self.channel_id: int = int(data["channel_id"])
        self.topic: str = data["topic"]
        self.privacy_level: StagePrivacyLevel = try_enum(
            StagePrivacyLevel, data["privacy_level"]
        )
        self.discoverable_disabled: bool = data.get("discoverable_disabled", False)

        event_id = data.get("guild_scheduled_event_id", None)
        self.scheduled_event_id: int | None = int(event_id) if event_id else None

    def __repr__(self) -> str:
        return (
            "<StageInstance"
            f" id={self.id} guild_id={self.guild_id} channel_id={self.channel_id} topic={self.topic!r}>"
        )

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild that the stage instance is running in.

        This is the cached :class:`Guild` when the in-process cache holds it,
        otherwise a :class:`PartialGuild` handle (always the case with a remote cache backend).
        """
        from .guild import PartialGuild

        state = self._state
        if state.cache.supports_sync:
            guild = state._guilds.get_nowait(self.guild_id)
            if guild is not None:
                return guild
        return PartialGuild(state=state, id=self.guild_id)

    @property
    def channel(self) -> StageChannel | PartialGuildChannel:
        """The stage channel that the stage instance is running in.

        This is the cached channel when the in-process cache holds it,
        otherwise a :class:`PartialGuildChannel` handle (always the case with a remote cache backend).
        """
        from .channel import PartialGuildChannel

        state = self._state
        if state.cache.supports_sync:
            channel = state._guild_bucket("channels", self.guild_id).get_nowait(
                self.channel_id
            )
            if channel is not None:
                return channel
        return PartialGuildChannel(
            state=state,
            id=self.channel_id,
            guild_id=self.guild_id,
            type=ChannelType.stage_voice,
        )

    async def get_channel(self) -> StageChannel | None:
        """|coro|

        Returns the cached stage channel that the stage instance is running in.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`StageChannel`]
            The channel, or ``None`` if it is not cached.
        """
        return await self._state._guild_bucket("channels", self.guild_id).get(
            self.channel_id
        )

    @property
    def scheduled_event(self) -> ScheduledEvent | None:
        """The scheduled event linked with the stage instance, if any.

        This reads the in-process cache and raises :exc:`SyncCacheAccessError`
        with a remote cache backend, use :meth:`get_scheduled_event` instead.
        """
        if self.scheduled_event_id is None:
            return None
        return self._state._guild_bucket("scheduled_events", self.guild_id).get_nowait(
            self.scheduled_event_id
        )

    async def get_scheduled_event(self) -> ScheduledEvent | None:
        """|coro|

        Returns the cached scheduled event this stage instance is linked to, if any.

        Returns
        -------
        Optional[:class:`ScheduledEvent`]
            The scheduled event, or ``None`` if there is none or it is not cached.
        """
        if self.scheduled_event_id is None:
            return None
        return await self._state._guild_bucket("scheduled_events", self.guild_id).get(
            self.scheduled_event_id
        )

    def is_public(self) -> bool:
        """Whether the stage instance is public, always ``False`` since public stages are deprecated.

        Returns
        -------
        :class:`bool`
            Always ``False``.
        """
        return False

    async def edit(
        self,
        *,
        topic: str = MISSING,
        privacy_level: StagePrivacyLevel = MISSING,
        reason: str | None = None,
    ) -> None:
        """|coro|

        Edits the stage instance.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        Parameters
        ----------
        topic: :class:`str`
            The stage instance's new topic.
        privacy_level: :class:`StagePrivacyLevel`
            The stage instance's new privacy level.
        reason: :class:`str`
            The reason the stage instance was edited. Shows up on the audit log.

        Raises
        ------
        InvalidArgument
            If the ``privacy_level`` parameter is not the proper type.
        Forbidden
            You do not have permissions to edit the stage instance.
        HTTPException
            Editing a stage instance failed.
        """
        payload: dict[str, Any] = {}

        if topic is not MISSING:
            payload["topic"] = topic

        if privacy_level is not MISSING:
            level = cast("object", privacy_level)
            if not isinstance(level, StagePrivacyLevel):
                raise InvalidArgument(
                    "privacy_level field must be of type PrivacyLevel"
                )

            payload["privacy_level"] = level.value

        if payload:
            await self._state.http.edit_stage_instance(
                self.channel_id, **payload, reason=reason
            )

    async def delete(self, *, reason: str | None = None) -> None:
        """|coro|

        Deletes the stage instance.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        Parameters
        ----------
        reason: :class:`str`
            The reason the stage instance was deleted. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to delete the stage instance.
        HTTPException
            Deleting the stage instance failed.
        """
        await self._state.http.delete_stage_instance(self.channel_id, reason=reason)
