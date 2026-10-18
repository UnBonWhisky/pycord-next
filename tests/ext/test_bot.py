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
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from tests.ext.support import Server

USER = 1300000000000000009


def incoming(server: Server, content: str) -> discord.Message:
    return server.message(content, author=server.add_user(USER, "bob"))


def context_for(server: Server, content: str, bot: Any = None) -> commands.Context:
    return server.run((bot or server.bot).get_context(incoming(server, content)))


class TestWhenMentioned:
    def test_when_mentioned(self, server: Server) -> None:
        uid = server.bot.user.id
        assert commands.when_mentioned(server.bot, MagicMock()) == [
            f"<@{uid}> ",
            f"<@!{uid}> ",
        ]

    def test_when_mentioned_or(self, server: Server) -> None:
        uid = server.bot.user.id
        prefixes = commands.when_mentioned_or("!", "?")(server.bot, MagicMock())
        assert prefixes == [f"<@{uid}> ", f"<@!{uid}> ", "!", "?"]


class TestGetPrefix:
    def test_string(self, server: Server) -> None:
        assert server.run(server.bot.get_prefix(incoming(server, "x"))) == "!"

    def test_iterable(self, server: Server) -> None:
        server.bot.command_prefix = ("a", "b")
        assert server.run(server.bot.get_prefix(incoming(server, "x"))) == ["a", "b"]

    def test_callable(self, server: Server) -> None:
        server.bot.command_prefix = lambda bot, msg: ["x"]
        assert server.run(server.bot.get_prefix(incoming(server, "x"))) == ["x"]

    def test_coroutine_callable(self, server: Server) -> None:
        async def prefix(bot: Any, msg: Any) -> str:
            return "?"

        server.bot.command_prefix = prefix
        assert server.run(server.bot.get_prefix(incoming(server, "x"))) == "?"

    def test_invalid_type(self, server: Server) -> None:
        server.bot.command_prefix = 5
        with pytest.raises(TypeError, match="command_prefix must be plain string"):
            server.run(server.bot.get_prefix(incoming(server, "x")))

    def test_empty_iterable(self, server: Server) -> None:
        server.bot.command_prefix = []
        with pytest.raises(ValueError, match="at least one prefix"):
            server.run(server.bot.get_prefix(incoming(server, "x")))

    def test_generator_errors_are_not_replaced(self, server: Server) -> None:
        def broken() -> Any:
            raise TypeError("inner")
            yield

        server.bot.command_prefix = broken()
        with pytest.raises(TypeError, match="inner"):
            server.run(server.bot.get_prefix(incoming(server, "x")))


class TestGetContext:
    def test_string_prefix(self, server: Server) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context) -> None: ...

        ctx = context_for(server, "!ping now")
        assert ctx.valid
        assert (ctx.prefix, ctx.invoked_with, ctx.command) == ("!", "ping", ping)

    def test_unknown_command_is_not_valid(self, server: Server) -> None:
        ctx = context_for(server, "!nope")
        assert not ctx.valid
        assert ctx.invoked_with == "nope"

    def test_wrong_prefix(self, server: Server) -> None:
        ctx = context_for(server, "?ping")
        assert ctx.prefix is None
        assert ctx.invoked_with is None

    def test_list_prefix(self, server: Server) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context) -> None: ...

        server.bot.command_prefix = ["!!", "!"]
        ctx = context_for(server, "!!ping")
        assert ctx.prefix == "!!"
        assert ctx.command is ping
        assert context_for(server, "?ping").prefix is None

    def test_strip_after_prefix(self, server: Server) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context) -> None: ...

        assert context_for(server, "!  ping").command is None
        server.bot.strip_after_prefix = True
        assert context_for(server, "!  ping").command is ping

    def test_bot_own_messages_are_never_commands(self, server: Server) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context) -> None: ...

        ctx = server.run(server.bot.get_context(server.message("!ping")))
        assert ctx.prefix is None

    def test_custom_context_class(self, server: Server) -> None:
        class Mine(commands.Context): ...

        ctx = server.run(server.bot.get_context(incoming(server, "!x"), cls=Mine))
        assert isinstance(ctx, Mine)

    def test_non_string_entry_in_a_prefix_list(self, server: Server) -> None:
        server.bot.command_prefix = ["!", 5]
        with pytest.raises(TypeError, match="must contain only strings"):
            server.run(server.bot.get_context(incoming(server, "?x")))

    def test_non_list_iterable_with_bad_entries(self, server: Server) -> None:
        server.bot.get_prefix = AsyncMock(return_value=5)
        with pytest.raises(TypeError, match="must return either a string or a list"):
            server.run(server.bot.get_context(incoming(server, "!x")))

    def test_unexpected_type_error_is_reraised(self, server: Server) -> None:
        server.bot.get_prefix = AsyncMock(return_value=["!"])
        message = incoming(server, "!x")
        server.bot.get_prefix.return_value = ["!", "?"]
        original = discord.utils.find

        def boom(*args: Any, **kwargs: Any) -> None:
            raise TypeError("inner")

        discord.utils.find = boom
        try:
            with pytest.raises(TypeError, match="inner"):
                server.run(server.bot.get_context(message))
        finally:
            discord.utils.find = original


