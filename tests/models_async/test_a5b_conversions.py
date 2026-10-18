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

from typing import TYPE_CHECKING, Any

import pytest

from discord import types as t
from discord.audit_logs import AuditLogEntry
from discord.channel import PartialMessageable
from discord.enums import AuditLogAction
from discord.errors import SyncCacheAccessError
from discord.guild import PartialGuild
from discord.http import HTTPClient
from discord.lobby import Lobby, LobbyMember
from discord.member import Member
from discord.monetization import Subscription
from discord.object import Object
from discord.onboarding import Onboarding, PromptOption
from discord.role import Role
from discord.template import Template
from discord.user import User
from discord.webhook.async_ import Webhook
from discord.webhook.sync import SyncWebhook
from discord.welcome_screen import WelcomeScreen, WelcomeScreenChannel
from tests.models.context import World
from tests.payloads.overrides import CHANNEL_ID
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

CHAN = int(CHANNEL_ID)
USER_ID = 8100
ROLE_ID = 8200
OTHER_ID = 8300


@pytest.fixture(params=["memory", "redis"])
def remote_world(
    request: pytest.FixtureRequest, loop: asyncio.AbstractEventLoop
) -> World:
    state = build_state(loop, HTTPClient(loop=loop), request.param)
    return World(state)


@pytest.fixture
def redis_world(loop: asyncio.AbstractEventLoop) -> World:
    return World(build_state(loop, HTTPClient(loop=loop), "redis"))


def add_member(world: World, user_id: int = USER_ID) -> Member:
    payload = world.payload(
        t.member.MemberWithUser,
        roles=[],
        user={**world.payload(t.user.User), "id": str(user_id)},
    )
    payload.pop("communication_disabled_until", None)
    member = Member(data=payload, guild=world.guild, state=world.state)
    world.run(world.guild._add_member(member))
    return member


def add_role(world: World, role_id: int = ROLE_ID) -> Role:
    payload = world.payload(t.role.Role, id=str(role_id), position=1)
    payload.pop("tags", None)
    role = Role(guild=world.guild, state=world.state, data=payload)
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def make_entry(
    world: World,
    action: AuditLogAction,
    *,
    users: dict[int, User] | None = None,
    **fields: Any,
) -> AuditLogEntry:
    payload = world.payload(
        t.audit_log.AuditLogEntry,
        action_type=action.value,
        id="9001",
        **fields,
    )
    for key in ("options", "changes", "target_id", "user_id"):
        if key not in fields:
            payload.pop(key, None)
    return AuditLogEntry(users=users or {}, data=payload, guild=world.guild)


class TestAuditLogEntryUser:
    def test_no_user(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.channel_update)
        assert entry.user_id is None
        assert entry.user is None
        assert world.run(entry.get_user()) is None

    def test_cached_member(self, world: World) -> None:
        member = add_member(world)
        entry = make_entry(world, AuditLogAction.channel_update, user_id=str(USER_ID))
        assert entry.user_id == USER_ID
        assert entry.user is member
        assert world.run(entry.get_user()) is member

    def test_falls_back_to_the_entry_users(self, world: World) -> None:
        user = User(
            state=world.state,
            data={**world.payload(t.user.User), "id": str(USER_ID)},
        )
        entry = make_entry(
            world,
            AuditLogAction.channel_update,
            users={USER_ID: user},
            user_id=str(USER_ID),
        )
        assert entry.user is user
        assert world.run(entry.get_user()) is user

    def test_uncached_user_is_none(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.kick, user_id=str(USER_ID))
        assert entry.user is None
        assert world.run(entry.get_user()) is None


