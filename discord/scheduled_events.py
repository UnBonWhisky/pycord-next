"""
The MIT License (MIT)

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
import datetime as dt
from typing import TYPE_CHECKING, Any, cast

from . import utils
from ._internal.cache_peek import cached_channel
from .asset import Asset
from .enums import (
    ChannelType,
    ScheduledEventEntityType,
    ScheduledEventLocationType,
    ScheduledEventPrivacyLevel,
    ScheduledEventRecurrenceFrequency,
    ScheduledEventStatus,
    ScheduledEventWeekday,
    try_enum,
)
from .errors import InvalidArgument, ValidationError
from .iterators import ScheduledEventSubscribersIterator
from .mixins import Hashable
from .object import Object
from .utils import warn_deprecated

__all__ = (
    "ScheduledEvent",
    "ScheduledEventEntityMetadata",
    "ScheduledEventLocation",
    "ScheduledEventNWeekday",
    "ScheduledEventRecurrenceRule",
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from typing_extensions import Self

    from .abc import GuildChannel, Snowflake
    from .channel import PartialGuildChannel, StageChannel, VoiceChannel
    from .guild import Guild, PartialGuild
    from .member import Member
    from .state import ConnectionState
    from .threads import Thread
    from .types.scheduled_events import (
        ScheduledEvent as ScheduledEventPayload,
        ScheduledEventEntityMetadata as ScheduledEventEntityMetadataPayload,
        ScheduledEventRecurrenceRule as ScheduledEventRecurrenceRulePayload,
    )
    from .user import User

MISSING = utils.MISSING


class ScheduledEventLocation:
    """Represents a scheduled event's location.

    Setting the ``value`` to its corresponding type will set the location type automatically:

    +------------------------+---------------------------------------------------+
    |     Type of Input      |                   Location Type                   |
    +========================+===================================================+
    | :class:`StageChannel`  | :attr:`ScheduledEventLocationType.stage_instance` |
    | :class:`VoiceChannel`  | :attr:`ScheduledEventLocationType.voice`          |
    | :class:`str`           | :attr:`ScheduledEventLocationType.external`       |
    +------------------------+---------------------------------------------------+

    .. versionadded:: 2.0

    Attributes
    ----------
    value: Union[:class:`str`, :class:`StageChannel`, :class:`VoiceChannel`, :class:`Object`]
        The actual location of the scheduled event.
    type: :class:`ScheduledEventLocationType`
        The type of location.
    """

    __slots__ = (
        "_state",
        "_type",
        "_value",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        value: str | int | StageChannel | VoiceChannel,
        type: ScheduledEventLocationType | None = None,
    ) -> None:
        self._state = state
        self._type: ScheduledEventLocationType | None = type
        self._value: str | StageChannel | VoiceChannel | Object
        if isinstance(value, int):
            self._value = Object(id=int(value))
        else:
            self._value = value

    @property
    def value(self) -> str | StageChannel | VoiceChannel | Object:
        """The actual location of the scheduled event.

        A channel location is the cached channel when it is in the in-process
        cache, otherwise an :class:`Object` carrying its ID.
        """
        value = self._value
        if isinstance(value, Object):
            return (
                cast(
                    "StageChannel | VoiceChannel | None",
                    cached_channel(self._state, value.id),
                )
                or value
            )
        return value

    @value.setter
    def value(self, value: str | StageChannel | VoiceChannel | Object) -> None:
        self._value = value

    def __repr__(self) -> str:
        return f"<ScheduledEventLocation value={self.value!r} type={self.type}>"

    def __str__(self) -> str:
        return str(self.value)

    @property
    def type(self) -> ScheduledEventLocationType | None:
        """The type of the location, inferred from the value when it was not given."""
        if self._type is not None:
            return self._type
        if isinstance(self.value, str):
            return ScheduledEventLocationType.external
        if self.value.__class__.__name__ == "StageChannel":
            return ScheduledEventLocationType.stage_instance
        if self.value.__class__.__name__ == "VoiceChannel":
            return ScheduledEventLocationType.voice
        return None


class ScheduledEventEntityMetadata:
    """Represents the additional metadata of a scheduled event.

    Discord requires a ``location`` for events with the
    :attr:`ScheduledEventEntityType.external` entity type and silently discards
    the metadata of every other event.

    .. versionadded:: 3.0

    Attributes
    ----------
    location: Optional[:class:`str`]
        The location of the event (1-100 characters).
    """

    __slots__ = ("location",)

    def __init__(self, location: str | None = None) -> None:
        self.location: str | None = location

    @classmethod
    def _from_data(cls, data: ScheduledEventEntityMetadataPayload) -> Self:
        return cls(location=data.get("location"))

    def _to_dict(self) -> ScheduledEventEntityMetadataPayload:
        payload: ScheduledEventEntityMetadataPayload = {}
        if self.location is not None:
            payload["location"] = self.location
        return payload

    def __repr__(self) -> str:
        return f"<ScheduledEventEntityMetadata location={self.location!r}>"

    def __str__(self) -> str:
        return self.location or ""

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ScheduledEventEntityMetadata)
            and self.location == other.location
        )

    def __hash__(self) -> int:
        return hash(self.location)


class ScheduledEventNWeekday:
    """A specific day within a specific week of a month.

    This is used by :class:`ScheduledEventRecurrenceRule`.
    A plain ``(n, day)`` tuple is accepted wherever this is expected, and this
    can be unpacked like one.

    .. versionadded:: 3.0

    Attributes
    ----------
    n: :class:`int`
        The week of the month to recur on, from 1 to 5.
    day: :class:`ScheduledEventWeekday`
        The day within that week to recur on.
    """

    __slots__ = ("day", "n")

    def __init__(self, n: int, day: int | ScheduledEventWeekday) -> None:
        self.n: int = n
        self.day: ScheduledEventWeekday = _to_weekday(day)

    def __iter__(self) -> Iterator[Any]:
        yield self.n
        yield self.day

    def __repr__(self) -> str:
        return f"<ScheduledEventNWeekday n={self.n} day={self.day}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ScheduledEventNWeekday)
            and self.n == other.n
            and self.day == other.day
        )

    def __hash__(self) -> int:
        return hash((self.n, self.day.value))


def _to_weekday(value: int | ScheduledEventWeekday) -> ScheduledEventWeekday:
    if isinstance(value, ScheduledEventWeekday):
        return value
    return try_enum(ScheduledEventWeekday, int(value))


class ScheduledEventRecurrenceRule:
    """Represents how often a :class:`ScheduledEvent` recurs.

    Discord's recurrence rule is a subset of the behaviours defined in the
    iCalendar RFC. Discord documents these current limitations:

    - ``count``, ``end`` and ``by_year_day`` cannot be set by an application.
    - ``weekdays``, ``n_weekdays`` and ``month_days`` are mutually exclusive.
    - ``weekdays`` is only valid for :attr:`~ScheduledEventRecurrenceFrequency.daily`
      and :attr:`~ScheduledEventRecurrenceFrequency.weekly` events. A daily event
      needs one of these sets: Monday-Friday, Tuesday-Saturday, Sunday-Thursday,
      Friday and Saturday, Saturday and Sunday, or Sunday and Monday. A weekly event
      can only have one weekday.
    - ``n_weekdays`` is only valid for :attr:`~ScheduledEventRecurrenceFrequency.monthly`
      events and can only have one item.
    - ``month_days`` is only valid for :attr:`~ScheduledEventRecurrenceFrequency.yearly`
      events and must have exactly one item.
    - ``interval`` can only be something other than ``1`` for
      :attr:`~ScheduledEventRecurrenceFrequency.weekly` events, where ``2`` means
      "every other week".

    .. versionadded:: 3.0

    Parameters
    ----------
    start_date: :class:`datetime.datetime`
        The starting time of the recurrence interval.
    frequency: :class:`ScheduledEventRecurrenceFrequency`
        How often the event occurs.
    interval: :class:`int`
        The spacing between the events, defined by ``frequency``.
    weekdays: List[Union[:class:`ScheduledEventWeekday`, :class:`int`]]
        The days within a week the event recurs on, from 0 (Monday) to 6 (Sunday).
    n_weekdays: List[Union[:class:`ScheduledEventNWeekday`, Tuple[:class:`int`, :class:`int`]]]
        The specific days within a specific week (1 to 5) of a month the event recurs on.
    month_days: List[:class:`datetime.date`]
        The specific month and day the event recurs on. The year is ignored.

    Attributes
    ----------
    start_date: :class:`datetime.datetime`
        The starting time of the recurrence interval.
    end_date: Optional[:class:`datetime.datetime`]
        The ending time of the recurrence interval. This can only be received.
    frequency: :class:`ScheduledEventRecurrenceFrequency`
        How often the event occurs.
    interval: :class:`int`
        The spacing between the events, defined by ``frequency``.
    weekdays: List[:class:`ScheduledEventWeekday`]
        The days within a week the event recurs on.
    n_weekdays: List[:class:`ScheduledEventNWeekday`]
        The specific days within a specific week of a month the event recurs on.
    month_days: List[:class:`datetime.date`]
        The specific month and day the event recurs on. The year is always 2000.
    year_days: List[:class:`int`]
        The days within a year the event recurs on. This can only be received.
    count: Optional[:class:`int`]
        The total amount of times the event can recur before stopping.
        This can only be received.

    Examples
    --------
    Every weekday: ::

        discord.ScheduledEventRecurrenceRule(
            start_date,
            discord.ScheduledEventRecurrenceFrequency.daily,
            weekdays=[0, 1, 2, 3, 4],
        )

    Every other Wednesday: ::

        discord.ScheduledEventRecurrenceRule(
            start_date,
            discord.ScheduledEventRecurrenceFrequency.weekly,
            2,
            weekdays=[discord.ScheduledEventWeekday.wednesday],
        )

    Monthly on the fourth Wednesday: ::

        discord.ScheduledEventRecurrenceRule(
            start_date,
            discord.ScheduledEventRecurrenceFrequency.monthly,
            n_weekdays=[(4, 2)],
        )

    Annually on July 24: ::

        discord.ScheduledEventRecurrenceRule(
            start_date,
            discord.ScheduledEventRecurrenceFrequency.yearly,
            month_days=[datetime.date(2000, 7, 24)],
        )
    """

    __slots__ = (
        "_month_days",
        "count",
        "end_date",
        "frequency",
        "interval",
        "n_weekdays",
        "start_date",
        "weekdays",
        "year_days",
    )

    def __init__(
        self,
        start_date: dt.datetime,
        frequency: ScheduledEventRecurrenceFrequency,
        interval: int = 1,
        *,
        weekdays: Sequence[int | ScheduledEventWeekday] = MISSING,
        n_weekdays: Sequence[ScheduledEventNWeekday | tuple[int, int]] = MISSING,
        month_days: Sequence[dt.date] = MISSING,
    ) -> None:
        self.start_date: dt.datetime = start_date
        self.end_date: dt.datetime | None = None
        self.frequency: ScheduledEventRecurrenceFrequency = frequency
        self.interval: int = interval
        self.weekdays: list[ScheduledEventWeekday] = (
            [] if weekdays is MISSING else [_to_weekday(w) for w in weekdays]
        )
        self.n_weekdays: list[ScheduledEventNWeekday] = (
            []
            if n_weekdays is MISSING
            else [ScheduledEventNWeekday(n, day) for n, day in n_weekdays]
        )
        self._month_days: list[tuple[int, int]] = (
            [] if month_days is MISSING else [(d.month, d.day) for d in month_days]
        )
        self.year_days: list[int] = []
        self.count: int | None = None

    @classmethod
    def _from_data(cls, data: ScheduledEventRecurrenceRulePayload) -> Self:
        self = cls(
            utils.parse_time(data["start"]),
            try_enum(ScheduledEventRecurrenceFrequency, data["frequency"]),
            int(data["interval"]),
            weekdays=data.get("by_weekday") or MISSING,
            n_weekdays=[(n["n"], n["day"]) for n in data.get("by_n_weekday") or ()]
            or MISSING,
        )
        self.end_date = utils.parse_time(data.get("end"))
        self.count = data.get("count")
        self.year_days = list(data.get("by_year_day") or ())
        for month, day in zip(
            data.get("by_month") or (), data.get("by_month_day") or (), strict=False
        ):
            self._month_days.append((month, day))
        return self

    @property
    def month_days(self) -> list[dt.date]:
        """List[:class:`datetime.date`]: The specific month and day the event recurs on.

        The year is always 2000.
        """
        dates: list[dt.date] = []
        for month, day in self._month_days:
            with contextlib.suppress(ValueError):
                dates.append(dt.date(2000, month, day))
        return dates

    @month_days.setter
    def month_days(self, value: Sequence[dt.date]) -> None:
        self._month_days = [(d.month, d.day) for d in value]

    def _to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start_date.isoformat(),
            "frequency": self.frequency.value,
            "interval": self.interval,
            "by_weekday": [w.value for w in self.weekdays] or None,
            "by_n_weekday": [{"n": n, "day": d.value} for n, d in self.n_weekdays]
            or None,
            "by_month": [m for m, _ in self._month_days] or None,
            "by_month_day": [d for _, d in self._month_days] or None,
        }

    def __repr__(self) -> str:
        return (
            f"<ScheduledEventRecurrenceRule start_date={self.start_date} "
            f"frequency={self.frequency} interval={self.interval}>"
        )


def _single(legacy: Any, api: Any, name: str) -> Any:
    if legacy is not MISSING and api is not MISSING:
        raise InvalidArgument(f"cannot pass both `{name}` and `scheduled_{name}`")
    return legacy if api is MISSING else api


def _entity_payload(
    state: ConnectionState,
    *,
    location: Any,
    entity_type: ScheduledEventEntityType,
    entity_metadata: ScheduledEventEntityMetadata | None,
    channel_id: int | None,
    required: bool,
) -> dict[str, Any]:
    explicit = (entity_type, entity_metadata, channel_id)
    if location is not MISSING:
        if any(value is not MISSING for value in explicit):
            raise InvalidArgument(
                "cannot pass `location` with `entity_type`, `entity_metadata` or `channel_id`"
            )
        if not isinstance(location, ScheduledEventLocation):
            location = ScheduledEventLocation(state=state, value=location)
        location_type = cast("ScheduledEventEntityType", location.type)
        if location_type is ScheduledEventEntityType.external:
            return {
                "entity_type": location_type.value,
                "channel_id": None,
                "entity_metadata": {"location": str(location.value)},
            }
        return {
            "entity_type": location_type.value,
            "channel_id": cast(
                "StageChannel | VoiceChannel | Object", location.value
            ).id,
            "entity_metadata": None,
        }

    if required and entity_type is MISSING:
        raise InvalidArgument("either `location` or `entity_type` must be passed")

    payload: dict[str, Any] = {}
    if entity_type is not MISSING:
        payload["entity_type"] = int(entity_type)
    if channel_id is not MISSING:
        payload["channel_id"] = channel_id
    if entity_metadata is not MISSING:
        payload["entity_metadata"] = (
            None if entity_metadata is None else entity_metadata._to_dict()
        )

    if entity_type is not MISSING:
        if int(entity_type) == ScheduledEventEntityType.external.value:
            if payload.setdefault("channel_id", None) is not None:
                raise ValidationError("channel_id must be None for external events.")
            metadata: dict[str, Any] = payload.get("entity_metadata") or {}
            if not metadata.get("location"):
                raise ValidationError(
                    "entity_metadata with a location is required for external events."
                )
        else:
            if required and payload.get("channel_id") is None:
                raise ValidationError(
                    "channel_id is required for stage instance and voice events."
                )
            payload.setdefault("entity_metadata", None)
    return payload


class ScheduledEvent(Hashable):
    """Represents a Discord Guild Scheduled Event.

    .. container:: operations

        .. describe:: x == y

            Checks if two scheduled events are equal.

        .. describe:: x != y

            Checks if two scheduled events are not equal.

        .. describe:: hash(x)

            Returns the scheduled event's hash.

        .. describe:: str(x)

            Returns the scheduled event's name.

    .. versionadded:: 2.0

    Attributes
    ----------
    guild_id: :class:`int`
        The ID of the guild where the scheduled event is happening.
    channel_id: Optional[:class:`int`]
        The ID of the channel where the scheduled event is happening, if any.
    name: :class:`str`
        The name of the scheduled event.
    description: Optional[:class:`str`]
        The description of the scheduled event.
    start_time: :class:`datetime.datetime`
        The time when the event will start
    end_time: Optional[:class:`datetime.datetime`]
        The time when the event is supposed to end.
    status: :class:`ScheduledEventStatus`
        The status of the scheduled event.
    location: :class:`ScheduledEventLocation`
        The location of the event.
        See :class:`ScheduledEventLocation` for more information.
    subscriber_count: Optional[:class:`int`]
        The number of users that have marked themselves as interested in the event.
    creator_id: Optional[:class:`int`]
        The ID of the user who created the event.
        It may be ``None`` because events created before October 25th, 2021 haven't
        had their creators tracked.
    creator: Optional[Union[:class:`Member`, :class:`User`]]
        The member who created the event if it was resolved by the caller,
        otherwise the user given by the payload.
        Use :meth:`get_creator` to get the cached :class:`Member`.
    privacy_level: :class:`ScheduledEventPrivacyLevel`
        The privacy level of the event. Currently, the only possible value
        is :attr:`ScheduledEventPrivacyLevel.guild_only`, which is default,
        so there is no need to use this attribute.
    entity_type: :class:`ScheduledEventEntityType`
        The type of the event: a stage instance, a voice channel or an external location.

        .. versionadded:: 3.0
    entity_id: Optional[:class:`int`]
        The ID of an entity associated with the event.

        .. versionadded:: 3.0
    entity_metadata: Optional[:class:`ScheduledEventEntityMetadata`]
        Additional metadata of the event, such as the location of an external event.

        .. versionadded:: 3.0
    recurrence_rule: Optional[:class:`ScheduledEventRecurrenceRule`]
        How often the event recurs, or ``None`` for a one-time event.

        .. versionadded:: 3.0
    """

    __slots__ = (
        "_image",
        "_state",
        "_subscriber_ids",
        "channel_id",
        "creator",
        "creator_id",
        "description",
        "end_time",
        "entity_id",
        "entity_metadata",
        "entity_type",
        "guild_id",
        "id",
        "location",
        "name",
        "privacy_level",
        "recurrence_rule",
        "start_time",
        "status",
        "subscriber_count",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        guild: Guild | PartialGuild,
        data: ScheduledEventPayload,
        creator: Member | None = None,
    ) -> None:
        self._state: ConnectionState = state

        self.id: int = int(data.get("id"))
        self.guild_id: int = guild.id
        self.name: str = data.get("name")
        self.description: str | None = data.get("description", None)
        self._image: str | None = data.get("image", None)
        self.start_time: dt.datetime = utils.parse_time(
            data.get("scheduled_start_time")
        )
        end_time_data = data.get("scheduled_end_time", None)
        self.end_time: dt.datetime | None = (
            utils.parse_time(end_time_data) if end_time_data else None
        )
        self.status: ScheduledEventStatus = try_enum(
            ScheduledEventStatus, data.get("status")
        )
        self.subscriber_count: int | None = data.get("user_count", None)
        self._subscriber_ids: set[int] = set()
        self.creator_id: int | None = utils._get_as_snowflake(data, "creator_id")
        self.privacy_level: ScheduledEventPrivacyLevel = try_enum(
            ScheduledEventPrivacyLevel, data.get("privacy_level")
        )
        self.entity_type: ScheduledEventEntityType = try_enum(
            ScheduledEventEntityType, data.get("entity_type")
        )
        self.entity_id: int | None = utils._get_as_snowflake(data, "entity_id")
        entity_metadata_data = data.get("entity_metadata")
        self.entity_metadata: ScheduledEventEntityMetadata | None = (
            ScheduledEventEntityMetadata._from_data(entity_metadata_data)
            if entity_metadata_data
            else None
        )
        recurrence_rule_data = data.get("recurrence_rule")
        self.recurrence_rule: ScheduledEventRecurrenceRule | None = (
            ScheduledEventRecurrenceRule._from_data(recurrence_rule_data)
            if recurrence_rule_data
            else None
        )
        creator_data = data.get("creator")
        self.creator: Member | User | None = creator or (
            state.create_user(creator_data) if creator_data else None
        )

        channel_id = data.get("channel_id", None)
        self.channel_id: int | None = (
            int(channel_id) if channel_id is not None else None
        )
        if channel_id is None:
            self.location = ScheduledEventLocation(
                state=state, value=(entity_metadata_data or {}).get("location") or ""
            )
        else:
            self.location = ScheduledEventLocation(
                state=state,
                value=int(channel_id),
                type=try_enum(ScheduledEventLocationType, data.get("entity_type")),
            )

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return (
            f"<ScheduledEvent id={self.id} "
            f"name={self.name} "
            f"description={self.description} "
            f"start_time={self.start_time} "
            f"end_time={self.end_time} "
            f"location={self.location!r} "
            f"recurrence_rule={self.recurrence_rule!r} "
            f"status={self.status.name} "
            f"subscriber_count={self.subscriber_count} "
            f"creator_id={self.creator_id}>"
        )

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild where the scheduled event is happening.

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
    def channel(self) -> GuildChannel | PartialGuildChannel | None:
        """The channel where the scheduled event is happening, if any.

        This is the cached channel when the in-process cache holds it,
        otherwise a :class:`PartialGuildChannel` handle (always the case with a remote cache backend).
        """
        if self.channel_id is None:
            return None
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
            type=ChannelType.stage_voice
            if self.location.type is ScheduledEventLocationType.stage_instance
            else ChannelType.voice,
        )

    async def get_creator(self) -> Member | User | None:
        """|coro|

        Returns the member who created the event, like :attr:`creator` but resolved
        from the cache with any backend.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`Member`, :class:`User`]]
            The cached member, else the user of the payload, or ``None`` if the
            creator is unknown.
        """
        member = await self._state._get_member(self.guild_id, self.creator_id)
        return member or self.creator

    async def get_channel(self) -> GuildChannel | Thread | None:
        """|coro|

        Returns the cached channel where the scheduled event is happening.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`abc.GuildChannel`, :class:`Thread`]]
            The channel, or ``None`` if the event has no channel or it is not cached.
        """
        if self.channel_id is None:
            return None
        return await self._state._resolve_guild_channel(self.guild_id, self.channel_id)

    @property
    def created_at(self) -> dt.datetime:
        """Returns the scheduled event's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def interested(self) -> int | None:
        """An alias to :attr:`.subscriber_count`"""
        return self.subscriber_count

    @property
    def user_count(self) -> int | None:
        """The number of users subscribed to the event, named like the API field.

        This is an alias to :attr:`.subscriber_count`.

        .. versionadded:: 3.0
        """
        return self.subscriber_count

    @property
    def scheduled_start_time(self) -> dt.datetime:
        """The time when the event will start, named like the API field.

        This is an alias to :attr:`.start_time`.

        .. versionadded:: 3.0
        """
        return self.start_time

    @property
    def scheduled_end_time(self) -> dt.datetime | None:
        """The time when the event is supposed to end, named like the API field.

        This is an alias to :attr:`.end_time`.

        .. versionadded:: 3.0
        """
        return self.end_time

    @property
    def url(self) -> str:
        """The url to reference the scheduled event."""
        return f"https://discord.com/events/{self.guild.id}/{self.id}"

    @property
    def cover(self) -> Asset | None:
        """
        Returns the scheduled event cover image asset, if available.

        .. deprecated:: 2.7
                Use the :attr:`image` property instead.
        """
        warn_deprecated("cover", "image", "2.7")
        return self.image

    @property
    def image(self) -> Asset | None:
        """Returns the scheduled event cover image asset, if available."""
        if self._image is None:
            return None
        return Asset._from_scheduled_event_image(
            self._state,
            self.id,
            self._image,
        )

    async def edit(
        self,
        *,
        reason: str | None = None,
        name: str = MISSING,
        description: str | None = MISSING,
        status: int | ScheduledEventStatus = MISSING,
        location: (
            str | int | VoiceChannel | StageChannel | ScheduledEventLocation
        ) = MISSING,
        start_time: dt.datetime = MISSING,
        end_time: dt.datetime = MISSING,
        cover: bytes | None = MISSING,
        image: bytes | None = MISSING,
        privacy_level: ScheduledEventPrivacyLevel = ScheduledEventPrivacyLevel.guild_only,
        scheduled_start_time: dt.datetime = MISSING,
        scheduled_end_time: dt.datetime = MISSING,
        entity_type: ScheduledEventEntityType = MISSING,
        entity_metadata: ScheduledEventEntityMetadata | None = MISSING,
        channel_id: int | None = MISSING,
        recurrence_rule: ScheduledEventRecurrenceRule | None = MISSING,
    ) -> ScheduledEvent | None:
        """|coro|

        Edits the Scheduled Event's data

        All parameters are optional unless the event becomes an
        :attr:`ScheduledEventEntityType.external` one, then ``end_time``
        is required.

        Will return a new :class:`.ScheduledEvent` object if applicable.

        Parameters
        ----------
        name: :class:`str`
            The new name of the event.
        description: Optional[:class:`str`]
            The new description of the event.
        location: :class:`.ScheduledEventLocation`
            The location of the event. This is a shortcut for ``entity_type``,
            ``entity_metadata`` and ``channel_id`` and cannot be used with them.
        status: :class:`ScheduledEventStatus`
            The status of the event. It is recommended, however,
            to use :meth:`.start`, :meth:`.complete`, and
            :meth:`cancel` to edit statuses instead.
        start_time: :class:`datetime.datetime`
            The new starting time for the event.
        end_time: :class:`datetime.datetime`
            The new ending time of the event.
        scheduled_start_time: :class:`datetime.datetime`
            The new starting time for the event, named like the API field.
            Cannot be used with ``start_time``.

            .. versionadded:: 3.0
        scheduled_end_time: :class:`datetime.datetime`
            The new ending time of the event, named like the API field.
            Cannot be used with ``end_time``.

            .. versionadded:: 3.0
        entity_type: :class:`ScheduledEventEntityType`
            The new type of the event. When changing to
            :attr:`ScheduledEventEntityType.external`, ``entity_metadata`` with a
            location and a ending time are required and the channel is cleared.

            .. versionadded:: 3.0
        entity_metadata: Optional[:class:`ScheduledEventEntityMetadata`]
            The new metadata of the event. Discord silently discards it for
            events that are not external.

            .. versionadded:: 3.0
        channel_id: Optional[:class:`int`]
            The ID of the new channel of the event, ``None`` for an external event.

            .. versionadded:: 3.0
        recurrence_rule: Optional[:class:`ScheduledEventRecurrenceRule`]
            How often the event recurs, or ``None`` to make it a one-time event.

            .. versionadded:: 3.0
        privacy_level: :class:`ScheduledEventPrivacyLevel`
            The privacy level of the event. Currently, the only possible value
            is :attr:`ScheduledEventPrivacyLevel.guild_only`, which is default,
            so there is no need to change this parameter.
        reason: Optional[:class:`str`]
            The reason to show in the audit log.
        image: Optional[:class:`bytes`]
            The cover image of the scheduled event.
        cover: Optional[:class:`bytes`]
            The cover image of the scheduled event.

            .. deprecated:: 2.7
                Use the `image` argument instead.

        Returns
        -------
        Optional[:class:`.ScheduledEvent`]
            The newly updated scheduled event object. This is only returned when certain
            fields are updated.

        Raises
        ------
        Forbidden
            You do not have the Manage Events permission.
        HTTPException
            The operation failed.
        InvalidArgument
            Conflicting parameters were passed.
        ValidationError
            An external event is missing its location or ending time.
        """
        payload: dict[str, Any] = {}

        if name is not MISSING:
            payload["name"] = name

        if description is not MISSING:
            payload["description"] = description

        if status is not MISSING:
            payload["status"] = int(status)

        if privacy_level is not MISSING:
            payload["privacy_level"] = int(privacy_level)

        if cover is not MISSING:
            warn_deprecated("cover", "image", "2.7")
            if image is not MISSING:
                raise InvalidArgument(
                    "cannot pass both `image` and `cover` to `ScheduledEvent.edit`"
                )
            image = cover

        if image is not MISSING:
            if image is None:
                payload["image"] = None
            else:
                payload["image"] = utils._bytes_to_base64_data(image)

        if recurrence_rule is not MISSING:
            payload["recurrence_rule"] = (
                None if recurrence_rule is None else recurrence_rule._to_dict()
            )

        start_time = _single(start_time, scheduled_start_time, "start_time")
        end_time = _single(end_time, scheduled_end_time, "end_time")

        entity = _entity_payload(
            self._state,
            location=location,
            entity_type=entity_type,
            entity_metadata=entity_metadata,
            channel_id=channel_id,
            required=False,
        )
        payload.update(entity)

        entity_type_value = entity.get("entity_type", self.entity_type.value)
        if (
            end_time is MISSING
            and entity_type_value == ScheduledEventEntityType.external.value
        ):
            current_end_time = self.end_time
            if current_end_time is None:
                raise ValidationError(
                    "end_time needs to be passed if location type is external."
                )
            end_time = current_end_time

        if start_time is not MISSING:
            payload["scheduled_start_time"] = start_time.isoformat()

        if end_time is not MISSING:
            payload["scheduled_end_time"] = end_time.isoformat()

        if payload != {}:
            data = await self._state.http.edit_scheduled_event(
                self.guild.id, self.id, **payload, reason=reason
            )
            return ScheduledEvent(data=data, guild=self.guild, state=self._state)
        return None

    async def delete(self) -> None:
        """|coro|

        Deletes the scheduled event.

        Raises
        ------
        Forbidden
            You do not have the Manage Events permission.
        HTTPException
            The operation failed.
        """
        await self._state.http.delete_scheduled_event(self.guild.id, self.id)

    async def start(self, *, reason: str | None = None) -> ScheduledEvent | None:
        """|coro|

        Starts the scheduled event. Shortcut from :meth:`.edit`.

        .. note::

            This method can only be used if :attr:`.status` is :attr:`ScheduledEventStatus.scheduled`.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason to show in the audit log.

        Returns
        -------
        Optional[:class:`.ScheduledEvent`]
            The newly updated scheduled event object.

        Raises
        ------
        Forbidden
            You do not have the Manage Events permission.
        HTTPException
            The operation failed.
        """
        return await self.edit(status=ScheduledEventStatus.active, reason=reason)

    async def complete(self, *, reason: str | None = None) -> ScheduledEvent | None:
        """|coro|

        Ends/completes the scheduled event. Shortcut from :meth:`.edit`.

        .. note::

            This method can only be used if :attr:`.status` is :attr:`ScheduledEventStatus.active`.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason to show in the audit log.

        Returns
        -------
        Optional[:class:`.ScheduledEvent`]
            The newly updated scheduled event object.

        Raises
        ------
        Forbidden
            You do not have the Manage Events permission.
        HTTPException
            The operation failed.
        """
        return await self.edit(status=ScheduledEventStatus.completed, reason=reason)

    async def cancel(self, *, reason: str | None = None) -> ScheduledEvent | None:
        """|coro|

        Cancels the scheduled event. Shortcut from :meth:`.edit`.

        .. note::

            This method can only be used if :attr:`.status` is :attr:`ScheduledEventStatus.scheduled`.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason to show in the audit log.

        Returns
        -------
        Optional[:class:`.ScheduledEvent`]
            The newly updated scheduled event object.

        Raises
        ------
        Forbidden
            You do not have the Manage Events permission.
        HTTPException
            The operation failed.
        """
        return await self.edit(status=ScheduledEventStatus.canceled, reason=reason)

    def subscribers(
        self,
        *,
        limit: int | None = 100,
        as_member: bool = False,
        before: Snowflake | dt.datetime | None = None,
        after: Snowflake | dt.datetime | None = None,
        use_cache: bool = False,
    ) -> ScheduledEventSubscribersIterator:
        """Returns an :class:`AsyncIterator` representing the users or members subscribed to the event.

        The ``after`` and ``before`` parameters must represent member
        or user objects and meet the :class:`abc.Snowflake` abc.

        .. note::

            Even is ``as_member`` is set to ``True``, if the user
            is outside the guild, it will be a :class:`User` object.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of results to return.
        as_member: Optional[:class:`bool`]
            Whether to fetch :class:`Member` objects instead of user objects.
            There may still be :class:`User` objects if the user is outside
            the guild.
        before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieves users before this date or object. If a datetime is provided,
            it is recommended to use a UTC aware datetime. If the datetime is naive,
            it is assumed to be local time.
        after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieves users after this date or object. If a datetime is provided,
            it is recommended to use a UTC aware datetime. If the datetime is naive,
            it is assumed to be local time.
        use_cache: :class:`bool`
            Whether to yield the subscribers tracked from the gateway events
            instead of requesting them from Discord. Only subscribers that are
            cached are returned. Defaults to ``False``.

        Yields
        ------
        Union[:class:`User`, :class:`Member`]
            The subscribed :class:`Member`. If ``as_member`` is set to
            ``False`` or the user is outside the guild, it will be a
            :class:`User` object.

        Raises
        ------
        HTTPException
            Fetching the subscribed users failed.

        Examples
        --------
        Usage ::

            async for user in event.subscribers(limit=100):
                print(user.name)

        Flattening into a list: ::

            users = await event.subscribers(limit=100).flatten()
            # users is now a list of User...

        Getting members instead of user objects: ::

            async for member in event.subscribers(limit=100, as_member=True):
                print(member.display_name)
        """
        return ScheduledEventSubscribersIterator(
            event=self,
            limit=limit,
            with_member=as_member,
            before=before,
            after=after,
            use_cache=use_cache,
        )
