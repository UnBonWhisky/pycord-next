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
from unittest.mock import AsyncMock

import pytest

from discord import types as t
from discord.automod import AutoModRule
from discord.channel import PartialGuildChannel
from discord.emoji import AppEmoji, GuildEmoji
from discord.enums import ChannelType, ExpireBehaviour
from discord.guild import PartialGuild
from discord.integrations import (
    BotIntegration,
    Integration,
    StreamIntegration,
    _integration_factory,
)
from discord.invite import Invite, PartialInviteChannel, PartialInviteGuild
from discord.member import Member
from discord.object import Object
from discord.role import Role
from discord.scheduled_events import ScheduledEvent
from discord.soundboard import SoundboardSound
from discord.stage_instance import StageInstance
from discord.sticker import GuildSticker, StandardSticker
from discord.user import User
from tests.payloads.overrides import CHANNEL_ID

if TYPE_CHECKING:
    from tests.models.context import World


def add_role(world: World, role_id: int, position: int) -> Role:
    role = Role(
        guild=world.guild,
        state=world.state,
        data=world.payload(t.role.Role, id=str(role_id), position=position),
    )
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def emoji_payload(world: World, **fields: Any) -> Any:
    return world.payload(t.emoji.Emoji, **fields)


class TestGuildEmoji:
    def test_role_ids_come_from_payload(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, roles=["30", "10", "20"]),
        )
        assert emoji.role_ids == [10, 20, 30]

    def test_get_roles_sorted_by_position_and_skips_uncached(
        self, world: World
    ) -> None:
        low = add_role(world, 20, position=1)
        high = add_role(world, 10, position=5)
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, roles=["10", "20", "99"]),
        )
        assert world.run(emoji.get_roles()) == [low, high]

    def test_get_roles_empty_when_unrestricted(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, roles=[]),
        )
        assert world.run(emoji.get_roles()) == []

    def test_get_roles_uses_the_guild_of_the_emoji(self, world: World) -> None:
        add_role(world, 10, position=1)
        other = GuildEmoji(
            guild=PartialGuild(state=world.state, id=424242),
            state=world.state,
            data=emoji_payload(world, roles=["10"]),
        )
        assert world.run(other.get_roles()) == []

    def test_sync_roles_match_async_getter(self, world: World) -> None:
        low = add_role(world, 20, position=1)
        high = add_role(world, 10, position=5)
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, roles=["10", "20", "99"]),
        )
        assert emoji.roles == [low, high]
        assert emoji.roles == world.run(emoji.get_roles())

    def test_guild_is_the_cached_guild(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild, state=world.state, data=emoji_payload(world)
        )
        assert emoji.guild is world.guild
        other = GuildEmoji(
            guild=PartialGuild(state=world.state, id=424242),
            state=world.state,
            data=emoji_payload(world),
        )
        assert isinstance(other.guild, PartialGuild)
        assert other.guild.id == 424242

    def test_is_usable_unavailable(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, available=False, roles=[]),
        )
        assert emoji.is_usable() is False
        assert world.run(emoji.check_usable()) is False

    def test_is_usable_unrestricted(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, available=True, roles=[]),
        )
        assert emoji.is_usable() is True
        assert world.run(emoji.check_usable()) is True

    def test_is_usable_requires_cached_member_with_role(self, world: World) -> None:
        emoji = GuildEmoji(
            guild=world.guild,
            state=world.state,
            data=emoji_payload(world, available=True, roles=["10"]),
        )
        assert emoji.is_usable() is False
        assert world.run(emoji.check_usable()) is False

        member = Member(
            data=world.payload(
                t.member.MemberWithUser,
                roles=["11"],
                user={**world.payload(t.user.User), "id": str(world.me.id)},
            ),
            guild=world.guild,
            state=world.state,
        )
        world.run(world.guild._add_member(member))
        assert emoji.is_usable() is False
        assert world.run(emoji.check_usable()) is False

        member._roles.add(10)
        assert emoji.is_usable() is True
        assert world.run(emoji.check_usable()) is True


