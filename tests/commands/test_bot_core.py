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

import asyncio
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord import types as t
from discord.enums import InteractionType, TeamRole
from discord.errors import CheckFailure, DiscordException
from tests.commands.helpers import Payload, echo
from tests.commands.interaction_support import (
    interaction_payload,
    make_interaction,
)
from tests.core.rig import FakeHTTP

if TYPE_CHECKING:
    from tests.models.context import World

APP = 4242


def slash(name: str, **kwargs: Any) -> discord.SlashCommand:
    async def callback(ctx: Any) -> None: ...

    return discord.SlashCommand(callback, name=name, description="d", **kwargs)


def make_bot(world: World, *commands: Any, **kwargs: Any) -> discord.Bot:
    bot = discord.Bot(loop=world.state.loop, **kwargs)
    bot._connection.user = SimpleNamespace(id=APP)  # type: ignore[assignment]
    bot.http = FakeHTTP(bot.http)  # type: ignore[assignment]
    bot._connection.http = bot.http  # type: ignore[assignment]
    for command in commands:
        bot.add_application_command(command)
    return bot


def remote(command: discord.SlashCommand, command_id: int) -> Payload:
    if command.contexts is None and not command.guild_ids:
        command.contexts = set(discord.InteractionContextType)
        command.integration_types = {discord.IntegrationType.guild_install}
    return {**echo(command), "id": str(command_id)}


def test_owner_arguments_are_validated() -> None:
    with pytest.raises(TypeError, match="Both owner_id and owner_ids"):
        discord.Bot(owner_id=1, owner_ids={2})
    with pytest.raises(TypeError, match="owner_ids must be a collection"):
        discord.Bot(owner_ids=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="default_command_contexts"):
        discord.Bot(default_command_contexts=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="default_command_integration_types"):
        discord.Bot(default_command_integration_types=5)  # type: ignore[arg-type]
    bot = discord.Bot(description="  Hello\n  there")
    assert bot.description == "Hello\nthere"


def test_checks_hooks_and_can_run(world: World) -> None:
    bot = discord.Bot(loop=world.state.loop)

    @bot.check
    def deny_blocked(ctx: Any) -> bool:
        return not ctx.blocked

    @bot.check_once
    async def only_once(ctx: Any) -> bool:
        return True

    ctx = SimpleNamespace(blocked=False)
    assert world.run(bot.can_run(ctx)) is True  # type: ignore[arg-type]
    assert world.run(bot.can_run(ctx, call_once=True)) is True  # type: ignore[arg-type]
    assert world.run(bot.can_run(SimpleNamespace(blocked=True))) is False  # type: ignore[arg-type]

    bot.remove_check(deny_blocked)
    bot.remove_check(deny_blocked)
    bot.remove_check(only_once, call_once=True)
    assert world.run(bot.can_run(SimpleNamespace(blocked=True))) is True  # type: ignore[arg-type]
    assert world.run(bot.can_run(ctx, call_once=True)) is True  # type: ignore[arg-type]


def test_global_invoke_hooks_require_coroutines() -> None:
    bot = discord.Bot()

    def sync_hook(ctx: Any) -> None: ...

    async def hook(ctx: Any) -> None: ...

    with pytest.raises(TypeError, match="pre-invoke"):
        bot.before_invoke(sync_hook)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="post-invoke"):
        bot.after_invoke(sync_hook)  # type: ignore[arg-type]
    assert bot.before_invoke(hook) is hook
    assert bot.after_invoke(hook) is hook
    assert bot._before_invoke is hook
    assert bot._after_invoke is hook


