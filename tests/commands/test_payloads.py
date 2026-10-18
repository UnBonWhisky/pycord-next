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

"""Automatic payload checks for every application command class."""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord.commands import core
from discord.enums import SlashCommandOptionType

if TYPE_CHECKING:
    from collections.abc import Callable

VALID_OPTION_TYPES = {t.value for t in SlashCommandOptionType}


async def callback(ctx: discord.ApplicationContext, text: str) -> None: ...


def build_slash() -> discord.SlashCommand:
    return discord.SlashCommand(callback)


def build_group() -> discord.SlashCommandGroup:
    group = discord.SlashCommandGroup("group", "Group")
    sub = group.create_subgroup("sub", "Sub")
    sub.add_command(discord.SlashCommand(callback, name="leaf"))
    group.add_command(discord.SlashCommand(callback, name="direct"))
    return group


def build_user() -> discord.UserCommand:
    async def user_cb(ctx: discord.ApplicationContext, user: discord.User) -> None: ...

    return discord.UserCommand(user_cb)


def build_message() -> discord.MessageCommand:
    async def message_cb(
        ctx: discord.ApplicationContext, message: discord.Message
    ) -> None: ...

    return discord.MessageCommand(message_cb)


def build_entry_point() -> discord.EntryPointCommand:
    async def entry_cb(ctx: discord.ApplicationContext) -> None: ...

    return discord.EntryPointCommand(entry_cb, name="launch")


BUILDERS: dict[type[discord.ApplicationCommand], Callable[[], Any]] = {
    discord.SlashCommand: build_slash,
    discord.SlashCommandGroup: build_group,
    discord.UserCommand: build_user,
    discord.MessageCommand: build_message,
    discord.EntryPointCommand: build_entry_point,
}


def concrete_command_classes() -> list[type[discord.ApplicationCommand]]:
    return [
        cls
        for _, cls in inspect.getmembers(core, inspect.isclass)
        if issubclass(cls, discord.ApplicationCommand)
        and cls is not discord.ApplicationCommand
        and cls is not core.ContextMenuCommand
    ]


def check_options(options: list[dict[str, Any]], depth: int) -> None:
    for option in options:
        assert option["type"] in VALID_OPTION_TYPES
        assert 1 <= len(option["name"]) <= 32
        if option["type"] in (1, 2):
            assert depth < 3
            check_options(option.get("options", []), depth + 1)
            if option["type"] == 2:
                assert option["options"]
                assert all(o["type"] == 1 for o in option["options"])


@pytest.mark.parametrize("cls", concrete_command_classes(), ids=lambda c: c.__name__)
def test_every_command_class_has_a_builder(cls: type) -> None:
    assert cls in BUILDERS


@pytest.mark.parametrize(
    "cls", sorted(BUILDERS, key=lambda c: c.__name__), ids=lambda c: c.__name__
)
def test_payload_round_trips(cls: type[discord.ApplicationCommand]) -> None:
    command = BUILDERS[cls]()
    bot = discord.Bot()
    bot.add_application_command(command)
    data = command.to_dict()
    assert json.loads(json.dumps(data)) == data
    assert 1 <= len(data["name"]) <= 32
    assert "integration_types" in data
    assert "contexts" in data
    check_options(data.get("options", []), 1)


def test_group_payload_has_valid_nesting() -> None:
    group = build_group()
    discord.Bot().add_application_command(group)
    data = group.to_dict()
    assert [o["type"] for o in data["options"]] == [2, 1]
    assert data["options"][0]["options"][0]["name"] == "leaf"
