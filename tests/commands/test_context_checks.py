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


"""The checks and the shared context members, run on both contexts and both cache backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.channel import PartialMessageable
from discord.enums import ChannelType
from discord.ext import commands
from discord.ext.commands.context import Context
from discord.member import Member
from discord.role import Role
from tests.commands.interaction_support import (
    MEMBER_ID,
    add_member,
    backend_world,
    interaction_payload,
    is_memory,
    make_bot,
    make_context,
    member_payload,
)

if TYPE_CHECKING:
    from discord.commands.context import ApplicationContext
    from tests.models.context import World

__all__ = ("backend_world",)

ADMIN = 10
MOD = 11
BOT_ROLE = 20
DM_CHANNEL = 8600
VISIBLE = discord.Permissions(view_channel=True, send_messages=True)


def set_role(world: World, role_id: int, name: str, permissions: int = 0) -> Role:
    payload = world.payload(
        t.role.Role,
        id=str(role_id),
        name=name,
        position=role_id,
        permissions=str(permissions),
    )
    payload.pop("tags", None)
    role = Role(guild=world.guild, state=world.state, data=payload)
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def setup(world: World, everyone: int = 0) -> None:
    set_role(world, world.guild.id, "@everyone", everyone)
    set_role(world, ADMIN, "Admin")
    set_role(world, MOD, "Mod")
    set_role(world, BOT_ROLE, "Bot")
    world.channel._overwrites = []
    world.run(world.guild._add_channel(world.channel))
    for user_id, roles in ((MEMBER_ID, [ADMIN, MOD]), (world.me.id, [BOT_ROLE])):
        payload = member_payload(world, user_id, roles=[str(r) for r in roles])
        member = Member(data=payload, guild=world.guild, state=world.state)
        world.run(world.guild._add_member(member))


def app_context(world: World, **fields: Any) -> ApplicationContext:
    member = member_payload(world, MEMBER_ID, roles=[str(ADMIN), str(MOD)])
    return make_context(world, interaction_payload(world, member=member, **fields))


def ext_context(world: World, *, guild: bool = True) -> Context:
    payload = world.payload(
        t.message.Message,
        id="7800",
        type=0,
        mentions=[],
        mention_roles=[],
        reactions=[],
        channel_id=str(world.channel.id if guild else DM_CHANNEL),
        author={**world.payload(t.user.User), "id": str(MEMBER_ID)},
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "poll",
        "thread",
        "call",
        "interaction",
        "interaction_metadata",
        "member",
        "guild_id",
    ):
        payload.pop(key, None)
    if guild:
        payload["guild_id"] = str(world.guild.id)
    message = world.run(
        world.state._create_message(
            channel=world.channel
            if guild
            else PartialMessageable(
                state=world.state, id=DM_CHANNEL, type=ChannelType.private
            ),
            data=payload,
        )
    )
    return Context(message=message, bot=make_bot(world.state), view=None)  # type: ignore[arg-type]


def app_dm(world: World) -> ApplicationContext:
    return make_context(
        world, interaction_payload(world, guild=False, channel_id=str(DM_CHANNEL))
    )


def ext_dm(world: World) -> Context:
    return ext_context(world, guild=False)


GUILD_FACTORIES = [app_context, ext_context]
DM_FACTORIES = [app_dm, ext_dm]


def run_check(world: World, decorator: Any, ctx: Any) -> Any:
    async def callback(ctx: Any) -> None: ...

    (predicate,) = decorator(callback).__commands_checks__
    return world.run(discord.utils.maybe_coroutine(predicate, ctx))


@pytest.mark.parametrize("factory", GUILD_FACTORIES)
class TestPermissions:
    def test_channel_permissions(self, backend_world: World, factory: Any) -> None:
        setup(
            backend_world,
            VISIBLE.value | discord.Permissions(manage_messages=True).value,
        )
        ctx = factory(backend_world)
        decorator = commands.has_permissions(manage_messages=True)
        assert run_check(backend_world, decorator, ctx) is True
        denied = commands.has_permissions(manage_guild=True)
        with pytest.raises(commands.MissingPermissions) as info:
            run_check(backend_world, denied, ctx)
        assert info.value.missing_permissions == ["manage_guild"]

    def test_denied_channel_permissions(
        self, backend_world: World, factory: Any
    ) -> None:
        setup(backend_world)
        with pytest.raises(commands.MissingPermissions) as info:
            run_check(
                backend_world,
                commands.has_permissions(manage_messages=True),
                factory(backend_world),
            )
        assert info.value.missing_permissions == ["manage_messages"]

    def test_bot_channel_permissions(self, backend_world: World, factory: Any) -> None:
        granted = VISIBLE.value | discord.Permissions(manage_messages=True).value
        setup(backend_world, VISIBLE.value if factory is app_context else granted)
        ctx = (
            factory(backend_world, app_permissions=str(granted))
            if factory is app_context
            else factory(backend_world)
        )
        assert (
            run_check(
                backend_world, commands.bot_has_permissions(manage_messages=True), ctx
            )
            is True
        )
        with pytest.raises(commands.BotMissingPermissions):
            run_check(
                backend_world, commands.bot_has_permissions(manage_guild=True), ctx
            )

    def test_guild_permissions(self, backend_world: World, factory: Any) -> None:
        setup(
            backend_world, VISIBLE.value | discord.Permissions(kick_members=True).value
        )
        ctx = factory(backend_world)
        assert (
            run_check(
                backend_world, commands.has_guild_permissions(kick_members=True), ctx
            )
            is True
        )
        assert (
            run_check(
                backend_world,
                commands.bot_has_guild_permissions(kick_members=True),
                ctx,
            )
            is True
        )
        with pytest.raises(commands.MissingPermissions):
            run_check(
                backend_world, commands.has_guild_permissions(ban_members=True), ctx
            )
        with pytest.raises(commands.BotMissingPermissions):
            run_check(
                backend_world, commands.bot_has_guild_permissions(ban_members=True), ctx
            )


def test_bot_permissions_prefer_app_permissions(backend_world: World) -> None:
    setup(backend_world)
    ctx = app_context(
        backend_world,
        app_permissions=str(
            VISIBLE.value | discord.Permissions(manage_messages=True).value
        ),
    )
    decorator = commands.bot_has_permissions(manage_messages=True)
    assert run_check(backend_world, decorator, ctx) is True
    denied = app_context(backend_world, app_permissions="0")
    with pytest.raises(commands.BotMissingPermissions):
        run_check(backend_world, decorator, denied)


@pytest.mark.parametrize(
    ("factory", "expected"),
    [(app_context, discord.CheckFailure), (ext_context, commands.CheckFailure)],
)
def test_an_uncached_channel_raises_the_error_of_the_context(
    backend_world: World, factory: Any, expected: type[Exception]
) -> None:
    setup(backend_world, VISIBLE.value)
    ctx = factory(backend_world)

    async def uncached() -> None:
        return None

    ctx.get_channel = uncached
    with pytest.raises(expected) as info:
        run_check(backend_world, commands.has_permissions(manage_messages=True), ctx)
    assert type(info.value) is expected
    assert isinstance(info.value, commands.CommandError) is (factory is ext_context)


@pytest.mark.parametrize("factory", DM_FACTORIES)
class TestDirectMessages:
    def test_channel_permissions_pass(self, backend_world: World, factory: Any) -> None:
        setup(backend_world)
        ctx = factory(backend_world)
        assert (
            run_check(backend_world, commands.has_permissions(administrator=True), ctx)
            is True
        )

    def test_guild_checks_raise(self, backend_world: World, factory: Any) -> None:
        setup(backend_world)
        ctx = factory(backend_world)
        for decorator in (
            commands.has_guild_permissions(kick_members=True),
            commands.bot_has_guild_permissions(kick_members=True),
            commands.has_role("Admin"),
            commands.has_any_role("Admin"),
            commands.bot_has_role(1),
            commands.bot_has_any_role(1),
        ):
            with pytest.raises(commands.NoPrivateMessage):
                run_check(backend_world, decorator, ctx)


@pytest.mark.parametrize("factory", GUILD_FACTORIES)
def test_role_checks(backend_world: World, factory: Any) -> None:
    setup(backend_world)
    ctx = factory(backend_world)

    def passes(decorator: Any) -> bool:
        return run_check(backend_world, decorator, ctx)

    assert passes(commands.has_role("Admin")) is True
    assert passes(commands.has_role(MOD)) is True
    assert passes(commands.has_any_role("Nope", MOD)) is True
    assert passes(commands.bot_has_role("Bot")) is True
    assert passes(commands.bot_has_any_role(1, BOT_ROLE)) is True
    with pytest.raises(commands.MissingRole):
        passes(commands.has_role("Nope"))
    with pytest.raises(commands.MissingAnyRole):
        passes(commands.has_any_role("Nope", 99))
    with pytest.raises(commands.BotMissingRole):
        passes(commands.bot_has_role("Admin"))
    with pytest.raises(commands.BotMissingAnyRole):
        passes(commands.bot_has_any_role(1, 2))


@pytest.mark.parametrize("factory", GUILD_FACTORIES)
class TestSharedMembers:
    def test_me_is_the_guild_member(self, backend_world: World, factory: Any) -> None:
        setup(backend_world)
        ctx = factory(backend_world)
        resolved = backend_world.run(ctx.get_me())
        assert isinstance(resolved, Member)
        assert resolved.id == backend_world.me.id
        if is_memory(backend_world):
            assert ctx.me is resolved
        else:
            assert ctx.me is backend_world.me

    def test_me_falls_back_to_the_bot_user(
        self, backend_world: World, factory: Any
    ) -> None:
        add_member(backend_world)
        ctx = factory(backend_world)
        assert ctx.me is backend_world.me
        assert backend_world.run(ctx.get_me()) is backend_world.me

    def test_voice_client(self, backend_world: World, factory: Any) -> None:
        ctx = factory(backend_world)
        assert ctx.voice_client is None
        backend_world.state._add_voice_client(backend_world.guild.id, "vc")  # type: ignore[arg-type]
        assert ctx.voice_client == "vc"

    def test_guild_and_channel_getters(
        self, backend_world: World, factory: Any
    ) -> None:
        ctx = factory(backend_world)
        guild = backend_world.run(ctx.get_guild())
        assert guild is not None
        assert guild.id == backend_world.guild.id
        channel = backend_world.run(ctx.get_channel())
        assert channel is not None
        assert channel.id == backend_world.channel.id


@pytest.mark.parametrize("factory", DM_FACTORIES)
def test_dm_members(backend_world: World, factory: Any) -> None:
    ctx = factory(backend_world)
    assert ctx.guild is None
    assert ctx.voice_client is None
    assert ctx.me is backend_world.me
    assert backend_world.run(ctx.get_me()) is backend_world.me
    assert backend_world.run(ctx.get_guild()) is None
