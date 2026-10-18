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

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.errors import ClientException, InvalidArgument
from discord.utils import MISSING
from tests.core.rig import (
    PNG,
    Case,
    Rig,
    check_type,
    execute,
    guild,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World

IMG = "data:image/png;base64,iVBORw0KGgo="


def set_features(*features: str) -> Any:
    def setup(r: Rig) -> None:
        r.guild.features = list(features)

    return setup


def fields(**expected: Any) -> Any:
    return lambda r: expected


def edit(
    case_id: str, kwargs: Any, expected: dict[str, Any], features: tuple[str, ...] = ()
) -> Case:
    return Case(
        case_id,
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=kwargs if callable(kwargs) else (lambda r: kwargs),
        called_with=lambda r: ((r.guild.id,), {"reason": MISSING, **expected}),
        check=check_type(discord.Guild),
        setup=set_features(*features),
    )


def edit_raises(case_id: str, kwargs: Any, message: str) -> Case:
    return Case(
        case_id,
        guild,
        "edit",
        "edit_guild",
        kwargs=kwargs if callable(kwargs) else (lambda r: kwargs),
        raises=(InvalidArgument, message),
        setup=set_features(),
    )


EDIT_CASES = [
    edit("nothing", {}, {}),
    edit(
        "plain_fields",
        {"name": "n", "description": None, "preferred_locale": "fr", "afk_timeout": 60},
        {
            "name": "n",
            "description": None,
            "preferred_locale": "fr",
            "afk_timeout": 60,
        },
    ),
    edit(
        "assets",
        {"icon": PNG, "banner": PNG, "splash": PNG, "discovery_splash": PNG},
        {"icon": IMG, "banner": IMG, "splash": IMG, "discovery_splash": IMG},
    ),
    edit(
        "assets_cleared",
        {"icon": None, "banner": None, "splash": None, "discovery_splash": None},
        {"icon": None, "banner": None, "splash": None, "discovery_splash": None},
    ),
    edit(
        "enums",
        {
            "default_notifications": discord.NotificationLevel.only_mentions,
            "verification_level": discord.VerificationLevel.high,
            "explicit_content_filter": discord.ContentFilter.all_members,
            "system_channel_flags": discord.SystemChannelFlags(join_notifications=True),
            "premium_progress_bar_enabled": True,
        },
        {
            "default_message_notifications": 1,
            "verification_level": 3,
            "explicit_content_filter": 2,
            "system_channel_flags": discord.SystemChannelFlags(
                join_notifications=True
            ).value,
            "premium_progress_bar_enabled": True,
        },
    ),
    Case(
        "channels",
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=lambda r: {
            "afk_channel": r.channel,
            "system_channel": r.channel,
            "rules_channel": None,
            "public_updates_channel": r.channel,
        },
        called_with=lambda r: (
            (r.guild.id,),
            {
                "reason": MISSING,
                "afk_channel_id": r.channel.id,
                "system_channel_id": r.channel.id,
                "rules_channel_id": None,
                "public_updates_channel_id": r.channel.id,
            },
        ),
        setup=set_features(),
    ),
    Case(
        "channels_cleared",
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=lambda r: {
            "afk_channel": None,
            "system_channel": None,
            "public_updates_channel": None,
        },
        called_with=lambda r: (
            (r.guild.id,),
            {
                "reason": MISSING,
                "afk_channel_id": None,
                "system_channel_id": None,
                "public_updates_channel_id": None,
            },
        ),
        setup=set_features(),
    ),
    Case(
        "community_on",
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=lambda r: {
            "community": True,
            "rules_channel": r.channel,
            "public_updates_channel": r.channel,
            "reason": "r",
        },
        called_with=lambda r: (
            (r.guild.id,),
            {
                "reason": "r",
                "rules_channel_id": r.channel.id,
                "public_updates_channel_id": r.channel.id,
                "features": ["COMMUNITY"],
            },
        ),
        setup=set_features(),
    ),
    Case(
        "community_on_already",
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=lambda r: {
            "community": True,
            "rules_channel": r.channel,
            "public_updates_channel": r.channel,
        },
        called_with=lambda r: (
            (r.guild.id,),
            {
                "reason": MISSING,
                "rules_channel_id": r.channel.id,
                "public_updates_channel_id": r.channel.id,
            },
        ),
        setup=set_features("COMMUNITY"),
    ),
    Case(
        "community_off",
        guild,
        "edit",
        "edit_guild",
        one(t.guild.Guild),
        kwargs=lambda r: {
            "community": False,
            "rules_channel": r.channel,
            "public_updates_channel": r.channel,
        },
        called_with=lambda r: (
            (r.guild.id,),
            {
                "reason": MISSING,
                "rules_channel_id": None,
                "public_updates_channel_id": None,
                "features": [],
            },
        ),
        setup=set_features("COMMUNITY"),
    ),
    edit_raises("community_needs_channels", {"community": True}, "community field"),
    edit_raises("bad_notifications", {"default_notifications": 1}, "NotificationLevel"),
    edit_raises("bad_verification", {"verification_level": 1}, "VerificationLevel"),
    edit_raises("bad_content_filter", {"explicit_content_filter": 1}, "ContentFilter"),
    edit_raises("bad_flags", {"system_channel_flags": 1}, "SystemChannelFlags"),
    edit(
        "invites_disabled_on",
        {"disable_invites": True},
        {"features": ["INVITES_DISABLED"]},
    ),
    edit(
        "invites_disabled_on_already",
        {"disable_invites": True},
        {},
        features=("INVITES_DISABLED",),
    ),
    edit(
        "invites_disabled_off",
        {"disable_invites": False},
        {"features": []},
        features=("INVITES_DISABLED",),
    ),
    edit("invites_disabled_off_already", {"disable_invites": False}, {}),
    edit("discoverable_on", {"discoverable": True}, {"features": ["DISCOVERABLE"]}),
    edit(
        "discoverable_on_already",
        {"discoverable": True},
        {},
        features=("DISCOVERABLE",),
    ),
    edit(
        "discoverable_off",
        {"discoverable": False},
        {"features": []},
        features=("DISCOVERABLE",),
    ),
    edit("discoverable_off_already", {"discoverable": False}, {}),
    edit(
        "raid_alerts_off",
        {"disable_raid_alerts": True},
        {"features": ["RAID_ALERTS_DISABLED"]},
    ),
    edit(
        "raid_alerts_off_already",
        {"disable_raid_alerts": True},
        {},
        features=("RAID_ALERTS_DISABLED",),
    ),
    edit(
        "raid_alerts_on",
        {"disable_raid_alerts": False},
        {"features": []},
        features=("RAID_ALERTS_DISABLED",),
    ),
    edit("raid_alerts_on_already", {"disable_raid_alerts": False}, {}),
    edit(
        "activity_feed_on",
        {"enable_activity_feed": True},
        {"features": ["ACTIVITY_FEED_ENABLED_BY_USER"]},
        features=("ACTIVITY_FEED_DISABLED_BY_USER",),
    ),
    edit(
        "activity_feed_on_already",
        {"enable_activity_feed": True},
        {},
        features=("ACTIVITY_FEED_ENABLED_BY_USER",),
    ),
    edit(
        "activity_feed_off",
        {"enable_activity_feed": False},
        {"features": ["ACTIVITY_FEED_DISABLED_BY_USER"]},
        features=("ACTIVITY_FEED_ENABLED_BY_USER",),
    ),
    edit(
        "activity_feed_off_already",
        {"enable_activity_feed": False},
        {},
        features=("ACTIVITY_FEED_DISABLED_BY_USER",),
    ),
]


@pytest.mark.parametrize("case", EDIT_CASES, ids=lambda c: c.id)
def test_guild_edit(world: World, case: Case) -> None:
    execute(Rig(world), case)


def welcome_channel(r: Rig) -> discord.WelcomeScreenChannel:
    return discord.WelcomeScreenChannel(r.channel, "start here", "\N{WAVING HAND SIGN}")


def _welcome(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.WelcomeScreen)
    args, kwargs = r.http.edit_welcome_screen.call_args
    assert args[0] == r.guild.id
    assert args[1]["description"] == "d"
    assert args[1]["welcome_channels"] == [welcome_channel(r).to_dict()]
    assert kwargs == {"reason": "r"}


def _events(r: Rig, result: Any) -> None:
    assert len(result) == 2
    assert all(isinstance(e, discord.ScheduledEvent) for e in result)
    assert {e.id for e in r.guild.scheduled_events} == {e.id for e in result}


def _event(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.ScheduledEvent)
    assert r.http.get_scheduled_event.call_args.kwargs == {
        "guild_id": r.guild.id,
        "event_id": 11,
        "with_user_count": True,
    }
    assert r.run(r.guild.get_scheduled_event(result.id)) is result


def _rule(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.AutoModRule)
    _, payload = r.http.create_auto_moderation_rule.call_args.args
    assert payload["name"] == "no spam"
    assert payload["event_type"] == 1
    assert payload["trigger_type"] == 1
    assert payload["enabled"] is True
    assert payload["exempt_roles"] == [1]
    assert payload["exempt_channels"] == [r.channel.id]
    assert r.http.create_auto_moderation_rule.call_args.kwargs == {"reason": "r"}


OTHER_CASES = [
    Case(
        "edit_welcome_screen",
        guild,
        "edit_welcome_screen",
        "edit_welcome_screen",
        one(t.welcome_screen.WelcomeScreen),
        kwargs=lambda r: {
            "welcome_channels": [welcome_channel(r)],
            "description": "d",
            "reason": "r",
        },
        check=_welcome,
    ),
    Case(
        "edit_welcome_screen_bad_channel",
        guild,
        "edit_welcome_screen",
        "edit_welcome_screen",
        kwargs=lambda r: {"welcome_channels": [r.channel]},
        raises=(TypeError, "WelcomeScreenChannel"),
    ),
    Case(
        "fetch_scheduled_events",
        guild,
        "fetch_scheduled_events",
        "get_scheduled_events",
        lambda r: [
            r.payload(
                t.scheduled_events.ScheduledEvent,
                guild_id=str(r.guild.id),
                creator_id=None,
            ),
            r.payload(
                t.scheduled_events.ScheduledEvent,
                id="9999",
                guild_id=str(r.guild.id),
                creator_id=str(r.world.member.id),
                creator=r.payload(t.user.User, id=str(r.world.member.id)),
            ),
        ],
        kwargs=lambda r: {"with_user_count": False},
        called_with=lambda r: ((r.guild.id,), {"with_user_count": False}),
        check=_events,
    ),
    Case(
        "fetch_scheduled_event",
        guild,
        "fetch_scheduled_event",
        "get_scheduled_event",
        one(
            t.scheduled_events.ScheduledEvent,
            creator_id=None,
        ),
        args=lambda r: (11,),
        check=_event,
    ),
    Case(
        "fetch_scheduled_event_creator",
        guild,
        "fetch_scheduled_event",
        "get_scheduled_event",
        lambda r: r.payload(
            t.scheduled_events.ScheduledEvent,
            creator_id=str(r.world.member.id),
            creator=r.payload(t.user.User, id=str(r.world.member.id)),
        ),
        args=lambda r: (11,),
        check=check_type(discord.ScheduledEvent),
    ),
    Case(
        "create_scheduled_event_options",
        guild,
        "create_scheduled_event",
        "create_scheduled_event",
        one(t.scheduled_events.ScheduledEvent, creator_id=None),
        kwargs=lambda r: {
            "name": "party",
            "description": "fun",
            "start_time": discord.utils.utcnow(),
            "location": "somewhere",
            "image": PNG,
            "reason": "r",
        },
        kwargs_include=lambda r: {
            "name": "party",
            "description": "fun",
            "image": IMG,
            "reason": "r",
            "entity_type": 3,
            "entity_metadata": {"location": "somewhere"},
        },
        check=check_type(discord.ScheduledEvent),
    ),
    Case(
        "create_auto_moderation_rule",
        guild,
        "create_auto_moderation_rule",
        "create_auto_moderation_rule",
        one(t.automod.AutoModRule),
        kwargs=lambda r: {
            "name": "no spam",
            "event_type": discord.AutoModEventType.message_send,
            "trigger_type": discord.AutoModTriggerType.keyword,
            "trigger_metadata": discord.AutoModTriggerMetadata(keyword_filter=["x"]),
            "actions": [
                discord.AutoModAction(
                    discord.AutoModActionType.block_message,
                    discord.AutoModActionMetadata(),
                )
            ],
            "enabled": True,
            "exempt_roles": [discord.Object(id=1)],
            "exempt_channels": [r.channel],
            "reason": "r",
        },
        check=_rule,
    ),
    Case(
        "create_test_entitlement",
        guild,
        "create_test_entitlement",
        "create_test_entitlement",
        one(t.monetization.Entitlement),
        args=lambda r: (discord.Object(id=31),),
        setup=lambda r: setattr(r.state, "application_id", 1234),
        called_with=lambda r: (
            (1234, {"sku_id": 31, "owner_id": r.guild.id, "owner_type": 1}),
            {},
        ),
        check=check_type(discord.Entitlement),
    ),
    Case(
        "create_test_entitlement_without_application",
        guild,
        "create_test_entitlement",
        "create_test_entitlement",
        args=lambda r: (discord.Object(id=31),),
        setup=lambda r: setattr(r.state, "application_id", None),
        raises=(ClientException, "application ID"),
    ),
]


@pytest.mark.parametrize("case", OTHER_CASES, ids=lambda c: c.id)
def test_guild_remote_calls_rest(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_query_members_validates_before_asking_the_gateway(world: World) -> None:
    rig = Rig(world)
    rig.state.query_members = AsyncMock(return_value=["member"])
    guild_ = rig.guild
    rig.state._intents = discord.Intents.default()

    def call(**kwargs: Any) -> Any:
        return rig.run(guild_.query_members(**kwargs))

    with pytest.raises(ClientException, match="presences"):
        call(query="a", presences=True)
    with pytest.raises(ValueError, match="between 1 and 100"):
        call(query="a", limit=500)
    with pytest.raises(ValueError, match="between 1 and 100"):
        call(user_ids=[1], limit=0)
    with pytest.raises(ValueError, match="Must pass query or user_ids"):
        call()
    with pytest.raises(ValueError, match="Cannot pass both"):
        call(query="a", user_ids=[1])
    with pytest.raises(ValueError, match="at least 1 value"):
        call(user_ids=[], limit=1)
    rig.state.query_members.assert_not_called()

    assert call(query="a") == ["member"]
    assert call(user_ids=[1, 2]) == ["member"]
    assert call(limit=None, query="") == ["member"]
    assert call(limit=0) == ["member"]
    first, second, third, fourth = rig.state.query_members.await_args_list
    assert first.kwargs["query"] == "a"
    assert first.kwargs["limit"] == 5
    assert second.kwargs["user_ids"] == [1, 2]
    assert third.kwargs["limit"] == 0
    assert third.kwargs["query"] == ""
    assert fourth.kwargs["query"] == ""
    assert fourth.kwargs["limit"] == 0


def test_query_members_with_presences_intent(world: World) -> None:
    rig = Rig(world)
    rig.state.query_members = AsyncMock(return_value=[])
    rig.state._intents = discord.Intents.all()

    assert rig.run(rig.guild.query_members("a", presences=True)) == []
    assert rig.state.query_members.await_args.kwargs["presences"] is True


def test_member_listing_needs_the_members_intent(world: World) -> None:
    rig = Rig(world)
    rig.state._intents = discord.Intents.none()
    with pytest.raises(ClientException, match=r"Intents\.members"):
        rig.guild.fetch_members()
    with pytest.raises(ClientException, match=r"Intents\.members"):
        rig.run(rig.guild.chunk())

    rig.state._intents = discord.Intents(members=True)
    iterator = rig.guild.fetch_members(limit=5)
    assert iterator.limit == 5
    rig.state.chunk_guild = AsyncMock(return_value=["chunk"])
    assert rig.run(rig.guild.chunk(cache=False)) == ["chunk"]
    rig.state.chunk_guild.assert_awaited_once_with(rig.guild, cache=False)


def test_chunk_of_an_evicted_guild_is_none(world: World) -> None:
    rig = Rig(world)
    rig.state._intents = discord.Intents(members=True)
    rig.run(rig.state._guilds.pop(rig.guild.id))
    assert rig.run(rig.guild.chunk()) is None


def test_iterator_factories(world: World) -> None:
    rig = Rig(world)
    bans = rig.guild.bans(limit=3)
    assert isinstance(bans, discord.iterators.BanIterator)
    logs = rig.guild.audit_logs(
        limit=4,
        user=discord.Object(id=5),
        action=discord.AuditLogAction.kick,
    )
    assert isinstance(logs, discord.iterators.AuditLogIterator)
    assert logs.user_id == 5
    assert logs.action_type == discord.AuditLogAction.kick.value
    plain = rig.guild.audit_logs()
    assert plain.user_id is None
    assert plain.action_type is None
    entitlements = rig.guild.entitlements(
        skus=[discord.Object(id=7)], limit=2, exclude_ended=True
    )
    assert isinstance(entitlements, discord.iterators.EntitlementIterator)
    assert entitlements.sku_ids == [7]
    assert entitlements.guild_id == rig.guild.id
    assert rig.guild.entitlements().sku_ids is None
