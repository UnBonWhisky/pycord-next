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
from discord.automod import AutoModRule
from discord.channel import PartialGuildChannel
from discord.emoji import GuildEmoji
from discord.errors import SyncCacheAccessError
from discord.guild import PartialGuild
from discord.integrations import Integration, StreamIntegration
from discord.invite import Invite, PartialInviteChannel, PartialInviteGuild
from discord.role import Role
from discord.scheduled_events import ScheduledEvent
from discord.stage_instance import StageInstance
from discord.sticker import GuildSticker
from tests.models.context import World
from tests.payloads.overrides import CHANNEL_ID
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient


@pytest.fixture
def remote(loop: asyncio.AbstractEventLoop, http: HTTPClient) -> World:
    return World(build_state(loop, http, "redis"))


def add_role(world: World, role_id: int) -> Role:
    role = Role(
        guild=world.guild,
        state=world.state,
        data=world.payload(t.role.Role, id=str(role_id)),
    )
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def test_world_uses_a_remote_backend(remote: World) -> None:
    assert not remote.state.cache.supports_sync


def test_emoji(remote: World) -> None:
    role = add_role(remote, 10)
    emoji = GuildEmoji(
        guild=remote.guild,
        state=remote.state,
        data=remote.payload(t.emoji.Emoji, roles=["10"], available=True),
    )
    assert isinstance(emoji.guild, PartialGuild)
    assert emoji.guild.id == remote.guild.id
    with pytest.raises(SyncCacheAccessError):
        _ = emoji.roles
    with pytest.raises(SyncCacheAccessError):
        emoji.is_usable()
    assert remote.run(emoji.get_roles())[0].id == role.id
    assert remote.run(emoji.check_usable()) is False


def test_sticker(remote: World) -> None:
    sticker = GuildSticker(
        state=remote.state,
        data=remote.payload(t.sticker.GuildSticker, guild_id=str(remote.guild.id)),
    )
    assert isinstance(sticker.guild, PartialGuild)


def test_scheduled_event(remote: World) -> None:
    event = ScheduledEvent(
        state=remote.state,
        guild=remote.guild,
        data=remote.payload(
            t.scheduled_events.ScheduledEvent,
            guild_id=str(remote.guild.id),
            channel_id=CHANNEL_ID,
        ),
    )
    assert isinstance(event.guild, PartialGuild)
    assert isinstance(event.channel, PartialGuildChannel)
    assert remote.run(event.get_channel()).id == int(CHANNEL_ID)  # type: ignore[union-attr]


def test_stage_instance(remote: World) -> None:
    instance = StageInstance(
        state=remote.state,
        guild=remote.guild,
        data=remote.payload(t.channel.StageInstance, channel_id=CHANNEL_ID),
    )
    assert isinstance(instance.guild, PartialGuild)
    assert isinstance(instance.channel, PartialGuildChannel)
    assert remote.run(instance.get_channel()) is not None
    instance.scheduled_event_id = 1
    with pytest.raises(SyncCacheAccessError):
        _ = instance.scheduled_event


def test_integration(remote: World) -> None:
    add_role(remote, 10)
    integration = StreamIntegration(
        data=remote.payload(t.integration.StreamIntegration, role_id="10"),
        guild=remote.guild,
    )
    assert isinstance(integration.guild, PartialGuild)
    with pytest.raises(SyncCacheAccessError):
        _ = integration.role
    assert remote.run(integration.get_role()) is not None
    plain = Integration(
        data=remote.payload(t.integration.BaseIntegration), guild=remote.guild
    )
    assert isinstance(plain.guild, PartialGuild)


def test_automod(remote: World) -> None:
    rule = AutoModRule(
        state=remote.state,
        data=remote.payload(
            t.automod.AutoModRule,
            guild_id=str(remote.guild.id),
            exempt_roles=["10"],
            exempt_channels=[CHANNEL_ID],
        ),
    )
    add_role(remote, 10)
    for name in ("guild", "creator", "exempt_roles", "exempt_channels"):
        with pytest.raises(SyncCacheAccessError):
            getattr(rule, name)
    assert remote.run(rule.get_guild()) is not None
    assert remote.run(rule.get_exempt_roles())[0].id == 10
    assert remote.run(rule.get_exempt_channels())[0].id == int(CHANNEL_ID)


def test_invite_from_incomplete_gives_payload_objects(remote: World) -> None:
    payload: Any = remote.payload(t.invite.Invite)
    payload["guild"]["id"] = str(remote.guild.id)
    invite = Invite.from_incomplete(state=remote.state, data=payload)
    assert isinstance(invite.guild, PartialInviteGuild)
    assert isinstance(invite.channel, PartialInviteChannel)
    assert remote.run(invite.get_guild()) is not None


def test_invite_from_gateway_gives_handles(remote: World) -> None:
    payload: Any = remote.payload(
        t.invite.GatewayInviteCreate,
        guild_id=str(remote.guild.id),
        channel_id=CHANNEL_ID,
    )
    invite = Invite.from_gateway(state=remote.state, data=payload)
    assert isinstance(invite.guild, PartialGuild)
    assert isinstance(invite.channel, PartialGuildChannel)
    assert remote.run(invite.get_channel()) is not None
