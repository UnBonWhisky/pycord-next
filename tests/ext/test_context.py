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

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

import discord
from discord.channel import PartialMessageable, TextChannel
from discord.ext import commands
from discord.guild import Guild, PartialGuild

if TYPE_CHECKING:
    from discord.member import Member
    from tests.ext.support import Server


class TestRelationshipAttributes:
    def test_guild_and_channel_follow_the_backend(
        self, server: Server, backend_kind: str
    ) -> None:
        ctx = server.context("x")
        if backend_kind == "memory":
            assert isinstance(ctx.guild, Guild)
            assert ctx.guild is server.guild
            assert isinstance(ctx.channel, TextChannel)
        else:
            assert isinstance(ctx.guild, PartialGuild)
            assert isinstance(ctx.channel, PartialMessageable)
        assert ctx.guild.id == server.guild.id
        assert ctx.channel.id == server.world.channel.id

    def test_the_author_is_always_the_member(self, server: Server) -> None:
        member = server.add_member(1300000000000000001, name="alice")
        ctx = server.context("x", author=member)
        assert isinstance(ctx.author, discord.Member)
        assert ctx.author.id == member.id

    def test_direct_message(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        assert ctx.guild is None
        assert isinstance(ctx.channel, PartialMessageable)
        assert not isinstance(ctx.author, discord.Member)
        assert ctx.me is server.bot.user
        assert server.run(ctx.get_guild()) is None
        assert server.run(ctx.get_me()) is server.bot.user
        assert ctx.voice_client is None

    def test_an_uncached_guild_is_a_partial_handle(self, server: Server) -> None:
        ctx = server.context("x")
        server.run(server.state._remove_guild(server.guild))
        assert isinstance(ctx.guild, PartialGuild)
        assert ctx.guild.id == server.guild.id
        assert server.run(ctx.get_guild()) is None
        assert ctx.me is server.bot.user


class TestMe:
    def test_the_bot_member_when_the_cache_is_in_process(
        self, server: Server, backend_kind: str
    ) -> None:
        ctx = server.context("x")
        me = ctx.me
        if backend_kind == "memory":
            assert isinstance(me, discord.Member)
            assert me.id == server.bot.user.id
        else:
            assert me is server.bot.user

    def test_it_never_raises_on_a_remote_backend(self, server: Server) -> None:
        assert server.context("x").me.id == server.bot.user.id

    def test_the_async_twin_returns_the_member_on_every_backend(
        self, server: Server
    ) -> None:
        ctx = server.context("x")
        me = server.run(ctx.get_me())
        assert isinstance(me, discord.Member)
        assert me.id == server.bot.user.id

    def test_clean_prefix(self, server: Server) -> None:
        ctx = server.context("x")
        ctx.prefix = f"<@{server.bot.user.id}> "
        assert ctx.clean_prefix == f"@{ctx.me.display_name} "


class TestAsyncTwins:
    def test_get_guild_and_get_channel(self, server: Server) -> None:
        ctx = server.context("x")
        guild = server.run(ctx.get_guild())
        channel = server.run(ctx.get_channel())
        assert isinstance(guild, Guild)
        assert guild.id == server.guild.id
        assert isinstance(channel, TextChannel)
        assert channel.id == server.world.channel.id

    def test_get_channel_is_none_when_the_channel_is_not_cached(
        self, server: Server
    ) -> None:
        other = PartialMessageable(
            state=server.state, id=1750000000000000001, type=discord.ChannelType.text
        )
        ctx = server.context("x", channel=other)
        assert server.run(ctx.get_channel()) is None
        assert server.run(ctx._get_channel()).id == other.id

    def test_voice_client_reads_the_state(self, server: Server) -> None:
        ctx = server.context("x")
        assert ctx.voice_client is None
        marker = object()
        server.state._add_voice_client = None
        server.state._get_voice_client = lambda guild_id: (
            marker if guild_id == server.guild.id else None
        )
        assert ctx.voice_client is marker


class TestSend:
    def test_send_targets_the_message_channel(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = server.context("x")
        reply = server.add_message(server.world.channel, "pong")
        sent = AsyncMock(return_value=reply._raw_data)
        monkeypatch.setattr(server.state.http, "send_message", sent)
        message = server.run(ctx.send("hello"))
        assert sent.await_args.args[0] == server.world.channel.id
        assert message.content == "pong"

    def test_reply_goes_through_the_message(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = server.context("x")
        reply = AsyncMock(return_value="sent")
        monkeypatch.setattr(discord.Message, "reply", reply)
        assert server.run(ctx.reply("hello")) == "sent"
        reply.assert_awaited_once_with("hello")


@pytest.fixture
def people(server: Server) -> SimpleNamespace:
    mods = server.add_role(
        None,
        "Mods",
        position=2,
        permissions=discord.Permissions(view_channel=True, manage_messages=True),
    )
    admins = server.add_role(None, "Admins", position=3)
    alice = server.add_member(
        1300000000000000001, name="alice", roles=[mods.id, admins.id]
    )
    carol = server.add_member(1300000000000000002, name="carol")
    text = server.add_text("chat")
    return SimpleNamespace(
        mods=mods, admins=admins, alice=alice, carol=carol, text=text
    )


def give_bot(server: Server, *roles: int) -> Member:
    return server.add_member(server.world.me.id, name="botuser", roles=list(roles))


def run_check(server: Server, check: object, ctx: commands.Context) -> bool:
    return server.run(check.predicate(ctx))


class TestChecks:
    def test_has_role(self, server: Server, people: SimpleNamespace) -> None:
        member_ctx = server.context("x", author=people.alice)
        other_ctx = server.context("x", author=people.carol)
        for item in (people.mods.id, "Mods"):
            check = commands.has_role(item)
            assert run_check(server, check, member_ctx)
            with pytest.raises(commands.MissingRole):
                run_check(server, check, other_ctx)

    def test_has_role_in_a_direct_message(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        with pytest.raises(commands.NoPrivateMessage):
            run_check(server, commands.has_role("Mods"), ctx)

    def test_has_any_role(self, server: Server, people: SimpleNamespace) -> None:
        check = commands.has_any_role("Nothing", people.admins.id)
        assert run_check(server, check, server.context("x", author=people.alice))
        with pytest.raises(commands.MissingAnyRole):
            run_check(server, check, server.context("x", author=people.carol))

    def test_bot_has_role(self, server: Server, people: SimpleNamespace) -> None:
        ctx = server.context("x", author=people.alice)
        give_bot(server)
        with pytest.raises(commands.BotMissingRole):
            run_check(server, commands.bot_has_role(people.mods.id), ctx)
        with pytest.raises(commands.BotMissingAnyRole):
            run_check(server, commands.bot_has_any_role(people.mods.id), ctx)
        give_bot(server, people.mods.id)
        assert run_check(server, commands.bot_has_role(people.mods.id), ctx)
        assert run_check(server, commands.bot_has_any_role(people.mods.id), ctx)

    def test_has_permissions(self, server: Server, people: SimpleNamespace) -> None:
        check = commands.has_permissions(manage_messages=True)
        assert run_check(
            server, check, server.context("x", author=people.alice, channel=people.text)
        )
        with pytest.raises(commands.MissingPermissions) as error:
            run_check(
                server,
                check,
                server.context("x", author=people.carol, channel=people.text),
            )
        assert error.value.missing_permissions == ["manage_messages"]

    def test_has_permissions_in_a_direct_message(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        assert run_check(server, commands.has_permissions(manage_messages=True), ctx)

    def test_bot_has_permissions(self, server: Server, people: SimpleNamespace) -> None:
        ctx = server.context("x", author=people.alice, channel=people.text)
        check = commands.bot_has_permissions(manage_messages=True)
        give_bot(server)
        with pytest.raises(commands.BotMissingPermissions):
            run_check(server, check, ctx)
        give_bot(server, people.mods.id)
        assert run_check(server, check, ctx)

    def test_has_guild_permissions(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        check = commands.has_guild_permissions(manage_messages=True)
        assert run_check(server, check, server.context("x", author=people.alice))
        with pytest.raises(commands.MissingPermissions):
            run_check(server, check, server.context("x", author=people.carol))
        with pytest.raises(commands.NoPrivateMessage):
            run_check(server, check, server.context("x", in_guild=False))

    def test_bot_has_guild_permissions(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        check = commands.bot_has_guild_permissions(manage_messages=True)
        ctx = server.context("x", author=people.alice)
        give_bot(server)
        with pytest.raises(commands.BotMissingPermissions):
            run_check(server, check, ctx)
        give_bot(server, people.mods.id)
        assert run_check(server, check, ctx)

    def test_permissions_need_a_cached_channel(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        other = PartialMessageable(
            state=server.state, id=1750000000000000001, type=discord.ChannelType.text
        )
        ctx = server.context("x", author=people.alice, channel=other)
        with pytest.raises(commands.CheckFailure) as caught:
            run_check(server, commands.has_permissions(manage_messages=True), ctx)
        assert isinstance(caught.value, commands.CommandError)
        assert isinstance(caught.value, discord.CheckFailure)

    def test_guild_only_and_dm_only(self, server: Server) -> None:
        guild_ctx = server.context("x")
        dm_ctx = server.context("x", in_guild=False)
        assert run_check(server, commands.guild_only(), guild_ctx)
        assert run_check(server, commands.dm_only(), dm_ctx)
        with pytest.raises(commands.NoPrivateMessage):
            run_check(server, commands.guild_only(), dm_ctx)
        with pytest.raises(commands.PrivateMessageOnly):
            run_check(server, commands.dm_only(), guild_ctx)

    def test_is_nsfw(self, server: Server) -> None:
        adult = server.add_text("adult", nsfw=True)
        plain = server.add_text("plain", nsfw=False)
        thread = server.add_thread("under-adult", adult)
        check = commands.is_nsfw()
        assert run_check(server, check, server.context("x", channel=adult))
        assert run_check(server, check, server.context("x", channel=thread))
        assert run_check(server, check, server.context("x", in_guild=False))
        with pytest.raises(commands.NSFWChannelRequired):
            run_check(server, check, server.context("x", channel=plain))