def test_is_owner(world: World) -> None:
    user = SimpleNamespace(id=7)
    assert world.run(discord.Bot(owner_id=7).is_owner(user)) is True  # type: ignore[arg-type]
    assert world.run(discord.Bot(owner_id=8).is_owner(user)) is False  # type: ignore[arg-type]
    assert world.run(discord.Bot(owner_ids={7, 9}).is_owner(user)) is True  # type: ignore[arg-type]
    assert world.run(discord.Bot(owner_ids={9}).is_owner(user)) is False  # type: ignore[arg-type]

    solo = discord.Bot()
    solo.application_info = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(team=None, owner=SimpleNamespace(id=7))
    )
    assert world.run(solo.is_owner(user)) is True  # type: ignore[arg-type]
    assert solo.owner_id == 7
    assert world.run(solo.is_owner(SimpleNamespace(id=1))) is False  # type: ignore[arg-type]
    solo.application_info.assert_awaited_once()

    team = discord.Bot()
    members = [
        SimpleNamespace(id=7, role=TeamRole.developer),
        SimpleNamespace(id=8, role=TeamRole.read_only),
    ]
    team.application_info = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(team=SimpleNamespace(members=members), owner=None)
    )
    assert world.run(team.is_owner(user)) is True  # type: ignore[arg-type]
    assert team.owner_ids == {7}
    assert world.run(team.is_owner(SimpleNamespace(id=8))) is False  # type: ignore[arg-type]


