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


"""Builders of interactions and contexts shared by the B1 tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from discord import types as t
from discord.commands.context import ApplicationContext
from discord.http import HTTPClient
from discord.interactions import Interaction
from discord.member import Member
from discord.role import Role
from discord.threads import Thread
from tests.models.context import World
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.state import ConnectionState

MEMBER_ID = 8100
OTHER_ID = 8300
ROLE_ID = 8200
THREAD_ID = 8400
INTERACTION_ID = 9100


@pytest.fixture(params=["memory", "redis"])
def backend_world(
    request: pytest.FixtureRequest, loop: asyncio.AbstractEventLoop
) -> World:
    return World(build_state(loop, HTTPClient(loop=loop), request.param))


def is_memory(world: World) -> bool:
    return world.state.cache.supports_sync


def member_payload(world: World, user_id: int = MEMBER_ID, **fields: Any) -> Any:
    payload = world.payload(
        t.member.MemberWithUser,
        **{
            "roles": [],
            "user": {
                **world.payload(t.user.User),
                "id": str(user_id),
                "username": "Neo",
            },
            **fields,
        },
    )
    payload.pop("communication_disabled_until", None)
    return payload


def add_member(world: World, user_id: int = MEMBER_ID) -> Member:
    member = Member(
        data=member_payload(world, user_id), guild=world.guild, state=world.state
    )
    world.run(world.guild._add_member(member))
    return member


def add_bot_member(world: World) -> Member:
    return add_member(world, world.me.id)


def add_role(world: World, role_id: int = ROLE_ID) -> Role:
    payload = world.payload(t.role.Role, id=str(role_id), position=1)
    payload.pop("tags", None)
    role = Role(guild=world.guild, state=world.state, data=payload)
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


def thread_payload(world: World, thread_id: int = THREAD_ID, **fields: Any) -> Any:
    payload = world.payload(
        t.threads.Thread,
        id=str(thread_id),
        guild_id=str(world.guild.id),
        parent_id=str(world.channel.id),
        owner_id=str(MEMBER_ID),
        **fields,
    )
    payload.pop("member", None)
    return payload


def add_thread(world: World, thread_id: int = THREAD_ID) -> Thread:
    thread = Thread(
        guild=world.guild, state=world.state, data=thread_payload(world, thread_id)
    )
    world.run(world.state._add_thread(world.guild.id, thread))
    return thread


def interaction_payload(
    world: World,
    *,
    guild: bool = True,
    member_id: int = MEMBER_ID,
    data: Any = None,
    **fields: Any,
) -> Any:
    payload: dict[str, Any] = {
        "id": str(INTERACTION_ID),
        "application_id": "1234",
        "type": 2,
        "token": "token",
        "version": 1,
        "channel_id": str(world.channel.id),
        "data": data if data is not None else {"id": "1", "name": "cmd", "type": 1},
    }
    if guild:
        channel = world.payload(
            t.channel.TextChannel,
            id=str(world.channel.id),
            guild_id=str(world.guild.id),
        )
        payload.update(
            guild_id=str(world.guild.id),
            member=member_payload(world, member_id),
            channel=channel,
        )
    else:
        payload.update(user={**world.payload(t.user.User), "id": str(member_id)})
    payload.update(fields)
    return payload


def make_bot(state: ConnectionState) -> Any:
    return SimpleNamespace(
        _connection=state,
        user=state.user,
        _bot=None,
    )


def make_interaction(
    world: World, payload: Any | None = None, **kwargs: Any
) -> Interaction:
    payload = payload or interaction_payload(world, **kwargs)
    interaction = Interaction(data=payload, state=world.state)
    world.run(world.state._populate_interaction(interaction, payload))
    return interaction


def make_context(
    world: World, payload: Any | None = None, **kwargs: Any
) -> ApplicationContext:
    interaction = make_interaction(world, payload, **kwargs)
    return ApplicationContext(make_bot(world.state), interaction)
