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

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.errors import HTTPException, NoMoreItems
from discord.iterators import (
    ArchivedThreadIterator,
    AuditLogIterator,
    BanIterator,
    EntitlementIterator,
    GuildIterator,
    HistoryIterator,
    MemberIterator,
    MessagePinIterator,
    ReactionIterator,
    ScheduledEventSubscribersIterator,
    SubscriptionIterator,
    VoteIterator,
    _AsyncIterator,
)
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


class Numbers(_AsyncIterator[int]):
    def __init__(self, count: int) -> None:
        self.values = list(range(count))

    async def next(self) -> int:
        if not self.values:
            raise NoMoreItems
        return self.values.pop(0)


def ids(items: list[Any]) -> list[int]:
    return [int(i.id) for i in items]


def test_base_iterator_helpers(world: World) -> None:
    run = world.run

    async def collect() -> None:
        assert await Numbers(5).flatten() == [0, 1, 2, 3, 4]
        assert await Numbers(5).find(lambda n: n > 2) == 3
        assert await Numbers(5).find(lambda n: n > 9) is None

        async def async_predicate(n: int) -> bool:
            return n == 2

        assert await Numbers(5).find(async_predicate) == 2
        assert await Numbers(7).chunk(3).flatten() == [[0, 1, 2], [3, 4, 5], [6]]
        assert await Numbers(4).map(lambda n: n * 2).flatten() == [0, 2, 4, 6]
        assert await Numbers(6).filter(lambda n: n % 2).flatten() == [1, 3, 5]
        assert await Numbers(3).filter(None).flatten() == [1, 2]

        async def async_double(n: int) -> int:
            return n * 2

        assert await Numbers(3).map(async_double).flatten() == [0, 2, 4]
        collected = [n async for n in Numbers(3)]
        assert collected == [0, 1, 2]

    run(collect())
    with pytest.raises(ValueError, match="greater than 0"):
        Numbers(1).chunk(0)


def test_get_matches_nested_attributes(world: World) -> None:
    class Holder(_AsyncIterator[Any]):
        def __init__(self) -> None:
            self.items = [
                SimpleNamespace(name="a", inner=SimpleNamespace(size=1)),
                SimpleNamespace(name="b", inner=SimpleNamespace(size=2)),
            ]

        async def next(self) -> Any:
            if not self.items:
                raise NoMoreItems
            return self.items.pop(0)

    found = world.run(Holder().get(name="b", inner__size=2))
    assert found.name == "b"
    assert world.run(Holder().get(name="b", inner__size=1)) is None


def make_messages(rig: Rig, first: int, count: int, step: int = -1) -> list[Any]:
    return [rig.message_payload(first + i * step) for i in range(count)]


def test_history_before_pages_until_a_short_page(world: World) -> None:
    rig = Rig(world)
    rig.pages("logs_from", make_messages(rig, 1000, 100), make_messages(rig, 900, 30))

    messages = rig.run(HistoryIterator(rig.channel, limit=None).flatten())

    assert len(messages) == 130
    assert ids(messages)[:2] == [1000, 999]
    first, second = rig.http.logs_from.call_args_list
    assert first.args == (rig.channel.id, 100)
    assert first.kwargs == {"before": None}
    assert second.kwargs == {"before": 901}


def test_history_limit_and_after_filter(world: World) -> None:
    rig = Rig(world)
    rig.pages("logs_from", make_messages(rig, 100, 3))

    iterator = HistoryIterator(rig.channel, limit=3, before=discord.Object(id=500))
    assert len(rig.run(iterator.flatten())) == 3
    assert rig.http.logs_from.call_args.args == (rig.channel.id, 3)

    rig.pages("logs_from", make_messages(rig, 100, 3))
    filtered = HistoryIterator(
        rig.channel,
        limit=None,
        oldest_first=False,
        after=discord.Object(id=99),
    )
    assert filtered.reverse is False
    assert ids(rig.run(filtered.flatten())) == [100]