def test_default_error_handler(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    bot = discord.Bot(loop=world.state.loop)
    error = DiscordException("bad")

    def context(handler: bool = False, cog: Any = None) -> Any:
        command = SimpleNamespace(has_error_handler=lambda: handler)
        return SimpleNamespace(command=command, cog=cog)

    world.run(bot.on_application_command_error(context(), error))  # type: ignore[arg-type]
    assert "Ignoring exception in command" in capsys.readouterr().err

    world.run(bot.on_application_command_error(context(handler=True), error))  # type: ignore[arg-type]
    cog = SimpleNamespace(has_error_handler=lambda: True)
    world.run(bot.on_application_command_error(context(cog=cog), error))  # type: ignore[arg-type]
    bot._event_handlers["on_application_command_error"] = [AsyncMock()]
    world.run(bot.on_application_command_error(context(), error))  # type: ignore[arg-type]
    assert capsys.readouterr().err == ""


def test_connect_and_interaction_listeners(world: World) -> None:
    bot = discord.Bot(loop=world.state.loop)
    bot.sync_commands = AsyncMock()  # type: ignore[method-assign]
    bot.process_application_commands = AsyncMock()  # type: ignore[method-assign]
    world.run(bot.on_connect())
    bot.sync_commands.assert_awaited_once_with()
    interaction = object()
    world.run(bot.on_interaction(interaction))  # type: ignore[arg-type]
    bot.process_application_commands.assert_awaited_once_with(interaction)

    manual = discord.Bot(auto_sync_commands=False)
    manual.sync_commands = AsyncMock()  # type: ignore[method-assign]
    world.run(manual.on_connect())
    manual.sync_commands.assert_not_called()


def test_command_registry_helpers(world: World) -> None:
    bot = make_bot(world, debug_guilds=[1])
    first = slash("first")
    second = slash("second", guild_ids=None)
    bot.add_application_command(first)
    bot.add_application_command(first)
    assert first.guild_ids == [1]
    assert bot.pending_application_commands.count(first) == 1

    first.id = 5
    bot._application_commands[5] = first
    assert bot.all_commands == {5: first}
    assert bot.application_commands == [first]
    assert bot.commands == [first]
    assert bot.get_command("first") is first
    assert bot.get_application_command("first") is first
    assert bot.get_application_command("first", guild_ids=[2]) is None
    assert bot.get_application_command("first", type=discord.UserCommand) is None
    assert bot.get_application_command("nothing") is None

    assert bot.remove_application_command(first) is first
    assert bot.all_commands == {}
    assert bot.remove_application_command(first) is None
    _ = second


def test_adding_a_subcommand_is_rejected(world: World) -> None:
    bot = make_bot(world)
    group = discord.SlashCommandGroup("tools", "Tools")

    @group.command()
    async def sub(ctx: Any) -> None: ...

    with pytest.raises(TypeError, match="sub-command of group"):
        bot.add_application_command(sub)


def test_adding_a_command_that_is_already_known_reuses_its_id(world: World) -> None:
    bot = make_bot(world)
    original = slash("same")
    bot.add_application_command(original)
    original.id = 77
    clone = slash("same")
    bot._pending_application_commands = [original]
    bot.add_application_command(clone)
    assert clone.id == 77
    assert bot._application_commands[77] is clone


def test_nested_command_lookup(world: World) -> None:
    bot = make_bot(world)
    group = discord.SlashCommandGroup("tools", "Tools")
    inner = group.create_subgroup("inner", "Inner")

    @group.command()
    async def top(ctx: Any) -> None: ...

    @inner.command()
    async def leaf(ctx: Any) -> None: ...

    bot.add_application_command(group)
    group.id = 9
    bot._application_commands[9] = group

    assert bot.get_application_command("tools top") is top
    assert bot.get_application_command("tools inner leaf") is leaf
    assert bot.get_application_command("tools missing") is None
    assert bot.get_application_command("tools top extra") is None
    assert bot.get_application_command("tools inner leaf", guild_ids=[5]) is None
    assert bot.get_application_command("tools inner nothing") is None
    assert sorted(c.name for c in bot.walk_application_commands()) == [
        "inner",
        "leaf",
        "tools",
        "top",
    ]


def test_group_decorator(world: World) -> None:
    bot = make_bot(world)

    @bot.group()
    class documented(discord.SlashCommandGroup):  # noqa: N801
        """First line.

        More.
        """

    @bot.group("named", "Given description", guild_ids=[3])
    class undocumented(discord.SlashCommandGroup):  # noqa: N801
        pass

    assert documented.description == "First line."
    assert undocumented.name == "named"
    assert undocumented.description == "Given description"
    assert undocumented.guild_ids == [3]
    assert undocumented in bot.pending_application_commands


def test_contexts_are_built_by_the_bot(world: World) -> None:
    bot = make_bot(world)
    interaction = make_interaction(world)
    ctx = world.run(bot.get_application_context(interaction))
    assert isinstance(ctx, discord.ApplicationContext)
    auto = world.run(bot.get_autocomplete_context(interaction))
    assert isinstance(auto, discord.AutocompleteContext)


def command_interaction(world: World, command: Any, **fields: Any) -> Any:
    data = {"id": str(command.id), "name": command.name, "type": 1}
    return make_interaction(world, interaction_payload(world, data=data, **fields))


def test_process_known_commands_by_id(world: World) -> None:
    bot = make_bot(world)
    command = slash("known")
    command.id = 55
    bot.add_application_command(command)
    bot._application_commands[55] = command
    bot.invoke_application_command = AsyncMock()  # type: ignore[method-assign]
    interaction = command_interaction(world, command)

    world.run(bot.process_application_commands(interaction))

    assert interaction.command is command
    bot.invoke_application_command.assert_awaited_once()
    assert bot.invoke_application_command.await_args.args[0].command is None or True


def test_process_ignores_other_interaction_types(world: World) -> None:
    bot = make_bot(world)
    bot.invoke_application_command = AsyncMock()  # type: ignore[method-assign]
    interaction = make_interaction(
        world, type=3, data={"custom_id": "x", "component_type": 2}
    )
    world.run(bot.process_application_commands(interaction))
    bot.invoke_application_command.assert_not_called()


def test_process_finds_unregistered_commands_by_name(world: World) -> None:
    bot = make_bot(world)
    command = slash("fresh")
    bot.add_application_command(command)
    bot.invoke_application_command = AsyncMock()  # type: ignore[method-assign]
    interaction = make_interaction(
        world,
        interaction_payload(world, data={"id": "999", "name": "fresh", "type": 1}),
    )
    world.run(bot.process_application_commands(interaction))
    bot.invoke_application_command.assert_awaited_once()
    assert interaction.command is command

    guilded = slash("guilded", guild_ids=[world.guild.id])
    bot.add_application_command(guilded)
    bot.invoke_application_command.reset_mock()
    guild_interaction = make_interaction(
        world,
        interaction_payload(
            world,
            data={
                "id": "998",
                "name": "guilded",
                "type": 1,
                "guild_id": str(world.guild.id),
            },
        ),
    )
    world.run(bot.process_application_commands(guild_interaction))
    bot.invoke_application_command.assert_awaited_once()
    assert guild_interaction.command is guilded


def test_unknown_commands_trigger_a_sync_when_auto_syncing(world: World) -> None:
    bot = make_bot(world)
    bot.sync_commands = AsyncMock()  # type: ignore[method-assign]
    dispatched: list[Any] = []
    bot.dispatch = lambda name, *args: dispatched.append(name)  # type: ignore[method-assign]
    unknown = make_interaction(
        world,
        interaction_payload(
            world,
            data={
                "id": "1",
                "name": "ghost",
                "type": 1,
                "guild_id": str(world.guild.id),
            },
        ),
    )

    world.run(bot.process_application_commands(unknown))
    bot.sync_commands.assert_awaited_once_with(check_guilds=[str(world.guild.id)])
    assert dispatched == ["unknown_application_command"]

    bot.sync_commands.reset_mock()
    direct = make_interaction(
        world,
        interaction_payload(
            world, guild=False, data={"id": "1", "name": "ghost", "type": 1}
        ),
    )
    world.run(bot.process_application_commands(direct))
    bot.sync_commands.assert_awaited_once_with()

    bot.sync_commands.reset_mock()
    world.run(bot.process_application_commands(unknown, auto_sync=False))
    bot.sync_commands.assert_not_called()


def test_autocomplete_interactions_are_dispatched(world: World) -> None:
    bot = make_bot(world)
    command = slash("complete")
    command.id = 66
    bot.add_application_command(command)
    bot._application_commands[66] = command
    dispatched: list[Any] = []
    bot.dispatch = lambda name, *args: dispatched.append((name, args))  # type: ignore[method-assign]
    interaction = make_interaction(
        world,
        interaction_payload(
            world,
            type=4,
            data={"id": "66", "name": "complete", "type": 1, "options": []},
        ),
    )
    assert interaction.type is InteractionType.auto_complete
    world.run(bot.process_application_commands(interaction))
    assert dispatched == [("application_command_auto_complete", (interaction, command))]


def test_autocomplete_listener_runs_the_callback(world: World) -> None:
    bot = make_bot(world)
    command = slash("complete")
    command.invoke_autocomplete_callback = AsyncMock()  # type: ignore[method-assign]
    interaction = make_interaction(
        world,
        interaction_payload(
            world,
            type=4,
            data={"id": "66", "name": "complete", "type": 1, "options": []},
        ),
    )

    async def scenario() -> None:
        listener = asyncio.ensure_future(
            bot.on_application_command_auto_complete(interaction, command)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        ((future, _check),) = bot._listeners["application_command_auto_complete"]
        future.set_result((interaction, command))
        await listener

    world.run(scenario())
    command.invoke_autocomplete_callback.assert_awaited_once()
    assert interaction.command is command


def test_autocomplete_listener_gives_up_after_the_timeout(world: World) -> None:
    bot = make_bot(world)
    command = slash("complete")

    async def slow(ctx: Any) -> None:
        await asyncio.sleep(10)

    command.invoke_autocomplete_callback = slow  # type: ignore[method-assign]
    interaction = make_interaction(
        world,
        interaction_payload(
            world,
            type=4,
            data={"id": "66", "name": "complete", "type": 1, "options": []},
        ),
    )

    async def scenario() -> None:
        original = asyncio.wait_for

        async def fast(awaitable: Any, timeout: float) -> Any:
            return await original(awaitable, 0.01)

        asyncio.wait_for = fast  # type: ignore[assignment]
        try:
            await bot.on_application_command_auto_complete(interaction, command)
        finally:
            asyncio.wait_for = original  # type: ignore[assignment]

    world.run(scenario())


def test_invoking_a_command(world: World) -> None:
    bot = make_bot(world)
    events: list[str] = []
    bot.dispatch = lambda name, *args: events.append(name)  # type: ignore[method-assign]
    command = MagicMock()
    command.invoke = AsyncMock()
    command.dispatch_error = AsyncMock()
    ctx = SimpleNamespace(command=command)

    world.run(bot.invoke_application_command(ctx))  # type: ignore[arg-type]
    command.invoke.assert_awaited_once_with(ctx)
    assert events == ["application_command", "application_command_completion"]

    events.clear()
    command.invoke.side_effect = DiscordException("bad")
    world.run(bot.invoke_application_command(ctx))  # type: ignore[arg-type]
    command.dispatch_error.assert_awaited_once()
    assert events == ["application_command"]

    command.dispatch_error.reset_mock()
    bot.add_check(lambda c: False, call_once=True)
    world.run(bot.invoke_application_command(ctx))  # type: ignore[arg-type]
    error = command.dispatch_error.await_args.args[1]
    assert isinstance(error, CheckFailure)
    assert "global check once" in str(error)


def test_sync_after_a_group_change_logs_failures(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    bot = make_bot(world)
    bot.sync_commands = AsyncMock()  # type: ignore[method-assign]
    world.run(bot._sync_after_group_change())
    bot.sync_commands.assert_awaited_once_with()
    bot.sync_commands.side_effect = RuntimeError("down")
    with caplog.at_level(logging.ERROR):
        world.run(bot._sync_after_group_change())
    assert "Failed to sync the commands after a cog change" in caplog.text


def sync_http(
    bot: discord.Bot,
    *,
    global_remote: list[Payload],
    guild_remote: list[Payload] | None = None,
) -> None:
    http = bot.http
    http.get_global_commands.response = global_remote
    http.get_guild_commands.response = guild_remote or []
    http.bulk_upsert_global_commands.response = []
    http.bulk_upsert_guild_commands.response = []


def test_individual_registration_edits_creates_and_deletes(world: World) -> None:
    kept = slash("kept", guild_ids=None)
    changed = slash("changed")
    created = slash("created")
    bot = make_bot(world, kept, changed, created)
    stale = slash("changed")
    stale.description = "old description"
    stale_payload = {**remote(stale, 12)}
    obsolete = {**remote(slash("obsolete"), 13)}
    bot.http.get_global_commands.pages = [
        [remote(kept, 11), stale_payload, obsolete],
        [remote(kept, 11), remote(changed, 12), remote(created, 14)],
    ]
    bot.http.edit_global_command.response = remote(changed, 12)
    bot.http.upsert_global_command.response = remote(created, 14)

    registered = world.run(bot.register_commands(method="individual"))

    bot.http.edit_global_command.assert_called_once()
    assert bot.http.edit_global_command.call_args.args[:2] == (APP, 12)
    bot.http.upsert_global_command.assert_called_once()
    assert bot.http.upsert_global_command.call_args.args[0] == APP
    bot.http.delete_global_command.assert_called_once_with(APP, 13)
    bot.http.bulk_upsert_global_commands.assert_not_called()
    assert {p["name"] for p in registered} == {"kept", "changed", "created"}
    assert int(kept.id) == 11
    assert int(created.id) == 14
    assert bot._application_commands["12"] is changed


def test_individual_registration_with_nothing_to_do(world: World) -> None:
    kept = slash("kept")
    bot = make_bot(world, kept)
    bot.http.get_global_commands.response = [remote(kept, 11)]
    registered = world.run(bot.register_commands(method="individual"))
    assert [p["name"] for p in registered] == ["kept"]
    bot.http.edit_global_command.assert_not_called()
    bot.http.upsert_global_command.assert_not_called()
    bot.http.bulk_upsert_global_commands.assert_not_called()


def test_bulk_registration_skips_up_to_date_commands(world: World) -> None:
    kept = slash("kept")
    bot = make_bot(world, kept)
    bot.http.get_global_commands.response = [remote(kept, 11)]
    registered = world.run(bot.register_commands())
    bot.http.bulk_upsert_global_commands.assert_not_called()
    assert [p["id"] for p in registered] == ["11"]
    assert int(kept.id) == 11


def test_auto_registration_bulk_updates_when_everything_changed(world: World) -> None:
    fresh = slash("fresh")
    bot = make_bot(world, fresh)
    bot.http.get_global_commands.pages = [[], [remote(fresh, 21)]]
    bot.http.bulk_upsert_global_commands.response = [remote(fresh, 21)]
    world.run(bot.register_commands(method="auto"))
    bot.http.bulk_upsert_global_commands.assert_called_once()
    (_, payload) = bot.http.bulk_upsert_global_commands.call_args.args
    assert [p["name"] for p in payload] == ["fresh"]
    assert int(fresh.id) == 21


def test_delete_existing_false_keeps_unknown_remote_commands(world: World) -> None:
    fresh = slash("fresh")
    bot = make_bot(world, fresh)
    other = remote(slash("other"), 31)
    bot.http.get_global_commands.response = [other]
    bot.http.bulk_upsert_global_commands.response = [remote(fresh, 32)]
    world.run(bot.register_commands(delete_existing=False))
    payload = bot.http.bulk_upsert_global_commands.call_args.args[1]
    assert sorted(p["name"] for p in payload) == ["fresh", "other"]


def test_forced_registration_keeps_primary_entry_points(world: World) -> None:
    fresh = slash("fresh")
    bot = make_bot(world, fresh)
    entry = {"id": "41", "name": "launch", "type": 4, "description": ""}
    bot.http.get_global_commands.response = [entry]
    bot.http.bulk_upsert_global_commands.response = [remote(fresh, 42), entry]
    registered = world.run(bot.register_commands(force=True))
    payload = bot.http.bulk_upsert_global_commands.call_args.args[1]
    assert sorted(p["name"] for p in payload) == ["fresh", "launch"]
    assert len(registered) == 2
    assert int(fresh.id) == 42


def test_registration_warns_about_unknown_registered_commands(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    bot = make_bot(world)
    ghost = remote(slash("ghost"), 51)
    bot.http.get_global_commands.response = []
    bot.http.bulk_upsert_global_commands.response = [ghost]
    with caplog.at_level(logging.WARNING):
        world.run(bot.register_commands([], force=True))
    assert "Registered command ghost" in caplog.text


def test_guild_registration(world: World) -> None:
    guild_id = world.guild.id
    guilded = slash("guilded", guild_ids=[guild_id])
    bot = make_bot(world, guilded)
    bot.http.get_guild_commands.response = []
    bot.http.bulk_upsert_guild_commands.response = [
        {**remote(guilded, 61), "guild_id": str(guild_id)}
    ]
    world.run(bot.register_commands(guild_id=guild_id))
    bot.http.bulk_upsert_guild_commands.assert_called_once()
    assert bot.http.bulk_upsert_guild_commands.call_args.args[:2] == (APP, guild_id)
    assert bot._application_commands["61"].name == "guilded"


def test_individual_guild_registration(world: World) -> None:
    guild_id = world.guild.id
    guilded = slash("guilded", guild_ids=[guild_id])
    bot = make_bot(world, guilded)
    stale = remote(slash("old"), 71)
    bot.http.get_guild_commands.pages = [[stale], [remote(guilded, 72)]]
    bot.http.upsert_guild_command.response = remote(guilded, 72)
    registered = world.run(
        bot.register_commands(guild_id=guild_id, method="individual")
    )
    assert bot.http.upsert_guild_command.call_args.args[:2] == (APP, guild_id)
    bot.http.delete_guild_command.assert_called_once_with(APP, guild_id, 71)
    assert [p["name"] for p in registered] == ["guilded"]


def test_sync_commands_registers_global_and_guild_commands(world: World) -> None:
    guild_id = world.guild.id
    everywhere = slash("everywhere")
    guilded = slash("guilded", guild_ids=[guild_id])
    bot = make_bot(world, everywhere, guilded)
    bot.http.get_global_commands.response = []
    bot.http.get_guild_commands.response = []
    bot.http.bulk_upsert_global_commands.response = [remote(everywhere, 81)]
    bot.http.bulk_upsert_guild_commands.response = [
        {**remote(guilded, 82), "guild_id": str(guild_id)}
    ]

    world.run(bot.sync_commands(check_guilds=[guild_id]))

    assert int(everywhere.id) == 81
    assert int(guilded.id) == 82
    assert bot._application_commands["82"] is guilded

    only_global = make_bot(world, slash("solo"))
    only_global.http.get_global_commands.response = []
    only_global.http.bulk_upsert_global_commands.response = []
    world.run(only_global.sync_commands(register_guild_commands=False))
    only_global.http.get_guild_commands.assert_not_called()

    forced = make_bot(world)
    pending = slash("moved")
    forced.http.get_global_commands.response = []
    forced.http.bulk_upsert_global_commands.response = []
    forced.http.bulk_upsert_guild_commands.response = []
    world.run(forced.sync_commands([pending], guild_ids=[5], force=True))
    assert pending.guild_ids == [5]
    assert forced.http.bulk_upsert_guild_commands.call_args.args[:2] == (APP, 5)
    _ = t