class TestAuditLogEntryTarget:
    def test_no_target(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.channel_update)
        assert entry.target_id is None
        assert entry.target is None
        assert world.run(entry.get_target()) is None

    def test_cached_channel(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.channel_update, target_id=str(CHAN))
        assert entry.target_id == CHAN
        assert entry.target is world.channel
        assert world.run(entry.get_target()) is world.channel

    def test_uncached_channel_is_an_object(self, world: World) -> None:
        entry = make_entry(
            world, AuditLogAction.channel_update, target_id=str(OTHER_ID)
        )
        assert isinstance(entry.target, Object)
        assert entry.target.id == OTHER_ID
        assert world.run(entry.get_target()) == entry.target

    def test_role_and_member_targets(self, world: World) -> None:
        role = add_role(world)
        member = add_member(world)
        role_entry = make_entry(
            world, AuditLogAction.role_update, target_id=str(ROLE_ID)
        )
        user_entry = make_entry(world, AuditLogAction.kick, target_id=str(USER_ID))
        assert role_entry.target is role
        assert world.run(role_entry.get_target()) is role
        assert user_entry.target is member
        assert world.run(user_entry.get_target()) is member

    def test_unknown_member_target_is_none(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.kick, target_id=str(OTHER_ID))
        assert entry.target is None
        assert world.run(entry.get_target()) is None

    def test_guild_target(self, world: World) -> None:
        entry = make_entry(
            world, AuditLogAction.guild_update, target_id=str(world.guild.id)
        )
        assert entry.target is world.guild
        assert world.run(entry.get_target()) is world.guild

    def test_target_without_a_converter_is_an_object(self, world: World) -> None:
        entry = make_entry(
            world, AuditLogAction.webhook_create, target_id=str(OTHER_ID)
        )
        assert entry.target == Object(id=OTHER_ID)
        assert world.run(entry.get_target()) == Object(id=OTHER_ID)


class TestAuditLogEntryChanges:
    def changes(self, role: Any = None) -> list[dict[str, Any]]:
        return [
            {"key": "afk_channel_id", "old_value": None, "new_value": str(CHAN)},
            {"key": "rules_channel_id", "new_value": str(OTHER_ID)},
            {"key": "owner_id", "new_value": str(USER_ID)},
            {"key": "exempt_roles", "new_value": [str(ROLE_ID), str(OTHER_ID)]},
            {
                "key": "$add",
                "new_value": [{"id": str(ROLE_ID), "name": "added"}],
            },
            {
                "key": "permission_overwrites",
                "new_value": [
                    {"id": str(ROLE_ID), "type": 0, "allow": "1", "deny": "0"},
                    {"id": str(USER_ID), "type": 1, "allow": "0", "deny": "2"},
                    {"id": str(OTHER_ID), "type": 0, "allow": "0", "deny": "0"},
                ],
            },
        ]

    def test_uncached_values_are_objects(self, world: World) -> None:
        entry = make_entry(world, AuditLogAction.guild_update, changes=self.changes())
        after = entry.after
        assert after.rules_channel == Object(id=OTHER_ID)
        assert after.owner == Object(id=USER_ID)
        assert after.exempt_roles == [Object(id=ROLE_ID), Object(id=OTHER_ID)]
        assert [target.id for target, _ in after.overwrites] == [
            ROLE_ID,
            USER_ID,
            OTHER_ID,
        ]
        assert after.roles[0].name == "added"

    def test_sync_changes_resolve_from_the_cache(self, world: World) -> None:
        role = add_role(world)
        member = add_member(world)
        entry = make_entry(world, AuditLogAction.guild_update, changes=self.changes())
        after = entry.after
        assert after.afk_channel is world.channel
        assert after.owner is member
        assert after.exempt_roles == [role, Object(id=OTHER_ID)]
        assert after.roles == [role]
        assert [target for target, _ in after.overwrites] == [
            role,
            member,
            Object(id=OTHER_ID),
        ]
        assert entry.before.afk_channel is None

    def test_async_changes_match_the_sync_ones(self, world: World) -> None:
        add_role(world)
        add_member(world)
        sync_entry = make_entry(
            world, AuditLogAction.guild_update, changes=self.changes()
        )
        async_entry = make_entry(
            world, AuditLogAction.guild_update, changes=self.changes()
        )
        expected = dict(sync_entry.after)
        changes = world.run(async_entry.get_changes())
        assert dict(changes.after) == expected
        assert changes is async_entry.changes
        assert world.run(async_entry.get_changes()) is changes

    def test_invite_target_uses_the_resolved_channel(self, world: World) -> None:
        changes = [
            {"key": "channel_id", "new_value": str(CHAN)},
            {"key": "code", "new_value": "abc"},
            {"key": "max_age", "new_value": 60},
            {"key": "max_uses", "new_value": 1},
            {"key": "temporary", "new_value": False},
            {"key": "uses", "new_value": 0},
        ]
        entry = make_entry(
            world, AuditLogAction.invite_create, changes=changes, target_id="1"
        )
        assert entry.after.channel is world.channel
        assert entry.target.code == "abc"  # type: ignore[union-attr]
        assert world.run(entry.get_target()).code == "abc"  # type: ignore[union-attr]