def test_history_oldest_first_walks_forward(world: World) -> None:
    rig = Rig(world)
    rig.pages("logs_from", make_messages(rig, 20, 3, step=-1))

    iterator = HistoryIterator(
        rig.channel,
        limit=None,
        after=discord.Object(id=10),
        before=discord.Object(id=20),
    )
    messages = rig.run(iterator.flatten())

    assert ids(messages) == [18, 19]
    assert rig.http.logs_from.call_args.kwargs == {"after": 10}


def test_history_around(world: World) -> None:
    rig = Rig(world)
    rig.pages("logs_from", make_messages(rig, 30, 5))

    iterator = HistoryIterator(
        rig.channel,
        limit=101,
        around=discord.Object(id=28),
        before=discord.Object(id=40),
        after=discord.Object(id=26),
    )
    assert iterator.limit == 100
    assert ids(rig.run(iterator.flatten())) == [27, 28, 29, 30]
    assert rig.http.logs_from.call_args.kwargs == {"around": 28}
    assert rig.run(iterator._retrieve_messages_around_strategy(10)) == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"before": discord.Object(id=40)}, [30, 29, 28, 27, 26]),
        ({"after": discord.Object(id=28)}, [29, 30]),
    ],
)
def test_history_around_single_bound(
    world: World, kwargs: dict[str, Any], expected: list[int]
) -> None:
    rig = Rig(world)
    rig.pages("logs_from", make_messages(rig, 30, 5))
    iterator = HistoryIterator(
        rig.channel, limit=10, around=discord.Object(id=28), **kwargs
    )
    assert ids(rig.run(iterator.flatten())) == expected


def test_history_around_validates_the_limit(world: World) -> None:
    rig = Rig(world)
    with pytest.raises(ValueError, match="limit=None"):
        HistoryIterator(rig.channel, limit=None, around=discord.Object(id=1))
    with pytest.raises(ValueError, match="max limit 101"):
        HistoryIterator(rig.channel, limit=102, around=discord.Object(id=1))


def test_history_accepts_datetimes(world: World) -> None:
    rig = Rig(world)
    moment = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    iterator = HistoryIterator(rig.channel, limit=1, before=moment)
    assert iterator.before is not None
    assert discord.utils.snowflake_time(iterator.before.id) <= moment


def audit_page(rig: Rig, first: int, count: int) -> dict[str, Any]:
    entries = [
        rig.payload(t.audit_log.AuditLogEntry, id=str(first - i)) for i in range(count)
    ]
    return {
        "audit_log_entries": entries,
        "users": [rig.payload(t.user.User)],
        "application_commands": [],
        "auto_moderation_rules": [],
        "guild_scheduled_events": [],
        "integrations": [],
        "threads": [],
        "webhooks": [],
    }


