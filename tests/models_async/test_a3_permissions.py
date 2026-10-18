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

from discord import ClientException, SyncCacheAccessError
from discord.permissions import Permissions
from tests.models_async.a2_support import GUILD_ID, OWNER_ID, Scene
from tests.models_async.a3_support import (
    MEMBER,
    ROLE,
    add_text,
    add_thread,
    add_voice,
    overwrite,
)
from tests.state.conftest import build_state

if TYPE_CHECKING:
    from discord import Member, Role
    from discord.abc import GuildChannel
    from tests.models.context import World

MINUTE = dt.timedelta(minutes=1)
SEND = Permissions(send_messages=True)
VIEW = Permissions(view_channel=True)
VIEW_SEND = Permissions(view_channel=True, send_messages=True)


@pytest.fixture
def scene(world: World) -> Scene:
    scene = Scene(world)
    scene.everyone._permissions = VIEW_SEND.value
    return scene


def both(scene: Scene, channel: GuildChannel, obj: Member | Role) -> Permissions:
    resolved = channel.permissions_for(obj)
    assert scene.run(channel.get_permissions_for(obj)) == resolved
    return resolved


def test_owner_has_every_permission_despite_overwrites(scene: Scene) -> None:
    owner = scene.add_member(OWNER_ID)
    channel = add_voice(
        scene, 1, [overwrite(GUILD_ID, ROLE, deny=Permissions(view_channel=True))]
    )
    assert both(scene, channel, owner) == Permissions.all()


def test_administrator_bypasses_every_overwrite(scene: Scene) -> None:
    scene.add_role(10, position=1, permissions=Permissions(administrator=True))
    member = scene.add_member(1, roles=[10])
    channel = add_voice(
        scene,
        1,
        [
            overwrite(GUILD_ID, ROLE, deny=Permissions.all_channel()),
            overwrite(1, MEMBER, deny=Permissions.all_channel()),
        ],
    )
    assert both(scene, channel, member) == Permissions.all()


def test_everyone_base_permissions_apply_without_overwrites(scene: Scene) -> None:
    member = scene.add_member(1)
    channel = add_text(scene, 1)
    assert both(scene, channel, member) == Permissions(
        view_channel=True, send_messages=True
    )


def test_everyone_overwrite_denies_then_role_overwrite_allows(scene: Scene) -> None:
    scene.add_role(10, position=1)
    channel = add_text(
        scene,
        1,
        [
            overwrite(GUILD_ID, ROLE, deny=SEND),
            overwrite(10, ROLE, allow=SEND),
        ],
    )
    without = scene.add_member(1)
    with_role = scene.add_member(2, roles=[10])
    assert not both(scene, channel, without).send_messages
    assert both(scene, channel, with_role).send_messages


def test_everyone_overwrite_is_applied_first_whatever_its_position(
    scene: Scene,
) -> None:
    scene.add_role(10, position=1)
    channel = add_text(
        scene,
        1,
        [
            overwrite(10, ROLE, allow=SEND),
            overwrite(GUILD_ID, ROLE, deny=SEND),
        ],
    )
    member = scene.add_member(1, roles=[10])
    assert both(scene, channel, member).send_messages


def test_role_allow_wins_over_another_role_deny(scene: Scene) -> None:
    scene.add_role(10, position=1)
    scene.add_role(11, position=2)
    channel = add_text(
        scene,
        1,
        [overwrite(10, ROLE, deny=SEND), overwrite(11, ROLE, allow=SEND)],
    )
    member = scene.add_member(1, roles=[10, 11])
    assert both(scene, channel, member).send_messages


def test_member_overwrite_beats_role_overwrites(scene: Scene) -> None:
    scene.add_role(10, position=1)
    channel = add_text(
        scene,
        1,
        [overwrite(10, ROLE, allow=SEND), overwrite(1, MEMBER, deny=SEND)],
    )
    denied = scene.add_member(1, roles=[10])
    allowed = scene.add_member(2, roles=[10])
    assert not both(scene, channel, denied).send_messages
    assert both(scene, channel, allowed).send_messages


def test_member_allow_overrides_role_deny(scene: Scene) -> None:
    scene.add_role(10, position=1)
    channel = add_text(
        scene,
        1,
        [overwrite(10, ROLE, deny=SEND), overwrite(1, MEMBER, allow=SEND)],
    )
    member = scene.add_member(1, roles=[10])
    assert both(scene, channel, member).send_messages


def test_overwrites_of_other_members_are_ignored(scene: Scene) -> None:
    channel = add_text(scene, 1, [overwrite(99, MEMBER, deny=SEND)])
    member = scene.add_member(1)
    assert both(scene, channel, member).send_messages


def test_without_view_channel_nothing_remains(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        manage_messages=True,
        kick_members=True,
    ).value
    channel = add_text(scene, 1, [overwrite(GUILD_ID, ROLE, deny=VIEW)])
    member = scene.add_member(1)
    resolved = both(scene, channel, member)
    assert resolved.value & Permissions.all_channel().value == 0
    assert resolved.kick_members


def test_without_send_messages_dependent_permissions_are_removed(
    scene: Scene,
) -> None:
    scene.everyone._permissions = Permissions(
        view_channel=True,
        send_messages=True,
        send_tts_messages=True,
        mention_everyone=True,
        embed_links=True,
        attach_files=True,
        add_reactions=True,
    ).value
    channel = add_text(scene, 1, [overwrite(GUILD_ID, ROLE, deny=SEND)])
    member = scene.add_member(1)
    resolved = both(scene, channel, member)
    assert not resolved.send_tts_messages
    assert not resolved.mention_everyone
    assert not resolved.embed_links
    assert not resolved.attach_files
    assert resolved.add_reactions


