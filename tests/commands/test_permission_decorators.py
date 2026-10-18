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

from __future__ import annotations

from typing import Any

import pytest

import discord
from discord import InteractionContextType, Permissions
from discord.commands.permissions import default_permissions, guild_only, is_nsfw


def make_command() -> Any:
    @discord.slash_command()
    async def sample(ctx: Any) -> None: ...

    return sample


def test_default_permissions_on_a_command_sets_the_defaults() -> None:
    command = default_permissions(manage_messages=True)(make_command())

    assert command.default_member_permissions == Permissions(manage_messages=True)


def test_default_permissions_on_a_callback_is_read_when_the_command_is_built() -> None:
    async def callback(ctx: Any) -> None: ...

    marked = default_permissions(kick_members=True)(callback)
    assert marked is callback
    command = discord.slash_command()(marked)

    assert command.default_member_permissions == Permissions(kick_members=True)


def test_default_permissions_rejects_unknown_flags() -> None:
    with pytest.raises(TypeError, match="Invalid permission"):
        default_permissions(not_a_permission=True)


def test_default_permissions_rejects_subcommands() -> None:
    group = discord.SlashCommandGroup("grp", "group")

    @group.command()
    async def child(ctx: Any) -> None: ...

    with pytest.raises(RuntimeError, match="top-level"):
        default_permissions(administrator=True)(child)


def test_guild_only_on_a_command_and_a_callback() -> None:
    command = guild_only()(make_command())
    assert command.contexts == {InteractionContextType.guild}

    async def callback(ctx: Any) -> None: ...

    built = discord.slash_command()(guild_only()(callback))
    assert built.contexts == {InteractionContextType.guild}


def test_is_nsfw_on_a_command_and_a_callback() -> None:
    command = is_nsfw()(make_command())
    assert command.nsfw is True

    async def callback(ctx: Any) -> None: ...

    built = discord.slash_command()(is_nsfw()(callback))
    assert built.nsfw is True