class TestAppEmoji:
    def make(self, world: World) -> AppEmoji:
        return AppEmoji(
            application_id=1234,
            state=world.state,
            data=emoji_payload(world),
        )

    def test_roles_are_empty(self, world: World) -> None:
        emoji = self.make(world)
        assert emoji.role_ids == []
        assert emoji.roles == []
        assert world.run(emoji.get_roles()) == []
        assert emoji.guild is None

    def test_is_usable_compares_application(self, world: World) -> None:
        emoji = self.make(world)
        world.state.application_id = 1234
        assert emoji.is_usable() is True
        assert world.run(emoji.check_usable()) is True
        world.state.application_id = 4321
        assert emoji.is_usable() is False
        assert world.run(emoji.check_usable()) is False

    def test_delete_evicts_cached_emoji(self, world: World) -> None:
        emoji = self.make(world)
        world.state.cache_app_emojis = True
        world.run(world.state._app_emojis.set(emoji.id, emoji))
        world.state.http.delete_application_emoji = AsyncMock(return_value=None)
        world.run(emoji.delete())
        assert world.run(world.state.get_emoji(emoji.id)) is None

    def test_edit_stores_the_returned_emoji(self, world: World) -> None:
        emoji = self.make(world)
        world.state.cache_app_emojis = True
        data = emoji_payload(world, id=str(emoji.id), name="renamed")
        world.state.http.edit_application_emoji = AsyncMock(return_value=data)
        edited = world.run(emoji.edit(name="renamed"))
        assert isinstance(edited, AppEmoji)
        assert edited.name == "renamed"
        assert world.run(world.state.get_emoji(emoji.id)) is edited


class TestStickers:
    def sticker_payload(self, world: World, tp: Any, **fields: Any) -> Any:
        return world.payload(tp, **fields)

    def test_guild_sticker_description_can_be_null(self, world: World) -> None:
        sticker = GuildSticker(
            state=world.state,
            data=self.sticker_payload(world, t.sticker.GuildSticker, description=None),
        )
        assert sticker.description is None

    def test_standard_sticker_description_can_be_null(self, world: World) -> None:
        sticker = StandardSticker(
            state=world.state,
            data=self.sticker_payload(
                world, t.sticker.StandardSticker, description=None
            ),
        )
        assert sticker.description is None

    def test_guild_sticker_guild_falls_back_to_a_handle(self, world: World) -> None:
        sticker = GuildSticker(
            state=world.state,
            data=self.sticker_payload(world, t.sticker.GuildSticker),
        )
        assert isinstance(sticker.guild, PartialGuild)
        assert sticker.guild.id == sticker.guild_id
        cached = GuildSticker(
            state=world.state,
            data=self.sticker_payload(
                world, t.sticker.GuildSticker, guild_id=str(world.guild.id)
            ),
        )
        assert cached.guild is world.guild


class TestSoundboardSound:
    def make(self, world: World, **fields: Any) -> SoundboardSound:
        return SoundboardSound(
            state=world.state,
            http=world.state.http,
            data=world.payload(t.soundboard.SoundboardSound, **fields),
        )

    def test_edit_returns_a_sound(self, world: World) -> None:
        sound = self.make(world)
        updated = world.payload(
            t.soundboard.SoundboardSound,
            sound_id=str(sound.id),
            guild_id=str(sound.guild_id),
            name="renamed",
        )
        world.state.http.edit_guild_sound = AsyncMock(return_value=updated)
        edited = world.run(sound.edit(name="renamed"))
        assert isinstance(edited, SoundboardSound)
        assert edited.name == "renamed"
        assert edited.id == sound.id

    def test_delete_awaits_the_request(self, world: World) -> None:
        sound = self.make(world)
        world.state.http.delete_sound = AsyncMock(return_value=None)
        assert world.run(sound.delete(reason="r")) is None
        world.state.http.delete_sound.assert_awaited_once_with(sound, reason="r")

    def test_default_sound_cannot_be_edited_or_deleted(self, world: World) -> None:
        payload = world.payload(t.soundboard.SoundboardSound)
        payload.pop("guild_id", None)
        sound = SoundboardSound(state=world.state, http=world.state.http, data=payload)
        with pytest.raises(ValueError, match="default"):
            world.run(sound.edit(name="x"))
        with pytest.raises(ValueError, match="default"):
            world.run(sound.delete())


