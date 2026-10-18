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

"""Helpers shared by the application command tests."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import discord

Payload = dict[str, Any]
APP_ID = 4242


def make_bot(*commands: Any, **kwargs: Any) -> discord.Bot:
    bot = discord.Bot(**kwargs)
    for command in commands:
        bot.add_application_command(command)
    return bot


def fill_option(option: Payload, explicit: bool) -> Payload:
    option = copy.deepcopy(option)
    if option.get("type") in (1, 2):
        return fill_node(option, explicit, top=False)
    if explicit:
        option.setdefault("required", False)
        option.setdefault("choices", [])
        option.setdefault("autocomplete", False)
        option.setdefault("name_localizations", None)
        option.setdefault("description_localizations", None)
        option["choices"] = [
            {"name_localizations": None, **choice} for choice in option["choices"]
        ]
    else:
        if option.get("required") is False:
            del option["required"]
        if option.get("autocomplete") is False:
            del option["autocomplete"]
        if option.get("choices") == []:
            del option["choices"]
    return option


def fill_node(node: Payload, explicit: bool, *, top: bool) -> Payload:
    node = copy.deepcopy(node)
    if "options" in node:
        node["options"] = [fill_option(o, explicit) for o in node["options"]]
    if explicit:
        node.setdefault("name_localizations", None)
        node.setdefault("description_localizations", None)
    if top:
        if "default_member_permissions" in node:
            node["default_member_permissions"] = str(node["default_member_permissions"])
        if explicit:
            node.setdefault("type", 1)
            node.setdefault("nsfw", False)
            node.setdefault("default_member_permissions", None)
            node["dm_permission"] = True
            node["default_permission"] = True
        elif node.get("nsfw") is False:
            del node["nsfw"]
        node.update(id="1", application_id=str(APP_ID), version="1")
    return node


def echo(command: Any, *, explicit: bool = True) -> Payload:
    return fill_node(command.to_dict(), explicit, top=True)


async def actions(
    bot: discord.Bot, remote: list[Payload], guild_id: int | None = None
) -> list[tuple[str, str | None]]:
    desynced = await bot.get_desynced_commands(guild_id=guild_id, prefetched=remote)
    return [
        (
            c["command"]["name"]
            if isinstance(c["command"], dict)
            else c["command"].name,
            c["action"],
        )
        for c in desynced
    ]


def make_ctx(bot: discord.Bot, name: str) -> discord.ApplicationContext:
    interaction = SimpleNamespace(
        data={"name": name, "type": 1},
        command=None,
        guild=None,
        user=SimpleNamespace(id=1),
        channel=None,
        _state=SimpleNamespace(),
    )
    return discord.ApplicationContext(bot, interaction)  # type: ignore[arg-type]
