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
from collections.abc import Callable, Generator
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

from . import enums, utils
from ._internal.aliases import AliasMixin, alias_of, canonical_of
from ._internal.cache_peek import cached_guild
from .asset import Asset
from .automod import AutoModAction, AutoModTriggerMetadata
from .colour import Colour
from .invite import Invite
from .mixins import Hashable
from .object import Object
from .permissions import PermissionOverwrite, Permissions

__all__ = (
    "AuditLogChanges",
    "AuditLogDiff",
    "AuditLogEntry",
)


if TYPE_CHECKING:
    import datetime as dt

    from . import abc
    from .emoji import GuildEmoji
    from .guild import Guild, PartialGuild
    from .member import Member
    from .role import Role
    from .scheduled_events import ScheduledEvent
    from .stage_instance import StageInstance
    from .state import ConnectionState
    from .sticker import GuildSticker
    from .threads import Thread
    from .types.audit_log import (
        AuditLogChange as AuditLogChangePayload,
        AuditLogEntry as AuditLogEntryPayload,
    )
    from .types.automod import (
        AutoModAction as AutoModActionPayload,
        AutoModTriggerMetadata as AutoModTriggerMetadataPayload,
    )
    from .types.channel import PermissionOverwrite as PermissionOverwritePayload
    from .types.invite import Invite as InvitePayload
    from .types.role import Role as RolePayload
    from .types.snowflake import Snowflake
    from .user import User


class _NamedObject(Object):
    name: str | None


def _transform_permissions(_entry: AuditLogEntry, data: str) -> Permissions:
    return Permissions(int(data))


def _transform_color(_entry: AuditLogEntry, data: int) -> Colour:
    return Colour(data)


def _transform_snowflake(_entry: AuditLogEntry, data: Snowflake) -> int:
    return int(data)


def _transform_channel(_entry: AuditLogEntry, data: Snowflake | None) -> Object | None:
    if data is None:
        return None
    return Object(id=int(data))


def _transform_channels(
    _entry: AuditLogEntry, data: list[Snowflake] | None
) -> list[Object] | None:
    if data is None:
        return None
    return [Object(id=int(channel)) for channel in data]


def _transform_roles(
    _entry: AuditLogEntry, data: list[Snowflake] | None
) -> list[Object] | None:
    if data is None:
        return None
    return [Object(id=int(r)) for r in data]


def _transform_member_id(
    entry: AuditLogEntry, data: Snowflake | None
) -> User | Object | None:
    if data is None:
        return None
    user_id = int(data)
    return entry._users.get(user_id) or Object(id=user_id)


def _transform_guild_id(
    entry: AuditLogEntry, data: Snowflake | None
) -> PartialGuild | None:
    if data is None:
        return None
    from .guild import PartialGuild

    return PartialGuild(state=entry._state, id=int(data))


def _transform_overwrites(
    _entry: AuditLogEntry, data: list[PermissionOverwritePayload]
) -> list[tuple[Object, PermissionOverwrite]]:
    from .member import Member
    from .role import Role

    overwrites: list[tuple[Object, PermissionOverwrite]] = []
    for elem in data:
        allow = Permissions(int(elem["allow"]))
        deny = Permissions(int(elem["deny"]))
        ow = PermissionOverwrite.from_pair(allow, deny)

        ow_type = elem["type"]
        ow_id = int(elem["id"])
        target = Object(
            id=ow_id,
            type=Role if ow_type == 0 else Member if ow_type == 1 else utils.MISSING,
        )

        overwrites.append((target, ow))

    return overwrites


def _transform_icon(entry: AuditLogEntry, data: str | None) -> Asset | None:
    if data is None:
        return None
    return Asset._from_guild_icon(entry._state, entry.guild.id, data)


def _transform_avatar(entry: AuditLogEntry, data: str | None) -> Asset | None:
    if data is None:
        return None
    return Asset._from_avatar(entry._state, cast("int", entry.target_id), data)


def _transform_scheduled_event_image(
    entry: AuditLogEntry, data: str | None
) -> Asset | None:
    if data is None:
        return None
    return Asset._from_scheduled_event_image(
        entry._state, cast("int", entry.target_id), data
    )