def test_audit_log_iterator_pages_and_cursors(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_audit_logs", audit_page(rig, 500, 100), audit_page(rig, 400, 20))

    entries = rig.run(
        AuditLogIterator(
            rig.guild, limit=None, user_id=3, action_type=discord.AuditLogAction.kick
        ).flatten()
    )

    assert len(entries) == 120
    first, second = rig.http.get_audit_logs.call_args_list
    assert first.args == (rig.guild.id,)
    assert first.kwargs["user_id"] == 3
    assert first.kwargs["before"] is None
    assert second.kwargs["before"] == 401


def test_audit_log_iterator_after_only_walks_forward(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_audit_logs", audit_page(rig, 500, 100), audit_page(rig, 400, 1))
    iterator = AuditLogIterator(rig.guild, limit=150, after=discord.Object(id=1))

    assert len(rig.run(iterator.flatten())) == 101
    first, second = rig.http.get_audit_logs.call_args_list
    assert first.kwargs["after"] == 1
    assert second.kwargs["after"] == 401
    assert second.kwargs["before"] is None


def test_audit_log_iterator_with_nothing_to_retrieve(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_audit_logs", {"audit_log_entries": [], "users": []})
    assert rig.run(AuditLogIterator(rig.guild, limit=0).flatten()) == []
    rig.http.get_audit_logs.assert_not_called()
    assert rig.run(AuditLogIterator(rig.guild, limit=5).flatten()) == []


def guild_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [
        rig.payload(t.guild.Guild, id=str(first + i), unavailable=False)
        for i in range(count)
    ]


def make_bot(rig: Rig) -> Any:
    return SimpleNamespace(
        _connection=rig.state, http=rig.http, max_concurrency=None, shard_count=None
    )


def test_guild_iterator_after_strategy(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_guilds", guild_payloads(rig, 200, 2))

    iterator = GuildIterator(
        make_bot(rig), limit=2, after=discord.Object(id=100), with_counts=False
    )
    guilds = rig.run(iterator.flatten())

    assert ids(guilds) == [200, 201]
    assert rig.http.get_guilds.call_args.args == (2,)
    assert rig.http.get_guilds.call_args.kwargs == {"after": 100, "with_counts": False}


def test_guild_iterator_before_and_after_filters(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_guilds", guild_payloads(rig, 100, 3))
    iterator = GuildIterator(
        make_bot(rig),
        limit=10,
        before=discord.Object(id=300),
        after=discord.Object(id=100),
    )
    assert ids(rig.run(iterator.flatten())) == [101, 102]


def test_guild_iterator_error_without_a_shard_gets_a_hint(world: World) -> None:
    rig = Rig(world)
    response = SimpleNamespace(status=400, reason="Bad Request")
    rig.http.get_guilds.side_effect = HTTPException(response, {"message": "bad"})  # type: ignore[arg-type]
    iterator = GuildIterator(make_bot(rig), limit=1)
    with pytest.raises(HTTPException, match="shard") as info:
        rig.run(iterator.flatten())
    assert "all_shards=True" in info.value.text


def test_guild_iterator_error_with_a_shard_is_untouched(world: World) -> None:
    rig = Rig(world)
    response = SimpleNamespace(status=400, reason="Bad Request")
    error = HTTPException(response, {"message": "bad"})  # type: ignore[arg-type]
    rig.http.get_guilds.side_effect = error
    iterator = GuildIterator(make_bot(rig), limit=1, shard=0)
    iterator._max_concurrency = lambda: None  # type: ignore[method-assign]
    with pytest.raises(HTTPException) as info:
        rig.run(iterator.flatten())
    assert info.value is error
    assert "all_shards" not in info.value.text


def member_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [
        rig.payload(
            t.member.MemberWithUser,
            user=rig.payload(t.user.User, id=str(first + i)),
            roles=[],
        )
        for i in range(count)
    ]


def test_member_iterator_pages(world: World) -> None:
    rig = Rig(world)
    rig.pages(
        "get_members", member_payloads(rig, 1, 1000), member_payloads(rig, 2000, 2)
    )

    members = rig.run(MemberIterator(rig.guild, limit=None).flatten())

    assert len(members) == 1002
    first, second = rig.http.get_members.call_args_list
    assert first.args == (rig.guild.id, 1000, 0)
    assert second.args[2] == 1000


def test_member_iterator_stops_on_empty_and_zero_limit(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_members", [])
    assert rig.run(MemberIterator(rig.guild, limit=3).flatten()) == []
    assert rig.run(MemberIterator(rig.guild, limit=0).flatten()) == []
    assert rig.http.get_members.call_count == 1


def ban_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [
        {"reason": f"r{i}", "user": rig.payload(t.user.User, id=str(first + i))}
        for i in range(count)
    ]


def test_ban_iterator_pages(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_bans", ban_payloads(rig, 1, 3))

    bans = rig.run(
        BanIterator(rig.guild, limit=10, before=discord.Object(id=50)).flatten()
    )

    assert [b.reason for b in bans] == ["r2", "r1", "r0"]
    assert [b.user.id for b in bans] == [3, 2, 1]
    assert rig.http.get_bans.call_args.args == (rig.guild.id, 10, 50, None)


def test_ban_iterator_bounded_by_limit_and_empty(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_bans", ban_payloads(rig, 1, 1000), [])
    iterator = BanIterator(rig.guild, limit=None, after=discord.Object(id=0))
    assert len(rig.run(iterator.flatten())) == 1000
    first, second = rig.http.get_bans.call_args_list
    assert first.args == (rig.guild.id, 1000, None, 0)
    assert second.args == (rig.guild.id, 1000, None, 1000)
    rig.pages("get_bans", [])
    assert rig.run(BanIterator(rig.guild, limit=5).flatten()) == []
    assert rig.run(BanIterator(rig.guild, limit=0).flatten()) == []


def thread_page(rig: Rig, first: int, count: int, more: bool) -> dict[str, Any]:
    threads = [
        rig.payload(
            t.threads.Thread,
            id=str(first + i),
            guild_id=str(rig.guild.id),
            parent_id=str(rig.channel.id),
        )
        for i in range(count)
    ]
    return {"threads": threads, "members": [], "has_more": more}


@pytest.mark.parametrize(
    ("joined", "private", "route"),
    [
        (False, False, "get_public_archived_threads"),
        (False, True, "get_private_archived_threads"),
        (True, True, "get_joined_private_archived_threads"),
    ],
)
def test_archived_thread_iterator_routes_and_cursors(
    world: World, joined: bool, private: bool, route: str
) -> None:
    rig = Rig(world)
    first_page = thread_page(rig, 10, 2, True)
    rig.pages(route, first_page, thread_page(rig, 20, 1, False))

    threads = rig.run(
        ArchivedThreadIterator(
            rig.channel.id, rig.guild, limit=None, joined=joined, private=private
        ).flatten()
    )

    assert len(threads) == 3
    first, second = getattr(rig.http, route).call_args_list
    assert first.args == (rig.channel.id,)
    assert first.kwargs == {"before": None, "limit": 50}
    last = first_page["threads"][-1]
    if joined:
        assert second.kwargs["before"] == last["id"]
    else:
        assert second.kwargs["before"] == last["thread_metadata"]["archive_timestamp"]


def test_archived_thread_iterator_limit_and_before_forms(world: World) -> None:
    rig = Rig(world)
    moment = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    public = ArchivedThreadIterator(
        1, rig.guild, limit=1, joined=False, private=False, before=moment
    )
    assert public.before == moment.isoformat()
    joined = ArchivedThreadIterator(
        1, rig.guild, limit=1, joined=True, private=True, before=moment
    )
    assert joined.before == str(discord.utils.time_snowflake(moment, high=False))
    from_object = ArchivedThreadIterator(
        1, rig.guild, limit=1, joined=True, private=True, before=discord.Object(id=5)
    )
    assert from_object.before == "5"
    snowflake = ArchivedThreadIterator(
        1, rig.guild, limit=1, joined=False, private=True, before=discord.Object(id=5)
    )
    assert snowflake.before == discord.utils.snowflake_time(5).isoformat()
    with pytest.raises(ValueError, match="joined public"):
        ArchivedThreadIterator(1, rig.guild, limit=1, joined=True, private=False)


def subscriber_payload(rig: Rig, user_id: int, with_member: bool) -> dict[str, Any]:
    payload = {
        "guild_scheduled_event_id": "1",
        "user_id": str(user_id),
        "user": rig.payload(t.user.User, id=str(user_id)),
    }
    if with_member:
        payload["member"] = rig.payload(t.member.Member, roles=[])
    return payload


async def fetch_event(rig: Rig) -> Any:
    rig.respond(
        "get_scheduled_event",
        rig.payload(
            t.scheduled_events.ScheduledEvent,
            guild_id=str(rig.guild.id),
            creator_id=None,
        ),
    )
    return await rig.guild.fetch_scheduled_event(1)


def test_archived_thread_iterator_respects_limit(world: World) -> None:
    rig = Rig(world)
    rig.pages("get_public_archived_threads", thread_page(rig, 10, 2, True))
    threads = rig.run(
        ArchivedThreadIterator(
            rig.channel.id, rig.guild, limit=2, joined=False, private=False
        ).flatten()
    )
    assert len(threads) == 2
    assert rig.http.get_public_archived_threads.call_count == 1
    assert rig.http.get_public_archived_threads.call_args.kwargs["limit"] == 2


def test_subscribers_from_the_api_with_members(world: World) -> None:
    rig = Rig(world)
    event = rig.run(fetch_event(rig))
    rig.pages(
        "get_scheduled_event_users",
        [subscriber_payload(rig, 5, True), subscriber_payload(rig, 6, True)],
    )

    subscribers = rig.run(
        ScheduledEventSubscribersIterator(
            event, limit=None, with_member=True, before=discord.Object(id=99)
        ).flatten()
    )

    assert all(isinstance(s, discord.Member) for s in subscribers)
    assert len(subscribers) == 2
    kwargs = rig.http.get_scheduled_event_users.call_args.kwargs
    assert kwargs["guild_id"] == rig.guild.id
    assert kwargs["event_id"] == event.id
    assert kwargs["limit"] == 100
    assert kwargs["with_member"] is True
    assert kwargs["before"] == 99


def test_subscribers_from_the_api_as_users_page_twice(world: World) -> None:
    rig = Rig(world)
    event = rig.run(fetch_event(rig))
    full = [subscriber_payload(rig, 1000 + i, False) for i in range(100)]
    rig.pages("get_scheduled_event_users", full, [subscriber_payload(rig, 5000, False)])

    subscribers = rig.run(
        ScheduledEventSubscribersIterator(event, limit=None).flatten()
    )

    assert len(subscribers) == 101
    assert all(isinstance(s, discord.User) for s in subscribers)
    first, second = rig.http.get_scheduled_event_users.call_args_list
    assert first.kwargs["after"] is None
    assert second.kwargs["after"] == 1099


def test_subscribers_from_the_cache(world: World) -> None:
    rig = Rig(world)
    event = rig.run(fetch_event(rig))
    member = world.member
    rig.run(rig.guild._add_member(member))
    event._subscriber_ids = {member.id, member.id + 1, member.id + 2}
    rig.state._cache_users = True
    rig.run(rig.state.store_user(world.payload(t.user.User, id=str(member.id))))

    as_members = rig.run(
        ScheduledEventSubscribersIterator(
            event, limit=None, with_member=True, use_cache=True
        ).flatten()
    )
    assert as_members == [member]

    capped = rig.run(
        ScheduledEventSubscribersIterator(event, limit=1, use_cache=True).flatten()
    )
    assert [s.id for s in capped] == [member.id]

    bounded = rig.run(
        ScheduledEventSubscribersIterator(
            event,
            limit=None,
            use_cache=True,
            before=discord.Object(id=member.id),
        ).flatten()
    )
    assert bounded == []
    after = rig.run(
        ScheduledEventSubscribersIterator(
            event,
            limit=None,
            use_cache=True,
            after=discord.Object(id=member.id),
        ).flatten()
    )
    assert after == []
    rig.http.get_scheduled_event_users.assert_not_called()


def entitlement_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [
        rig.payload(t.monetization.Entitlement, id=str(first - i)) for i in range(count)
    ]


def test_entitlement_iterator_before_strategy(world: World) -> None:
    rig = Rig(world)
    rig.state.application_id = 77
    rig.pages("list_entitlements", entitlement_payloads(rig, 50, 3))

    entitlements = rig.run(
        EntitlementIterator(
            rig.state,
            user_id=4,
            sku_ids=[9],
            limit=None,
            guild_id=5,
            exclude_ended=True,
        ).flatten()
    )

    assert [e.id for e in entitlements] == [50, 49, 48]
    assert rig.http.list_entitlements.call_args.args == (77,)
    assert rig.http.list_entitlements.call_args.kwargs == {
        "before": None,
        "limit": 100,
        "user_id": 4,
        "guild_id": 5,
        "sku_ids": [9],
        "exclude_ended": True,
    }


def test_entitlement_iterator_after_strategy_and_range_filter(world: World) -> None:
    rig = Rig(world)
    rig.state.application_id = 77
    rig.pages("list_entitlements", entitlement_payloads(rig, 50, 3))
    forward = rig.run(
        EntitlementIterator(
            rig.state, after=discord.Object(id=10), limit=None
        ).flatten()
    )
    assert len(forward) == 3
    assert rig.http.list_entitlements.call_args.kwargs["after"] == 10

    rig.pages("list_entitlements", entitlement_payloads(rig, 50, 3))
    ranged = rig.run(
        EntitlementIterator(
            rig.state,
            before=discord.Object(id=100),
            after=discord.Object(id=49),
            limit=5,
        ).flatten()
    )
    assert [e.id for e in ranged] == [50]
    assert rig.run(EntitlementIterator(rig.state, limit=0).flatten()) == []


def subscription_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [
        rig.payload(t.monetization.Subscription, id=str(first - i))
        for i in range(count)
    ]


def test_subscription_iterator_strategies(world: World) -> None:
    rig = Rig(world)
    rig.pages("list_sku_subscriptions", subscription_payloads(rig, 50, 3))
    subs = rig.run(SubscriptionIterator(rig.state, 8, limit=None, user_id=2).flatten())
    assert [s.id for s in subs] == [50, 49, 48]
    assert rig.http.list_sku_subscriptions.call_args.args == (8,)
    assert rig.http.list_sku_subscriptions.call_args.kwargs == {
        "limit": 100,
        "before": None,
        "user_id": 2,
    }

    rig.pages("list_sku_subscriptions", subscription_payloads(rig, 50, 3))
    forward = rig.run(
        SubscriptionIterator(
            rig.state, 8, limit=None, after=discord.Object(id=1)
        ).flatten()
    )
    assert len(forward) == 3
    assert rig.http.list_sku_subscriptions.call_args.kwargs["after"] == 1

    rig.pages("list_sku_subscriptions", subscription_payloads(rig, 50, 3))
    ranged = rig.run(
        SubscriptionIterator(
            rig.state,
            8,
            limit=None,
            before=discord.Object(id=99),
            after=discord.Object(id=49),
        ).flatten()
    )
    assert [s.id for s in ranged] == [50]
    assert rig.run(SubscriptionIterator(rig.state, 8, limit=0).flatten()) == []


def pin_payload(rig: Rig, message_id: int) -> dict[str, Any]:
    return {
        "pinned_at": f"2024-01-0{message_id}T00:00:00+00:00",
        "message": rig.message_payload(message_id),
    }


def test_message_pin_iterator_pages_and_awaits_to_messages(world: World) -> None:
    rig = Rig(world)
    rig.pages(
        "pins_from",
        {"items": [pin_payload(rig, 1), pin_payload(rig, 2)], "has_more": True},
        {"items": [pin_payload(rig, 3)], "has_more": False},
    )

    pins = rig.run(MessagePinIterator(rig.channel, limit=None).flatten())

    assert [p.message.id for p in pins] == [1, 2, 3]
    first, second = rig.http.pins_from.call_args_list
    assert first.args == (rig.channel.id,)
    assert first.kwargs == {"before": None, "limit": 50}
    assert second.kwargs["before"] == "2024-01-02T00:00:00+00:00"

    rig.pages("pins_from", {"items": [pin_payload(rig, 4)], "has_more": False})
    with pytest.warns(DeprecationWarning, match="pins"):
        messages = rig.run(MessagePinIterator(rig.channel, limit=5))
    assert [m.id for m in messages] == [4]


def test_message_pin_iterator_limit_and_before(world: World) -> None:
    rig = Rig(world)
    rig.pages(
        "pins_from",
        {"items": [pin_payload(rig, 1), pin_payload(rig, 2)], "has_more": True},
    )
    moment = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    iterator = MessagePinIterator(rig.channel, limit=2, before=moment)
    assert iterator.before == moment.isoformat()
    assert len(rig.run(iterator.flatten())) == 2
    assert rig.http.pins_from.call_args.kwargs == {
        "before": moment.isoformat(),
        "limit": 2,
    }
    from_object = MessagePinIterator(rig.channel, limit=1, before=discord.Object(id=5))
    assert from_object.before == discord.utils.snowflake_time(5).isoformat()


def test_message_pin_iterator_without_a_real_channel(world: World) -> None:
    rig = Rig(world)
    iterator = MessagePinIterator(rig.channel, limit=1)
    with pytest.raises(RuntimeError, match="Channel is None"):
        rig.run(iterator.create_pin(pin_payload(rig, 1)))
    iterator.channel = discord.Object(id=1)
    with pytest.raises(RuntimeError, match="Object channel"):
        rig.run(iterator.create_pin(pin_payload(rig, 1)))


def user_payloads(rig: Rig, first: int, count: int) -> list[Any]:
    return [rig.payload(t.user.User, id=str(first + i)) for i in range(count)]


def test_vote_iterator_resolves_cached_members_and_users(world: World) -> None:
    rig = Rig(world)
    message = world.message
    rig.run(rig.guild._add_member(world.member))
    answer = SimpleNamespace(id=3)
    users = [
        rig.payload(t.user.User, id=str(world.member.id)),
        rig.payload(t.user.User, id=str(world.member.id + 1)),
    ]
    rig.pages("get_answer_voters", {"users": users})

    voters = rig.run(VoteIterator(message, answer, limit=10).flatten())  # type: ignore[arg-type]

    assert voters[1] is world.member
    assert isinstance(voters[0], discord.User)
    assert not isinstance(voters[0], discord.Member)
    assert rig.http.get_answer_voters.call_args.args == (
        message.channel.id,
        message.id,
        3,
        10,
    )
    assert rig.http.get_answer_voters.call_args.kwargs == {"after": None}


def test_vote_iterator_without_a_guild_makes_users(world: World) -> None:
    rig = Rig(world)
    message = SimpleNamespace(
        _state=rig.state,
        guild=None,
        channel=SimpleNamespace(id=5),
        id=6,
    )
    rig.pages("get_answer_voters", {"users": user_payloads(rig, 1, 2)}, {"users": []})

    voters = rig.run(
        VoteIterator(
            message, SimpleNamespace(id=1), limit=200, after=discord.Object(id=0)
        ).flatten()  # type: ignore[arg-type]
    )

    assert [v.id for v in voters] == [2, 1]
    assert all(isinstance(v, discord.User) for v in voters)
    assert rig.http.get_answer_voters.call_args_list[0].kwargs == {"after": 0}


def test_reaction_iterator_makes_users_without_a_guild(world: World) -> None:
    rig = Rig(world)
    message = SimpleNamespace(
        _state=rig.state, guild=None, channel=SimpleNamespace(id=5), id=6
    )
    rig.pages("get_reaction_users", user_payloads(rig, 1, 2))

    voters = rig.run(
        ReactionIterator(message, "x", limit=5, type=1).flatten()  # type: ignore[arg-type]
    )

    assert [v.id for v in voters] == [2, 1]
    assert rig.http.get_reaction_users.call_args.kwargs == {"after": None, "type": 1}
