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

# ruff: noqa: N805

"""Tests for the bridge context typing support and bridge subgroups."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord.context_managers import Typing
from discord.ext import bridge, commands
from discord.ext.bridge.context import (
    BridgeApplicationContext,
    BridgeContext,
    BridgeExtContext,
    DeferTyping,
)


class FakeAppContext:
    def __init__(self) -> None:
        self._state = SimpleNamespace(loop=asyncio.get_running_loop())
        self.deferred: list[bool] = []

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.deferred.append(ephemeral)


def test_bridge_context_requires_typing_implementation() -> None:
    assert "_typing" in BridgeContext.__abstractmethods__
    assert "typing" not in BridgeContext.__abstractmethods__


def test_defer_typing_is_exported() -> None:
    assert bridge.DeferTyping is DeferTyping
    assert "DeferTyping" in bridge.context.__all__


async def test_defer_typing_defers_while_active() -> None:
    ctx = FakeAppContext()
    with DeferTyping(ctx, ephemeral=True):  # type: ignore[arg-type]
        await asyncio.sleep(0)
    assert ctx.deferred == [True]


async def test_defer_typing_async_context_manager() -> None:
    ctx = FakeAppContext()
    async with DeferTyping(ctx):  # type: ignore[arg-type]
        await asyncio.sleep(0)
    assert ctx.deferred == [False]


async def test_defer_typing_exit_cancels_a_pending_defer() -> None:
    ctx = FakeAppContext()
    manager = DeferTyping(ctx)  # type: ignore[arg-type]
    with manager:
        pass
    await asyncio.sleep(0)
    assert manager.task.cancelled()
    assert ctx.deferred == []


async def test_bridge_application_context_typing_defers() -> None:
    state = SimpleNamespace(loop=asyncio.get_running_loop())
    ctx = BridgeApplicationContext.__new__(BridgeApplicationContext)
    ctx._state = state  # type: ignore[assignment]
    manager = ctx.typing(ephemeral=True)
    assert isinstance(manager, DeferTyping)
    assert manager.ephemeral is True
    assert manager.ctx is ctx


async def test_bridge_ext_context_typing_drops_ephemeral() -> None:
    state = SimpleNamespace(loop=asyncio.get_running_loop())
    ctx = BridgeExtContext.__new__(BridgeExtContext)
    ctx._state = state  # type: ignore[assignment]
    manager = ctx.typing(ephemeral=True)
    assert isinstance(manager, Typing)


def make_bot() -> bridge.Bot:
    return bridge.Bot(command_prefix="!", intents=discord.Intents.default())


def build_group(bot: bridge.Bot) -> bridge.BridgeCommandGroup:
    @bot.bridge_group()
    async def top(ctx: Any) -> None: ...

    @top.subgroup(description="sub description")
    async def sub(ctx: Any) -> None: ...

    @sub.command()
    async def leaf(ctx: Any) -> None: ...

    @top.command()
    async def direct(ctx: Any) -> None: ...

    return top


def test_bridge_subgroup_builds_both_variants() -> None:
    bot = make_bot()
    top = build_group(bot)
    (sub, direct) = top.subcommands
    assert isinstance(sub, bridge.BridgeCommandGroup)
    assert sub.parent is top
    assert isinstance(sub.slash_variant, discord.SlashCommandGroup)
    assert sub.slash_variant.parent is top.slash_variant
    assert sub.slash_variant.description == "sub description"
    assert sub.ext_variant.parent is top.ext_variant
    assert sub.name == "sub"
    assert direct.name == "direct"


def test_bridge_group_walk_commands_is_recursive() -> None:
    top = build_group(make_bot())
    assert [c.name for c in top.walk_commands()] == ["sub", "leaf", "direct"]


def test_bridge_subgroup_slash_payload() -> None:
    bot = make_bot()
    build_group(bot)
    (payload,) = [c.to_dict() for c in bot.pending_application_commands]
    (sub, direct) = payload["options"]
    assert (sub["name"], sub["type"]) == ("sub", 2)
    assert [o["name"] for o in sub["options"]] == ["leaf"]
    assert (direct["name"], direct["type"]) == ("direct", 1)


def test_bridge_subgroup_is_reachable_with_prefix() -> None:
    bot = make_bot()
    build_group(bot)
    assert bot.get_command("top sub leaf") is not None
    assert isinstance(bot.get_command("top sub"), commands.Group)


def test_bridge_subgroup_defaults_to_function_name() -> None:
    bot = make_bot()

    @bot.bridge_group()
    async def parent(ctx: Any) -> None: ...

    @parent.subgroup()
    async def child(ctx: Any) -> None: ...

    assert child.name == "child"
    assert child.slash_variant.name == "child"


def test_bridge_group_in_cog_registers_nested_commands() -> None:
    bot = make_bot()

    class Nested(commands.Cog):
        @bridge.bridge_group()
        async def g(self, ctx: Any) -> None: ...

        @g.subgroup()
        async def sg(self, ctx: Any) -> None: ...

        @sg.command()
        async def leaf(self, ctx: Any) -> None: ...

    cog = Nested()
    bot.add_cog(cog)
    command = bot.get_command("g sg leaf")
    assert command is not None
    assert command.cog is cog
    (payload,) = [
        c.to_dict() for c in bot.pending_application_commands if c.name == "g"
    ]
    assert payload["options"][0]["options"][0]["name"] == "leaf"


def test_bridge_group_name_is_not_consumed_by_decorator_reuse() -> None:
    decorator = bridge.bridge_group(description="d")

    async def first(ctx: Any) -> None: ...

    async def second(ctx: Any) -> None: ...

    assert decorator(first).name == "first"
    assert decorator(second).name == "second"


@pytest.mark.parametrize("data", [None, {}])
async def test_bridge_slash_group_invoke_without_subcommand_data(
    data: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[Any] = []

    async def callback(_ctx: Any) -> None: ...

    group = bridge.BridgeCommandGroup(callback, name="g")
    ctx = SimpleNamespace(interaction=SimpleNamespace(data=data), command=None)

    async def fake_invoke(_self: Any, invoked_ctx: Any) -> None:
        called.append(invoked_ctx)

    monkeypatch.setattr(bridge.BridgeSlashCommand, "invoke", fake_invoke)
    await group.slash_variant._invoke(ctx)  # type: ignore[arg-type]
    assert called == [ctx]
    assert isinstance(ctx.command, bridge.BridgeSlashCommand)


def test_bridge_group_shared_between_cogs() -> None:
    bot = make_bot()

    @bot.bridge_group()
    async def top(ctx: discord.ApplicationContext) -> None: ...

    class First(commands.Cog):
        @top.command()
        async def one(self, ctx: discord.ApplicationContext) -> None: ...

    class Second(commands.Cog):
        @top.subgroup()
        async def sub(ctx: discord.ApplicationContext) -> None: ...

        @top.command()
        async def two(self, ctx: discord.ApplicationContext) -> None: ...

        @sub.command()
        async def deep(self, ctx: discord.ApplicationContext) -> None: ...

    assert bot.get_command("top one") is None
    first, second = First(), Second()
    bot.add_cog(first)
    bot.add_cog(second)
    (payload,) = [c.to_dict() for c in bot.pending_application_commands]
    names = {o["name"] for o in payload["options"]}
    assert names == {"one", "two", "sub"}
    assert bot.get_command("top one").cog is first
    assert bot.get_command("top two").cog is second
    assert bot.get_command("top sub deep").cog is second
    bot.remove_cog("Second")
    assert bot.get_command("top two") is None
    assert bot.get_command("top sub") is None
    assert bot.get_command("top one") is not None
    (payload,) = [c.to_dict() for c in bot.pending_application_commands]
    assert {o["name"] for o in payload["options"]} == {"one"}
    bot.remove_cog("First")
    assert bot.get_command("top one") is None
    assert [c.name for c in bot.pending_application_commands] == ["top"]
