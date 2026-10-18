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

from discord.permissions import Permissions
from tests.models_async.a2_support import GUILD_ID, OWNER_ID, Scene

if TYPE_CHECKING:
    from tests.models.context import World

MINUTE = dt.timedelta(minutes=1)
TIMEOUT_KEEPS = Permissions(view_channel=True, read_message_history=True)


@pytest.fixture
def scene(world: World) -> Scene:
    return Scene(world)


def test_owner_has_every_permission_without_roles(scene: Scene) -> None:
    owner = scene.add_member(OWNER_ID)
    assert scene.run(owner.get_guild_permissions()) == Permissions.all()


def test_owner_is_exempt_from_timeout(scene: Scene) -> None:
    owner = scene.add_member(OWNER_ID, timed_out_for=MINUTE)
    assert scene.run(owner.get_guild_permissions()) == Permissions.all()


def test_everyone_permissions_apply_to_a_member_without_roles(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(send_messages=True).value
    member = scene.add_member(1)
    assert scene.run(member.get_guild_permissions()) == Permissions(send_messages=True)


def test_role_permissions_are_or_ed_with_everyone(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(send_messages=True).value
    scene.add_role(10, position=1, permissions=Permissions(kick_members=True))
    scene.add_role(11, position=2, permissions=Permissions(manage_roles=True))
    member = scene.add_member(1, roles=[10, 11])
    assert scene.run(member.get_guild_permissions()) == Permissions(
        send_messages=True, kick_members=True, manage_roles=True
    )


def test_administrator_role_grants_every_permission(scene: Scene) -> None:
    scene.add_role(10, position=1, permissions=Permissions(administrator=True))
    member = scene.add_member(1, roles=[10])
    assert scene.run(member.get_guild_permissions()) == Permissions.all()


def test_administrator_is_exempt_from_timeout(scene: Scene) -> None:
    scene.add_role(10, position=1, permissions=Permissions(administrator=True))
    member = scene.add_member(1, roles=[10], timed_out_for=MINUTE)
    assert scene.run(member.get_guild_permissions()) == Permissions.all()


def test_timed_out_member_keeps_only_view_channel_and_read_message_history(
    scene: Scene,
) -> None:
    scene.everyone._permissions = Permissions(
        view_channel=True, send_messages=True, read_message_history=True
    ).value
    scene.add_role(10, position=1, permissions=Permissions(kick_members=True))
    member = scene.add_member(1, roles=[10], timed_out_for=MINUTE)
    assert member.timed_out
    assert scene.run(member.get_guild_permissions()) == TIMEOUT_KEEPS


def test_timed_out_member_does_not_gain_permissions_they_lack(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(send_messages=True).value
    member = scene.add_member(1, timed_out_for=MINUTE)
    assert scene.run(member.get_guild_permissions()) == Permissions.none()


def test_expired_timeout_does_not_mask(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(send_messages=True).value
    member = scene.add_member(1, timed_out_for=-MINUTE)
    assert not member.timed_out
    assert scene.run(member.get_guild_permissions()) == Permissions(send_messages=True)


def test_uncached_guild_means_nobody_is_the_owner(scene: Scene) -> None:
    owner = scene.add_member(OWNER_ID)
    scene.run(scene.state._remove_guild(scene.guild))
    assert scene.run(owner.get_guild_permissions()) == Permissions.none()


def test_permissions_ignore_role_position(scene: Scene) -> None:
    scene.add_role(10, position=5, permissions=Permissions(kick_members=True))
    scene.add_role(11, position=1, permissions=Permissions(ban_members=True))
    member = scene.add_member(1, roles=[10, 11])
    assert scene.run(member.get_guild_permissions()) == Permissions(
        kick_members=True, ban_members=True
    )


def test_role_ordering_is_position_then_lower_id_first(scene: Scene) -> None:
    low = scene.add_role(10, position=1)
    tie_high_id = scene.add_role(30, position=2)
    tie_low_id = scene.add_role(20, position=2)
    top = scene.add_role(15, position=3)
    assert scene.everyone < low < tie_high_id < tie_low_id < top
    member = scene.add_member(1, roles=[top.id, low.id, tie_low_id.id, tie_high_id.id])
    assert scene.run(member.get_roles()) == [
        scene.everyone,
        low,
        tie_high_id,
        tie_low_id,
        top,
    ]


def test_top_role_is_the_highest_of_the_member(scene: Scene) -> None:
    scene.add_role(10, position=1)
    high = scene.add_role(11, position=4)
    scene.add_role(12, position=9)
    member = scene.add_member(1, roles=[10, 11])
    assert scene.run(member.get_top_role()) == high


def test_top_role_without_roles_is_everyone(scene: Scene) -> None:
    scene.add_role(10, position=1)
    member = scene.add_member(1)
    assert scene.run(member.get_top_role()) == scene.everyone


def test_top_role_without_cached_roles_is_none(scene: Scene) -> None:
    member = scene.add_member(1)
    scene.run(scene.state._guild_bucket("roles", GUILD_ID).clear())
    assert scene.run(member.get_top_role()) is None
