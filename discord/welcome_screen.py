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

from typing import TYPE_CHECKING, Any, cast, overload

from ._internal.cache_peek import cached_emoji
from .object import Object
from .partial_emoji import PartialEmoji, _EmojiTag
from .utils import _get_as_snowflake

if TYPE_CHECKING:
    from typing_extensions import Self

    from .abc import GuildChannel, Snowflake
    from .emoji import AppEmoji, GuildEmoji
    from .guild import Guild, PartialGuild
    from .state import ConnectionState
    from .types.welcome_screen import (
        WelcomeScreen as WelcomeScreenPayload,
        WelcomeScreenChannel as WelcomeScreenChannelPayload,
    )

__all__ = (
    "WelcomeScreen",
    "WelcomeScreenChannel",
)


class WelcomeScreenChannel:
    """Represents a welcome channel displayed on :class:`WelcomeScreen`

    .. versionadded:: 2.0

    Attributes
    ----------
    channel: :class:`abc.Snowflake`
        The channel that is being referenced.
    description: :class:`str`
        The description of the channel that is shown on the welcome screen.
    emoji: Union[:class:`GuildEmoji`, :class:`PartialEmoji`, :class:`str`]
        The emoji of the channel that is shown on welcome screen.
    """

    def __init__(
        self,
        channel: Snowflake,
        description: str,
        emoji: GuildEmoji | AppEmoji | PartialEmoji | str | None,
    ) -> None:
        self._channel = channel
        self.description = description
        self._emoji = emoji
        self._state: ConnectionState | None = None
        self._guild_id: int | None = None

    @property
    def channel(self) -> Snowflake:
        """The channel that is being referenced.

        This is the cached :class:`~discord.abc.GuildChannel` when it is in the
        in-process cache, otherwise the :class:`Object` (or the snowflake) the
        object was built with. Use :meth:`get_channel` with any cache backend.
        """
        state, guild_id = self._state, self._guild_id
        if state is None or guild_id is None or not state.cache.supports_sync:
            return self._channel
        return (
            state._guild_bucket("channels", guild_id).get_nowait(self._channel.id)
            or self._channel
        )

    @channel.setter
    def channel(self, value: Snowflake) -> None:
        self._channel = value

    @property
    def emoji(self) -> GuildEmoji | AppEmoji | PartialEmoji | str | None:
        """The emoji of the channel that is shown on welcome screen.

        A custom emoji that is in the in-process cache is the cached
        :class:`GuildEmoji`, otherwise it is the :class:`PartialEmoji`.
        Use :meth:`get_emoji` with any cache backend.
        """
        emoji = self._emoji
        emoji_id = getattr(emoji, "id", None)
        if self._state is None or not emoji_id:
            return emoji
        return cached_emoji(self._state, emoji_id) or emoji

    @emoji.setter
    def emoji(self, value: GuildEmoji | AppEmoji | PartialEmoji | str | None) -> None:
        self._emoji = value

    def __repr__(self) -> str:
        return f"WelcomeScreenChannel(channel={self.channel} description={self.description})"

    def to_dict(self) -> WelcomeScreenChannelPayload:
        """Convert this object to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The payload.
        """
        dict_: WelcomeScreenChannelPayload = {
            "channel_id": self._channel.id,
            "description": self.description,
            "emoji_id": None,
            "emoji_name": None,
        }

        if isinstance(self._emoji, _EmojiTag):
            # custom guild emoji
            dict_["emoji_id"] = self._emoji.id
            dict_["emoji_name"] = self._emoji.name
        else:
            # unicode emoji or None
            dict_["emoji_name"] = self._emoji
            dict_["emoji_id"] = None

        return dict_

    async def get_channel(self) -> GuildChannel | Snowflake:
        """|coro|

        Returns the channel that is being referenced.

        .. versionadded:: 3.0

        Returns
        -------
        Union[:class:`~discord.abc.GuildChannel`, :class:`Snowflake`]
            The cached channel, or :attr:`channel` if it is not cached.
        """
        if self._state is None or self._guild_id is None:
            return self._channel
        channels = self._state._guild_bucket("channels", self._guild_id)
        return await channels.get(self._channel.id) or self._channel

    async def get_emoji(self) -> GuildEmoji | AppEmoji | PartialEmoji | str | None:
        """|coro|

        Returns the emoji of the channel that is shown on welcome screen.

        .. versionadded:: 3.0

        Returns
        -------
        Union[:class:`GuildEmoji`, :class:`PartialEmoji`, :class:`str`]
            The cached emoji if there is one, else :attr:`emoji`.
        """
        emoji_id = getattr(self._emoji, "id", None)
        if self._state is None or not emoji_id:
            return self._emoji
        return await self._state.get_emoji(emoji_id) or self._emoji

    @classmethod
    def _from_dict(
        cls, data: WelcomeScreenChannelPayload, guild: Guild | PartialGuild
    ) -> WelcomeScreenChannel:
        channel_id = _get_as_snowflake(data, "channel_id")
        channel = Object(cast("int", channel_id))
        description = data.get("description")
        _emoji_id = _get_as_snowflake(data, "emoji_id")
        _emoji_name = data.get("emoji_name")

        emoji = (
            PartialEmoji(name=_emoji_name, id=_emoji_id) if _emoji_id else _emoji_name
        )
        welcome_channel = cls(channel=channel, description=description, emoji=emoji)
        welcome_channel._state = guild._state
        welcome_channel._guild_id = guild.id
        return welcome_channel