class TestAuditLogEntryExtra:
    def test_member_move_channel(self, world: World) -> None:
        options = {"channel_id": str(CHAN), "count": "3"}
        entry = make_entry(world, AuditLogAction.member_move, options=options)
        assert entry.extra.count == 3  # type: ignore[union-attr]
        assert entry.extra.channel is world.channel  # type: ignore[union-attr]
        other = make_entry(world, AuditLogAction.member_move, options=options)
        assert world.run(other.get_extra()).channel is world.channel

    def test_uncached_channel_stays_an_object(self, world: World) -> None:
        options = {"channel_id": str(OTHER_ID), "count": "3"}
        entry = make_entry(world, AuditLogAction.message_delete, options=options)
        assert entry.extra.channel == Object(id=OTHER_ID)  # type: ignore[union-attr]
        assert world.run(entry.get_extra()).channel == Object(id=OTHER_ID)

    def test_overwrite_role_and_member(self, world: World) -> None:
        role = add_role(world)
        member = add_member(world)
        role_entry = make_entry(
            world,
            AuditLogAction.overwrite_create,
            options={"id": str(ROLE_ID), "type": "0", "role_name": "r"},
        )
        member_entry = make_entry(
            world,
            AuditLogAction.overwrite_create,
            options={"id": str(USER_ID), "type": "1"},
        )
        assert role_entry.extra is role
        assert member_entry.extra is member
        async_role = make_entry(
            world,
            AuditLogAction.overwrite_create,
            options={"id": str(ROLE_ID), "type": "0", "role_name": "r"},
        )
        assert world.run(async_role.get_extra()) is role

    def test_unknown_overwrite_role_keeps_its_name(self, world: World) -> None:
        entry = make_entry(
            world,
            AuditLogAction.overwrite_create,
            options={"id": str(OTHER_ID), "type": "0", "role_name": "gone"},
        )
        assert entry.extra.id == OTHER_ID  # type: ignore[union-attr]
        assert entry.extra.name == "gone"  # type: ignore[union-attr]


class TestAuditLogEntryRemote:
    def test_guild_handle_and_cached_guild(self, remote_world: World) -> None:
        entry = make_entry(remote_world, AuditLogAction.guild_update)
        if remote_world.state.cache.supports_sync:
            assert entry.guild is remote_world.guild
        else:
            assert isinstance(entry.guild, PartialGuild)
        assert entry.guild.id == remote_world.guild.id

    def test_sync_accessors_raise_on_a_remote_backend(self, redis_world: World) -> None:
        entry = make_entry(
            redis_world,
            AuditLogAction.channel_update,
            user_id=str(USER_ID),
            target_id=str(CHAN),
            changes=[{"key": "afk_channel_id", "new_value": str(CHAN)}],
        )
        with pytest.raises(SyncCacheAccessError):
            _ = entry.user
        with pytest.raises(SyncCacheAccessError):
            _ = entry.target
        with pytest.raises(SyncCacheAccessError):
            _ = entry.changes

    def test_async_accessors_work_on_a_remote_backend(self, redis_world: World) -> None:
        member = add_member(redis_world)
        entry = make_entry(
            redis_world,
            AuditLogAction.channel_update,
            user_id=str(USER_ID),
            target_id=str(CHAN),
            changes=[{"key": "afk_channel_id", "new_value": str(CHAN)}],
            options=None,
        )
        assert redis_world.run(entry.get_user()) == member
        target = redis_world.run(entry.get_target())
        assert target is not None
        assert target.id == CHAN
        changes = redis_world.run(entry.get_changes())
        assert changes.after.afk_channel.id == CHAN

    def test_async_extra_on_a_remote_backend(self, redis_world: World) -> None:
        entry = make_entry(
            redis_world,
            AuditLogAction.member_move,
            options={"channel_id": str(CHAN), "count": "1"},
        )
        with pytest.raises(SyncCacheAccessError):
            _ = entry.extra
        extra = redis_world.run(entry.get_extra())
        assert extra.channel.id == CHAN


