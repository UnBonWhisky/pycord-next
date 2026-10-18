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

import ast
import textwrap
from typing import TYPE_CHECKING

import pytest

import migrate

if TYPE_CHECKING:
    from pathlib import Path


def run(source: str, *, aggressive: bool = False) -> migrate.Result:
    result = migrate.migrate_source(textwrap.dedent(source), aggressive=aggressive)
    assert result.error is None
    ast.parse(result.migrated)
    again = migrate.migrate_source(result.migrated, aggressive=aggressive)
    assert again.migrated == result.migrated
    return result


def migrated(source: str, *, aggressive: bool = False) -> str:
    return run(source, aggressive=aggressive).migrated


def warnings(source: str) -> list[str]:
    return [n.message for n in run(source).notes if n.level == "warning"]


def body(code: str) -> str:
    return textwrap.dedent(code).strip()


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("x = bot.get_guild(1)", "x = await bot.get_guild(1)"),
        ("x = client.get_user(1)", "x = await client.get_user(1)"),
        ("x = ctx.guild.get_member(1)", "x = await ctx.guild.get_member(1)"),
        (
            "x = interaction.client.get_channel(1)",
            "x = await interaction.client.get_channel(1)",
        ),
        ("x = message.guild.get_role(1)", "x = await message.guild.get_role(1)"),
        ("x = self.bot.get_emoji(1)", "x = await self.bot.get_emoji(1)"),
        (
            "x = guild.get_channel_or_thread(1)",
            "x = await guild.get_channel_or_thread(1)",
        ),
        ("x = bot.get_guild(1).name", "x = (await bot.get_guild(1)).name"),
        (
            "await bot.get_channel(1).send('hi')",
            "await (await bot.get_channel(1)).send('hi')",
        ),
        (
            "x = bot.get_guild(1).get_member(2).name",
            "x = (await (await bot.get_guild(1)).get_member(2)).name",
        ),
        ("x = guild.get_member(1)['a']", "x = (await guild.get_member(1))['a']"),
        ("x = bot.get_user(1) is None", "x = await bot.get_user(1) is None"),
        ("x = not bot.get_user(1)", "x = not await bot.get_user(1)"),
        ("bot.clear()", "await bot.clear()"),
        (
            "x = [guild.get_member(i) for i in ids]",
            "x = [await guild.get_member(i) for i in ids]",
        ),
    ],
)
def test_lookups_are_awaited_in_coroutines(before: str, after: str) -> None:
    source = f"async def f(bot, client, guild, ctx, interaction, message, ids, self):\n    {before}\n"
    assert migrated(source).splitlines()[1].strip() == after


@pytest.mark.parametrize(
    "line",
    [
        "member.get_role(1)",
        "channel.get_thread(1)",
        "lobby.get_member(1)",
        "bot.http.get_guild(1)",
        "await bot.get_guild(1)",
        "self._connection.clear()",
        "guild.get_member_count()",
        "cache.get(1)",
    ],
)
def test_other_receivers_are_left_alone(line: str) -> None:
    source = (
        f"async def f(bot, guild, member, channel, lobby, cache, self):\n    {line}\n"
    )
    assert not run(source).changed


def test_receivers_are_inferred_from_the_code() -> None:
    source = """
        import discord
        from discord.ext import commands

        class MyBot(commands.Bot):
            async def on_ready(self):
                self.get_guild(1)

        class Child(MyBot):
            async def setup_hook(self):
                self.get_user(2)

        mine = Child()

        async def annotated(g: discord.Guild, c: "discord.Client | None"):
            g.get_member(1)
            c.get_channel(2)

        async def loops(bot):
            for g in bot.guilds:
                g.get_role(1)
            first = bot.get_guild(1)
            first.get_member(2)
            mine.get_sticker(3)
    """
    out = migrated(source)
    for line in (
        "await self.get_guild(1)",
        "await self.get_user(2)",
        "await g.get_member(1)",
        "await c.get_channel(2)",
        "await g.get_role(1)",
        "first = await bot.get_guild(1)",
        "await first.get_member(2)",
        "await mine.get_sticker(3)",
    ):
        assert line in out


def test_names_bound_to_something_else_are_not_rewritten() -> None:
    source = """
        import database

        async def f(client: database.Client):
            client.get_user(1)

        async def g():
            client = database.connect()
            client.get_message(1)
    """
    result = run(source)
    assert not result.changed
    assert len([n for n in result.notes if n.level == "warning"]) == 2


def test_aggressive_rewrites_unique_names_on_unknown_receivers() -> None:
    source = "async def f(store):\n    store.my_bot.get_guild(1)\n"
    assert not run(source).changed
    assert "await store.my_bot.get_guild(1)" in migrated(source, aggressive=True)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("def f(bot):\n    bot.get_guild(1)\n", "the function 'f' is not async"),
        ("bot.get_guild(1)\n", "module level"),
        ("async def f(bot):\n    g = lambda: bot.get_guild(1)\n", "lambda"),
        ("async def f(bot):\n    x = f'{bot.get_user(1)}'\n", "f-string"),
        (
            "async def f(guild, ids):\n    x = any(guild.get_member(i) for i in ids)\n",
            "generator expression",
        ),
        ("class C:\n    x = bot.get_guild(1)\n", "body of the class 'C'"),
    ],
)
def test_lookups_that_cannot_be_awaited_are_reported(code: str, reason: str) -> None:
    result = run(code)
    assert not result.changed
    assert any(reason in n.message for n in result.notes if n.level == "warning")


