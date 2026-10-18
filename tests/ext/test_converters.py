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
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord.channel import TextChannel
from discord.ext import commands
from discord.guild import GuildActionsMixin, PartialGuild

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.ext.support import Server

ALICE = 1300000000000000001
CAROL = 1300000000000000002
BOBBY = 1300000000000000003
DAVE = 1300000000000000004
ERIN = 1300000000000000005
OUTSIDE = 1999999999999999999
FAR_GUILD = 1600000000000000001

pytestmark = pytest.mark.usefixtures("cast")


class Cast(SimpleNamespace):
    pass


@pytest.fixture
def cast(server: Server) -> Cast:
    alice = server.add_member(
        ALICE, name="alice", nick="Ally", global_name="Alice G", roles=[]
    )
    carol = server.add_member(
        CAROL, name="carol", global_name="Carol", discriminator="1234"
    )
    server.add_user(ALICE, "alice", global_name="Alice G")
    server.add_user(CAROL, "carol", global_name="Carol", discriminator="1234")
    server.add_user(BOBBY, "bobby", global_name="Bob")
    server.add_user(DAVE, "dave", global_name="Dave", discriminator="4321")
    mods = server.add_role(None, "Mods", position=2)
    general = server.world.channel
    category = server.add_category("cat1")
    voice = server.add_voice("lounge", parent_id=str(category.id))
    stage = server.add_stage("stage1")
    forum = server.add_forum("forum1")
    text = server.add_text("chat")
    thread = server.add_thread("thr1", general)
    far = PartialGuild(state=server.state, id=FAR_GUILD)
    return Cast(
        alice=alice,
        carol=carol,
        mods=mods,
        general=general,
        category=category,
        voice=voice,
        stage=stage,
        forum=forum,
        text=text,
        thread=thread,
        wave=server.add_emoji("wave"),
        far_emoji=server.add_emoji("faraway", far),
        sticker=server.add_sticker("hello"),
        far_sticker=server.add_sticker("distant", far),
    )


def convert(
    server: Server, converter: Any, ctx: commands.Context, argument: str
) -> Any:
    return server.run(converter.convert(ctx, argument))


def http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(SimpleNamespace(status=status, reason="x"), "x")


@pytest.fixture
def gateway(
    monkeypatch: pytest.MonkeyPatch, server: Server
) -> Callable[[bool], SimpleNamespace]:
    def install(ratelimited: bool = False) -> SimpleNamespace:
        calls = SimpleNamespace(
            query=AsyncMock(return_value=[]),
            fetch=AsyncMock(),
            ws=SimpleNamespace(is_ratelimited=lambda: ratelimited),
        )
        monkeypatch.setattr(GuildActionsMixin, "query_members", calls.query)
        monkeypatch.setattr(GuildActionsMixin, "fetch_member", calls.fetch)
        monkeypatch.setattr(server.bot, "_get_websocket", lambda *_a, **_k: calls.ws)
        return calls

    return install


class TestContextShape:
    def test_guild_context_matches_the_backend(
        self, server: Server, backend_kind: str
    ) -> None:
        ctx = server.context("x")
        if backend_kind == "memory":
            assert ctx.guild is server.guild
        else:
            assert isinstance(ctx.guild, PartialGuild)
            assert ctx.guild.id == server.guild.id