def message_payload(world: World, **fields: Any) -> Any:
    data = world.payload(t.message.Message, **fields)
    for key in (
        "thread",
        "message_reference",
        "referenced_message",
        "message_snapshots",
    ):
        data.pop(key, None)
    return data


class TestWebhook:
    def payload(self, world: World, **fields: Any) -> Any:
        return world.payload(
            t.webhook.Webhook,
            **{
                "id": "8400",
                "type": 1,
                "guild_id": str(world.guild.id),
                "channel_id": str(CHAN),
                **fields,
            },
        )

    def test_guild_and_channel_when_cached(self, world: World) -> None:
        webhook = Webhook(self.payload(world), session=world.session, state=world.state)
        assert webhook.guild is world.guild
        assert webhook.channel is world.channel
        assert world.run(webhook.get_guild()) is world.guild
        assert world.run(webhook.get_channel()) is world.channel

    def test_partial_fallback_when_not_cached(self, world: World) -> None:
        data = self.payload(world, guild_id="999", channel_id="998")
        webhook = Webhook(data, session=world.session, state=world.state)
        assert isinstance(webhook.guild, PartialGuild)
        assert webhook.guild.id == 999
        assert isinstance(webhook.channel, PartialMessageable)
        assert webhook.channel.id == 998
        assert world.run(webhook.get_guild()) is None
        assert world.run(webhook.get_channel()) is None

    def test_remote_backend_returns_handles(self, redis_world: World) -> None:
        webhook = Webhook(
            self.payload(redis_world),
            session=redis_world.session,
            state=redis_world.state,
        )
        assert isinstance(webhook.guild, PartialGuild)
        assert isinstance(webhook.channel, PartialMessageable)
        assert redis_world.run(webhook.get_guild()).id == redis_world.guild.id
        assert redis_world.run(webhook.get_channel()).id == redis_world.channel.id

    def test_partial_webhook_has_no_guild_or_channel(self, world: World) -> None:
        data = self.payload(world)
        data.pop("guild_id")
        data.pop("channel_id")
        webhook = Webhook(data, session=world.session)
        assert webhook.guild is None
        assert webhook.channel is None
        assert world.run(webhook.get_guild()) is None
        assert world.run(webhook.get_channel()) is None

    def test_sync_webhook_never_touches_the_cache(self, world: World) -> None:
        webhook = SyncWebhook(self.payload(world), session=world.session)
        assert webhook.guild is not None
        assert webhook.guild.id == world.guild.id
        assert isinstance(webhook.channel, PartialMessageable)
        assert webhook._cache_state() is None
        message = webhook._create_message(message_payload(world))
        assert message.channel_id == message.channel.id

    def test_create_message_uses_the_payload_channel_and_guild(
        self, world: World
    ) -> None:
        webhook = Webhook(self.payload(world), session=world.session, state=world.state)
        data = message_payload(world, channel_id="777")
        data.pop("guild_id", None)
        message = world.run(webhook._create_message(data))
        assert message.channel_id == 777
        assert message.guild_id == world.guild.id