def _guild_hash_transformer(
    path: str,
) -> Callable[[AuditLogEntry, str | None], Asset | None]:
    def _transform(entry: AuditLogEntry, data: str | None) -> Asset | None:
        if data is None:
            return None
        return Asset._from_guild_image(entry._state, entry.guild.id, data, path=path)

    return _transform


T = TypeVar("T", bound=enums.Enum)


def _enum_transformer(enum: type[T]) -> Callable[[AuditLogEntry, int], T]:
    def _transform(_entry: AuditLogEntry, data: int) -> T:
        return enums.try_enum(enum, data)

    return _transform


def _transform_type(
    entry: AuditLogEntry, data: int
) -> enums.ChannelType | enums.StickerType:
    if entry.action.name.startswith("sticker_"):
        return enums.try_enum(enums.StickerType, data)
    return enums.try_enum(enums.ChannelType, data)


def _transform_actions(
    _entry: AuditLogEntry, data: list[AutoModActionPayload] | None
) -> list[AutoModAction] | None:
    if data is None:
        return None
    return [AutoModAction.from_dict(d) for d in data]


def _transform_trigger_metadata(
    _entry: AuditLogEntry, data: AutoModTriggerMetadataPayload | None
) -> AutoModTriggerMetadata | None:
    if data is None:
        return None
    return AutoModTriggerMetadata.from_dict(data)


def _transform_communication_disabled_until(
    _entry: AuditLogEntry, data: str
) -> dt.datetime | None:
    if data:
        return utils.parse_time(data)
    return None


_RESOLVER_KINDS: dict[Callable[..., Any], str] = {
    _transform_channel: "channels",
    _transform_channels: "channels",
    _transform_roles: "roles",
    _transform_member_id: "members",
}


def _overwrite_kind(target: Object) -> str:
    from .member import Member
    from .role import Role

    if target.type is Role:
        return "roles"
    if target.type is Member:
        return "members"
    return ""


def _collect(transformer: Transformer, value: Any) -> list[tuple[str, Object]]:
    if transformer is _transform_overwrites:
        return [(_overwrite_kind(target), target) for target, _ in value]
    kind = _RESOLVER_KINDS[transformer]
    objects: list[Object] = (
        cast("list[Object]", value) if isinstance(value, list) else [value]
    )
    return [(kind, obj) for obj in objects]


def _rebuild(
    transformer: Transformer, value: Any, found: dict[tuple[str, int], Any]
) -> Any:
    def pick(kind: str, obj: Object) -> Any:
        return found.get((kind, obj.id)) or obj

    if transformer is _transform_overwrites:
        return [(pick(_overwrite_kind(target), target), ow) for target, ow in value]
    kind = _RESOLVER_KINDS[transformer]
    if isinstance(value, list):
        return [pick(kind, obj) for obj in cast("list[Object]", value)]
    return pick(kind, value)


class AuditLogDiff(AliasMixin):
    """Represents the attributes of an audit log entry target before or after a change.

    The attributes are the names of the changed keys, see :class:`AuditLogChanges`.

    .. container:: operations

        .. describe:: iter(diff)

            Returns an iterator over ``(attribute, value)`` pairs.

        .. describe:: len(diff)

            Returns the number of changed attributes.
    """

    def __len__(self) -> int:
        return len(self.__dict__)

    def __iter__(self) -> Generator[tuple[str, Any]]:
        yield from self.__dict__.items()

    def __repr__(self) -> str:
        values = " ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"<AuditLogDiff {values}>"

    def __getattr__(self, item: str) -> Any:
        if not item.startswith("_"):
            for candidate in (alias_of(item), canonical_of(item)):
                if candidate is not None and candidate in self.__dict__:
                    return self.__dict__[candidate]
        raise AttributeError(item)

    if TYPE_CHECKING:

        def __setattr__(self, key: str, value: Any) -> Any: ...


Transformer = Callable[["AuditLogEntry", Any], Any]

_RESOLVABLE = {*_RESOLVER_KINDS, _transform_overwrites}


