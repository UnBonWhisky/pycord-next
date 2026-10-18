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

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

import discord
from discord.commands.context import AutocompleteContext
from discord.interactions import InteractionResponse
from tests.commands.interaction_support import (
    MEMBER_ID,
    interaction_payload,
    make_context,
    make_interaction,
)

if TYPE_CHECKING:
    from tests.models.context import World


def slash_command() -> discord.SlashCommand:
    async def cb(ctx: Any, first: str, second: str = "x") -> None: ...

    return discord.SlashCommand(
        cb,
        name="cmd",
        description="d",
        options=[
            discord.Option(str, name="first"),
            discord.Option(str, name="second", required=False),
        ],
    )


def test_context_mirrors_the_interaction(world: World) -> None:
    payload = interaction_payload(
        world,
        locale="fr",
        guild_locale="de",
        data={
            "id": "1",
            "name": "cmd",
            "type": 1,
            "options": [{"name": "first", "type": 3, "value": "a"}],
        },
    )
    ctx = make_context(world, payload)
    ctx.command = slash_command()

    assert ctx.channel_id == world.channel.id
    assert ctx.guild_id == world.guild.id
    assert ctx.locale == "fr"
    assert ctx.guild_locale == "de"
    assert ctx.response is ctx.interaction.response
    assert ctx.selected_options == [{"name": "first", "type": 3, "value": "a"}]
    assert [o.name for o in ctx.unselected_options] == ["second"]
    assert ctx.attachment_size_limit == ctx.interaction.attachment_size_limit
    assert ctx.send_modal == ctx.interaction.response.send_modal
    assert ctx.defer == ctx.interaction.response.defer
    assert ctx.edit == ctx.interaction.edit_original_response
    assert world.run(ctx._get_channel()) is ctx.interaction.channel


def test_selected_and_unselected_options_edge_cases(world: World) -> None:
    ctx = make_context(world)
    ctx.interaction.data = None
    assert ctx.selected_options is None
    ctx.interaction.data = {"id": "1", "name": "cmd", "type": 1}  # type: ignore[typeddict-item]
    assert ctx.selected_options is None

    ctx.command = None
    assert ctx.unselected_options is None
    command = slash_command()
    ctx.command = command
    assert ctx.unselected_options == command.options


def test_authorisation_helpers_delegate(world: World) -> None:
    ctx = make_context(world)
    with (
        patch.object(type(ctx.interaction), "is_guild_authorised", return_value=True),
        patch.object(type(ctx.interaction), "is_user_authorised", return_value=False),
    ):
        assert ctx.is_guild_authorised() is True
        assert ctx.is_guild_authorized() is True
        assert ctx.is_user_authorised() is False
        assert ctx.is_user_authorized() is False


def test_send_response_and_followup_depend_on_the_response_state(world: World) -> None:
    ctx = make_context(world)
    assert ctx.send_response == ctx.interaction.response.send_message
    with pytest.raises(RuntimeError, match=r"respond\(\) first"):
        _ = ctx.send_followup
    ctx.interaction.response._responded = True
    assert ctx.send_followup == ctx.followup.send
    with pytest.raises(RuntimeError, match="already issued a response"):
        _ = ctx.send_response


def test_delete_defers_first(world: World) -> None:
    ctx = make_context(world)
    with (
        patch.object(InteractionResponse, "defer", new=AsyncMock()) as defer,
        patch.object(
            type(ctx.interaction), "delete_original_response", new=AsyncMock()
        ) as delete,
    ):
        world.run(ctx.delete(delay=2))
    defer.assert_awaited_once_with()
    delete.assert_awaited_once_with(delay=2)


def test_delete_after_a_response_does_not_defer(world: World) -> None:
    ctx = make_context(world)
    ctx.interaction.response._responded = True
    with patch.object(
        type(ctx.interaction), "delete_original_response", new=AsyncMock()
    ) as delete:
        world.run(ctx.delete())
    delete.assert_awaited_once_with(delay=None)


def test_invoke_calls_the_command_with_the_context(world: World) -> None:
    ctx = make_context(world)
    seen: list[Any] = []

    async def cb(context: Any, value: int) -> str:
        seen.append((context, value))
        return "done"

    command = discord.SlashCommand(
        cb, name="cmd", description="d", options=[discord.Option(int, name="value")]
    )
    assert world.run(ctx.invoke(command, 5)) == "done"
    assert seen == [(ctx, 5)]


def test_autocomplete_context(world: World) -> None:
    interaction = make_interaction(world)
    bot = SimpleNamespace()
    ctx = AutocompleteContext(bot, interaction)  # type: ignore[arg-type]
    assert ctx.bot is bot
    assert ctx.command is None
    assert ctx.cog is None

    command = SimpleNamespace(cog="the-cog")
    ctx.command = command  # type: ignore[assignment]
    assert interaction.command is command
    assert ctx.command is command
    assert ctx.cog == "the-cog"
    _ = MEMBER_ID
