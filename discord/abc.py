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

import asyncio
import contextlib
import copy
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from . import utils
from .context_managers import Typing
from .enums import ChannelType
from .errors import ClientException, InvalidArgument
from .file import File, VoiceMessage
from .flags import ChannelFlags, MessageFlags
from .invite import Invite
from .iterators import HistoryIterator, MessagePinIterator
from .mentions import AllowedMentions
from .partial_emoji import PartialEmoji, _EmojiTag
from .permissions import PermissionOverwrite, Permissions
from .role import Role
from .utils import warn_deprecated

__all__ = (
    "Connectable",
    "GuildChannel",
    "Mentionable",
    "Messageable",
    "PrivateChannel",
    "Snowflake",
    "User",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from datetime import datetime

    from typing_extensions import Self

    from .asset import Asset
    from .channel import (
        CategoryChannel,
        DMChannel,
        GroupChannel,
        PartialGuildChannel,
        PartialMessageable,
        StageChannel,
        TextChannel,
        VoiceChannel,
    )
    from .client import Client
    from .embeds import Embed
    from .enums import InviteTarget
    from .guild import Guild, GuildChannel as GuildChannelType, PartialGuild
    from .iterators import MessageSearchIterator
    from .member import Member
    from .message import Message, MessageReference, PartialMessage
    from .object import Object
    from .poll import Poll
    from .scheduled_events import ScheduledEvent
    from .shared_client_theme import SharedClientTheme
    from .state import ConnectionState
    from .sticker import GuildSticker, StickerItem
    from .threads import Thread
    from .types.channel import (
        Channel as ChannelPayload,
        GuildChannel as GuildChannelPayload,
        OverwriteType,
        PermissionOverwrite as PermissionOverwritePayload,
    )
    from .types.embed import Embed as EmbedData
    from .types.guild import ChannelPositionUpdate
    from .types.invite import InviteTargetType
    from .types.message import (
        AllowedMentions as AllowedMentionsPayload,
        MessageReference as MessageReferencePayload,
        SharedClientTheme as SharedClientThemePayload,
    )
    from .types.poll import Poll as PollPayload
    from .ui.view import BaseView
    from .user import ClientUser

    PartialMessageableChannel: TypeAlias = (
        TextChannel
        | VoiceChannel
        | StageChannel
        | Thread
        | DMChannel
        | PartialMessageable
    )
    MessageableChannel: TypeAlias = PartialMessageableChannel | GroupChannel
    SnowflakeTime: TypeAlias = "Snowflake | datetime"

    from .voice import VoiceProtocol

    T = TypeVar("T", bound=VoiceProtocol[Any])

MISSING = utils.MISSING


async def _single_delete_strategy(
    messages: Iterable[Message], *, reason: str | None = None
) -> None:
    for m in messages:
        await m.delete(reason=reason)


def _always_true(_: object) -> bool:
    return True


async def purge_messages_helper(
    channel: TextChannel | StageChannel | Thread | VoiceChannel,
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
    """Purge the messages of a channel matching ``check``."""
    if check is MISSING:
        check = _always_true

    iterator = channel.history(
        limit=limit,
        before=before,
        after=after,
        oldest_first=oldest_first,
        around=around,
    )
    ret: list[Message] = []
    count = 0

    minimum_time = int((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
    strategy = channel.delete_messages if bulk else _single_delete_strategy

    async for message in iterator:
        if count == 100:
            to_delete = ret[-100:]
            await strategy(to_delete, reason=reason)
            count = 0
            await asyncio.sleep(1)

        if not check(message):
            continue

        if message.id < minimum_time:
            # older than 14 days old
            if count == 1:
                await ret[-1].delete(reason=reason)
            elif count >= 2:
                to_delete = ret[-count:]
                await strategy(to_delete, reason=reason)

            count = 0
            strategy = _single_delete_strategy

        count += 1
        ret.append(message)

    # Some messages remaining to poll
    if count >= 2:
        # more than 2 messages -> bulk delete
        to_delete = ret[-count:]
        await strategy(to_delete, reason=reason)
    elif count == 1:
        # delete a single message
        await ret[-1].delete(reason=reason)

    return ret


@runtime_checkable
class Snowflake(Protocol):
    """An ABC that details the common operations on a Discord model.

    Almost all :ref:`Discord models <discord_api_models>` meet this
    abstract base class.

    If you want to create a snowflake on your own, consider using
    :class:`.Object`.

    Attributes
    ----------
    id: :class:`int`
        The model's unique ID.
    """

    __slots__ = ()
    id: int


@runtime_checkable
class User(Snowflake, Protocol):
    """An ABC that details the common operations on a Discord user.

    The following implement this ABC:

    - :class:`~discord.User`
    - :class:`~discord.ClientUser`
    - :class:`~discord.Member`

    This ABC must also implement :class:`~discord.abc.Snowflake`.

    Attributes
    ----------
    name: :class:`str`
        The user's username.
    discriminator: :class:`str`
        The user's discriminator.

        .. note::

            If the user has migrated to the new username system, this will always be "0".
    global_name: :class:`str`
        The user's global name.

        .. versionadded:: 2.5
    avatar: :class:`~discord.Asset`
        The avatar asset the user has.
    bot: :class:`bool`
        If the user is a bot account.
    """

    __slots__ = ()

    name: str
    discriminator: str
    global_name: str | None
    avatar: Asset | None
    bot: bool

    @property
    def display_name(self) -> str:
        """Returns the user's display name."""
        raise NotImplementedError

    @property
    def mention(self) -> str:
        """Returns a string that allows you to mention the given user."""
        raise NotImplementedError


@runtime_checkable
class PrivateChannel(Snowflake, Protocol):
    """An ABC that details the common operations on a private Discord channel.

    The following implement this ABC:

    - :class:`~discord.DMChannel`
    - :class:`~discord.GroupChannel`

    This ABC must also implement :class:`~discord.abc.Snowflake`.

    Attributes
    ----------
    me: :class:`~discord.ClientUser`
        The user presenting yourself.
    """

    __slots__ = ()

    me: ClientUser


class _Overwrites:
    __slots__ = ("allow", "deny", "id", "type")

    ROLE = 0
    MEMBER = 1

    def __init__(self, data: PermissionOverwritePayload) -> None:
        self.id: int = int(data["id"])
        self.allow: int = int(data.get("allow", 0))
        self.deny: int = int(data.get("deny", 0))
        self.type: OverwriteType = data["type"]

    def _asdict(self) -> PermissionOverwritePayload:
        return {
            "id": self.id,
            "allow": str(self.allow),
            "deny": str(self.deny),
            "type": self.type,
        }

    def is_role(self) -> bool:
        return self.type == self.ROLE

    def is_member(self) -> bool:
        return self.type == self.MEMBER


GCH = TypeVar("GCH", bound="GuildChannel")


def cached_message(state: ConnectionState, message_id: int | None) -> Message | None:
    messages = state._messages
    if messages is None or message_id is None:
        return None
    return messages.get_nowait(message_id)


class GuildChannel:
    """An ABC that details the common operations on a Discord guild channel.

    The following implement this ABC:

    - :class:`~discord.TextChannel`
    - :class:`~discord.VoiceChannel`
    - :class:`~discord.CategoryChannel`
    - :class:`~discord.StageChannel`
    - :class:`~discord.ForumChannel`

    This ABC must also implement :class:`~discord.abc.Snowflake`.

    Attributes
    ----------
    name: :class:`str`
        The channel name.
    guild_id: :class:`int`
        The ID of the guild the channel belongs to.
    position: :class:`int`
        The position in the channel list. This is a number that starts at 0.
        e.g. the top channel is position 0.
    """

    __slots__ = ()

    id: int
    name: str
    guild_id: int
    position: int
    category_id: int | None
    flags: ChannelFlags
    _state: ConnectionState
    _overwrites: list[_Overwrites]

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            state: ConnectionState,
            guild: Guild | PartialGuild,
            data: Any,
        ) -> None: ...

        @property
        def type(self) -> ChannelType:
            """The channel's Discord type."""
            ...

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild the channel belongs to.

        This is the cached :class:`~discord.Guild` with the in-process cache,
        or a :class:`~discord.PartialGuild` handle if it is not cached or the
        cache backend is remote. Use :meth:`PartialGuild.get` to get the cached guild.
        """
        from .guild import PartialGuild

        state = self._state
        if state.cache.supports_sync:
            guild = state._guilds.get_nowait(self.guild_id)
            if guild is not None:
                return guild
        return PartialGuild(state=state, id=self.guild_id)

    async def _get_cached_channels(self) -> list[GuildChannelType]:
        return await self._state._guild_bucket("channels", self.guild_id).values()

    async def _get_cached_channel(self, channel_id: int | None) -> GuildChannel | None:
        if channel_id is None:
            return None
        return await self._state._guild_bucket("channels", self.guild_id).get(
            channel_id
        )

    def __str__(self) -> str:
        if self.obfuscated:
            return f"Obfuscated Channel ({self.id})"

        return self.name

    @property
    def _sorting_bucket(self) -> int:
        raise NotImplementedError

    @property
    def obfuscated(self) -> bool:
        """Whether the channel's metadata has been obfuscated.

        Discord obfuscates channels the client cannot view, and only sends them over
        the gateway. Other fields of an obfuscated channel, such as :attr:`name`, must
        not be relied on; only :attr:`id`, :attr:`type`, :attr:`position` and
        :attr:`category_id` are kept. When access is regained, a channel update
        replaces the obfuscated data.

        This is a shortcut for :attr:`ChannelFlags.channel_obfuscated`.

        .. versionadded:: 3.0
        """
        flags = getattr(self, "flags", None)
        return flags is not None and flags.channel_obfuscated

    def _update(self, guild: Guild | PartialGuild, data: Any) -> None:
        raise NotImplementedError

    async def _move(
        self,
        position: int,
        parent_id: Any | None = None,
        lock_permissions: bool = False,
        *,
        reason: str | None,
    ) -> None:
        if position < 0:
            raise InvalidArgument("Channel position cannot be less than 0.")

        http = self._state.http
        bucket = self._sorting_bucket
        channels: list[GuildChannel] = [
            c for c in await self._get_cached_channels() if c._sorting_bucket == bucket
        ]

        channels.sort(key=lambda c: c.position)

        try:
            # remove ourselves from the channel list
            channels.remove(self)
        except ValueError:
            # not there somehow lol
            return
        else:
            index = next(
                (i for i, c in enumerate(channels) if c.position >= position),
                len(channels),
            )
            # add ourselves at our designated position
            channels.insert(index, self)

        payload: list[ChannelPositionUpdate] = []
        for index, c in enumerate(channels):
            d: ChannelPositionUpdate = {"id": c.id, "position": index}
            if parent_id is not MISSING and c.id == self.id:
                d.update(parent_id=parent_id, lock_permissions=lock_permissions)
            payload.append(d)

        await http.bulk_channel_update(self.guild.id, payload, reason=reason)

    async def _edit(
        self, options: dict[str, Any], reason: str | None
    ) -> ChannelPayload | None:
        try:
            parent = options.pop("category")
        except KeyError:
            parent_id = MISSING
        else:
            parent_id = parent and parent.id

        with contextlib.suppress(KeyError):
            options["rate_limit_per_user"] = options.pop("slowmode_delay")

        with contextlib.suppress(KeyError):
            options["default_thread_rate_limit_per_user"] = options.pop(
                "default_thread_slowmode_delay"
            )

        with contextlib.suppress(KeyError):
            options["flags"] = options.pop("flags").value

        with contextlib.suppress(KeyError):
            options["available_tags"] = [
                tag.to_dict() for tag in options.pop("available_tags")
            ]

        try:
            rtc_region = options.pop("rtc_region")
        except KeyError:
            pass
        else:
            options["rtc_region"] = None if rtc_region is None else str(rtc_region)

        try:
            video_quality_mode = options.pop("video_quality_mode")
        except KeyError:
            pass
        else:
            options["video_quality_mode"] = int(video_quality_mode)

        lock_permissions = options.pop("sync_permissions", False)

        try:
            position = options.pop("position")
        except KeyError:
            if parent_id is not MISSING:
                if lock_permissions:
                    category = await self._get_cached_channel(parent_id)
                    if category:
                        options["permission_overwrites"] = [
                            c._asdict() for c in category._overwrites
                        ]
                options["parent_id"] = parent_id
            elif lock_permissions and self.category_id is not None:
                # if we're syncing permissions on a pre-existing channel category without changing it
                # we need to update the permissions to point to the pre-existing category
                category = await self._get_cached_channel(self.category_id)
                if category:
                    options["permission_overwrites"] = [
                        c._asdict() for c in category._overwrites
                    ]
        else:
            await self._move(
                position,
                parent_id=parent_id,
                lock_permissions=lock_permissions,
                reason=reason,
            )

        overwrites = options.get("overwrites")
        if overwrites is not None:
            perms: list[dict[str, Any]] = []
            for target, perm in overwrites.items():
                if not isinstance(perm, PermissionOverwrite):
                    raise InvalidArgument(
                        "Expected PermissionOverwrite received"
                        f" {perm.__class__.__name__}"
                    )

                allow, deny = perm.pair()
                payload = {
                    "allow": allow.value,
                    "deny": deny.value,
                    "id": target.id,
                    "type": (
                        _Overwrites.ROLE
                        if isinstance(target, Role)
                        else _Overwrites.MEMBER
                    ),
                }

                perms.append(payload)
            options["permission_overwrites"] = perms

        try:
            ch_type = options["type"]
        except KeyError:
            pass
        else:
            if not isinstance(ch_type, ChannelType):
                raise InvalidArgument("type field must be of type ChannelType")
            options["type"] = ch_type.value

        try:
            default_reaction_emoji = options["default_reaction_emoji"]
        except KeyError:
            pass
        else:
            if isinstance(
                default_reaction_emoji, _EmojiTag
            ):  # GuildEmoji, PartialEmoji
                default_reaction_emoji = default_reaction_emoji._to_partial()
            elif isinstance(default_reaction_emoji, int):
                default_reaction_emoji = PartialEmoji(
                    name=None, id=default_reaction_emoji
                )
            elif isinstance(default_reaction_emoji, str):
                default_reaction_emoji = PartialEmoji.from_str(default_reaction_emoji)
            elif default_reaction_emoji is None:
                pass
            else:
                raise InvalidArgument(
                    "default_reaction_emoji must be of type: GuildEmoji | int | str | None"
                )

            options["default_reaction_emoji"] = (
                default_reaction_emoji._to_forum_reaction_payload()
                if default_reaction_emoji
                else None
            )

        if options:
            return await self._state.http.edit_channel(
                self.id, reason=reason, **options
            )
        return None

    def _fill_overwrites(self, data: GuildChannelPayload) -> None:
        self._overwrites = []
        everyone_index = 0
        everyone_id = self.guild.id

        for index, overridden in enumerate(data.get("permission_overwrites", [])):
            overwrite = _Overwrites(overridden)
            self._overwrites.append(overwrite)

            if overwrite.type == _Overwrites.MEMBER:
                continue

            if overwrite.id == everyone_id:
                # the @everyone role is not guaranteed to be the first one
                # in the list of permission overwrites, however the permission
                # resolution code kind of requires that it is the first one in
                # the list since it is special. So we need the index so we can
                # swap it to be the first one.
                everyone_index = index

        # do the swap
        tmp = self._overwrites
        if tmp:
            tmp[everyone_index], tmp[0] = tmp[0], tmp[everyone_index]

    def _changed_roles_with(self, resolve: Callable[[int], Role | None]) -> list[Role]:
        ret: list[Role] = []
        for overwrite in filter(lambda o: o.is_role(), self._overwrites):
            role = resolve(overwrite.id)
            if role is None:
                continue

            role = copy.copy(role)
            permissions = role.permissions
            permissions.handle_overwrite(overwrite.allow, overwrite.deny)
            role._permissions = permissions.value
            ret.append(role)
        return ret

    @property
    def changed_roles(self) -> list[Role]:
        """Returns a list of roles that have been overridden from their default values.

        This is the list of roles of the :attr:`~discord.Guild.roles` attribute that have
        an overwrite in this channel.

        This reads the cache synchronously and raises
        :class:`~discord.SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_changed_roles` there.
        """
        return self._changed_roles_with(
            self._state._guild_bucket("roles", self.guild_id).get_nowait
        )

    async def get_changed_roles(self) -> list[Role]:
        """|coro|

        Returns a list of roles that have been overridden from
        their default values in the guild's roles.

        Returns
        -------
        List[:class:`~discord.Role`]
            The cached roles that have an overwrite in this channel, with the
            overwrite applied to their permissions.
        """
        role_ids = [o.id for o in self._overwrites if o.is_role()]
        found = await self._state._guild_bucket("roles", self.guild_id).get_many(
            role_ids
        )
        return self._changed_roles_with(found.get)

    @property
    def mention(self) -> str:
        """The string that allows you to mention the channel."""
        return f"<#{self.id}>"

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to the channel.

        .. versionadded:: 2.0
        """
        return f"https://discord.com/channels/{self.guild.id}/{self.id}"

    @property
    def created_at(self) -> datetime:
        """Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def overwrites_for(self, obj: Role | User) -> PermissionOverwrite:
        """Returns the channel-specific overwrites for a member or a role.

        Parameters
        ----------
        obj: Union[:class:`~discord.Role`, :class:`~discord.abc.User`]
            The role or user denoting
            whose overwrite to get.

        Returns
        -------
        :class:`~discord.PermissionOverwrite`
            The permission overwrites for this object.
        """
        predicate: Callable[[_Overwrites], bool]
        if isinstance(obj, User):
            predicate = _Overwrites.is_member
        elif isinstance(obj, Role):  # pyright: ignore[reportUnnecessaryIsInstance]
            predicate = _Overwrites.is_role
        else:
            predicate = _always_true

        for overwrite in filter(predicate, self._overwrites):
            if overwrite.id == obj.id:
                allow = Permissions(overwrite.allow)
                deny = Permissions(overwrite.deny)
                return PermissionOverwrite.from_pair(allow, deny)

        return PermissionOverwrite()

    def _overwrites_with(
        self, resolve: Callable[[_Overwrites], Role | Member | None]
    ) -> dict[Role | Member, PermissionOverwrite]:
        ret: dict[Role | Member, PermissionOverwrite] = {}
        for ow in self._overwrites:
            allow = Permissions(ow.allow)
            deny = Permissions(ow.deny)
            overwrite = PermissionOverwrite.from_pair(allow, deny)
            target = resolve(ow)

            # TODO: There is potential data loss here in the non-chunked
            # case, i.e. target is None because the member is not cached.
            # This can be fixed with a slight breaking change to the return type,
            # i.e. adding discord.Object to the list of it
            # However, for now this is an acceptable compromise.
            if target is not None:
                ret[target] = overwrite
        return ret

    @property
    def overwrites(self) -> dict[Role | Member, PermissionOverwrite]:
        """Returns all of the channel's overwrites.

        This is returned as a dictionary where the key contains the target which
        can be either a :class:`~discord.Role` or a :class:`~discord.Member` and the value is the
        overwrite as a :class:`~discord.PermissionOverwrite`.

        This reads the cache synchronously and raises
        :class:`~discord.SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_overwrites` there.

        Returns
        -------
        Dict[Union[:class:`~discord.Role`, :class:`~discord.Member`], :class:`~discord.PermissionOverwrite`]
            The channel's permission overwrites.
        """
        return self._overwrites_with(
            lambda ow: self._state._guild_bucket(
                "roles" if ow.is_role() else "members", self.guild_id
            ).get_nowait(ow.id)
        )

    async def get_overwrites(self) -> dict[Role | Member, PermissionOverwrite]:
        """|coro|

        Returns all of the channel's overwrites.

        This is returned as a dictionary where the key contains the target which
        can be either a :class:`~discord.Role` or a :class:`~discord.Member` and the value is the
        overwrite as a :class:`~discord.PermissionOverwrite`.

        Targets that are not cached are left out.

        Returns
        -------
        Dict[Union[:class:`~discord.Role`, :class:`~discord.Member`], :class:`~discord.PermissionOverwrite`]
            The channel's permission overwrites.
        """
        found: dict[bool, dict[int, Role | Member]] = {}
        for kind, is_role in (("roles", True), ("members", False)):
            ids = [o.id for o in self._overwrites if o.is_role() is is_role]
            found[is_role] = await self._state._guild_bucket(
                kind, self.guild_id
            ).get_many(ids)
        return self._overwrites_with(lambda ow: found[ow.is_role()].get(ow.id))

    @property
    def category(self) -> CategoryChannel | PartialGuildChannel | None:
        """The category this channel belongs to.

        If there is no category then this is ``None``.

        With the in-process cache this is the cached category, or ``None`` if it is
        not cached. With a remote cache backend this is a :class:`~discord.PartialGuildChannel`
        handle, use :meth:`get_category` to get the cached category.
        """
        if self.category_id is None:
            return None

        state = self._state
        if state.cache.supports_sync:
            return state._guild_bucket("channels", self.guild_id).get_nowait(
                self.category_id
            )

        from .channel import PartialGuildChannel

        return PartialGuildChannel(
            state=state,
            id=self.category_id,
            guild_id=self.guild_id,
            type=ChannelType.category,
        )

    async def get_category(self) -> CategoryChannel | None:
        """|coro|

        Returns the category this channel belongs to.

        If there is no category then this is ``None``.

        Returns
        -------
        Optional[:class:`~discord.CategoryChannel`]
            The cached category, or ``None`` if there is none or it is not cached.
        """
        return cast(
            "CategoryChannel | None",
            await self._get_cached_channel(self.category_id),
        )

    @property
    def permissions_synced(self) -> bool:
        """Whether the permissions for this channel are synced with its category.

        If there is no category then this is ``False``.

        This reads the cache synchronously and raises
        :class:`~discord.SyncCacheAccessError` with a remote cache backend,
        use :meth:`is_permissions_synced` there.

        .. versionadded:: 1.3
        """
        if self.category_id is None:
            return False

        category = self._state._guild_bucket("channels", self.guild_id).get_nowait(
            self.category_id
        )
        return bool(category and category.overwrites == self.overwrites)

    async def is_permissions_synced(self) -> bool:
        """|coro|

        Whether the permissions for this channel are synced with the
        category it belongs to.

        If there is no category then this is ``False``.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`bool`
            Whether the overwrites of this channel equal those of its category.
        """
        if self.category_id is None:
            return False

        category = await self._get_cached_channel(self.category_id)
        return bool(
            category and await category.get_overwrites() == await self.get_overwrites()
        )

    async def get_members(self) -> list[Member]:
        """|coro|

        Returns the cached members that can see this channel.

        .. versionadded:: 3.0

        Returns
        -------
        List[:class:`~discord.Member`]
            The members whose resolved permissions include :attr:`~discord.Permissions.read_messages`.
        """
        return [
            member
            for member in await self._state._guild_bucket(
                "members", self.guild_id
            ).values()
            if (await self.get_permissions_for(member)).read_messages
        ]

    @staticmethod
    def _role_base_permissions(
        role: Role, owner_id: int | None, default: Role | None
    ) -> Permissions:
        if owner_id == role.id:
            return Permissions.all()

        base = Permissions(default.permissions.value if default else 0)
        base.value |= role._permissions
        return base

    def _resolve_permissions(
        self, obj: Member | Role, base: Permissions
    ) -> Permissions:
        guild_id = self.guild_id

        # Guild-wide Administrator -> True for everything
        # Bypass all channel-specific overrides
        if base.administrator:
            return Permissions.all()

        # Handle the role case first
        if isinstance(obj, Role):
            # Apply @everyone allow/deny first since it's special
            try:
                maybe_everyone = self._overwrites[0]
                if maybe_everyone.id == guild_id:
                    base.handle_overwrite(
                        allow=maybe_everyone.allow, deny=maybe_everyone.deny
                    )
            except IndexError:
                pass

            if obj.is_default():
                return base

            overwrite = utils.get(self._overwrites, type=_Overwrites.ROLE, id=obj.id)
            if overwrite is not None:
                base.handle_overwrite(overwrite.allow, overwrite.deny)

            return base

        roles = obj._roles

        # Apply @everyone allow/deny first since it's special
        try:
            maybe_everyone = self._overwrites[0]
            if maybe_everyone.id == guild_id:
                base.handle_overwrite(
                    allow=maybe_everyone.allow, deny=maybe_everyone.deny
                )
                remaining_overwrites = self._overwrites[1:]
            else:
                remaining_overwrites = self._overwrites
        except IndexError:
            remaining_overwrites = self._overwrites

        denies = 0
        allows = 0

        # Apply channel specific role permission overwrites
        for overwrite in remaining_overwrites:
            if overwrite.is_role() and roles.has(overwrite.id):
                denies |= overwrite.deny
                allows |= overwrite.allow

        base.handle_overwrite(allow=allows, deny=denies)

        # Apply member specific permission overwrites
        for overwrite in remaining_overwrites:
            if overwrite.is_member() and overwrite.id == obj.id:
                base.handle_overwrite(allow=overwrite.allow, deny=overwrite.deny)
                break

        # timed out members only keep viewing the channel and its history
        if obj.timed_out:
            base.value &= Permissions(
                view_channel=True, read_message_history=True
            ).value

        # if you can't send a message in a channel then you can't have certain
        # permissions as well
        if not base.send_messages:
            base.send_tts_messages = False
            base.mention_everyone = False
            base.embed_links = False
            base.attach_files = False

        # if you can't read a channel then you have no permissions there
        if not base.read_messages:
            denied = Permissions.all_channel()
            base.value &= ~denied.value

        return base

    def permissions_for(self, obj: Member | Role, /) -> Permissions:
        """Handles permission resolution for a :class:`~discord.Member` or :class:`~discord.Role`.

        This function takes into consideration the following cases:

        - Guild owner
        - Guild roles
        - Channel overrides
        - Member overrides
        - Timed out members

        If a :class:`~discord.Role` is passed, then it checks the permissions
        someone with that role would have, which is essentially:

        - The default role permissions
        - The permissions of the role used as a parameter
        - The default role permission overwrites
        - The permission overwrites of the role used as a parameter

        This reads the cache synchronously and raises
        :class:`~discord.SyncCacheAccessError` with a remote cache backend,
        use :meth:`get_permissions_for` there.

        .. versionchanged:: 2.0
            The object passed in can now be a role object.

        .. versionchanged:: 3.0
            Timed out members only keep :attr:`~discord.Permissions.view_channel`
            and :attr:`~discord.Permissions.read_message_history`.

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
        """
        # The current cases can be explained as:
        # Guild owner get all permissions -- no questions asked. Otherwise...
        # The @everyone role gets the first application.
        # After that, the applied roles that the user has in the channel
        # (or otherwise) are then OR'd together.
        # After the role permissions are resolved, the member permissions
        # have to take into effect.
        # After all that is done, you have to do the following:

        # If manage permissions is True, then all permissions are set to True.

        # The operation first takes into consideration the denied
        # and then the allowed.

        if isinstance(obj, Role):
            state = self._state
            guild = state._guilds.get_nowait(self.guild_id)
            default = state._guild_bucket("roles", self.guild_id).get_nowait(
                self.guild_id
            )
            base = self._role_base_permissions(
                obj, guild.owner_id if guild is not None else None, default
            )
        else:
            base = obj.guild_permissions

        return self._resolve_permissions(obj, base)

    async def get_permissions_for(self, obj: Member | Role, /) -> Permissions:
        """|coro|

        Handles permission resolution for the :class:`~discord.Member`
        or :class:`~discord.Role`, reading the cache through its asynchronous API.

        It follows the same rules as :meth:`permissions_for`: the guild owner and
        administrators have every permission, then the permissions of the default
        role and of the roles are combined, the overwrites of the default role, of
        the roles and of the member are applied in that order, timed out members only
        keep :attr:`~discord.Permissions.view_channel` and
        :attr:`~discord.Permissions.read_message_history`, and the permissions that
        make no sense without :attr:`~discord.Permissions.send_messages` or
        :attr:`~discord.Permissions.read_messages` are removed.

        .. versionadded:: 3.0

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
        """
        if isinstance(obj, Role):
            state = self._state
            guild = await state._guilds.get(self.guild_id)
            default = await state._guild_bucket("roles", self.guild_id).get(
                self.guild_id
            )
            base = self._role_base_permissions(
                obj, guild.owner_id if guild is not None else None, default
            )
        else:
            base = await obj.get_guild_permissions()

        return self._resolve_permissions(obj, base)

    async def delete(self, *, reason: str | None = None) -> None:
        """|coro|

        Deletes the channel.

        You must have :attr:`~discord.Permissions.manage_channels` permission to use this.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this channel.
            Shows up on the audit log.

        Raises
        ------
        ~discord.Forbidden
            You do not have proper permissions to delete the channel.
        ~discord.NotFound
            The channel was not found or was already deleted.
        ~discord.HTTPException
            Deleting the channel failed.
        """
        await self._state.http.delete_channel(self.id, reason=reason)

    @overload
    async def set_permissions(
        self,
        target: Member | Role,
        *,
        overwrite: PermissionOverwrite | None = ...,
        reason: str | None = ...,
    ) -> None: ...

    @overload
    async def set_permissions(
        self,
        target: Member | Role,
        *,
        reason: str | None = ...,
        **permissions: bool,
    ) -> None: ...

    async def set_permissions(
        self,
        target: Snowflake,
        *,
        overwrite: Any = MISSING,
        reason: str | None = None,
        **permissions: bool,
    ) -> None:
        r"""|coro|

        Sets the channel specific permission overwrites for a target in the
        channel.

        The ``target`` parameter should either be a :class:`~discord.Member` or a
        :class:`~discord.Role` that belongs to guild.

        The ``overwrite`` parameter, if given, must either be ``None`` or
        :class:`~discord.PermissionOverwrite`. For convenience, you can pass in
        keyword arguments denoting :class:`~discord.Permissions` attributes. If this is
        done, then you cannot mix the keyword arguments with the ``overwrite``
        parameter.

        If the ``overwrite`` parameter is ``None``, then the permission
        overwrites are deleted.

        You must have the :attr:`~discord.Permissions.manage_roles` permission to use this.

        .. note::

            This method *replaces* the old overwrites with the ones given.

        Examples
        --------
        Setting allow and deny: ::

            await message.channel.set_permissions(
                message.author, read_messages=True, send_messages=False
            )

        Deleting overwrites ::

            await channel.set_permissions(member, overwrite=None)

        Using :class:`~discord.PermissionOverwrite` ::

            overwrite = discord.PermissionOverwrite()
            overwrite.send_messages = False
            overwrite.read_messages = True
            await channel.set_permissions(member, overwrite=overwrite)

        Parameters
        ----------
        target: Union[:class:`~discord.Member`, :class:`~discord.Role`]
            The member or role to overwrite permissions for.
        overwrite: Optional[:class:`~discord.PermissionOverwrite`]
            The permissions to allow and deny to the target, or ``None`` to
            delete the overwrite.
        \*\*permissions
            A keyword argument list of permissions to set for ease of use.
            Cannot be mixed with ``overwrite``.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        ------
        ~discord.Forbidden
            You do not have permissions to edit channel specific permissions.
        ~discord.HTTPException
            Editing channel specific permissions failed.
        ~discord.NotFound
            The role or member being edited is not part of the guild.
        ~discord.InvalidArgument
            The overwrite parameter invalid or the target type was not
            :class:`~discord.Role` or :class:`~discord.Member`.
        """
        http = self._state.http

        if isinstance(target, User):
            perm_type = _Overwrites.MEMBER
        elif isinstance(target, Role):
            perm_type = _Overwrites.ROLE
        else:
            raise InvalidArgument("target parameter must be either Member or Role")

        if overwrite is MISSING:
            if len(permissions) == 0:
                raise InvalidArgument("No overwrite provided.")
            try:
                overwrite = PermissionOverwrite(**permissions)
            except (ValueError, TypeError):
                raise InvalidArgument(
                    "Invalid permissions given to keyword arguments."
                ) from None
        elif len(permissions) > 0:
            raise InvalidArgument("Cannot mix overwrite and keyword arguments.")

        # TODO: wait for event

        if overwrite is None:
            await http.delete_channel_permissions(self.id, target.id, reason=reason)
        elif isinstance(overwrite, PermissionOverwrite):
            allow, deny = overwrite.pair()
            await http.edit_channel_permissions(
                self.id, target.id, allow.value, deny.value, perm_type, reason=reason
            )
        else:
            raise InvalidArgument("Invalid overwrite type provided.")

    async def _clone_impl(
        self,
        base_attrs: dict[str, Any],
        *,
        name: str | None = None,
        reason: str | None = None,
    ) -> Self:
        base_attrs["permission_overwrites"] = [x._asdict() for x in self._overwrites]
        base_attrs["parent_id"] = self.category_id
        base_attrs["name"] = name or self.name
        guild_id = self.guild.id
        cls = self.__class__
        data = await self._state.http.create_channel(
            guild_id, self.type.value, reason=reason, **base_attrs
        )
        obj = cls(state=self._state, guild=self.guild, data=data)

        # temporarily add it to the cache
        await self._state._add_channel(guild_id, obj)
        return obj

    async def clone(
        self, *, name: str | None = None, reason: str | None = None
    ) -> Self:
        """|coro|

        Clones this channel. This creates a channel with the same properties
        as this channel.

        You must have the :attr:`~discord.Permissions.manage_channels` permission to
        do this.

        .. versionadded:: 1.1

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the new channel. If not provided, defaults to this
            channel name.
        reason: Optional[:class:`str`]
            The reason for cloning this channel. Shows up on the audit log.

        Returns
        -------
        :class:`.abc.GuildChannel`
            The channel that was created.

        Raises
        ------
        ~discord.Forbidden
            You do not have the proper permissions to create this channel.
        ~discord.HTTPException
            Creating the channel failed.
        """
        raise NotImplementedError

    @overload
    async def move(
        self,
        *,
        beginning: bool,
        offset: int = MISSING,
        category: Snowflake | None = MISSING,
        sync_permissions: bool = MISSING,
        reason: str | None = MISSING,
    ) -> None: ...

    @overload
    async def move(
        self,
        *,
        end: bool,
        offset: int = MISSING,
        category: Snowflake | None = MISSING,
        sync_permissions: bool = MISSING,
        reason: str = MISSING,
    ) -> None: ...

    @overload
    async def move(
        self,
        *,
        before: Snowflake,
        offset: int = MISSING,
        category: Snowflake | None = MISSING,
        sync_permissions: bool = MISSING,
        reason: str = MISSING,
    ) -> None: ...

    @overload
    async def move(
        self,
        *,
        after: Snowflake,
        offset: int = MISSING,
        category: Snowflake | None = MISSING,
        sync_permissions: bool = MISSING,
        reason: str = MISSING,
    ) -> None: ...

    async def move(self, **kwargs: Any) -> None:
        """|coro|

        A rich interface to help move a channel relative to other channels.

        If exact position movement is required, ``edit`` should be used instead.

        You must have the :attr:`~discord.Permissions.manage_channels` permission to
        do this.

        .. note::

            Voice channels will always be sorted below text channels.
            This is a Discord limitation.

        .. versionadded:: 1.7

        Parameters
        ----------
        beginning: :class:`bool`
            Whether to move the channel to the beginning of the
            channel list (or category if given).
            This is mutually exclusive with ``end``, ``before``, and ``after``.
        end: :class:`bool`
            Whether to move the channel to the end of the
            channel list (or category if given).
            This is mutually exclusive with ``beginning``, ``before``, and ``after``.
        before: :class:`~discord.abc.Snowflake`
            The channel that should be before our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``after``.
        after: :class:`~discord.abc.Snowflake`
            The channel that should be after our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``before``.
        offset: :class:`int`
            The number of channels to offset the move by. For example,
            an offset of ``2`` with ``beginning=True`` would move
            it 2 after the beginning. A positive number moves it below
            while a negative number moves it above. Note that this
            number is relative and computed after the ``beginning``,
            ``end``, ``before``, and ``after`` parameters.
        category: Optional[:class:`~discord.abc.Snowflake`]
            The category to move this channel under.
            If ``None`` is given then it moves it out of the category.
            This parameter is ignored if moving a category channel.
        sync_permissions: :class:`bool`
            Whether to sync the permissions with the category (if given).
        reason: :class:`str`
            The reason for the move.

        Raises
        ------
        InvalidArgument
            An invalid position was given or a bad mix of arguments was passed.
        Forbidden
            You do not have permissions to move the channel.
        HTTPException
            Moving the channel failed.
        """
        if not kwargs:
            return

        beginning, end = kwargs.get("beginning"), kwargs.get("end")
        before, after = kwargs.get("before"), kwargs.get("after")
        offset = kwargs.get("offset", 0)
        if sum(bool(a) for a in (beginning, end, before, after)) > 1:
            raise InvalidArgument(
                "Only one of [before, after, end, beginning] can be used."
            )

        bucket = self._sorting_bucket
        parent_id: Any = kwargs.get("category", MISSING)
        channels: list[GuildChannel]
        if parent_id not in (MISSING, None):
            parent_id = parent_id.id
            channels = [
                ch
                for ch in await self._get_cached_channels()
                if ch._sorting_bucket == bucket and ch.category_id == parent_id
            ]
        else:
            channels = [
                ch
                for ch in await self._get_cached_channels()
                if ch._sorting_bucket == bucket and ch.category_id == self.category_id
            ]

        channels.sort(key=lambda c: (c.position, c.id))

        with contextlib.suppress(ValueError):
            # Try to remove ourselves from the channel list
            # If we're not there then it's probably due to not being in the category
            channels.remove(self)

        index = None
        if beginning:
            index = 0
        elif end:
            index = len(channels)
        elif before:
            index = next((i for i, c in enumerate(channels) if c.id == before.id), None)
        elif after:
            index = next(
                (i + 1 for i, c in enumerate(channels) if c.id == after.id), None
            )

        if index is None:
            raise InvalidArgument("Could not resolve appropriate move position")

        channels.insert(max((index + offset), 0), self)
        payload: list[ChannelPositionUpdate] = []
        lock_permissions = kwargs.get("sync_permissions", False)
        reason = kwargs.get("reason")
        for index, channel in enumerate(channels):
            d: ChannelPositionUpdate = {"id": channel.id, "position": index}
            if parent_id is not MISSING and channel.id == self.id:
                d.update(parent_id=parent_id, lock_permissions=lock_permissions)
            payload.append(d)

        await self._state.http.bulk_channel_update(
            self.guild.id, payload, reason=reason
        )

    async def create_invite(
        self,
        *,
        reason: str | None = None,
        max_age: int = 0,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = True,
        target_event: ScheduledEvent | None = None,
        target_type: InviteTarget | None = None,
        target_user: User | None = None,
        target_application_id: int | None = None,
        roles: list[Role | Object] | None = None,
        target_users_file: File | None = None,
        target_user_ids: Sequence[int] | None = None,
    ) -> Invite:
        """|coro|

        Creates an instant invite from a text or voice channel.

        You must have the :attr:`~discord.Permissions.create_instant_invite` permission to
        do this.

        Parameters
        ----------
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
        target_type: Optional[:class:`.InviteTarget`]
            The type of target for the voice channel invite, if any.

            .. versionadded:: 2.0

        target_user: Optional[:class:`User`]
            The user whose stream to display for this invite, required if `target_type` is `TargetType.stream`.
            The user must be streaming in the channel.

            .. versionadded:: 2.0

        target_application_id: Optional[:class:`int`]
            The id of the embedded application for the invite, required if `target_type` is
            `TargetType.embedded_application`.

            .. versionadded:: 2.0

        target_event: Optional[:class:`.ScheduledEvent`]
            The scheduled event object to link to the event.
            Shortcut to :meth:`.Invite.set_scheduled_event`

            See :meth:`.Invite.set_scheduled_event` for more
            info on event invite linking.

            .. versionadded:: 2.0

        roles: Optional[List[Union[:class:`.Role`, :class:`.Object`]]]
            The roles to give a user when joining through this invite.

            You must have the :attr:`~Permissions.manage_roles` permission to do this and roles cannot be higher than your own.

            .. versionadded:: 2.8

        target_users_file: Optional[:class:`File`]
            A CSV file with a single column of user IDs for all the users able to accept this invite.

            You can use :func:`utils.users_to_csv` to generate a virtual CSV file from a sequence of user IDs.

            .. versionadded:: 2.8

        target_user_ids: Optional[Sequence[:class:`int`]]
            The IDs of the users able to see and accept this invite, up to 1000. Unlike
            ``target_users_file`` no CSV file is needed. Mutually exclusive with ``target_users_file``.

            .. versionadded:: 3.0

        Returns
        -------
        :class:`~discord.Invite`
            The invite that was created.

        Raises
        ------
        ~discord.HTTPException
            Invite creation failed.

        ~discord.NotFound
            The channel that was passed is a category or an invalid channel.
        """
        data = await self._state.http.create_invite(
            self.id,
            reason=reason,
            max_age=max_age,
            max_uses=max_uses,
            temporary=temporary,
            unique=unique,
            target_type=cast("InviteTargetType", target_type.value)
            if target_type
            else None,
            target_user_id=target_user.id if target_user else None,
            target_application_id=target_application_id,
            roles=[str(r.id) for r in roles] if roles else None,
            target_users_file=target_users_file,
            target_user_ids=list(target_user_ids)
            if target_user_ids is not None
            else None,
        )
        invite = Invite.from_incomplete(data=data, state=self._state)

        if target_event:
            invite.set_scheduled_event(target_event)
        return invite

    async def invites(self) -> list[Invite]:
        """|coro|

        Returns a list of all active instant invites from this channel.

        You must have :attr:`~discord.Permissions.manage_channels` to get this information.

        Returns
        -------
        List[:class:`~discord.Invite`]
            The list of invites that are currently active.

        Raises
        ------
        ~discord.Forbidden
            You do not have proper permissions to get the information.
        ~discord.HTTPException
            An error occurred while fetching the information.
        """
        state = self._state
        data = await state.http.invites_from_channel(self.id)
        guild = self.guild
        return [
            Invite(state=state, data=invite, channel=self, guild=guild)
            for invite in data
        ]

    def search_messages(self, **filters: Any) -> MessageSearchIterator:
        """Retrieves an :class:`.AsyncIterator` of the messages of this channel matching a search.

        This is :meth:`Guild.search_messages` with ``channels`` set to this channel.

        .. versionadded:: 3.0
        """
        return self.guild.search_messages(channels=[self], **filters)


class Messageable:
    """An ABC that details the common operations on a model that can send messages.

    The following implement this ABC:

    - :class:`~discord.TextChannel`
    - :class:`~discord.VoiceChannel`
    - :class:`~discord.StageChannel`
    - :class:`~discord.DMChannel`
    - :class:`~discord.GroupChannel`
    - :class:`~discord.User`
    - :class:`~discord.Member`
    - :class:`~discord.ext.commands.Context`
    - :class:`~discord.Thread`
    - :class:`~discord.ApplicationContext`
    """

    __slots__ = ()
    _state: ConnectionState

    async def _get_channel(self) -> MessageableChannel:
        raise NotImplementedError

    @overload
    async def send(
        self,
        content: str | None = ...,
        *,
        tts: bool = ...,
        embed: Embed = ...,
        file: File = ...,
        stickers: Sequence[GuildSticker | StickerItem] = ...,
        delete_after: float | None = ...,
        nonce: int | str = ...,
        enforce_nonce: bool = ...,
        allowed_mentions: AllowedMentions | None = ...,
        reference: Message | MessageReference | PartialMessage | None = ...,
        mention_author: bool | None = ...,
        view: BaseView = ...,
        poll: Poll = ...,
        suppress: bool = ...,
        suppress_embeds: bool = ...,
        silent: bool = ...,
        shared_client_theme: SharedClientTheme = ...,
    ) -> Message: ...

    @overload
    async def send(
        self,
        content: str | None = ...,
        *,
        tts: bool = ...,
        embed: Embed = ...,
        files: list[File] = ...,
        stickers: Sequence[GuildSticker | StickerItem] = ...,
        delete_after: float | None = ...,
        nonce: int | str = ...,
        enforce_nonce: bool = ...,
        allowed_mentions: AllowedMentions | None = ...,
        reference: Message | MessageReference | PartialMessage | None = ...,
        mention_author: bool | None = ...,
        view: BaseView = ...,
        poll: Poll = ...,
        suppress: bool = ...,
        suppress_embeds: bool = ...,
        silent: bool = ...,
        shared_client_theme: SharedClientTheme = ...,
    ) -> Message: ...

    @overload
    async def send(
        self,
        content: str | None = ...,
        *,
        tts: bool = ...,
        embeds: list[Embed] = ...,
        file: File = ...,
        stickers: Sequence[GuildSticker | StickerItem] = ...,
        delete_after: float | None = ...,
        nonce: int | str = ...,
        enforce_nonce: bool = ...,
        allowed_mentions: AllowedMentions | None = ...,
        reference: Message | MessageReference | PartialMessage | None = ...,
        mention_author: bool | None = ...,
        view: BaseView = ...,
        poll: Poll = ...,
        suppress: bool = ...,
        suppress_embeds: bool = ...,
        silent: bool = ...,
        shared_client_theme: SharedClientTheme = ...,
    ) -> Message: ...

    @overload
    async def send(
        self,
        content: str | None = ...,
        *,
        tts: bool = ...,
        embeds: list[Embed] = ...,
        files: list[File] = ...,
        stickers: Sequence[GuildSticker | StickerItem] = ...,
        delete_after: float | None = ...,
        nonce: int | str = ...,
        enforce_nonce: bool = ...,
        allowed_mentions: AllowedMentions | None = ...,
        reference: Message | MessageReference | PartialMessage | None = ...,
        mention_author: bool | None = ...,
        view: BaseView = ...,
        poll: Poll = ...,
        suppress: bool = ...,
        suppress_embeds: bool = ...,
        silent: bool = ...,
        shared_client_theme: SharedClientTheme = ...,
    ) -> Message: ...

    async def send(
        self,
        content: Any = None,
        *,
        tts: bool | None = None,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        stickers: Sequence[GuildSticker | StickerItem] | None = None,
        delete_after: float | None = None,
        nonce: int | str | None = None,
        enforce_nonce: bool | None = None,
        allowed_mentions: AllowedMentions | None = None,
        reference: Message | MessageReference | PartialMessage | None = None,
        mention_author: bool | None = None,
        view: BaseView | None = None,
        poll: Poll | None = None,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
        silent: bool | None = None,
        shared_client_theme: SharedClientTheme | None = None,
    ) -> Message:
        """|coro|

        Sends a message to the destination with the content given.

        The content must be a type that can convert to a string through ``str(content)``.
        If the content is set to ``None`` (the default), then the ``embed`` parameter must
        be provided.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`~discord.File` object. To upload multiple files, the ``files``
        parameter should be used with a :class:`list` of :class:`~discord.File` objects.
        **Specifying both parameters will lead to an exception**.

        To upload a single embed, the ``embed`` parameter should be used with a
        single :class:`~discord.Embed` object. To upload multiple embeds, the ``embeds``
        parameter should be used with a :class:`list` of :class:`~discord.Embed` objects.
        **Specifying both parameters will lead to an exception**.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content of the message to send.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        embed: :class:`~discord.Embed`
            The rich embed for the content.
        file: :class:`~discord.File`
            The file to upload.
        files: List[:class:`~discord.File`]
            A list of files to upload. Must be a maximum of 10.
        nonce: Union[:class:`str`, :class:`int`]
            The nonce to use for sending this message. If the message was successfully sent,
            then the message will have a nonce with this value.
        enforce_nonce: Optional[:class:`bool`]
            Whether :attr:`nonce` is enforced to be validated.

            .. versionadded:: 2.5
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: :class:`~discord.AllowedMentions`
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.

            .. versionadded:: 1.4

        reference: Union[:class:`~discord.Message`, :class:`~discord.MessageReference`, :class:`~discord.PartialMessage`]
            A reference to the :class:`~discord.Message` being replied to or forwarded. This can be created using
            :meth:`~discord.Message.to_reference`.
            When replying, you can control whether this mentions the author of the referenced message using the
            :attr:`~discord.AllowedMentions.replied_user` attribute of ``allowed_mentions`` or by
            setting ``mention_author``.

            .. versionadded:: 1.6

        mention_author: Optional[:class:`bool`]
            If set, overrides the :attr:`~discord.AllowedMentions.replied_user` attribute of ``allowed_mentions``.

            .. versionadded:: 1.6
        view: :class:`discord.ui.BaseView`
            A Discord UI View to add to the message.
        embeds: List[:class:`~discord.Embed`]
            A list of embeds to upload. Must be a maximum of 10.

            .. versionadded:: 2.0
        stickers: Sequence[Union[:class:`~discord.GuildSticker`, :class:`~discord.StickerItem`]]
            A list of stickers to upload. Must be a maximum of 3.

            .. versionadded:: 2.0
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.

            .. versionadded:: 2.4
        poll: :class:`Poll`
            The poll to send.

            .. versionadded:: 2.6
        shared_client_theme: :class:`SharedClientTheme`
            The client theme to share via the message. It cannot be combined with
            a view using components v2.

            .. versionadded:: 3.0

        Returns
        -------
        :class:`~discord.Message`
            The message that was sent.

        Raises
        ------
        ~discord.HTTPException
            Sending the message failed.
        ~discord.Forbidden
            You do not have the proper permissions to send the message.
        ~discord.InvalidArgument
            The ``files`` list is not of the appropriate size,
            you specified both ``file`` and ``files``,
            or you specified both ``embed`` and ``embeds``,
            or the ``reference`` object is not a :class:`~discord.Message`,
            :class:`~discord.MessageReference` or :class:`~discord.PartialMessage`.
        """
        channel = await self._get_channel()
        state = self._state
        text = str(content) if content is not None else None

        if embed is not None and embeds is not None:
            raise InvalidArgument(
                "cannot pass both embed and embeds parameter to send()"
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

        if suppress is not None:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is None:
                suppress_embeds = suppress

        flags = MessageFlags(
            suppress_embeds=bool(suppress_embeds),
            suppress_notifications=bool(silent),
        )

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

        if mention_author is not None:
            mentions_payload = mentions_payload or AllowedMentions().to_dict()
            mentions_payload["replied_user"] = bool(mention_author)

        _reference: MessageReferencePayload | None = None
        if reference is not None:
            try:
                _reference = reference.to_message_reference_dict()
                from .message import MessageReference

                if not isinstance(reference, MessageReference):
                    utils.warn_deprecated(
                        f"Passing {type(reference).__name__} to reference",
                        "MessageReference",
                        "2.7",
                        "3.0",
                    )
            except AttributeError:
                raise InvalidArgument(
                    "reference parameter must be Message, MessageReference, or"
                    " PartialMessage"
                ) from None

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
                if shared_client_theme is not None:
                    raise TypeError(
                        "cannot send a shared client theme with a view using v2 component logic"
                    )
                flags.is_components_v2 = True
        else:
            components = None

        theme_payload: SharedClientThemePayload | None = None
        if shared_client_theme is not None:
            theme_payload = shared_client_theme.to_dict()

        poll_payload: PollPayload | None = None
        if poll:
            poll_payload = poll.to_dict()

        if file is not None and files is not None:
            raise InvalidArgument("cannot pass both file and files parameter to send()")

        if file is not None:
            if not isinstance(file, File):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidArgument("file parameter must be File")
            files = [file]
        elif files is not None:
            if len(files) > 10:
                raise InvalidArgument(
                    "files parameter must be a list of up to 10 elements"
                )
            if not all(isinstance(f, File) for f in files):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidArgument("files parameter must be a list of File")

        if files is not None:
            flags = flags + MessageFlags(
                is_voice_message=any(isinstance(f, VoiceMessage) for f in files)
            )
            try:
                data = await state.http.send_files(
                    channel.id,
                    files=files,
                    content=text,
                    tts=bool(tts),
                    embed=embed_payload,
                    embeds=embeds_payload,
                    nonce=nonce,
                    enforce_nonce=enforce_nonce,
                    allowed_mentions=mentions_payload,
                    message_reference=_reference,
                    stickers=sticker_ids,
                    components=components,
                    flags=flags.value,
                    poll=poll_payload,
                    shared_client_theme=theme_payload,
                )
            finally:
                for f in files:
                    f.close()
        else:
            data = await state.http.send_message(
                channel.id,
                text,
                tts=bool(tts),
                embed=embed_payload,
                embeds=embeds_payload,
                nonce=nonce,
                enforce_nonce=enforce_nonce,
                allowed_mentions=mentions_payload,
                message_reference=_reference,
                stickers=sticker_ids,
                components=components,
                flags=flags.value,
                poll=poll_payload,
                shared_client_theme=theme_payload,
            )

        ret = await state._create_message(channel=channel, data=data)
        if view:
            if view.is_dispatchable():
                state.store_view(view, ret.id)
            view.message = ret
            view._refresh(ret.components)

        if delete_after is not None:
            await ret.delete(delay=delete_after)
        return ret

    async def trigger_typing(self) -> None:
        """|coro|

        Triggers a *typing* indicator to the destination.

        *Typing* indicator will go away after 10 seconds, or after a message is sent.
        """
        channel = await self._get_channel()
        await self._state.http.send_typing(channel.id)

    def typing(self) -> Typing:
        """Returns a context manager that allows you to type for an indefinite period of time.

        This is useful for denoting long computations in your bot.

        .. note::

            This is both a regular context manager and an async context manager.
            This means that both ``with`` and ``async with`` work with this.

        Example Usage: ::

            async with channel.typing():
                # simulate something heavy
                await asyncio.sleep(10)

            await channel.send("done!")
        """
        return Typing(self)

    async def fetch_message(self, id: int, /) -> Message:
        """|coro|

        Retrieves a single :class:`~discord.Message` from the destination.

        Parameters
        ----------
        id: :class:`int`
            The message ID to look for.

        Returns
        -------
        :class:`~discord.Message`
            The message asked for.

        Raises
        ------
        ~discord.NotFound
            The specified message was not found.
        ~discord.Forbidden
            You do not have the permissions required to get a message.
        ~discord.HTTPException
            Retrieving the message failed.
        """
        channel = await self._get_channel()
        data = await self._state.http.get_message(channel.id, id)
        return await self._state._cache_fetched(
            await self._state._create_message(channel=channel, data=data)
        )

    def pins(
        self,
        *,
        limit: int | None = 50,
        before: SnowflakeTime | None = None,
    ) -> MessagePinIterator:
        """Returns a :class:`~discord.MessagePinIterator` that enables receiving the destination's pinned messages.

        You must have :attr:`~discord.Permissions.read_message_history` permissions to use this.

        .. warning::

            Starting from version 3.0, `await channel.pins()` will no longer return a list of :class:`Message`. See examples below for new usage instead.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of pinned messages to retrieve.
            If ``None``, retrieves every pinned message in the channel.
        before: Optional[Union[:class:`~discord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages pinned before this datetime.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.

        Yields
        ------
        :class:`~discord.MessagePin`
            The pinned message.

        Raises
        ------
        ~discord.Forbidden
            You do not have permissions to get pinned messages.
        ~discord.HTTPException
            The request to get pinned messages failed.

        Examples
        --------
        Usage ::

            counter = 0
            async for pin in channel.pins(limit=250):
                if pin.message.author == client.user:
                    counter += 1

        Flattening into a list: ::

            pins = await channel.pins(limit=None).flatten()
            # pins is now a list of MessagePin...

        All parameters are optional.
        """
        return MessagePinIterator(
            self,
            limit=limit,
            before=before,
        )

    def _send_permissions(
        self, objects: tuple[Any, ...]
    ) -> tuple[Any, list[str]] | None:
        mapping = {
            "Message": "send_messages",
            "Embed": "embed_links",
            "File": "attach_files",
            "GuildEmoji": "use_external_emojis",
            "GuildSticker": "use_external_stickers",
        }
        no_permissions = ("DMChannel", "GroupChannel")
        if type(self).__name__ in no_permissions:
            return None

        channel: Any
        if hasattr(self, "permissions_for"):
            channel = cast("Any", self)
        elif hasattr(self, "channel") and type(
            cast("Any", self).channel
        ).__name__ not in (no_permissions):
            channel = cast("Any", self).channel
        else:
            return None  # Permissions don't exist for User DMs

        required: list[str] = []
        for obj in (None, *objects):  # Makes sure we check for send_messages first
            try:
                if obj is None:
                    permission = mapping["Message"]
                else:
                    permission = (
                        mapping.get(type(obj).__name__) or mapping[obj.__name__]
                    )

                    if type(obj).__name__ == "GuildEmoji":
                        if (
                            obj._to_partial().is_unicode_emoji()
                            or obj.guild_id == channel.guild.id
                        ):
                            continue
                    elif (
                        type(obj).__name__ == "GuildSticker"
                        and obj.guild_id == channel.guild.id
                    ):
                        continue

            except (KeyError, AttributeError):
                raise TypeError(f"The object {obj} is of an invalid type.") from None

            required.append(permission)

        return channel, required

    def can_send(self, *objects: Any) -> bool:
        """Returns a :class:`bool` indicating whether you have the permissions to send the object(s).

        This reads the cache synchronously and raises
        :class:`~discord.SyncCacheAccessError` with a remote cache backend,
        use :meth:`check_can_send` there.

        Returns
        -------
        :class:`bool`
            Indicates whether you have the permissions to send the object(s).

        Raises
        ------
        TypeError
            An invalid type has been passed.
        """
        plan = self._send_permissions(objects)
        if plan is None:
            return True

        channel, required = plan
        self_id = self._state.self_id
        me = (
            self._state._guild_bucket("members", channel.guild.id).get_nowait(self_id)
            if self_id is not None
            else None
        )
        if me is None:
            raise ClientException("The bot's member is not cached.")

        permissions = channel.permissions_for(me)
        return all(getattr(permissions, permission) for permission in required)

    async def check_can_send(self, *objects: Any) -> bool:
        """|coro|

        Returns a :class:`bool` indicating whether you have the permissions to send the object(s),
        reading the cache through its asynchronous API.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`bool`
            Indicates whether you have the permissions to send the object(s).

        Raises
        ------
        TypeError
            An invalid type has been passed.
        ClientException
            The bot's member is not cached.
        """
        plan = self._send_permissions(objects)
        if plan is None:
            return True

        channel, required = plan
        me = await self._state._get_member(channel.guild.id, self._state.self_id)
        if me is None:
            raise ClientException("The bot's member is not cached.")

        permissions = await channel.get_permissions_for(me)
        return all(getattr(permissions, permission) for permission in required)

    def history(
        self,
        *,
        limit: int | None = 100,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        around: SnowflakeTime | None = None,
        oldest_first: bool | None = None,
    ) -> HistoryIterator:
        """Returns an :class:`~discord.AsyncIterator` that enables receiving the destination's message history.

        You must have :attr:`~discord.Permissions.read_message_history` permissions to use this.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The number of messages to retrieve.
            If ``None``, retrieves every message in the channel. Note, however,
            that this would make it a slow operation.
        before: Optional[Union[:class:`~discord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages before this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
        after: Optional[Union[:class:`~discord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages after this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
        around: Optional[Union[:class:`~discord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages around this date or message.
            If a datetime is provided, it is recommended to use a UTC aware datetime.
            If the datetime is naive, it is assumed to be local time.
            When using this argument, the maximum limit is 101. Note that if the limit is an
            even number, then this will return at most limit + 1 messages.
        oldest_first: Optional[:class:`bool`]
            If set to ``True``, return messages in oldest->newest order. Defaults to ``True`` if
            ``after`` is specified, otherwise ``False``.

        Yields
        ------
        :class:`~discord.Message`
            The message with the message data parsed.

        Raises
        ------
        ~discord.Forbidden
            You do not have permissions to get channel message history.
        ~discord.HTTPException
            The request to get message history failed.

        Examples
        --------
        Usage ::

            counter = 0
            async for message in channel.history(limit=200):
                if message.author == client.user:
                    counter += 1

        Flattening into a list: ::

            messages = await channel.history(limit=123).flatten()
            # messages is now a list of Message...

        All parameters are optional.
        """
        return HistoryIterator(
            self,
            limit=limit,
            before=before,
            after=after,
            around=around,
            oldest_first=oldest_first,
        )


class Connectable(Protocol):
    """An ABC that details the common operations on a channel that can connect to a voice server.

    The following implement this ABC:

    - :class:`~discord.VoiceChannel`
    - :class:`~discord.StageChannel`

    Note
    ----
    This ABC is not decorated with :func:`typing.runtime_checkable`, so will fail :func:`isinstance`/:func:`issubclass`
    checks.
    """

    __slots__ = ()
    _state: ConnectionState
    id: int

    def _get_voice_client_key(self) -> tuple[int, str]:
        raise NotImplementedError

    def _get_voice_state_pair(self) -> tuple[int, int]:
        raise NotImplementedError

    async def connect(
        self,
        *,
        timeout: float = 60.0,
        reconnect: bool = True,
        cls: Callable[[Client, Connectable], T] = MISSING,
    ) -> T:
        """|coro|

        Connects to voice and creates a :class:`VoiceClient` to establish
        your connection to the voice server.

        This requires :attr:`Intents.voice_states`.

        Parameters
        ----------
        timeout: :class:`float`
            The timeout in seconds to wait for the voice endpoint.
        reconnect: :class:`bool`
            Whether the bot should automatically attempt
            a reconnect if a part of the handshake fails
            or the gateway goes down.
        cls: Type[:class:`VoiceProtocol`]
            A type that subclasses :class:`~discord.VoiceProtocol` to connect with.
            Defaults to :class:`~discord.VoiceClient`.

        Returns
        -------
        :class:`~discord.VoiceProtocol`
            A voice client that is fully connected to the voice server.

        Raises
        ------
        asyncio.TimeoutError
            Could not connect to the voice channel in time.
        ~discord.ClientException
            You are already connected to a voice channel.
        ~discord.opus.OpusNotLoaded
            The opus library has not been loaded.
        """
        # import directly from _types so if the user does not have davey
        # it won't error here
        from .voice._types import VoiceProtocol

        if cls is MISSING:
            # if the user passes no cls, then actually import VoiceClient
            from .voice import VoiceClient

            cls = VoiceClient  # pyright: ignore[reportAssignmentType]

        key_id, _ = self._get_voice_client_key()
        state = self._state

        if state._get_voice_client(key_id):
            raise ClientException("Already connected to a voice channel.")

        client = state._get_client()
        voice = cls(client, self)

        if not isinstance(voice, VoiceProtocol):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Type must meet VoiceProtocol abstract base class.")

        state._add_voice_client(key_id, voice)

        try:
            await voice.connect(timeout=timeout, reconnect=reconnect)
        except asyncio.TimeoutError:
            # we don't care if disconnect failed because connection failed
            with contextlib.suppress(Exception):
                await voice.disconnect(force=True)
            raise  # re-raise

        return voice


class Mentionable:
    """An ABC that details the common operations on a mentionable model."""

    # TODO: documentation, methods if needed