class TestTemplate:
    def make(self, world: World, guild_id: int) -> Template:
        data = world.payload(t.template.Template, source_guild_id=str(guild_id))
        data["serialized_source_guild"] = {
            **world.payload(t.guild.Guild),
            "id": str(guild_id),
        }
        return Template(state=world.state, data=data)

    def test_cached_source_guild(self, world: World) -> None:
        template = self.make(world, world.guild.id)
        assert template.source_guild_id == world.guild.id
        assert template.source_guild is world.guild
        assert world.run(template.get_source_guild()) is world.guild

    def test_serialised_source_guild_when_not_cached(self, world: World) -> None:
        template = self.make(world, 4242)
        assert template.source_guild.id == 4242
        assert world.run(template.get_source_guild()) is template.source_guild
        assert world.run(template.source_guild.get_channels()) == []

    def test_remote_backend(self, redis_world: World) -> None:
        template = self.make(redis_world, 4242)
        with pytest.raises(SyncCacheAccessError):
            _ = template.source_guild
        assert redis_world.run(template.get_source_guild()).id == 4242
        assert "source_guild_id=4242" in repr(template)


class TestOnboarding:
    def make(self, world: World, channel_ids: list[int]) -> Onboarding:
        data = world.payload(
            t.onboarding.Onboarding,
            guild_id=str(world.guild.id),
            default_channel_ids=[str(i) for i in channel_ids],
        )
        return Onboarding(data, world.guild)

    def test_default_channels_sync_matches_async(self, world: World) -> None:
        onboarding = self.make(world, [CHAN, OTHER_ID])
        expected = [world.channel, Object(OTHER_ID)]
        assert onboarding.default_channels == expected
        assert world.run(onboarding.get_default_channels()) == expected

    def test_default_channels_remote(self, redis_world: World) -> None:
        onboarding = self.make(redis_world, [CHAN])
        with pytest.raises(SyncCacheAccessError):
            _ = onboarding.default_channels
        assert redis_world.run(onboarding.get_default_channels()) == [
            redis_world.channel
        ]

    def test_prompt_option_resolution(self, world: World) -> None:
        role = add_role(world)
        option_payload = world.payload(
            t.onboarding.PromptOption,
            channel_ids=[str(CHAN), str(OTHER_ID)],
            role_ids=[str(ROLE_ID)],
        )
        option = PromptOption._from_dict(option_payload, world.guild)
        assert option.channels == [world.channel, Object(OTHER_ID)]
        assert option.roles == [role]
        assert world.run(option.get_channels()) == [world.channel, Object(OTHER_ID)]
        assert world.run(option.get_roles()) == [role]
        assert option.to_dict()["channel_ids"] == [CHAN, OTHER_ID]

    def test_prompt_option_lazy_properties_on_a_remote_backend(
        self, redis_world: World
    ) -> None:
        option_payload = redis_world.payload(
            t.onboarding.PromptOption,
            channel_ids=[str(CHAN)],
            role_ids=[str(ROLE_ID)],
        )
        option = PromptOption._from_dict(option_payload, redis_world.guild)
        assert option.channels == [Object(CHAN)]
        assert option.roles == [Object(ROLE_ID)]
        assert option.to_dict()["channel_ids"] == [CHAN]
        option.channels = [Object(OTHER_ID)]
        assert option.to_dict()["channel_ids"] == [OTHER_ID]

    def test_user_made_prompt_option_resolves_to_itself(self, world: World) -> None:
        option = PromptOption("title", channels=[Object(CHAN)])
        assert world.run(option.get_channels()) == [Object(CHAN)]
        assert world.run(option.get_roles()) == []
        assert world.run(option.get_emoji()) is None