class AuditLogChanges:
    """Represents the changes of an audit log entry.

    Attributes
    ----------
    before: :class:`AuditLogDiff`
        The target's attributes before the changes.
    after: :class:`AuditLogDiff`
        The target's attributes after the changes.
    """

    TRANSFORMERS: ClassVar[dict[str, tuple[str | None, Transformer | None]]] = {
        "verification_level": (None, _enum_transformer(enums.VerificationLevel)),
        "explicit_content_filter": (None, _enum_transformer(enums.ContentFilter)),
        "allow": (None, _transform_permissions),
        "deny": (None, _transform_permissions),
        "permissions": (None, _transform_permissions),
        "id": (None, _transform_snowflake),
        "color": ("colour", _transform_color),
        "owner_id": ("owner", _transform_member_id),
        "inviter_id": ("inviter", _transform_member_id),
        "channel_id": ("channel", _transform_channel),
        "afk_channel_id": ("afk_channel", _transform_channel),
        "system_channel_id": ("system_channel", _transform_channel),
        "widget_channel_id": ("widget_channel", _transform_channel),
        "rules_channel_id": ("rules_channel", _transform_channel),
        "public_updates_channel_id": ("public_updates_channel", _transform_channel),
        "permission_overwrites": ("overwrites", _transform_overwrites),
        "splash_hash": ("splash", _guild_hash_transformer("splashes")),
        "banner_hash": ("banner", _guild_hash_transformer("banners")),
        "discovery_splash_hash": (
            "discovery_splash",
            _guild_hash_transformer("discovery-splashes"),
        ),
        "icon_hash": ("icon", _transform_icon),
        "avatar_hash": ("avatar", _transform_avatar),
        "rate_limit_per_user": ("slowmode_delay", None),
        "guild_id": ("guild", _transform_guild_id),
        "tags": ("emoji", None),
        "default_message_notifications": (
            "default_notifications",
            _enum_transformer(enums.NotificationLevel),
        ),
        "rtc_region": (None, _enum_transformer(enums.VoiceRegion)),
        "video_quality_mode": (None, _enum_transformer(enums.VideoQualityMode)),
        "privacy_level": (None, _enum_transformer(enums.StagePrivacyLevel)),
        "format_type": (None, _enum_transformer(enums.StickerFormatType)),
        "type": (None, _transform_type),
        "status": (None, _enum_transformer(enums.ScheduledEventStatus)),
        "entity_type": (
            "location_type",
            _enum_transformer(enums.ScheduledEventLocationType),
        ),
        "command_id": ("command_id", _transform_snowflake),
        "image_hash": ("image", _transform_scheduled_event_image),
        "trigger_type": (None, _enum_transformer(enums.AutoModTriggerType)),
        "event_type": (None, _enum_transformer(enums.AutoModEventType)),
        "actions": (None, _transform_actions),
        "trigger_metadata": (None, _transform_trigger_metadata),
        "exempt_roles": (None, _transform_roles),
        "exempt_channels": (None, _transform_channels),
        "communication_disabled_until": (None, _transform_communication_disabled_until),
    }

    def __init__(
        self,
        entry: AuditLogEntry,
        data: list[AuditLogChangePayload],
        *,
        state: ConnectionState,
    ) -> None:
        self.before = AuditLogDiff()
        self.after = AuditLogDiff()
        self._entry = entry
        self._resolved = False
        self._pending: list[tuple[AuditLogDiff, str, Transformer]] = []

        for elem in sorted(data, key=lambda i: i["key"]):
            attr = elem["key"]

            # special cases for role/trigger_metadata add/remove
            if attr == "$add":
                self._handle_role(
                    self.before,
                    self.after,
                    entry,
                    cast("list[RolePayload]", elem["new_value"]),
                )
                continue
            if attr == "$remove":
                self._handle_role(
                    self.after,
                    self.before,
                    entry,
                    cast("list[RolePayload]", elem["new_value"]),
                )
                continue
            if attr in [
                "$add_keyword_filter",
                "$add_regex_patterns",
                "$add_allow_list",
            ]:
                self._handle_trigger_metadata(
                    self.before,
                    self.after,
                    entry,
                    cast("list[AutoModTriggerMetadataPayload]", elem["new_value"]),
                    attr,
                )
                continue
            if attr in [
                "$remove_keyword_filter",
                "$remove_regex_patterns",
                "$remove_allow_list",
            ]:
                self._handle_trigger_metadata(
                    self.after,
                    self.before,
                    entry,
                    cast("list[AutoModTriggerMetadataPayload]", elem["new_value"]),
                    attr,
                )
                continue

            try:
                key, transformer = self.TRANSFORMERS[attr]
            except (ValueError, KeyError):
                transformer = None
            else:
                if key:
                    attr = key

            transformer: Transformer | None

            before: Any
            try:
                before = elem["old_value"]
            except KeyError:
                before = None
            else:
                if transformer:
                    before = transformer(entry, before)

            if attr == "location" and hasattr(self.before, "location_type"):
                from .scheduled_events import ScheduledEventLocation

                if (
                    self.before.location_type
                    is enums.ScheduledEventLocationType.external
                ):
                    before = ScheduledEventLocation(state=state, value=before)
                elif hasattr(self.before, "channel"):
                    before = ScheduledEventLocation(
                        state=state, value=self.before.channel
                    )

            setattr(self.before, attr, before)
            if transformer is not None and transformer in _RESOLVABLE:
                self._pending.append((self.before, attr, transformer))

            after: Any
            try:
                after = elem["new_value"]
            except KeyError:
                after = None
            else:
                if transformer:
                    after = transformer(entry, after)

            if attr == "location" and hasattr(self.after, "location_type"):
                from .scheduled_events import ScheduledEventLocation

                if (
                    self.after.location_type
                    is enums.ScheduledEventLocationType.external
                ):
                    after = ScheduledEventLocation(state=state, value=after)
                elif hasattr(self.after, "channel"):
                    after = ScheduledEventLocation(
                        state=state, value=self.after.channel
                    )

            setattr(self.after, attr, after)
            if transformer is not None and transformer in _RESOLVABLE:
                self._pending.append((self.after, attr, transformer))

    def __repr__(self) -> str:
        return f"<AuditLogChanges before={self.before!r} after={self.after!r}>"

    def _apply(self, found: dict[tuple[str, int], Any]) -> AuditLogChanges:
        for diff, attr, transformer in self._pending:
            value = diff.__dict__.get(attr)
            if value is not None:
                setattr(diff, attr, _rebuild(transformer, value, found))
        self._resolved = True
        return self

    def _lookups(self) -> list[tuple[str, int]]:
        lookups: list[tuple[str, int]] = []
        for diff, attr, transformer in self._pending:
            value = diff.__dict__.get(attr)
            if value is not None:
                lookups.extend(
                    (kind, obj.id) for kind, obj in _collect(transformer, value)
                )
        return lookups

    def _resolve_sync(self) -> AuditLogChanges:
        if self._resolved:
            return self
        entry = self._entry
        return self._apply({(k, i): entry._peek(k, i) for k, i in self._lookups()})

    async def resolve(self) -> AuditLogChanges:
        """|coro|

        Replaces the :class:`Object` placeholders held by :attr:`before` and
        :attr:`after` (channels, roles, members and overwrite targets) with the
        cached entities, when they are cached. Unlike reading
        :attr:`AuditLogEntry.changes`, this works with any cache backend.

        Returns
        -------
        :class:`AuditLogChanges`
            These changes.
        """
        if self._resolved:
            return self
        entry = self._entry
        return self._apply({(k, i): await entry._get(k, i) for k, i in self._lookups()})

    def _handle_role(
        self,
        first: AuditLogDiff,
        second: AuditLogDiff,
        entry: AuditLogEntry,
        elem: list[RolePayload],
    ) -> None:
        if not hasattr(first, "roles"):
            first.roles = []

        data: list[Object] = []

        for e in elem:
            role = _NamedObject(id=int(e["id"]))
            role.name = e["name"]
            data.append(role)

        second.roles = data
        self._pending.append((second, "roles", _transform_roles))

    def _handle_trigger_metadata(
        self,
        first: AuditLogDiff,
        second: AuditLogDiff,
        entry: AuditLogEntry,
        elem: list[AutoModTriggerMetadataPayload],
        attr: str,
    ) -> None:
        if not hasattr(first, "trigger_metadata"):
            first.trigger_metadata = None

        key = attr.split("_", 1)[-1]
        data = cast("AutoModTriggerMetadataPayload", {key: elem})
        tm = AutoModTriggerMetadata.from_dict(data)

        second.trigger_metadata = tm