def test_text_channel_strips_voice_permissions(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(view_channel=True, connect=True).value
    member = scene.add_member(1)
    assert not both(scene, add_text(scene, 1), member).connect
    assert both(scene, add_voice(scene, 2), member).connect


def test_voice_channel_without_connect_strips_management(scene: Scene) -> None:
    scene.add_role(
        10,
        position=1,
        permissions=Permissions(manage_channels=True, manage_roles=True),
    )
    scene.everyone._permissions = VIEW.value
    member = scene.add_member(1, roles=[10])
    voice = add_voice(scene, 2)
    resolved = both(scene, voice, member)
    assert not resolved.manage_channels
    assert not resolved.manage_roles
    scene.everyone._permissions = Permissions(view_channel=True, connect=True).value
    assert both(scene, voice, member).manage_channels


def test_timed_out_member_only_keeps_viewing_and_history(scene: Scene) -> None:
    scene.everyone._permissions = Permissions(
        view_channel=True, send_messages=True, read_message_history=True
    ).value
    channel = add_text(scene, 1, [overwrite(1, MEMBER, allow=SEND)])
    member = scene.add_member(1, timed_out_for=MINUTE)
    assert both(scene, channel, member) == Permissions(
        view_channel=True, read_message_history=True
    )


def test_expired_timeout_changes_nothing(scene: Scene) -> None:
    channel = add_text(scene, 1)
    member = scene.add_member(1, timed_out_for=-MINUTE)
    assert both(scene, channel, member).send_messages


def test_timed_out_owner_and_administrator_are_exempt(scene: Scene) -> None:
    scene.add_role(10, position=1, permissions=Permissions(administrator=True))
    owner = scene.add_member(OWNER_ID, timed_out_for=MINUTE)
    admin = scene.add_member(1, roles=[10], timed_out_for=MINUTE)
    channel = add_voice(scene, 1)
    assert both(scene, channel, owner) == Permissions.all()
    assert both(scene, channel, admin) == Permissions.all()


def test_default_role_object_gets_everyone_overwrite(scene: Scene) -> None:
    channel = add_text(scene, 1, [overwrite(GUILD_ID, ROLE, deny=SEND)])
    resolved = both(scene, channel, scene.everyone)
    assert resolved.view_channel
    assert not resolved.send_messages


def test_role_object_combines_default_and_role_overwrites(scene: Scene) -> None:
    role = scene.add_role(10, position=1, permissions=Permissions(add_reactions=True))
    channel = add_text(
        scene,
        1,
        [overwrite(GUILD_ID, ROLE, deny=SEND), overwrite(10, ROLE, allow=SEND)],
    )
    resolved = both(scene, channel, role)
    assert resolved.send_messages
    assert resolved.add_reactions
    assert resolved.view_channel


def test_role_object_with_administrator_has_everything(scene: Scene) -> None:
    role = scene.add_role(10, position=1, permissions=Permissions(administrator=True))
    channel = add_voice(scene, 1, [overwrite(10, ROLE, deny=Permissions.all_channel())])
    assert both(scene, channel, role) == Permissions.all()


def test_thread_inherits_the_parent_permissions(scene: Scene) -> None:
    parent = add_text(scene, 1, [overwrite(GUILD_ID, ROLE, deny=SEND)])
    thread = add_thread(scene, 2, parent.id)
    member = scene.add_member(1)
    resolved = thread.permissions_for(member)
    assert resolved == parent.permissions_for(member)
    assert scene.run(thread.get_permissions_for(member)) == resolved
    assert not resolved.send_messages


def test_thread_without_cached_parent_raises(scene: Scene) -> None:
    thread = add_thread(scene, 2, 404)
    member = scene.add_member(1)
    with pytest.raises(ClientException):
        thread.permissions_for(member)
    with pytest.raises(ClientException):
        scene.run(thread.get_permissions_for(member))


def test_get_members_returns_members_that_can_view(scene: Scene) -> None:
    scene.add_role(10, position=1)
    channel = add_text(
        scene,
        1,
        [overwrite(GUILD_ID, ROLE, deny=VIEW), overwrite(10, ROLE, allow=VIEW)],
    )
    scene.add_member(1)
    seen = scene.add_member(2, roles=[10])
    members = scene.run(channel.get_members())
    assert [m.id for m in members] == [seen.id]
    assert [m.id for m in channel.members] == [seen.id]


@pytest.fixture
def redis_scene(world: World) -> Scene:
    state = build_state(world.state.loop, world.state.http, "redis")
    remote = Scene(type(world)(state))
    remote.everyone._permissions = VIEW_SEND.value
    remote.run(state._guild_bucket("roles", GUILD_ID).set(GUILD_ID, remote.everyone))
    return remote


def test_remote_backend_sync_permissions_raise_and_async_works(
    redis_scene: Scene,
) -> None:
    scene = redis_scene
    scene.add_role(10, position=1)
    channel = add_text(scene, 1, [overwrite(10, ROLE, deny=SEND)])
    member = scene.add_member(1, roles=[10])
    with pytest.raises(SyncCacheAccessError):
        channel.permissions_for(member)
    resolved = scene.run(channel.get_permissions_for(member))
    assert resolved.view_channel
    assert not resolved.send_messages
    role_resolved = scene.run(channel.get_permissions_for(scene.everyone))
    assert role_resolved == VIEW_SEND
