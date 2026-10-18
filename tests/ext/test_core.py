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

# ruff: noqa: UP045, PT018

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, Optional
from unittest.mock import AsyncMock

import pytest

import discord
from discord.ext import commands
from discord.ext.commands import core
from discord.permissions import Permissions

if TYPE_CHECKING:
    from tests.ext.support import Server

USER = 1300000000000000009


def invoke(server: Server, content: str) -> commands.Context:
    author = server.add_user(USER, "bob")
    ctx = server.run(server.bot.get_context(server.message(content, author=author)))
    server.run(server.bot.invoke(ctx))
    return ctx


@pytest.fixture
def errors(server: Server, monkeypatch: pytest.MonkeyPatch) -> list[Exception]:
    caught: list[Exception] = []

    def dispatch(event: str, *args: Any) -> None:
        if event == "command_error":
            caught.append(args[1])

    monkeypatch.setattr(server.bot, "dispatch", dispatch)
    return caught


class DefaultFlags(commands.FlagConverter):
    a: int = 1


async def noop(ctx: commands.Context) -> None: ...


class TestCommandConstruction:
    def test_callback_must_be_a_coroutine(self) -> None:
        with pytest.raises(TypeError, match="coroutine"):
            commands.Command(lambda ctx: None)

    def test_name_must_be_a_string(self) -> None:
        with pytest.raises(TypeError, match="string"):
            commands.Command(noop, name=5)

    def test_aliases_must_be_a_sequence(self) -> None:
        with pytest.raises(TypeError, match="Aliases"):
            commands.Command(noop, aliases="abc")

    def test_cooldown_must_be_a_mapping(self) -> None:
        with pytest.raises(TypeError, match="Cooldown must be"):
            commands.Command(noop, cooldown=5)

    def test_help_and_brief(self) -> None:
        cmd = commands.Command(noop, help="  Line one\n  line two", brief="short")
        assert cmd.help == "Line one\nline two"
        assert cmd.short_doc == "short"
        assert commands.Command(noop, help="First\nsecond").short_doc == "First"
        assert commands.Command(noop).short_doc == ""

    def test_docstring_is_the_help(self) -> None:
        async def documented(ctx: commands.Context) -> None:
            """Docs here."""

        assert commands.Command(documented).help == "Docs here."

    def test_cog_name(self, server: Server) -> None:
        class Mine(commands.Cog):
            @commands.command()
            async def inner(self, ctx: commands.Context) -> None: ...

        server.bot.add_cog(Mine())
        assert server.bot.get_command("inner").cog_name == "Mine"
        assert commands.Command(noop).cog_name is None

    def test_update_changes_attributes(self) -> None:
        cmd = commands.Command(noop, name="a")
        cmd.update(brief="new")
        assert (cmd.name, cmd.brief) == ("a", "new")

    def test_copy_keeps_hooks_checks_and_handlers(self) -> None:
        async def hook(ctx: Any) -> None: ...

        async def handler(ctx: Any, error: Any) -> None: ...

        cmd = commands.Command(noop, name="a", cooldown=None)
        cmd.add_check(lambda ctx: True)
        cmd.before_invoke(hook)
        cmd.after_invoke(hook)
        cmd.error(handler)
        copy = cmd.copy()
        assert copy is not cmd
        assert copy.checks == cmd.checks and copy.checks is not cmd.checks
        assert copy._before_invoke is hook and copy._after_invoke is hook
        assert copy.on_error is handler

    def test_update_copy(self) -> None:
        cmd = commands.Command(noop, name="a")
        assert cmd._update_copy({}).name == "a"
        assert cmd._update_copy({"brief": "b"}).brief == "b"

    def test_copy_keeps_cooldown_and_concurrency(self) -> None:
        @commands.max_concurrency(2)
        @commands.cooldown(1, 5)
        async def limited(ctx: commands.Context) -> None: ...

        cmd = commands.Command(limited)
        copy = cmd.copy()
        assert copy.cooldown is not None and copy.cooldown.rate == 1
        assert copy._max_concurrency.number == 2

    def test_str_and_parents(self, server: Server) -> None:
        @server.bot.group()
        async def a(ctx: commands.Context) -> None: ...

        @a.group()
        async def b(ctx: commands.Context) -> None: ...

        @b.command()
        async def c(ctx: commands.Context) -> None: ...

        assert str(c) == "a b c"
        assert c.parents == [b, a]
        assert c.root_parent is a
        assert a.root_parent is None
        assert c.full_parent_name == "a b"

    def test_clean_params_missing_parameters(self) -> None:
        async def nothing() -> None: ...

        with pytest.raises(ValueError, match="'context'"):
            commands.Command(nothing).clean_params  # noqa: B018

    def test_clean_params_missing_self(self, server: Server) -> None:
        cmd = commands.Command(noop)
        cmd.cog = object()
        cmd.params.clear()
        with pytest.raises(ValueError, match="'self'"):
            cmd.clean_params  # noqa: B018

    def test_unparameterized_greedy_is_rejected(self) -> None:
        async def bad(ctx: commands.Context, x: commands.Greedy) -> None: ...

        with pytest.raises(TypeError, match="Greedy"):
            commands.Command(bad)

    def test_none_annotation(self) -> None:
        async def cb(ctx: commands.Context, x: Any = None) -> None: ...

        cb.__annotations__["x"] = None
        assert commands.Command(cb).params["x"].annotation is type(None)

    def test_missing_ctx_and_self_parameters(self, server: Server) -> None:
        async def nothing() -> None: ...

        cmd = commands.Command(nothing)
        ctx = server.context("x")
        with pytest.raises(discord.ClientException, match='"ctx"'):
            server.run(cmd._parse_arguments(ctx))
        cmd.cog = object()
        with pytest.raises(discord.ClientException, match='"self"'):
            server.run(cmd._parse_arguments(ctx))


