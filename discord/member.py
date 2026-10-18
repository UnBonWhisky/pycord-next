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

import inspect
import sys
from contextlib import suppress
from operator import attrgetter
from typing import TYPE_CHECKING, Any, TypeVar, cast

import discord.abc

from . import utils
from ._internal.aliases import AliasMixin
from ._internal.cache_peek import cached_guild_channel
from .activity import ActivityTypes, create_activity
from .asset import Asset
from .enums import ChannelType, Status, try_enum
from .errors import ClientException, InvalidArgument
from .flags import MemberFlags
from .object import Object
from .permissions import Permissions
from .primary_guild import PrimaryGuild
from .role import RoleColours
from .user import BaseUser, User, _UserTag
from .utils import MISSING, utcnow

__all__ = (
    "Member",
    "VoiceState",
)

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Callable, Sequence

    from typing_extensions import Self

    from .abc import Snowflake
    from .cache import CacheBucket
    from .channel import DMChannel, PartialGuildChannel, VocalGuildChannel
    from .client import Client
    from .collectibles import Collectibles
    from .colour import Colour
    from .flags import PublicUserFlags
    from .guild import Guild, PartialGuild
    from .iterators import MessageSearchIterator
    from .message import Message
    from .role import Role
    from .state import ConnectionState
    from .types.activity import PartialPresenceUpdate
    from .types.collectibles import AvatarDecoration
    from .types.member import (
        Member as MemberPayload,
        MemberUpdateEvent as MemberUpdateEventPayload,
        MemberWithUser as MemberWithUserPayload,
        UserWithMember as UserWithMemberPayload,
    )
    from .types.user import User as UserPayload
    from .types.voice import (
        VoiceState as GuildVoiceStatePayload,
        VoiceState as VoiceStatePayload,
    )


class VoiceState:
    """Represents a Discord user's voice state.

    Attributes
    ----------
    deaf: :class:`bool`
        Indicates if the user is currently deafened by the guild.
    mute: :class:`bool`
        Indicates if the user is currently muted by the guild.
    self_mute: :class:`bool`
        Indicates if the user is currently muted by their own accord.
    self_deaf: :class:`bool`
        Indicates if the user is currently deafened by their own accord.
    self_stream: :class:`bool`
        Indicates if the user is currently streaming via 'Go Live' feature.

        .. versionadded:: 1.3

    self_video: :class:`bool`
        Indicates if the user is currently broadcasting video.
    suppress: :class:`bool`
        Indicates if the user is suppressed from speaking.

        Only applies to stage channels.

        .. versionadded:: 1.7

    requested_to_speak_at: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC that the member
        requested to speak. It will be ``None`` if they are not requesting to speak
        anymore or have been accepted to speak.

        Only applicable to stage channels.

        .. versionadded:: 1.7

    afk: :class:`bool`
        Indicates if the user is currently in the AFK channel in the guild.
    channel_id: Optional[:class:`int`]
        The ID of the voice channel that the user is currently connected to. ``None`` if the user
        is not currently in a voice channel.
    guild_id: Optional[:class:`int`]
        The ID of the guild the voice state belongs to.
    """

    __slots__ = (
        "_state",
        "afk",
        "channel_id",
        "deaf",
        "guild_id",
        "mute",
        "requested_to_speak_at",
        "self_deaf",
        "self_mute",
        "self_stream",
        "self_video",
        "session_id",
        "suppress",
    )

    def __init__(
        self,
        *,
        data: VoiceStatePayload | GuildVoiceStatePayload,
        state: ConnectionState | None = None,
        channel: VocalGuildChannel | None = None,
    ) -> None:
        if state is None and channel is not None:
            state = channel._state
        self._state: ConnectionState | None = state
        self.session_id: str = data.get("session_id")
        guild_id = utils._get_as_snowflake(data, "guild_id")
        if guild_id is None and channel is not None:
            guild_id = channel.guild_id
        self.guild_id: int | None = guild_id
        self._update(data, channel)

    @property
    def channel(self) -> VocalGuildChannel | PartialGuildChannel | None:
        """The voice channel that the user is currently connected to.

        ``None`` if the user is not currently in a voice channel.

        This is the cached channel with the in-process cache, and a
        :class:`PartialGuildChannel` handle when it is not cached or the cache
        backend is not the in-process one. Use :meth:`PartialGuildChannel.get` to
        get the cached channel with any backend.
        """
        if self.channel_id is None or self.guild_id is None or self._state is None:
            return None
        cached = cached_guild_channel(self._state, self.guild_id, self.channel_id)
        if cached is not None:
            return cast("VocalGuildChannel", cached)
        from .channel import PartialGuildChannel

        return PartialGuildChannel(
            state=self._state,
            id=self.channel_id,
            guild_id=self.guild_id,
            type=ChannelType.voice,
        )

    def _update(
        self,
        data: VoiceStatePayload | GuildVoiceStatePayload,
        channel: VocalGuildChannel | None,
    ) -> None:
        self.self_mute: bool = data.get("self_mute", False)
        self.self_deaf: bool = data.get("self_deaf", False)
        self.self_stream: bool = data.get("self_stream", False)
        self.self_video: bool = data.get("self_video", False)
        self.afk: bool = data.get("suppress", False)
        self.mute: bool = data.get("mute", False)
        self.deaf: bool = data.get("deaf", False)
        self.suppress: bool = data.get("suppress", False)
        self.requested_to_speak_at: dt.datetime | None = utils.parse_time(
            data.get("request_to_speak_timestamp")
        )
        self.channel_id: int | None = channel.id if channel is not None else None

    def __repr__(self) -> str:
        attrs = [
            ("self_mute", self.self_mute),
            ("self_deaf", self.self_deaf),
            ("self_stream", self.self_stream),
            ("suppress", self.suppress),
            ("requested_to_speak_at", self.requested_to_speak_at),
            ("channel", self.channel),
        ]
        inner = " ".join(f"{name}={value!r}" for name, value in attrs)
        return f"<{self.__class__.__name__} {inner}>"

    @classmethod
    def _create_default(cls, channel: VocalGuildChannel, client: Client) -> VoiceState:
        return cls(
            data=cast(
                "VoiceStatePayload",
                {
                    "channel_id": channel.id,
                    "guild_id": channel.guild_id,
                    "self_deaf": False,
                    "self_mute": False,
                    "user_id": client._connection.self_id,
                },
            ),
            state=client._connection,
            channel=channel,
        )