_TARGET_KINDS: dict[str, str] = {
    "guild": "guilds",
    "channel": "channels",
    "user": "members",
    "message": "members",
    "role": "roles",
    "emoji": "emojis",
    "stage_instance": "stage_instances",
    "sticker": "stickers",
    "thread": "threads",
    "scheduled_event": "scheduled_events",
}


class _AuditLogProxyMemberPrune:
    delete_member_days: int
    members_removed: int


class _AuditLogProxyMemberMoveOrMessageDelete:
    channel: abc.GuildChannel | Object
    count: int


class _AuditLogProxyMemberDisconnect:
    count: int


class _AuditLogProxyPinAction:
    channel: abc.GuildChannel | Object
    message_id: int


class _AuditLogProxyStageInstanceAction:
    channel: abc.GuildChannel | Object


class AuditLogEntry(Hashable):
    r"""Represents an Audit Log entry.

    You retrieve these via :meth:`Guild.audit_logs`.

    .. container:: operations

        .. describe:: x == y

            Checks if two entries are equal.

        .. describe:: x != y

            Checks if two entries are not equal.

        .. describe:: hash(x)

            Returns the entry's hash.

    .. versionchanged:: 1.7
        Audit log entries are now comparable and hashable.

    Attributes
    ----------
    action: :class:`AuditLogAction`
        The action that was done.
    user_id: Optional[:class:`int`]
        The ID of the user who initiated this action.
    id: :class:`int`
        The entry ID.
    target_id: Optional[:class:`int`]
        The ID of the target that got changed.
    reason: Optional[:class:`str`]
        The reason this action was done.
    """

    def __init__(
        self,
        *,
        users: dict[int, User],
        data: AuditLogEntryPayload,
        guild: Guild | PartialGuild,
    ) -> None:
        self._state = guild._state
        self.guild_id: int = guild.id
        self._users = users
        self._from_data(data)

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild this entry belongs to.

        This is a :class:`PartialGuild` when the guild is not cached or when the
        cache is not held in-process.
        """
        from .guild import PartialGuild

        guild = cached_guild(self._state, self.guild_id)
        if guild is not None:
            return guild
        return PartialGuild(state=self._state, id=self.guild_id)

    def _from_data(self, data: AuditLogEntryPayload) -> None:
        self.action = enums.try_enum(enums.AuditLogAction, data["action_type"])
        self.id = int(data["id"])

        # this key is technically not usually present
        self.reason = data.get("reason")
        options = data.get("options")
        extra: Any = options

        if options:
            if self.action is enums.AuditLogAction.member_prune:
                # member prune has two keys with useful information
                extra = type(
                    "_AuditLogProxy",
                    (),
                    {k: int(v) for k, v in cast("dict[str, Any]", options).items()},
                )()
            elif (
                self.action is enums.AuditLogAction.member_move
                or self.action is enums.AuditLogAction.message_delete
            ):
                elems = {
                    "count": int(options["count"]),
                    "channel": Object(id=int(options["channel_id"])),
                }
                extra = type("_AuditLogProxy", (), elems)()
            elif self.action is enums.AuditLogAction.member_disconnect:
                # The member disconnect action has a dict with some information
                extra = type("_AuditLogProxy", (), {"count": int(options["count"])})()
            elif self.action.name.endswith("pin"):
                # the pin actions have a dict with some information
                elems = {
                    "channel": Object(id=int(options["channel_id"])),
                    "message_id": int(options["message_id"]),
                }
                extra = type("_AuditLogProxy", (), elems)()
            elif self.action.name.startswith("overwrite_"):
                # the overwrite_ actions have a dict with some information
                from .member import Member
                from .role import Role

                instance_id = int(options["id"])
                the_type = options.get("type")
                if the_type == "1":
                    extra = self._users.get(instance_id) or Object(
                        id=instance_id, type=Member
                    )
                elif the_type == "0":
                    role = _NamedObject(id=instance_id, type=Role)
                    role.name = options.get("role_name")
                    extra = role
            elif self.action.name.startswith("stage_instance"):
                elems = {"channel": Object(id=int(options["channel_id"]))}
                extra = type("_AuditLogProxy", (), elems)()

        self._extra: Any = extra
        self._extra_resolved = False

        # this key is not present when the above is present, typically.
        # It's a list of { new_value: a, old_value: b, key: c }
        # where new_value and old_value are not guaranteed to be there depending
        # on the action type, so let's just fetch it for now and only turn it
        # into meaningful data when requested
        self._changes = data.get("changes", [])

        self.user_id: int | None = utils._get_as_snowflake(data, "user_id")
        self.target_id: int | None = utils._get_as_snowflake(data, "target_id")

    def _peek(self, kind: str, id: int) -> Any:
        state = self._state
        if kind == "members":
            return state._guild_bucket(kind, self.guild_id).get_nowait(
                id
            ) or self._users.get(id)
        if not kind:
            return None
        if kind == "guilds":
            return state._guilds.get_nowait(id)
        if kind == "stickers":
            return state._stickers.get_nowait(id)
        if kind == "emojis":
            return state._emojis.get_nowait(id) or state._app_emojis.get_nowait(id)
        return state._guild_bucket(kind, self.guild_id).get_nowait(id)

    async def _get(self, kind: str, id: int) -> Any:
        state = self._state
        if kind == "members":
            return await state._guild_bucket(kind, self.guild_id).get(
                id
            ) or self._users.get(id)
        if not kind:
            return None
        if kind == "guilds":
            return await state._guilds.get(id)
        if kind == "stickers":
            return await state._stickers.get(id)
        if kind == "emojis":
            return await state.get_emoji(id)
        return await state._guild_bucket(kind, self.guild_id).get(id)

    def _extra_lookup(self) -> tuple[str, int] | None:
        extra = self._extra
        if isinstance(extra, Object):
            return _overwrite_kind(extra), extra.id
        channel = getattr(extra, "channel", None)
        if isinstance(channel, Object):
            return "channels", channel.id
        return None

    def _apply_extra(self, found: Any) -> Any:
        lookup = self._extra_lookup()
        if lookup is not None and found is not None:
            if isinstance(self._extra, Object):
                self._extra = found
            else:
                self._extra.channel = found
        self._extra_resolved = True
        return self._extra

    @property
    def extra(
        self,
    ) -> (
        _AuditLogProxyMemberPrune
        | _AuditLogProxyMemberMoveOrMessageDelete
        | _AuditLogProxyMemberDisconnect
        | _AuditLogProxyPinAction
        | _AuditLogProxyStageInstanceAction
        | Member
        | User
        | Role
        | Object
        | None
    ):
        """Extra information that this entry has that might be useful.

        For most actions, this is ``None``. However, in some cases it
        contains extra information. See :class:`AuditLogAction` for
        which actions have this field filled out. Channels, roles and members
        it references are read from the in-memory cache and are :class:`Object`
        placeholders when not found. Use :meth:`get_extra` with any cache backend.
        """
        if not self._extra_resolved:
            lookup = self._extra_lookup()
            self._apply_extra(None if lookup is None else self._peek(*lookup))
        return self._extra

    async def get_extra(self) -> Any:
        """|coro|

        Returns :attr:`extra` with the channel, role or member it references
        resolved from the cache, instead of an :class:`Object` placeholder.

        .. versionadded:: 3.0

        Returns
        -------
        Any
            The extra information of this entry.
        """
        if not self._extra_resolved:
            lookup = self._extra_lookup()
            self._apply_extra(None if lookup is None else await self._get(*lookup))
        return self._extra

    @property
    def user(self) -> Member | User | None:
        """The user who initiated this action. Usually a :class:`Member`, unless gone then it's a :class:`User`.

        This reads the in-memory cache, use :meth:`get_user` with any cache backend.
        """
        if self.user_id is None:
            return None
        return self._peek("members", self.user_id)

    async def get_user(self) -> Member | User | None:
        """|coro|

        Returns the user who initiated this action.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`Member`, :class:`User`]]
            The cached :class:`Member`, or the :class:`User` sent with the entry
            when the member is not cached.
        """
        if self.user_id is None:
            return None
        return await self._get("members", self.user_id)

    def __repr__(self) -> str:
        return f"<AuditLogEntry id={self.id} action={self.action} user_id={self.user_id!r}>"

    @property
    def created_at(self) -> dt.datetime:
        """Returns the entry's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def _target_kind(self) -> str | None:
        target_type = self.action.target_type
        return None if target_type is None else _TARGET_KINDS.get(target_type)

    @property
    def target(
        self,
    ) -> (
        Guild
        | abc.GuildChannel
        | Member
        | User
        | Role
        | Invite
        | GuildEmoji
        | StageInstance
        | GuildSticker
        | Thread
        | ScheduledEvent
        | Object
        | None
    ):
        """The target that got changed. The exact type of this depends on the action being done.

        This reads the in-memory cache, use :meth:`get_target` with any cache backend.
        """
        if self.target_id is None:
            return None
        target_type = self.action.target_type
        if target_type == "invite":
            return self._invite_from(self.changes)
        kind = self._target_kind()
        if kind is None:
            return Object(id=self.target_id)
        return self._peek(kind, self.target_id) or self._target_default(kind)

    async def get_target(
        self,
    ) -> (
        Guild
        | abc.GuildChannel
        | Member
        | User
        | Role
        | Invite
        | GuildEmoji
        | StageInstance
        | GuildSticker
        | Thread
        | ScheduledEvent
        | Object
        | None
    ):
        """|coro|

        Returns the target that got changed. The exact type of this depends on
        the action being done, and is an :class:`Object` when the target is not
        cached.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Any]
            The target, or ``None`` if the entry has no target.
        """
        if self.target_id is None:
            return None
        target_type = self.action.target_type
        if target_type == "invite":
            return self._invite_from(await self.get_changes())
        kind = self._target_kind()
        if kind is None:
            return Object(id=self.target_id)
        return await self._get(kind, self.target_id) or self._target_default(kind)

    def _target_default(self, kind: str) -> Object | None:
        if kind == "members":
            return None
        return Object(id=cast("int", self.target_id))

    @property
    def category(self) -> enums.AuditLogActionCategory | None:
        """The category of the action, if applicable."""
        return self.action.category

    @cached_property
    def changes(self) -> AuditLogChanges:
        """The list of changes this entry has.

        The channels, roles and members it references are read from the in-memory
        cache, use :meth:`get_changes` with any cache backend.
        """
        return AuditLogChanges(self, self._changes, state=self._state)._resolve_sync()

    async def get_changes(self) -> AuditLogChanges:
        """|coro|

        Returns :attr:`changes` with the channels, roles and members it references
        resolved from the cache, instead of :class:`Object` placeholders.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`AuditLogChanges`
            The list of changes this entry has.
        """
        changes = self.__dict__.get("changes")
        if changes is None:
            changes = AuditLogChanges(self, self._changes, state=self._state)
            await changes.resolve()
            self.__dict__["changes"] = changes
        return changes

    @property
    def before(self) -> AuditLogDiff:
        """The target's prior state."""
        return self.changes.before

    @property
    def after(self) -> AuditLogDiff:
        """The target's subsequent state."""
        return self.changes.after

    def _invite_from(self, changes: AuditLogChanges) -> Invite:
        # invites have target_id set to null
        # so figure out which change has the full invite data
        changeset = (
            changes.before
            if self.action is enums.AuditLogAction.invite_delete
            else changes.after
        )

        fake_payload = {
            "max_age": changeset.max_age,
            "max_uses": changeset.max_uses,
            "code": changeset.code,
            "temporary": changeset.temporary,
            "uses": changeset.uses,
        }

        obj = Invite(
            state=self._state,
            data=cast("InvitePayload", fake_payload),
            guild=self.guild,
            channel=changeset.channel,
        )
        with contextlib.suppress(AttributeError):
            obj.inviter = changeset.inviter
        return obj