class TestWelcomeScreen:
    def test_channel_resolution(self, world: World) -> None:
        payload = world.payload(
            t.welcome_screen.WelcomeScreenChannel,
            channel_id=str(CHAN),
            emoji_id=None,
            emoji_name="x",
        )
        channel = WelcomeScreenChannel._from_dict(payload, world.guild)
        assert channel.channel is world.channel
        assert channel.emoji == "x"
        assert world.run(channel.get_channel()) is world.channel
        assert world.run(channel.get_emoji()) == "x"
        assert channel.to_dict()["channel_id"] == CHAN

    def test_custom_emoji_is_a_partial_emoji(self, world: World) -> None:
        payload = world.payload(
            t.welcome_screen.WelcomeScreenChannel,
            channel_id=str(CHAN),
            emoji_id="555",
            emoji_name="e",
        )
        channel = WelcomeScreenChannel._from_dict(payload, world.guild)
        assert channel.emoji.id == 555  # type: ignore[union-attr]
        assert world.run(channel.get_emoji()) is channel.emoji

    def test_enabled_and_guild(self, world: World) -> None:
        screen = WelcomeScreen(
            world.payload(t.welcome_screen.WelcomeScreen), world.guild
        )
        assert screen.guild is world.guild
        assert world.run(screen.get_guild()) is world.guild
        assert screen.enabled == world.run(screen.get_enabled())

    def test_partial_guild_resolution(self, world: World) -> None:
        handle = PartialGuild(state=world.state, id=world.guild.id)
        screen = WelcomeScreen(world.payload(t.welcome_screen.WelcomeScreen), handle)
        assert screen.guild is world.guild
        assert world.run(screen.get_guild()) is world.guild
        assert screen.enabled == world.run(screen.get_enabled())

    def test_remote_backend(self, redis_world: World) -> None:
        handle = PartialGuild(state=redis_world.state, id=redis_world.guild.id)
        screen = WelcomeScreen(
            redis_world.payload(t.welcome_screen.WelcomeScreen), handle
        )
        with pytest.raises(SyncCacheAccessError):
            _ = screen.guild
        assert redis_world.run(screen.get_guild()).id == redis_world.guild.id


class TestMonetizationAppInfoLobby:
    def test_subscription_user(self, world: World) -> None:
        payload = world.payload(t.monetization.Subscription, user_id=str(world.me.id))
        subscription = Subscription(data=payload, state=world.state)
        world.run(world.state._users.set(world.user.id, world.user))
        subscription.user_id = world.user.id
        assert subscription.user is world.user
        assert world.run(subscription.get_user()) is world.user

    def test_subscription_user_remote(self, redis_world: World) -> None:
        payload = redis_world.payload(t.monetization.Subscription)
        subscription = Subscription(data=payload, state=redis_world.state)
        with pytest.raises(SyncCacheAccessError):
            _ = subscription.user
        assert redis_world.run(subscription.get_user()) is None

    def test_appinfo_guild(self, world: World) -> None:
        from discord.appinfo import AppInfo

        payload = world.payload(
            t.appinfo.AppInfo,
            guild_id=str(world.guild.id),
            team=None,
        )
        info = AppInfo(state=world.state, data=payload)
        assert info.guild is world.guild
        assert world.run(info.get_guild()) is world.guild

    def test_lobby_member_user(self, world: World) -> None:
        member = LobbyMember(
            state=world.state,
            lobby_id=1,
            data=world.payload(t.lobby.LobbyMember, id=str(world.user.id)),
        )
        world.run(world.state._users.set(world.user.id, world.user))
        assert member.user is world.user
        assert world.run(member.get_user()) is world.user

    def test_lobby_linked_channel(self, world: World) -> None:
        payload = world.payload(
            t.lobby.Lobby,
            linked_channel={**world.payload(t.channel.TextChannel), "id": str(CHAN)},
        )
        lobby = Lobby(state=world.state, data=payload)
        assert lobby.linked_channel_id == CHAN
        assert lobby.linked_channel is world.channel
        assert world.run(lobby.get_linked_channel()) is world.channel

    def test_lobby_linked_channel_remote(self, redis_world: World) -> None:
        payload = redis_world.payload(
            t.lobby.Lobby,
            linked_channel={
                **redis_world.payload(t.channel.TextChannel),
                "id": str(CHAN),
            },
        )
        lobby = Lobby(state=redis_world.state, data=payload)
        with pytest.raises(SyncCacheAccessError):
            _ = lobby.linked_channel
        assert redis_world.run(lobby.get_linked_channel()).id == redis_world.channel.id
