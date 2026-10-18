"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import discord
from discord import SyncCacheAccessError
from discord.channel import PartialMessageable
from discord.commands.cooldowns import (
    BucketType,
    Cooldown,
    CooldownMapping,
    MaxConcurrency,
)
from discord.ext import commands

if TYPE_CHECKING:
    from tests.ext.support import Server


@pytest.fixture
def people(server: Server) -> SimpleNamespace:
    mods = server.add_role(None, "Mods", position=2)
    admins = server.add_role(None, "Admins", position=3)
    alice = server.add_member(
        1300000000000000001, name="alice", roles=[mods.id, admins.id]
    )
    bob = server.add_member(1300000000000000002, name="bob", roles=[mods.id])
    carol = server.add_member(1300000000000000003, name="carol")
    section = server.add_category("section")
    other = server.add_category("other")
    inside = server.add_text("inside", parent_id=section.id)
    sibling = server.add_text("sibling", parent_id=section.id)
    elsewhere = server.add_text("elsewhere", parent_id=other.id)
    loose = server.add_text("loose")
    return SimpleNamespace(
        mods=mods,
        admins=admins,
        alice=alice,
        bob=bob,
        carol=carol,
        section=section,
        other=other,
        inside=inside,
        sibling=sibling,
        elsewhere=elsewhere,
        loose=loose,
    )


def key(server: Server, bucket: BucketType, message: discord.Message) -> object:
    return server.run(bucket.get_key_async(message))


