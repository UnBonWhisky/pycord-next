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


"""Cooldown and concurrency buckets of application commands on every cache backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.commands.cooldowns import BucketType, CooldownMapping, MaxConcurrency
from discord.ext import commands
from discord.role import Role
from tests.commands.interaction_support import (
    MEMBER_ID,
    OTHER_ID,
    backend_world,
    interaction_payload,
    make_context,
    member_payload,
)

if TYPE_CHECKING:
    from discord.commands.context import ApplicationContext
    from tests.models.context import World

__all__ = ("backend_world",)

MOD = 8201
ADMIN = 8202
CATEGORY = 8301


def set_role(world: World, role_id: int, position: int) -> Role:
    payload = world.payload(
        t.role.Role, id=str(role_id), position=position, name=f"role-{role_id}"
    )
    payload.pop("tags", None)
    role = Role(guild=world.guild, state=world.state, data=payload)
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def context_for(
    world: World, user_id: int, roles: list[int], **fields: Any
) -> ApplicationContext:
    member = member_payload(world, user_id, roles=[str(role_id) for role_id in roles])
    return make_context(world, interaction_payload(world, member=member, **fields))


@pytest.fixture
def roles(backend_world: World) -> None:
    set_role(backend_world, MOD, 2)
    set_role(backend_world, ADMIN, 3)


def make_command(**kwargs: Any) -> discord.SlashCommand:
    async def ping(ctx: discord.ApplicationContext) -> None: ...

    return discord.SlashCommand(ping, name="ping", description="Ping", **kwargs)


def invoke(world: World, command: discord.SlashCommand, ctx: Any) -> None:
    async def can_run(_ctx: Any) -> bool:
        return True

    ctx.bot.can_run = can_run
    ctx.bot._before_invoke = None
    ctx.bot._after_invoke = None

    async def run() -> None:
        await command.prepare(ctx)

    world.run(run())


@pytest.mark.usefixtures("roles")
class TestRoleBuckets:
    def test_keys(self, backend_world: World) -> None:
        admin = context_for(backend_world, MEMBER_ID, [MOD, ADMIN])
        mod = context_for(backend_world, OTHER_ID, [MOD])
        plain = context_for(backend_world, 8500, [])

        def key(ctx: Any) -> Any:
            return backend_world.run(BucketType.role.get_key_async(ctx))

        assert key(admin) == ADMIN
        assert key(mod) == MOD
        assert key(plain) == backend_world.guild.id

    def test_direct_messages_use_the_channel(self, backend_world: World) -> None:
        ctx = make_context(
            backend_world,
            interaction_payload(backend_world, guild=False, channel_id="8600"),
        )
        assert backend_world.run(BucketType.role.get_key_async(ctx)) == 8600

    def test_cooldown_per_role_on_invocation(self, backend_world: World) -> None:
        command = make_command(
            cooldown=CooldownMapping.from_cooldown(1, 60, BucketType.role)
        )
        admin = context_for(backend_world, MEMBER_ID, [MOD, ADMIN])
        same_role = context_for(backend_world, 8501, [ADMIN])
        mod = context_for(backend_world, OTHER_ID, [MOD])

        invoke(backend_world, command, admin)
        invoke(backend_world, command, mod)
        with pytest.raises(commands.CommandOnCooldown):
            invoke(backend_world, command, same_role)

    def test_max_concurrency_per_role_on_invocation(self, backend_world: World) -> None:
        command = make_command(
            max_concurrency=MaxConcurrency(1, per=BucketType.role, wait=False)
        )
        admin = context_for(backend_world, MEMBER_ID, [ADMIN])
        same_role = context_for(backend_world, 8501, [ADMIN])
        mod = context_for(backend_world, OTHER_ID, [MOD])

        invoke(backend_world, command, admin)
        invoke(backend_world, command, mod)
        with pytest.raises(commands.MaxConcurrencyReached):
            invoke(backend_world, command, same_role)

        async def release() -> None:
            assert command._max_concurrency is not None
            await command._max_concurrency.release(admin)

        backend_world.run(release())
        invoke(backend_world, command, same_role)

    def test_the_sync_key_follows_the_cache_backend(self, backend_world: World) -> None:
        ctx = context_for(backend_world, MEMBER_ID, [ADMIN])
        if backend_world.state.cache.supports_sync:
            assert BucketType.role.get_key(ctx) == ADMIN  # type: ignore[arg-type]
        else:
            with pytest.raises(discord.SyncCacheAccessError):
                BucketType.role.get_key(ctx)  # type: ignore[arg-type]


class TestCategoryBuckets:
    @staticmethod
    def categorised(world: World, channel_id: int, category_id: int | None) -> Any:
        channel = world.payload(
            t.channel.TextChannel,
            id=str(channel_id),
            guild_id=str(world.guild.id),
            parent_id=None if category_id is None else str(category_id),
        )
        return make_context(
            world,
            interaction_payload(world, channel_id=str(channel_id), channel=channel),
        )

    def test_keys(self, backend_world: World) -> None:
        inside = self.categorised(backend_world, 8701, CATEGORY)
        sibling = self.categorised(backend_world, 8702, CATEGORY)
        loose = self.categorised(backend_world, 8703, None)

        def key(ctx: Any) -> Any:
            return backend_world.run(BucketType.category.get_key_async(ctx))

        assert key(inside) == CATEGORY
        assert key(sibling) == CATEGORY
        assert key(loose) == 8703

    def test_cooldown_per_category_on_invocation(self, backend_world: World) -> None:
        command = make_command(
            cooldown=CooldownMapping.from_cooldown(1, 60, BucketType.category)
        )
        inside = self.categorised(backend_world, 8701, CATEGORY)
        sibling = self.categorised(backend_world, 8702, CATEGORY)
        loose = self.categorised(backend_world, 8703, None)

        invoke(backend_world, command, inside)
        invoke(backend_world, command, loose)
        with pytest.raises(commands.CommandOnCooldown):
            invoke(backend_world, command, sibling)


@pytest.mark.usefixtures("roles")
class TestAsyncTwins:
    def test_twins_follow_the_role_bucket(self, backend_world: World) -> None:
        command = make_command(
            cooldown=CooldownMapping.from_cooldown(1, 60, BucketType.role)
        )
        admin = context_for(backend_world, MEMBER_ID, [ADMIN])
        same_role = context_for(backend_world, 8501, [ADMIN])
        mod = context_for(backend_world, OTHER_ID, [MOD])

        assert not backend_world.run(command.check_on_cooldown(admin))
        assert backend_world.run(command.cooldown_retry_after(admin)) == 0.0
        invoke(backend_world, command, admin)

        async def after() -> tuple[bool, bool, bool, float]:
            return (
                await command.check_on_cooldown(admin),
                await command.check_on_cooldown(same_role),
                await command.check_on_cooldown(mod),
                await command.cooldown_retry_after(same_role),
            )

        on_admin, on_same, on_mod, retry = backend_world.run(after())
        assert on_admin
        assert on_same
        assert not on_mod
        assert 0 < retry <= 60

        backend_world.run(command.reset_cooldown_async(same_role))
        assert not backend_world.run(command.check_on_cooldown(admin))
        assert backend_world.run(command.cooldown_retry_after(admin)) == 0.0

    def test_twins_without_a_cooldown(self, backend_world: World) -> None:
        command = make_command()
        ctx = context_for(backend_world, MEMBER_ID, [ADMIN])
        assert backend_world.run(command.check_on_cooldown(ctx)) is False
        assert backend_world.run(command.cooldown_retry_after(ctx)) == 0.0
        backend_world.run(command.reset_cooldown_async(ctx))

    def test_twins_match_the_sync_methods_on_the_memory_backend(
        self, backend_world: World
    ) -> None:
        if not backend_world.state.cache.supports_sync:
            pytest.skip("the sync methods need an in-process cache")
        command = make_command(
            cooldown=CooldownMapping.from_cooldown(1, 60, BucketType.role)
        )
        ctx = context_for(backend_world, MEMBER_ID, [ADMIN])
        invoke(backend_world, command, ctx)
        assert command.is_on_cooldown(ctx) is backend_world.run(
            command.check_on_cooldown(ctx)
        )
        assert (
            abs(
                command.get_cooldown_retry_after(ctx)
                - backend_world.run(command.cooldown_retry_after(ctx))
            )
            < 1
        )
        command.reset_cooldown(ctx)
        assert not backend_world.run(command.check_on_cooldown(ctx))
