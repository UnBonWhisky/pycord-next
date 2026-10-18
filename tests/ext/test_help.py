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

# ruff: noqa: PT018, RUF001

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord.ext import commands
from discord.ext.commands.help import Paginator

if TYPE_CHECKING:
    from tests.ext.support import Server


def _callback() -> Any:
    async def callback(ctx: Any) -> None: ...

    return callback


class TestPaginator:
    def test_wraps_pages_with_prefix_and_suffix(self) -> None:
        p = Paginator(max_size=30)
        p.add_line("a" * 10)
        p.add_line("b" * 10)
        p.add_line("c" * 10)
        assert p.pages == [
            "```\n" + "a" * 10 + "\n" + "b" * 10 + "\n```",
            "```\n" + "c" * 10 + "\n```",
        ]

    def test_without_prefix_and_suffix(self) -> None:
        p = Paginator(prefix=None, suffix=None, max_size=20)
        assert len(p) == 0
        p.add_line("hello", empty=True)
        assert len(p) == 5 + 1 + 1
        p.add_line("x" * 12)
        assert p.pages == ["hello\n\n" + "x" * 12]
        assert "prefix: None" in repr(p)

    def test_close_page_and_clear(self) -> None:
        p = Paginator(prefix=None, suffix=None)
        p.add_line("one")
        p.close_page()
        p.add_line("two")
        assert p.pages == ["one", "two"]
        p.clear()
        assert p.pages == []

    def test_empty_paginator_has_no_pages(self) -> None:
        assert Paginator().pages == []

    def test_line_too_long(self) -> None:
        p = Paginator(max_size=20)
        with pytest.raises(RuntimeError, match="maximum page size"):
            p.add_line("x" * 20)


class Cogged(commands.Cog):
    """Cog description"""

    @commands.command(aliases=["al"])
    async def alpha(self, ctx: commands.Context, arg: int) -> None:
        """Alpha help text"""

    @commands.command(hidden=True)
    async def secret(self, ctx: commands.Context) -> None:
        """Hidden"""


@pytest.fixture
def populated(bot: commands.Bot) -> commands.Bot:
    bot.description = "The bot"

    @bot.command()
    async def zeta(ctx: commands.Context) -> None:
        """Zeta short.

        Zeta long."""

    @bot.group(invoke_without_command=True)
    async def grp(ctx: commands.Context) -> None:
        """Group help"""

    @grp.command()
    async def sub(ctx: commands.Context) -> None:
        """Sub short"""

    @grp.command()
    async def hidden_sub(ctx: commands.Context) -> None:
        """Another"""

    @bot.command(name="denied")
    async def denied(ctx: commands.Context) -> None:
        """Not allowed"""

    denied.add_check(lambda ctx: False)
    bot.add_cog(Cogged())
    return bot


class Sink:
    def __init__(self) -> None:
        self.send = AsyncMock()

    @property
    def sent(self) -> list[str]:
        return [c.args[0] for c in self.send.await_args_list]


def prepare(
    server: Server, help_command: commands.HelpCommand, content: str = "!help"
) -> tuple[commands.HelpCommand, Sink, commands.Context]:
    ctx = server.context(content)
    ctx.invoked_with = "help"
    help_command.context = ctx
    sink = Sink()
    help_command.get_destination = lambda: sink  # type: ignore[method-assign]
    return help_command, sink, ctx