def test_async_generators_are_iterated_with_async_for() -> None:
    source = """
        import discord

        async def f(bot):
            for channel in bot.get_all_channels():
                print(channel)
            names = [m.name for m in bot.get_all_members()]
            pairs = {m.id: m for m in bot.get_all_members() if m.bot}
            nested = [c for g in groups for c in bot.get_all_channels()]
            members = list(bot.get_all_members())
            found = discord.utils.get(bot.get_all_members(), name="x")
    """
    out = migrated(source)
    assert "async for channel in bot.get_all_channels():" in out
    assert "[m.name async for m in bot.get_all_members()]" in out
    assert "{m.id: m async for m in bot.get_all_members() if m.bot}" in out
    assert "[c for g in groups async for c in bot.get_all_channels()]" in out
    assert "members = [_item async for _item in bot.get_all_members()]" in out
    assert (
        'discord.utils.get([_item async for _item in bot.get_all_members()], name="x")'
        in out
    )


def test_async_generators_outside_coroutines_are_reported() -> None:
    source = """
        def f(bot):
            for channel in bot.get_all_channels():
                pass

        async def g(bot):
            return sum(1 for _ in bot.get_all_members())
    """
    result = run(source)
    assert result.migrated == textwrap.dedent(source)
    assert len([n for n in result.notes if n.level == "warning"]) == 2


def test_state_subclasses_and_converters_become_async() -> None:
    source = """
        from discord.state import ConnectionState
        from discord.ext.commands import GuildChannelConverter

        class State(ConnectionState):
            def parse_message_create(self, data):
                pass

            def helper(self):
                pass

        class Converter(GuildChannelConverter):
            @staticmethod
            def _resolve_channel(ctx, argument, attribute, type):
                pass

        async def f(state):
            state.store_user({})
            state._connection.get_channel(1)
    """
    out = migrated(source)
    assert "    async def parse_message_create(self, data):" in out
    assert "    def helper(self):" in out
    assert "    async def _resolve_channel(ctx, argument, attribute, type):" in out
    assert "await state.store_user({})" in out
    assert "await state._connection.get_channel(1)" in out


def test_attachment_spoiler_key() -> None:
    source = "x = attachment.to_dict()['spoiler']\ny = attachment.to_dict()['url']\n"
    assert migrated(source) == (
        "x = attachment.to_dict()['is_spoiler']\ny = attachment.to_dict()['url']\n"
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("async def f(bot):\n    await bot.launch_shards()\n", "ShardManager"),
        (
            "async def f(bot):\n    await bot.ws.change_presence()\n",
            "gateway transport",
        ),
        ("def f(bot):\n    bot.ws = None\n", "read-only"),
        ("async def f(bot):\n    await bot.get_desynced_commands()\n", "payload dict"),
        ("from discord.voice.utils.buffer import Buffer\n", "JitterBuffer"),
        (
            "def f(vc):\n    return vc._connection.self_voice_state\n",
            "get_self_voice_state",
        ),
        (
            (
                "import discord\nclass B(discord.Client):\n"
                "    async def before_identify_hook(self, shard_id, *, initial):\n"
                "        pass\n"
            ),
            "no longer sleeps",
        ),
    ],
)
def test_breaking_changes_without_rewrite_are_reported(
    code: str, expected: str
) -> None:
    assert any(expected in message for message in warnings(code))


def test_comments_and_formatting_are_kept() -> None:
    source = body(
        """
        async def f(bot):  # handler
            # find it
            guild = bot.get_guild(  # the id
                1,
            )
            return guild
        """
    )
    assert migrated(source) == source.replace("guild = bot", "guild = await bot")


def test_unicode_before_the_call() -> None:
    source = "async def f(bot):\n    x = ('é', bot.get_guild(1))\n"
    assert (
        migrated(source) == "async def f(bot):\n    x = ('é', await bot.get_guild(1))\n"
    )


def test_syntax_errors_are_reported() -> None:
    result = migrate.migrate_source("def f(:\n")
    assert result.error is not None
    assert not result.changed


def test_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    package = tmp_path / "bot"
    (package / "cogs").mkdir(parents=True)
    (package / ".venv").mkdir()
    main = package / "main.py"
    main.write_text(
        "# -*- coding: latin-1 -*-\nasync def f(bot):\n    return bot.get_guild(1), 'é'\n",
        encoding="latin-1",
    )
    (package / "cogs" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (package / ".venv" / "lib.py").write_text("bot.get_guild(1)\n", encoding="utf-8")

    assert migrate.main([str(package), "--check"]) == 1
    assert migrate.main([str(package)]) == 0
    out = capsys.readouterr().out
    assert "+    return await bot.get_guild(1), 'é'" in out
    assert "lib.py" not in out

    assert migrate.main([str(package), "--write", "--quiet"]) == 0
    assert main.read_text(encoding="latin-1").endswith(
        "return await bot.get_guild(1), 'é'\n"
    )
    assert migrate.main([str(package), "--check"]) == 0

    broken = package / "broken.py"
    broken.write_text("def f(:\n", encoding="utf-8")
    assert migrate.main([str(broken)]) == 2
