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

"""Tests for the shared error, context, cooldown and check code of the command stack."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord.commands import checks as shared_checks, cooldowns as shared_cooldowns
from discord.commands.context import ApplicationContext, BaseContext
from discord.ext import bridge, commands
from discord.ext.commands import cooldowns as ext_cooldowns
from discord.ext.commands.context import Context

CHECK_ERRORS = [
    commands.CheckFailure,
    commands.CheckAnyFailure,
    commands.PrivateMessageOnly,
    commands.NoPrivateMessage,
    commands.NotOwner,
    commands.MissingRole,
    commands.BotMissingRole,
    commands.MissingAnyRole,
    commands.BotMissingAnyRole,
    commands.NSFWChannelRequired,
    commands.MissingPermissions,
    commands.BotMissingPermissions,
]


@pytest.mark.parametrize("error", CHECK_ERRORS)
def test_ext_check_errors_are_discord_check_failures(error: type[Exception]) -> None:
    assert issubclass(error, commands.CheckFailure)
    assert issubclass(error, commands.CommandError)
    assert issubclass(error, discord.CheckFailure)
    assert issubclass(error, discord.ApplicationCommandError)


def test_discord_check_failure_stays_outside_ext() -> None:
    assert not issubclass(discord.CheckFailure, commands.CommandError)
    assert not issubclass(discord.CheckFailure, commands.CheckFailure)


def test_ext_check_error_is_caught_by_discord_check_failure() -> None:
    with pytest.raises(discord.CheckFailure):
        raise commands.MissingPermissions(["manage_messages"])


def test_ext_check_error_message_still_cleans_mentions() -> None:
    error = commands.CheckFailure("@everyone")
    assert "@\u200beveryone" in str(error)


@pytest.mark.parametrize(
    "name",
    [
        "BucketType",
        "Cooldown",
        "CooldownMapping",
        "DynamicCooldownMapping",
        "MaxConcurrency",
    ],
)
def test_ext_cooldowns_reexport_the_same_objects(name: str) -> None:
    assert getattr(ext_cooldowns, name) is getattr(shared_cooldowns, name)
    assert getattr(commands, name) is getattr(shared_cooldowns, name)


def test_resolve_cooldown_settings_defaults() -> None:
    buckets, concurrency = shared_cooldowns.resolve_cooldown_settings(
        cooldown=None, max_concurrency=None
    )
    assert isinstance(buckets, shared_cooldowns.CooldownMapping)
    assert not buckets.valid
    assert concurrency is None


def test_resolve_cooldown_settings_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="Cooldown"):
        shared_cooldowns.resolve_cooldown_settings(
            cooldown=object(), max_concurrency=None
        )  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="max_concurrency"):
        shared_cooldowns.resolve_cooldown_settings(
            cooldown=None, max_concurrency=object()
        )  # type: ignore[arg-type]


def test_command_and_group_share_cooldown_setup() -> None:
    mapping = shared_cooldowns.CooldownMapping.from_cooldown(
        1, 5, shared_cooldowns.BucketType.user
    )
    concurrency = shared_cooldowns.MaxConcurrency(
        1, per=shared_cooldowns.BucketType.user, wait=False
    )

    async def callback(ctx: Any) -> None: ...

    command = discord.SlashCommand(
        callback, cooldown=mapping, max_concurrency=concurrency
    )
    group = discord.SlashCommandGroup(
        "g", "d", cooldown=mapping, max_concurrency=concurrency
    )
    for target in (command, group):
        assert target._buckets is mapping
        assert target._max_concurrency is concurrency
    with pytest.raises(TypeError):
        discord.SlashCommand(callback, cooldown=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        discord.SlashCommandGroup("h", cooldown=1)  # type: ignore[arg-type]


async def test_max_concurrency_raises_ext_error() -> None:
    limit = shared_cooldowns.MaxConcurrency(
        1, per=shared_cooldowns.BucketType.default, wait=False
    )
    message = SimpleNamespace()
    await limit.acquire(message)  # type: ignore[arg-type]
    with pytest.raises(commands.MaxConcurrencyReached):
        await limit.acquire(message)  # type: ignore[arg-type]


def make_app_context(**attrs: Any) -> ApplicationContext:
    interaction = SimpleNamespace(
        guild=attrs.get("guild"),
        channel=attrs.get("channel"),
        user=attrs.get("user"),
        command=attrs.get("command"),
        app_permissions=attrs.get("app_permissions"),
        _state=SimpleNamespace(),
    )
    bot = attrs.get("bot", SimpleNamespace(user=SimpleNamespace(id=99)))
    return ApplicationContext(bot, interaction)  # type: ignore[arg-type]


def make_ext_context(**attrs: Any) -> Context:
    message = SimpleNamespace(
        guild=attrs.get("guild"),
        channel=attrs.get("channel"),
        author=attrs.get("user"),
        _state=SimpleNamespace(),
    )
    bot = attrs.get("bot", SimpleNamespace(user=SimpleNamespace(id=99)))
    return Context(message=message, bot=bot, view=None, command=attrs.get("command"))  # type: ignore[arg-type]


CONTEXT_FACTORIES = [make_app_context, make_ext_context]


def test_both_contexts_share_the_base() -> None:
    assert issubclass(ApplicationContext, BaseContext)
    assert issubclass(Context, BaseContext)
    assert issubclass(bridge.BridgeApplicationContext, BaseContext)
    assert issubclass(bridge.BridgeExtContext, BaseContext)
    assert issubclass(BaseContext, discord.abc.Messageable)


def test_base_context_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseContext()  # type: ignore[abstract]


@pytest.mark.parametrize("name", ["cog", "me", "voice_client", "get_me", "get_guild"])
def test_shared_members_are_defined_once(name: str) -> None:
    assert name not in vars(ApplicationContext)
    assert name not in vars(Context)
    assert name in vars(BaseContext)


@pytest.mark.parametrize("factory", CONTEXT_FACTORIES)
def test_cog_resolution(factory: Any) -> None:
    cog = object()
    assert factory().cog is None
    assert factory(command=SimpleNamespace(cog=cog)).cog is cog


def test_permission_name_validation_is_shared() -> None:
    for decorator in (
        commands.has_permissions,
        commands.bot_has_permissions,
        commands.has_guild_permissions,
        commands.bot_has_guild_permissions,
    ):
        with pytest.raises(TypeError, match="Invalid permission"):
            decorator(not_a_permission=True)
    with pytest.raises(TypeError):
        shared_checks.validate_permission_names(["nope"])
    shared_checks.validate_permission_names(["administrator"])


def test_missing_permissions_helper() -> None:
    granted = discord.Permissions(kick_members=True)
    assert shared_checks.missing_permissions(
        granted, {"kick_members": True, "ban_members": True, "manage_roles": False}
    ) == ["ban_members"]


def test_ext_cog_has_no_duplicated_helpers() -> None:
    assert "walk_commands" not in vars(commands.Cog)
    assert "get_commands" not in vars(commands.Cog)
    assert "__new__" not in vars(commands.Cog)
    assert "__new__" not in vars(discord.Cog)


def test_cog_walk_and_get_commands_cover_ext_and_app_commands() -> None:
    class Mixed(commands.Cog):
        @commands.group()
        async def parent(self, ctx: Any) -> None: ...

        @parent.command()
        async def child(self, ctx: Any) -> None: ...

        @discord.slash_command()
        async def slash(self, ctx: Any) -> None: ...

        grp = discord.SlashCommandGroup("grp", "d")

        @grp.command()
        async def leaf(self, ctx: Any) -> None: ...

    cog = Mixed()
    assert {c.name for c in cog.get_commands()} == {"parent", "slash", "grp"}
    assert {c.qualified_name for c in cog.walk_commands()} >= {
        "parent",
        "parent child",
        "slash",
        "grp leaf",
    }
