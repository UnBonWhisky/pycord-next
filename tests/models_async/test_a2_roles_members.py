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

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from discord import Colour, RoleColours, types as t
from discord.member import VoiceState
from tests.models_async.a2_support import GUILD_ID, Scene

if TYPE_CHECKING:
    from tests.models.context import World


@pytest.fixture
def scene(world: World) -> Scene:
    return Scene(world)


def test_member_get_roles_skips_roles_that_are_not_cached(scene: Scene) -> None:
    role = scene.add_role(10, position=1)
    member = scene.add_member(1, roles=[10, 99])
    assert scene.run(member.get_roles()) == [scene.everyone, role]


def test_member_get_roles_without_roles_is_only_everyone(scene: Scene) -> None:
    member = scene.add_member(1)
    assert scene.run(member.get_roles()) == [scene.everyone]


def test_member_get_colours_uses_the_highest_role_with_a_colour(scene: Scene) -> None:
    scene.add_role(10, position=1, colour=0x112233)
    high = scene.add_role(11, position=2, colour=0x445566)
    scene.add_role(12, position=3, colour=0)
    member = scene.add_member(1, roles=[10, 11, 12])
    assert scene.run(member.get_colours()) == high.colours
    assert scene.run(member.get_colour()).value == 0x445566
    assert scene.run(member.get_color()).value == 0x445566
    assert scene.run(member.get_colors()) == high.colours


def test_member_get_colours_defaults_when_no_role_has_a_colour(scene: Scene) -> None:
    scene.add_role(10, position=1, colour=0)
    member = scene.add_member(1, roles=[10])
    assert scene.run(member.get_colour()).value == 0


def test_member_get_voice_state(scene: Scene, world: World) -> None:
    member = scene.add_member(1)
    assert scene.run(member.get_voice_state()) is None
    payload = world.payload(
        t.voice.GuildVoiceState, user_id="1", guild_id=str(GUILD_ID)
    )
    voice_state = VoiceState(data=payload, state=scene.state, channel=world.channel)  # type: ignore[arg-type]
    scene.run(scene.state._guild_bucket("voice_states", GUILD_ID).set(1, voice_state))
    state = scene.run(member.get_voice_state())
    assert state is voice_state
    assert state.channel_id == world.channel.id


def test_role_get_members_of_the_default_role_is_every_member_in_cache_order(
    scene: Scene,
) -> None:
    scene.add_role(10, position=1)
    first = scene.add_member(3, roles=[10])
    second = scene.add_member(1)
    third = scene.add_member(2, roles=[10])
    assert scene.run(scene.everyone.get_members()) == [first, second, third]


def test_role_get_members_filters_on_the_role_in_cache_order(scene: Scene) -> None:
    role = scene.add_role(10, position=1)
    other = scene.add_role(11, position=2)
    first = scene.add_member(3, roles=[10])
    scene.add_member(1, roles=[11])
    third = scene.add_member(2, roles=[11, 10])
    assert scene.run(role.get_members()) == [first, third]
    assert len(scene.run(other.get_members())) == 2


def test_role_get_members_is_empty_for_a_role_nobody_has(scene: Scene) -> None:
    role = scene.add_role(10, position=1)
    scene.add_member(1)
    assert scene.run(role.get_members()) == []


def test_role_edit_moves_using_the_cached_roles(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene.add_role(10, position=1)
    scene.add_role(11, position=2)
    moving = scene.add_role(12, position=3)
    move = AsyncMock()
    monkeypatch.setattr(scene.state.http, "move_role_position", move)
    scene.run(moving._move(1, None))
    move.assert_awaited_once()
    args: Any = move.await_args
    assert args.args[0] == GUILD_ID
    assert args.args[1] == [
        {"id": 12, "position": 1},
        {"id": 10, "position": 2},
        {"id": 11, "position": 3},
    ]


def test_role_edit_drops_enhanced_colours_when_the_guild_lacks_the_feature(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = scene.add_role(10, position=1)
    edit = AsyncMock(return_value=scene.world.payload(t.role.Role, id="10"))
    monkeypatch.setattr(scene.state.http, "edit_role", edit)
    scene.guild.features = []
    colours = RoleColours(primary=Colour(1), secondary=Colour(2), tertiary=Colour(3))
    scene.run(role.edit(colours=colours))
    sent = edit.await_args.kwargs["colors"]
    assert sent["secondary_color"] is None
    assert sent["tertiary_color"] is None


def test_user_get_dm_channel_and_mutual_guilds(scene: Scene, world: World) -> None:
    member = scene.add_member(55)
    user = member._user
    assert scene.run(user.get_dm_channel()) is None
    payload = world.payload(
        t.channel.DMChannel,
        recipients=[world.payload(t.user.User, id="55")],
    )
    channel = scene.run(scene.state.add_dm_channel(payload))
    assert scene.run(user.get_dm_channel()) is channel
    assert scene.run(user.get_mutual_guilds()) == [scene.guild]
    stranger = world.user
    assert scene.run(stranger.get_mutual_guilds()) == []