class TestScheduledEvent:
    def make(self, world: World, **fields: Any) -> ScheduledEvent:
        return ScheduledEvent(
            state=world.state,
            guild=world.guild,
            data=world.payload(
                t.scheduled_events.ScheduledEvent,
                guild_id=str(world.guild.id),
                **fields,
            ),
        )

    def test_creator_is_built_from_the_payload(self, world: World) -> None:
        creator = world.payload(t.user.User)
        event = self.make(world, creator=creator, creator_id=creator["id"])
        assert isinstance(event.creator, User)
        assert event.creator.id == int(creator["id"])
        assert event.creator_id == int(creator["id"])

    def test_creator_is_none_without_payload(self, world: World) -> None:
        payload = world.payload(t.scheduled_events.ScheduledEvent)
        payload.pop("creator")
        payload["creator_id"] = None
        event = ScheduledEvent(state=world.state, guild=world.guild, data=payload)
        assert event.creator is None
        assert event.creator_id is None
        assert world.run(event.get_creator()) is None

    def test_resolved_creator_argument_is_kept(self, world: World) -> None:
        event = ScheduledEvent(
            state=world.state,
            guild=world.guild,
            creator=world.member,
            data=world.payload(t.scheduled_events.ScheduledEvent),
        )
        assert event.creator is world.member

    def test_get_creator_returns_cached_member(self, world: World) -> None:
        member = world.member
        event = self.make(world, creator_id=str(member.id))
        event.creator = None
        assert world.run(event.get_creator()) is None
        assert event.creator is None
        world.run(world.guild._add_member(member))
        assert world.run(event.get_creator()) is member

    def test_get_channel(self, world: World) -> None:
        event = self.make(world, channel_id=CHANNEL_ID)
        assert world.run(event.get_channel()) is world.channel
        assert event.channel is world.channel
        assert event.guild is world.guild

    def test_get_channel_without_channel(self, world: World) -> None:
        payload = world.payload(t.scheduled_events.ScheduledEvent)
        payload["channel_id"] = None
        payload["entity_metadata"] = {"location": "somewhere"}
        event = ScheduledEvent(state=world.state, guild=world.guild, data=payload)
        assert event.channel is None
        assert world.run(event.get_channel()) is None
        assert event.location.value == "somewhere"

    def test_get_channel_uncached(self, world: World) -> None:
        event = self.make(world, channel_id="777")
        assert world.run(event.get_channel()) is None
        assert isinstance(event.channel, PartialGuildChannel)
        assert event.channel.id == 777

    def test_location_value_is_the_cached_channel_or_an_object(
        self, world: World
    ) -> None:
        event = self.make(world, channel_id=CHANNEL_ID)
        assert event.location.value is world.channel
        world.run(world.guild._remove_channel(world.channel))
        assert isinstance(event.location.value, Object)
        assert event.location.value.id == int(CHANNEL_ID)

    def test_edit_returns_event(self, world: World) -> None:
        event = self.make(world)
        updated = world.payload(
            t.scheduled_events.ScheduledEvent,
            id=str(event.id),
            guild_id=str(world.guild.id),
            name="renamed",
        )
        world.state.http.edit_scheduled_event = AsyncMock(return_value=updated)
        edited = world.run(event.edit(name="renamed"))
        assert isinstance(edited, ScheduledEvent)
        assert edited.name == "renamed"
        assert edited.guild_id == world.guild.id

    def test_shortcuts_return_the_edited_event(self, world: World) -> None:
        event = self.make(world)
        updated = world.payload(
            t.scheduled_events.ScheduledEvent,
            id=str(event.id),
            guild_id=str(world.guild.id),
        )
        world.state.http.edit_scheduled_event = AsyncMock(return_value=updated)
        assert isinstance(world.run(event.start()), ScheduledEvent)
        assert isinstance(world.run(event.complete()), ScheduledEvent)
        assert isinstance(world.run(event.cancel()), ScheduledEvent)


