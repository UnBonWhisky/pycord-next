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

import contextlib
from typing import TYPE_CHECKING, cast

from ._internal.cache_peek import cached_channel
from .abc import (
    Messageable,
    cached_message,
    purge_messages_helper,
)
from .enums import (
    ChannelType,
    ThreadArchiveDuration as ThreadArchiveDurationEnum,
    try_enum,
)
from .errors import ClientException
from .flags import ChannelFlags
from .mixins import Hashable
from .utils import MISSING, _get_as_snowflake, parse_time

__all__ = (
    "Thread",
    "ThreadMember",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .abc import Snowflake, SnowflakeTime
    from .channel import (
        CategoryChannel,
        ForumChannel,
        ForumTag,
        PartialGuildChannel,
        PartialMessageable,
        TextChannel,
    )
    from .guild import Guild, PartialGuild
    from .member import Member
    from .message import Message, PartialMessage
    from .permissions import Permissions
    from .role import Role
    from .state import ConnectionState
    from .types.raw_models import ThreadMemberUpdateEvent
    from .types.snowflake import SnowflakeList
    from .types.threads import (
        Thread as ThreadPayload,
        ThreadArchiveDuration,
        ThreadMember as ThreadMemberPayload,
        ThreadMetadata,
    )


class Thread(Messageable, Hashable):
    """Represents a Discord thread.

    .. container:: operations

        .. describe:: x == y

            Checks if two threads are equal.

        .. describe:: x != y

            Checks if two threads are not equal.

        .. describe:: hash(x)

            Returns the thread's hash.

        .. describe:: str(x)

            Returns the thread's name.

    .. versionadded:: 2.0

    Attributes
    ----------
    name: :class:`str`
        The thread name.
    guild: :class:`Guild`
        The guild the thread belongs to.
    id: :class:`int`
        The thread ID.

        .. note::
            This ID is the same as the thread starting message ID.

    parent_id: :class:`int`
        The parent :class:`TextChannel` ID this thread belongs to.
    owner_id: :class:`int`
        The user's ID that created this thread.
    last_message_id: Optional[:class:`int`]
        The last message ID of the message sent to this thread. It may
        *not* point to an existing or valid message.
    slowmode_delay: :class:`int`
        The number of seconds a member must wait between sending messages
        in this thread. A value of `0` denotes that it is disabled.
        Bots and users with :attr:`~Permissions.manage_channels` or
        :attr:`~Permissions.manage_messages` bypass slowmode.
    message_count: :class:`int`
        An approximate number of messages in this thread. This caps at 50.
    member_count: :class:`int`
        An approximate number of members in this thread. This caps at 50.
    me: Optional[:class:`ThreadMember`]
        A thread member representing yourself, if you've joined the thread.
        This could not be available.
    archived: :class:`bool`
        Whether the thread is archived.
    locked: :class:`bool`
        Whether the thread is locked.
    invitable: :class:`bool`
        Whether non-moderators can add other non-moderators to this thread.
        This is always ``True`` for public threads.
    auto_archive_duration: :class:`int`
        The duration in minutes until the thread is automatically archived due to inactivity.
        Usually a value of 60, 1440, 4320 and 10080.
    archive_timestamp: :class:`datetime.datetime`
        An aware timestamp of when the thread's archived status was last updated in UTC.
    created_at: Optional[:class:`datetime.datetime`]
        An aware timestamp of when the thread was created.
        Only available for threads created after 2022-01-09.
    flags: :class:`ChannelFlags`
        Extra features of the thread.

        .. versionadded:: 2.0
    total_message_sent: :class:`int`
        Number of messages ever sent in a thread.
        It's similar to message_count on message creation,
        but will not decrement the number when a message is deleted.

        .. versionadded:: 2.3
    """

    __slots__ = (
        "_applied_tags",
        "_state",
        "_type",
        "archive_timestamp",
        "archived",
        "auto_archive_duration",
        "created_at",
        "flags",
        "guild_id",
        "id",
        "invitable",
        "last_message_id",
        "locked",
        "me",
        "member_count",
        "message_count",
        "name",
        "owner_id",
        "parent_id",
        "slowmode_delay",
        "total_message_sent",
    )

    def __init__(
        self,
        *,
        guild: Guild | PartialGuild,
        state: ConnectionState,
        data: ThreadPayload,
    ) -> None:
        self._state: ConnectionState = state
        self.guild_id: int = guild.id
        self._from_data(data)

    async def _get_channel(self) -> Thread:
        return self

    def __repr__(self) -> str:
        return (
            f"<Thread id={self.id!r} name={self.name!r} parent={self.parent}"
            f" owner_id={self.owner_id!r} locked={self.locked} archived={self.archived}>"
        )

    def __str__(self) -> str:
        return self.name

    def _from_data(self, data: ThreadPayload) -> None:
        # This data will always exist
        self.id = int(data["id"])
        self.parent_id = int(data["parent_id"])
        self.name = data["name"]
        self._type = try_enum(ChannelType, data["type"])

        # This data may be missing depending on how this object is being created
        owner_id = data.get("owner_id")
        self.owner_id = int(owner_id) if owner_id is not None else None
        self.last_message_id = _get_as_snowflake(data, "last_message_id")
        self.slowmode_delay = data.get("rate_limit_per_user", 0)
        self.message_count = data.get("message_count", None)
        self.member_count = data.get("member_count", None)
        self.flags: ChannelFlags = ChannelFlags._from_value(data.get("flags", 0))
        self.total_message_sent = data.get("total_message_sent", None)
        self._applied_tags: list[int] = [
            int(tag_id) for tag_id in data.get("applied_tags", [])
        ]

        data.pop("_invoke_flag", False)

        self._unroll_metadata(data["thread_metadata"])

        self.me: ThreadMember | None
        if "member" in data:
            self.me = ThreadMember(self, data["member"])
        else:
            self.me = None

    def _unroll_metadata(self, data: ThreadMetadata) -> None:
        self.archived = data["archived"]
        self.auto_archive_duration = data["auto_archive_duration"]
        self.archive_timestamp = parse_time(data["archive_timestamp"])
        self.locked = data["locked"]
        self.invitable = data.get("invitable", True)
        self.created_at = parse_time(data.get("create_timestamp", None))

    def _update(self, data: ThreadPayload) -> None:
        with contextlib.suppress(KeyError):
            self.name = data["name"]

        self._applied_tags: list[int] = [
            int(tag_id) for tag_id in data.get("applied_tags", [])
        ]
        self.flags: ChannelFlags = ChannelFlags._from_value(data.get("flags", 0))
        self.slowmode_delay = data.get("rate_limit_per_user", 0)

        with contextlib.suppress(KeyError):
            self._unroll_metadata(data["thread_metadata"])

    @property
    def type(self) -> ChannelType:
        """The channel's Discord type."""
        return self._type

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild this thread belongs to.

        This is the cached :class:`Guild` with the in-process cache, or a
        :class:`PartialGuild` handle if it is not cached or the cache backend is remote.
        """
        from .guild import PartialGuild

        state = self._state
        if state.cache.supports_sync:
            guild = state._guilds.get_nowait(self.guild_id)
            if guild is not None:
                return guild
        return PartialGuild(state=state, id=self.guild_id)

    @property
    def parent(self) -> TextChannel | ForumChannel | PartialGuildChannel:
        """The parent channel this thread belongs to.

        This is the cached channel with the in-process cache, or a
        :class:`PartialGuildChannel` handle if it is not cached or the cache backend
        is remote. Use :meth:`get_parent` to get the cached channel.
        """
        from .channel import PartialGuildChannel

        state = self._state
        if state.cache.supports_sync:
            parent = state._guild_bucket("channels", self.guild_id).get_nowait(
                self.parent_id
            )
            if parent is not None:
                return parent  # type: ignore[no-any-return]
        return PartialGuildChannel(
            state=state, id=self.parent_id, guild_id=self.guild_id
        )

    def _cached_parent(self) -> TextChannel | ForumChannel | None:
        return self._state._guild_bucket("channels", self.guild_id).get_nowait(
            self.parent_id
        )

    async def get_parent(self) -> TextChannel | ForumChannel | None:
        """|coro|

        Returns the cached parent channel this thread belongs to.

        Returns
        -------
        Optional[Union[:class:`TextChannel`, :class:`ForumChannel`]]
            The parent channel, or ``None`` if it is not cached.
        """
        return await self._state._guild_bucket("channels", self.guild_id).get(
            self.parent_id
        )

    @property
    def owner(self) -> Member | None:
        """The member this thread belongs to.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_owner` there.
        """
        if self.owner_id is None:
            return None
        return self._state._guild_bucket("members", self.guild_id).get_nowait(
            self.owner_id
        )

    async def get_owner(self) -> Member | None:
        """|coro|

        Returns the cached member this thread belongs to.

        Returns
        -------
        Optional[:class:`Member`]
            The owner, or ``None`` if it is not cached.
        """
        if self.owner_id is None:
            return None
        return await self._state._get_member(self.guild_id, self.owner_id)

    @property
    def mention(self) -> str:
        """The string that allows you to mention the thread."""
        return f"<#{self.id}>"

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to the thread.

        .. versionadded:: 2.0
        """
        return f"https://discord.com/channels/{self.guild.id}/{self.id}"

    @property
    def members(self) -> list[ThreadMember]:
        """A list of thread members in this thread, including the bot if it is a member of this thread.

        This requires :attr:`Intents.members` to be properly filled. Most of the time however,
        this data is not provided by the gateway and a call to :meth:`fetch_members` is
        needed.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_members` there.
        """
        return self._state._store.bucket(
            "thread_members", scope=self.id
        ).values_nowait()

    async def get_members(self) -> list[ThreadMember]:
        """|coro|

        Returns a list of the thread members in this thread, including the bot if it is a member of this thread.

        This requires :attr:`Intents.members` to be properly filled. Most of the time however,
        this data is not provided by the gateway and a call to :meth:`fetch_members` is
        needed.

        Returns
        -------
        List[:class:`ThreadMember`]
            The cached thread members.
        """
        return await self._state._store.bucket("thread_members", scope=self.id).values()

    @property
    def applied_tags(self) -> list[ForumTag]:
        """List[:class:`ForumTag`]: A list of tags applied to this thread.

        This is only available for threads in forum or media channels.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_applied_tags` there.
        """
        from .channel import ForumChannel  # to prevent circular import

        parent = self._cached_parent()
        if isinstance(parent, ForumChannel):
            return [
                tag
                for tag_id in self._applied_tags
                if (tag := parent.get_tag(tag_id)) is not None
            ]
        return []

    async def get_applied_tags(self) -> list[ForumTag]:
        """|coro|

        Returns the tags applied to this thread.

        This is only available for threads in forum or media channels.

        Returns
        -------
        List[:class:`ForumTag`]
            The tags applied to this thread, empty if the parent channel is not cached.
        """
        from .channel import ForumChannel  # to prevent circular import

        parent = await self.get_parent()
        if isinstance(parent, ForumChannel):
            return [
                tag
                for tag_id in self._applied_tags
                if (tag := parent.get_tag(tag_id)) is not None
            ]
        return []

    @property
    def last_message(self) -> Message | None:
        """Returns the last message from this thread in cache.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_last_message` there.

        The message might not be valid or point to an existing message.

        Returns
        -------
        Optional[:class:`Message`]
            The last message in this channel or ``None`` if not found.
        """
        return cached_message(self._state, self.last_message_id)

    async def get_last_message(self) -> Message | None:
        """|coro|

        Returns the last message from this thread in cache.

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

    @property
    def category(self) -> CategoryChannel | PartialGuildChannel | None:
        """The category channel the parent channel belongs to, if applicable.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_category` there.

        Returns
        -------
        Optional[:class:`CategoryChannel`]
            The parent channel's category.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``.
        """
        parent = self._cached_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return parent.category

    @property
    def category_id(self) -> int | None:
        """The category channel ID the parent channel belongs to, if applicable.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_category_id` there.

        Returns
        -------
        Optional[:class:`int`]
            The parent channel's category ID.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``.
        """
        parent = self._cached_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return parent.category_id

    async def get_category(self) -> CategoryChannel | None:
        """|coro|

        Returns the category channel the parent channel belongs to, if applicable.

        Returns
        -------
        Optional[:class:`CategoryChannel`]
            The parent channel's category.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``.
        """
        parent = await self.get_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return await parent.get_category()

    async def get_category_id(self) -> int | None:
        """|coro|

        Returns the category channel ID the parent channel belongs to, if applicable.

        Returns
        -------
        Optional[:class:`int`]
            The parent channel's category ID.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``.
        """
        parent = await self.get_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return parent.category_id

    @property
    def starting_message(self) -> Message | None:
        """Returns the message that started this thread.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_starting_message` there.

        .. note::
            The ID for this message is the same as the thread ID.

        Returns
        -------
        Optional[:class:`Message`]
            The message that started this thread or ``None`` if not found in the cache.
        """
        return cached_message(self._state, self.id)

    async def get_starting_message(self) -> Message | None:
        """|coro|

        Returns the message that started this thread.

        The message might not be valid or point to an existing message.

        .. note::
            The ID for this message is the same as the thread ID.

        Returns
        -------
        Optional[:class:`Message`]
            The message that started this thread or ``None`` if not found in the cache.
        """
        return await self._state._get_message(self.id)

    def is_pinned(self) -> bool:
        """Whether the thread is pinned to the top of its parent forum or media channel.

        .. versionadded:: 2.3
        """
        return self.flags.pinned

    def is_private(self) -> bool:
        """Whether the thread is a private thread.

        A private thread is only viewable by those that have been explicitly
        invited or have :attr:`~.Permissions.manage_threads`.
        """
        return self._type is ChannelType.private_thread

    def is_news(self) -> bool:
        """Whether the thread is a news thread.

        A news thread is a thread that has a parent that is a news channel,
        i.e. :meth:`.TextChannel.is_news` is ``True``.
        """
        return self._type is ChannelType.news_thread

    def is_nsfw(self) -> bool:
        """Whether the thread is NSFW or not.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`check_nsfw` there.

        An NSFW thread is a thread that has a parent that is an NSFW channel,
        i.e. :meth:`.TextChannel.is_nsfw` is ``True``.
        """
        parent = self._cached_parent()
        return parent is not None and parent.is_nsfw()

    async def check_nsfw(self) -> bool:
        """|coro|

        Whether the thread is NSFW or not.

        .. versionadded:: 3.0

        An NSFW thread is a thread that has a parent that is an NSFW channel,
        i.e. :meth:`.TextChannel.is_nsfw` is ``True``.
        """
        parent = await self.get_parent()
        return parent is not None and parent.is_nsfw()

    def permissions_for(self, obj: Member | Role, /) -> Permissions:
        """Handles permission resolution for a :class:`~discord.Member` or :class:`~discord.Role`.

        This reads the cache synchronously and raises
        :class:`SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_permissions_for` there.

        Since threads do not have their own permissions, they inherit them
        from the parent channel. This is a convenience method for
        calling :meth:`~discord.TextChannel.permissions_for` on the
        parent channel.

        Parameters
        ----------
        obj: Union[:class:`~discord.Member`, :class:`~discord.Role`]
            The object to resolve permissions for. This could be either
            a member or a role. If it's a role then member overwrites
            are not computed.

        Returns
        -------
        :class:`~discord.Permissions`
            The resolved permissions for the member or role.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``
        """
        parent = self._cached_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return parent.permissions_for(obj)

    async def get_permissions_for(self, obj: Member | Role, /) -> Permissions:
        """|coro|

        Handles permission resolution for the :class:`~discord.Member`
        or :class:`~discord.Role` on the parent channel, reading the cache
        through its asynchronous API.

        .. versionadded:: 3.0

        Parameters
        ----------
        obj: Union[:class:`~discord.Member`, :class:`~discord.Role`]
            The object to resolve permissions for.

        Returns
        -------
        :class:`~discord.Permissions`
            The resolved permissions for the member or role.

        Raises
        ------
        ClientException
            The parent channel was not cached and returned ``None``
        """
        parent = await self.get_parent()
        if parent is None:
            raise ClientException("Parent channel not found")
        return await parent.get_permissions_for(obj)

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

        Usable only by bot accounts.

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
            You do not have proper permissions to delete the messages, or
            you're not using a bot account.
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
            message_id = messages[0].id
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
        delete messages even if they are your own (unless you are a user
        account). The :attr:`~Permissions.read_message_history` permission is
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


            deleted = await thread.purge(limit=100, check=is_me)
            await thread.send(f"Deleted {len(deleted)} message(s)")
        """
        return await purge_messages_helper(
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

    async def edit(
        self,
        *,
        name: str = MISSING,
        archived: bool = MISSING,
        locked: bool = MISSING,
        invitable: bool = MISSING,
        slowmode_delay: int = MISSING,
        auto_archive_duration: (
            ThreadArchiveDuration | ThreadArchiveDurationEnum
        ) = MISSING,
        pinned: bool = MISSING,
        applied_tags: list[ForumTag] = MISSING,
        reason: str | None = None,
    ) -> Thread:
        """|coro|

        Edits the thread.

        Editing the thread requires :attr:`.Permissions.manage_threads`. The thread
        creator can also edit ``name``, ``archived`` or ``auto_archive_duration``.
        Note that if the thread is locked then only those with :attr:`.Permissions.manage_threads`
        can send messages in it or unarchive a thread.

        The thread must be unarchived to be edited.

        Parameters
        ----------
        name: :class:`str`
            The new name of the thread.
        archived: :class:`bool`
            Whether to archive the thread or not.
        locked: :class:`bool`
            Whether to lock the thread or not.
        invitable: :class:`bool`
            Whether non-moderators can add other non-moderators to this thread.
            Only available for private threads.
        auto_archive_duration: :class:`int`
            The new duration in minutes before a thread is automatically archived for inactivity.
            Must be one of ``60``, ``1440``, ``4320``, or ``10080``.
            :class:`ThreadArchiveDuration` can be used alternatively.
        slowmode_delay: :class:`int`
            Specifies the slowmode rate limit for user in this thread, in seconds.
            A value of ``0`` disables slowmode. The maximum value possible is ``21600``.
        reason: Optional[:class:`str`]
            The reason for editing this thread. Shows up on the audit log.
        pinned: :class:`bool`
            Whether to pin the thread or not. This only works if the thread is part of a forum or media channel.
        applied_tags: List[:class:`ForumTag`]
            The set of tags to apply to the thread. Each tag object should have an ID set.

            .. versionadded:: 2.3

        Returns
        -------
        :class:`Thread`
            The newly edited thread.

        Raises
        ------
        Forbidden
            You do not have permissions to edit the thread.
        HTTPException
            Editing the thread failed.
        """
        payload = {}
        if name is not MISSING:
            payload["name"] = str(name)
        if archived is not MISSING:
            payload["archived"] = archived
        if auto_archive_duration is not MISSING:
            payload["auto_archive_duration"] = auto_archive_duration
        if locked is not MISSING:
            payload["locked"] = locked
        if invitable is not MISSING:
            payload["invitable"] = invitable
        if slowmode_delay is not MISSING:
            payload["rate_limit_per_user"] = slowmode_delay
        if pinned is not MISSING:
            # copy the ChannelFlags object to avoid mutating the original
            flags = ChannelFlags._from_value(self.flags.value)
            flags.pinned = pinned
            payload["flags"] = flags.value
        if applied_tags is not MISSING:
            payload["applied_tags"] = [tag.id for tag in applied_tags]

        data = await self._state.http.edit_channel(self.id, **payload, reason=reason)
        # The data payload will always be a Thread payload
        return Thread(
            data=cast("ThreadPayload", data), state=self._state, guild=self.guild
        )

    async def archive(self, locked: bool = MISSING) -> Thread:
        """|coro|

        Archives the thread. This is a shorthand of :meth:`.edit`.

        Parameters
        ----------
        locked: :class:`bool`
            Whether to lock the thread on archive, Defaults to ``False``.

        Returns
        -------
        :class:`.Thread`
            The updated thread.
        """
        return await self.edit(archived=True, locked=locked)

    async def unarchive(self) -> Thread:
        """|coro|

        Unarchives the thread. This is a shorthand of :meth:`.edit`.

        Returns
        -------
        :class:`.Thread`
            The updated thread.
        """
        return await self.edit(archived=False)

    async def join(self) -> None:
        """|coro|

        Joins this thread.

        You must have :attr:`~Permissions.send_messages_in_threads` to join a thread.
        If the thread is private, :attr:`~Permissions.manage_threads` is also needed.

        Raises
        ------
        Forbidden
            You do not have permissions to join the thread.
        HTTPException
            Joining the thread failed.
        """
        await self._state.http.join_thread(self.id)

    async def leave(self) -> None:
        """|coro|

        Leaves this thread.

        Raises
        ------
        HTTPException
            Leaving the thread failed.
        """
        await self._state.http.leave_thread(self.id)

    async def add_user(self, user: Snowflake) -> None:
        """|coro|

        Adds a user to this thread.

        You must have :attr:`~Permissions.send_messages_in_threads`
        to add a user to a public thread. If the thread is private and
        :attr:`invitable` is ``False``, then
        :attr:`~Permissions.manage_threads` is required.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
            The user to add to the thread.

        Raises
        ------
        Forbidden
            You do not have permissions to add the user to the thread.
        HTTPException
            Adding the user to the thread failed.
        """
        await self._state.http.add_user_to_thread(self.id, user.id)

    async def remove_user(self, user: Snowflake) -> None:
        """|coro|

        Removes a user from this thread.

        You must have :attr:`~Permissions.manage_threads` or be the creator of the thread to remove a user.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
            The user to remove from the thread.

        Raises
        ------
        Forbidden
            You do not have permissions to remove the user from the thread.
        HTTPException
            Removing the user from the thread failed.
        """
        await self._state.http.remove_user_from_thread(self.id, user.id)

    async def fetch_members(self) -> list[ThreadMember]:
        """|coro|

        Retrieves all :class:`ThreadMember` that are in this thread.

        This requires :attr:`Intents.members` to get information about members
        other than yourself.

        Returns
        -------
        List[:class:`ThreadMember`]
            All thread members in the thread.

        Raises
        ------
        HTTPException
            Retrieving the members failed.
        """
        members = await self._state.http.get_thread_members(self.id)

        thread_members = [ThreadMember(parent=self, data=data) for data in members]

        for member in thread_members:
            await self._add_member(member)

        return thread_members

    async def delete(self) -> None:
        """|coro|

        Deletes this thread.

        You must have :attr:`~Permissions.manage_threads` to delete threads.

        Raises
        ------
        Forbidden
            You do not have permissions to delete this thread.
        HTTPException
            Deleting the thread failed.
        """
        await self._state.http.delete_channel(self.id)

    def get_partial_message(self, message_id: int, /) -> PartialMessage:
        """Creates a :class:`PartialMessage` from the message ID.

        This is useful if you want to work with a message and only have its ID without
        doing an unnecessary API call.

        .. versionadded:: 2.0

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

    async def _add_member(self, member: ThreadMember) -> None:
        await self._state._store.bucket("thread_members", scope=self.id).set(
            member.id, member
        )

    async def _pop_member(self, member_id: int) -> ThreadMember | None:
        return await self._state._store.bucket("thread_members", scope=self.id).pop(
            member_id
        )


class ThreadMember(Hashable):
    """Represents a Discord thread member.

    .. container:: operations

        .. describe:: x == y

            Checks if two thread members are equal.

        .. describe:: x != y

            Checks if two thread members are not equal.

        .. describe:: hash(x)

            Returns the thread member's hash.

        .. describe:: str(x)

            Returns the thread member's name.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The thread member's ID.
    thread_id: :class:`int`
        The thread's ID.
    joined_at: :class:`datetime.datetime`
        The time the member joined the thread in UTC.
    """

    __slots__ = (
        "_state",
        "flags",
        "id",
        "joined_at",
        "thread_id",
    )

    def __init__(
        self, parent: Thread, data: ThreadMemberPayload | ThreadMemberUpdateEvent
    ) -> None:
        self._state = parent._state
        self._from_data(data, parent.id)

    def __repr__(self) -> str:
        return (
            "<ThreadMember"
            f" id={self.id} thread_id={self.thread_id} joined_at={self.joined_at!r}>"
        )

    def _from_data(
        self, data: ThreadMemberPayload | ThreadMemberUpdateEvent, parent_id: int
    ) -> None:
        if "user_id" in data:
            self.id = int(data["user_id"])
        else:
            self_id = self._state.self_id
            if self_id is None:
                raise ClientException("The current user ID is not known yet.")
            self.id = self_id

        if "id" in data:
            self.thread_id = int(data["id"])
        else:
            self.thread_id = parent_id

        self.joined_at = parse_time(data["join_timestamp"])
        self.flags = data["flags"]

    @property
    def thread(self) -> Thread | PartialMessageable:
        """The thread this member belongs to.

        This is the cached :class:`Thread` with the in-process cache, and a
        :class:`PartialMessageable` handle when it is not cached or the cache
        backend is not the in-process one. ``await client.get_channel(member.thread_id)``
        returns the cached thread with any backend.
        """
        cached = cached_channel(self._state, self.thread_id)
        if cached is not None:
            return cast("Thread | PartialMessageable", cached)
        from .channel import PartialMessageable

        return PartialMessageable(
            state=self._state, id=self.thread_id, type=ChannelType.public_thread
        )

    @property
    def parent(self) -> Thread | PartialMessageable:
        """The thread this member belongs to. An alias of :attr:`thread`."""
        return self.thread