class TestSignature:
    def sig(self, callback: Any, **kwargs: Any) -> str:
        return commands.Command(callback, **kwargs).signature

    def test_usage_wins(self) -> None:
        assert self.sig(noop, usage="custom") == "custom"

    def test_no_params(self) -> None:
        assert self.sig(noop) == ""

    def test_parameter_forms(self) -> None:
        async def cb(
            ctx: commands.Context,
            required: int,
            opt_default: int = 5,
            text_default: str = "x",
            none_default: Optional[int] = None,
            empty_default: str = "",
            optional: Optional[int] = ...,
        ) -> None: ...

        assert self.sig(cb) == (
            "<required> [opt_default=5] [text_default=x] [none_default]"
            " [empty_default] [optional=Ellipsis]"
        )

    def test_optional_without_default(self) -> None:
        async def cb(ctx: commands.Context, maybe: Optional[int]) -> None: ...

        assert self.sig(cb) == "[maybe]"

    def test_literal(self) -> None:
        async def cb(
            ctx: commands.Context, mode: Literal["a", "b", 3], other: Literal["z"] = "z"
        ) -> None: ...

        assert self.sig(cb) == '<"a"|"b"|3> ["z"=z]'

    def test_optional_literal(self) -> None:
        async def cb(
            ctx: commands.Context, mode: Optional[Literal["a", "b"]]
        ) -> None: ...

        assert self.sig(cb) == '["a"|"b"]'

    def test_greedy(self) -> None:
        async def cb(
            ctx: commands.Context,
            many: commands.Greedy[int],
            more: commands.Greedy[int] = 2,
        ) -> None: ...

        assert self.sig(cb) == "[many]... [more=2]..."

    def test_var_positional(self) -> None:
        async def cb(ctx: commands.Context, *rest: int) -> None: ...

        assert self.sig(cb) == "[rest...]"
        assert self.sig(cb, require_var_positional=True) == "<rest...>"

    def test_keyword_only(self) -> None:
        async def cb(ctx: commands.Context, *, text: str) -> None: ...

        assert self.sig(cb) == "<text>"