class TestStageInstance:
    def test_handles_and_scheduled_event(self, world: World) -> None:
        instance = StageInstance(
            state=world.state,
            guild=PartialGuild(state=world.state, id=world.guild.id),
            data=world.payload(
                t.channel.StageInstance,
                channel_id=CHANNEL_ID,
                guild_scheduled_event_id="555",
            ),
        )
        assert instance.guild_id == world.guild.id
        assert instance.guild is world.guild
        assert instance.channel is world.channel
        assert world.run(instance.get_channel()) is world.channel
        assert instance.scheduled_event is None
        assert world.run(instance.get_scheduled_event()) is None

        event = ScheduledEvent(
            state=world.state,
            guild=world.guild,
            data=world.payload(
                t.scheduled_events.ScheduledEvent,
                id="555",
                guild_id=str(world.guild.id),
            ),
        )
        world.run(world.guild._add_scheduled_event(event))
        assert world.run(instance.get_scheduled_event()) is event
        assert instance.scheduled_event is event

    def test_uncached_channel_falls_back_to_a_handle(self, world: World) -> None:
        instance = StageInstance(
            state=world.state,
            guild=PartialGuild(state=world.state, id=31337),
            data=world.payload(t.channel.StageInstance, channel_id="42"),
        )
        assert isinstance(instance.guild, PartialGuild)
        assert isinstance(instance.channel, PartialGuildChannel)
        assert instance.channel.type is ChannelType.stage_voice
        assert world.run(instance.get_channel()) is None


class TestInvite:
    def test_from_incomplete_uses_the_cache(self, world: World) -> None:
        payload = world.payload(
            t.invite.Invite,
            channel={"id": CHANNEL_ID, "name": "general", "type": 0},
        )
        payload["guild"]["id"] = str(world.guild.id)
        invite = Invite.from_incomplete(state=world.state, data=payload)
        assert invite.guild is world.guild
        assert invite.channel is world.channel
        assert world.run(invite.get_guild()) is world.guild
        assert world.run(invite.get_channel()) is world.channel

    def test_from_incomplete_uncached_guild(self, world: World) -> None:
        payload = world.payload(t.invite.Invite)
        payload["guild"]["id"] = "31337"
        invite = Invite.from_incomplete(state=world.state, data=payload)
        assert isinstance(invite.guild, PartialInviteGuild)
        assert isinstance(invite.channel, PartialInviteChannel)
        assert world.run(invite.get_guild()) is None
        assert world.run(invite.get_channel()) is None

    def test_from_incomplete_group_dm(self, world: World) -> None:
        payload = world.payload(t.invite.Invite)
        payload.pop("guild")
        invite = Invite.from_incomplete(state=world.state, data=payload)
        assert invite.guild is None
        assert world.run(invite.get_guild()) is None
        assert world.run(invite.get_channel()) is None

    def test_from_gateway_cached_guild(self, world: World) -> None:
        payload = world.payload(
            t.invite.GatewayInviteCreate,
            guild_id=str(world.guild.id),
            channel_id=CHANNEL_ID,
        )
        invite = Invite.from_gateway(state=world.state, data=payload)
        assert invite.guild is world.guild
        assert invite.channel is world.channel
        assert world.run(invite.get_guild()) is world.guild
        assert world.run(invite.get_channel()) is world.channel

    def test_from_gateway_uncached_guild(self, world: World) -> None:
        payload = world.payload(
            t.invite.GatewayInviteCreate, guild_id="31337", channel_id="42"
        )
        invite = Invite.from_gateway(state=world.state, data=payload)
        assert isinstance(invite.guild, Object)
        assert invite.guild.id == 31337
        assert isinstance(invite.channel, Object)
        assert world.run(invite.get_guild()) is None
        assert world.run(invite.get_channel()) is None

    def test_from_gateway_without_guild(self, world: World) -> None:
        payload = world.payload(t.invite.GatewayInviteCreate, channel_id="42")
        payload.pop("guild_id")
        invite = Invite.from_gateway(state=world.state, data=payload)
        assert invite.guild is None
        assert isinstance(invite.channel, Object)
        assert world.run(invite.get_channel()) is None

    def test_scheduled_event_in_payload(self, world: World) -> None:
        payload = world.payload(
            t.invite.Invite,
            guild_scheduled_event=world.payload(
                t.scheduled_events.ScheduledEvent, guild_id=str(world.guild.id)
            ),
        )
        invite = Invite(state=world.state, data=payload)
        assert isinstance(invite.scheduled_event, ScheduledEvent)
        assert invite.scheduled_event.guild_id == world.guild.id
        assert f"?event={invite.scheduled_event.id}" in invite.url

    def test_roles_are_built_from_the_payload(self, world: World) -> None:
        payload = world.payload(
            t.invite.Invite, roles=[world.payload(t.role.Role, id="55")]
        )
        invite = Invite(state=world.state, data=payload)
        assert invite.guild is not None
        assert [type(r) for r in invite.roles] == [Role]
        assert invite.roles[0].guild_id == invite.guild.id