class WelcomeScreen:
    """Represents the welcome screen of a guild.

    .. versionadded:: 2.0

    Attributes
    ----------
    description: :class:`str`
        The description text displayed on the welcome screen.
    welcome_channels: List[:class:`WelcomeScreenChannel`]
        A list of channels displayed on welcome screen.
    """

    def __init__(self, data: WelcomeScreenPayload, guild: Guild | PartialGuild) -> None:
        self._guild = guild
        self._update(data)

    def __repr__(self) -> str:
        return (
            "<WelcomeScreen"
            f" description={self.description} welcome_channels={self.welcome_channels}"
        )

    def _update(self, data: WelcomeScreenPayload) -> None:
        self.description: str = data.get("description")
        self.welcome_channels: list[WelcomeScreenChannel] = [
            WelcomeScreenChannel._from_dict(channel, self._guild)
            for channel in data.get("welcome_channels", [])
        ]

    @property
    def enabled(self) -> bool:
        """Indicates whether the welcome screen is enabled or not.

        This reads the in-memory cache, use :meth:`get_enabled` with any cache backend.
        """
        guild = self.guild
        return guild is not None and "WELCOME_SCREEN_ENABLED" in guild.features

    async def get_enabled(self) -> bool:
        """|coro|

        Indicates whether the welcome screen is enabled or not.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`bool`
            Whether the welcome screen is enabled. ``False`` if the guild is not
            cached.
        """
        guild = await self.get_guild()
        return guild is not None and "WELCOME_SCREEN_ENABLED" in guild.features

    @property
    def guild(self) -> Guild | None:
        """The guild this welcome screen belongs to.

        This reads the in-memory cache, use :meth:`get_guild` with any cache backend.
        """
        if hasattr(self._guild, "features"):
            return cast("Guild", self._guild)
        return self._guild._state._guilds.get_nowait(self._guild.id)

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the guild this welcome screen belongs to.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`Guild`]
            The guild, or ``None`` if it is not cached.
        """
        if hasattr(self._guild, "features"):
            return cast("Guild", self._guild)
        return await self._guild._state._get_guild(self._guild.id)

    @overload
    async def edit(
        self,
        *,
        description: str | None = ...,
        welcome_channels: list[WelcomeScreenChannel] | None = ...,
        enabled: bool | None = ...,
        reason: str | None = ...,
    ) -> Self: ...

    @overload
    async def edit(self) -> Self: ...

    async def edit(self, **options: Any) -> Self:
        """|coro|

        Edits the welcome screen.

        You must have the :attr:`~Permissions.manage_guild` permission in the
        guild to do this.

        Parameters
        ----------
        description: Optional[:class:`str`]
            The new description of welcome screen.
        welcome_channels: Optional[List[:class:`WelcomeScreenChannel`]]
            The welcome channels. The order of the channels would be same as the passed list order.
        enabled: Optional[:class:`bool`]
            Whether the welcome screen should be displayed.
        reason: Optional[:class:`str`]
            The reason that shows up on Audit log.

        Raises
        ------
        HTTPException
            Editing the welcome screen failed somehow.
        Forbidden
            You don't have permissions to edit the welcome screen.
        NotFound
            This welcome screen does not exist.

        Example
        -------
        .. code-block:: python3

            rules_channel = await guild.get_channel(12345678)
            announcements_channel = await guild.get_channel(87654321)
            custom_emoji = utils.get(await guild.get_emojis(), name="loudspeaker")
            await welcome_screen.edit(
                description="This is a very cool community server!",
                welcome_channels=[
                    WelcomeChannel(
                        channel=rules_channel,
                        description="Read the rules!",
                        emoji="👨‍🏫",
                    ),
                    WelcomeChannel(
                        channel=announcements_channel,
                        description="Watch out for announcements!",
                        emoji=custom_emoji,
                    ),
                ],
            )

        .. note::
            Welcome channels can only accept custom emojis if :attr:`~Guild.premium_tier` is level 2 or above.
        """
        welcome_channels: list[Any] = options.get("welcome_channels", [])
        welcome_channels_data: list[WelcomeScreenChannelPayload] = []

        for channel in welcome_channels:
            if not isinstance(channel, WelcomeScreenChannel):
                raise TypeError(
                    "welcome_channels parameter must be a list of WelcomeScreenChannel."
                )

            welcome_channels_data.append(channel.to_dict())

        options["welcome_channels"] = welcome_channels_data

        if options:
            new = await self._guild._state.http.edit_welcome_screen(
                self._guild.id, options, reason=options.get("reason")
            )
            self._update(new)

        return self