class TestRegistration:
    def test_only_commands_can_be_added(self, server: Server) -> None:
        with pytest.raises(TypeError, match="subclass of Command"):
            server.bot.add_command(object())

    def test_duplicate_name(self, server: Server) -> None:
        server.bot.add_command(commands.Command(noop, name="a"))
        with pytest.raises(commands.CommandRegistrationError) as info:
            server.bot.add_command(commands.Command(noop, name="a"))
        assert info.value.name == "a"
        assert not info.value.alias_conflict

    def test_alias_conflict_rolls_back(self, server: Server) -> None:
        server.bot.add_command(commands.Command(noop, name="taken"))
        with pytest.raises(commands.CommandRegistrationError) as info:
            server.bot.add_command(
                commands.Command(noop, name="fresh", aliases=["taken"])
            )
        assert info.value.alias_conflict
        assert server.bot.get_command("fresh") is None
        assert server.bot.get_command("taken").name == "taken"

    def test_remove_command_and_aliases(self, server: Server) -> None:
        cmd = commands.Command(noop, name="a", aliases=["b", "c"])
        server.bot.add_command(cmd)
        assert server.bot.remove_command("b") is cmd
        assert server.bot.get_command("a") is cmd
        assert server.bot.remove_command("a") is cmd
        assert server.bot.get_command("c") is None
        assert server.bot.remove_command("missing") is None

    def test_walk_and_get_nested(self, server: Server) -> None:
        @server.bot.group()
        async def a(ctx: commands.Context) -> None: ...

        @a.group()
        async def b(ctx: commands.Context) -> None: ...

        @b.command()
        async def c(ctx: commands.Context) -> None: ...

        @server.bot.command()
        async def d(ctx: commands.Context) -> None: ...

        walked = {x.qualified_name for x in server.bot.walk_commands()}
        assert {"a", "a b", "a b c", "d"} <= walked
        assert server.bot.get_command("a b c") is c
        assert server.bot.get_command("a b nope") is None
        assert server.bot.get_command("d x") is d
        assert server.bot.get_command("") is None
        assert server.bot.get_command("   ") is None

    def test_recursively_remove_all_commands(self, server: Server) -> None:
        @server.bot.group()
        async def a(ctx: commands.Context) -> None: ...

        @a.command()
        async def b(ctx: commands.Context) -> None: ...

        server.bot.recursively_remove_all_commands()
        assert not list(server.bot.commands)
        assert not list(a.commands)

    def test_case_insensitive_groups(self, server: Server) -> None:
        ran: list[str] = []

        @server.bot.group(case_insensitive=True, invoke_without_command=True)
        async def grp(ctx: commands.Context) -> None: ...

        @grp.command(name="Sub")
        async def sub(ctx: commands.Context) -> None:
            ran.append("sub")

        assert "SUB" in grp.all_commands
        assert grp.all_commands.get("sUb") is sub
        invoke(server, "!grp SUB")
        assert ran == ["sub"]
        assert grp.remove_command("SUB") is sub
        assert "sub" not in grp.all_commands

    def test_command_decorator_rejects_commands(self) -> None:
        cmd = commands.Command(noop)
        with pytest.raises(TypeError, match="already a command"):
            commands.command()(cmd)

    def test_group_copy_copies_subcommands(self, server: Server) -> None:
        @server.bot.group()
        async def a(ctx: commands.Context) -> None: ...

        @a.command()
        async def b(ctx: commands.Context) -> None: ...

        copy = a.copy()
        assert [c.name for c in copy.commands] == ["b"]
        assert copy.get_command("b") is not b


