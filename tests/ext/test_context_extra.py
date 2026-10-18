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

from discord.ext import commands
from discord.message import Message

if TYPE_CHECKING:
    from tests.ext.support import Server

USER = 1300000000000000009


def get_ctx(server: Server, content: str) -> commands.Context:
    author = server.add_user(USER, "bob")
    return server.run(server.bot.get_context(server.message(content, author=author)))


class TestInvokeAndReinvoke:
    def test_invoke_calls_the_callback_directly(self, server: Server) -> None:
        @server.bot.command()
        async def add(ctx: commands.Context, a: int, b: int) -> int:
            return a + b

        ctx = server.context("x")
        assert server.run(ctx.invoke(add, 1, 2)) == 3

    def test_reinvoke_without_command(self, server: Server) -> None:
        ctx = server.context("x")
        with pytest.raises(ValueError, match="not valid"):
            server.run(ctx.reinvoke())

    def test_valid(self, server: Server) -> None:
        @server.bot.command()
        async def thing(ctx: commands.Context) -> None: ...

        assert get_ctx(server, "!thing").valid
        assert not get_ctx(server, "!nothing").valid
        assert not get_ctx(server, "thing").valid

    def test_reinvoke_replays_the_arguments_and_restores_state(
        self, server: Server
    ) -> None:
        calls: list[Any] = []

        @server.bot.command()
        async def echo(ctx: commands.Context, value: int) -> None:
            calls.append(value)

        ctx = get_ctx(server, "!echo 7")
        server.run(server.bot.invoke(ctx))
        index = ctx.view.index
        server.run(ctx.reinvoke())
        assert calls == [7, 7]
        assert ctx.view.index == index
        assert ctx.command is echo
        assert ctx.invoked_with == "echo"

    def test_reinvoke_without_restart(self, server: Server) -> None:
        calls: list[Any] = []

        @server.bot.group(invoke_without_command=True)
        async def root(ctx: commands.Context) -> None:
            calls.append("root")

        @root.command()
        async def leaf(ctx: commands.Context) -> None:
            calls.append("leaf")

        ctx = get_ctx(server, "!root leaf")
        server.run(server.bot.invoke(ctx))
        assert calls == ["leaf"]
        server.run(ctx.reinvoke(restart=False))
        assert calls == ["leaf", "leaf"]
        server.run(ctx.reinvoke())
        assert calls == ["leaf"] * 3
        assert ctx.command is leaf

    def test_reinvoke_with_hooks(self, server: Server) -> None:
        calls: list[str] = []

        @server.bot.command()
        async def hooked(ctx: commands.Context) -> None:
            calls.append("run")

        @hooked.before_invoke
        async def before(ctx: commands.Context) -> None:
            calls.append("before")

        @hooked.after_invoke
        async def after(ctx: commands.Context) -> None:
            calls.append("after")

        ctx = get_ctx(server, "!hooked")
        server.run(ctx.reinvoke(call_hooks=True))
        assert calls == ["before", "run", "after"]

    def test_reinvoke_state_restored_on_failure(self, server: Server) -> None:
        @server.bot.command()
        async def bad(ctx: commands.Context) -> None:
            raise RuntimeError("x")

        ctx = get_ctx(server, "!bad")
        index = ctx.view.index
        with pytest.raises(RuntimeError):
            server.run(ctx.reinvoke())
        assert ctx.view.index == index
        assert ctx.command is bad


class TestCleanPrefix:
    def test_no_prefix(self, server: Server) -> None:
        ctx = server.context("x")
        ctx.prefix = None
        assert ctx.clean_prefix == ""

    def test_plain_prefix(self, server: Server) -> None:
        assert server.context("x").clean_prefix == "!"

    def test_mention_prefix(self, server: Server) -> None:
        ctx = server.context("x")
        ctx.prefix = f"<@{server.bot.user.id}> "
        assert ctx.clean_prefix == f"@{ctx.me.display_name} "


class TestSendHelp:
    @pytest.fixture
    def help_command(self, server: Server) -> commands.HelpCommand:
        class Recorder(commands.HelpCommand):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self.calls: list[tuple[str, Any]] = []

            async def send_bot_help(self, mapping: Any) -> None:
                self.calls.append(("bot", mapping))

            async def send_cog_help(self, cog: Any) -> None:
                self.calls.append(("cog", cog))

            async def send_group_help(self, group: Any) -> None:
                self.calls.append(("group", group))

            async def send_command_help(self, command: Any) -> None:
                self.calls.append(("command", command))

        recorder = Recorder()
        recorder.copy = lambda: recorder  # type: ignore[method-assign]
        server.bot.help_command = recorder
        return recorder

    def test_no_help_command(self, server: Server) -> None:
        server.bot.help_command = None
        assert server.run(server.context("x").send_help()) is None

    def test_bot_help(self, server: Server, help_command: commands.HelpCommand) -> None:
        ctx = server.context("x")
        server.run(ctx.send_help())
        assert help_command.calls[0][0] == "bot"
        assert help_command.context is ctx

    def test_bot_help_error_goes_to_the_error_handler(
        self, server: Server, help_command: commands.HelpCommand
    ) -> None:
        error = commands.CommandError("boom")
        help_command.send_bot_help = AsyncMock(side_effect=error)
        help_command.on_help_command_error = AsyncMock()
        ctx = server.context("x")
        assert server.run(ctx.send_help()) is None
        help_command.on_help_command_error.assert_awaited_once_with(ctx, error)

    def test_entities(self, server: Server, help_command: commands.HelpCommand) -> None:
        class Mine(commands.Cog):
            @commands.command()
            async def inner(self, ctx: commands.Context) -> None: ...

        @server.bot.command()
        async def single(ctx: commands.Context) -> None: ...

        @server.bot.group()
        async def grp(ctx: commands.Context) -> None: ...

        cog = Mine()
        server.bot.add_cog(cog)
        ctx = server.context("x")
        server.run(ctx.send_help(cog))
        server.run(ctx.send_help("Mine"))
        server.run(ctx.send_help(grp))
        server.run(ctx.send_help("single"))
        assert help_command.calls == [
            ("cog", cog),
            ("cog", cog),
            ("group", grp),
            ("command", single),
        ]

    def test_unknown_entities(
        self, server: Server, help_command: commands.HelpCommand
    ) -> None:
        ctx = server.context("x")
        assert server.run(ctx.send_help("missing")) is None
        assert server.run(ctx.send_help(object())) is None
        assert help_command.calls == []

    def test_entity_error_goes_to_the_error_handler(
        self, server: Server, help_command: commands.HelpCommand
    ) -> None:
        @server.bot.command()
        async def single(ctx: commands.Context) -> None: ...

        error = commands.CommandError("boom")
        help_command.send_command_help = AsyncMock(side_effect=error)
        help_command.on_help_command_error = AsyncMock()
        ctx = server.context("x")
        assert server.run(ctx.send_help(single)) is None
        help_command.on_help_command_error.assert_awaited_once_with(ctx, error)


class TestForwardTo:
    def test_forward_to_delegates_to_the_message(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = server.context("x")
        sent = object()
        forward = AsyncMock(return_value=sent)
        monkeypatch.setattr(Message, "forward_to", forward)
        target = server.world.channel
        assert server.run(ctx.forward_to(target, content="hi")) is sent
        forward.assert_awaited_once_with(target, content="hi")
