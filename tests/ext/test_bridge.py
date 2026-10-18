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

# ruff: noqa: PT018, I002

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord import SlashCommandOptionType
from discord.ext import bridge, commands
from discord.ext.bridge import core as bridge_core
from discord.flags import MemberCacheFlags
from discord.guild import GuildActionsMixin
from tests.ext.support import Server
from tests.models.context import World

USER = 1300000000000000009


def _callback() -> Any:
    async def callback(ctx: Any) -> None: ...

    return callback


@pytest.fixture
def bbot(loop: asyncio.AbstractEventLoop) -> bridge.Bot:
    bot = bridge.Bot(command_prefix="!", intents=discord.Intents.all(), loop=loop)
    bot._connection.member_cache_flags = MemberCacheFlags.all()
    return bot


@pytest.fixture
def bserver(bbot: bridge.Bot) -> Server:
    return Server(bbot, World(bbot._connection))


def prefixed(server: Server, content: str) -> bridge.BridgeExtContext:
    author = server.add_user(USER, "bob")
    message = server.message(content, author=author)
    return server.run(server.bot.get_context(message))


def app_ctx(server: Server, **data: Any) -> bridge.BridgeApplicationContext:
    interaction = SimpleNamespace(
        _state=server.state, data=data or {}, channel=server.world.channel
    )
    return bridge.BridgeApplicationContext(server.bot, interaction)


@pytest.fixture
def events(bserver: Server, monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        bserver.bot, "dispatch", lambda event, *args, **kw: seen.append((event, *args))
    )
    return seen