class TestAsyncKeys:
    def test_role_uses_the_top_role(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        guild = server.guild
        assert (
            key(server, BucketType.role, server.message("x", author=people.alice))
            == people.admins.id
        )
        assert (
            key(server, BucketType.role, server.message("x", author=people.bob))
            == people.mods.id
        )
        assert (
            key(server, BucketType.role, server.message("x", author=people.carol))
            == guild.id
        )

    def test_role_in_a_direct_message_is_the_channel(self, server: Server) -> None:
        message = server.message("x", in_guild=False)
        assert key(server, BucketType.role, message) == message.channel.id

    def test_category_uses_the_category_id(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        inside = server.message("x", channel=people.inside)
        sibling = server.message("x", channel=people.sibling)
        elsewhere = server.message("x", channel=people.elsewhere)
        loose = server.message("x", channel=people.loose)
        assert key(server, BucketType.category, inside) == people.section.id
        assert key(server, BucketType.category, sibling) == people.section.id
        assert key(server, BucketType.category, elsewhere) == people.other.id
        assert key(server, BucketType.category, loose) == people.loose.id

    def test_category_resolves_a_partial_channel(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        partial = PartialMessageable(state=server.state, id=people.inside.id)
        message = server.message("x", channel=partial)
        assert key(server, BucketType.category, message) == people.section.id

    def test_category_of_an_uncached_channel_is_the_channel(
        self, server: Server
    ) -> None:
        partial = PartialMessageable(state=server.state, id=999)
        message = server.message("x", channel=partial)
        assert key(server, BucketType.category, message) == 999

    @pytest.mark.parametrize(
        "bucket",
        [
            BucketType.default,
            BucketType.user,
            BucketType.guild,
            BucketType.channel,
            BucketType.member,
        ],
    )
    def test_other_buckets_match_the_sync_key(
        self, server: Server, people: SimpleNamespace, bucket: BucketType
    ) -> None:
        message = server.message("x", author=people.alice, channel=people.inside)
        assert key(server, bucket, message) == bucket.get_key(message)

    def test_the_sync_key_stays_for_the_in_process_cache(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        message = server.message("x", author=people.alice, channel=people.inside)
        if server.state.cache.supports_sync:
            assert BucketType.role.get_key(message) == people.admins.id
            assert BucketType.category.get_key(message) == people.section.id
        else:
            with pytest.raises(SyncCacheAccessError):
                BucketType.role.get_key(message)


class TestMappings:
    def test_buckets_are_shared_per_role(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        mapping = CooldownMapping.from_cooldown(1, 60, BucketType.role)
        alice = server.message("x", author=people.alice)
        bob = server.message("x", author=people.bob)
        carol = server.message("x", author=people.carol)

        async def run() -> list[float | None]:
            return [
                await mapping.update_rate_limit_async(alice),
                await mapping.update_rate_limit_async(bob),
                await mapping.update_rate_limit_async(carol),
                await mapping.update_rate_limit_async(alice),
            ]

        results = server.run(run())
        assert results[:3] == [None, None, None]
        assert results[3] is not None
        assert set(mapping._cache) == {
            people.admins.id,
            people.mods.id,
            server.guild.id,
        }

    def test_update_rate_limit_async(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        mapping = CooldownMapping.from_cooldown(1, 60, BucketType.category)
        inside = server.message("x", channel=people.inside)
        sibling = server.message("x", channel=people.sibling)
        elsewhere = server.message("x", channel=people.elsewhere)

        async def run() -> list[float | None]:
            return [
                await mapping.update_rate_limit_async(inside, 100.0),
                await mapping.update_rate_limit_async(sibling, 101.0),
                await mapping.update_rate_limit_async(elsewhere, 101.0),
            ]

        limited = server.run(run())
        assert limited[0] is None
        assert limited[1] is not None
        assert limited[2] is None

    def test_default_type_returns_the_shared_cooldown(self, server: Server) -> None:
        cooldown = Cooldown(1, 60)
        mapping = CooldownMapping(cooldown, BucketType.default)
        assert server.run(mapping.get_bucket_async(server.message("x"))) is cooldown

    def test_a_callable_type_may_be_a_coroutine_function(self, server: Server) -> None:
        async def by_author(message: discord.Message) -> int:
            return message.author.id

        mapping = CooldownMapping(Cooldown(1, 60), by_author)  # type: ignore[arg-type]

        async def run() -> list[float | None]:
            message = server.message("x")
            return [
                await mapping.update_rate_limit_async(message, 100.0),
                await mapping.update_rate_limit_async(message, 101.0),
            ]

        first, second = server.run(run())
        assert first is None
        assert second is not None

    def test_a_callable_type_stays_synchronous_for_update_rate_limit(
        self, server: Server
    ) -> None:
        mapping = CooldownMapping(Cooldown(1, 60), lambda message: message.author.id)
        message = server.message("x")
        assert mapping.update_rate_limit(message, 100.0) is None
        assert mapping.update_rate_limit(message, 101.0) is not None
        assert server.run(mapping.update_rate_limit_async(message, 102.0)) is not None


class TestMaxConcurrency:
    def test_acquire_and_release_per_role(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        limit = MaxConcurrency(1, per=BucketType.role, wait=False)
        alice = server.message("x", author=people.alice)
        bob = server.message("x", author=people.bob)

        async def run() -> None:
            await limit.acquire(alice)
            await limit.acquire(bob)
            with pytest.raises(commands.MaxConcurrencyReached):
                await limit.acquire(alice)
            await limit.release(alice)
            await limit.acquire(alice)
            await limit.release(alice)
            await limit.release(bob)

        server.run(run())
        assert not limit._mapping


class TestInvocation:
    def invoke(
        self, server: Server, command: commands.Command, message: object
    ) -> None:
        async def run() -> None:
            ctx = await server.bot.get_context(message)  # type: ignore[arg-type]
            await command.invoke(ctx)

        server.run(run())

    @pytest.mark.parametrize("bucket", [BucketType.role, BucketType.category])
    def test_cooldown_buckets_work_on_every_backend(
        self, server: Server, people: SimpleNamespace, bucket: BucketType
    ) -> None:
        calls: list[int] = []

        @commands.command()
        @commands.cooldown(1, 60, bucket)
        async def ping(ctx: commands.Context) -> None:
            calls.append(ctx.author.id)

        server.bot.add_command(ping)
        first = server.message("!ping", author=people.alice, channel=people.inside)
        same = server.message("!ping", author=people.alice, channel=people.sibling)
        other = server.message("!ping", author=people.carol, channel=people.elsewhere)

        self.invoke(server, ping, first)
        self.invoke(server, ping, other)
        with pytest.raises(commands.CommandOnCooldown):
            self.invoke(server, ping, same)
        assert calls == [people.alice.id, people.carol.id]

    @pytest.mark.parametrize("bucket", [BucketType.role, BucketType.category])
    def test_max_concurrency_buckets_work_on_every_backend(
        self, server: Server, people: SimpleNamespace, bucket: BucketType
    ) -> None:
        @commands.command()
        @commands.max_concurrency(1, bucket)
        async def work(_ctx: commands.Context) -> None:
            raise RuntimeError("stop")

        server.bot.add_command(work)
        message = server.message("!work", author=people.alice, channel=people.inside)

        for _ in range(2):
            with pytest.raises(commands.CommandInvokeError):
                self.invoke(server, work, message)

    def test_a_cooldown_failure_through_the_bot_reaches_the_error_event(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        errors: list[Exception] = []

        @server.bot.event
        async def on_command_error(_ctx: commands.Context, error: Exception) -> None:
            errors.append(error)

        @commands.command()
        @commands.cooldown(1, 60, BucketType.role)
        async def ping(_ctx: commands.Context) -> None: ...

        server.bot.add_command(ping)
        message = server.message("!ping", author=people.bob)

        async def run() -> None:
            for _ in range(2):
                await server.bot.invoke(await server.bot.get_context(message))

        server.run(run())
        assert len(errors) == 1
        assert isinstance(errors[0], commands.CommandOnCooldown)


class TestAsyncTwins:
    @pytest.mark.parametrize("bucket", [BucketType.role, BucketType.category])
    def test_twins_work_on_every_backend(
        self, server: Server, people: SimpleNamespace, bucket: BucketType
    ) -> None:
        @commands.command()
        @commands.cooldown(1, 60, bucket)
        async def ping(_ctx: commands.Context) -> None: ...

        server.bot.add_command(ping)
        first = server.message("!ping", author=people.alice, channel=people.inside)
        same = server.message("!ping", author=people.alice, channel=people.sibling)
        other = server.message("!ping", author=people.carol, channel=people.elsewhere)

        async def run() -> None:
            ctx = await server.bot.get_context(first)
            same_ctx = await server.bot.get_context(same)
            other_ctx = await server.bot.get_context(other)
            assert not await ping.check_on_cooldown(ctx)
            assert await ping.cooldown_retry_after(ctx) == 0.0
            await ping.prepare(ctx)
            assert await ping.check_on_cooldown(same_ctx)
            assert not await ping.check_on_cooldown(other_ctx)
            assert 0 < await ping.cooldown_retry_after(same_ctx) <= 60
            await ping.reset_cooldown_async(same_ctx)
            assert not await ping.check_on_cooldown(ctx)
            assert await ping.cooldown_retry_after(ctx) == 0.0

        server.run(run())

    def test_twins_match_the_sync_methods_on_the_memory_backend(
        self, server: Server, people: SimpleNamespace
    ) -> None:
        if not server.state.cache.supports_sync:
            pytest.skip("the sync methods need an in-process cache")

        @commands.command()
        @commands.cooldown(1, 60, BucketType.role)
        async def ping(_ctx: commands.Context) -> None: ...

        server.bot.add_command(ping)
        message = server.message("!ping", author=people.alice)

        async def run() -> None:
            ctx = await server.bot.get_context(message)
            await ping.prepare(ctx)
            assert ping.is_on_cooldown(ctx) is await ping.check_on_cooldown(ctx)
            assert (
                abs(
                    ping.get_cooldown_retry_after(ctx)
                    - await ping.cooldown_retry_after(ctx)
                )
                < 1
            )
            ping.reset_cooldown(ctx)
            assert not await ping.check_on_cooldown(ctx)

        server.run(run())

    def test_twins_without_a_cooldown(self, server: Server) -> None:
        @commands.command()
        async def ping(_ctx: commands.Context) -> None: ...

        server.bot.add_command(ping)

        async def run() -> None:
            ctx = await server.bot.get_context(server.message("!ping"))
            assert await ping.check_on_cooldown(ctx) is False
            assert await ping.cooldown_retry_after(ctx) == 0.0
            await ping.reset_cooldown_async(ctx)

        server.run(run())