class TestInvoke:
    def test_runs_the_command_and_dispatches(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ran: list[int] = []

        @server.bot.command()
        async def ping(ctx: commands.Context, n: int) -> None:
            ran.append(n)

        dispatch = MagicMock()
        monkeypatch.setattr(server.bot, "dispatch", dispatch)
        ctx = context_for(server, "!ping 4")
        server.run(server.bot.invoke(ctx))
        assert ran == [4]
        assert [c.args[0] for c in dispatch.call_args_list] == [
            "command",
            "command_completion",
        ]

    def test_failing_command_dispatches_error(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context, n: int) -> None: ...

        dispatch = MagicMock()
        monkeypatch.setattr(server.bot, "dispatch", dispatch)
        server.run(server.bot.invoke(context_for(server, "!ping x")))
        names = [c.args[0] for c in dispatch.call_args_list]
        assert names == ["command", "command_error"]
        assert isinstance(dispatch.call_args.args[2], commands.BadArgument)

    def test_global_check_once(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ran: list[int] = []

        @server.bot.command()
        async def ping(ctx: commands.Context) -> None:
            ran.append(1)

        server.bot.check_once(lambda ctx: False)
        dispatch = MagicMock()
        monkeypatch.setattr(server.bot, "dispatch", dispatch)
        server.run(server.bot.invoke(context_for(server, "!ping")))
        assert ran == []
        assert isinstance(dispatch.call_args.args[2], commands.CheckFailure)

    def test_unknown_command(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dispatch = MagicMock()
        monkeypatch.setattr(server.bot, "dispatch", dispatch)
        server.run(server.bot.invoke(context_for(server, "!nope")))
        name, _, error = dispatch.call_args.args
        assert name == "command_error"
        assert isinstance(error, commands.CommandNotFound)

    def test_not_a_command_message(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dispatch = MagicMock()
        monkeypatch.setattr(server.bot, "dispatch", dispatch)
        server.run(server.bot.invoke(context_for(server, "hello")))
        dispatch.assert_not_called()


class TestProcessCommands:
    def test_bots_are_ignored(self, server: Server) -> None:
        server.bot.get_context = AsyncMock()
        message = incoming(server, "!x")
        message.author._user.bot = True
        server.run(server.bot.process_commands(message))
        server.bot.get_context.assert_not_awaited()

    def test_on_message_processes_commands(self, server: Server) -> None:
        ran: list[int] = []

        @server.bot.command()
        async def ping(ctx: commands.Context) -> None:
            ran.append(1)

        server.run(server.bot.on_message(incoming(server, "!ping")))
        assert ran == [1]


class TestChecks:
    def test_no_checks(self, server: Server) -> None:
        assert server.run(server.bot.can_run(server.context("x"))) is True

    def test_global_checks(self, server: Server) -> None:
        server.bot.add_check(lambda ctx: True)
        assert server.run(server.bot.can_run(server.context("x"))) is True
        server.bot.add_check(lambda ctx: False)
        assert server.run(server.bot.can_run(server.context("x"))) is False

    def test_check_once_is_separate(self, server: Server) -> None:
        server.bot.check_once(lambda ctx: False)
        ctx = server.context("x")
        assert server.run(server.bot.can_run(ctx)) is True
        assert server.run(server.bot.can_run(ctx, call_once=True)) is False


class TestOnCommandError:
    def run_error(self, server: Server, ctx: commands.Context) -> None:
        server.run(server.bot.on_command_error(ctx, commands.CommandError("boom")))

    def test_prints_to_stderr(
        self, server: Server, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.run_error(server, server.context("x"))
        err = capsys.readouterr().err
        assert "Ignoring exception in command None" in err
        assert "boom" in err

    def test_listener_silences_the_default(
        self, server: Server, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server.bot._event_handlers["on_command_error"] = [AsyncMock()]
        self.run_error(server, server.context("x"))
        assert capsys.readouterr().err == ""

    def test_command_handler_silences_the_default(
        self, server: Server, capsys: pytest.CaptureFixture[str]
    ) -> None:
        @server.bot.command()
        async def ping(ctx: commands.Context) -> None: ...

        @ping.error
        async def handler(ctx: commands.Context, error: Exception) -> None: ...

        ctx = server.context("x")
        ctx.command = ping
        self.run_error(server, ctx)
        assert capsys.readouterr().err == ""

    def test_cog_handler_silences_the_default(
        self, server: Server, capsys: pytest.CaptureFixture[str]
    ) -> None:
        class Mine(commands.Cog):
            async def cog_command_error(self, ctx: Any, error: Any) -> None: ...

            @commands.command()
            async def ping(self, ctx: commands.Context) -> None: ...

        cog = Mine()
        server.bot.add_cog(cog)
        ctx = server.context("x")
        ctx.command = server.bot.get_command("ping")
        self.run_error(server, ctx)
        assert capsys.readouterr().err == ""


class TestHelpCommandSetter:
    def test_default_help_command(self, server: Server) -> None:
        assert isinstance(server.bot.help_command, commands.DefaultHelpCommand)
        assert server.bot.get_command("help") is not None

    def test_no_help_command_at_construction(self, loop: Any) -> None:
        bot = commands.Bot(
            command_prefix="!",
            intents=discord.Intents.none(),
            loop=loop,
            help_command=None,
        )
        assert bot.help_command is None
        assert bot.get_command("help") is None
        bot.help_command = None
        assert bot.help_command is None


class TestClose:
    def test_close_unloads_cogs_and_extensions(self, server: Server) -> None:
        class Mine(commands.Cog): ...

        server.bot.add_cog(Mine())
        server.bot.unload_extension = MagicMock()
        server.bot._CogMixin__extensions["ext.demo"] = object()
        server.run(server.bot.close())
        assert server.bot.get_cog("Mine") is None
        server.bot.unload_extension.assert_called_once_with("ext.demo")