class TestHandlersAndHooks:
    def test_error_requires_a_coroutine(self) -> None:
        cmd = commands.Command(noop)
        with pytest.raises(TypeError, match="error handler"):
            cmd.error(lambda ctx, error: None)
        assert not cmd.has_error_handler()

        @cmd.error
        async def handler(ctx: Any, error: Any) -> None: ...

        assert cmd.has_error_handler()

    def test_hooks_require_coroutines(self) -> None:
        cmd = commands.Command(noop)
        with pytest.raises(TypeError, match="pre-invoke"):
            cmd.before_invoke(lambda ctx: None)
        with pytest.raises(TypeError, match="post-invoke"):
            cmd.after_invoke(lambda ctx: None)

    def test_local_error_handler_runs(self, server: Server, errors: list) -> None:
        seen: list[Exception] = []

        @server.bot.command()
        async def boom(ctx: commands.Context) -> None:
            raise RuntimeError("x")

        @boom.error
        async def handler(ctx: commands.Context, error: Exception) -> None:
            seen.append(error)

        ctx = invoke(server, "!boom")
        assert ctx.command_failed
        assert isinstance(seen[0], commands.CommandInvokeError)
        assert isinstance(errors[0].original, RuntimeError)

    def test_cog_error_handler_and_cog_local_handler(
        self, server: Server, errors: list
    ) -> None:
        seen: list[str] = []

        class Mine(commands.Cog):
            async def cog_command_error(self, ctx: Any, error: Any) -> None:
                seen.append("cog")

            @commands.command()
            async def boom(self, ctx: commands.Context) -> None:
                raise RuntimeError("x")

            @boom.error
            async def boom_error(self, ctx: Any, error: Any) -> None:
                seen.append("local")

        server.bot.add_cog(Mine())
        invoke(server, "!boom")
        assert seen == ["local", "cog"]
        assert len(errors) == 1

    def test_hook_order_for_command_cog_and_bot(self, server: Server) -> None:
        order: list[str] = []

        class Mine(commands.Cog):
            async def cog_before_invoke(self, ctx: Any) -> None:
                order.append("cog_before")

            async def cog_after_invoke(self, ctx: Any) -> None:
                order.append("cog_after")

            @commands.command()
            async def run(self, ctx: commands.Context) -> None:
                order.append("run")

            @run.before_invoke
            async def run_before(self, ctx: Any) -> None:
                order.append("cmd_before")

            @run.after_invoke
            async def run_after(self, ctx: Any) -> None:
                order.append("cmd_after")

        async def bot_before(ctx: Any) -> None:
            order.append("bot_before")

        async def bot_after(ctx: Any) -> None:
            order.append("bot_after")

        server.bot.before_invoke(bot_before)
        server.bot.after_invoke(bot_after)
        server.bot.add_cog(Mine())
        invoke(server, "!run")
        assert order == [
            "cmd_before",
            "cog_before",
            "bot_before",
            "run",
            "cmd_after",
            "cog_after",
            "bot_after",
        ]

    def test_decorator_hooks_on_functions_and_commands(self, server: Server) -> None:
        order: list[str] = []

        async def before(ctx: Any) -> None:
            order.append("before")

        async def after(ctx: Any) -> None:
            order.append("after")

        @server.bot.command()
        @commands.after_invoke(after)
        @commands.before_invoke(before)
        async def plain(ctx: commands.Context) -> None:
            order.append("run")

        async def second(ctx: commands.Context) -> None:
            order.append("run2")

        cmd = server.bot.command(name="second")(second)
        commands.before_invoke(before)(cmd)
        commands.after_invoke(after)(cmd)
        invoke(server, "!plain")
        invoke(server, "!second")
        assert order == ["before", "run", "after", "before", "run2", "after"]

    def test_cancelled_callback_is_swallowed(
        self, server: Server, errors: list
    ) -> None:
        @server.bot.command()
        async def cancelled(ctx: commands.Context) -> None:
            raise asyncio.CancelledError

        ctx = invoke(server, "!cancelled")
        assert ctx.command_failed
        assert errors == []

    def test_command_errors_pass_through_wrap_callback(
        self, server: Server, errors: list
    ) -> None:
        @server.bot.command()
        async def failing(ctx: commands.Context) -> None:
            raise commands.UserInputError("bad")

        invoke(server, "!failing")
        assert isinstance(errors[0], commands.UserInputError)


class TestCanRun:
    def test_disabled(self, server: Server, errors: list) -> None:
        @server.bot.command(enabled=False)
        async def off(ctx: commands.Context) -> None: ...

        invoke(server, "!off")
        assert isinstance(errors[0], commands.DisabledCommand)

    def test_check_failure_and_checks_api(self, server: Server, errors: list) -> None:
        ran: list[int] = []

        @server.bot.command()
        async def guarded(ctx: commands.Context) -> None:
            ran.append(1)

        def deny(ctx: Any) -> bool:
            return False

        guarded.add_check(deny)
        invoke(server, "!guarded")
        assert isinstance(errors[0], commands.CheckFailure)
        assert ran == []
        guarded.remove_check(deny)
        guarded.remove_check(deny)
        invoke(server, "!guarded")
        assert ran == [1]

    def test_bot_level_check_failure(self, server: Server, errors: list) -> None:
        @server.bot.command()
        async def cmd(ctx: commands.Context) -> None: ...

        server.bot.add_check(lambda ctx: False)
        invoke(server, "!cmd")
        assert isinstance(errors[0], commands.CheckFailure)

    def test_cog_check(self, server: Server, errors: list) -> None:
        ran: list[int] = []

        class Mine(commands.Cog):
            def cog_check(self, ctx: Any) -> bool:
                return False

            @commands.command()
            async def inner(self, ctx: commands.Context) -> None:
                ran.append(1)

        server.bot.add_cog(Mine())
        invoke(server, "!inner")
        assert ran == []
        assert isinstance(errors[0], commands.CheckFailure)

    def test_cog_check_passing(self, server: Server) -> None:
        ran: list[int] = []

        class Mine(commands.Cog):
            async def cog_check(self, ctx: Any) -> bool:
                return True

            @commands.command()
            async def inner(self, ctx: commands.Context) -> None:
                ran.append(1)

        server.bot.add_cog(Mine())
        invoke(server, "!inner")
        assert ran == [1]