class TestIntegrations:
    def account(self) -> dict[str, str]:
        return {"id": "acc", "name": "account"}

    def test_stream_integration_with_all_fields(self, world: World) -> None:
        payload = world.payload(
            t.integration.StreamIntegration,
            type="twitch",
            expire_behavior=1,
            expire_grace_period=7,
            role_id="10",
            syncing=True,
            enable_emoticons=True,
            subscriber_count=3,
            revoked=False,
            synced_at="2024-01-01T00:00:00+00:00",
        )
        integration = StreamIntegration(data=payload, guild=world.guild)
        assert integration.expire_behaviour is ExpireBehaviour.kick
        assert integration.expire_grace_period == 7
        assert integration.role_id == 10
        assert integration.syncing is True
        assert integration.enable_emoticons is True
        assert integration.subscriber_count == 3
        assert integration.revoked is False
        assert integration.synced_at is not None

    def test_stream_integration_optional_fields_absent(self, world: World) -> None:
        payload = {
            "id": "1",
            "name": "n",
            "type": "twitch",
            "account": self.account(),
            "enabled": True,
        }
        integration = StreamIntegration(data=payload, guild=world.guild)  # type: ignore[arg-type]
        assert integration.user is None
        assert integration.syncing is None
        assert integration.synced_at is None
        assert integration.expire_behaviour is None
        assert integration.expire_grace_period is None
        assert integration.role_id is None
        assert integration.enable_emoticons is None
        assert integration.subscriber_count is None
        assert integration.revoked is None
        assert world.run(integration.get_role()) is None
        assert integration.role is None

    def test_get_role(self, world: World) -> None:
        role = add_role(world, 10, position=1)
        payload = world.payload(t.integration.StreamIntegration, role_id="10")
        integration = StreamIntegration(data=payload, guild=world.guild)
        assert world.run(integration.get_role()) is role
        payload["role_id"] = "11"
        assert (
            world.run(StreamIntegration(data=payload, guild=world.guild).get_role())
            is None
        )

    def test_sync_sets_synced_at(self, world: World) -> None:
        payload = world.payload(t.integration.StreamIntegration)
        payload.pop("synced_at", None)
        integration = StreamIntegration(data=payload, guild=world.guild)
        world.state.http.sync_integration = AsyncMock(return_value=None)
        world.run(integration.sync())
        assert integration.synced_at is not None

    def test_bot_integration_without_stream_fields(self, world: World) -> None:
        payload = {
            "id": "1",
            "name": "n",
            "type": "discord",
            "account": self.account(),
            "enabled": True,
            "application": {
                "id": "2",
                "name": "app",
                "icon": None,
                "description": "",
            },
            "scopes": ["bot", "applications.commands"],
        }
        integration = BotIntegration(data=payload, guild=world.guild)  # type: ignore[arg-type]
        assert integration.user is None
        assert integration.application.summary == ""
        assert integration.scopes == ["bot", "applications.commands"]

    def test_bot_integration_scopes_default(self, world: World) -> None:
        payload = world.payload(t.integration.BotIntegration)
        payload.pop("scopes", None)
        assert BotIntegration(data=payload, guild=world.guild).scopes == []

    def test_factory(self) -> None:
        assert _integration_factory("discord")[0] is BotIntegration
        assert _integration_factory("youtube")[0] is StreamIntegration
        assert _integration_factory("guild_subscription")[0] is Integration

    def test_guild(self, world: World) -> None:
        integration = Integration(
            data=world.payload(t.integration.BaseIntegration), guild=world.guild
        )
        assert integration.guild is world.guild
        assert integration.guild_id == world.guild.id
        other = Integration(
            data=world.payload(t.integration.BaseIntegration),
            guild=PartialGuild(state=world.state, id=31337),
        )
        assert isinstance(other.guild, PartialGuild)


