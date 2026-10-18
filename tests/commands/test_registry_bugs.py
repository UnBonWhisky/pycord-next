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

"""Regression tests for the bugs found while probing the command registry."""

from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands


def test_copy_keeps_positional_guild_ids() -> None:
    group = discord.SlashCommandGroup("g", "d", [123])
    assert group.copy().guild_ids == [123]


def test_copy_keeps_keyword_guild_ids() -> None:
    group = discord.SlashCommandGroup("g", "d", guild_ids=[5])
    assert group.copy().guild_ids == [5]


def test_copy_keeps_positional_cooldown_settings() -> None:
    mapping = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user)
    concurrency = commands.MaxConcurrency(1, per=commands.BucketType.user, wait=True)
    group = discord.SlashCommandGroup("g", "d", None, None, mapping, concurrency)
    clone = group.copy()
    assert clone._buckets is mapping
    assert clone._max_concurrency is concurrency


def test_create_subgroup_guild_ids_survive_copy() -> None:
    group = discord.SlashCommandGroup("g", "d")
    sub = group.create_subgroup("s", "sd", [7])
    assert sub.guild_ids == [7]
    assert sub.copy().guild_ids == [7]


def test_update_copy_with_positional_name() -> None:
    group = discord.SlashCommandGroup("g", "d", [1])
    clone = group._update_copy({"nsfw": True})
    assert (clone.name, clone.description, clone.guild_ids, clone.nsfw) == (
        "g",
        "d",
        [1],
        True,
    )


def test_cog_command_attrs_with_positional_group() -> None:
    class Attrs(discord.Cog, command_attrs={"nsfw": True}):
        group = discord.SlashCommandGroup("attrs", "d")

    (copied,) = Attrs.__cog_commands__
    assert copied.name == "attrs"
    assert copied.nsfw is True


async def callback(ctx: Any) -> None: ...


def test_remove_application_command_removes_the_identical_object() -> None:
    bot = discord.Bot()
    first = discord.SlashCommand(callback, name="same")
    second = discord.SlashCommand(callback, name="same")
    assert first == second
    bot._pending_application_commands.extend([first, second])
    assert bot.remove_application_command(second) is second
    assert bot.pending_application_commands == [first]
    assert bot.pending_application_commands[0] is first


def test_remove_application_command_falls_back_to_equality() -> None:
    bot = discord.Bot()
    registered = discord.SlashCommand(callback, name="same")
    bot.add_application_command(registered)
    equal = discord.SlashCommand(callback, name="same")
    assert bot.remove_application_command(equal) is equal
    assert bot.pending_application_commands == []


def test_remove_application_command_unknown_returns_none() -> None:
    bot = discord.Bot()
    assert bot.remove_application_command(discord.SlashCommand(callback)) is None


def test_adding_the_same_command_twice_registers_it_once() -> None:
    bot = discord.Bot()
    command = discord.SlashCommand(callback)
    bot.add_application_command(command)
    bot.add_application_command(command)
    assert bot.pending_application_commands == [command]