class TestArgumentParsing:
    def test_optional_missing_argument_is_none(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, value: Optional[int]) -> None:
            got.append(value)

        invoke(server, "!cmd")
        invoke(server, "!cmd 4")
        assert got == [None, 4]

    def test_optional_unclosed_quote_is_none(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, value: Optional[int]) -> None:
            got.append(value)

        invoke(server, '!cmd "oops')
        assert got == [None]

    def test_unclosed_quote_error(self, server: Server, errors: list) -> None:
        @server.bot.command()
        async def cmd(ctx: commands.Context, value: str) -> None: ...

        invoke(server, '!cmd "oops')
        assert isinstance(
            errors[0],
            commands.UnexpectedQuoteError | commands.ExpectedClosingQuoteError,
        )

    def test_missing_required(self, server: Server, errors: list) -> None:
        @server.bot.command()
        async def cmd(ctx: commands.Context, value: int) -> None: ...

        invoke(server, "!cmd")
        assert isinstance(errors[0], commands.MissingRequiredArgument)

    def test_flag_converter_default_when_empty(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, *, flags: DefaultFlags) -> None:
            got.append(flags.a)

        invoke(server, "!cmd")
        invoke(server, "!cmd a: 5")
        assert got == [1, 5]

    def test_greedy(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(
            ctx: commands.Context, nums: commands.Greedy[int], word: str
        ) -> None:
            got.append((nums, word))

        invoke(server, "!cmd 1 2 3 end")
        invoke(server, "!cmd end")
        assert got == [([1, 2, 3], "end"), ([], "end")]

    def test_greedy_not_required(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, nums: commands.Greedy[int] = None) -> None:
            got.append(nums)

        invoke(server, "!cmd")
        assert got == [None]

    def test_greedy_keyword_only(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, *, num: commands.Greedy[int]) -> None:
            got.append(num)

        invoke(server, "!cmd 12")
        assert got == [12]

    def test_greedy_var_positional(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, *nums: commands.Greedy[int]) -> None:
            got.append(nums)

        invoke(server, "!cmd 1 2 x")
        assert got == [(1, 2)]

    def test_var_positional(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, *rest: str) -> None:
            got.append(rest)

        invoke(server, "!cmd a b c")
        invoke(server, "!cmd")
        assert got == [("a", "b", "c"), ()]

    def test_require_var_positional(self, server: Server, errors: list) -> None:
        @server.bot.command(require_var_positional=True)
        async def cmd(ctx: commands.Context, *rest: str) -> None: ...

        invoke(server, "!cmd")
        assert isinstance(errors[0], commands.MissingRequiredArgument)

    def test_keyword_only_consumes_rest(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command()
        async def cmd(ctx: commands.Context, first: str, *, rest: str) -> None:
            got.append((first, rest))

        invoke(server, "!cmd a  b c  ")
        assert got == [("a", "b c")]

    def test_rest_is_raw(self, server: Server) -> None:
        got: list[Any] = []

        @server.bot.command(rest_is_raw=True)
        async def cmd(ctx: commands.Context, *, rest: str) -> None:
            got.append(rest)

        invoke(server, "!cmd  a b ")
        assert got == ["  a b "]

    def test_too_many_arguments(self, server: Server, errors: list) -> None:
        @server.bot.command(ignore_extra=False)
        async def cmd(ctx: commands.Context, one: str) -> None: ...

        invoke(server, "!cmd a b")
        assert isinstance(errors[0], commands.TooManyArguments)

    def test_cooldown_after_parsing(self, server: Server, errors: list) -> None:
        @server.bot.command(cooldown_after_parsing=True)
        @commands.cooldown(1, 60)
        async def cmd(ctx: commands.Context, value: int) -> None: ...

        invoke(server, "!cmd x")
        invoke(server, "!cmd 1")
        invoke(server, "!cmd 2")
        assert isinstance(errors[0], commands.BadArgument)
        assert isinstance(errors[1], commands.CommandOnCooldown)

    def test_max_concurrency_released_after_a_failure(
        self, server: Server, errors: list
    ) -> None:
        @server.bot.command()
        @commands.max_concurrency(1)
        async def cmd(ctx: commands.Context, value: int) -> None: ...

        invoke(server, "!cmd x")
        invoke(server, "!cmd 1")
        assert len(errors) == 1
        assert isinstance(errors[0], commands.BadArgument)


class TestGroups:
    def test_group_callback_then_subcommand(self, server: Server) -> None:
        order: list[str] = []

        @server.bot.group()
        async def grp(ctx: commands.Context) -> None:
            order.append(f"grp:{ctx.invoked_subcommand}")

        @grp.command()
        async def sub(ctx: commands.Context) -> None:
            order.append("sub")

        invoke(server, "!grp sub")
        invoke(server, "!grp")
        invoke(server, "!grp unknown")
        assert order == ["grp:grp sub", "sub", "grp:None", "grp:None"]

    def test_invoke_without_command(self, server: Server) -> None:
        order: list[str] = []

        @server.bot.group(invoke_without_command=True)
        async def grp(ctx: commands.Context, arg: str = "-") -> None:
            order.append(f"grp:{arg}")

        @grp.command()
        async def sub(ctx: commands.Context) -> None:
            order.append("sub")

        invoke(server, "!grp sub")
        invoke(server, "!grp other")
        invoke(server, "!grp")
        assert order == ["sub", "grp:other", "grp:-"]

    def test_group_error_in_early_callback_runs_hooks(
        self, server: Server, errors: list
    ) -> None:
        @server.bot.group()
        async def grp(ctx: commands.Context) -> None:
            raise RuntimeError

        @grp.command()
        async def sub(ctx: commands.Context) -> None: ...

        ctx = invoke(server, "!grp sub")
        assert ctx.command_failed
        assert isinstance(errors[0], commands.CommandInvokeError)

    def test_group_reinvoke(self, server: Server) -> None:
        order: list[str] = []

        @server.bot.group()
        async def grp(ctx: commands.Context) -> None:
            order.append("grp")

        @grp.command()
        async def sub(ctx: commands.Context) -> None:
            order.append("sub")

        @grp.before_invoke
        async def before(ctx: Any) -> None:
            order.append("before")

        ctx = invoke(server, "!grp sub")
        order.clear()
        server.run(ctx.reinvoke(call_hooks=True))
        assert order == ["before", "grp", "sub"]

    def test_group_reinvoke_failure(self, server: Server) -> None:
        @server.bot.group()
        async def grp(ctx: commands.Context) -> None:
            raise RuntimeError("x")

        @grp.command()
        async def sub(ctx: commands.Context) -> None: ...

        ctx = invoke(server, "!grp sub")
        with pytest.raises(RuntimeError):
            server.run(ctx.reinvoke())
        assert ctx.command_failed

    def test_group_reinvoke_without_command(self, server: Server) -> None:
        order: list[str] = []

        @server.bot.group(invoke_without_command=True)
        async def grp(ctx: commands.Context) -> None:
            order.append("grp")

        @grp.command()
        async def sub(ctx: commands.Context) -> None:
            order.append("sub")

        ctx = invoke(server, "!grp sub")
        order.clear()
        server.run(ctx.reinvoke())
        assert order == ["sub"]
        ctx2 = invoke(server, "!grp")
        order.clear()
        server.run(ctx2.reinvoke())
        assert order == ["grp"]


class TestChecksDecorators:
    @pytest.fixture
    def patched(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        def patch(name: str, value: Any) -> None:
            monkeypatch.setattr(core, name, AsyncMock(return_value=value))

        return patch

    def test_check_decorator_on_functions_and_commands(self, server: Server) -> None:
        async def cb(ctx: commands.Context) -> None: ...

        pred = lambda ctx: True  # noqa: E731
        decorated = commands.check(pred)(cb)
        assert decorated.__commands_checks__ == [pred]
        cmd = commands.Command(noop)
        commands.check(pred)(cmd)
        assert cmd.checks == [pred]

    def test_check_predicate_attribute_is_a_coroutine(self, server: Server) -> None:
        decorator = commands.check(lambda ctx: True)
        assert server.run(decorator.predicate(None)) is True

    def test_check_any(self, server: Server) -> None:
        ok = commands.check(lambda ctx: True)
        bad = commands.check(lambda ctx: False)

        async def raising(ctx: Any) -> bool:
            raise commands.CheckFailure("no")

        raises = commands.check(raising)
        ctx = server.context("x")
        assert server.run(commands.check_any(bad, ok).predicate(ctx)) is True
        with pytest.raises(commands.CheckAnyFailure) as info:
            server.run(commands.check_any(bad, raises).predicate(ctx))
        assert len(info.value.errors) == 1
        with pytest.raises(TypeError, match="must be wrapped"):
            commands.check_any(lambda ctx: True)

    def test_role_checks_in_dms(self, server: Server, patched: Any) -> None:
        patched("get_author_roles", None)
        patched("get_bot_roles", None)
        ctx = server.context("x")
        for decorator in (
            commands.has_role("a"),
            commands.has_any_role("a"),
            commands.bot_has_role(1),
            commands.bot_has_any_role(1),
        ):
            with pytest.raises(commands.NoPrivateMessage):
                server.run(decorator.predicate(ctx))

    def test_role_checks(self, server: Server, patched: Any) -> None:
        role = server.add_role(None, "Mods")
        patched("get_author_roles", [role])
        patched("get_bot_roles", [role])
        ctx = server.context("x")
        assert server.run(commands.has_role("Mods").predicate(ctx))
        assert server.run(commands.has_any_role("x", role.id).predicate(ctx))
        assert server.run(commands.bot_has_role(role.id).predicate(ctx))
        assert server.run(commands.bot_has_any_role(role.id).predicate(ctx))
        with pytest.raises(commands.MissingRole):
            server.run(commands.has_role("Other").predicate(ctx))
        with pytest.raises(commands.MissingAnyRole):
            server.run(commands.has_any_role("Other").predicate(ctx))
        with pytest.raises(commands.BotMissingRole):
            server.run(commands.bot_has_role(1).predicate(ctx))
        with pytest.raises(commands.BotMissingAnyRole):
            server.run(commands.bot_has_any_role(1).predicate(ctx))

    def test_permission_checks(self, server: Server, patched: Any) -> None:
        patched("get_author_channel_permissions", Permissions(manage_messages=True))
        patched("get_bot_channel_permissions", Permissions(manage_messages=True))
        patched("get_author_guild_permissions", Permissions(manage_guild=True))
        patched("get_bot_guild_permissions", Permissions(manage_guild=True))
        ctx = server.context("x")
        assert server.run(commands.has_permissions(manage_messages=True).predicate(ctx))
        assert server.run(
            commands.bot_has_permissions(manage_messages=True).predicate(ctx)
        )
        assert server.run(
            commands.has_guild_permissions(manage_guild=True).predicate(ctx)
        )
        assert server.run(
            commands.bot_has_guild_permissions(manage_guild=True).predicate(ctx)
        )
        with pytest.raises(commands.MissingPermissions):
            server.run(commands.has_permissions(ban_members=True).predicate(ctx))
        with pytest.raises(commands.BotMissingPermissions):
            server.run(commands.bot_has_permissions(ban_members=True).predicate(ctx))
        with pytest.raises(commands.MissingPermissions):
            server.run(commands.has_guild_permissions(ban_members=True).predicate(ctx))
        with pytest.raises(commands.BotMissingPermissions):
            server.run(
                commands.bot_has_guild_permissions(ban_members=True).predicate(ctx)
            )
        with pytest.raises(TypeError):
            commands.has_permissions(not_a_permission=True)

    def test_permission_checks_in_dms(self, server: Server, patched: Any) -> None:
        patched("get_author_channel_permissions", None)
        patched("get_bot_channel_permissions", None)
        patched("get_author_guild_permissions", None)
        patched("get_bot_guild_permissions", None)
        ctx = server.context("x")
        assert server.run(commands.has_permissions(ban_members=True).predicate(ctx))
        assert server.run(commands.bot_has_permissions(ban_members=True).predicate(ctx))
        with pytest.raises(commands.NoPrivateMessage):
            server.run(commands.has_guild_permissions(ban_members=True).predicate(ctx))
        with pytest.raises(commands.NoPrivateMessage):
            server.run(
                commands.bot_has_guild_permissions(ban_members=True).predicate(ctx)
            )

    def test_dm_and_guild_only(self, server: Server) -> None:
        guild_ctx = server.context("x")
        dm_ctx = server.context("x", in_guild=False)
        assert commands.dm_only().predicate  # decorator exposes the predicate
        assert server.run(commands.dm_only().predicate(dm_ctx))
        assert server.run(commands.guild_only().predicate(guild_ctx))
        with pytest.raises(commands.PrivateMessageOnly):
            server.run(commands.dm_only().predicate(guild_ctx))
        with pytest.raises(commands.NoPrivateMessage):
            server.run(commands.guild_only().predicate(dm_ctx))

    def test_is_owner(self, server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = server.context("x")
        monkeypatch.setattr(type(server.bot), "is_owner", AsyncMock(return_value=True))
        assert server.run(commands.is_owner().predicate(ctx))
        monkeypatch.setattr(type(server.bot), "is_owner", AsyncMock(return_value=False))
        with pytest.raises(commands.NotOwner):
            server.run(commands.is_owner().predicate(ctx))

    def test_is_nsfw(self, server: Server) -> None:
        sfw = server.add_text("sfw")
        nsfw = server.add_text("hot", nsfw=True)
        check = commands.is_nsfw().predicate
        assert server.run(check(server.context("x", in_guild=False)))
        assert server.run(check(server.context("x", channel=nsfw)))
        with pytest.raises(commands.NSFWChannelRequired):
            server.run(check(server.context("x", channel=sfw)))

    def test_is_nsfw_in_threads(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        parent = server.add_text("hot2", nsfw=True)
        thread = server.add_thread("thr", parent)
        check = commands.is_nsfw().predicate
        ctx = server.context("x", channel=thread)
        ctx.get_channel = AsyncMock(return_value=thread)
        monkeypatch.setattr(discord.Thread, "check_nsfw", AsyncMock(return_value=True))
        assert server.run(check(ctx))
        monkeypatch.setattr(discord.Thread, "check_nsfw", AsyncMock(return_value=False))
        with pytest.raises(commands.NSFWChannelRequired):
            server.run(check(ctx))


class TestCooldownDecorators:
    def test_cooldown_on_function_then_command(self) -> None:
        @commands.cooldown(2, 10)
        async def cb(ctx: commands.Context) -> None: ...

        assert cb.__commands_cooldown__.valid
        cmd = commands.Command(cb)
        assert cmd.cooldown.rate == 2 and cmd.cooldown.per == 10

    def test_cooldown_on_command(self) -> None:
        cmd = commands.Command(noop)
        commands.cooldown(3, 4)(cmd)
        assert cmd.cooldown.rate == 3

    def test_dynamic_cooldown_requires_a_callable(self) -> None:
        with pytest.raises(TypeError, match="callable"):
            commands.dynamic_cooldown(5)

    def test_dynamic_cooldown_on_function_and_command(self) -> None:
        def factory(message: Any) -> Any:
            return commands.Cooldown(1, 5)

        @commands.dynamic_cooldown(factory)
        async def cb(ctx: commands.Context) -> None: ...

        assert isinstance(cb.__commands_cooldown__, commands.DynamicCooldownMapping)
        cmd = commands.Command(noop)
        commands.dynamic_cooldown(factory)(cmd)
        assert isinstance(cmd._buckets, commands.DynamicCooldownMapping)

    def test_max_concurrency_on_command(self) -> None:
        cmd = commands.Command(noop)
        commands.max_concurrency(2, commands.BucketType.user)(cmd)
        assert cmd._max_concurrency.number == 2

    def test_cooldown_flow(self, server: Server) -> None:
        @server.bot.command()
        @commands.cooldown(1, 60)
        async def limited(ctx: commands.Context) -> None: ...

        ctx = invoke(server, "!limited")
        assert limited.is_on_cooldown(ctx)
        assert limited.get_cooldown_retry_after(ctx) > 0
        limited.reset_cooldown(ctx)
        assert not limited.is_on_cooldown(ctx)
        assert limited.get_cooldown_retry_after(ctx) == 0

    def test_no_cooldown_flow(self, server: Server) -> None:
        @server.bot.command()
        async def free(ctx: commands.Context) -> None: ...

        ctx = invoke(server, "!free")
        assert not free.is_on_cooldown(ctx)
        assert free.get_cooldown_retry_after(ctx) == 0.0
        free.reset_cooldown(ctx)


class TestUnwrap:
    def test_unwrap_function(self) -> None:
        import functools

        def base() -> None: ...

        wrapped = functools.wraps(base)(lambda: None)
        assert core.unwrap_function(wrapped) is base
        assert core.unwrap_function(functools.partial(base)) is base


class TestCommandCall:
    def test_call_bypasses_everything(self, server: Server) -> None:
        @server.bot.command()
        async def add(ctx: commands.Context, a: int) -> int:
            return a + 1

        ctx = server.context("x")
        assert server.run(add(ctx, 1)) == 2

    def test_call_with_cog(self, server: Server) -> None:
        class Mine(commands.Cog):
            @commands.command()
            async def inner(self, ctx: commands.Context, a: int) -> tuple[Any, int]:
                return self, a

        cog = Mine()
        server.bot.add_cog(cog)
        result = server.run(server.bot.get_command("inner")(server.context("x"), 3))
        assert result == (cog, 3)
