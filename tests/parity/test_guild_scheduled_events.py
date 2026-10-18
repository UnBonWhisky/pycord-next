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


"""Guild scheduled event parity: entity fields, recurrence rules and cache fixes (upstream #3025, #2749)."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest

from discord import (
    InvalidArgument,
    Member,
    Object,
    ScheduledEvent,
    ScheduledEventEntityMetadata,
    ScheduledEventEntityType,
    ScheduledEventLocation,
    ScheduledEventLocationType,
    ScheduledEventNWeekday,
    ScheduledEventPrivacyLevel,
    ScheduledEventRecurrenceFrequency,
    ScheduledEventRecurrenceRule,
    ScheduledEventStatus,
    ScheduledEventWeekday,
    ValidationError,
)
from tests.state.conftest import build_state
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    OTHER_USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    ready,
    user_payload,
)

if TYPE_CHECKING:
    from discord.guild import Guild
    from discord.http import HTTPClient
    from discord.state import ConnectionState

EVENT_ID = 7_000_000_000_000_001
START = dt.datetime(2030, 1, 1, 12, tzinfo=dt.timezone.utc)
END = dt.datetime(2030, 1, 1, 14, tzinfo=dt.timezone.utc)


@pytest.fixture(params=["memory", "redis"])
def backend_kind(request: pytest.FixtureRequest) -> str:
    return request.param


def event_payload(**fields: Any) -> dict[str, Any]:
    return {
        "id": str(EVENT_ID),
        "guild_id": str(GUILD_ID),
        "channel_id": str(CHANNEL_ID),
        "creator_id": None,
        "name": "event",
        "description": None,
        "scheduled_start_time": START.isoformat(),
        "scheduled_end_time": None,
        "privacy_level": 2,
        "status": 1,
        "entity_type": 2,
        "entity_id": None,
        "entity_metadata": None,
        "recurrence_rule": None,
        **fields,
    }


def external_payload(**fields: Any) -> dict[str, Any]:
    return event_payload(
        channel_id=None,
        entity_type=3,
        entity_metadata={"location": "somewhere"},
        scheduled_end_time=END.isoformat(),
        **fields,
    )


def rule_payload(**fields: Any) -> dict[str, Any]:
    return {
        "start": START.isoformat(),
        "end": None,
        "frequency": 2,
        "interval": 2,
        "by_weekday": [2],
        "by_n_weekday": None,
        "by_month": None,
        "by_month_day": None,
        "by_year_day": None,
        "count": None,
        **fields,
    }


async def setup(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, kind: str
) -> tuple[ConnectionState, Recorder, Guild]:
    state = build_state(loop, http, kind, cache_default_sounds=False)
    recorder = Recorder()
    state.dispatch = recorder
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    return state, recorder, guild


class Capture:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or event_payload()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, route: Any, **kwargs: Any) -> dict[str, Any]:
        payload = kwargs.get("json", {})
        self.calls.append((route.method, route.path, payload))
        return self.response


def model(guild: Guild, **fields: Any) -> ScheduledEvent:
    return ScheduledEvent(
        state=guild._state,
        guild=guild,
        data=event_payload(**fields),  # type: ignore[arg-type]
    )


def test_enum_alias_and_values() -> None:
    assert ScheduledEventLocationType is ScheduledEventEntityType
    assert [e.value for e in ScheduledEventEntityType] == [1, 2, 3]
    assert [e.name for e in ScheduledEventRecurrenceFrequency] == [
        "yearly",
        "monthly",
        "weekly",
        "daily",
    ]
    assert [e.value for e in ScheduledEventRecurrenceFrequency] == [0, 1, 2, 3]
    assert ScheduledEventWeekday.monday.value == 0
    assert ScheduledEventWeekday.sunday.value == 6


async def test_event_exposes_the_api_fields(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(
        guild,
        entity_id="5",
        user_count=3,
        recurrence_rule=rule_payload(),
        scheduled_end_time=END.isoformat(),
    )
    assert event.entity_type is ScheduledEventEntityType.voice
    assert event.entity_id == 5
    assert event.entity_metadata is None
    assert event.privacy_level is ScheduledEventPrivacyLevel.guild_only
    assert event.user_count == event.subscriber_count == event.interested == 3
    assert event.scheduled_start_time == event.start_time == START
    assert event.scheduled_end_time == event.end_time == END
    assert event.channel_id == CHANNEL_ID
    assert event.recurrence_rule is not None


async def test_external_event_has_entity_metadata_and_legacy_location(
    http: HTTPClient,
) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = ScheduledEvent(state=guild._state, guild=guild, data=external_payload())  # type: ignore[arg-type]
    assert event.entity_type is ScheduledEventEntityType.external
    assert isinstance(event.entity_metadata, ScheduledEventEntityMetadata)
    assert event.entity_metadata.location == "somewhere"
    assert str(event.location) == "somewhere"
    assert event.location.type is ScheduledEventEntityType.external


async def test_event_without_recurrence_rule(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    assert event.recurrence_rule is None
    event = model(guild, recurrence_rule=None, entity_metadata=None, channel_id=None)
    assert str(event.location) == ""


def test_recurrence_rule_parses_the_payload() -> None:
    rule = ScheduledEventRecurrenceRule._from_data(
        rule_payload(  # type: ignore[arg-type]
            frequency=0,
            interval=1,
            by_weekday=None,
            by_month=[7],
            by_month_day=[24],
            by_year_day=[205],
            count=4,
            end=END.isoformat(),
        )
    )
    assert rule.start_date == START
    assert rule.end_date == END
    assert rule.frequency is ScheduledEventRecurrenceFrequency.yearly
    assert rule.interval == 1
    assert rule.month_days == [dt.date(2000, 7, 24)]
    assert rule.year_days == [205]
    assert rule.count == 4
    assert rule.weekdays == []


def test_recurrence_rule_examples_from_the_docs() -> None:
    weekday = ScheduledEventRecurrenceRule(
        START, ScheduledEventRecurrenceFrequency.daily, weekdays=[0, 1, 2, 3, 4]
    )
    assert weekday._to_dict() == {
        "start": START.isoformat(),
        "frequency": 3,
        "interval": 1,
        "by_weekday": [0, 1, 2, 3, 4],
        "by_n_weekday": None,
        "by_month": None,
        "by_month_day": None,
    }

    other_wednesday = ScheduledEventRecurrenceRule(
        START,
        ScheduledEventRecurrenceFrequency.weekly,
        2,
        weekdays=[ScheduledEventWeekday.wednesday],
    )
    assert other_wednesday._to_dict()["by_weekday"] == [2]
    assert other_wednesday._to_dict()["interval"] == 2
    assert other_wednesday.weekdays == [ScheduledEventWeekday.wednesday]

    fourth_wednesday = ScheduledEventRecurrenceRule(
        START, ScheduledEventRecurrenceFrequency.monthly, n_weekdays=[(4, 2)]
    )
    assert fourth_wednesday._to_dict()["by_n_weekday"] == [{"n": 4, "day": 2}]
    assert fourth_wednesday.n_weekdays == [
        ScheduledEventNWeekday(4, ScheduledEventWeekday.wednesday)
    ]
    assert list(fourth_wednesday.n_weekdays[0]) == [4, ScheduledEventWeekday.wednesday]

    july_24 = ScheduledEventRecurrenceRule(
        START,
        ScheduledEventRecurrenceFrequency.yearly,
        month_days=[dt.date(1900, 7, 24)],
    )
    assert july_24._to_dict()["by_month"] == [7]
    assert july_24._to_dict()["by_month_day"] == [24]
    assert july_24.month_days == [dt.date(2000, 7, 24)]


def test_recurrence_rule_never_sends_the_read_only_fields() -> None:
    rule = ScheduledEventRecurrenceRule._from_data(
        rule_payload(count=3, by_year_day=[1], end=END.isoformat())  # type: ignore[arg-type]
    )
    assert {"count", "end", "by_year_day"}.isdisjoint(rule._to_dict())


async def test_create_keeps_the_legacy_signature(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    location = ScheduledEventLocation(
        state=guild._state, value=CHANNEL_ID, type=ScheduledEventEntityType.voice
    )
    event = await guild.create_scheduled_event(
        name="event", start_time=START, end_time=END, location=location
    )
    method, path, payload = capture.calls[0]
    assert (method, path) == ("POST", "/guilds/{guild_id}/scheduled-events")
    assert payload["name"] == "event"
    assert payload["scheduled_start_time"] == START.isoformat()
    assert payload["scheduled_end_time"] == END.isoformat()
    assert payload["privacy_level"] == 2
    assert payload["channel_id"] == CHANNEL_ID
    assert payload["entity_metadata"] is None
    assert payload["entity_type"] == 2
    assert "recurrence_rule" not in payload
    assert event is not None
    assert await guild.get_scheduled_event(event.id) is not None


async def test_create_external_with_a_string_location(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture(external_payload())
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    await guild.create_scheduled_event(
        name="event", start_time=START, end_time=END, location="somewhere"
    )
    payload = capture.calls[0][2]
    assert payload["entity_type"] == 3
    assert payload["channel_id"] is None
    assert payload["entity_metadata"] == {"location": "somewhere"}


async def test_create_with_the_api_named_parameters_and_recurrence(
    http: HTTPClient,
) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture(external_payload(recurrence_rule=rule_payload()))
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    rule = ScheduledEventRecurrenceRule(
        START,
        ScheduledEventRecurrenceFrequency.weekly,
        2,
        weekdays=[ScheduledEventWeekday.wednesday],
    )
    event = await guild.create_scheduled_event(
        name="event",
        scheduled_start_time=START,
        scheduled_end_time=END,
        entity_type=ScheduledEventEntityType.external,
        entity_metadata=ScheduledEventEntityMetadata("somewhere"),
        recurrence_rule=rule,
    )
    payload = capture.calls[0][2]
    assert payload["entity_type"] == 3
    assert payload["channel_id"] is None
    assert payload["entity_metadata"] == {"location": "somewhere"}
    assert payload["recurrence_rule"] == rule._to_dict()
    assert event is not None
    assert event.recurrence_rule is not None
    assert event.recurrence_rule.interval == 2
    assert event.recurrence_rule.weekdays == [ScheduledEventWeekday.wednesday]


async def test_create_with_an_entity_channel(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    await guild.create_scheduled_event(
        name="event",
        scheduled_start_time=START,
        entity_type=ScheduledEventEntityType.stage_instance,
        channel_id=CHANNEL_ID,
    )
    payload = capture.calls[0][2]
    assert payload["entity_type"] == 1
    assert payload["channel_id"] == CHANNEL_ID
    assert payload["entity_metadata"] is None


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"start_time": START}, InvalidArgument),
        ({"location": "x"}, InvalidArgument),
        (
            {"start_time": START, "scheduled_start_time": START, "location": "x"},
            InvalidArgument,
        ),
        (
            {
                "start_time": START,
                "location": "x",
                "entity_type": ScheduledEventEntityType.external,
            },
            InvalidArgument,
        ),
        (
            {
                "start_time": START,
                "entity_type": ScheduledEventEntityType.external,
            },
            ValidationError,
        ),
        (
            {"start_time": START, "entity_type": ScheduledEventEntityType.voice},
            ValidationError,
        ),
    ],
)
async def test_create_rejects_invalid_combinations(
    http: HTTPClient, fields: dict[str, Any], error: type[Exception]
) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(error):
        await guild.create_scheduled_event(name="event", **fields)
    assert capture.calls == []


async def test_edit_keeps_the_legacy_signature(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    await event.edit(
        name="new", status=2, start_time=START, location="here", end_time=END
    )
    method, path, payload = capture.calls[0]
    assert (method, path) == ("PATCH", "/guilds/{guild_id}/scheduled-events/{event_id}")
    assert payload == {
        "name": "new",
        "status": 2,
        "privacy_level": 2,
        "scheduled_start_time": START.isoformat(),
        "scheduled_end_time": END.isoformat(),
        "entity_type": 3,
        "channel_id": None,
        "entity_metadata": {"location": "here"},
    }


async def test_edit_external_requires_an_end_time(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValidationError):
        await event.edit(location="here")
    with pytest.raises(ValidationError):
        await event.edit(
            entity_type=ScheduledEventEntityType.external,
            entity_metadata=ScheduledEventEntityMetadata("here"),
        )
    assert capture.calls == []


async def test_edit_with_the_api_named_parameters(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    rule = ScheduledEventRecurrenceRule(
        START, ScheduledEventRecurrenceFrequency.daily, weekdays=[5, 6]
    )
    await event.edit(
        scheduled_start_time=START,
        scheduled_end_time=END,
        entity_type=ScheduledEventEntityType.external,
        entity_metadata=ScheduledEventEntityMetadata("here"),
        recurrence_rule=rule,
    )
    payload = capture.calls[0][2]
    assert payload["scheduled_start_time"] == START.isoformat()
    assert payload["scheduled_end_time"] == END.isoformat()
    assert payload["entity_type"] == 3
    assert payload["channel_id"] is None
    assert payload["entity_metadata"] == {"location": "here"}
    assert payload["recurrence_rule"]["by_weekday"] == [5, 6]


async def test_edit_can_remove_the_recurrence_rule(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild, recurrence_rule=rule_payload())
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    await event.edit(recurrence_rule=None)
    assert capture.calls[0][2]["recurrence_rule"] is None


async def test_edit_rejects_both_spellings(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    with pytest.raises(InvalidArgument):
        await event.edit(start_time=START, scheduled_start_time=START)
    with pytest.raises(InvalidArgument):
        await event.edit(
            location="x", end_time=END, entity_type=ScheduledEventEntityType.voice
        )


async def test_start_still_edits_the_status(http: HTTPClient) -> None:
    _, _, guild = await setup(asyncio.get_running_loop(), http, "memory")
    event = model(guild)
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    await event.start()
    assert capture.calls[0][2]["status"] == ScheduledEventStatus.active.value


async def test_gateway_event_keeps_the_recurrence_rule(
    http: HTTPClient, backend_kind: str
) -> None:
    state, _, guild = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](
        event_payload(recurrence_rule=rule_payload(), user_count=2)
    )
    cached = await guild.get_scheduled_event(EVENT_ID)
    assert cached is not None
    assert cached.recurrence_rule is not None
    assert cached.recurrence_rule.weekdays == [ScheduledEventWeekday.wednesday]
    assert cached.user_count == 2


async def test_user_add_counts_uncached_members(
    http: HTTPClient, backend_kind: str
) -> None:
    state, recorder, guild = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event_payload(user_count=2))
    subscription = {
        "guild_scheduled_event_id": str(EVENT_ID),
        "user_id": str(OTHER_USER_ID + 99),
        "guild_id": str(GUILD_ID),
    }
    await state.parsers["GUILD_SCHEDULED_EVENT_USER_ADD"](subscription)
    cached = await guild.get_scheduled_event(EVENT_ID)
    assert cached is not None
    assert cached.subscriber_count == 3
    assert "raw_scheduled_event_user_add" in recorder.names()
    assert "scheduled_event_user_add" not in recorder.names()

    await state.parsers["GUILD_SCHEDULED_EVENT_USER_REMOVE"](subscription)
    cached = await guild.get_scheduled_event(EVENT_ID)
    assert cached is not None
    assert cached.subscriber_count == 2


async def test_user_add_without_a_known_count(
    http: HTTPClient, backend_kind: str
) -> None:
    state, _, guild = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event_payload())
    await state.parsers["GUILD_SCHEDULED_EVENT_USER_ADD"](
        {
            "guild_scheduled_event_id": str(EVENT_ID),
            "user_id": str(OTHER_USER_ID),
            "guild_id": str(GUILD_ID),
        }
    )
    cached = await guild.get_scheduled_event(EVENT_ID)
    assert cached is not None
    assert cached.subscriber_count is None


async def test_user_add_dispatches_for_cached_members(
    http: HTTPClient, backend_kind: str
) -> None:
    state, recorder, _ = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["GUILD_MEMBER_ADD"](
        {
            "guild_id": str(GUILD_ID),
            "user": user_payload(OTHER_USER_ID),
            "roles": [],
            "joined_at": "2024-01-01T00:00:00+00:00",
            "deaf": False,
            "mute": False,
            "flags": 0,
        }
    )
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event_payload(user_count=0))
    await state.parsers["GUILD_SCHEDULED_EVENT_USER_ADD"](
        {
            "guild_scheduled_event_id": str(EVENT_ID),
            "user_id": str(OTHER_USER_ID),
            "guild_id": str(GUILD_ID),
        }
    )
    event, member = recorder.last("scheduled_event_user_add")
    assert event.subscriber_count == 1
    assert member.id == OTHER_USER_ID


async def test_update_and_delete_keep_the_cached_count(
    http: HTTPClient, backend_kind: str
) -> None:
    state, recorder, guild = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event_payload(user_count=4))
    await state.parsers["GUILD_SCHEDULED_EVENT_UPDATE"](event_payload(name="renamed"))
    old, new = recorder.last("scheduled_event_update")
    assert old.subscriber_count == 4
    assert new.name == "renamed"
    assert new.subscriber_count == 4
    cached = await guild.get_scheduled_event(EVENT_ID)
    assert cached is not None
    assert cached.subscriber_count == 4

    await state.parsers["GUILD_SCHEDULED_EVENT_DELETE"](event_payload())
    (deleted,) = recorder.last("scheduled_event_delete")
    assert deleted.status is ScheduledEventStatus.canceled
    assert deleted.subscriber_count == 4
    assert await guild.get_scheduled_event(EVENT_ID) is None


async def test_subscribers_use_cache(http: HTTPClient, backend_kind: str) -> None:
    state, _, guild = await setup(asyncio.get_running_loop(), http, backend_kind)
    for user_id in (OTHER_USER_ID, OTHER_USER_ID + 1):
        await state.parsers["GUILD_MEMBER_ADD"](
            {
                "guild_id": str(GUILD_ID),
                "user": user_payload(user_id),
                "roles": [],
                "joined_at": "2024-01-01T00:00:00+00:00",
                "deaf": False,
                "mute": False,
                "flags": 0,
            }
        )
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event_payload(user_count=0))
    for user_id in (OTHER_USER_ID + 1, OTHER_USER_ID, OTHER_USER_ID + 500):
        await state.parsers["GUILD_SCHEDULED_EVENT_USER_ADD"](
            {
                "guild_scheduled_event_id": str(EVENT_ID),
                "user_id": str(user_id),
                "guild_id": str(GUILD_ID),
            }
        )
    event = await guild.get_scheduled_event(EVENT_ID)
    assert event is not None

    members = await event.subscribers(use_cache=True, as_member=True).flatten()
    assert [m.id for m in members] == [OTHER_USER_ID, OTHER_USER_ID + 1]
    assert all(isinstance(m, Member) for m in members)

    limited = await event.subscribers(use_cache=True, limit=1).flatten()
    assert [u.id for u in limited] == [OTHER_USER_ID]

    after = await event.subscribers(
        use_cache=True, after=Object(id=OTHER_USER_ID)
    ).flatten()
    assert [u.id for u in after] == [OTHER_USER_ID + 1]

    await state.parsers["GUILD_SCHEDULED_EVENT_UPDATE"](event_payload(name="renamed"))
    await state.parsers["GUILD_SCHEDULED_EVENT_USER_REMOVE"](
        {
            "guild_scheduled_event_id": str(EVENT_ID),
            "user_id": str(OTHER_USER_ID),
            "guild_id": str(GUILD_ID),
        }
    )
    event = await guild.get_scheduled_event(EVENT_ID)
    assert event is not None
    remaining = await event.subscribers(use_cache=True).flatten()
    assert [u.id for u in remaining] == [OTHER_USER_ID + 1]