M = TypeVar("M", bound="Member")


def flatten_user(cls: type[M]) -> type[M]:
    for attr, value in [*BaseUser.__dict__.items(), *User.__dict__.items()]:
        # ignore private/special methods
        if attr.startswith("_"):
            continue

        # don't override what we already have
        if attr in cls.__dict__:
            continue

        # if it's a slotted attribute or a property, redirect it
        # slotted members are implemented as member_descriptors in Type.__dict__
        if not hasattr(value, "__annotations__"):
            getter = attrgetter(f"_user.{attr}")
            setattr(
                cls, attr, property(getter, doc=f"Equivalent to :attr:`User.{attr}`")
            )
        else:
            # Technically, this can also use attrgetter
            # However I'm not sure how I feel about "functions" returning properties
            # It probably breaks something in Sphinx.
            # probably a member function by now
            def generate_function(x: str, original: Any) -> Callable[..., Any]:
                general: Callable[..., Any]
                # We want sphinx to properly show coroutine functions as coroutines
                if inspect.iscoroutinefunction(original):

                    async def async_general(
                        self: Member, *args: Any, **kwargs: Any
                    ) -> Any:
                        return await getattr(self._user, x)(*args, **kwargs)

                    general = async_general

                else:

                    def sync_general(self: Member, *args: Any, **kwargs: Any) -> Any:
                        return getattr(self._user, x)(*args, **kwargs)

                    general = sync_general

                general.__name__ = x
                general.__qualname__ = f"Member.{x}"
                return general

            func = generate_function(attr, value)
            func = utils.copy_doc(value)(func)
            setattr(cls, attr, func)

    return cls