class TestHelpCommandBase:
    def test_copy_preserves_arguments(self) -> None:
        h = commands.DefaultHelpCommand(width=10, command_attrs={"name": "aide"})
        copy = h.copy()
        assert copy is not h
        assert copy.width == 10
        assert copy._command_impl is h._command_impl

    def test_registered_on_the_bot(self, bot: commands.Bot) -> None:
        impl = bot.help_command._command_impl
        assert bot.get_command("help") is impl
        bot.help_command = None
        assert bot.get_command("help") is None
        assert bot.help_command is None
        bot.help_command = None

    def test_replacing_the_help_command(self, bot: commands.Bot) -> None:
        old = bot.help_command
        new = commands.MinimalHelpCommand(command_attrs={"name": "h2"})
        bot.help_command = new
        assert bot.get_command("help") is None
        assert bot.get_command("h2") is new._command_impl
        assert old is not bot.help_command

    def test_invalid_help_command(self, bot: commands.Bot) -> None:
        with pytest.raises(TypeError):
            bot.help_command = object()  # type: ignore[assignment]

    def test_checks(self, bot: commands.Bot) -> None:
        def check(ctx: Any) -> bool:
            return True

        h = bot.help_command
        h.add_check(check)
        assert check in h._command_impl.checks
        h.remove_check(check)
        assert check not in h._command_impl.checks

    def test_clean_params_requires_a_context_parameter(self) -> None:
        h = commands.HelpCommand()
        impl = h._command_impl
        assert list(impl.clean_params) == ["command"]
        impl.params.clear()
        with pytest.raises(ValueError, match="Missing context parameter"):
            impl.clean_params  # noqa: B018

    def test_bot_mapping(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        mapping = h.get_bot_mapping()
        cog = populated.get_cog("Cogged")
        assert cog in mapping
        assert {c.name for c in mapping[None]} == {"help", "zeta", "grp", "denied"}
        assert {c.name for c in mapping[cog]} == {"alpha", "secret"}

    def test_invoked_with(self, server: Server, populated: commands.Bot) -> None:
        h, _, ctx = prepare(server, populated.help_command)
        assert h.invoked_with == "help"
        ctx.command = h._command_impl
        ctx.invoked_with = "aide"
        assert h.invoked_with == "aide"
        ctx.command = populated.get_command("zeta")
        assert h.invoked_with == "help"
        h.context = None  # type: ignore[assignment]
        assert h.invoked_with == "help"

    def test_command_signature(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        assert h.get_command_signature(populated.get_command("alpha")) == (
            "!alpha|al <arg>".replace("alpha|al", "[alpha|al]")
        )
        assert h.get_command_signature(populated.get_command("zeta")) == "!zeta "
        assert h.get_command_signature(populated.get_command("grp sub")) == "!grp sub "

    def test_command_signature_nested_with_aliases(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)
        grp = populated.get_command("grp")

        @grp.command(aliases=["x"])
        async def deep(ctx: commands.Context, value: int) -> None: ...

        assert h.get_command_signature(grp.get_command("deep")) == (
            "!grp [deep|x] <value>"
        )

    def test_command_signature_with_parent_signature(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)

        @populated.group()
        async def pg(ctx: commands.Context, thing: str) -> None: ...

        @pg.command()
        async def leaf(ctx: commands.Context) -> None: ...

        assert h.get_command_signature(pg.get_command("leaf")) == "!pg <thing> leaf "

    def test_remove_mentions(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        text = "@everyone @here <@123456789012345678> <@&123456789012345678>"
        assert h.remove_mentions(text) == (
            "@\u200beveryone @\u200bhere @deleted-user @deleted-role"
        )

    def test_not_found_messages(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        assert h.command_not_found("x") == 'No command called "x" found.'
        assert h.subcommand_not_found(populated.get_command("grp"), "y") == (
            'Command "grp" has no subcommand named y'
        )
        assert h.subcommand_not_found(populated.get_command("zeta"), "y") == (
            'Command "zeta" has no subcommands.'
        )

    def test_cog_property(self, bot: commands.Bot) -> None:
        h = bot.help_command
        cog = Cogged()
        h.cog = cog
        assert h.cog is cog
        assert h._command_impl in cog.get_commands()
        assert h._command_impl in list(cog.walk_commands())
        h.cog = None
        assert h.cog is None
        assert h._command_impl not in cog.get_commands()

    def test_get_max_size(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        assert h.get_max_size(populated.commands) == len("denied")
        assert h.get_max_size([]) == 0

    def test_default_destination(self, server: Server) -> None:
        h = commands.HelpCommand()
        h.context = server.context("x")
        assert h.get_destination().id == h.context.channel.id

    def test_send_error_message(self, server: Server) -> None:
        h, sink, _ = prepare(server, commands.HelpCommand())
        server.run(h.send_error_message("oops"))
        assert sink.sent == ["oops"]

    def test_base_senders_do_nothing(self, server: Server) -> None:
        h, sink, _ = prepare(server, commands.HelpCommand())
        server.run(h.send_bot_help({}))
        server.run(h.send_cog_help(MagicMock()))
        server.run(h.send_group_help(MagicMock()))
        server.run(h.send_command_help(MagicMock()))
        server.run(h.on_help_command_error(h.context, commands.CommandError()))
        assert sink.send.await_count == 0


class TestFilterCommands:
    def test_hidden_and_checks(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        result = server.run(h.filter_commands(populated.commands, sort=True))
        assert [c.name for c in result] == ["alpha", "grp", "help", "zeta"]

    def test_show_hidden(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        h.show_hidden = True
        cog = populated.get_cog("Cogged")
        result = server.run(h.filter_commands(cog.get_commands(), sort=True))
        assert [c.name for c in result] == ["alpha", "secret"]

    def test_no_verification(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        h.verify_checks = False
        result = server.run(h.filter_commands(populated.commands, sort=True))
        assert "denied" in [c.name for c in result]
        unsorted = server.run(h.filter_commands(populated.commands))
        assert {c.name for c in unsorted} == {c.name for c in result}

    def test_verification_skipped_in_dms(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)
        h.verify_checks = None
        h.context = server.context("x", in_guild=False)
        result = server.run(h.filter_commands(populated.commands, sort=True))
        assert "denied" in [c.name for c in result]
        h.context = server.context("x")
        result = server.run(h.filter_commands(populated.commands, sort=True))
        assert "denied" not in [c.name for c in result]

    def test_custom_key_and_exclude(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)
        result = server.run(
            h.filter_commands(
                populated.commands,
                sort=True,
                key=lambda c: -len(c.name),
                exclude=(commands.Group,),
            )
        )
        assert sorted(c.name for c in result) == ["alpha", "help", "zeta"]
        assert result[0].name == "alpha"

    def test_application_commands_are_ignored(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)
        slash = discord.SlashCommand(_callback(), name="app")
        result = server.run(h.filter_commands([slash, *populated.commands]))
        assert slash not in result

    def test_failing_check_raising_error_is_filtered(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)

        def failing(ctx: Any) -> bool:
            raise commands.CommandError("no")

        populated.get_command("zeta").add_check(failing)
        result = server.run(h.filter_commands(populated.commands))
        assert "zeta" not in [c.name for c in result]


class TestCommandCallback:
    def run_callback(
        self, server: Server, h: commands.HelpCommand, command: str | None
    ) -> None:
        server.run(h.command_callback(h.context, command=command))

    def test_dispatch(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, populated.help_command)
        for name in ("send_bot_help", "send_cog_help", "send_group_help"):
            setattr(h, name, AsyncMock())
        h.send_command_help = AsyncMock()
        h.prepare_help_command = AsyncMock()

        self.run_callback(server, h, None)
        h.send_bot_help.assert_awaited_once()
        assert populated.get_cog("Cogged") in h.send_bot_help.await_args.args[0]

        self.run_callback(server, h, "Cogged")
        h.send_cog_help.assert_awaited_once_with(populated.get_cog("Cogged"))

        self.run_callback(server, h, "grp")
        h.send_group_help.assert_awaited_once_with(populated.get_command("grp"))

        self.run_callback(server, h, "grp sub")
        h.send_command_help.assert_awaited_once_with(populated.get_command("grp sub"))
        assert h.prepare_help_command.await_count == 4

    def test_unknown_command(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        self.run_callback(server, h, "@everyone")
        assert sink.sent == ['No command called "@\u200beveryone" found.']

    def test_unknown_subcommand(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        self.run_callback(server, h, "grp nope")
        self.run_callback(server, h, "zeta nope")
        assert sink.sent == [
            'Command "grp" has no subcommand named nope',
            'Command "zeta" has no subcommands.',
        ]

    def test_error_handler_wiring_with_cog(
        self, server: Server, populated: commands.Bot
    ) -> None:
        class Custom(commands.DefaultHelpCommand):
            on_help_command_error = AsyncMock()

        custom = Custom()
        populated.help_command = custom
        cog = Cogged()
        custom.cog = cog
        ctx = server.context("!help")
        impl = custom._command_impl
        server.run(impl.prepare(ctx))
        assert impl.on_error == impl._on_error_cog_implementation
        err = commands.CommandError()
        server.run(impl._on_error_cog_implementation(None, ctx, err))
        impl._injected.on_help_command_error.assert_awaited_once_with(ctx, err)

    def test_error_handler_without_cog(
        self, server: Server, populated: commands.Bot
    ) -> None:
        class Custom(commands.DefaultHelpCommand):
            async def on_help_command_error(self, ctx: Any, error: Any) -> None:
                pass

        custom = Custom()
        populated.help_command = custom
        ctx = server.context("!help")
        server.run(custom._command_impl.prepare(ctx))
        assert custom._command_impl.on_error is not None

    def test_full_invocation_through_the_bot(
        self, server: Server, populated: commands.Bot
    ) -> None:
        sink = Sink()
        populated.help_command.get_destination = lambda: sink
        original = commands.DefaultHelpCommand.get_destination
        commands.DefaultHelpCommand.get_destination = lambda self: sink  # type: ignore[method-assign]
        try:
            msg = server.message("!help zeta", author=server.add_user(5, "bob"))
            server.run(populated.process_commands(msg))
        finally:
            commands.DefaultHelpCommand.get_destination = original  # type: ignore[method-assign]
        assert len(sink.sent) == 1
        assert "!zeta" in sink.sent[0]
        assert "Zeta long." in sink.sent[0]


class TestDefaultHelpCommand:
    def test_shorten_text(self) -> None:
        h = commands.DefaultHelpCommand(width=10)
        assert h.shorten_text("short") == "short"
        assert h.shorten_text("x" * 20) == "x" * 7 + "..."

    def test_bot_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        server.run(h.send_bot_help(h.get_bot_mapping()))
        assert len(sink.sent) == 1
        page = sink.sent[0]
        assert "The bot" in page
        assert "Cogged:" in page
        assert "alpha" in page
        assert "\u200bNo Category:" in page
        assert "  zeta" in page
        assert "Zeta short." in page
        assert "secret" not in page
        assert "denied" not in page
        assert "Type !help command for more info on a command." in page
        assert page.startswith("```") and page.endswith("```")

    def test_bot_help_unsorted_and_no_note(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        h.sort_commands = False
        h.get_ending_note = lambda: ""  # type: ignore[method-assign]
        server.run(h.send_bot_help({}))
        assert "Type" not in sink.sent[0]

    def test_bot_help_without_description(
        self, server: Server, populated: commands.Bot
    ) -> None:
        populated.description = ""
        h, sink, _ = prepare(server, populated.help_command)
        server.run(h.send_bot_help({}))
        assert "The bot" not in sink.sent[0]

    def test_command_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        server.run(h.send_command_help(populated.get_command("alpha")))
        page = sink.sent[0]
        assert "!alpha|al" in page.replace("[", "").replace("]", "")
        assert "Alpha help text" in page

    def test_command_help_with_description_and_long_help(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        cmd = populated.get_command("zeta")
        cmd.description = "A description"
        cmd.help = "\n".join("l" * 100 for _ in range(30))
        server.run(h.send_command_help(cmd))
        assert sink.sent[0].startswith("```\nA description")
        assert len(sink.sent) >= 2
        assert all(len(p) <= 2000 for p in sink.sent)

    def test_group_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        server.run(h.send_group_help(populated.get_command("grp")))
        page = sink.sent[0]
        assert "Group help" in page
        assert "Commands:" in page
        assert "sub" in page
        assert "Type !help command" in page

    def test_group_help_without_subcommands(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        group = populated.get_command("grp")
        group.remove_command("sub")
        group.remove_command("hidden_sub")
        server.run(h.send_group_help(group))
        assert "Commands:" not in sink.sent[0]
        assert "Type" not in sink.sent[0]

    def test_cog_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        server.run(h.send_cog_help(populated.get_cog("Cogged")))
        page = sink.sent[0]
        assert "Cog description" in page
        assert "alpha" in page
        assert "secret" not in page
        assert "Type !help command" in page

    def test_cog_help_without_description_or_note(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, populated.help_command)
        cog = populated.get_cog("Cogged")
        cog.description = ""
        h.get_ending_note = lambda: ""  # type: ignore[method-assign]
        server.run(h.send_cog_help(cog))
        assert "Cog description" not in sink.sent[0]
        assert "Type" not in sink.sent[0]

    def test_add_indented_commands_empty(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, populated.help_command)
        h.add_indented_commands([], heading="x")
        assert h.paginator.pages == []

    def test_destination_dm_rules(self, server: Server) -> None:
        h = commands.DefaultHelpCommand()
        h.context = server.context("x")
        assert h.get_destination().id == h.context.channel.id
        h.dm_help = True
        assert h.get_destination() is h.context.author
        h.dm_help = None
        assert h.get_destination().id == h.context.channel.id
        h.paginator.add_line("x" * 1500)
        h.paginator.close_page()
        h.paginator.add_line("x" * 1500)
        assert h.get_destination() is h.context.author

    def test_prepare_clears_the_paginator(self, server: Server) -> None:
        h = commands.DefaultHelpCommand()
        h.paginator.add_line("stale")
        server.run(h.prepare_help_command(server.context("x"), None))
        assert h.paginator.pages == []

    def test_ending_note(self, server: Server) -> None:
        h = commands.DefaultHelpCommand()
        h.context = server.context("x")
        assert "!help command" in h.get_ending_note()


class TestMinimalHelpCommand:
    def test_notes(self, server: Server) -> None:
        h = commands.MinimalHelpCommand()
        h.context = server.context("x")
        assert "`!help [command]`" in h.get_opening_note()
        assert h.get_ending_note() is None

    def test_signature(self, server: Server, populated: commands.Bot) -> None:
        h, _, _ = prepare(server, commands.MinimalHelpCommand())
        assert h.get_command_signature(populated.get_command("grp sub")) == (
            "!grp sub "
        )

    def test_bot_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        server.run(h.send_bot_help({}))
        page = sink.sent[0]
        assert "The bot" in page
        assert "Use `!help [command]`" in page
        assert "__**Cogged**__" in page
        assert "__**\u200bNo Category**__" in page
        assert "grp help zeta" in page

    def test_bot_help_variants(self, server: Server, populated: commands.Bot) -> None:
        populated.description = ""
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        h.sort_commands = False
        h.get_opening_note = lambda: ""  # type: ignore[method-assign]
        h.get_ending_note = lambda: "THE END"  # type: ignore[method-assign]
        server.run(h.send_bot_help({}))
        assert "Use" not in sink.sent[0]
        assert sink.sent[0].endswith("THE END")

    def test_cog_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        h.get_ending_note = lambda: "THE END"  # type: ignore[method-assign]
        server.run(h.send_cog_help(populated.get_cog("Cogged")))
        page = sink.sent[0]
        assert "The bot" in page
        assert "Cog description" in page
        assert "**Cogged Commands**" in page
        assert "!alpha \N{EN DASH} Alpha help text" in page
        assert page.endswith("THE END")

    def test_cog_help_empty(self, server: Server, populated: commands.Bot) -> None:
        populated.description = ""
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        h.get_opening_note = lambda: ""  # type: ignore[method-assign]
        cog = populated.get_cog("Cogged")
        cog.description = ""
        for command in cog.get_commands():
            command.hidden = True
        server.run(h.send_cog_help(cog))
        assert sink.sent == []

    def test_group_help(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        h.get_ending_note = lambda: "THE END"  # type: ignore[method-assign]
        server.run(h.send_group_help(populated.get_command("grp")))
        page = sink.sent[0]
        assert "Group help" in page
        assert "Use `!help [command]`" in page
        assert "**Commands**" in page
        assert "!grp sub \N{EN DASH} Sub short" in page
        assert page.endswith("THE END")

    def test_group_help_empty(self, server: Server, populated: commands.Bot) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        group = populated.get_command("grp")
        group.remove_command("sub")
        group.remove_command("hidden_sub")
        server.run(h.send_group_help(group))
        assert "**Commands**" not in sink.sent[0]

    def test_group_help_without_notes(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        h.get_opening_note = lambda: ""  # type: ignore[method-assign]
        server.run(h.send_group_help(populated.get_command("grp")))
        assert "Use" not in sink.sent[0]

    def test_command_help_with_aliases(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        cmd = populated.get_command("alpha")
        cmd.description = "Desc"
        server.run(h.send_command_help(cmd))
        page = sink.sent[0]
        assert page.startswith("Desc")
        assert "**Aliases:** al" in page
        assert "Alpha help text" in page

    def test_command_help_without_aliases_and_long_help(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, sink, _ = prepare(server, commands.MinimalHelpCommand())
        cmd = populated.get_command("zeta")
        cmd.help = "\n".join("l" * 100 for _ in range(30))
        server.run(h.send_command_help(cmd))
        assert "Aliases" not in sink.sent[0]
        assert len(sink.sent) >= 2

    def test_subcommand_formatting_without_doc(
        self, server: Server, populated: commands.Bot
    ) -> None:
        h, _, _ = prepare(server, commands.MinimalHelpCommand())
        populated.get_command("zeta").help = None
        h.add_subcommand_formatting(populated.get_command("zeta"))
        assert h.paginator.pages == ["!zeta"]

    def test_bot_commands_formatting_empty(self, server: Server) -> None:
        h = commands.MinimalHelpCommand()
        h.add_bot_commands_formatting([], "x")
        assert h.paginator.pages == []

    def test_destination_dm_rules(self, server: Server) -> None:
        h = commands.MinimalHelpCommand()
        h.context = server.context("x")
        assert h.get_destination().id == h.context.channel.id
        h.dm_help = True
        assert h.get_destination() is h.context.author
        h.dm_help = None
        h.dm_help_threshold = 5
        h.paginator.add_line("x" * 10)
        assert h.get_destination() is h.context.author

    def test_prepare_clears_the_paginator(self, server: Server) -> None:
        h = commands.MinimalHelpCommand()
        h.paginator.add_line("stale")
        server.run(h.prepare_help_command(server.context("x"), None))
        assert h.paginator.pages == []