class TestAutoModRule:
    def make(self, world: World, **fields: Any) -> AutoModRule:
        return AutoModRule(
            state=world.state,
            data=world.payload(
                t.automod.AutoModRule,
                **{"guild_id": str(world.guild.id), **fields},
            ),
        )

    def test_guild(self, world: World) -> None:
        rule = self.make(world)
        assert rule.guild is world.guild
        assert world.run(rule.get_guild()) is world.guild
        unknown = self.make(world, guild_id="31337")
        assert unknown.guild is None
        assert world.run(unknown.get_guild()) is None

    def test_get_creator(self, world: World) -> None:
        member = world.member
        rule = self.make(world, creator_id=str(member.id))
        assert rule.creator is None
        assert world.run(rule.get_creator()) is None
        world.run(world.guild._add_member(member))
        assert rule.creator is member
        assert world.run(rule.get_creator()) is member

    def test_exempt_roles_fall_back_to_objects(self, world: World) -> None:
        role = add_role(world, 10, position=1)
        rule = self.make(world, exempt_roles=["10", "11"])
        for resolved in (rule.exempt_roles, world.run(rule.get_exempt_roles())):
            assert resolved[0] is role
            assert isinstance(resolved[1], Object)
            assert resolved[1].id == 11

    def test_exempt_channels_keep_payload_order(self, world: World) -> None:
        rule = self.make(world, exempt_channels=["999", CHANNEL_ID])
        for resolved in (rule.exempt_channels, world.run(rule.get_exempt_channels())):
            assert isinstance(resolved[0], Object)
            assert resolved[0].id == 999
            assert resolved[1] is world.channel

    def test_async_exempt_lists_are_not_cached_between_calls(
        self, world: World
    ) -> None:
        rule = self.make(world, exempt_roles=["10"])
        assert isinstance(world.run(rule.get_exempt_roles())[0], Object)
        role = add_role(world, 10, position=1)
        assert world.run(rule.get_exempt_roles()) == [role]

    def test_unknown_guild_gives_objects(self, world: World) -> None:
        rule = self.make(
            world, guild_id="31337", exempt_roles=["10"], exempt_channels=["20"]
        )
        for roles, channels in (
            (rule.exempt_roles, rule.exempt_channels),
            (world.run(rule.get_exempt_roles()), world.run(rule.get_exempt_channels())),
        ):
            assert [o.id for o in roles] == [10]
            assert [o.id for o in channels] == [20]
