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


"""D12 semantics of the interaction and of the application context on both cache backends."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from discord import types as t
from discord.channel import TextChannel
from discord.commands.checks import (
    author_channel_permissions,
    author_guild_permissions,
    author_roles,
    bot_channel_permissions,
    bot_guild_permissions,
    bot_roles,
    get_author_channel_permissions,
    get_author_guild_permissions,
    get_author_roles,
    get_bot_channel_permissions,
    get_bot_guild_permissions,
    get_bot_roles,
)
from discord.errors import SyncCacheAccessError
from discord.guild import Guild, PartialGuild
from discord.interactions import (
    AuthorizingIntegrationOwners,
    InteractionMessage,
    InteractionMetadata,
)
from discord.member import Member
from discord.message import Message
from discord.user import ClientUser, User
from tests.commands.interaction_support import (
    MEMBER_ID,
    add_bot_member,
    add_member,
    backend_world,
    interaction_payload,
    is_memory,
    make_context,
    make_interaction,
)

if TYPE_CHECKING:
    from tests.models.context import World

__all__ = ("backend_world",)


class TestGuild:
    def test_cached_guild_in_process_else_handle(self, backend_world: World) -> None:
        interaction = make_interaction(backend_world)
        if is_memory(backend_world):
            assert interaction.guild is backend_world.guild
        else:
            assert type(interaction.guild) is PartialGuild
            assert interaction.guild.id == backend_world.guild.id

    def test_payload_guild_stays_a_real_object(self, backend_world: World) -> None:
        payload = interaction_payload(backend_world)
        payload["guild"] = backend_world.payload(
            t.guild.Guild, id=str(backend_world.guild.id)
        )
        interaction = make_interaction(backend_world, payload)
        assert type(interaction.guild) is Guild
        assert interaction.guild is not backend_world.guild

    def test_get_guild_returns_the_cached_guild(self, backend_world: World) -> None:
        ctx = make_context(backend_world)
        guild = backend_world.run(ctx.get_guild())
        assert guild is not None
        assert guild.id == backend_world.guild.id
        assert backend_world.run(ctx.interaction.get_guild()) is not None

    def test_get_guild_none_when_uncached(self, backend_world: World) -> None:
        backend_world.run(backend_world.state._remove_guild(backend_world.guild))
        ctx = make_context(backend_world)
        assert type(ctx.guild) is PartialGuild
        assert backend_world.run(ctx.get_guild()) is None

    def test_dm_has_no_guild(self, backend_world: World) -> None:
        ctx = make_context(backend_world, guild=False)
        assert ctx.guild is None
        assert backend_world.run(ctx.get_guild()) is None
        assert ctx.voice_client is None
        assert ctx.me is ctx.bot.user
        assert backend_world.run(ctx.get_me()) is ctx.bot.user
        assert isinstance(ctx.author, User)


class TestChannelAndAuthor:
    def test_channel_comes_from_the_cache_after_population(
        self, backend_world: World
    ) -> None:
        ctx = make_context(backend_world)
        assert isinstance(ctx.channel, TextChannel)
        assert ctx.channel.id == backend_world.channel.id
        if is_memory(backend_world):
            assert ctx.channel is backend_world.channel

    def test_channel_from_the_payload_when_not_cached(
        self, backend_world: World
    ) -> None:
        backend_world.run(
            backend_world.state._remove_channel(
                backend_world.guild.id, backend_world.channel.id
            )
        )
        ctx = make_context(backend_world)
        assert isinstance(ctx.channel, TextChannel)
        assert ctx.channel is not backend_world.channel
        assert ctx.channel.id == backend_world.channel.id

    def test_author_is_the_payload_member_or_the_cached_one(
        self, backend_world: World
    ) -> None:
        cached = add_member(backend_world)
        ctx = make_context(backend_world)
        assert isinstance(ctx.author, Member)
        assert ctx.author.id == MEMBER_ID
        assert ctx.user is ctx.author
        if is_memory(backend_world):
            assert ctx.author is cached

    def test_author_without_cached_member(self, backend_world: World) -> None:
        ctx = make_context(backend_world)
        assert isinstance(ctx.author, Member)
        assert ctx.author.guild_id == backend_world.guild.id
        assert ctx.interaction.user_id == MEMBER_ID

    def test_message_comes_from_the_payload(self, backend_world: World) -> None:
        message = backend_world.payload(
            t.message.Message,
            id="7777",
            channel_id=str(backend_world.channel.id),
            guild_id=str(backend_world.guild.id),
        )
        ctx = make_context(backend_world, message=message)
        assert ctx.message is not None
        assert ctx.message.id == 7777
        assert ctx.interaction.message is ctx.message


class TestMe:
    def test_me_falls_back_to_the_client_user(self, backend_world: World) -> None:
        ctx = make_context(backend_world)
        assert isinstance(ctx.me, ClientUser)
        assert ctx.me is backend_world.me
        assert backend_world.run(ctx.get_me()) is backend_world.me

    def test_me_is_the_cached_member(self, backend_world: World) -> None:
        bot_member = add_bot_member(backend_world)
        ctx = make_context(backend_world)
        if is_memory(backend_world):
            assert ctx.me is bot_member
        else:
            assert ctx.me is backend_world.me
        resolved = backend_world.run(ctx.get_me())
        assert isinstance(resolved, Member)
        assert resolved.id == bot_member.id

    def test_me_never_raises(self, backend_world: World) -> None:
        add_bot_member(backend_world)
        ctx = make_context(backend_world)
        assert ctx.me.id == backend_world.me.id


class TestVoiceClient:
    def test_voice_client(self, backend_world: World) -> None:
        ctx = make_context(backend_world)
        assert ctx.voice_client is None
        voice = SimpleNamespace(guild=backend_world.guild)
        backend_world.state._add_voice_client(backend_world.guild.id, voice)  # type: ignore[arg-type]
        assert ctx.voice_client is voice


class TestInteractionMessage:
    def test_response_message_is_populated(self, backend_world: World) -> None:
        cached = add_member(backend_world)
        interaction = make_interaction(backend_world)
        payload = backend_world.payload(
            t.message.Message,
            id="7778",
            channel_id=str(backend_world.channel.id),
            guild_id=str(backend_world.guild.id),
            author={**backend_world.payload(t.user.User), "id": str(MEMBER_ID)},
            member={"roles": [], "joined_at": "2020-01-01T00:00:00+00:00"},
            mentions=[],
            mention_roles=[],
            reactions=[],
        )
        assert interaction.channel is not None
        message = backend_world.run(
            interaction._create_response_message(interaction.channel, payload)  # type: ignore[arg-type]
        )
        assert isinstance(message, InteractionMessage)
        assert message.id == 7778
        assert isinstance(message.author, Member)
        assert message.author.id == MEMBER_ID
        if is_memory(backend_world):
            assert message.author is cached


class TestMetadataTwins:
    def test_authorizing_integration_owners(self, backend_world: World) -> None:
        state = backend_world.state
        backend_world.run(state._users.set(backend_world.user.id, backend_world.user))
        owners = AuthorizingIntegrationOwners(
            {"0": str(backend_world.guild.id), "1": str(backend_world.user.id)}, state
        )
        user = backend_world.run(owners.get_user())
        guild = backend_world.run(owners.get_guild())
        assert user is not None
        assert user.id == backend_world.user.id
        assert guild is not None
        assert guild.id == backend_world.guild.id
        if is_memory(backend_world):
            assert owners.user is user
            assert owners.guild is guild
        else:
            with pytest.raises(SyncCacheAccessError):
                owners.user  # noqa: B018
            with pytest.raises(SyncCacheAccessError):
                owners.guild  # noqa: B018

    def test_authorizing_integration_owners_empty(self, backend_world: World) -> None:
        owners = AuthorizingIntegrationOwners({}, backend_world.state)
        assert backend_world.run(owners.get_user()) is None
        assert backend_world.run(owners.get_guild()) is None

    def test_metadata_messages(self, backend_world: World) -> None:
        payload = backend_world.payload(
            t.message.Message,
            type=0,
            mentions=[],
            mention_roles=[],
            reactions=[],
            guild_id=str(backend_world.guild.id),
            channel_id=str(backend_world.channel.id),
        )
        for key in (
            "message_reference",
            "referenced_message",
            "message_snapshots",
            "poll",
            "thread",
            "call",
            "interaction",
            "interaction_metadata",
            "member",
        ):
            payload.pop(key, None)
        message = Message(
            state=backend_world.state, channel=backend_world.channel, data=payload
        )
        backend_world.run(backend_world.state._store_message(message))
        data = {
            "id": "55",
            "type": 3,
            "user": backend_world.payload(t.user.User),
            "authorizing_integration_owners": {},
            "original_response_message_id": str(message.id),
            "interacted_message_id": str(message.id),
        }
        metadata = InteractionMetadata(data=data, state=backend_world.state)  # type: ignore[arg-type]
        original = backend_world.run(metadata.get_original_response_message())
        interacted = backend_world.run(metadata.get_interacted_message())
        assert original is not None
        assert original.id == message.id
        assert interacted is not None
        assert interacted.id == message.id
        if is_memory(backend_world):
            assert metadata.original_response_message is original
            assert metadata.interacted_message is interacted


class TestChecks:
    def test_async_twins_match_the_sync_helpers(self, backend_world: World) -> None:
        world = backend_world
        add_member(world, world.me.id)
        add_member(world)
        ctx = make_context(world)
        pairs = [
            (author_channel_permissions, get_author_channel_permissions),
            (bot_channel_permissions, get_bot_channel_permissions),
            (author_guild_permissions, get_author_guild_permissions),
            (bot_guild_permissions, get_bot_guild_permissions),
        ]
        for sync, twin in pairs:
            resolved = world.run(twin(ctx))
            assert resolved is not None
            if is_memory(world):
                assert sync(ctx) == resolved
            elif sync in (author_guild_permissions, bot_guild_permissions):
                with pytest.raises(SyncCacheAccessError):
                    sync(ctx)

    def test_roles_twins(self, backend_world: World) -> None:
        world = backend_world
        add_member(world, world.me.id)
        add_member(world)
        ctx = make_context(world)
        for sync, twin in (
            (author_roles, get_author_roles),
            (bot_roles, get_bot_roles),
        ):
            resolved = world.run(twin(ctx))
            assert resolved is not None
            assert [r.id for r in resolved] == [world.guild.id]
            if is_memory(world):
                assert [r.id for r in sync(ctx) or []] == [r.id for r in resolved]
            else:
                with pytest.raises(SyncCacheAccessError):
                    sync(ctx)

    def test_twins_return_none_in_dms(self, backend_world: World) -> None:
        ctx = make_context(backend_world, guild=False)
        assert backend_world.run(get_author_guild_permissions(ctx)) is None
        assert backend_world.run(get_bot_guild_permissions(ctx)) is None
        assert backend_world.run(get_author_roles(ctx)) is None
        assert backend_world.run(get_bot_roles(ctx)) is None
