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

import datetime as dt
import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    NamedTuple,
    TypeVar,
    cast,
    overload,
)

from typing_extensions import deprecated, override

import discord.abc

from . import utils
from ._internal.cache_peek import cached_emoji, cached_guild
from .asset import Asset
from .enums import (
    ChannelType,
    EmbeddedActivity,
    InviteTarget,
    SortOrder,
    StagePrivacyLevel,
    ThreadArchiveDuration as ThreadArchiveDurationEnum,
    VideoQualityMode,
    VoiceChannelEffectAnimationType,
    VoiceRegion,
    try_enum,
)
from .errors import ClientException, InvalidArgument
from .file import File
from .flags import ChannelFlags, MessageFlags
from .iterators import ArchivedThreadIterator
from .mixins import Hashable
from .object import Object
from .partial_emoji import PartialEmoji, _EmojiTag
from .permissions import PermissionOverwrite, Permissions
from .soundboard import PartialSoundboardSound, SoundboardSound
from .stage_instance import StageInstance
from .threads import Thread
from .utils import MISSING

__all__ = (
    "CategoryChannel",
    "DMChannel",
    "ForumChannel",
    "ForumTag",
    "GroupChannel",
    "MediaChannel",
    "PartialGuildChannel",
    "PartialMessageable",
    "StageChannel",
    "TextChannel",
    "VoiceChannel",
    "VoiceChannelEffectSendEvent",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from typing_extensions import Self

    from .abc import MessageableChannel, Snowflake, SnowflakeTime
    from .embeds import Embed
    from .emoji import AppEmoji, GuildEmoji
    from .guild import Guild, GuildChannel as GuildChannelType, PartialGuild
    from .invite import Invite
    from .member import Member, VoiceState
    from .mentions import AllowedMentions
    from .message import EmojiInputType, Message, PartialMessage
    from .role import Role
    from .state import ConnectionState
    from .sticker import GuildSticker, StickerItem
    from .types.channel import (
        CategoryChannel as CategoryChannelPayload,
        DMChannel as DMChannelPayload,
        ForumChannel as ForumChannelPayload,
        ForumTag as ForumTagPayload,
        GroupDMChannel as GroupChannelPayload,
        StageChannel as StageChannelPayload,
        TextChannel as TextChannelPayload,
        VoiceChannel as VoiceChannelPayload,
        VoiceChannelEffectSendEvent as VoiceChannelEffectSend,
    )
    from .types.embed import Embed as EmbedData
    from .types.message import AllowedMentions as AllowedMentionsPayload
    from .types.snowflake import SnowflakeList
    from .types.threads import ThreadArchiveDuration, ThreadType
    from .ui.view import BaseView
    from .user import BaseUser, ClientUser, User
    from .webhook import Webhook


_SPOILER_NSFW_WARNING = (
    "A spoiler channel cannot be NSFW: Discord only allows is_spoiler_channel when "
    "nsfw is false."
)


def _apply_spoiler(
    channel: _TextChannel | VoiceChannel, options: dict[str, Any]
) -> None:
    if "spoiler" not in options:
        return
    spoiler = options.pop("spoiler")
    flags = options.get("flags")
    if flags is None:
        flags = ChannelFlags._from_value(channel.flags.value)
    flags.is_spoiler_channel = spoiler
    options["flags"] = flags
    if spoiler and options.get("nsfw"):
        warnings.warn(_SPOILER_NSFW_WARNING, stacklevel=3)


def _spoiler_create_flags(spoiler: bool, nsfw: bool) -> int:  # pyright: ignore[reportUnusedFunction]
    if spoiler and nsfw:
        warnings.warn(_SPOILER_NSFW_WARNING, stacklevel=4)
    return ChannelFlags(is_spoiler_channel=bool(spoiler)).value


class ForumTag(Hashable):
    """Represents a forum tag that can be added to a thread inside a :class:`ForumChannel`.

        .. versionadded:: 2.3

        .. container:: operations

            .. describe:: x == y

                Checks if two forum tags are equal.

            .. describe:: x != y

                Checks if two forum tags are not equal.

            .. describe:: hash(x)

                Returns the forum tag's hash.

            .. describe:: str(x)

                Returns the forum tag's name.

    Attributes
    ----------
        id: :class:`int`
            The tag ID.
            Note that if the object was created manually then this will be ``0``.
        name: :class:`str`
            The name of the tag. Can only be up to 20 characters.
        moderated: :class:`bool`
            Whether this tag can only be added or removed by a moderator with
            the :attr:`~Permissions.manage_threads` permission.
        emoji: Optional[:class:`PartialEmoji`]
            The emoji that is used to represent this tag. Defaults to ``None``.
            Note that if the emoji is a custom emoji, it will *not* have name information.
    """

    __slots__ = ("emoji", "id", "moderated", "name")

    def __init__(
        self, *, name: str, emoji: EmojiInputType | None = None, moderated: bool = False
    ) -> None:
        self.name: str = name
        self.id: int = 0
        self.moderated: bool = moderated
        self.emoji: PartialEmoji | None = None
        if isinstance(emoji, _EmojiTag):
            self.emoji = emoji._to_partial()
        elif isinstance(emoji, str):
            self.emoji = PartialEmoji.from_str(emoji)
        elif emoji is not None:
            raise TypeError(
                "emoji must be a GuildEmoji, PartialEmoji, str, or None and not"
                f" {emoji.__class__!r}"
            )

    def __repr__(self) -> str:
        return (
            "<ForumTag"
            f" id={self.id} name={self.name!r} emoji={self.emoji!r} moderated={self.moderated}>"
        )

    def __str__(self) -> str:
        return self.name

    @classmethod
    def from_data(cls, *, state: ConnectionState, data: ForumTagPayload) -> ForumTag:
        """Build a forum tag from its payload."""
        self = cls.__new__(cls)
        self.name = data["name"]
        self.id = int(data["id"])
        self.moderated = data.get("moderated", False)

        emoji_name = data.get("emoji_name") or ""
        emoji_id = utils._get_as_snowflake(data, "emoji_id") or None
        self.emoji = None
        if emoji_name or emoji_id:
            self.emoji = PartialEmoji.with_state(
                state=state, name=emoji_name, id=emoji_id
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert this forum tag to its payload."""
        payload: dict[str, Any] = {
            "name": self.name,
            "moderated": self.moderated,
            "emoji_id": None,
            "emoji_name": None,
        }
        if self.emoji is not None:
            payload.update(self.emoji._to_forum_reaction_payload())

        if self.id:
            payload["id"] = self.id

        return payload


class _TextChannel(discord.abc.GuildChannel, Hashable):
    __slots__ = (
        "_default_reaction_emoji",
        "_overwrites",
        "_state",
        "_type",
        "available_tags",
        "category_id",
        "default_auto_archive_duration",
        "default_sort_order",
        "default_thread_slowmode_delay",
        "flags",
        "guild_id",
        "id",
        "last_message_id",
        "name",
        "nsfw",
        "position",
        "slowmode_delay",
        "topic",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: TextChannelPayload | ForumChannelPayload,
    ) -> None:
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self._update(guild, data)

    @property
    def _repr_attrs(self) -> tuple[str, ...]:
        return "id", "name", "position", "category_id"

    def __repr__(self) -> str:
        attrs = [(val, getattr(self, val)) for val in self._repr_attrs]
        joined = " ".join("{}={!r}".format(*t) for t in attrs)
        return f"<{self.__class__.__name__} {joined}>"

    def _update(
        self,
        guild: Guild | PartialGuild,
        data: TextChannelPayload | ForumChannelPayload,
    ) -> None:
        # This data will always exist
        self.guild_id: int = guild.id
        self.name: str = data["name"]
        self.category_id: int | None = utils._get_as_snowflake(data, "parent_id")
        self._type: int = data["type"]
        # This data may be missing depending on how this object is being created/updated
        if not data.pop("_invoke_flag", False):
            self.topic: str | None = data.get("topic")
            self.position: int = data.get("position")
            self.nsfw: bool = data.get("nsfw", False)
            # Does this need coercion into `int`? No idea yet.
            self.slowmode_delay: int = data.get("rate_limit_per_user", 0)
            self.default_auto_archive_duration: ThreadArchiveDuration = data.get(
                "default_auto_archive_duration", 1440
            )
            self.default_thread_slowmode_delay: int | None = data.get(
                "default_thread_rate_limit_per_user"
            )
            self.last_message_id: int | None = utils._get_as_snowflake(
                data, "last_message_id"
            )
            self.flags: ChannelFlags = ChannelFlags._from_value(data.get("flags", 0))
            self._fill_overwrites(data)

        self._default_reaction_emoji: str | PartialEmoji | None = None

        reaction_emoji_ctx = data.get("default_reaction_emoji")
        if reaction_emoji_ctx is not None:
            emoji_name = reaction_emoji_ctx.get("emoji_name")
            if emoji_name is not None:
                self._default_reaction_emoji = emoji_name
            else:
                emoji_id = utils._get_as_snowflake(reaction_emoji_ctx, "emoji_id")
                if emoji_id is not None:
                    self._default_reaction_emoji = PartialEmoji(name=None, id=emoji_id)

    @property
    def default_reaction_emoji(
        self,
    ) -> str | GuildEmoji | AppEmoji | PartialEmoji | None:
        """The default forum reaction emoji.

        This is the unicode emoji as a :class:`str`, the cached custom emoji when it
        is in the in-process cache, or a :class:`PartialEmoji` carrying its ID
        otherwise (always with a remote cache backend, use
        :meth:`get_default_reaction_emoji` there).
        """
        emoji = self._default_reaction_emoji
        if isinstance(emoji, PartialEmoji):
            return cached_emoji(self._state, emoji.id) or emoji
        return emoji

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return try_enum(ChannelType, self._type)

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.text.value

    @staticmethod
    def _text_permissions(base: Permissions) -> Permissions:
        # text channels do not have voice related permissions
        denied = Permissions.voice()
        base.value &= ~denied.value
        return base

    @utils.copy_doc(discord.abc.GuildChannel.permissions_for)
    def permissions_for(self, obj: Member | Role, /) -> Permissions:
        return self._text_permissions(super().permissions_for(obj))

    async def get_permissions_for(self, obj: Member | Role, /) -> Permissions:
        return self._text_permissions(await super().get_permissions_for(obj))

    @property
    def members(self) -> list[Member]:
        """Returns all members that can see this channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_members` there.
        """
        return [
            m
            for m in self._state._guild_bucket("members", self.guild_id).values_nowait()
            if self.permissions_for(m).read_messages
        ]

    @property
    def threads(self) -> list[Thread]:
        """Returns all the threads that you can see.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_threads` there.

        .. versionadded:: 2.0
        """
        return [
            thread
            for thread in self._state._guild_bucket(
                "threads", self.guild_id
            ).values_nowait()
            if thread.parent_id == self.id
        ]

    async def get_threads(self) -> list[Thread]:
        """|coro|

        Returns all the cached threads of this channel that you can see.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`Thread`]
            The cached threads.
        """
        return [
            thread
            for thread in await self._state._guild_bucket(
                "threads", self.guild_id
            ).values()
            if thread.parent_id == self.id
        ]

    def is_nsfw(self) -> bool:
        """Checks if the channel is NSFW."""
        return self.nsfw

    @property
    def spoiler(self) -> bool:
        """Checks if the channel is a spoiler channel.

        This is a shortcut for :attr:`ChannelFlags.is_spoiler_channel`.

        .. versionadded:: 3.0
        """
        return self.flags.is_spoiler_channel

    @property
    def last_message(self) -> Message | None:
        """Fetches the last message from this channel in cache.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_last_message` there.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return discord.abc.cached_message(self._state, self.last_message_id)

    async def get_last_message(self) -> Message | None:
        """|coro|

        Fetches the last message from this channel in cache.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return (
            await self._state._get_message(self.last_message_id)
            if self.last_message_id
            else None
        )

    async def edit(self, **options: Any) -> _TextChannel | None:
        """Edits the channel."""
        raise NotImplementedError

    @override
    @utils.copy_doc(discord.abc.GuildChannel.clone)
    async def clone(
        self, *, name: str | None = None, reason: str | None = None
    ) -> Self:
        return await self._clone_impl(
            {
                "topic": self.topic,
                "nsfw": self.nsfw,
                "rate_limit_per_user": self.slowmode_delay,
            },
            name=name,
            reason=reason,
        )

    async def delete_messages(
        self, messages: Iterable[Snowflake], *, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes a list of messages. This is similar to :meth:`Message.delete`
        except it bulk deletes multiple messages.

        As a special case, if the number of messages is 0, then nothing
        is done. If the number of messages is 1 then single message
        delete is done. If it's more than two, then bulk delete is used.

        You cannot bulk delete more than 100 messages or messages that
        are older than 14 days old.

        You must have the :attr:`~Permissions.manage_messages` permission to
        use this.

        Parameters
        ----------
        messages: Iterable[:class:`abc.Snowflake`]
            An iterable of messages denoting which ones to bulk delete.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Raises
        ------
        ClientException
            The number of messages to delete was more than 100.
        Forbidden
            You do not have proper permissions to delete the messages.
        NotFound
            If single delete, then the message was already deleted.
        HTTPException
            Deleting the messages failed.
        """
        if not isinstance(messages, (list, tuple)):
            messages = list(messages)

        if len(messages) == 0:
            return  # do nothing

        if len(messages) == 1:
            message_id: int = messages[0].id
            await self._state.http.delete_message(self.id, message_id, reason=reason)
            return

        if len(messages) > 100:
            raise ClientException("Can only bulk delete messages up to 100 messages")

        message_ids: SnowflakeList = [m.id for m in messages]
        await self._state.http.delete_messages(self.id, message_ids, reason=reason)

    async def purge(
        self,
        *,
        limit: int | None = 100,
        check: Callable[[Message], bool] = MISSING,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        around: SnowflakeTime | None = None,
        oldest_first: bool | None = False,
        bulk: bool = True,
        reason: str | None = None,
    ) -> list[Message]:
        """|coro|

        Purges a list of messages that meet the criteria given by the predicate
        ``check``. If a ``check`` is not provided then all messages are deleted
        without discrimination.

        You must have the :attr:`~Permissions.manage_messages` permission to
        delete messages even if they are your own.
        The :attr:`~Permissions.read_message_history` permission is
        also needed to retrieve message history.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of messages to search through. This is not the number
            of messages that will be deleted, though it can be.
        check: Callable[[:class:`Message`], :class:`bool`]
            The function used to check if a message should be deleted.
            It must take a :class:`Message` as its sole parameter.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``before`` in :meth:`history`.
        after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``after`` in :meth:`history`.
        around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``around`` in :meth:`history`.
        oldest_first: Optional[:class:`bool`]
            Same as ``oldest_first`` in :meth:`history`.
        bulk: :class:`bool`
            If ``True``, use bulk delete. Setting this to ``False`` is useful for mass-deleting
            a bot's own messages without :attr:`Permissions.manage_messages`. When ``True``, will
            fall back to single delete if messages are older than two weeks.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Returns
        -------
        List[:class:`.Message`]
            The list of messages that were deleted.

        Raises
        ------
        Forbidden
            You do not have proper permissions to do the actions required.
        HTTPException
            Purging the messages failed.

        Examples
        --------
        Deleting bot's messages ::

            def is_me(m):
                return m.author == client.user


            deleted = await channel.purge(limit=100, check=is_me)
            await channel.send(f"Deleted {len(deleted)} message(s)")
        """
        return await discord.abc.purge_messages_helper(
            cast("TextChannel", self),
            limit=limit,
            check=check,
            before=before,
            after=after,
            around=around,
            oldest_first=oldest_first,
            bulk=bulk,
            reason=reason,
        )

    async def webhooks(self) -> list[Webhook]:
        """|coro|

        Gets the list of webhooks from this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        Returns
        -------
        List[:class:`Webhook`]
            The webhooks for this channel.

        Raises
        ------
        Forbidden
            You don't have permissions to get the webhooks.
        """
        from .webhook import Webhook

        data = await self._state.http.channel_webhooks(self.id)
        return [Webhook.from_state(d, state=self._state) for d in data]

    async def create_webhook(
        self, *, name: str, avatar: bytes | None = None, reason: str | None = None
    ) -> Webhook:
        """|coro|

        Creates a webhook for this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        .. versionchanged:: 1.1
            Added the ``reason`` keyword-only parameter.

        Parameters
        ----------
        name: :class:`str`
            The webhook's name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's default avatar.
            This operates similarly to :meth:`~ClientUser.edit`.
        reason: Optional[:class:`str`]
            The reason for creating this webhook. Shows up in the audit logs.

        Returns
        -------
        :class:`Webhook`
            The created webhook.

        Raises
        ------
        HTTPException
            Creating the webhook failed.
        Forbidden
            You do not have permissions to create a webhook.
        """
        from .webhook import Webhook

        avatar_data = (
            utils._bytes_to_base64_data(avatar) if avatar is not None else None
        )

        data = await self._state.http.create_webhook(
            self.id, name=str(name), avatar=avatar_data, reason=reason
        )
        return Webhook.from_state(data, state=self._state)

    async def follow(
        self, *, destination: TextChannel, reason: str | None = None
    ) -> Webhook:
        """
        Follows a channel using a webhook.

        Only news channels can be followed.

        .. note::

            The webhook returned will not provide a token to do webhook
            actions, as Discord does not provide it.

        .. versionadded:: 1.3

        Parameters
        ----------
        destination: :class:`TextChannel`
            The channel you would like to follow from.
        reason: Optional[:class:`str`]
            The reason for following the channel. Shows up on the destination guild's audit log.

            .. versionadded:: 1.4

        Returns
        -------
        :class:`Webhook`
            The created webhook.

        Raises
        ------
        HTTPException
            Following the channel failed.
        Forbidden
            You do not have the permissions to create a webhook.
        """
        if not cast("TextChannel", self).is_news():
            raise ClientException("The channel must be a news channel.")

        if not isinstance(destination, TextChannel):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise InvalidArgument(
                f"Expected TextChannel received {destination.__class__.__name__}"
            )

        from .webhook import Webhook

        data = await self._state.http.follow_webhook(
            self.id, webhook_channel_id=destination.id, reason=reason
        )
        return Webhook._as_follower(
            data, channel=destination, user=cast("ClientUser", self._state.user)
        )

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        -------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=cast("TextChannel", self), id=message_id)

    def get_thread(self, thread_id: int, /) -> Thread | None:
        """Returns a thread with the given ID.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`Guild.get_thread` there.

        .. versionadded:: 2.0

        Parameters
        ----------
        thread_id: :class:`int`
            The ID to search for.

        Returns
        -------
        Optional[:class:`Thread`]
            The returned thread or ``None`` if not found.
        """
        return self._state._guild_bucket("threads", self.guild_id).get_nowait(thread_id)

    def archived_threads(
        self,
        *,
        private: bool = False,
        joined: bool = False,
        limit: int | None = 50,
        before: Snowflake | dt.datetime | None = None,
    ) -> ArchivedThreadIterator:
        """Returns an :class:`~discord.AsyncIterator` that iterates over all archived threads in the guild.

        You must have :attr:`~Permissions.read_message_history` to use this. If iterating over private threads
        then :attr:`~Permissions.manage_threads` is also required.

        .. versionadded:: 2.0

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of threads to retrieve.
            If ``None``, retrieves every archived thread in the channel. Note, however,
            that this would make it a slow operation.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve archived channels before the given date or ID.
        private: :class:`bool`
            Whether to retrieve private archived threads.
        joined: :class:`bool`
            Whether to retrieve private archived threads that you've joined.
            You cannot set ``joined`` to ``True`` and ``private`` to ``False``.

        Yields
        ------
        :class:`Thread`
            The archived threads.

        Raises
        ------
        Forbidden
            You do not have permissions to get archived threads.
        HTTPException
            The request to get the archived threads failed.
        """
        return ArchivedThreadIterator(
            self.id,
            self.guild,
            limit=limit,
            joined=joined,
            private=private,
            before=before,
        )


class TextChannel(discord.abc.Messageable, _TextChannel):
    """Represents a Discord text channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    topic: Optional[:class:`str`]
        The channel's topic. ``None`` if it doesn't exist.
    position: Optional[:class:`int`]
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0. Can be ``None`` if the channel was received in an interaction.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this channel. It may
        *not* point to an existing or valid message.
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this channel. A value of `0` denotes that it is disabled.
        Bots and users with :attr:`~Permissions.manage_channels` or
        :attr:`~Permissions.manage_messages` bypass slowmode.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work".

        .. note::

            To check if the channel or the guild of that channel are marked as NSFW, consider :meth:`is_nsfw` instead.
    default_auto_archive_duration: :class:`int`
        The default auto archive duration in minutes for threads created in this channel.

        .. versionadded:: 2.0
    flags: :class:`ChannelFlags`
        Extra features of the channel.

        .. versionadded:: 2.0
    default_thread_slowmode_delay: Optional[:class:`int`]
        The initial slowmode delay to set on newly created threads in this channel.

        .. versionadded:: 2.3
    """

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: TextChannelPayload,
    ) -> None:
        super().__init__(state=state, guild=guild, data=data)

    @property
    def _repr_attrs(self) -> tuple[str, ...]:
        return (*super()._repr_attrs, "news")

    async def _get_channel(self) -> TextChannel:
        return self

    def is_news(self) -> bool:
        """Checks if the channel is a news/announcements channel."""
        return self._type == ChannelType.news.value

    @property
    def news(self) -> bool:
        """Equivalent to :meth:`is_news`."""
        return self.is_news()

    @overload
    async def edit(
        self,
        *,
        reason: str | None = ...,
        name: str = ...,
        topic: str = ...,
        position: int = ...,
        nsfw: bool = ...,
        sync_permissions: bool = ...,
        category: CategoryChannel | None = ...,
        slowmode_delay: int = ...,
        default_auto_archive_duration: ThreadArchiveDuration = ...,
        default_thread_slowmode_delay: int = ...,
        type: ChannelType = ...,
        overwrites: Mapping[Role | Member | Snowflake, PermissionOverwrite] = ...,
        spoiler: bool = ...,
    ) -> TextChannel | None: ...

    @overload
    async def edit(self) -> TextChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> TextChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        .. versionchanged:: 1.3
            The ``overwrites`` keyword-only parameter was added.

        .. versionchanged:: 1.4
            The ``type`` keyword-only parameter was added.

        .. versionchanged:: 2.0
            Edits are no longer in-place, the newly edited channel is returned instead.

        Parameters
        ----------
        name: :class:`str`
            The new channel name.
        topic: :class:`str`
            The new channel's topic.
        position: :class:`int`
            The new channel's position.
        nsfw: :class:`bool`
            Whether the channel is marked as NSFW.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of `0` disables slowmode. The maximum value possible is `21600`.
        type: :class:`ChannelType`
            Change the type of this text channel. Currently, only conversion between
            :attr:`ChannelType.text` and :attr:`ChannelType.news` is supported. This
            is only available to guilds that contain ``NEWS`` in :attr:`Guild.features`.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.
        default_auto_archive_duration: :class:`int`
            The new default auto archive duration in minutes for threads created in this channel.
            Must be one of ``60``, ``1440``, ``4320``, or ``10080``.
        default_thread_slowmode_delay: :class:`int`
            The new default slowmode delay in seconds for threads created in this channel.

            .. versionadded:: 2.3
        spoiler: :class:`bool`
            Whether the channel is a spoiler channel, i.e. users must opt in to view its
            contents. Discord only allows this on channels that are not NSFW, and a
            warning is emitted if ``nsfw`` is also ``True``.

            .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`.TextChannel`]
            The newly edited text channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If position is less than 0 or greater than the number of channels, or if
            the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        """
        _apply_spoiler(self, options)
        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("TextChannelPayload", payload),
            )
        return None

    async def create_thread(
        self,
        *,
        name: str,
        message: Snowflake | None = None,
        auto_archive_duration: ThreadArchiveDuration = MISSING,
        type: ChannelType | None = None,
        slowmode_delay: int | None = None,
        invitable: bool | None = None,
        reason: str | None = None,
    ) -> Thread:
        """|coro|

        Creates a thread in this text channel.

        To create a public thread, you must have :attr:`~discord.Permissions.create_public_threads`.
        For a private thread, :attr:`~discord.Permissions.create_private_threads` is needed instead.

        .. versionadded:: 2.0

        Parameters
        ----------
        name: :class:`str`
            The name of the thread.
        message: Optional[:class:`abc.Snowflake`]
            A snowflake representing the message to create the thread with.
            If ``None`` is passed then a private thread is created.
            Defaults to ``None``.
        auto_archive_duration: :class:`int`
            The duration in minutes before a thread is automatically archived for inactivity.
            If not provided, the channel's default auto archive duration is used.
        type: Optional[:class:`ChannelType`]
            The type of thread to create. If a ``message`` is passed then this parameter
            is ignored, as a thread created with a message is always a public thread.
            By default, this creates a private thread if this is ``None``.
        slowmode_delay: Optional[:class:`int`]
            Specifies the slowmode rate limit for users in this thread, in seconds.
            A value of ``0`` disables slowmode. The maximum value possible is ``21600``.
        invitable: Optional[:class:`bool`]
            Whether non-moderators can add other non-moderators to this thread.
            Only available for private threads, where it defaults to True.
        reason: :class:`str`
            The reason for creating a new thread. Shows up on the audit log.

        Returns
        -------
        :class:`Thread`
            The created thread

        Raises
        ------
        Forbidden
            You do not have permissions to create a thread.
        HTTPException
            Starting the thread failed.
        """
        if type is None:
            type = ChannelType.private_thread

        if message is None:
            data = await self._state.http.start_thread_without_message(
                self.id,
                name=name,
                auto_archive_duration=auto_archive_duration
                or self.default_auto_archive_duration,
                type=cast("ThreadType", type.value),
                rate_limit_per_user=slowmode_delay or 0,
                invitable=cast("bool", invitable),
                reason=reason,
            )
        else:
            data = await self._state.http.start_thread_with_message(
                self.id,
                message.id,
                name=name,
                auto_archive_duration=auto_archive_duration
                or self.default_auto_archive_duration,
                rate_limit_per_user=slowmode_delay or 0,
                reason=reason,
            )

        return Thread(guild=self.guild, state=self._state, data=data)


class ForumChannel(_TextChannel):
    """Represents a Discord forum channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    topic: Optional[:class:`str`]
        The channel's topic. ``None`` if it doesn't exist.

        .. note::

            :attr:`guidelines` exists as an alternative to this attribute.
    position: Optional[:class:`int`]
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0. Can be ``None`` if the channel was received in an interaction.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this channel. It may
        *not* point to an existing or valid message.
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this channel. A value of `0` denotes that it is disabled.
        Bots and users with :attr:`~Permissions.manage_channels` or
        :attr:`~Permissions.manage_messages` bypass slowmode.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work".

        .. note::

            To check if the channel or the guild of that channel are marked as NSFW, consider :meth:`is_nsfw` instead.
    default_auto_archive_duration: :class:`int`
        The default auto archive duration in minutes for threads created in this channel.

        .. versionadded:: 2.0
    flags: :class:`ChannelFlags`
        Extra features of the channel.

        .. versionadded:: 2.0
    available_tags: List[:class:`ForumTag`]
        The set of tags that can be used in a forum channel.

        .. versionadded:: 2.3
    default_sort_order: Optional[:class:`SortOrder`]
        The default sort order type used to order posts in this channel.

        .. versionadded:: 2.3
    default_thread_slowmode_delay: Optional[:class:`int`]
        The initial slowmode delay to set on newly created threads in this channel.

        .. versionadded:: 2.3
    default_reaction_emoji: Optional[:class:`str` | :class:`GuildEmoji` | :class:`PartialEmoji`]
        The default forum reaction emoji, as a unicode string, the cached custom
        emoji or a partial custom emoji when it is not cached (property).
        Use :meth:`get_default_reaction_emoji` with any cache backend.

        .. versionadded:: 2.5
    """

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: ForumChannelPayload,
    ) -> None:
        super().__init__(state=state, guild=guild, data=data)

    def _update(
        self,
        guild: Guild | PartialGuild,
        data: TextChannelPayload | ForumChannelPayload,
    ) -> None:
        super()._update(guild, data)
        data = cast("ForumChannelPayload", data)
        self.available_tags: list[ForumTag] = [
            ForumTag.from_data(state=self._state, data=tag)
            for tag in (data.get("available_tags") or [])
        ]
        sort_order = data.get("default_sort_order", None)
        self.default_sort_order: SortOrder | None = (
            try_enum(SortOrder, sort_order) if sort_order is not None else None
        )

    async def get_default_reaction_emoji(self) -> str | GuildEmoji | AppEmoji | None:
        """|coro|

        Returns the default forum reaction emoji, resolving custom emojis from the cache.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`str`, :class:`GuildEmoji`, :class:`AppEmoji`]]
            The unicode emoji, the cached custom emoji, or ``None`` if there is
            none or the custom emoji is not cached.
        """
        emoji = self._default_reaction_emoji
        if isinstance(emoji, PartialEmoji):
            return await self._state.get_emoji(emoji.id)
        return emoji

    @property
    def guidelines(self) -> str | None:
        """The channel's guidelines. An alias of :attr:`topic`."""
        return self.topic

    @property
    def requires_tag(self) -> bool:
        """Whether a tag is required to be specified when creating a thread in this forum or media channel.

        Tags are specified in :attr:`applied_tags`.

        .. versionadded:: 2.3
        """
        return self.flags.require_tag

    def get_tag(self, id: int, /) -> ForumTag | None:
        """Returns the :class:`ForumTag` from this forum channel with the given ID, if any.

        .. versionadded:: 2.3
        """
        return utils.get(self.available_tags, id=id)

    @overload
    async def edit(
        self,
        *,
        reason: str | None = ...,
        name: str = ...,
        topic: str = ...,
        position: int = ...,
        nsfw: bool = ...,
        sync_permissions: bool = ...,
        category: CategoryChannel | None = ...,
        slowmode_delay: int = ...,
        default_auto_archive_duration: (
            ThreadArchiveDuration | ThreadArchiveDurationEnum
        ) = ...,
        default_thread_slowmode_delay: int = ...,
        default_sort_order: SortOrder = ...,
        default_reaction_emoji: GuildEmoji | int | str | None = ...,
        available_tags: list[ForumTag] = ...,
        require_tag: bool = ...,
        overwrites: Mapping[Role | Member | Snowflake, PermissionOverwrite] = ...,
        spoiler: bool = ...,
    ) -> ForumChannel | None: ...

    @overload
    async def edit(self) -> ForumChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> ForumChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        Parameters
        ----------
        name: :class:`str`
            The new channel name.
        topic: :class:`str`
            The new channel's topic.
        position: :class:`int`
            The new channel's position.
        nsfw: :class:`bool`
            Whether the channel is marked as NSFW.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of `0` disables slowmode. The maximum value possible is `21600`.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.
        default_auto_archive_duration: :class:`int`
            The new default auto archive duration in minutes for threads created in this channel.
            Must be one of ``60``, ``1440``, ``4320``, or ``10080``.
            :class:`ThreadArchiveDuration` can be used alternatively.
        default_thread_slowmode_delay: :class:`int`
            The new default slowmode delay in seconds for threads created in this channel.

            .. versionadded:: 2.3
        default_sort_order: Optional[:class:`SortOrder`]
            The default sort order type to use to order posts in this channel.

            .. versionadded:: 2.3
        default_reaction_emoji: Optional[:class:`discord.GuildEmoji` | :class:`int` | :class:`str`]
            The default reaction emoji.
            Can be a unicode emoji or a custom emoji in the forms:
            :class:`GuildEmoji`, snowflake ID, string representation (eg. '<a:emoji_name:emoji_id>').

            .. versionadded:: 2.5
        available_tags: List[:class:`ForumTag`]
            The set of tags that can be used in this channel. Must be less than `20`.

            .. versionadded:: 2.3
        require_tag: :class:`bool`
            Whether a tag should be required to be specified when creating a thread in this channel.

            .. versionadded:: 2.3
        spoiler: :class:`bool`
            Whether the channel is a spoiler channel, i.e. users must opt in to view its
            contents. Discord only allows this on channels that are not NSFW, and a
            warning is emitted if ``nsfw`` is also ``True``.

            .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`.ForumChannel`]
            The newly edited forum channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If position is less than 0 or greater than the number of channels, or if
            the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        """
        if "require_tag" in options:
            options["flags"] = ChannelFlags._from_value(self.flags.value)
            options["flags"].require_tag = options.pop("require_tag")
        _apply_spoiler(self, options)

        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("ForumChannelPayload", payload),
            )
        return None

    async def create_thread(
        self,
        name: str,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        stickers: Sequence[GuildSticker | StickerItem] | None = None,
        delete_message_after: float | None = None,
        nonce: int | str | None = None,
        allowed_mentions: AllowedMentions | None = None,
        view: BaseView | None = None,
        applied_tags: list[ForumTag] | None = None,
        suppress: bool = False,
        silent: bool = False,
        auto_archive_duration: ThreadArchiveDuration = MISSING,
        slowmode_delay: int = MISSING,
        reason: str | None = None,
    ) -> Thread:
        """|coro|

        Creates a thread in this forum channel.

        To create a public thread, you must have :attr:`~discord.Permissions.create_public_threads`.
        For a private thread, :attr:`~discord.Permissions.create_private_threads` is needed instead.

        .. versionadded:: 2.0

        Parameters
        ----------
        name: :class:`str`
            The name of the thread.
        content: :class:`str`
            The content of the message to send.
        embed: :class:`~discord.Embed`
            The rich embed for the content.
        embeds: List[:class:`~discord.Embed`]
            A list of embeds to upload. Must be a maximum of 10.
        file: :class:`~discord.File`
            The file to upload.
        files: List[:class:`~discord.File`]
            A list of files to upload. Must be a maximum of 10.
        stickers: Sequence[Union[:class:`~discord.GuildSticker`, :class:`~discord.StickerItem`]]
            A list of stickers to upload. Must be a maximum of 3.
        delete_message_after: :class:`int`
            The time to wait before deleting the thread.
        nonce: Union[:class:`str`, :class:`int`]
            The nonce to use for sending this message. If the message was successfully sent,
            then the message will have a nonce with this value.
        allowed_mentions: :class:`~discord.AllowedMentions`
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.
        view: :class:`discord.ui.BaseView`
            A Discord UI View to add to the message.
        applied_tags: List[:class:`discord.ForumTag`]
            A list of tags to apply to the new thread.
        auto_archive_duration: :class:`int`
            The duration in minutes before a thread is automatically archived for inactivity.
            If not provided, the channel's default auto archive duration is used.
        slowmode_delay: :class:`int`
            The number of seconds a member must wait between sending messages
            in the new thread. A value of `0` denotes that it is disabled.
            Bots and users with :attr:`~Permissions.manage_channels` or
            :attr:`~Permissions.manage_messages` bypass slowmode.
            If not provided, the forum channel's default slowmode is used.
        reason: :class:`str`
            The reason for creating a new thread. Shows up on the audit log.

        Returns
        -------
        :class:`Thread`
            The created thread

        Raises
        ------
        Forbidden
            You do not have permissions to create a thread.
        HTTPException
            Starting the thread failed.
        """
        state = self._state
        message_content = str(content) if content is not None else None

        if embed is not None and embeds is not None:
            raise InvalidArgument(
                "cannot pass both embed and embeds parameter to create_thread()"
            )

        embed_payload: EmbedData | None = None
        embeds_payload: list[EmbedData] | None = None
        if embed is not None:
            embed_payload = embed.to_dict()

        elif embeds is not None:
            if len(embeds) > 10:
                raise InvalidArgument(
                    "embeds parameter must be a list of up to 10 elements"
                )
            embeds_payload = [e.to_dict() for e in embeds]

        sticker_ids: list[int] | None = None
        if stickers is not None:
            sticker_ids = [sticker.id for sticker in stickers]

        mentions_payload: AllowedMentionsPayload | None
        if allowed_mentions is None:
            mentions_payload = (
                state.allowed_mentions and state.allowed_mentions.to_dict()
            )
        elif state.allowed_mentions is not None:
            mentions_payload = state.allowed_mentions.merge(allowed_mentions).to_dict()
        else:
            mentions_payload = allowed_mentions.to_dict()

        flags = MessageFlags(
            suppress_embeds=bool(suppress),
            suppress_notifications=bool(silent),
        )

        if view:
            if not hasattr(view, "__discord_ui_view__"):
                raise InvalidArgument(
                    f"view parameter must be BaseView not {view.__class__!r}"
                )

            components = view.to_components()
            if view.is_components_v2():
                if embeds or content:
                    raise TypeError(
                        "cannot send embeds or content with a view using v2 component logic"
                    )
                flags.is_components_v2 = True
        else:
            components = None

        tag_ids: list[str] | None = None
        if applied_tags is not None:
            tag_ids = [str(tag.id) for tag in applied_tags]

        if file is not None and files is not None:
            raise InvalidArgument("cannot pass both file and files parameter to send()")

        if files is not None:
            if len(files) > 10:
                raise InvalidArgument(
                    "files parameter must be a list of up to 10 elements"
                )
            if not all(isinstance(f, File) for f in files):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidArgument("files parameter must be a list of File")

        if file is not None:
            if not isinstance(file, File):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidArgument("file parameter must be File")
            files = [file]

        try:
            data = await state.http.start_forum_thread(
                self.id,
                content=message_content,
                name=name,
                files=files,
                embed=embed_payload,
                embeds=embeds_payload,
                nonce=nonce,
                allowed_mentions=mentions_payload,
                stickers=sticker_ids,
                components=components,
                auto_archive_duration=auto_archive_duration
                or self.default_auto_archive_duration,
                rate_limit_per_user=slowmode_delay or self.slowmode_delay,
                applied_tags=tag_ids,
                flags=flags.value,
                reason=reason,
            )
        finally:
            if files is not None:
                for f in files:
                    f.close()

        ret = Thread(guild=self.guild, state=self._state, data=data)
        msg = ret.get_partial_message(
            int(cast("dict[str, Any]", data)["last_message_id"])
        )
        if view and view.is_dispatchable():
            state.store_view(view, msg.id)

        if delete_message_after is not None:
            await msg.delete(delay=delete_message_after)
        return ret


class MediaChannel(ForumChannel):
    """Represents a Discord media channel. Subclass of :class:`ForumChannel`.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

        .. versionadded:: 2.7

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    topic: Optional[:class:`str`]
        The channel's topic. ``None`` if it doesn't exist.

        .. note::

            :attr:`guidelines` exists as an alternative to this attribute.
    position: Optional[:class:`int`]
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0. Can be ``None`` if the channel was received in an interaction.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this channel. It may
        *not* point to an existing or valid message.
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this channel. A value of `0` denotes that it is disabled.
        Bots and users with :attr:`~Permissions.manage_channels` or
        :attr:`~Permissions.manage_messages` bypass slowmode.
    nsfw: :class:`bool`
        If the channel is marked as "not safe for work".

        .. note::

            To check if the channel or the guild of that channel are marked as NSFW, consider :meth:`is_nsfw` instead.
    default_auto_archive_duration: :class:`int`
        The default auto archive duration in minutes for threads created in this channel.

    flags: :class:`ChannelFlags`
        Extra features of the channel.

    available_tags: List[:class:`ForumTag`]
        The set of tags that can be used in a forum channel.

    default_sort_order: Optional[:class:`SortOrder`]
        The default sort order type used to order posts in this channel.

    default_thread_slowmode_delay: Optional[:class:`int`]
        The initial slowmode delay to set on newly created threads in this channel.

    default_reaction_emoji: Optional[:class:`str` | :class:`GuildEmoji` | :class:`PartialEmoji`]
        The default forum reaction emoji, as a unicode string, the cached custom
        emoji or a partial custom emoji when it is not cached (property).
        Use :meth:`get_default_reaction_emoji` with any cache backend.
    """

    @property
    def media_download_options_hidden(self) -> bool:
        """Whether media download options are hidden in this media channel.

        .. versionadded:: 2.7
        """
        return self.flags.hide_media_download_options

    @overload
    async def edit(
        self,
        *,
        reason: str | None = ...,
        name: str = ...,
        topic: str = ...,
        position: int = ...,
        nsfw: bool = ...,
        sync_permissions: bool = ...,
        category: CategoryChannel | None = ...,
        slowmode_delay: int = ...,
        default_auto_archive_duration: ThreadArchiveDuration = ...,
        default_thread_slowmode_delay: int = ...,
        default_sort_order: SortOrder = ...,
        default_reaction_emoji: GuildEmoji | int | str | None = ...,
        available_tags: list[ForumTag] = ...,
        require_tag: bool = ...,
        hide_media_download_options: bool = ...,
        overwrites: Mapping[Role | Member | Snowflake, PermissionOverwrite] = ...,
        spoiler: bool = ...,
    ) -> MediaChannel | None: ...

    @overload
    async def edit(self) -> MediaChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> MediaChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        Parameters
        ----------
        name: :class:`str`
            The new channel name.
        topic: :class:`str`
            The new channel's topic.
        position: :class:`int`
            The new channel's position.
        nsfw: :class:`bool`
            Whether the channel is marked as NSFW.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of `0` disables slowmode. The maximum value possible is `21600`.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.
        default_auto_archive_duration: :class:`int`
            The new default auto archive duration in minutes for threads created in this channel.
            Must be one of ``60``, ``1440``, ``4320``, or ``10080``.
        default_thread_slowmode_delay: :class:`int`
            The new default slowmode delay in seconds for threads created in this channel.

        default_sort_order: Optional[:class:`SortOrder`]
            The default sort order type to use to order posts in this channel.

        default_reaction_emoji: Optional[:class:`discord.GuildEmoji` | :class:`int` | :class:`str`]
            The default reaction emoji.
            Can be a unicode emoji or a custom emoji in the forms:
            :class:`GuildEmoji`, snowflake ID, string representation (e.g., '<a:emoji_name:emoji_id>').

        available_tags: List[:class:`ForumTag`]
            The set of tags that can be used in this channel. Must be less than `20`.

        require_tag: :class:`bool`
            Whether a tag should be required to be specified when creating a thread in this channel.

        hide_media_download_options: :class:`bool`
            Whether media download options should be hidden in this media channel.
        spoiler: :class:`bool`
            Whether the channel is a spoiler channel, i.e. users must opt in to view its
            contents. Discord only allows this on channels that are not NSFW, and a
            warning is emitted if ``nsfw`` is also ``True``.

            .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`.MediaChannel`]
            The newly edited media channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If position is less than 0 or greater than the number of channels, or if
            the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        """
        if "require_tag" in options or "hide_media_download_options" in options:
            flags = ChannelFlags._from_value(self.flags.value)
            flags.require_tag = options.pop("require_tag", flags.require_tag)
            flags.hide_media_download_options = options.pop(
                "hide_media_download_options", flags.hide_media_download_options
            )
            options["flags"] = flags
        _apply_spoiler(self, options)

        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("ForumChannelPayload", payload),
            )
        return None


class VocalGuildChannel(discord.abc.Connectable, discord.abc.GuildChannel, Hashable):
    __slots__ = (
        "_overwrites",
        "_state",
        "_voice_start_time",
        "bitrate",
        "category_id",
        "flags",
        "guild_id",
        "id",
        "last_message_id",
        "name",
        "nsfw",
        "position",
        "rtc_region",
        "slowmode_delay",
        "status",
        "user_limit",
        "video_quality_mode",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: VoiceChannelPayload | StageChannelPayload,
    ) -> None:
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self.status: str | None = None
        self._voice_start_time: int | None = None
        self._update(guild, data)

    def _get_voice_client_key(self) -> tuple[int, str]:
        return self.guild.id, "guild_id"

    def _get_voice_state_pair(self) -> tuple[int, int]:
        return self.guild.id, self.id

    def _update(
        self,
        guild: Guild | PartialGuild,
        data: VoiceChannelPayload | StageChannelPayload,
    ) -> None:
        # This data will always exist
        self.guild_id: int = guild.id
        self.name: str = data["name"]
        self.category_id: int | None = utils._get_as_snowflake(data, "parent_id")

        # This data may be missing depending on how this object is being created/updated
        if not data.pop("_invoke_flag", False):
            rtc = data.get("rtc_region")
            self.rtc_region: VoiceRegion | None = (
                try_enum(VoiceRegion, rtc) if rtc is not None else None
            )
            self.video_quality_mode: VideoQualityMode = try_enum(
                VideoQualityMode, data.get("video_quality_mode", 1)
            )
            self.last_message_id: int | None = utils._get_as_snowflake(
                data, "last_message_id"
            )
            self.position: int = data.get("position")
            self.slowmode_delay = data.get("rate_limit_per_user", 0)
            self.bitrate: int = data.get("bitrate")
            self.user_limit: int = data.get("user_limit")
            self.flags: ChannelFlags = ChannelFlags._from_value(data.get("flags", 0))
            self.nsfw: bool = data.get("nsfw", False)
            self._fill_overwrites(data)

    def _update_status(
        self,
        *,
        status: str | None = MISSING,
        voice_start_time: int | None = MISSING,
    ) -> None:
        if status is not MISSING:
            self.status = status
        if voice_start_time is not MISSING:
            self._voice_start_time = voice_start_time

    @property
    def voice_start_time(self) -> dt.datetime | None:
        """Optional[:class:`datetime.datetime`]: The time the current voice session started, in UTC.

        ``None`` if there is no voice session or if the start time is not known,
        see :meth:`Guild.request_channel_info` and the ``cache_channel_info`` option of :class:`Client`.

        .. versionadded:: 3.0
        """
        if self._voice_start_time is None:
            return None
        return dt.datetime.fromtimestamp(self._voice_start_time, tz=dt.timezone.utc)

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.voice.value

    @property
    def members(self) -> list[Member]:
        """Returns all members that are currently inside this voice channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_members` there.
        """
        ret: list[Member] = []
        for user_id in self.voice_states:
            member = self._state._guild_bucket("members", self.guild_id).get_nowait(
                user_id
            )
            if member is not None:
                ret.append(member)
        return ret

    @property
    def voice_states(self) -> dict[int, VoiceState]:
        """Returns a mapping of member IDs who have voice states in this channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_voice_states` there.

        .. versionadded:: 1.3

        .. note::

            This function is intentionally low level to replace :attr:`members`
            when the member cache is unavailable.

        Returns
        -------
        Mapping[:class:`int`, :class:`VoiceState`]
            The mapping of member ID to a voice state.
        """
        states = self._state._guild_bucket("voice_states", self.guild_id).items_nowait()
        return {key: value for key, value in states if value.channel_id == self.id}

    async def get_members(self) -> list[Member]:
        """|coro|

        Returns all cached members that are currently inside this voice channel.

        Returns
        -------
        List[:class:`Member`]
            The members connected to this channel.
        """
        members = self._state._guild_bucket("members", self.guild_id)
        found = await members.get_many(list(await self.get_voice_states()))
        return list(found.values())

    async def get_voice_states(self) -> dict[int, VoiceState]:
        """|coro|

        Returns a mapping of member IDs who have voice states in this channel.

        .. versionadded:: 3.0

        .. note::

            This function is intentionally low level to replace :meth:`get_members`
            when the member cache is unavailable.

        Returns
        -------
        Mapping[:class:`int`, :class:`VoiceState`]
            The mapping of member ID to a voice state.
        """
        return {
            key: value
            for key, value in await self._state._guild_bucket(
                "voice_states", self.guild_id
            ).items()
            if value.channel_id == self.id
        }

    @staticmethod
    def _vocal_permissions(base: Permissions) -> Permissions:
        # Voice channels cannot be edited by people who can't connect to them.
        # It also implicitly denies all other voice perms
        if not base.connect:
            denied = Permissions.voice()
            denied.update(manage_channels=True, manage_roles=True)
            base.value &= ~denied.value
        return base

    @utils.copy_doc(discord.abc.GuildChannel.permissions_for)
    def permissions_for(self, obj: Member | Role, /) -> Permissions:
        return self._vocal_permissions(super().permissions_for(obj))

    async def get_permissions_for(self, obj: Member | Role, /) -> Permissions:
        return self._vocal_permissions(await super().get_permissions_for(obj))


class VoiceChannel(discord.abc.Messageable, VocalGuildChannel):
    """Represents a Discord guild voice channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    position: Optional[:class:`int`]
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0. Can be ``None`` if the channel was received in an interaction.
    bitrate: :class:`int`
        The channel's preferred audio bitrate in bits per second.
    user_limit: :class:`int`
        The channel's limit for number of members that can be in a voice channel.
    rtc_region: Optional[:class:`VoiceRegion`]
        The region for the voice channel's voice communication.
        A value of ``None`` indicates automatic voice region detection.

        .. versionadded:: 1.7
    video_quality_mode: :class:`VideoQualityMode`
        The camera video quality for the voice channel's participants.

        .. versionadded:: 2.0
    last_message_id: Optional[:class:`int`]
        The ID of the last message sent to this channel. It may not always point to an existing or valid message.

        .. versionadded:: 2.0
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this channel. A value of `0` denotes that it is disabled.
        Bots and users with :attr:`~Permissions.manage_channels` or
        :attr:`~Permissions.manage_messages` bypass slowmode.

        .. versionadded:: 2.5
    status: Optional[:class:`str`]
        The channel's status, if set.

        .. versionadded:: 2.5
    flags: :class:`ChannelFlags`
        Extra features of the channel.

        .. versionadded:: 2.0

    nsfw: :class:`bool`
        Whether the channel is marked as NSFW.

        .. versionadded:: 2.7
    """

    def _update(
        self,
        guild: Guild | PartialGuild,
        data: VoiceChannelPayload | StageChannelPayload,
    ) -> None:
        super()._update(guild, data)
        data = cast("VoiceChannelPayload", data)
        if data.get("status"):
            self.status = data.get("status")

    def __repr__(self) -> str:
        attrs = [
            ("id", self.id),
            ("name", self.name),
            ("status", self.status),
            ("rtc_region", self.rtc_region),
            ("position", self.position),
            ("bitrate", self.bitrate),
            ("video_quality_mode", self.video_quality_mode),
            ("user_limit", self.user_limit),
            ("category_id", self.category_id),
        ]
        joined = " ".join("{}={!r}".format(*t) for t in attrs)
        return f"<{self.__class__.__name__} {joined}>"

    async def _get_channel(self) -> VoiceChannel:
        return self

    def is_nsfw(self) -> bool:
        """Checks if the channel is NSFW."""
        return self.nsfw

    @property
    def spoiler(self) -> bool:
        """Checks if the channel is a spoiler channel.

        This is a shortcut for :attr:`ChannelFlags.is_spoiler_channel`.

        .. versionadded:: 3.0
        """
        return self.flags.is_spoiler_channel

    @property
    def last_message(self) -> Message | None:
        """Fetches the last message from this channel in cache.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_last_message` there.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return discord.abc.cached_message(self._state, self.last_message_id)

    async def get_last_message(self) -> Message | None:
        """|coro|

        Fetches the last message from this channel in cache.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return (
            await self._state._get_message(self.last_message_id)
            if self.last_message_id
            else None
        )

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        -------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)

    async def delete_messages(
        self, messages: Iterable[Snowflake], *, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes a list of messages. This is similar to :meth:`Message.delete`
        except it bulk deletes multiple messages.

        As a special case, if the number of messages is 0, then nothing
        is done. If the number of messages is 1 then single message
        delete is done. If it's more than two, then bulk delete is used.

        You cannot bulk delete more than 100 messages or messages that
        are older than 14 days old.

        You must have the :attr:`~Permissions.manage_messages` permission to
        use this.

        Parameters
        ----------
        messages: Iterable[:class:`abc.Snowflake`]
            An iterable of messages denoting which ones to bulk delete.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Raises
        ------
        ClientException
            The number of messages to delete was more than 100.
        Forbidden
            You do not have proper permissions to delete the messages.
        NotFound
            If single delete, then the message was already deleted.
        HTTPException
            Deleting the messages failed.
        """
        if not isinstance(messages, (list, tuple)):
            messages = list(messages)

        if len(messages) == 0:
            return  # do nothing

        if len(messages) == 1:
            message_id: int = messages[0].id
            await self._state.http.delete_message(self.id, message_id, reason=reason)
            return

        if len(messages) > 100:
            raise ClientException("Can only bulk delete messages up to 100 messages")

        message_ids: SnowflakeList = [m.id for m in messages]
        await self._state.http.delete_messages(self.id, message_ids, reason=reason)

    async def purge(
        self,
        *,
        limit: int | None = 100,
        check: Callable[[Message], bool] = MISSING,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        around: SnowflakeTime | None = None,
        oldest_first: bool | None = False,
        bulk: bool = True,
        reason: str | None = None,
    ) -> list[Message]:
        """|coro|

        Purges a list of messages that meet the criteria given by the predicate
        ``check``. If a ``check`` is not provided then all messages are deleted
        without discrimination.

        You must have the :attr:`~Permissions.manage_messages` permission to
        delete messages even if they are your own.
        The :attr:`~Permissions.read_message_history` permission is
        also needed to retrieve message history.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of messages to search through. This is not the number
            of messages that will be deleted, though it can be.
        check: Callable[[:class:`Message`], :class:`bool`]
            The function used to check if a message should be deleted.
            It must take a :class:`Message` as its sole parameter.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``before`` in :meth:`history`.
        after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``after`` in :meth:`history`.
        around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``around`` in :meth:`history`.
        oldest_first: Optional[:class:`bool`]
            Same as ``oldest_first`` in :meth:`history`.
        bulk: :class:`bool`
            If ``True``, use bulk delete. Setting this to ``False`` is useful for mass-deleting
            a bot's own messages without :attr:`Permissions.manage_messages`. When ``True``, will
            fall back to single delete if messages are older than two weeks.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Returns
        -------
        List[:class:`.Message`]
            The list of messages that were deleted.

        Raises
        ------
        Forbidden
            You do not have proper permissions to do the actions required.
        HTTPException
            Purging the messages failed.

        Examples
        --------
        Deleting bot's messages ::

            def is_me(m):
                return m.author == client.user


            deleted = await channel.purge(limit=100, check=is_me)
            await channel.send(f"Deleted {len(deleted)} message(s)")
        """
        return await discord.abc.purge_messages_helper(
            self,
            limit=limit,
            check=check,
            before=before,
            after=after,
            around=around,
            oldest_first=oldest_first,
            bulk=bulk,
            reason=reason,
        )

    async def webhooks(self) -> list[Webhook]:
        """|coro|

        Gets the list of webhooks from this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        Returns
        -------
        List[:class:`Webhook`]
            The webhooks for this channel.

        Raises
        ------
        Forbidden
            You don't have permissions to get the webhooks.
        """
        from .webhook import Webhook

        data = await self._state.http.channel_webhooks(self.id)
        return [Webhook.from_state(d, state=self._state) for d in data]

    async def create_webhook(
        self, *, name: str, avatar: bytes | None = None, reason: str | None = None
    ) -> Webhook:
        """|coro|

        Creates a webhook for this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        .. versionchanged:: 1.1
            Added the ``reason`` keyword-only parameter.

        Parameters
        ----------
        name: :class:`str`
            The webhook's name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's default avatar.
            This operates similarly to :meth:`~ClientUser.edit`.
        reason: Optional[:class:`str`]
            The reason for creating this webhook. Shows up in the audit logs.

        Returns
        -------
        :class:`Webhook`
            The created webhook.

        Raises
        ------
        HTTPException
            Creating the webhook failed.
        Forbidden
            You do not have permissions to create a webhook.
        """
        from .webhook import Webhook

        avatar_data = (
            utils._bytes_to_base64_data(avatar) if avatar is not None else None
        )

        data = await self._state.http.create_webhook(
            self.id, name=str(name), avatar=avatar_data, reason=reason
        )
        return Webhook.from_state(data, state=self._state)

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return ChannelType.voice

    @override
    @utils.copy_doc(discord.abc.GuildChannel.clone)
    async def clone(
        self, *, name: str | None = None, reason: str | None = None
    ) -> VoiceChannel:
        return await self._clone_impl(
            {"bitrate": self.bitrate, "user_limit": self.user_limit},
            name=name,
            reason=reason,
        )

    @overload
    async def edit(
        self,
        *,
        name: str = ...,
        bitrate: int = ...,
        user_limit: int = ...,
        position: int = ...,
        sync_permissions: bool = ...,
        category: CategoryChannel | None = ...,
        overwrites: Mapping[Role | Member, PermissionOverwrite] = ...,
        rtc_region: VoiceRegion | str | None = ...,
        video_quality_mode: VideoQualityMode = ...,
        slowmode_delay: int = ...,
        nsfw: bool = ...,
        reason: str | None = ...,
        spoiler: bool = ...,
    ) -> VoiceChannel | None: ...

    @overload
    async def edit(self) -> VoiceChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> VoiceChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        .. versionchanged:: 1.3
            The ``overwrites`` keyword-only parameter was added.

        .. versionchanged:: 2.0
            Edits are no longer in-place, the newly edited channel is returned instead.

        Parameters
        ----------
        name: :class:`str`
            The new channel's name.
        bitrate: :class:`int`
            The new channel's bitrate.
        user_limit: :class:`int`
            The new channel's user limit.
        position: :class:`int`
            The new channel's position.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.
        rtc_region: Optional[Union[:class:`str`, :class:`VoiceRegion`]]
            The new region ID for the voice channel's voice communication.
            A value of ``None`` indicates automatic voice region detection.
            Use :meth:`Guild.fetch_voice_regions` to get the available regions.

            .. versionadded:: 1.7

            .. versionchanged:: 3.0

                A region ID :class:`str` is now accepted.
        video_quality_mode: :class:`VideoQualityMode`
            The camera video quality for the voice channel's participants.

            .. versionadded:: 2.0

        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of `0` disables slowmode. The maximum value possible is `21600`.

        nsfw: :class:`bool`
            Whether the channel is marked as NSFW.

            .. versionadded:: 2.7
        spoiler: :class:`bool`
            Whether the channel is a spoiler channel, i.e. users must opt in to view its
            contents. Discord only allows this on channels that are not NSFW, and a
            warning is emitted if ``nsfw`` is also ``True``.

            .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`.VoiceChannel`]
            The newly edited voice channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        """
        _apply_spoiler(self, options)
        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("VoiceChannelPayload", payload),
            )
        return None

    async def create_activity_invite(
        self, activity: EmbeddedActivity | int, **kwargs: Any
    ) -> Invite:
        """|coro|

        A shortcut method that creates an instant activity invite.

        You must have the :attr:`~discord.Permissions.start_embedded_activities` permission to
        do this.

        Parameters
        ----------
        activity: Union[:class:`discord.EmbeddedActivity`, :class:`int`]
            The activity to create an invite for which can be an application id as well.
        max_age: :class:`int`
            How long the invite should last in seconds. If it's 0 then the invite
            doesn't expire. Defaults to ``0``.
        max_uses: :class:`int`
            How many uses the invite could be used for. If it's 0 then there
            are unlimited uses. Defaults to ``0``.
        temporary: :class:`bool`
            Denotes that the invite grants temporary membership
            (i.e. they get kicked after they disconnect). Defaults to ``False``.
        unique: :class:`bool`
            Indicates if a unique invite URL should be created. Defaults to True.
            If this is set to ``False`` then it will return a previously created
            invite.
        reason: Optional[:class:`str`]
            The reason for creating this invite. Shows up on the audit log.

        Returns
        -------
        :class:`~discord.Invite`
            The invite that was created.

        Raises
        ------
        TypeError
            If the activity is not a valid activity or application id.
        ~discord.HTTPException
            Invite creation failed.
        """
        if isinstance(activity, EmbeddedActivity):
            activity = activity.value

        elif not isinstance(activity, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Invalid type provided for the activity.")

        return await self.create_invite(
            target_type=InviteTarget.embedded_application,
            target_application_id=activity,
            **kwargs,
        )

    async def set_status(
        self, status: str | None, *, reason: str | None = None
    ) -> None:
        """|coro|

        Sets the status of the voice channel.

        You must have the :attr:`~Permissions.set_voice_channel_status` permission to use this.

        Parameters
        ----------
        status: Union[:class:`str`, None]
            The new status.
        reason: Optional[:class:`str`]
            The reason for setting the status. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have proper permissions to set the status.
        HTTPException
            Setting the status failed.
        """
        await self._state.http.set_voice_channel_status(self.id, status, reason=reason)

    async def send_soundboard_sound(self, sound: PartialSoundboardSound) -> None:
        """|coro|

        Sends a soundboard sound to the voice channel.

        Parameters
        ----------
        sound: :class:`PartialSoundboardSound`
            The soundboard sound to send.

        Raises
        ------
        Forbidden
            You do not have proper permissions to send the soundboard sound.
        HTTPException
            Sending the soundboard sound failed.
        """
        await self._state.http.send_soundboard_sound(self.id, sound)


class StageChannel(discord.abc.Messageable, VocalGuildChannel):
    """Represents a Discord guild stage channel.

    .. versionadded:: 1.7

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns the channel's name.

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild: :class:`Guild`
        The guild the channel belongs to.
    id: :class:`int`
        The channel ID.
    topic: Optional[:class:`str`]
        The channel's topic. ``None`` if it isn't set.
    category_id: Optional[:class:`int`]
        The category channel ID this channel belongs to, if applicable.
    position: Optional[:class:`int`]
        The position in the channel list. This is a number that starts at 0. e.g. the
        top channel is position 0. Can be ``None`` if the channel was received in an interaction.
    bitrate: :class:`int`
        The channel's preferred audio bitrate in bits per second.
    user_limit: :class:`int`
        The channel's limit for number of members that can be in a stage channel.
    rtc_region: Optional[:class:`VoiceRegion`]
        The region for the stage channel's voice communication.
        A value of ``None`` indicates automatic voice region detection.
    video_quality_mode: :class:`VideoQualityMode`
        The camera video quality for the stage channel's participants.

        .. versionadded:: 2.0
    flags: :class:`ChannelFlags`
        Extra features of the channel.

        .. versionadded:: 2.0
    last_message_id: Optional[:class:`int`]
        The ID of the last message sent to this channel. It may not always point to an existing or valid message.
        .. versionadded:: 2.5

    slowmode_delay: :class:`int`
        Specifies the slowmode rate limit for user in this channel, in seconds.
        The maximum value possible is `21600`.

    nsfw: :class:`bool`
        Whether the channel is marked as NSFW.

        .. versionadded:: 2.7
    """

    __slots__ = ("topic",)

    def _update(
        self,
        guild: Guild | PartialGuild,
        data: VoiceChannelPayload | StageChannelPayload,
    ) -> None:
        super()._update(guild, data)
        data = cast("StageChannelPayload", data)
        self.topic = data.get("topic")

    def __repr__(self) -> str:
        attrs = [
            ("id", self.id),
            ("name", self.name),
            ("topic", self.topic),
            ("rtc_region", self.rtc_region),
            ("position", self.position),
            ("bitrate", self.bitrate),
            ("video_quality_mode", self.video_quality_mode),
            ("user_limit", self.user_limit),
            ("category_id", self.category_id),
        ]
        joined = " ".join("{}={!r}".format(*t) for t in attrs)
        return f"<{self.__class__.__name__} {joined}>"

    @property
    def requesting_to_speak(self) -> list[Member]:
        """A list of members who are requesting to speak in the stage channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_requesting_to_speak` there.
        """
        return [
            member
            for member, voice in self._members_with_voice()
            if voice.requested_to_speak_at is not None
        ]

    @property
    def speakers(self) -> list[Member]:
        """A list of members who have been permitted to speak in the stage channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_speakers` there.

        .. versionadded:: 2.0
        """
        return [
            member
            for member, voice in self._members_with_voice()
            if not voice.suppress and voice.requested_to_speak_at is None
        ]

    @property
    def listeners(self) -> list[Member]:
        """A list of members who are listening in the stage channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_listeners` there.

        .. versionadded:: 2.0
        """
        return [
            member for member, voice in self._members_with_voice() if voice.suppress
        ]

    def _members_with_voice(self) -> list[tuple[Member, VoiceState]]:
        voice_states = self.voice_states
        found: list[tuple[Member, VoiceState]] = []
        for user_id, voice in voice_states.items():
            member = self._state._guild_bucket("members", self.guild_id).get_nowait(
                user_id
            )
            if member is not None:
                found.append((member, voice))
        return found

    async def _get_members_with_voice(self) -> list[tuple[Member, VoiceState]]:
        voice_states = await self.get_voice_states()
        members = self._state._guild_bucket("members", self.guild_id)
        found = await members.get_many(list(voice_states))
        return [(member, voice_states[user_id]) for user_id, member in found.items()]

    async def get_requesting_to_speak(self) -> list[Member]:
        """|coro|

        Returns the members who are requesting to speak in the stage channel.

        Returns
        -------
        List[:class:`Member`]
            The cached members who requested to speak.
        """
        return [
            member
            for member, voice in await self._get_members_with_voice()
            if voice.requested_to_speak_at is not None
        ]

    async def get_speakers(self) -> list[Member]:
        """|coro|

        Returns the members who have been permitted to speak in the stage channel.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`Member`]
            The cached members who can speak.
        """
        return [
            member
            for member, voice in await self._get_members_with_voice()
            if not voice.suppress and voice.requested_to_speak_at is None
        ]

    async def get_listeners(self) -> list[Member]:
        """|coro|

        Returns the members who are listening in the stage channel.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`Member`]
            The cached members who are listening.
        """
        return [
            member
            for member, voice in await self._get_members_with_voice()
            if voice.suppress
        ]

    async def _get_channel(self) -> StageChannel:
        return self

    def is_nsfw(self) -> bool:
        """Checks if the channel is NSFW."""
        return self.nsfw

    @property
    def last_message(self) -> Message | None:
        """Fetches the last message from this channel in cache.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_last_message` there.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return discord.abc.cached_message(self._state, self.last_message_id)

    async def get_last_message(self) -> Message | None:
        """|coro|

        Fetches the last message from this channel in cache.

        The message might not be valid or point to an existing message.

        .. admonition:: Reliable Fetching
            :class: helpful

            For a slightly more reliable method of fetching the
            last message, consider using either :meth:`history`
            or :meth:`fetch_message` with the :attr:`last_message_id`
            attribute.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return (
            await self._state._get_message(self.last_message_id)
            if self.last_message_id
            else None
        )

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        -------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)

    async def delete_messages(
        self, messages: Iterable[Snowflake], *, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes a list of messages. This is similar to :meth:`Message.delete`
        except it bulk deletes multiple messages.

        As a special case, if the number of messages is 0, then nothing
        is done. If the number of messages is 1 then single message
        delete is done. If it's more than two, then bulk delete is used.

        You cannot bulk delete more than 100 messages or messages that
        are older than 14 days old.

        You must have the :attr:`~Permissions.manage_messages` permission to
        use this.

        Parameters
        ----------
        messages: Iterable[:class:`abc.Snowflake`]
            An iterable of messages denoting which ones to bulk delete.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Raises
        ------
        ClientException
            The number of messages to delete was more than 100.
        Forbidden
            You do not have proper permissions to delete the messages.
        NotFound
            If single delete, then the message was already deleted.
        HTTPException
            Deleting the messages failed.
        """
        if not isinstance(messages, (list, tuple)):
            messages = list(messages)

        if len(messages) == 0:
            return  # do nothing

        if len(messages) == 1:
            message_id: int = messages[0].id
            await self._state.http.delete_message(self.id, message_id, reason=reason)
            return

        if len(messages) > 100:
            raise ClientException("Can only bulk delete messages up to 100 messages")

        message_ids: SnowflakeList = [m.id for m in messages]
        await self._state.http.delete_messages(self.id, message_ids, reason=reason)

    async def purge(
        self,
        *,
        limit: int | None = 100,
        check: Callable[[Message], bool] = MISSING,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        around: SnowflakeTime | None = None,
        oldest_first: bool | None = False,
        bulk: bool = True,
        reason: str | None = None,
    ) -> list[Message]:
        """|coro|

        Purges a list of messages that meet the criteria given by the predicate
        ``check``. If a ``check`` is not provided then all messages are deleted
        without discrimination.

        You must have the :attr:`~Permissions.manage_messages` permission to
        delete messages even if they are your own.
        The :attr:`~Permissions.read_message_history` permission is
        also needed to retrieve message history.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of messages to search through. This is not the number
            of messages that will be deleted, though it can be.
        check: Callable[[:class:`Message`], :class:`bool`]
            The function used to check if a message should be deleted.
            It must take a :class:`Message` as its sole parameter.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``before`` in :meth:`history`.
        after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``after`` in :meth:`history`.
        around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Same as ``around`` in :meth:`history`.
        oldest_first: Optional[:class:`bool`]
            Same as ``oldest_first`` in :meth:`history`.
        bulk: :class:`bool`
            If ``True``, use bulk delete. Setting this to ``False`` is useful for mass-deleting
            a bot's own messages without :attr:`Permissions.manage_messages`. When ``True``, will
            fall back to single delete if messages are older than two weeks.
        reason: Optional[:class:`str`]
            The reason for deleting the messages. Shows up on the audit log.

        Returns
        -------
        List[:class:`.Message`]
            The list of messages that were deleted.

        Raises
        ------
        Forbidden
            You do not have proper permissions to do the actions required.
        HTTPException
            Purging the messages failed.

        Examples
        --------
        Deleting bot's messages ::

            def is_me(m):
                return m.author == client.user


            deleted = await channel.purge(limit=100, check=is_me)
            await channel.send(f"Deleted {len(deleted)} message(s)")
        """
        return await discord.abc.purge_messages_helper(
            self,
            limit=limit,
            check=check,
            before=before,
            after=after,
            around=around,
            oldest_first=oldest_first,
            bulk=bulk,
            reason=reason,
        )

    async def webhooks(self) -> list[Webhook]:
        """|coro|

        Gets the list of webhooks from this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        Returns
        -------
        List[:class:`Webhook`]
            The webhooks for this channel.

        Raises
        ------
        Forbidden
            You don't have permissions to get the webhooks.
        """
        from .webhook import Webhook

        data = await self._state.http.channel_webhooks(self.id)
        return [Webhook.from_state(d, state=self._state) for d in data]

    async def create_webhook(
        self, *, name: str, avatar: bytes | None = None, reason: str | None = None
    ) -> Webhook:
        """|coro|

        Creates a webhook for this channel.

        Requires :attr:`~.Permissions.manage_webhooks` permissions.

        .. versionchanged:: 1.1
            Added the ``reason`` keyword-only parameter.

        Parameters
        ----------
        name: :class:`str`
            The webhook's name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's default avatar.
            This operates similarly to :meth:`~ClientUser.edit`.
        reason: Optional[:class:`str`]
            The reason for creating this webhook. Shows up in the audit logs.

        Returns
        -------
        :class:`Webhook`
            The created webhook.

        Raises
        ------
        HTTPException
            Creating the webhook failed.
        Forbidden
            You do not have permissions to create a webhook.
        """
        from .webhook import Webhook

        avatar_data = (
            utils._bytes_to_base64_data(avatar) if avatar is not None else None
        )

        data = await self._state.http.create_webhook(
            self.id, name=str(name), avatar=avatar_data, reason=reason
        )
        return Webhook.from_state(data, state=self._state)

    @property
    def moderators(self) -> list[Member]:
        """A list of members who are moderating the stage channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_moderators` there.

        .. versionadded:: 2.0
        """
        required_permissions = Permissions.stage_moderator()
        return [
            member
            for member in self.members
            if self.permissions_for(member) >= required_permissions
        ]

    async def get_moderators(self) -> list[Member]:
        """|coro|

        Returns the members who are moderating the stage channel.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`Member`]
            The cached members who are moderating.
        """
        required_permissions = Permissions.stage_moderator()
        return [
            member
            for member in await self.get_members()
            if await self.get_permissions_for(member) >= required_permissions
        ]

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return ChannelType.stage_voice

    @override
    @utils.copy_doc(discord.abc.GuildChannel.clone)
    async def clone(
        self, *, name: str | None = None, reason: str | None = None
    ) -> StageChannel:
        return await self._clone_impl({}, name=name, reason=reason)

    @property
    def instance(self) -> StageInstance | None:
        """The running stage instance of the stage channel.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_instance` there.

        .. versionadded:: 2.0
        """
        return utils.get(
            self._state._guild_bucket("stage_instances", self.guild_id).values_nowait(),
            channel_id=self.id,
        )

    async def get_instance(self) -> StageInstance | None:
        """|coro|

        Returns the running stage instance of the stage channel.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`StageInstance`]
            The cached stage instance, or ``None`` if there is none.
        """
        return utils.get(
            await self._state._guild_bucket("stage_instances", self.guild_id).values(),
            channel_id=self.id,
        )

    async def create_instance(
        self,
        *,
        topic: str,
        privacy_level: StagePrivacyLevel = MISSING,
        reason: str | None = None,
        send_notification: bool = False,
    ) -> StageInstance:
        """|coro|

        Create a stage instance.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        .. versionadded:: 2.0

        Parameters
        ----------
        topic: :class:`str`
            The stage instance's topic.
        privacy_level: :class:`StagePrivacyLevel`
            The stage instance's privacy level. Defaults to :attr:`StagePrivacyLevel.guild_only`.
        reason: :class:`str`
            The reason the stage instance was created. Shows up on the audit log.
        send_notification: :class:`bool`
            Send a notification to everyone in the server that the stage instance has started.
            Defaults to ``False``. Requires the ``mention_everyone`` permission.

        Returns
        -------
        :class:`StageInstance`
            The newly created stage instance.

        Raises
        ------
        InvalidArgument
            If the ``privacy_level`` parameter is not the proper type.
        Forbidden
            You do not have permissions to create a stage instance.
        HTTPException
            Creating a stage instance failed.
        """
        payload: dict[str, Any] = {
            "channel_id": self.id,
            "topic": topic,
            "send_start_notification": send_notification,
        }

        if privacy_level is not MISSING:
            if not isinstance(privacy_level, StagePrivacyLevel):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidArgument(
                    "privacy_level field must be of type PrivacyLevel"
                )

            payload["privacy_level"] = privacy_level.value

        data = await self._state.http.create_stage_instance(**payload, reason=reason)
        return StageInstance(guild=self.guild, state=self._state, data=data)

    async def fetch_instance(self) -> StageInstance:
        """|coro|

        Gets the running :class:`StageInstance`.

        .. versionadded:: 2.0

        Returns
        -------
        :class:`StageInstance`
            The stage instance.

        Raises
        ------
        NotFound
            The stage instance or channel could not be found.
        HTTPException
            Getting the stage instance failed.
        """
        data = await self._state.http.get_stage_instance(self.id)
        return await self._state._cache_fetched(
            StageInstance(guild=self.guild, state=self._state, data=data)
        )

    @overload
    async def edit(
        self,
        *,
        name: str = ...,
        topic: str | None = ...,
        position: int = ...,
        sync_permissions: bool = ...,
        category: CategoryChannel | None = ...,
        overwrites: Mapping[Role | Member, PermissionOverwrite] = ...,
        rtc_region: VoiceRegion | str | None = ...,
        video_quality_mode: VideoQualityMode = ...,
        bitrate: int = ...,
        user_limit: int = ...,
        slowmode_delay: int = ...,
        reason: str | None = ...,
    ) -> StageChannel | None: ...

    @overload
    async def edit(self) -> StageChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> StageChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        .. versionchanged:: 2.0
            The ``topic`` parameter must now be set via :attr:`create_instance`.

        .. versionchanged:: 2.0
            Edits are no longer in-place, the newly edited channel is returned instead.

        Parameters
        ----------
        name: :class:`str`
            The new channel's name.
        position: :class:`int`
            The new channel's position.
        sync_permissions: :class:`bool`
            Whether to sync permissions with the channel's new or pre-existing
            category. Defaults to ``False``.
        category: Optional[:class:`CategoryChannel`]
            The new category for this channel. Can be ``None`` to remove the
            category.
        reason: Optional[:class:`str`]
            The reason for editing this channel. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.
        rtc_region: Optional[Union[:class:`str`, :class:`VoiceRegion`]]
            The new region ID for the stage channel's voice communication.
            A value of ``None`` indicates automatic voice region detection.
            Use :meth:`Guild.fetch_voice_regions` to get the available regions.

            .. versionchanged:: 3.0

                A region ID :class:`str` is now accepted.
        video_quality_mode: :class:`VideoQualityMode`
            The camera video quality for the stage channel's participants.

            .. versionadded:: 2.0

        bitrate: :class:`int`
            The channel's preferred audio bitrate in bits per second.

        user_limit: :class:`int`
            The channel's limit for number of members that can be in a stage channel.

        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this channel, in seconds.
            A value of `0` disables slowmode. The maximum value possible is `21600`.

        Returns
        -------
        Optional[:class:`.StageChannel`]
            The newly edited stage channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If the permission overwrite information is not in proper form.
        Forbidden
            You do not have permissions to edit the channel.
        HTTPException
            Editing the channel failed.
        """
        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("StageChannelPayload", payload),
            )
        return None


class CategoryChannel(discord.abc.GuildChannel, Hashable):
    """Represents a Discord channel category.

    These are useful to group channels to logical compartments.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the category's hash.

        .. describe:: str(x)

            Returns the category's name.

    Attributes
    ----------
    name: :class:`str`
        The category name.
    guild: :class:`Guild`
        The guild the category belongs to.
    id: :class:`int`
        The category channel ID.
    position: Optional[:class:`int`]
        The position in the category list. This is a number that starts at 0. e.g. the
        top category is position 0. Can be ``None`` if the channel was received in an interaction.

    flags: :class:`ChannelFlags`
        Extra features of the channel.

        .. versionadded:: 2.0
    """

    __slots__ = (
        "_overwrites",
        "_state",
        "category_id",
        "flags",
        "guild_id",
        "id",
        "name",
        "position",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: CategoryChannelPayload,
    ) -> None:
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self._update(guild, data)

    def __repr__(self) -> str:
        return f"<CategoryChannel id={self.id} name={self.name!r} position={self.position}>"

    def _update(
        self, guild: Guild | PartialGuild, data: CategoryChannelPayload
    ) -> None:
        # This data will always exist
        self.guild_id: int = guild.id
        self.name: str = data["name"]
        self.category_id: int | None = utils._get_as_snowflake(data, "parent_id")

        # This data may be missing depending on how this object is being created/updated
        if not data.pop("_invoke_flag", False):
            self.position: int = data.get("position")
            self.flags: ChannelFlags = ChannelFlags._from_value(data.get("flags", 0))
            self._fill_overwrites(data)

    @property
    def _sorting_bucket(self) -> int:
        return ChannelType.category.value

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return ChannelType.category

    @override
    @utils.copy_doc(discord.abc.GuildChannel.clone)
    async def clone(
        self, *, name: str | None = None, reason: str | None = None
    ) -> CategoryChannel:
        return await self._clone_impl({}, name=name, reason=reason)

    @overload
    async def edit(
        self,
        *,
        name: str = ...,
        position: int = ...,
        overwrites: Mapping[Role | Member, PermissionOverwrite] = ...,
        reason: str | None = ...,
    ) -> CategoryChannel | None: ...

    @overload
    async def edit(self) -> CategoryChannel | None: ...

    async def edit(
        self, *, reason: str | None = None, **options: Any
    ) -> CategoryChannel | None:
        """|coro|

        Edits the channel.

        You must have the :attr:`~Permissions.manage_channels` permission to
        use this.

        .. versionchanged:: 1.3
            The ``overwrites`` keyword-only parameter was added.

        .. versionchanged:: 2.0
            Edits are no longer in-place, the newly edited channel is returned instead.

        Parameters
        ----------
        name: :class:`str`
            The new category's name.
        position: :class:`int`
            The new category's position.
        reason: Optional[:class:`str`]
            The reason for editing this category. Shows up on the audit log.
        overwrites: Dict[Union[:class:`Role`, :class:`Member`, :class:`~discord.abc.Snowflake`], :class:`PermissionOverwrite`]
            The overwrites to apply to channel permissions. Useful for creating secret channels.

        Returns
        -------
        Optional[:class:`.CategoryChannel`]
            The newly edited category channel. If the edit was only positional
            then ``None`` is returned instead.

        Raises
        ------
        InvalidArgument
            If position is less than 0 or greater than the number of categories.
        Forbidden
            You do not have permissions to edit the category.
        HTTPException
            Editing the category failed.
        """
        payload = await self._edit(options, reason=reason)
        if payload is not None:
            # the payload will always be the proper channel payload
            return self.__class__(
                state=self._state,
                guild=self.guild,
                data=cast("CategoryChannelPayload", payload),
            )
        return None

    @override
    @utils.copy_doc(discord.abc.GuildChannel.move)
    async def move(self, **kwargs: Any) -> None:
        kwargs.pop("category", None)
        await super().move(**kwargs)

    def _cached_category_channels(self) -> list[GuildChannelType]:
        return [
            c
            for c in self._state._guild_bucket(
                "channels", self.guild_id
            ).values_nowait()
            if c.category_id == self.id
        ]

    @property
    def channels(self) -> list[GuildChannelType]:
        """Returns the channels that are under this category.

        These are sorted by the official Discord UI, which places voice channels below the text channels.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_channels` there.
        """

        def comparator(channel: GuildChannelType) -> tuple[bool, int]:
            return not isinstance(channel, _TextChannel), (channel.position or -1)

        ret = self._cached_category_channels()
        ret.sort(key=comparator)
        return ret

    def _sorted_of(self, kind: type) -> list[Any]:
        ret = [c for c in self._cached_category_channels() if isinstance(c, kind)]
        ret.sort(key=lambda c: (c.position or -1, c.id))
        return ret

    @property
    def text_channels(self) -> list[TextChannel]:
        """Returns the text channels that are under this category.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_text_channels` there.
        """
        return self._sorted_of(TextChannel)

    @property
    def voice_channels(self) -> list[VoiceChannel]:
        """Returns the voice channels that are under this category.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_voice_channels` there.
        """
        return self._sorted_of(VoiceChannel)

    @property
    def stage_channels(self) -> list[StageChannel]:
        """Returns the stage channels that are under this category.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_stage_channels` there.

        .. versionadded:: 1.7
        """
        return self._sorted_of(StageChannel)

    @property
    def forum_channels(self) -> list[ForumChannel]:
        """Returns the forum channels that are under this category.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_forum_channels` there.

        .. versionadded:: 2.0
        """
        return self._sorted_of(ForumChannel)

    async def get_channels(self) -> list[GuildChannelType]:
        """|coro|

        Returns the channels that are under this category.

        These are sorted by the official Discord UI, which places voice channels below the text channels.

        Returns
        -------
        List[:class:`abc.GuildChannel`]
            The cached channels of this category.
        """

        def comparator(channel: GuildChannelType) -> tuple[bool, int]:
            return not isinstance(channel, _TextChannel), (channel.position or -1)

        ret = [c for c in await self._get_cached_channels() if c.category_id == self.id]
        ret.sort(key=comparator)
        return ret

    async def get_text_channels(self) -> list[TextChannel]:
        """|coro|

        Returns the text channels that are under this category.

        Returns
        -------
        List[:class:`TextChannel`]
            The cached text channels of this category.
        """
        ret = [
            c
            for c in await self._get_cached_channels()
            if c.category_id == self.id and isinstance(c, TextChannel)
        ]
        ret.sort(key=lambda c: (c.position or -1, c.id))
        return ret

    async def get_voice_channels(self) -> list[VoiceChannel]:
        """|coro|

        Returns the voice channels that are under this category.

        Returns
        -------
        List[:class:`VoiceChannel`]
            The cached voice channels of this category.
        """
        ret = [
            c
            for c in await self._get_cached_channels()
            if c.category_id == self.id and isinstance(c, VoiceChannel)
        ]
        ret.sort(key=lambda c: (c.position or -1, c.id))
        return ret

    async def get_stage_channels(self) -> list[StageChannel]:
        """|coro|

        Returns the stage channels that are under this category.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`StageChannel`]
            The cached stage channels of this category.
        """
        ret = [
            c
            for c in await self._get_cached_channels()
            if c.category_id == self.id and isinstance(c, StageChannel)
        ]
        ret.sort(key=lambda c: (c.position or -1, c.id))
        return ret

    async def get_forum_channels(self) -> list[ForumChannel]:
        """|coro|

        Returns the forum channels that are under this category.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`ForumChannel`]
            The cached forum channels of this category.
        """
        ret = [
            c
            for c in await self._get_cached_channels()
            if c.category_id == self.id and isinstance(c, ForumChannel)
        ]
        ret.sort(key=lambda c: (c.position or -1, c.id))
        return ret

    async def create_text_channel(self, name: str, **options: Any) -> TextChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_text_channel` to create a :class:`TextChannel` in the category.

        Returns
        -------
        :class:`TextChannel`
            The channel that was just created.
        """
        return await self.guild.create_text_channel(name, category=self, **options)

    async def create_voice_channel(self, name: str, **options: Any) -> VoiceChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_voice_channel` to create a :class:`VoiceChannel` in the category.

        Returns
        -------
        :class:`VoiceChannel`
            The channel that was just created.
        """
        return await self.guild.create_voice_channel(name, category=self, **options)

    async def create_stage_channel(self, name: str, **options: Any) -> StageChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_stage_channel` to create a :class:`StageChannel` in the category.

        .. versionadded:: 1.7

        Returns
        -------
        :class:`StageChannel`
            The channel that was just created.
        """
        return await self.guild.create_stage_channel(name, category=self, **options)

    async def create_forum_channel(self, name: str, **options: Any) -> ForumChannel:
        """|coro|

        A shortcut method to :meth:`Guild.create_forum_channel` to create a :class:`ForumChannel` in the category.

        .. versionadded:: 2.0

        Returns
        -------
        :class:`ForumChannel`
            The channel that was just created.
        """
        return await self.guild.create_forum_channel(name, category=self, **options)

    @deprecated(
        "CategoryChannel.is_nsfw is deprecated since version 2.7 and will be removed in version 3.0. NSFW categories are not available in the Discord API."
    )
    def is_nsfw(self) -> bool:
        """Checks if the category is NSFW, which is always ``False``."""
        return False

    # TODO: Remove in 3.0

    @property
    @deprecated(
        "CategoryChannel.nsfw is deprecated since version 2.7 and will be removed in version 3.0. NSFW categories are not available in the Discord API."
    )
    def nsfw(self) -> bool:
        """Whether the category is NSFW, which is always ``False``."""
        return False


DMC = TypeVar("DMC", bound="DMChannel")


class DMChannel(discord.abc.Messageable, Hashable):
    """Represents a Discord direct message channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns a string representation of the channel

    Attributes
    ----------
    recipient: Optional[:class:`User`]
        The user you are participating with in the direct message channel.
        If this channel is received through the gateway, the recipient information
        may not be always available.
    me: :class:`ClientUser`
        The user presenting yourself.
    id: :class:`int`
        The direct message channel ID.
    """

    __slots__ = ("_state", "id", "me", "recipient")

    def __init__(
        self, *, me: ClientUser, state: ConnectionState, data: DMChannelPayload
    ) -> None:
        self._state: ConnectionState = state
        self.recipient: User | None = None
        if r := data.get("recipients"):
            self.recipient = state.create_user(r[0])
        self.me: ClientUser = me
        self.id: int = int(data["id"])

    async def _get_channel(self) -> DMChannel:
        return self

    def __str__(self) -> str:
        if self.recipient:
            return f"Direct Message with {self.recipient}"
        return "Direct Message with Unknown User"

    def __repr__(self) -> str:
        return f"<DMChannel id={self.id} recipient={self.recipient!r}>"

    @classmethod
    def _from_message(cls: type[DMC], state: ConnectionState, channel_id: int) -> DMC:
        self: DMC = cls.__new__(cls)
        self._state = state
        self.id = channel_id
        self.recipient = None
        # state.user won't be None here
        self.me = cast("ClientUser", state.user)
        return self

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return ChannelType.private

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to the channel.

        .. versionadded:: 2.0
        """
        return f"https://discord.com/channels/@me/{self.id}"

    @property
    def created_at(self) -> dt.datetime:
        """Returns the direct message channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def permissions_for(self, obj: Any = None, /) -> Permissions:
        """Handles permission resolution for a :class:`User`.

        This function is there for compatibility with other channel types.

        Actual direct messages do not really have the concept of permissions.

        This returns all the Text related permissions set to ``True`` except:

        - :attr:`~Permissions.send_tts_messages`: You cannot send TTS messages in a DM.
        - :attr:`~Permissions.manage_messages`: You cannot delete others messages in a DM.

        Parameters
        ----------
        obj: :class:`User`
            The user to check permissions for. This parameter is ignored
            but kept for compatibility with other ``permissions_for`` methods.

        Returns
        -------
        :class:`Permissions`
            The resolved permissions.
        """
        base = Permissions.text()
        base.read_messages = True
        base.send_tts_messages = False
        base.manage_messages = False
        return base

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        -------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)


class GroupChannel(discord.abc.Messageable, Hashable):
    """Represents a Discord group channel.

    .. container:: operations

        .. describe:: x == y

            Checks if two channels are equal.

        .. describe:: x != y

            Checks if two channels are not equal.

        .. describe:: hash(x)

            Returns the channel's hash.

        .. describe:: str(x)

            Returns a string representation of the channel

    Attributes
    ----------
    recipients: List[:class:`User`]
        The users you are participating with in the group channel.
    me: :class:`ClientUser`
        The user presenting yourself.
    id: :class:`int`
        The group channel ID.
    owner: Optional[:class:`User`]
        The user that owns the group channel.
    owner_id: :class:`int`
        The owner ID that owns the group channel.

        .. versionadded:: 2.0
    name: Optional[:class:`str`]
        The group channel's name if provided.
    """

    __slots__ = (
        "_icon",
        "_state",
        "id",
        "me",
        "name",
        "owner",
        "owner_id",
        "recipients",
    )

    def __init__(
        self, *, me: ClientUser, state: ConnectionState, data: GroupChannelPayload
    ) -> None:
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self.me: ClientUser = me
        self._update_group(data)

    def _update_group(self, data: GroupChannelPayload) -> None:
        self.owner_id: int | None = utils._get_as_snowflake(data, "owner_id")
        self._icon: str | None = data.get("icon")
        self.name: str | None = data.get("name")
        self.recipients: list[User] = [
            self._state.create_user(u) for u in data.get("recipients", [])
        ]

        self.owner: BaseUser | None
        if self.owner_id == self.me.id:
            self.owner = self.me
        else:
            self.owner = utils.find(lambda u: u.id == self.owner_id, self.recipients)

    async def _get_channel(self) -> GroupChannel:
        return self

    def __str__(self) -> str:
        if self.name:
            return self.name

        if len(self.recipients) == 0:
            return "Unnamed"

        return ", ".join(x.name for x in self.recipients)

    def __repr__(self) -> str:
        return f"<GroupChannel id={self.id} name={self.name!r}>"

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return ChannelType.group

    @property
    def icon(self) -> Asset | None:
        """Returns the channel's icon asset if available."""
        if self._icon is None:
            return None
        return Asset._from_icon(self._state, self.id, self._icon, path="channel")

    @property
    def created_at(self) -> dt.datetime:
        """Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to the channel.

        .. versionadded:: 2.0
        """
        return f"https://discord.com/channels/@me/{self.id}"

    def permissions_for(self, obj: Snowflake, /) -> Permissions:
        """Handles permission resolution for a :class:`User`.

        This function is there for compatibility with other channel types.

        Actual direct messages do not really have the concept of permissions.

        This returns all the Text related permissions set to ``True`` except:

        - :attr:`~Permissions.send_tts_messages`: You cannot send TTS messages in a DM.
        - :attr:`~Permissions.manage_messages`: You cannot delete others messages in a DM.

        This also checks the kick_members permission if the user is the owner.

        Parameters
        ----------
        obj: :class:`~discord.abc.Snowflake`
            The user to check permissions for.

        Returns
        -------
        :class:`Permissions`
            The resolved permissions for the user.
        """
        base = Permissions.text()
        base.read_messages = True
        base.send_tts_messages = False
        base.manage_messages = False
        base.mention_everyone = True

        if obj.id == self.owner_id:
            base.kick_members = True

        return base

    async def leave(self) -> None:
        """|coro|

        Leave the group.

        If you are the only one in the group, this deletes it as well.

        Raises
        ------
        HTTPException
            Leaving the group failed.
        """
        await self._state.http.leave_group(self.id)


class PartialMessageable(discord.abc.Messageable, Hashable):
    """Represents a partial messageable to aid with working messageable channels when only a channel ID are present.

    The only way to construct this class is through :meth:`Client.get_partial_messageable`.

    Note that this class is trimmed down and has no rich attributes.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: x == y

            Checks if two partial messageables are equal.

        .. describe:: x != y

            Checks if two partial messageables are not equal.

        .. describe:: hash(x)

            Returns the partial messageable's hash.

    Attributes
    ----------
    id: :class:`int`
        The channel ID associated with this partial messageable.
    type: Optional[:class:`ChannelType`]
        The channel type associated with this partial messageable, if given.
    """

    __slots__ = ("_channel", "_state", "id", "type")

    def __init__(
        self, state: ConnectionState, id: int, type: ChannelType | None = None
    ) -> None:
        self._state: ConnectionState = state
        self._channel: Object = Object(id=id)
        self.id: int = id
        self.type: ChannelType | None = type

    async def _get_channel(self) -> MessageableChannel:
        return cast("MessageableChannel", self._channel)

    async def get(self) -> MessageableChannel | None:
        """|coro|

        Returns the cached channel.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`TextChannel`, :class:`VoiceChannel`, :class:`StageChannel`, :class:`DMChannel`, :class:`GroupChannel`, :class:`Thread`]]
            The channel, or ``None`` if it is not cached.
        """
        return cast("MessageableChannel | None", await self._state.get_channel(self.id))

    async def fetch(self) -> MessageableChannel:
        """|coro|

        Fetches the channel from the API.

        .. versionadded:: 3.0

        Returns
        -------
        Union[:class:`TextChannel`, :class:`VoiceChannel`, :class:`StageChannel`, :class:`DMChannel`, :class:`GroupChannel`, :class:`Thread`]
            The channel.

        Raises
        ------
        InvalidData
            An unknown channel type was received from Discord.
        NotFound
            Invalid channel ID.
        Forbidden
            You do not have permission to fetch this channel.
        HTTPException
            Retrieving the channel failed.
        """
        return cast("MessageableChannel", await self._state._fetch_channel(self.id))

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to create a partial message for.

        Returns
        -------
        :class:`PartialMessage`
            The partial message.
        """
        from .message import PartialMessage

        return PartialMessage(channel=self, id=message_id)

    def __repr__(self) -> str:
        return f"<PartialMessageable id={self.id} type={self.type!r}>"


class PartialGuildChannel(Hashable):
    """Represents a lightweight handle to a guild channel that is only known by its IDs.

    Relationship attributes pointing to channels that cannot send messages,
    such as :attr:`VoiceState.channel`, return this type. Use :meth:`get` to
    get the cached channel.

    .. versionadded:: 3.0

    .. container:: operations

        .. describe:: x == y

            Checks if two partial guild channels are equal.

        .. describe:: x != y

            Checks if two partial guild channels are not equal.

        .. describe:: hash(x)

            Returns the partial guild channel's hash.

    Attributes
    ----------
    id: :class:`int`
        The channel's ID.
    guild_id: :class:`int`
        The ID of the guild the channel belongs to.
    type: Optional[:class:`ChannelType`]
        The channel's type, if known.
    """

    __slots__ = ("_state", "guild_id", "id", "type")

    def __init__(
        self,
        *,
        state: ConnectionState,
        id: int,
        guild_id: int,
        type: ChannelType | None = None,
    ) -> None:
        self._state: ConnectionState = state
        self.id: int = id
        self.guild_id: int = guild_id
        self.type: ChannelType | None = type

    def __repr__(self) -> str:
        return f"<PartialGuildChannel id={self.id} guild_id={self.guild_id} type={self.type!r}>"

    @property
    def guild(self) -> PartialGuild:
        """A handle to the guild the channel belongs to."""
        from .guild import PartialGuild

        return PartialGuild(state=self._state, id=self.guild_id)

    async def get(self) -> GuildChannelType | Thread | None:
        """|coro|

        Returns the cached channel.

        Returns
        -------
        Optional[Union[:class:`abc.GuildChannel`, :class:`Thread`]]
            The channel, or ``None`` if it is not cached.
        """
        return await self._state._resolve_guild_channel(self.guild_id, self.id)

    async def fetch(self) -> GuildChannelType | Thread:
        """|coro|

        Fetches the channel from the API.

        Returns
        -------
        Union[:class:`abc.GuildChannel`, :class:`Thread`]
            The channel.

        Raises
        ------
        InvalidData
            The channel resolved to a private channel or another guild.
        NotFound
            Invalid channel ID.
        Forbidden
            You do not have permission to fetch this channel.
        HTTPException
            Retrieving the channel failed.
        """
        return await self.guild.fetch_channel(self.id)


class VoiceChannelEffectAnimation(NamedTuple):
    """Represents an animation that can be sent to a voice channel.

    .. versionadded:: 2.7
    """

    id: int
    type: VoiceChannelEffectAnimationType


class VoiceChannelSoundEffect(PartialSoundboardSound): ...


class VoiceChannelEffectSendEvent:
    """Represents the payload for an :func:`on_voice_channel_effect_send`.

    .. versionadded:: 2.7

    Attributes
    ----------
    animation_type: Optional[:class:`VoiceChannelEffectAnimationType`]
        The type of animation that is being sent, if any.
    animation_id: Optional[:class:`int`]
        The ID of the animation that is being sent, if any.
    sound: Optional[:class:`SoundboardSound`]
        The sound that is being sent, could be ``None`` if the effect is not a sound effect.
    guild_id: :class:`int`
        The ID of the guild in which the sound is being sent.
    user_id: :class:`int`
        The ID of the member that sent the sound.
    channel_id: :class:`int`
        The ID of the voice channel in which the sound is being sent.
    user: Optional[:class:`Member`]
        The member that sent the sound, if cached.
    channel: Optional[:class:`VoiceChannel`]
        The voice channel in which the sound is being sent, if cached.
    data: :class:`dict`
        The raw data sent by the gateway.
    """

    __slots__ = (
        "_state",
        "animation_id",
        "animation_type",
        "channel",
        "channel_id",
        "data",
        "emoji",
        "guild_id",
        "sound",
        "user",
        "user_id",
    )

    def __init__(
        self,
        data: VoiceChannelEffectSend,
        state: ConnectionState,
        sound: SoundboardSound | PartialSoundboardSound | None = None,
        *,
        user: Member | None = None,
        channel: VoiceChannel | None = None,
    ) -> None:
        self._state = state
        self.channel_id: int = int(data["channel_id"])
        self.user_id: int = int(data["user_id"])
        self.guild_id: int = int(data["guild_id"])
        animation_type = data.get("animation_type")
        self.animation_type: VoiceChannelEffectAnimationType | None = (
            try_enum(VoiceChannelEffectAnimationType, animation_type)
            if animation_type is not None
            else None
        )
        self.animation_id = (
            int(data["animation_id"]) if "animation_id" in data else None
        )
        self.sound = sound
        self.user = user
        self.channel = channel
        emoji_data = data.get("emoji", None)
        self.emoji = (
            PartialEmoji(
                name=emoji_data["name"],
                animated=emoji_data.get("animated", False),
                id=cast("int | None", emoji_data["id"]),
            )
            if emoji_data
            else None
        )
        self.data = data

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild in which the sound is being sent.

        This is the cached guild with the in-process cache, and a
        :class:`PartialGuild` handle when it is not cached or the cache backend
        is not the in-process one.
        """
        cached = cached_guild(self._state, self.guild_id)
        if cached is not None:
            return cached
        from .guild import PartialGuild

        return PartialGuild(state=self._state, id=self.guild_id)


def _guild_channel_factory(
    channel_type: int,
) -> tuple[
    type[
        TextChannel
        | VoiceChannel
        | CategoryChannel
        | StageChannel
        | ForumChannel
        | MediaChannel
    ]
    | None,
    ChannelType,
]:
    value = try_enum(ChannelType, channel_type)
    if value is ChannelType.text:
        return TextChannel, value
    if value is ChannelType.voice:
        return VoiceChannel, value
    if value is ChannelType.category:
        return CategoryChannel, value
    if value is ChannelType.news:
        return TextChannel, value
    if value is ChannelType.stage_voice:
        return StageChannel, value
    if value is ChannelType.directory:
        return None, value  # TODO: Add DirectoryChannel when applicable
    if value is ChannelType.forum:
        return ForumChannel, value
    if value is ChannelType.media:
        return MediaChannel, value
    return None, value


def _channel_factory(
    channel_type: int,
) -> tuple[
    type[
        TextChannel
        | VoiceChannel
        | CategoryChannel
        | StageChannel
        | ForumChannel
        | MediaChannel
        | DMChannel
        | GroupChannel
    ]
    | None,
    ChannelType,
]:
    cls, value = _guild_channel_factory(channel_type)
    if value is ChannelType.private:
        return DMChannel, value
    if value is ChannelType.group:
        return GroupChannel, value
    return cls, value


def _threaded_channel_factory(  # pyright: ignore[reportUnusedFunction]
    channel_type: int,
) -> tuple[
    type[
        TextChannel
        | VoiceChannel
        | CategoryChannel
        | StageChannel
        | ForumChannel
        | MediaChannel
        | DMChannel
        | GroupChannel
        | Thread
    ]
    | None,
    ChannelType,
]:
    cls, value = _channel_factory(channel_type)
    if value in (
        ChannelType.private_thread,
        ChannelType.public_thread,
        ChannelType.news_thread,
    ):
        return Thread, value
    return cls, value


def _threaded_guild_channel_factory(  # pyright: ignore[reportUnusedFunction]
    channel_type: int,
) -> tuple[
    type[
        TextChannel
        | VoiceChannel
        | CategoryChannel
        | StageChannel
        | ForumChannel
        | MediaChannel
        | Thread
    ]
    | None,
    ChannelType,
]:
    cls, value = _guild_channel_factory(channel_type)
    if value in (
        ChannelType.private_thread,
        ChannelType.public_thread,
        ChannelType.news_thread,
    ):
        return Thread, value
    return cls, value
