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

import datetime as dt
from typing import TYPE_CHECKING

import pytest

from discord import types as t
from discord.member import VoiceState
from discord.permissions import Permissions
from tests.models_async.a2_support import GUILD_ID, OWNER_ID, Scene

if TYPE_CHECKING:
    from tests.models.context import World

MINUTE = dt.timedelta(minutes=1)


@pytest.fixture
def scene(world: World) -> Scene:
    return Scene(world)


def populate(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(send_messages=True).value
    scene.add_role(10, position=1, permissions=Permissions(kick_members=True), colour=5)
    scene.add_role(11, position=3, permissions=Permissions(ban_members=True), colour=9)
    scene.add_role(12, position=2, colour=0)


@pytest.mark.parametrize(
    "roles", [[], [10], [10, 11, 12], [12, 99], [11, 12, 10]], ids=str
)
def test_sync_and_async_role_accessors_agree(scene: Scene, roles: list[int]) -> None:
    populate(scene)
    member = scene.add_member(1, roles=roles)
    assert member.roles == scene.run(member.get_roles())
    assert member.top_role == scene.run(member.get_top_role())
    assert member.guild_permissions == scene.run(member.get_guild_permissions())
    assert member.colours._to_dict() == scene.run(member.get_colours())._to_dict()
    assert member.colour == scene.run(member.get_colour())
    assert member.color == scene.run(member.get_color())


def test_sync_roles_are_sorted_with_everyone_first(scene: Scene) -> None:
    populate(scene)
    member = scene.add_member(1, roles=[11, 10, 12])
    assert [r.id for r in member.roles] == [GUILD_ID, 10, 12, 11]
    assert member.top_role.id == 11
    assert member.get_role(10) is not None
    assert member.get_role(99) is None


@pytest.mark.parametrize(
    ("user_id", "roles", "timed_out_for"),
    [
        (OWNER_ID, [], None),
        (OWNER_ID, [], MINUTE),
        (1, [10], None),
        (1, [10], MINUTE),
        (1, [10], -MINUTE),
        (1, [], MINUTE),
    ],
)
def test_sync_and_async_permissions_agree_with_timeout(
    scene: Scene, user_id: int, roles: list[int], timed_out_for: dt.timedelta | None
) -> None:
    populate(scene)
    member = scene.add_member(user_id, roles=roles, timed_out_for=timed_out_for)
    assert member.guild_permissions == scene.run(member.get_guild_permissions())


def test_sync_permissions_mask_a_timeout_except_for_admins(scene: Scene) -> None:
    populate(scene)
    scene.add_role(13, position=4, permissions=Permissions(administrator=True))
    timed_out = scene.add_member(1, roles=[10], timed_out_for=MINUTE)
    admin = scene.add_member(2, roles=[13], timed_out_for=MINUTE)
    assert timed_out.guild_permissions == Permissions.none()
    assert admin.guild_permissions == Permissions.all()


def test_sync_voice_matches_async(scene: Scene, world: World) -> None:
    member = scene.add_member(1)
    assert member.voice is None
    payload = world.payload(
        t.voice.GuildVoiceState, user_id="1", guild_id=str(GUILD_ID)
    )
    voice_state = VoiceState(data=payload, state=scene.state, channel=world.channel)  # type: ignore[arg-type]
    scene.run(scene.state._guild_bucket("voice_states", GUILD_ID).set(1, voice_state))
    assert member.voice is voice_state
    assert scene.run(member.get_voice_state()) is voice_state


def test_sync_role_members_match_async(scene: Scene) -> None:
    populate(scene)
    scene.add_member(3, roles=[10])
    scene.add_member(1)
    scene.add_member(2, roles=[11, 10])
    for role_id in (GUILD_ID, 10, 11, 12):
        role = scene.run(scene.state._guild_bucket("roles", GUILD_ID).get(role_id))
        assert role.members == scene.run(role.get_members())


def test_sync_role_is_assignable(scene: Scene, world: World) -> None:
    populate(scene)
    scene.add_role(14, position=8, permissions=Permissions(manage_roles=True))
    scene.add_role(15, position=9)
    scene.add_member(world.me.id, roles=[14])
    roles = scene.state._guild_bucket("roles", GUILD_ID)
    below = scene.run(roles.get(10))
    above = scene.run(roles.get(15))
    assert below.is_assignable()
    assert not above.is_assignable()
    assert not scene.everyone.is_assignable()
    below.managed = True
    assert not below.is_assignable()


def test_sync_role_is_not_assignable_without_manage_roles(
    scene: Scene, world: World
) -> None:
    populate(scene)
    scene.add_role(14, position=8)
    scene.add_member(world.me.id, roles=[14])
    assert not scene.run(
        scene.state._guild_bucket("roles", GUILD_ID).get(10)
    ).is_assignable()


def test_sync_user_dm_channel_and_mutual_guilds(scene: Scene, world: World) -> None:
    member = scene.add_member(55)
    user = member._user
    assert user.dm_channel is None
    payload = world.payload(
        t.channel.DMChannel, recipients=[world.payload(t.user.User, id="55")]
    )
    channel = scene.run(scene.state.add_dm_channel(payload))
    assert user.dm_channel is channel
    assert user.mutual_guilds == scene.run(user.get_mutual_guilds()) == [scene.guild]
    assert world.user.mutual_guilds == []