@flatten_user
class Member(discord.abc.Messageable, _UserTag, AliasMixin):
    """Represents a Discord member to a :class:`Guild`.

    This implements a lot of the functionality of :class:`User`.

    .. container:: operations

        .. describe:: x == y

            Checks if two members are equal.
            Note that this works with :class:`User` instances too.

        .. describe:: x != y

            Checks if two members are not equal.
            Note that this works with :class:`User` instances too.

        .. describe:: hash(x)

            Returns the member's hash.

        .. describe:: str(x)

            Returns the member's name with the discriminator or global_name.

    Attributes
    ----------
    joined_at: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC that the member joined the guild.
        If the member left and rejoined the guild, this will be the latest date. In certain cases, this can be ``None``.
    activities: Tuple[Union[:class:`BaseActivity`, :class:`Spotify`]]
        The activities that the user is currently doing.

        .. note::

            Due to a Discord API limitation, a user's Spotify activity may not appear
            if they are listening to a song with a title longer
            than 128 characters.

    guild_id: :class:`int`
        The ID of the guild that the member belongs to.
    nick: Optional[:class:`str`]
        The guild specific nickname of the user.
    pending: :class:`bool`
        Whether the member is pending member verification.

        .. versionadded:: 1.6
    premium_since: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC when the member used their
        "Nitro boost" on the guild, if available. This could be ``None``.
    communication_disabled_until: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies the date and time in UTC when the member will be removed from timeout.

        .. versionadded:: 2.0
    flags: :class:`MemberFlags`
        Extra attributes of the member.

        .. versionadded:: 2.6
    """

    __slots__ = (
        "_avatar",
        "_avatar_decoration",
        "_banner",
        "_client_status",
        "_roles",
        "_state",
        "_user",
        "activities",
        "communication_disabled_until",
        "flags",
        "guild_id",
        "joined_at",
        "nick",
        "pending",
        "premium_since",
    )

    if TYPE_CHECKING:
        name: str
        id: int
        discriminator: str
        bot: bool
        system: bool
        created_at: dt.datetime
        default_avatar: Asset
        avatar: Asset | None
        dm_channel: DMChannel | None
        get_dm_channel = User.get_dm_channel
        create_dm = User.create_dm
        mutual_guilds: list[Guild]
        get_mutual_guilds = User.get_mutual_guilds
        public_flags: PublicUserFlags
        banner: Asset | None
        accent_color: Colour | None
        accent_colour: Colour | None
        communication_disabled_until: dt.datetime | None
        primary_guild: PrimaryGuild | None
        collectibles: Collectibles | None
        avatar_decoration: Asset | None

    def __init__(
        self,
        *,
        data: MemberWithUserPayload | MemberUpdateEventPayload,
        guild: Guild | PartialGuild,
        state: ConnectionState,
    ) -> None:
        self._state: ConnectionState = state
        self._user: User = state.create_user(data["user"])
        self.guild_id: int = guild.id
        self.joined_at: dt.datetime | None = utils.parse_time(data.get("joined_at"))
        self.premium_since: dt.datetime | None = utils.parse_time(
            data.get("premium_since")
        )
        self._roles: utils.SnowflakeList = utils.SnowflakeList(map(int, data["roles"]))
        self._client_status: dict[str | None, str] = {None: "offline"}
        self.activities: tuple[ActivityTypes, ...] = ()
        self.nick: str | None = data.get("nick", None)
        self.pending: bool = data.get("pending", False)
        self._avatar: str | None = data.get("avatar")
        self._banner: str | None = data.get("banner")
        self.communication_disabled_until: dt.datetime | None = utils.parse_time(
            data.get("communication_disabled_until")
        )
        self.flags: MemberFlags = MemberFlags._from_value(data.get("flags") or 0)
        self._avatar_decoration: AvatarDecoration | None = data.get(
            "avatar_decoration_data"
        )

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild that the member belongs to.

        This is the cached :class:`Guild`, or a :class:`PartialGuild` handle when
        it is not cached or the cache backend is not the in-process one. Use
        :meth:`PartialGuild.get` to get the cached :class:`Guild` with any backend.
        """
        from .guild import PartialGuild

        state = self._state
        if state.cache.supports_sync:
            guild = state._guilds.get_nowait(self.guild_id)
            if guild is not None:
                return guild
        return PartialGuild(state=state, id=self.guild_id)

    def __str__(self) -> str:
        return str(self._user)

    def __repr__(self) -> str:
        if self._user.is_migrated:
            if self.global_name is not None:
                return (
                    "<Member"
                    f" id={self._user.id} name={self._user.name!r} global_name={self.global_name!r}"
                    f" bot={self._user.bot} nick={self.nick!r} guild={self.guild!r}>"
                )
            return (
                "<Member"
                f" id={self._user.id} name={self._user.name!r}"
                f" bot={self._user.bot} nick={self.nick!r} guild={self.guild!r}>"
            )
        return (
            "<Member"
            f" id={self._user.id} name={self._user.name!r} discriminator={self._user.discriminator!r}"
            f" bot={self._user.bot} nick={self.nick!r} guild={self.guild!r}>"
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UserTag) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self._user)

    @classmethod
    def _from_message(cls, *, message: Message, data: MemberPayload) -> Self:
        author = message.author
        user = author._user if isinstance(author, Member) else author
        data["user"] = user._to_minimal_user_json()
        return cls(
            data=cast("MemberWithUserPayload", data),
            guild=cast("Guild | PartialGuild", message.guild),
            state=message._state,
        )

    def _update_from_message(self, data: MemberPayload) -> None:
        self.joined_at = utils.parse_time(data.get("joined_at"))
        self.premium_since = utils.parse_time(data.get("premium_since"))
        self._roles = utils.SnowflakeList(map(int, data["roles"]))
        self.nick = data.get("nick", None)
        self.pending = data.get("pending", False)

    @classmethod
    def _try_upgrade(
        cls,
        *,
        data: UserWithMemberPayload,
        guild: Guild | PartialGuild,
        state: ConnectionState,
    ) -> User | Self:
        # A User object with a 'member' key
        try:
            member_data = data.pop("member")
        except KeyError:
            return state.create_user(data)
        else:
            full_data = cast("MemberWithUserPayload", member_data)
            full_data["user"] = data
            return cls(data=full_data, guild=guild, state=state)

    @classmethod
    def _copy(cls, member: Self) -> Self:
        self: Self = cls.__new__(cls)  # to bypass __init__

        self._roles = utils.SnowflakeList(member._roles, is_sorted=True)
        self.joined_at = member.joined_at
        self.premium_since = member.premium_since
        self._client_status = member._client_status.copy()
        self.guild_id = member.guild_id
        self.nick = member.nick
        self.pending = member.pending
        self.activities = member.activities
        self._state = member._state
        self._avatar = member._avatar
        self._banner = member._banner
        self.communication_disabled_until = member.communication_disabled_until
        self.flags = member.flags
        self._avatar_decoration = member._avatar_decoration

        # Reference will not be copied unless necessary by PRESENCE_UPDATE
        # See below
        self._user = member._user
        return self

    async def _get_channel(self) -> DMChannel:
        return await self.create_dm()

    def _update(self, data: MemberPayload | MemberUpdateEventPayload) -> None:
        # the nickname change is optional,
        # if it isn't in the payload then it didn't change
        if "nick" in data:
            self.nick = data["nick"]

        if "pending" in data:
            self.pending = data["pending"]

        self.premium_since = utils.parse_time(data.get("premium_since"))
        self._roles = utils.SnowflakeList(map(int, data["roles"]))
        self._avatar = data.get("avatar")
        self._banner = data.get("banner")
        self.communication_disabled_until = utils.parse_time(
            data.get("communication_disabled_until")
        )
        self.flags = MemberFlags._from_value(data.get("flags") or 0)
        self._avatar_decoration = data.get("avatar_decoration_data")

    def _presence_update(
        self, data: PartialPresenceUpdate, user: UserPayload | tuple[()]
    ) -> tuple[User, User] | None:
        self.activities = tuple(map(create_activity, data["activities"]))
        self._client_status = {
            sys.intern(key): sys.intern(value)
            for key, value in cast(
                "dict[str, str]", data.get("client_status", {})
            ).items()
        }
        self._client_status[None] = sys.intern(data["status"])

        if isinstance(user, dict) and len(user) > 1:
            return self._update_inner_user(user)
        return None

    def _update_inner_user(self, user: UserPayload) -> tuple[User, User] | None:
        u = self._user
        original = (
            u.name,
            u._avatar,
            u.discriminator,
            u.global_name,
            u._public_flags,
            u.primary_guild,
            u._collectibles,
            u._avatar_decoration,
        )
        # These keys seem to always be available
        if (
            new_primary_guild_data := user.get("primary_guild")
        ) and new_primary_guild_data.get("identity_enabled"):
            new_primary_guild: PrimaryGuild | None = PrimaryGuild(
                new_primary_guild_data, state=self._state
            )
        else:
            new_primary_guild = None
        modified = (
            user["username"],
            user["avatar"],
            user["discriminator"],
            user.get("global_name", None) or None,
            user.get("public_flags", 0),
            new_primary_guild,
            user.get("collectibles") or u._collectibles,
            user.get("avatar_decoration_data"),
        )
        if original != modified:
            to_return = User._copy(self._user)
            (
                u.name,
                u._avatar,
                u.discriminator,
                u.global_name,
                u._public_flags,
                u.primary_guild,
                u._collectibles,
                u._avatar_decoration,
            ) = modified
            # Signal to dispatch on_user_update
            return to_return, u
        return None

    @property
    def status(self) -> Status:
        """The member's overall status.

        If the value is unknown, then it will be a :class:`str` instead.
        """
        return try_enum(Status, self._client_status[None])

    @property
    def raw_status(self) -> str:
        """The member's overall status as a string value.

        .. versionadded:: 1.5
        """
        return self._client_status[None]

    @status.setter
    def status(self, value: Status) -> None:
        # internal use only
        self._client_status[None] = str(value)

    @property
    def mobile_status(self) -> Status:
        """The member's status on a mobile device, if applicable."""
        return try_enum(Status, self._client_status.get("mobile", "offline"))

    @property
    def desktop_status(self) -> Status:
        """The member's status on the desktop client, if applicable."""
        return try_enum(Status, self._client_status.get("desktop", "offline"))

    @property
    def vr_status(self) -> Status:
        """The member's status set for an active virtual reality application session, if applicable.

        .. versionadded:: 2.9
        """
        return try_enum(Status, self._client_status.get("vr", "offline"))

    @property
    def web_status(self) -> Status:
        """The member's status on the web client, if applicable."""
        return try_enum(Status, self._client_status.get("web", "offline"))

    @property
    def global_name(self) -> str | None:
        """The member's global name, if applicable."""
        return self._user.global_name

    def is_on_mobile(self) -> bool:
        """A helper function that determines if a member is active on a mobile device."""
        return "mobile" in self._client_status

    async def get_colour(self) -> Colour:
        """|coro|

        Returns the rendered primary colour for the member. If the default colour
        is the one rendered then an instance of :meth:`Colour.default` is returned.

        This is an alias for ``(await Member.get_colours()).primary``.

        Returns
        -------
        :class:`Colour`
            The rendered primary colour of the member.
        """
        return (await self.get_colours()).primary

    async def get_colours(self) -> RoleColours:
        """|coro|

        Returns the rendered :class:`RoleColours` for the member. If the default
        colour is the one rendered then an instance of :meth:`RoleColours.default`
        is returned.

        .. versionadded:: 2.8

        Returns
        -------
        :class:`RoleColours`
            The rendered colours of the member.
        """
        roles = (await self.get_roles())[1:]  # remove @everyone

        # highest order of the colour is the one that gets rendered.
        # if the highest is the default colour then the next one with a colour
        # is chosen instead
        for role in reversed(roles):
            if role.colours.primary.value:
                return role.colours
        return RoleColours.default()

    async def get_roles(self) -> list[Role]:
        r"""|coro|

        Returns the :class:`Role`\s that the member belongs to. Note
        that the first element of this list is always the default '@everyone'
        role.

        These roles are sorted by their position in the role hierarchy.

        Returns
        -------
        List[:class:`Role`]
            The cached roles of the member.
        """
        found = await self._roles_bucket().get_many({*self._roles, self.guild_id})
        return self._sorted_roles(found.get)

    def _roles_bucket(self) -> CacheBucket[int, Role]:
        return self._state._guild_bucket("roles", self.guild_id)

    def _sorted_roles(self, lookup: Callable[[int], Role | None]) -> list[Role]:
        result = [role for role_id in self._roles if (role := lookup(role_id))]
        default_role = lookup(self.guild_id)
        if default_role is not None:
            result.append(default_role)
        result.sort()
        return result

    def _permissions_from(self, roles: list[Role], *, is_owner: bool) -> Permissions:
        if is_owner:
            return Permissions.all()

        base = Permissions.none()
        for r in roles:
            base.value |= r.permissions.value

        if base.administrator:
            return Permissions.all()

        if self.timed_out:
            return Permissions(
                base.value
                & Permissions(view_channel=True, read_message_history=True).value
            )

        return base

    @property
    def colour(self) -> Colour:
        """A property that returns a colour denoting the rendered primary colour for the member. If the default colour is the one rendered then an instance of :meth:`Colour.default` is returned.

        This is an alias for ``Member.colours.primary``.
        """
        return self.colours.primary

    @property
    def colours(self) -> RoleColours:
        """A property that returns the rendered :class:`RoleColours` for the member. If the default color is the one rendered then an instance of :meth:`RoleColours.default`

        is returned.

        .. versionadded:: 2.8
        """
        roles = self.roles[1:]  # remove @everyone

        # highest order of the colour is the one that gets rendered.
        # if the highest is the default colour then the next one with a colour
        # is chosen instead
        for role in reversed(roles):
            if role.colours.primary.value:
                return role.colours
        return RoleColours.default()

    @property
    def roles(self) -> list[Role]:
        """A :class:`list` of :class:`Role` that the member belongs to. Note that the first element of this list is always the default '@everyone' role.

        These roles are sorted by their position in the role hierarchy.
        """
        return self._sorted_roles(self._roles_bucket().get_nowait)

    @property
    def mention(self) -> str:
        """Returns a string that allows you to mention the member."""
        return f"<@{self._user.id}>"

    @property
    def display_name(self) -> str:
        """Returns the user's display name.

        This will either be their guild specific nickname, global name or username.
        """
        return self.nick or self.global_name or self.name

    @property
    def display_avatar(self) -> Asset:
        """Returns the member's display avatar.

        Returns the user's guild avatar.
        If the user does not have a guild avatar, their global avatar is returned instead.

        .. versionadded:: 2.0
        """
        return self.guild_avatar or self._user.avatar or self._user.default_avatar

    @property
    def guild_avatar(self) -> Asset | None:
        """Returns an :class:`Asset` for the guild avatar the member has. If unavailable, ``None`` is returned.

        .. versionadded:: 2.0
        """
        if self._avatar is None:
            return None
        return Asset._from_guild_avatar(
            self._state, self.guild_id, self.id, self._avatar
        )

    @property
    def display_avatar_decoration(self) -> Asset | None:
        """Returns the member's displayed avatar decoration.

        Returns the user's guild avatar decoration.
        If the user does not have a guild avatar decoration, their global avatar decoration is returned instead.

        .. versionadded:: 2.8
        """
        return self.guild_avatar_decoration or self._user.avatar_decoration

    @property
    def guild_avatar_decoration(self) -> Asset | None:
        """Returns an :class:`Asset` for the guild specific avatar decoration the member has. If unavailable, ``None`` is returned.

        .. versionadded:: 2.8
        """
        if self._avatar_decoration is None:
            return None
        return Asset._from_avatar_decoration(
            self._state, self.id, self._avatar_decoration.get("asset")
        )

    @property
    def display_banner(self) -> Asset | None:
        """Returns the member's display banner.

        Returns the user's guild banner.
        If the user does not have a guild banner, their global banner is returned instead.

        .. versionadded:: 2.7
        """
        return self.guild_banner or self._user.banner

    @property
    def guild_banner(self) -> Asset | None:
        """Returns an :class:`Asset` for the guild banner the member has. If unavailable, ``None`` is returned.

        .. versionadded:: 2.7
        """
        if self._banner is None:
            return None
        return Asset._from_guild_banner(
            self._state, self.guild_id, self.id, self._banner
        )

    @property
    def activity(self) -> ActivityTypes | None:
        """Returns the primary activity the user is currently doing. Could be ``None`` if no activity is being done.

        .. note::

            Due to a Discord API limitation, this may be ``None`` if
            the user is listening to a song on Spotify with a title longer
            than 128 characters.

        .. note::

            A user may have multiple activities, these can be accessed under :attr:`activities`.
        """
        if self.activities:
            return self.activities[0]
        return None

    def mentioned_in(self, message: Message) -> bool:
        """Checks if the member is mentioned in the specified message.

        Parameters
        ----------
        message: :class:`Message`
            The message to check if you're mentioned in.

        Returns
        -------
        :class:`bool`
            Indicates if the member is mentioned in the message.
        """
        if message.guild_id is None or message.guild_id != self.guild_id:
            return False

        if self._user.mentioned_in(message):
            return True

        return any(self._roles.has(role.id) for role in message.role_mentions)

    @property
    def top_role(self) -> Role:
        """Returns the member's highest role.

        This is useful for figuring where a member stands in the role
        hierarchy chain.
        """
        bucket = self._roles_bucket()
        default_role = cast("Role", bucket.get_nowait(self.guild_id))
        if len(self._roles) == 0:
            return default_role

        return max(bucket.get_nowait(rid) or default_role for rid in self._roles)

    @property
    def guild_permissions(self) -> Permissions:
        """Returns the member's guild permissions.

        This only takes into consideration the guild permissions
        and not most of the implied permissions or any of the
        channel permission overwrites. For 100% accurate permission
        calculation, please use :meth:`abc.GuildChannel.permissions_for`.

        This does take into consideration guild ownership and the
        administrator implication.
        """
        guild = self._state._guilds.get_nowait(self.guild_id)
        return self._permissions_from(
            self.roles, is_owner=guild is not None and guild.owner_id == self.id
        )

    @property
    def voice(self) -> VoiceState | None:
        """Returns the member's current voice state."""
        return self._state._guild_bucket("voice_states", self.guild_id).get_nowait(
            self._user.id
        )

    async def get_top_role(self) -> Role | None:
        """|coro|

        Returns the member's highest role.

        This is useful for figuring where a member stands in the role
        hierarchy chain.

        Returns
        -------
        Optional[:class:`Role`]
            The highest cached role of the member, like :attr:`top_role`.
            ``None`` when the roles of the guild are not cached.
        """
        roles = await self.get_roles()
        return roles[-1] if roles else None

    async def get_guild_permissions(self) -> Permissions:
        """|coro|

        Returns the member's guild permissions.

        This only takes into consideration the guild permissions
        and not most of the implied permissions or any of the
        channel permission overwrites. For 100% accurate permission
        calculation, please use :meth:`abc.GuildChannel.permissions_for`.

        This does take into consideration guild ownership and the
        administrator implication. A member that is :attr:`timed_out` only
        keeps :attr:`~Permissions.view_channel` and
        :attr:`~Permissions.read_message_history`, unless they own the guild or
        have the administrator permission.

        Returns
        -------
        :class:`Permissions`
            The guild permissions of the member.
        """
        guild = await self._state._get_guild(self.guild_id)
        return self._permissions_from(
            await self.get_roles(),
            is_owner=guild is not None and guild.owner_id == self.id,
        )

    async def get_voice_state(self) -> VoiceState | None:
        """|coro|

        Returns the member's current voice state.

        Returns
        -------
        Optional[:class:`VoiceState`]
            The cached voice state, or ``None`` if the member is not connected to a voice channel.
        """
        return await self._state._guild_bucket("voice_states", self.guild_id).get(
            self._user.id
        )

    async def _get_voice_channel_id(self) -> int:
        voice = await self.get_voice_state()
        if voice is None or voice.channel_id is None:
            raise ClientException("The member is not connected to a voice channel.")
        return voice.channel_id

    @property
    def timed_out(self) -> bool:
        """Returns whether the member is timed out.

        .. versionadded:: 2.0
        """
        return (
            self.communication_disabled_until is not None
            and self.communication_disabled_until > utcnow()
        )

    async def ban(
        self,
        *,
        delete_message_seconds: int | None = None,
        reason: str | None = None,
    ) -> None:
        """|coro|

        Bans this member. Equivalent to :meth:`Guild.ban`.
        """
        await self.guild.ban(
            self,
            reason=reason,
            delete_message_seconds=delete_message_seconds,
        )

    async def unban(self, *, reason: str | None = None) -> None:
        """|coro|

        Unbans this member. Equivalent to :meth:`Guild.unban`.
        """
        await self.guild.unban(self, reason=reason)

    async def kick(self, *, reason: str | None = None) -> None:
        """|coro|

        Kicks this member. Equivalent to :meth:`Guild.kick`.
        """
        await self.guild.kick(self, reason=reason)

    async def edit(
        self,
        *,
        nick: str | None = MISSING,
        mute: bool = MISSING,
        deafen: bool = MISSING,
        suppress: bool = MISSING,
        roles: Sequence[discord.abc.Snowflake] = MISSING,
        voice_channel: VocalGuildChannel | None = MISSING,
        reason: str | None = None,
        communication_disabled_until: dt.datetime | None = MISSING,
        bypass_verification: bool | None = MISSING,
        banner: bytes | None = MISSING,
        avatar: bytes | None = MISSING,
        bio: str | None = MISSING,
    ) -> Member | None:
        """|coro|

        Edits the member's data.

        Depending on the parameter passed, this requires different permissions listed below:

        +------------------------------+--------------------------------------+
        |   Parameter                  |              Permission              |
        +------------------------------+--------------------------------------+
        | nick                         | :attr:`Permissions.manage_nicknames` |
        +------------------------------+--------------------------------------+
        | mute                         | :attr:`Permissions.mute_members`     |
        +------------------------------+--------------------------------------+
        | deafen                       | :attr:`Permissions.deafen_members`   |
        +------------------------------+--------------------------------------+
        | roles                        | :attr:`Permissions.manage_roles`     |
        +------------------------------+--------------------------------------+
        | voice_channel                | :attr:`Permissions.move_members`     |
        +------------------------------+--------------------------------------+
        | communication_disabled_until | :attr:`Permissions.moderate_members` |
        +------------------------------+--------------------------------------+
        | bypass_verification          | See note below                       |
        +------------------------------+--------------------------------------+

        .. note::

            `bypass_verification` may be edited under three scenarios:

            - Client has :attr:`Permissions.manage_guild`

            - Client has :attr:`Permissions.manage_roles`

            - Client has ALL THREE of :attr:`Permissions.moderate_members`, :attr:`Permissions.kick_members`, and :attr:`Permissions.ban_members`

        .. note::

            The following parameters are only available when editing the bot's own member:

            - ``avatar``
            - ``banner``
            - ``bio``

        All parameters are optional.

        .. versionchanged:: 1.1
            Can now pass ``None`` to ``voice_channel`` to kick a member from voice.

        .. versionchanged:: 2.0
            The newly member is now optionally returned, if applicable.

        Parameters
        ----------
        nick: Optional[:class:`str`]
            The member's new nickname. Use ``None`` to remove the nickname.
        mute: :class:`bool`
            Indicates if the member should be guild muted or un-muted.
        deafen: :class:`bool`
            Indicates if the member should be guild deafened or un-deafened.
        suppress: :class:`bool`
            Indicates if the member should be suppressed in stage channels.

            .. versionadded:: 1.7

        roles: List[:class:`Role`]
            The member's new list of roles. This *replaces* the roles.
        voice_channel: Optional[Union[:class:`VoiceChannel`, :class:`StageChannel`]]
            The voice channel to move the member to.
            Pass ``None`` to kick them from voice.
        reason: Optional[:class:`str`]
            The reason for editing this member. Shows up on the audit log.
        communication_disabled_until: Optional[:class:`datetime.datetime`]
            Temporarily puts the member in timeout until this time. If the value is ``None``, then the user is removed
            from timeout.

            .. versionadded:: 2.0
        bypass_verification: Optional[:class:`bool`]
            Indicates if the member should bypass the guild's verification requirements.

            .. versionadded:: 2.6
        banner: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the banner.
            Could be ``None`` to denote removal of the banner.

            This is only available when editing the bot's own member (i.e. :meth:`Guild.get_me`).

            .. versionadded:: 2.7
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the avatar.
            Could be ``None`` to denote removal of the avatar.

            This is only available when editing the bot's own member (i.e. :meth:`Guild.get_me`).

            .. versionadded:: 2.7
        bio: Optional[:class:`str`]
            The new bio for the member. Could be ``None`` to denote removal of the bio.

            This is only available when editing the bot's own member (i.e. :meth:`Guild.get_me`).

            .. versionadded:: 2.7

        Returns
        -------
        Optional[:class:`.Member`]
            The newly updated member, if applicable. This is only returned
            when certain fields are updated.

        Raises
        ------
        Forbidden
            You do not have the proper permissions to the action requested.
        HTTPException
            The operation failed.
        InvalidArgument
            You tried to edit the avatar, banner, or bio of a member that is not the bot.
        """
        http = self._state.http
        guild_id = self.guild_id
        me = self._state.self_id == self.id
        payload: dict[str, Any] = {}
        bot_payload: dict[str, Any] = {}

        if nick is not MISSING:
            nick = nick or ""
            if me:
                bot_payload["nick"] = nick
            else:
                payload["nick"] = nick

        if deafen is not MISSING:
            payload["deaf"] = deafen

        if mute is not MISSING:
            payload["mute"] = mute

        if suppress is not MISSING:
            voice_state_payload: dict[str, Any] = {
                "channel_id": await self._get_voice_channel_id(),
                "suppress": suppress,
            }

            if suppress or self.bot:
                voice_state_payload["request_to_speak_timestamp"] = None

            if me:
                await http.edit_my_voice_state(guild_id, voice_state_payload)
            else:
                if not suppress:
                    voice_state_payload["request_to_speak_timestamp"] = (
                        utcnow().isoformat()
                    )

                await http.edit_voice_state(guild_id, self.id, voice_state_payload)

        if voice_channel is not MISSING:
            payload["channel_id"] = voice_channel and voice_channel.id

        if roles is not MISSING:
            payload["roles"] = tuple(r.id for r in roles)

        if communication_disabled_until is not MISSING:
            if communication_disabled_until is not None:
                payload["communication_disabled_until"] = (
                    communication_disabled_until.isoformat()
                )
            else:
                payload["communication_disabled_until"] = communication_disabled_until

        if bypass_verification is not MISSING:
            flags = MemberFlags._from_value(self.flags.value)
            flags.bypasses_verification = bool(bypass_verification)
            payload["flags"] = flags.value

        if avatar is not MISSING:
            if avatar is None:
                bot_payload["avatar"] = None
            else:
                bot_payload["avatar"] = utils._bytes_to_base64_data(avatar)

        if banner is not MISSING:
            if banner is None:
                bot_payload["banner"] = None
            else:
                bot_payload["banner"] = utils._bytes_to_base64_data(banner)

        if bio is not MISSING:
            bot_payload["bio"] = bio or ""

        if bot_payload and not me:
            raise InvalidArgument(
                "Can only edit avatar, banner, or bio for the bot's member."
            )

        data = None

        if payload:
            data = await http.edit_member(guild_id, self.id, reason=reason, **payload)
        if bot_payload:
            data = await http.edit_member(guild_id, "@me", reason=reason, **bot_payload)

        if data is None:
            return None

        return Member(data=data, guild=self.guild, state=self._state)

    async def timeout(
        self, until: dt.datetime | None, *, reason: str | None = None
    ) -> None:
        """|coro|

        Applies a timeout to a member in the guild until a set datetime.

        You must have the :attr:`~Permissions.moderate_members` permission to timeout a member.

        Parameters
        ----------
        until: :class:`datetime.datetime`
            The date and time to timeout the member for. If this is ``None`` then the member is removed from timeout.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to timeout members.
        HTTPException
            An error occurred doing the request.
        """
        await self.edit(communication_disabled_until=until, reason=reason)

    async def timeout_for(
        self, duration: dt.timedelta, *, reason: str | None = None
    ) -> None:
        """|coro|

        Applies a timeout to a member in the guild for a set duration. A shortcut method for :meth:`~.timeout`, and
        equivalent to ``timeout(until=datetime.utcnow() + duration, reason=reason)``.

        You must have the :attr:`~Permissions.moderate_members` permission to
        timeout a member.

        Parameters
        ----------
        duration: :class:`datetime.timedelta`
            The duration to timeout the member for.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to timeout members.
        HTTPException
            An error occurred doing the request.
        """
        await self.timeout(utcnow() + duration, reason=reason)

    async def remove_timeout(self, *, reason: str | None = None) -> None:
        """|coro|

        Removes the timeout from a member.

        You must have the :attr:`~Permissions.moderate_members` permission to
        remove the timeout.

        This is equivalent to calling :meth:`~.timeout` and passing ``None`` to the ``until`` parameter.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have permissions to remove the timeout.
        HTTPException
            An error occurred doing the request.
        """
        await self.edit(communication_disabled_until=None, reason=reason)

    async def request_to_speak(self) -> None:
        """|coro|

        Request to speak in the connected channel.

        Only applies to stage channels.

        .. note::

            Requesting members that are not the client is equivalent
            to :attr:`.edit` providing ``suppress`` as ``False``.

        .. versionadded:: 1.7

        Raises
        ------
        Forbidden
            You do not have the proper permissions to the action requested.
        HTTPException
            The operation failed.
        """
        payload = {
            "channel_id": await self._get_voice_channel_id(),
            "request_to_speak_timestamp": utcnow().isoformat(),
        }

        if self._state.self_id != self.id:
            payload["suppress"] = False
            await self._state.http.edit_voice_state(self.guild_id, self.id, payload)
        else:
            await self._state.http.edit_my_voice_state(self.guild_id, payload)

    async def move_to(
        self, channel: VocalGuildChannel | None, *, reason: str | None = None
    ) -> None:
        """|coro|

        Moves a member to a new voice channel (they must be connected first).

        You must have the :attr:`~Permissions.move_members` permission to
        use this.

        This raises the same exceptions as :meth:`edit`.

        .. versionchanged:: 1.1
            Can now pass ``None`` to kick a member from voice.

        Parameters
        ----------
        channel: Optional[Union[:class:`VoiceChannel`, :class:`StageChannel`]]
            The new voice channel to move the member to.
            Pass ``None`` to kick them from voice.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.
        """
        await self.edit(voice_channel=channel, reason=reason)

    async def add_roles(
        self, *roles: Snowflake, reason: str | None = None, atomic: bool = True
    ) -> None:
        r"""|coro|

        Gives the member a number of :class:`Role`\s.

        You must have the :attr:`~Permissions.manage_roles` permission to
        use this, and the added :class:`Role`\s must appear lower in the list
        of roles than the highest role of the member.

        Parameters
        ----------
        \*roles: :class:`abc.Snowflake`
            An argument list of :class:`abc.Snowflake` representing a :class:`Role`
            to give to the member.
        reason: Optional[:class:`str`]
            The reason for adding these roles. Shows up on the audit log.
        atomic: :class:`bool`
            Whether to atomically add roles. This will ensure that multiple
            operations will always be applied regardless of the current
            state of the cache.

        Raises
        ------
        Forbidden
            You do not have permissions to add these roles.
        HTTPException
            Adding roles failed.
        """
        if not atomic:
            new_roles = utils._unique(
                Object(id=r.id)
                for s in ((await self.get_roles())[1:], roles)
                for r in s
            )
            await self.edit(roles=new_roles, reason=reason)
        else:
            req = self._state.http.add_role
            guild_id = self.guild_id
            user_id = self.id
            for role in roles:
                await req(guild_id, user_id, role.id, reason=reason)

    async def remove_roles(
        self, *roles: Snowflake, reason: str | None = None, atomic: bool = True
    ) -> None:
        r"""|coro|

        Removes :class:`Role`\s from this member.

        You must have the :attr:`~Permissions.manage_roles` permission to
        use this, and the removed :class:`Role`\s must appear lower in the list
        of roles than the highest role of the member.

        Parameters
        ----------
        \*roles: :class:`abc.Snowflake`
            An argument list of :class:`abc.Snowflake` representing a :class:`Role`
            to remove from the member.
        reason: Optional[:class:`str`]
            The reason for removing these roles. Shows up on the audit log.
        atomic: :class:`bool`
            Whether to atomically remove roles. This will ensure that multiple
            operations will always be applied regardless of the current
            state of the cache.

        Raises
        ------
        Forbidden
            You do not have permissions to remove these roles.
        HTTPException
            Removing the roles failed.
        """
        if not atomic:
            new_roles = [
                Object(id=r.id) for r in (await self.get_roles())[1:]
            ]  # remove @everyone
            for role in roles:
                with suppress(ValueError):
                    new_roles.remove(Object(id=role.id))

            await self.edit(roles=new_roles, reason=reason)
        else:
            req = self._state.http.remove_role
            guild_id = self.guild_id
            user_id = self.id
            for role in roles:
                await req(guild_id, user_id, role.id, reason=reason)

    def get_role(self, role_id: int, /) -> Role | None:
        """Returns a role with the given ID from roles which the member has.

        .. versionadded:: 2.0

        Parameters
        ----------
        role_id: :class:`int`
            The ID to search for.

        Returns
        -------
        Optional[:class:`Role`]
            The role or ``None`` if not found in the member's roles.
        """
        if not self._roles.has(role_id):
            return None
        return self._roles_bucket().get_nowait(role_id)

    def search_messages(self, **filters: Any) -> MessageSearchIterator:
        """Retrieves an :class:`.AsyncIterator` of the messages sent by this member.

        This is :meth:`Guild.search_messages` with ``authors`` set to this member.

        .. versionadded:: 3.0
        """
        return self.guild.search_messages(authors=[self], **filters)

    def search_replies(self, **filters: Any) -> MessageSearchIterator:
        """Retrieves an :class:`.AsyncIterator` of the messages replying to this member.

        This is :meth:`Guild.search_messages` with ``replied_to_users`` set to this member.

        .. versionadded:: 3.0
        """
        return self.guild.search_messages(replied_to_users=[self], **filters)

    def search_mentions(self, **filters: Any) -> MessageSearchIterator:
        """Retrieves an :class:`.AsyncIterator` of the messages mentioning this member.

        This is :meth:`Guild.search_messages` with ``mentions`` set to this member.

        .. versionadded:: 3.0
        """
        return self.guild.search_messages(mentions=[self], **filters)

    if TYPE_CHECKING:
        color = colour
        colors = colours
        get_color = get_colour
        get_colors = get_colours