class TestMemberConverter:
    converter = commands.MemberConverter()

    @pytest.mark.parametrize(
        "argument",
        [str(ALICE), f"<@{ALICE}>", f"<@!{ALICE}>", "alice", "Ally", "Alice G"],
    )
    def test_cached_member(self, server: Server, cast: Cast, argument: str) -> None:
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument) == cast.alice

    @pytest.mark.parametrize("argument", ["carol#1234", "carol", "Carol"])
    def test_discriminator_and_name(
        self, server: Server, cast: Cast, argument: str
    ) -> None:
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument) == cast.carol

    def test_wrong_discriminator_is_not_a_match(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        gateway()
        ctx = server.context("x")
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, "alice#9999")

    def test_message_mention_is_used_before_querying(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        calls = gateway()
        user = server.add_user(ERIN, "erin")
        ctx = server.context("x", mentions=[user])
        result = convert(server, self.converter, ctx, f"<@{ERIN}>")
        assert result.id == ERIN
        calls.query.assert_not_called()

    def test_unknown_id_is_queried_over_the_gateway(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        calls = gateway()
        found = server.build_member(OUTSIDE, name="outsider")
        calls.query.return_value = [found]
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, str(OUTSIDE)) is found
        calls.query.assert_awaited_once()
        assert calls.query.await_args.kwargs["user_ids"] == [OUTSIDE]

    def test_uncached_guild_is_still_queried_through_its_handle(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        calls = gateway()
        found = server.build_member(OUTSIDE, name="outsider")
        calls.query.return_value = [found]
        ctx = server.context("x")
        server.run(server.state._remove_guild(server.guild))
        assert isinstance(ctx.guild, PartialGuild)
        assert convert(server, self.converter, ctx, str(OUTSIDE)) is found
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, "alice")

    def test_unknown_id_not_on_the_gateway(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        gateway()
        ctx = server.context("x")
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, str(OUTSIDE))

    def test_rate_limited_gateway_uses_http_and_caches(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        calls = gateway(ratelimited=True)
        found = server.build_member(OUTSIDE, name="outsider")
        calls.fetch.return_value = found
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, str(OUTSIDE)) is found
        calls.query.assert_not_called()
        cached = server.run(server.guild.get_member(OUTSIDE))
        assert cached is not None
        assert cached.id == OUTSIDE

    def test_rate_limited_gateway_http_failure(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        calls = gateway(ratelimited=True)
        calls.fetch.side_effect = http_error(discord.NotFound, 404)
        ctx = server.context("x")
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, str(OUTSIDE))

    @pytest.mark.parametrize(
        ("argument", "expected"),
        [
            ("outsider#1111", "outsider"),
            ("outsider", "outsider"),
            ("Outie", "outsider"),
            ("Out G", "outsider"),
        ],
    )
    def test_unknown_name_is_queried_over_the_gateway(
        self,
        server: Server,
        gateway: Callable[..., SimpleNamespace],
        argument: str,
        expected: str,
    ) -> None:
        calls = gateway()
        found = server.build_member(
            OUTSIDE,
            name="outsider",
            nick="Outie",
            global_name="Out G",
            discriminator="1111",
        )
        calls.query.return_value = [found]
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument).name == expected

    def test_unknown_name_not_on_the_gateway(
        self, server: Server, gateway: Callable[..., SimpleNamespace]
    ) -> None:
        gateway()
        ctx = server.context("x")
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, "nobody")

    @pytest.mark.parametrize("argument", [str(ALICE), "alice", "Ally"])
    def test_direct_message_searches_every_guild(
        self, server: Server, cast: Cast, argument: str
    ) -> None:
        ctx = server.context("x", in_guild=False)
        assert convert(server, self.converter, ctx, argument) == cast.alice

    @pytest.mark.parametrize("argument", [str(OUTSIDE), "nobody"])
    def test_direct_message_unknown(self, server: Server, argument: str) -> None:
        ctx = server.context("x", in_guild=False)
        with pytest.raises(commands.MemberNotFound):
            convert(server, self.converter, ctx, argument)


