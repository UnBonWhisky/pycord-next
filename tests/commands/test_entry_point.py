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


"""Tests for entry point commands and the launch activity interaction response."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord.enums import InteractionResponseType
from discord.errors import InteractionResponded
from discord.interactions import (
    Interaction,
    InteractionCallbackActivityInstanceResource,
)
from discord.webhook.async_ import async_context

from .helpers import actions, echo, make_bot, make_ctx

if TYPE_CHECKING:
    from discord.state import ConnectionState


async def launch(ctx: discord.ApplicationContext) -> None: ...


def make_entry_point(**kwargs: Any) -> discord.EntryPointCommand:
    kwargs.setdefault("name", "launch")
    return discord.EntryPointCommand(launch, **kwargs)


def test_public_names() -> None:
    assert discord.EntryPointCommand is discord.commands.EntryPointCommand
    assert discord.entry_point_command is discord.commands.entry_point_command
    assert discord.EntryPointHandler.app_handler.value == 1
    assert discord.EntryPointHandler.discord_launch_activity.value == 2
    assert InteractionResponseType.launch_activity.value == 12
    assert discord.EntryPointCommand.type == 4


def test_payload() -> None:
    bot = make_bot()
    command = make_entry_point(
        description="Launch the game",
        handler=discord.EntryPointHandler.discord_launch_activity,
        name_localizations={"fr": "lancer"},
        description_localizations={"fr": "Lance le jeu"},
        nsfw=True,
        default_member_permissions=discord.Permissions(8),
    )
    bot.add_application_command(command)
    payload = command.to_dict()
    assert sorted(payload.pop("contexts")) == [0, 1, 2]
    assert payload == {
        "name": "launch",
        "description": "Launch the game",
        "type": 4,
        "name_localizations": {"fr": "lancer"},
        "description_localizations": {"fr": "Lance le jeu"},
        "nsfw": True,
        "default_member_permissions": 8,
        "handler": 2,
        "integration_types": [0],
    }


def test_handler_is_left_out_when_unset() -> None:
    bot = make_bot()
    command = make_entry_point()
    bot.add_application_command(command)
    assert "handler" not in command.to_dict()
    assert command.description == "No description provided"


def test_docstring_is_the_default_description() -> None:
    async def play(ctx: discord.ApplicationContext) -> None:
        """Play the game.

        More text.
        """

    assert discord.EntryPointCommand(play).description == "Play the game."


def test_validation() -> None:
    with pytest.raises(TypeError):
        make_entry_point(handler=2)
    with pytest.raises(discord.InvalidArgument):
        make_entry_point(guild_ids=[1])

    def not_a_coroutine(ctx: discord.ApplicationContext) -> None: ...

    with pytest.raises(TypeError):
        discord.EntryPointCommand(not_a_coroutine)

    async def no_ctx() -> None: ...

    async def too_many(ctx: discord.ApplicationContext, extra: int) -> None: ...

    with pytest.raises(discord.ClientException):
        discord.EntryPointCommand(no_ctx)
    with pytest.raises(discord.ClientException):
        discord.EntryPointCommand(too_many)
    with pytest.raises(discord.ValidationError):
        make_entry_point(name="Not Valid")


def test_entry_point_ignores_debug_guilds() -> None:
    bot = make_bot(debug_guilds=[1, 2])
    command = make_entry_point()
    other = discord.SlashCommand(launch, name="other", description="d")
    bot.add_application_command(command)
    bot.add_application_command(other)
    assert command.guild_ids is None
    assert other.guild_ids == [1, 2]
    assert "contexts" in command.to_dict()


def test_bot_decorators() -> None:
    bot = make_bot()

    @bot.entry_point_command(handler=discord.EntryPointHandler.app_handler)
    async def start(ctx: discord.ApplicationContext) -> None: ...

    @discord.entry_point_command(name="other", description="Another one")
    async def second(ctx: discord.ApplicationContext) -> None: ...

    assert isinstance(start, discord.EntryPointCommand)
    assert isinstance(second, discord.EntryPointCommand)
    assert start in bot.pending_application_commands
    assert start.handler is discord.EntryPointHandler.app_handler
    assert second.name == "other"
    assert second.description == "Another one"


async def test_invocation() -> None:
    seen: list[Any] = []

    class Games(discord.Cog):
        @discord.entry_point_command()
        async def start(self, ctx: discord.ApplicationContext) -> None:
            seen.append((self, ctx))

    bot = make_bot()
    cog = Games()
    bot.add_cog(cog)
    (command,) = bot.pending_application_commands
    assert isinstance(command, discord.EntryPointCommand)
    assert command.cog is cog
    ctx = make_ctx(bot, "start")
    await command.invoke(ctx)
    assert seen == [(cog, ctx)]
    assert ctx.command is command


async def test_plain_function_invocation() -> None:
    seen: list[Any] = []
    bot = make_bot()

    @bot.entry_point_command()
    async def start(ctx: discord.ApplicationContext) -> None:
        seen.append(ctx)

    ctx = make_ctx(bot, "start")
    await start.invoke(ctx)
    assert seen == [ctx]


def test_cog_command_attrs_copy_the_command() -> None:
    class Games(discord.Cog, command_attrs={"nsfw": True}):
        @discord.entry_point_command(handler=discord.EntryPointHandler.app_handler)
        async def start(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Games())
    (command,) = bot.pending_application_commands
    assert command.nsfw is True
    assert command.handler is discord.EntryPointHandler.app_handler
    copied = command.copy()
    assert copied.handler is command.handler
    assert copied.name == command.name
    bot.remove_cog("Games")
    assert not bot.pending_application_commands


async def test_sync_compares_the_handler() -> None:
    command = make_entry_point(
        handler=discord.EntryPointHandler.discord_launch_activity
    )
    bot = make_bot(command)
    remote = echo(command)
    assert await actions(bot, [remote]) == [("launch", None)]

    remote["handler"] = 1
    assert await actions(bot, [remote]) == [("launch", "edit")]

    del remote["handler"]
    assert await actions(bot, [remote]) == [("launch", "edit")]


async def test_sync_leaves_the_discord_default_handler_alone() -> None:
    command = make_entry_point()
    bot = make_bot(command)
    remote = echo(command)
    remote["handler"] = 2
    assert await actions(bot, [remote]) == [("launch", None)]
    remote["description"] = "Changed on the dashboard"
    assert await actions(bot, [remote]) == [("launch", "edit")]


async def test_entry_point_and_slash_command_may_share_a_name() -> None:
    entry = make_entry_point()
    slash = discord.SlashCommand(launch, name="launch", description="d", options=[])
    bot = make_bot(entry, slash)
    assert await actions(bot, [echo(entry)]) == [("launch", None), ("launch", "upsert")]


def make_interaction(state: ConnectionState) -> Interaction:
    return Interaction(
        data={
            "id": "1",
            "application_id": "2",
            "type": 2,
            "token": "token",
            "version": 1,
            "data": {"id": "3", "name": "launch", "type": 4},
            "user": {
                "id": "5",
                "username": "user",
                "discriminator": "0",
                "avatar": None,
                "global_name": None,
            },
        },  # type: ignore[typeddict-item]
        state=state,
    )


async def test_launch_activity(state: ConnectionState) -> None:
    interaction = make_interaction(state)
    adapter = AsyncMock()
    adapter.create_interaction_response.return_value = {
        "interaction": {"id": "1", "type": 2, "activity_instance_id": "instance-1"},
        "resource": {"type": 12, "activity_instance": {"id": "instance-1"}},
    }
    reset = async_context.set(adapter)
    try:
        returned = await interaction.response.launch_activity()
    finally:
        async_context.reset(reset)

    assert returned is interaction
    assert interaction.response.is_done()
    kwargs = adapter.create_interaction_response.await_args.kwargs
    assert kwargs["type"] == 12
    assert adapter.create_interaction_response.await_args.args == (1, "token")
    assert isinstance(
        interaction.activity_instance, InteractionCallbackActivityInstanceResource
    )
    assert interaction.activity_instance.id == "instance-1"
    assert interaction.callback is not None
    assert interaction.callback.activity_instance_id == "instance-1"
    assert "instance-1" in repr(interaction.callback)

    with pytest.raises(InteractionResponded):
        await interaction.response.launch_activity()


async def test_launch_activity_without_a_resource(state: ConnectionState) -> None:
    interaction = make_interaction(state)
    assert interaction.activity_instance is None
    adapter = AsyncMock()
    adapter.create_interaction_response.return_value = {
        "interaction": {"id": "1", "type": 2},
    }
    reset = async_context.set(adapter)
    try:
        await interaction.response.launch_activity()
    finally:
        async_context.reset(reset)
    assert interaction.activity_instance is None
    assert interaction.callback is not None
    assert interaction.callback.activity_instance_id is None