class TestBridgeCommand:
    def test_variants_and_registration(self, bserver: Server) -> None:
        @bserver.bot.bridge_command(description="says hi", brief="short")
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        assert isinstance(ping.slash_variant, bridge.BridgeSlashCommand)
        assert isinstance(ping.ext_variant, bridge.BridgeExtCommand)
        assert ping in bserver.bot.bridge_commands
        assert bserver.bot.get_command("ping") is ping.ext_variant
        assert ping.slash_variant in bserver.bot.pending_application_commands
        assert ping.slash_variant.brief == "short"
        assert ping.name == "ping"

    def test_attribute_lookup_prefers_slash_then_ext(self, bserver: Server) -> None:
        @bserver.bot.bridge_command(description="d")
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        assert ping.description == "d"
        assert ping.aliases == []
        with pytest.raises(AttributeError, match="no attribute 'nonexistent'"):
            ping.nonexistent  # noqa: B018

    def test_special_attributes_are_not_forwarded(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        ping.parent = None
        assert ping.parent is None
        del ping.__dict__["parent"]
        with pytest.raises(AttributeError):
            ping.parent  # noqa: B018

    def test_setting_attributes_updates_both_variants(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        ping.hidden = True
        assert ping.slash_variant.hidden is True
        assert ping.ext_variant.hidden is True

    def test_localizations(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        ping.name_localizations = {"fr": "pong"}
        ping.description_localizations = {"fr": "desc"}
        assert ping.slash_variant.name_localizations == {"fr": "pong"}
        assert ping.name_localizations == {"fr": "pong"}
        assert ping.description_localizations == {"fr": "desc"}

    def test_decorators_apply_to_both_variants(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        async def handler(ctx: Any, error: Any) -> None: ...

        async def hook(ctx: Any) -> None: ...

        assert ping.error(handler) is handler
        assert ping.before_invoke(hook) is hook
        assert ping.after_invoke(hook) is hook
        assert ping.ext_variant.on_error is handler
        assert ping.ext_variant._before_invoke is hook
        assert ping.ext_variant._after_invoke is hook
        assert ping.slash_variant.has_error_handler()

    def test_invoke_picks_the_variant(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        ping.slash_variant.invoke = AsyncMock(return_value="slash")
        ping.ext_variant.invoke = AsyncMock(return_value="ext")
        slash_ctx = app_ctx(bserver)
        ext_ctx = prefixed(bserver, "!ping")
        assert bserver.run(ping.invoke(slash_ctx)) == "slash"
        assert bserver.run(ping.invoke(ext_ctx)) == "ext"
        assert slash_ctx.is_app and not ext_ctx.is_app

    def test_bridge_options_in_ext_command_are_validated(self) -> None:
        async def cb(ctx: Any, value: discord.Option(int) = 1) -> None: ...

        with pytest.raises(TypeError, match="not supported in bridge commands"):
            bridge.BridgeExtCommand(cb)

    def test_prefixed_invocation_and_events(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        ran: list[int] = []

        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext, n: int = 1) -> None:
            ran.append(n)

        ctx = prefixed(bserver, "!ping 4")
        assert isinstance(ctx, bridge.BridgeExtContext)
        bserver.run(bserver.bot.invoke(ctx))
        assert ran == [4]
        assert [e[0] for e in events] == [
            "command",
            "bridge_command",
            "command_completion",
            "bridge_command_completion",
        ]

    def test_prefixed_failure_dispatches_bridge_error(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext, n: int) -> None: ...

        bserver.run(bserver.bot.invoke(prefixed(bserver, "!ping x")))
        names = [e[0] for e in events]
        assert names[-2:] == ["command_error", "bridge_command_error"]

    def test_global_check_once_failure(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        @bserver.bot.bridge_command()
        async def ping(ctx: bridge.BridgeContext) -> None: ...

        bserver.bot.check_once(lambda ctx: False)
        bserver.run(bserver.bot.invoke(prefixed(bserver, "!ping")))
        error = next(e for e in events if e[0] == "command_error")[2]
        assert isinstance(error, commands.CheckFailure)

    def test_unknown_prefixed_command(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        bserver.run(bserver.bot.invoke(prefixed(bserver, "!nope")))
        assert events[0][0] == "command_error"
        assert isinstance(events[0][2], commands.CommandNotFound)

    def test_plain_commands_do_not_dispatch_bridge_events(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        @bserver.bot.command()
        async def plain(ctx: commands.Context) -> None: ...

        bserver.run(bserver.bot.invoke(prefixed(bserver, "!plain")))
        assert [e[0] for e in events] == ["command", "command_completion"]

    def test_get_context_classes(self, bserver: Server) -> None:
        assert isinstance(prefixed(bserver, "!x"), bridge.BridgeExtContext)

        class Mine(bridge.BridgeExtContext): ...

        message = bserver.message("!x", author=bserver.add_user(USER, "bob"))
        assert isinstance(bserver.run(bserver.bot.get_context(message, cls=Mine)), Mine)

    def test_get_application_context(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        interaction = SimpleNamespace(_state=bserver.state, data={})
        ctx = bserver.run(bserver.bot.get_application_context(interaction))
        assert isinstance(ctx, bridge.BridgeApplicationContext)

        class Mine(bridge.BridgeApplicationContext): ...

        assert isinstance(
            bserver.run(bserver.bot.get_application_context(interaction, cls=Mine)),
            Mine,
        )


class TestApplicationInvocation:
    def test_dispatches_and_completes(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        slash = bridge.BridgeSlashCommand(_callback(), description="x", name="s")
        slash.invoke = AsyncMock()
        ctx = SimpleNamespace(command=slash)
        bserver.run(bserver.bot.invoke_application_command(ctx))
        assert [e[0] for e in events] == [
            "application_command",
            "bridge_command",
            "application_command_completion",
            "bridge_command_completion",
        ]

    def test_failure_goes_to_dispatch_error(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        error = discord.DiscordException("x")
        slash = bridge.BridgeSlashCommand(_callback(), description="x", name="s")
        slash.invoke = AsyncMock(side_effect=error)
        slash.dispatch_error = AsyncMock()
        ctx = SimpleNamespace(command=slash)
        bserver.run(bserver.bot.invoke_application_command(ctx))
        slash.dispatch_error.assert_awaited_once_with(ctx, error)
        assert "application_command_completion" not in [e[0] for e in events]

    def test_check_once_failure(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        bserver.bot.check_once(lambda ctx: False)
        slash = bridge.BridgeSlashCommand(_callback(), description="x", name="s")
        slash.invoke = AsyncMock()
        slash.dispatch_error = AsyncMock()
        ctx = SimpleNamespace(command=slash)
        bserver.run(bserver.bot.invoke_application_command(ctx))
        slash.invoke.assert_not_awaited()
        assert isinstance(slash.dispatch_error.await_args.args[1], discord.CheckFailure)

    def test_plain_application_command_has_no_bridge_events(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        slash = discord.SlashCommand(_callback(), description="x", name="s")
        slash.invoke = AsyncMock()
        bserver.run(
            bserver.bot.invoke_application_command(SimpleNamespace(command=slash))
        )
        assert [e[0] for e in events] == [
            "application_command",
            "application_command_completion",
        ]

    def test_slash_error_dispatches_bridge_error(
        self, bserver: Server, events: list[tuple[Any, ...]]
    ) -> None:
        slash = bridge.BridgeSlashCommand(_callback(), description="x", name="s")
        ctx = SimpleNamespace(bot=bserver.bot, command=slash, interaction=None)
        error = discord.DiscordException("x")
        bserver.run(slash.dispatch_error(ctx, error))
        assert events[-1] == ("bridge_command_error", ctx, error)


class TestBridgeGroup:
    @pytest.fixture
    def group(self, bserver: Server) -> bridge.BridgeCommandGroup:
        @bserver.bot.bridge_group()
        async def cfg(ctx: bridge.BridgeContext) -> None: ...

        return cfg

    def test_group_registration(
        self, bserver: Server, group: bridge.BridgeCommandGroup
    ) -> None:
        assert isinstance(group.slash_variant, bridge.BridgeSlashGroup)
        assert isinstance(group.ext_variant, bridge.BridgeExtGroup)
        assert bserver.bot.get_command("cfg") is group.ext_variant
        assert group.mapped is None
        assert group.name == "cfg"

    def test_subcommands_and_walking(
        self, bserver: Server, group: bridge.BridgeCommandGroup
    ) -> None:
        @group.command(description="toggle it")
        async def toggle(ctx: bridge.BridgeContext) -> None: ...

        @group.subgroup(name="deep", description="deeper")
        async def deep(ctx: bridge.BridgeContext) -> None: ...

        @deep.command()
        async def leaf(ctx: bridge.BridgeContext) -> None: ...

        assert group.subcommands == [toggle, deep]
        assert toggle.parent is group
        assert list(group.walk_commands()) == [toggle, deep, leaf]
        assert list(bserver.bot.walk_bridge_commands()) == [group, toggle, deep, leaf]
        assert bserver.bot.get_command("cfg toggle") is toggle.ext_variant
        assert bserver.bot.get_command("cfg deep leaf") is leaf.ext_variant

    def test_subgroup_defaults_to_the_function_name(
        self, group: bridge.BridgeCommandGroup
    ) -> None:
        @group.subgroup()
        async def sub(ctx: bridge.BridgeContext) -> None: ...

        assert sub.name == "sub"

    def test_map_to(self, bserver: Server) -> None:
        @bserver.bot.bridge_group()
        @bridge.map_to("show", "shows it")
        async def cfg(ctx: bridge.BridgeContext) -> None: ...

        assert cfg.mapped is not None
        assert cfg.mapped.name == "show"
        assert cfg.mapped.description == "shows it"

    def test_prefixed_group_invocation(self, bserver: Server) -> None:
        ran: list[str] = []

        @bserver.bot.bridge_group(invoke_without_command=True)
        async def cfg(ctx: bridge.BridgeContext) -> None:
            ran.append("cfg")

        @cfg.command()
        async def toggle(ctx: bridge.BridgeContext) -> None:
            ran.append("toggle")

        bserver.run(bserver.bot.invoke(prefixed(bserver, "!cfg toggle")))
        assert ran == ["toggle"]

    def test_slash_group_invokes_a_subcommand(
        self, bserver: Server, group: bridge.BridgeCommandGroup
    ) -> None:
        @group.command()
        async def toggle(ctx: bridge.BridgeContext) -> None: ...

        toggle.slash_variant.invoke = AsyncMock()
        ctx = app_ctx(
            bserver,
            options=[{"name": "toggle", "options": []}],
            resolved={"users": {}},
        )
        bserver.run(group.slash_variant._invoke(ctx))
        toggle.slash_variant.invoke.assert_awaited_once_with(ctx)
        assert ctx.interaction.data["name"] == "toggle"
        assert ctx.interaction.data["resolved"] == {"users": {}}

    def test_slash_group_without_options_runs_the_callback_command(
        self, bserver: Server, group: bridge.BridgeCommandGroup
    ) -> None:
        ctx = app_ctx(bserver)
        with pytest.MonkeyPatch.context() as mp:
            invoke = AsyncMock()
            mp.setattr(bridge.BridgeSlashCommand, "invoke", invoke)
            bserver.run(group.slash_variant._invoke(ctx))
            bserver.run(group.slash_variant._invoke(ctx))
        assert invoke.await_count == 2
        assert isinstance(ctx.command, bridge.BridgeSlashCommand)


class TestPermissionDecorators:
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_guild_only(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        @bridge.guild_only()
        async def a(ctx: bridge.BridgeContext) -> None: ...

        assert a.callback.__guild_only__ is True
        assert a.ext_variant.checks

        slash = discord.SlashCommand(_callback(), description="d", name="x")
        assert bridge.guild_only()(slash) is slash
        assert slash.guild_only is True

    def test_is_nsfw(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        @bridge.is_nsfw()
        async def a(ctx: bridge.BridgeContext) -> None: ...

        assert a.callback.__nsfw__ is True
        slash = discord.SlashCommand(_callback(), description="d", name="x")
        bridge.is_nsfw()(slash)
        assert slash.nsfw is True

    def test_has_permissions(self, bserver: Server) -> None:
        @bserver.bot.bridge_command()
        @bridge.has_permissions(manage_messages=True)
        async def a(ctx: bridge.BridgeContext) -> None: ...

        assert a.slash_variant.default_member_permissions.manage_messages
        assert a.ext_variant.checks
        slash = discord.SlashCommand(_callback(), description="d", name="x")
        bridge.has_permissions(ban_members=True)(slash)
        assert slash.default_member_permissions.ban_members

    def test_group_picks_up_default_permissions(self, bserver: Server) -> None:
        @bserver.bot.bridge_group()
        @bridge.has_permissions(manage_messages=True)
        async def g(ctx: bridge.BridgeContext) -> None: ...

        assert g.slash_variant.default_member_permissions.manage_messages


class TestConverters:
    def convert(self, server: Server, converter: Any, argument: Any) -> Any:
        return server.run(converter().convert(server.context("x"), argument))

    def test_boolean(self, bserver: Server) -> None:
        assert self.convert(bserver, bridge_core.BooleanConverter, "yes") is True
        assert self.convert(bserver, bridge_core.BooleanConverter, "off") is False
        with pytest.raises(commands.BadBoolArgument):
            self.convert(bserver, bridge_core.BooleanConverter, "maybe")

    def test_attachment(self, bserver: Server) -> None:
        ctx = bserver.context("x")
        ctx.message.attachments = [object()]
        first = ctx.message.attachments[0]
        assert bserver.run(bridge_core.AttachmentConverter().convert(ctx, "")) is first
        ctx.message.attachments = []
        with pytest.raises(commands.BadArgument, match="attachment"):
            bserver.run(bridge_core.AttachmentConverter().convert(ctx, ""))

    def test_mentionable(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            GuildActionsMixin, "query_members", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(GuildActionsMixin, "fetch_member", AsyncMock())
        monkeypatch.setattr(
            bserver.bot,
            "_get_websocket",
            lambda *_a, **_k: SimpleNamespace(is_ratelimited=lambda: False),
        )
        role = bserver.add_role(None, "Mods", position=2)
        member = bserver.add_member(USER, name="bob")
        bserver.add_user(USER, "bob")
        conv = bridge_core.MentionableConverter
        assert self.convert(bserver, conv, str(role.id)).id == role.id
        assert self.convert(bserver, conv, str(member.id)).id == member.id
        dm = bserver.context("x", in_guild=False)
        user = bserver.add_user(1300000000000000010, "dm_user")
        assert bserver.run(conv().convert(dm, str(user.id))).id == user.id
        with pytest.raises(commands.BadArgument):
            self.convert(bserver, conv, "99999")

    def test_attachment_parameter_in_prefixed_commands(self, bserver: Server) -> None:
        got: list[Any] = []

        @bserver.bot.bridge_command()
        async def up(ctx: bridge.BridgeContext, file: discord.Attachment) -> None:
            got.append(file)

        ctx = prefixed(bserver, "!up")
        ctx.message.attachments = ["A"]
        bserver.run(bserver.bot.invoke(ctx))
        assert got == ["A"]


class TestBridgeOption:
    def option(self, *args: Any, **kwargs: Any) -> bridge.BridgeOption:
        return bridge.BridgeOption(*args, **kwargs)

    def test_mapped_converters(self, bserver: Server) -> None:
        ctx = bserver.context("x")
        run = bserver.run
        assert run(self.option(int).convert(ctx, "5")) == 5
        assert run(self.option(str).convert(ctx, "a")) == "a"
        assert run(self.option(float).convert(ctx, "1.5")) == 1.5
        assert run(self.option(SlashCommandOptionType.boolean).convert(ctx, "yes"))
        assert run(self.option(SlashCommandOptionType.number).convert(ctx, "2")) == 2.0

    def test_invalid_value_is_a_bad_argument(self, bserver: Server) -> None:
        with pytest.raises(commands.BadArgument):
            bserver.run(self.option(int).convert(bserver.context("x"), "abc"))

    def test_custom_converter(self, bserver: Server) -> None:
        class Upper(commands.Converter):
            async def convert(self, ctx: Any, argument: str) -> str:
                return argument.upper()

        option = self.option(str, converter=Upper)
        assert bserver.run(option.convert(bserver.context("x"), "a")) == "A"

    def test_unknown_input_type(self, bserver: Server) -> None:
        option = self.option(SlashCommandOptionType.string)
        option.converter = None
        option.input_type = object()
        with pytest.raises(TypeError, match="Invalid converter"):
            bserver.run(option.convert(bserver.context("x"), "a"))

    def test_choices(self, bserver: Server) -> None:
        option = self.option(
            str,
            choices=[
                discord.OptionChoice("One", "1"),
                discord.OptionChoice("Two", "2"),
            ],
        )
        ctx = bserver.context("x")
        assert bserver.run(option.convert(ctx, "One")) == "1"
        assert bserver.run(option.convert(ctx, "2")) == "2"
        with pytest.raises(commands.BadArgument):
            bserver.run(option.convert(ctx, "Three"))

    def test_role_converter_mapping(self, bserver: Server) -> None:
        role = bserver.add_role(None, "Mods")
        option = self.option(SlashCommandOptionType.role)
        assert (
            bserver.run(option.convert(bserver.context("x"), str(role.id))).id
            == role.id
        )

    def test_bridge_option_decorator(self) -> None:
        @bridge.bridge_option("count", int, description="how many", parameter_name="n")
        async def cb(ctx: Any, n: int = 1) -> None: ...

        option = cb.__annotations__["n"]
        assert isinstance(option, bridge.BridgeOption)
        assert option.name == "count"
        assert option.description == "how many"

    def test_bridge_option_decorator_infers_the_type(self) -> None:
        async def cb(ctx: Any, count: int = 1) -> None: ...

        cb.__annotations__["count"] = int
        bridge.bridge_option("count")(cb)
        assert cb.__annotations__["count"].input_type is SlashCommandOptionType.integer

        async def other(ctx: Any, text: Any = None) -> None: ...

        other.__annotations__.pop("text", None)
        bridge.bridge_option("text", type=str)(other)
        assert other.__annotations__["text"].input_type is SlashCommandOptionType.string
        bare = AsyncMock()
        bare.__annotations__ = {}
        bridge.bridge_option("x")(bare)
        assert bare.__annotations__["x"].input_type is SlashCommandOptionType.string

    def test_bridge_option_in_prefixed_command(self, bserver: Server) -> None:
        got: list[Any] = []

        @bserver.bot.bridge_command()
        @bridge.bridge_option("n", int)
        async def cmd(ctx: bridge.BridgeContext, n: int) -> None:
            got.append(n)

        bserver.run(bserver.bot.invoke(prefixed(bserver, "!cmd 9")))
        assert got == [9]


class TestContexts:
    def test_ext_context_respond_edit_delete(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = prefixed(bserver, "!x")
        first, second = MagicMock(), MagicMock()
        first.edit = AsyncMock(return_value="edited")
        first.delete = AsyncMock()
        reply = AsyncMock(side_effect=[first, second])
        monkeypatch.setattr(commands.Context, "reply", reply)
        assert bserver.run(ctx.edit(content="n")) is None
        bserver.run(ctx.delete())
        assert bserver.run(ctx.respond("hi", ephemeral=True)) is first
        assert bserver.run(ctx.reply("again")) is second
        reply.assert_any_await("hi")
        assert ctx._original_response_message is first
        assert bserver.run(ctx.edit(content="n")) == "edited"
        bserver.run(ctx.delete(delay=3, reason="r"))
        first.delete.assert_awaited_once_with(delay=3, reason="r")

    def test_ext_context_defer_and_typing(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = prefixed(bserver, "!x")
        trigger = AsyncMock()
        monkeypatch.setattr(commands.Context, "trigger_typing", trigger, raising=False)
        bserver.run(ctx.defer(ephemeral=True))
        trigger.assert_awaited_once_with()
        sentinel = object()
        monkeypatch.setattr(
            commands.Context, "typing", lambda self, *a, **k: sentinel, raising=False
        )
        assert ctx.typing(ephemeral=True) is sentinel

    def test_application_context_forwarding(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = app_ctx(bserver)
        respond, defer, edit = (
            AsyncMock(return_value="r"),
            AsyncMock(),
            AsyncMock(return_value="e"),
        )
        monkeypatch.setattr(discord.ApplicationContext, "respond", respond)
        monkeypatch.setattr(discord.ApplicationContext, "defer", defer)
        monkeypatch.setattr(discord.ApplicationContext, "edit", edit)
        assert bserver.run(ctx.respond("hi")) == "r"
        assert bserver.run(ctx.reply("hi")) == "r"
        bserver.run(ctx.defer(ephemeral=True))
        assert bserver.run(ctx.edit(content="x")) == "e"
        assert respond.await_count == 2
        defer.assert_awaited_once_with(ephemeral=True)

    def test_defer_typing(
        self, bserver: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = app_ctx(bserver)
        defer = AsyncMock()
        monkeypatch.setattr(discord.ApplicationContext, "defer", defer)

        async def scenario() -> None:
            async with ctx.typing(ephemeral=True) as typing:
                assert isinstance(typing, bridge.DeferTyping)
                await typing.task
            with ctx.typing() as typing:
                task = typing.task
                await task
            assert task.done()

        bserver.run(scenario())
        assert defer.await_args_list[0].kwargs == {"ephemeral": True}
        assert defer.await_args_list[1].kwargs == {"ephemeral": False}

    def test_defer_typing_cancels_on_exit(self, bserver: Server) -> None:
        ctx = app_ctx(bserver)
        ctx.defer = AsyncMock()

        async def scenario() -> bool:
            typing = bridge.DeferTyping(ctx)
            typing.__enter__()
            typing.__exit__(None, None, None)
            await asyncio.wait([typing.task])
            return typing.task.cancelled() or typing.task.done()

        assert bserver.run(scenario())