class TestUserConverter:
    converter = commands.UserConverter()

    @pytest.mark.parametrize("argument", [str(BOBBY), f"<@{BOBBY}>", f"<@!{BOBBY}>"])
    def test_cached_by_id(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument).name == "bobby"

    @pytest.mark.parametrize(
        ("argument", "expected"),
        [
            ("bobby", "bobby"),
            ("Bob", "bobby"),
            ("@bobby", "bobby"),
            ("dave#4321", "dave"),
            ("@dave#4321", "dave"),
            ("Dave", "dave"),
        ],
    )
    def test_cached_by_name(self, server: Server, argument: str, expected: str) -> None:
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument).name == expected

    def test_message_mention(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = AsyncMock()
        monkeypatch.setattr(server.bot, "fetch_user", fetch)
        mentioned = SimpleNamespace(id=OUTSIDE)
        ctx = server.context("x")
        ctx.message.mentions = [mentioned]
        assert convert(server, self.converter, ctx, str(OUTSIDE)) is mentioned
        fetch.assert_not_called()

    def test_unknown_id_is_fetched(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetched = SimpleNamespace(id=OUTSIDE)
        fetch = AsyncMock(return_value=fetched)
        monkeypatch.setattr(server.bot, "fetch_user", fetch)
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, str(OUTSIDE)) is fetched
        fetch.assert_awaited_once_with(OUTSIDE)

    def test_unknown_id_fetch_failure(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = AsyncMock(side_effect=http_error(discord.NotFound, 404))
        monkeypatch.setattr(server.bot, "fetch_user", fetch)
        ctx = server.context("x")
        with pytest.raises(commands.UserNotFound):
            convert(server, self.converter, ctx, str(OUTSIDE))

    @pytest.mark.parametrize("argument", ["nobody", "bobby#9999", "@nobody#1234"])
    def test_unknown_name(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.UserNotFound):
            convert(server, self.converter, ctx, argument)

    def test_same_result_in_direct_messages(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        assert convert(server, self.converter, ctx, "Bob").name == "bobby"


class TestPartialMessageConverter:
    converter = commands.PartialMessageConverter()

    def test_message_id_uses_the_context_channel(
        self, server: Server, cast: Cast
    ) -> None:
        ctx = server.context("x")
        result = convert(server, self.converter, ctx, "1500000000000000042")
        assert isinstance(result, discord.PartialMessage)
        assert result.id == 1500000000000000042
        assert result.channel.id == cast.general.id

    def test_channel_and_message_id(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        argument = f"{cast.text.id}-1500000000000000042"
        result = convert(server, self.converter, ctx, argument)
        assert result.channel == cast.text

    def test_url(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        url = (
            f"https://discord.com/channels/{server.guild.id}/{cast.text.id}"
            "/1500000000000000042"
        )
        result = convert(server, self.converter, ctx, url)
        assert result.channel == cast.text
        assert result.id == 1500000000000000042

    def test_url_without_guild_uses_the_global_channel_lookup(
        self, server: Server, cast: Cast
    ) -> None:
        ctx = server.context("x")
        url = f"https://discord.com/channels/@me/{cast.text.id}/1500000000000000042"
        result = convert(server, self.converter, ctx, url)
        assert result.channel == cast.text

    def test_unknown_channel(self, server: Server) -> None:
        ctx = server.context("x")
        argument = f"{OUTSIDE}-1500000000000000042"
        with pytest.raises(commands.ChannelNotFound):
            convert(server, self.converter, ctx, argument)

    def test_unknown_guild(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        url = (
            f"https://discord.com/channels/{OUTSIDE}/{cast.text.id}/1500000000000000042"
        )
        with pytest.raises(commands.ChannelNotFound):
            convert(server, self.converter, ctx, url)

    def test_malformed(self, server: Server) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.MessageNotFound):
            convert(server, self.converter, ctx, "not a message")


class TestMessageConverter:
    converter = commands.MessageConverter()

    def test_cached_message(self, server: Server, cast: Cast) -> None:
        message = server.add_message(cast.general, "stored")
        ctx = server.context("x")
        by_id = convert(server, self.converter, ctx, str(message.id))
        by_pair = convert(
            server, self.converter, ctx, f"{cast.general.id}-{message.id}"
        )
        assert by_id.id == by_pair.id == message.id
        assert by_id.content == "stored"

    def test_uncached_message_is_fetched_from_the_channel(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetched = SimpleNamespace(id=1500000000000000077)
        fetch = AsyncMock(return_value=fetched)
        monkeypatch.setattr(TextChannel, "fetch_message", fetch)
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, "1500000000000000077") is fetched
        fetch.assert_awaited_once_with(1500000000000000077)

    @pytest.mark.parametrize(
        ("status", "error", "expected"),
        [
            (404, discord.NotFound, commands.MessageNotFound),
            (403, discord.Forbidden, commands.ChannelNotReadable),
        ],
    )
    def test_fetch_errors(
        self,
        server: Server,
        monkeypatch: pytest.MonkeyPatch,
        status: int,
        error: type[discord.HTTPException],
        expected: type[Exception],
    ) -> None:
        monkeypatch.setattr(
            TextChannel,
            "fetch_message",
            AsyncMock(side_effect=http_error(error, status)),
        )
        ctx = server.context("x")
        with pytest.raises(expected):
            convert(server, self.converter, ctx, "1500000000000000077")

    def test_unknown_channel(self, server: Server) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.ChannelNotFound):
            convert(server, self.converter, ctx, f"{OUTSIDE}-1500000000000000077")


class TestChannelConverters:
    @pytest.mark.parametrize(
        ("converter", "argument_of", "expected_type"),
        [
            (commands.GuildChannelConverter, lambda c: c.text, TextChannel),
            (commands.TextChannelConverter, lambda c: c.text, TextChannel),
            (
                commands.VoiceChannelConverter,
                lambda c: c.voice,
                discord.VoiceChannel,
            ),
            (
                commands.StageChannelConverter,
                lambda c: c.stage,
                discord.StageChannel,
            ),
            (
                commands.CategoryChannelConverter,
                lambda c: c.category,
                discord.CategoryChannel,
            ),
            (
                commands.ForumChannelConverter,
                lambda c: c.forum,
                discord.ForumChannel,
            ),
        ],
    )
    @pytest.mark.parametrize("form", ["id", "mention", "name"])
    def test_resolution_forms(
        self,
        server: Server,
        cast: Cast,
        converter: type,
        argument_of: Callable[[Cast], Any],
        expected_type: type,
        form: str,
    ) -> None:
        channel = argument_of(cast)
        argument = {
            "id": str(channel.id),
            "mention": f"<#{channel.id}>",
            "name": channel.name,
        }[form]
        ctx = server.context("x")
        result = convert(server, converter(), ctx, argument)
        assert result == channel
        assert isinstance(result, expected_type)

    @pytest.mark.parametrize(
        "converter",
        [
            commands.TextChannelConverter,
            commands.VoiceChannelConverter,
            commands.StageChannelConverter,
            commands.CategoryChannelConverter,
            commands.ForumChannelConverter,
        ],
    )
    @pytest.mark.parametrize("form", ["id", "name", "missing"])
    def test_wrong_type_and_unknown(
        self, server: Server, cast: Cast, converter: type, form: str
    ) -> None:
        wrong = {
            commands.TextChannelConverter: cast.voice,
            commands.VoiceChannelConverter: cast.text,
            commands.StageChannelConverter: cast.text,
            commands.CategoryChannelConverter: cast.text,
            commands.ForumChannelConverter: cast.text,
        }[converter]
        argument = {"id": str(wrong.id), "name": wrong.name, "missing": "nowhere"}[form]
        ctx = server.context("x")
        with pytest.raises(commands.ChannelNotFound):
            convert(server, converter(), ctx, argument)

    def test_threads_are_not_guild_channels(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.ChannelNotFound):
            convert(server, commands.GuildChannelConverter(), ctx, str(cast.thread.id))

    def test_direct_message_searches_every_guild(
        self, server: Server, cast: Cast
    ) -> None:
        ctx = server.context("x", in_guild=False)
        by_id = convert(server, commands.TextChannelConverter(), ctx, str(cast.text.id))
        by_name = convert(server, commands.TextChannelConverter(), ctx, "chat")
        by_mention = convert(
            server, commands.GuildChannelConverter(), ctx, f"<#{cast.voice.id}>"
        )
        assert by_id == by_name == cast.text
        assert by_mention == cast.voice

    def test_direct_message_unknown(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        with pytest.raises(commands.ChannelNotFound):
            convert(server, commands.TextChannelConverter(), ctx, "nowhere")
        with pytest.raises(commands.ChannelNotFound):
            convert(server, commands.TextChannelConverter(), ctx, str(OUTSIDE))


class TestThreadConverter:
    converter = commands.ThreadConverter()

    @pytest.mark.parametrize("form", ["id", "mention", "name"])
    def test_resolution_forms(self, server: Server, cast: Cast, form: str) -> None:
        thread = cast.thread
        argument = {
            "id": str(thread.id),
            "mention": f"<#{thread.id}>",
            "name": thread.name,
        }[form]
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument) == thread

    @pytest.mark.parametrize("argument", ["nowhere", str(OUTSIDE)])
    def test_unknown(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.ThreadNotFound):
            convert(server, self.converter, ctx, argument)

    def test_a_channel_is_not_a_thread(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.ThreadNotFound):
            convert(server, self.converter, ctx, str(cast.text.id))

    def test_direct_message_has_no_threads(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x", in_guild=False)
        with pytest.raises(commands.ThreadNotFound):
            convert(server, self.converter, ctx, str(cast.thread.id))


class TestRoleConverter:
    converter = commands.RoleConverter()

    @pytest.mark.parametrize("form", ["id", "mention", "name"])
    def test_resolution_forms(self, server: Server, cast: Cast, form: str) -> None:
        role = cast.mods
        argument = {"id": str(role.id), "mention": f"<@&{role.id}>", "name": "Mods"}[
            form
        ]
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, argument) == role

    @pytest.mark.parametrize("argument", ["Nothing", str(OUTSIDE), f"<@&{OUTSIDE}>"])
    def test_unknown(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.RoleNotFound):
            convert(server, self.converter, ctx, argument)

    def test_private_message(self, server: Server) -> None:
        ctx = server.context("x", in_guild=False)
        with pytest.raises(commands.NoPrivateMessage):
            convert(server, self.converter, ctx, "Mods")


class TestGuildConverter:
    converter = commands.GuildConverter()

    def test_by_id_and_name(self, server: Server) -> None:
        ctx = server.context("x")
        assert (
            convert(server, self.converter, ctx, str(server.guild.id)) == server.guild
        )
        assert convert(server, self.converter, ctx, server.guild.name) == server.guild

    def test_unknown(self, server: Server) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.GuildNotFound):
            convert(server, self.converter, ctx, str(OUTSIDE))
        with pytest.raises(commands.GuildNotFound):
            convert(server, self.converter, ctx, "no such guild")


class TestEmojiConverter:
    converter = commands.EmojiConverter()

    def test_local_emoji(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        emoji = cast.wave
        assert convert(server, self.converter, ctx, str(emoji.id)) == emoji
        assert convert(server, self.converter, ctx, f"<:wave:{emoji.id}>") == emoji
        assert convert(server, self.converter, ctx, f"<a:wave:{emoji.id}>") == emoji
        assert convert(server, self.converter, ctx, "wave") == emoji

    def test_global_emoji(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        emoji = cast.far_emoji
        assert convert(server, self.converter, ctx, "faraway") == emoji
        assert convert(server, self.converter, ctx, str(emoji.id)) == emoji

    def test_direct_message_names(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x", in_guild=False)
        assert convert(server, self.converter, ctx, "wave") == cast.wave

    @pytest.mark.parametrize("argument", ["nothing", str(OUTSIDE), f"<:x:{OUTSIDE}>"])
    def test_unknown(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.EmojiNotFound):
            convert(server, self.converter, ctx, argument)


class TestGuildStickerConverter:
    converter = commands.GuildStickerConverter()

    def test_local_and_global(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        assert convert(server, self.converter, ctx, "hello") == cast.sticker
        assert (
            convert(server, self.converter, ctx, str(cast.sticker.id)) == cast.sticker
        )
        assert convert(server, self.converter, ctx, "distant") == cast.far_sticker
        assert (
            convert(server, self.converter, ctx, str(cast.far_sticker.id))
            == cast.far_sticker
        )

    def test_direct_message_names(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x", in_guild=False)
        assert convert(server, self.converter, ctx, "hello") == cast.sticker

    @pytest.mark.parametrize("argument", ["nothing", str(OUTSIDE)])
    def test_unknown(self, server: Server, argument: str) -> None:
        ctx = server.context("x")
        with pytest.raises(commands.GuildStickerNotFound):
            convert(server, self.converter, ctx, argument)


class TestCacheIndependentConverters:
    def test_object(self, server: Server) -> None:
        ctx = server.context("x")
        for argument in (
            str(OUTSIDE),
            f"<@{OUTSIDE}>",
            f"<@&{OUTSIDE}>",
            f"<#{OUTSIDE}>",
        ):
            result = convert(server, commands.ObjectConverter(), ctx, argument)
            assert result.id == OUTSIDE
        with pytest.raises(commands.ObjectNotFound):
            convert(server, commands.ObjectConverter(), ctx, "nope")

    def test_partial_emoji(self, server: Server) -> None:
        ctx = server.context("x")
        converter = commands.PartialEmojiConverter()
        custom = convert(server, converter, ctx, f"<a:spin:{OUTSIDE}>")
        assert (custom.animated, custom.name, custom.id) == (True, "spin", OUTSIDE)
        assert convert(server, converter, ctx, "\N{THUMBS UP SIGN}").id is None
        with pytest.raises(commands.PartialEmojiConversionFailure):
            convert(server, converter, ctx, "nope")

    def test_game_and_colour(self, server: Server) -> None:
        ctx = server.context("x")
        assert convert(server, commands.GameConverter(), ctx, "chess").name == "chess"
        assert convert(
            server, commands.ColourConverter(), ctx, "#ff0000"
        ) == discord.Colour(0xFF0000)
        with pytest.raises(commands.BadColourArgument):
            convert(server, commands.ColourConverter(), ctx, "not a colour")

    def test_invite(self, server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = server.context("x")
        invite = object()
        monkeypatch.setattr(server.bot, "fetch_invite", AsyncMock(return_value=invite))
        assert convert(server, commands.InviteConverter(), ctx, "abc") is invite
        monkeypatch.setattr(
            server.bot,
            "fetch_invite",
            AsyncMock(side_effect=http_error(discord.NotFound, 404)),
        )
        with pytest.raises(commands.BadInviteArgument):
            convert(server, commands.InviteConverter(), ctx, "abc")


class TestCleanContent:
    def clean(
        self, server: Server, ctx: commands.Context, text: str, **options: Any
    ) -> str:
        return convert(server, commands.clean_content(**options), ctx, text)

    def test_guild_mentions(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        text = f"hi <@{ALICE}> <@!{CAROL}> <@&{cast.mods.id}> <#{cast.general.id}>"
        assert self.clean(server, ctx, text) == (
            f"hi @Ally @Carol @Mods <#{cast.general.id}>"
        )

    def test_nicknames_and_names(self, server: Server) -> None:
        ctx = server.context("x")
        assert self.clean(server, ctx, f"<@{ALICE}>") == "@Ally"
        assert self.clean(server, ctx, f"<@{ALICE}>", use_nicknames=False) == "@alice"

    def test_roles_channels_and_unknowns(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x")
        assert self.clean(server, ctx, f"<@&{cast.mods.id}>") == "@Mods"
        assert self.clean(server, ctx, f"<@&{OUTSIDE}>") == "@deleted-role"
        assert self.clean(server, ctx, f"<@{OUTSIDE}>") == "@deleted-user"
        assert (
            self.clean(server, ctx, f"<#{cast.general.id}>", fix_channel_mentions=True)
            == f"#{cast.general.name}"
        )
        assert (
            self.clean(server, ctx, f"<#{OUTSIDE}>", fix_channel_mentions=True)
            == "#deleted-channel"
        )
        assert (
            self.clean(server, ctx, f"<#{cast.general.id}>") == f"<#{cast.general.id}>"
        )

    def test_message_mentions_take_precedence(self, server: Server) -> None:
        user = server.add_user(ERIN, "erin", global_name="Erin")
        ctx = server.context("x", mentions=[user])
        assert self.clean(server, ctx, f"<@{ERIN}>") == "@Erin"

    def test_repeated_mentions_and_markdown(self, server: Server) -> None:
        ctx = server.context("x")
        text = f"<@{ALICE}> and <@{ALICE}> **bold**"
        assert self.clean(server, ctx, text) == "@Ally and @Ally **bold**"
        assert (
            self.clean(server, ctx, text, remove_markdown=True)
            == "@Ally and @Ally bold"
        )
        assert self.clean(server, ctx, text, escape_markdown=True).endswith(
            r"\*\*bold\*\*"
        )

    def test_everyone_is_neutralised(self, server: Server) -> None:
        ctx = server.context("x")
        assert self.clean(server, ctx, "@everyone @here") == (
            "@\u200beveryone @\u200bhere"
        )

    def test_direct_message(self, server: Server, cast: Cast) -> None:
        ctx = server.context("x", in_guild=False)
        assert self.clean(server, ctx, f"<@{BOBBY}>") == "@bobby"
        assert self.clean(server, ctx, f"<@&{cast.mods.id}>") == "@deleted-role"
        assert self.clean(server, ctx, f"<@{OUTSIDE}>") == "@deleted-user"
        assert (
            self.clean(server, ctx, f"<#{cast.general.id}>", fix_channel_mentions=True)
            == f"<#{cast.general.id}>"
        )


class TestEndToEnd:
    def test_command_arguments_are_converted(self, server: Server, cast: Cast) -> None:
        seen: dict[str, Any] = {}

        @commands.command()
        async def probe(
            _ctx: commands.Context,
            member: discord.Member,
            role: discord.Role,
            channel: discord.TextChannel,
            emoji: discord.GuildEmoji,
            guild: discord.Guild,
        ) -> None:
            seen.update(
                member=member, role=role, channel=channel, emoji=emoji, guild=guild
            )

        server.bot.add_command(probe)
        content = f"!probe <@{ALICE}> Mods <#{cast.text.id}> wave {server.guild.id}"
        message = server.message(content, author=cast.alice)

        async def run() -> commands.Context:
            ctx = await server.bot.get_context(message)
            await server.bot.invoke(ctx)
            return ctx

        ctx = server.run(run())
        assert ctx.command is probe
        assert not ctx.command_failed
        assert seen["member"] == cast.alice
        assert seen["role"] == cast.mods
        assert seen["channel"] == cast.text
        assert seen["emoji"] == cast.wave
        assert seen["guild"] == server.guild
