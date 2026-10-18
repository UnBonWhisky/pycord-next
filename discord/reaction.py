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

from typing import TYPE_CHECKING, cast

from ._internal.aliases import AliasMixin
from .colour import Colour
from .enums import ReactionType
from .iterators import ReactionIterator
from .partial_emoji import PartialEmoji
from .utils import _get_as_snowflake

__all__ = ("Reaction", "ReactionCountDetails")

if TYPE_CHECKING:
    from .abc import Snowflake
    from .emoji import AppEmoji, GuildEmoji
    from .message import Message, PartialMessage
    from .state import ConnectionState
    from .types.emoji import PartialEmoji as PartialEmojiPayload
    from .types.message import (
        Reaction as ReactionPayload,
        ReactionCountDetails as ReactionCountDetailsPayload,
    )
    from .types.raw_models import ReactionActionEvent


class Reaction(AliasMixin):
    """Represents a reaction to a message.

    Depending on the way this object was created, some of the attributes can
    have a value of ``None``.

    .. container:: operations

        .. describe:: x == y

            Checks if two reactions are equal. This works by checking if the emoji
            is the same. So two messages with the same reaction will be considered
            "equal".

        .. describe:: x != y

            Checks if two reactions are not equal.

        .. describe:: hash(x)

            Returns the reaction's hash.

        .. describe:: str(x)

            Returns the string form of the reaction's emoji.

    Attributes
    ----------
    emoji: Union[:class:`GuildEmoji`, :class:`AppEmoji`, :class:`PartialEmoji`, :class:`str`]
        The reaction emoji. May be a custom emoji, or a unicode emoji.
    count: :class:`int`
        The combined total of normal and super reactions for this emoji.
    me: :class:`bool`
        If the user sent this as a normal reaction.
    me_burst: :class:`bool`
        If the user sent this as a super reaction.
    message_id: :class:`int`
        The ID of the message this reaction is for.
    channel_id: :class:`int`
        The ID of the channel of the message this reaction is for.
    guild_id: Optional[:class:`int`]
        The ID of the guild of the message this reaction is for, if applicable.
    burst: :class:`bool`
        Whether this reaction is a burst (super) reaction.
    """

    __slots__ = (
        "_burst_colours",
        "_count_details",
        "_state",
        "burst",
        "channel_id",
        "count",
        "emoji",
        "guild_id",
        "me",
        "me_burst",
        "message_id",
    )

    def __init__(
        self,
        *,
        message: Message | PartialMessage,
        data: ReactionPayload | ReactionActionEvent,
        emoji: PartialEmoji | GuildEmoji | AppEmoji | str | None = None,
    ) -> None:
        self._state: ConnectionState = message._state
        self.message_id: int = message.id
        self.channel_id: int = (
            getattr(message, "channel_id", None) or message.channel.id
        )
        guild_id = getattr(message, "guild_id", None)
        if guild_id is None:
            guild_id = getattr(message.guild, "id", None)
        self.guild_id: int | None = guild_id
        self.emoji: PartialEmoji | GuildEmoji | AppEmoji | str = (
            emoji or self._emoji_from_payload(data["emoji"])
        )
        self.count: int = data.get("count", 1)
        self._count_details: ReactionCountDetailsPayload = data.get("count_details", {})
        self.me: bool = data.get("me", False)
        self.burst: bool = data.get("burst", False)
        self.me_burst: bool = data.get("me_burst", False)
        self._burst_colours: list[str] = data.get("burst_colors", [])

    def _emoji_from_payload(self, data: PartialEmojiPayload) -> PartialEmoji | str:
        emoji_id = _get_as_snowflake(data, "id")
        if not emoji_id:
            return cast("str", data["name"])

        return PartialEmoji.with_state(
            self._state,
            animated=data.get("animated", False),
            id=emoji_id,
            name=cast("str", data["name"]),
        )

    @property
    def message(self) -> Message | PartialMessage:
        """The message this reaction is for.

        This is the cached message when it is available in an in-process cache,
        otherwise a :class:`PartialMessage` handle.
        Use :meth:`get_message` to look the cached message up with any cache backend.
        """
        from .channel import PartialMessageable
        from .message import PartialMessage

        state = self._state
        if state._messages is not None and state.cache.supports_sync:
            cached = state._messages.get_nowait(self.message_id)
            if cached is not None:
                return cached
        return PartialMessage(
            channel=PartialMessageable(state=state, id=self.channel_id),
            id=self.message_id,
            guild_id=self.guild_id,
        )

    async def get_message(self) -> Message | None:
        """|coro|

        Returns the cached message this reaction is for.

        Returns
        -------
        Optional[:class:`Message`]
            The message, or ``None`` if it is not cached.
        """
        return await self._state._get_message(self.message_id)

    @property
    def burst_colours(self) -> list[Colour]:
        """Returns a list possible :class:`Colour` this super reaction can be."""
        # We receive a list of #FFFFFF, so omit the # and convert to base 16
        return [Colour(int(c[1:], 16)) for c in self._burst_colours]

    @property
    def count_details(self) -> ReactionCountDetails:
        """Returns :class:`ReactionCountDetails` for the individual counts of normal and super reactions made."""
        return ReactionCountDetails(self._count_details)

    # TODO: typeguard
    def is_custom_emoji(self) -> bool:
        """If this is a custom emoji."""
        return not isinstance(self.emoji, str)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and other.emoji == self.emoji

    def __ne__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return other.emoji != self.emoji
        return True

    def __hash__(self) -> int:
        return hash(self.emoji)

    def __str__(self) -> str:
        return str(self.emoji)

    def __repr__(self) -> str:
        return f"<Reaction emoji={self.emoji!r} me={self.me} count={self.count}>"

    async def remove(self, user: Snowflake) -> None:
        """|coro|

        Remove the reaction by the provided :class:`User` from the message.

        If the reaction is not your own (i.e. ``user`` parameter is not you) then
        the :attr:`~Permissions.manage_messages` permission is needed.

        The ``user`` parameter must represent a user or member and meet
        the :class:`abc.Snowflake` abc.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
             The user or member from which to remove the reaction.

        Raises
        ------
        HTTPException
            Removing the reaction failed.
        Forbidden
            You do not have the proper permissions to remove the reaction.
        NotFound
            The user you specified, or the reaction's message was not found.
        """
        await self.message.remove_reaction(self.emoji, user)

    async def clear(self) -> None:
        """|coro|

        Clears this reaction from the message.

        You need the :attr:`~Permissions.manage_messages` permission to use this.

        .. versionadded:: 1.3

        Raises
        ------
        HTTPException
            Clearing the reaction failed.
        Forbidden
            You do not have the proper permissions to clear the reaction.
        NotFound
            The emoji you specified was not found.
        InvalidArgument
            The emoji parameter is invalid.
        """
        await self.message.clear_reaction(self.emoji)

    def users(
        self,
        *,
        limit: int | None = None,
        after: Snowflake | None = None,
        type: ReactionType | None = None,
    ) -> ReactionIterator:
        """Returns an :class:`AsyncIterator` representing the users that have reacted to the message.

        The ``after`` parameter must represent a member
        and meet the :class:`abc.Snowflake` abc.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of results to return.
            If not provided, returns all the users who
            reacted to the message.
        after: Optional[:class:`abc.Snowflake`]
            For pagination, reactions are sorted by member.
        type: Optional[:class:`ReactionType`]
            The type of reaction to get users for. Defaults to `normal`.

        Yields
        ------
        Union[:class:`User`, :class:`Member`]
            The member (if retrievable) or the user that has reacted
            to this message. The case where it can be a :class:`Member` is
            in a guild message context. Sometimes it can be a :class:`User`
            if the member has left the guild.

        Raises
        ------
        HTTPException
            Getting the users for the reaction failed.

        Examples
        --------
        Usage ::

            # I do not actually recommend doing this.
            async for user in reaction.users():
                await channel.send(f"{user} has reacted with {reaction.emoji}!")

        Flattening into a list: ::

            users = await reaction.users().flatten()
            # users is now a list of User...
            winner = random.choice(users)
            await channel.send(f"{winner} has won the raffle.")

        Getting super reactors: ::

            users = await reaction.users(type=ReactionType.burst).flatten()
        """
        if not isinstance(self.emoji, str):
            emoji = f"{self.emoji.name}:{self.emoji.id}"
        else:
            emoji = self.emoji

        if limit is None:
            limit = self.count

        reaction_type = type.value if isinstance(type, ReactionType) else type

        return ReactionIterator(self.message, emoji, limit, after, reaction_type)

    if TYPE_CHECKING:
        burst_colors = burst_colours


class ReactionCountDetails:
    """Represents a breakdown of the normal and burst reaction counts for the emoji.

    Attributes
    ----------
    normal: :class:`int`
        The number of normal reactions for this emoji.
    burst: :class:`bool`
        The number of super reactions for this emoji.
    """

    def __init__(self, data: ReactionCountDetailsPayload) -> None:
        self.normal = data.get("normal", 0)
        self.burst = data.get("burst", 0)
