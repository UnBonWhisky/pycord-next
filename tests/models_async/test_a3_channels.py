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

from typing import TYPE_CHECKING

import pytest

from discord import ClientException, Embed, SyncCacheAccessError, types as t
from discord.channel import PartialGuildChannel
from discord.partial_emoji import PartialEmoji
from discord.permissions import Permissions
from discord.stage_instance import StageInstance
from discord.threads import ThreadMember
from tests.models_async.a2_support import GUILD_ID, Scene
from tests.models_async.a3_support import (
    MEMBER,
    ROLE,
    add_category,
    add_forum,
    add_stage,
    add_text,
    add_thread,
    add_voice,
    add_voice_state,
    overwrite,
)
from tests.state.conftest import build_state

if TYPE_CHECKING:
    from tests.models.context import World

SEND = Permissions(send_messages=True)
VIEW_SEND = Permissions(view_channel=True, send_messages=True)


@pytest.fixture
def scene(world: World) -> Scene:
    scene = Scene(world)
    scene.everyone._permissions = VIEW_SEND.value
    return scene


@pytest.fixture
def redis_scene(world: World) -> Scene:
    state = build_state(world.state.loop, world.state.http, "redis")
    return Scene(type(world)(state))


def ids(items: list) -> list[int]:
    return [item.id for item in items]


def test_category_resolves_the_cached_category(scene: Scene) -> None:
    category = add_category(scene, 100)
    child = add_text(scene, 1, category_id=100)
    orphan = add_text(scene, 2)
    assert child.category is category
    assert scene.run(child.get_category()) is category
    assert orphan.category is None
    assert scene.run(orphan.get_category()) is None


def test_category_is_none_when_not_cached(scene: Scene) -> None:
    child = add_text(scene, 1, category_id=100)
    assert child.category is None
    assert scene.run(child.get_category()) is None


def test_remote_category_is_a_partial_handle(redis_scene: Scene) -> None:
    category = add_category(redis_scene, 100)
    child = add_text(redis_scene, 1, category_id=100)
    handle = child.category
    assert isinstance(handle, PartialGuildChannel)
    assert handle.id == 100
    assert handle.guild_id == GUILD_ID
    assert redis_scene.run(child.get_category()) == category
    assert add_text(redis_scene, 2).category is None


def test_guild_attribute_is_full_object_or_handle(
    scene: Scene, redis_scene: Scene
) -> None:
    channel = add_text(scene, 1)
    assert channel.guild is scene.guild
    remote = add_text(redis_scene, 1)
    assert remote.guild.id == GUILD_ID
    assert not hasattr(remote.guild, "channels")
    assert redis_scene.run(remote.guild.get()) is not None


def test_overwrites_resolve_roles_and_members(scene: Scene) -> None:
    role = scene.add_role(10, position=1)
    member = scene.add_member(1)
    channel = add_text(
        scene,
        1,
        [
            overwrite(10, ROLE, allow=SEND),
            overwrite(1, MEMBER, deny=SEND),
            overwrite(555, MEMBER, deny=SEND),
            overwrite(556, ROLE, deny=SEND),
        ],
    )
    resolved = scene.run(channel.get_overwrites())
    assert resolved == channel.overwrites
    assert set(resolved) == {role, member}
    assert resolved[role].send_messages is True
    assert resolved[member].send_messages is False


def test_changed_roles_apply_the_overwrite_without_touching_the_cache(
    scene: Scene,
) -> None:
    role = scene.add_role(10, position=1, permissions=Permissions(add_reactions=True))
    channel = add_text(scene, 1, [overwrite(10, ROLE, allow=SEND)])
    (changed,) = channel.changed_roles
    assert changed.id == role.id
    assert changed.permissions.send_messages
    assert changed.permissions.add_reactions
    assert not role.permissions.send_messages
    assert ids(scene.run(channel.get_changed_roles())) == [10]
    assert scene.run(channel.get_changed_roles())[0].permissions == changed.permissions


def test_permissions_synced_compares_the_category_overwrites(scene: Scene) -> None:
    scene.add_role(10, position=1)
    shared = [overwrite(10, ROLE, allow=SEND)]
    add_category(scene, 100, shared)
    synced = add_text(scene, 1, shared, category_id=100)
    desynced = add_text(scene, 2, [overwrite(10, ROLE, deny=SEND)], category_id=100)
    orphan = add_text(scene, 3, shared)
    for channel, expected in ((synced, True), (desynced, False), (orphan, False)):
        assert channel.permissions_synced is expected
        assert scene.run(channel.is_permissions_synced()) is expected


def test_category_children_are_sorted_like_the_discord_ui(scene: Scene) -> None:
    category = add_category(scene, 100)
    add_voice(scene, 5, category_id=100)
    add_text(scene, 3, category_id=100, position=2)
    add_text(scene, 2, category_id=100, position=1)
    add_stage(scene, 6, category_id=100)
    add_forum(scene, 7, category_id=100)
    add_text(scene, 4)
    assert ids(category.channels) == ids(scene.run(category.get_channels()))
    assert ids(category.channels)[:2] == [2, 3]
    assert ids(category.text_channels) == [2, 3]
    assert ids(scene.run(category.get_text_channels())) == [2, 3]
    assert ids(category.voice_channels) == ids(scene.run(category.get_voice_channels()))
    assert ids(category.voice_channels) == [5]
    assert ids(category.stage_channels) == ids(scene.run(category.get_stage_channels()))
    assert ids(category.stage_channels) == [6]
    assert ids(category.forum_channels) == ids(scene.run(category.get_forum_channels()))
    assert ids(category.forum_channels) == [7]


def test_remote_category_children_sync_raise(redis_scene: Scene) -> None:
    category = add_category(redis_scene, 100)
    add_text(redis_scene, 1, category_id=100)
    with pytest.raises(SyncCacheAccessError):
        _ = category.channels
    assert ids(redis_scene.run(category.get_channels())) == [1]


def test_text_channel_threads_and_get_thread(scene: Scene) -> None:
    channel = add_text(scene, 1)
    other = add_text(scene, 2)
    mine = add_thread(scene, 10, channel.id)
    add_thread(scene, 11, other.id)
    assert channel.threads == [mine]
    assert scene.run(channel.get_threads()) == [mine]
    assert channel.get_thread(10) is mine
    assert channel.get_thread(404) is None


def test_voice_members_and_voice_states(scene: Scene) -> None:
    voice = add_voice(scene, 5)
    other = add_voice(scene, 6)
    inside = scene.add_member(1)
    scene.add_member(2)
    add_voice_state(scene, 1, voice)
    add_voice_state(scene, 2, other)
    add_voice_state(scene, 3, voice)
    assert voice.members == [inside]
    assert scene.run(voice.get_members()) == [inside]
    assert list(voice.voice_states) == [1, 3]
    assert scene.run(voice.get_voice_states()) == voice.voice_states


def test_stage_roles_of_the_attendees(scene: Scene) -> None:
    stage = add_stage(scene, 6)
    for user_id in (1, 2, 3):
        scene.add_member(user_id)
    add_voice_state(scene, 1, stage)
    add_voice_state(scene, 2, stage, suppress=True)
    add_voice_state(scene, 3, stage, suppress=True, requested=True)
    expected = {
        "speakers": [1],
        "listeners": [2, 3],
        "requesting_to_speak": [3],
    }
    for name, member_ids in expected.items():
        assert ids(getattr(stage, name)) == member_ids
        assert ids(scene.run(getattr(stage, f"get_{name}")())) == member_ids


def test_stage_moderators_need_the_moderator_permissions(scene: Scene) -> None:
    stage = add_stage(scene, 6)
    scene.add_role(
        10,
        position=1,
        permissions=Permissions(
            view_channel=True,
            connect=True,
            mute_members=True,
            move_members=True,
            request_to_speak=True,
        ),
    )
    scene.add_member(1, roles=[10])
    scene.add_member(2)
    add_voice_state(scene, 1, stage)
    add_voice_state(scene, 2, stage)
    assert ids(stage.moderators) == [1]
    assert ids(scene.run(stage.get_moderators())) == [1]


def test_stage_instance_lookup(scene: Scene) -> None:
    stage = add_stage(scene, 6)
    assert stage.instance is None
    assert scene.run(stage.get_instance()) is None
    payload = scene.world.payload(
        t.channel.StageInstance,
        id="900",
        guild_id=str(GUILD_ID),
        channel_id=str(stage.id),
    )
    instance = StageInstance(guild=scene.guild, state=scene.state, data=payload)
    scene.run(scene.state._guild_bucket("stage_instances", GUILD_ID).set(900, instance))
    assert stage.instance is instance
    assert scene.run(stage.get_instance()) is instance


def test_last_message_comes_from_the_message_cache(scene: Scene) -> None:
    channel = add_text(scene, 1)
    voice = add_voice(scene, 2)
    message = scene.world.message
    scene.run(scene.state._store_message(message))
    for target in (channel, voice):
        target.last_message_id = None
        assert target.last_message is None
        assert scene.run(target.get_last_message()) is None
        target.last_message_id = message.id
        assert target.last_message is message
        assert scene.run(target.get_last_message()) is message


def test_forum_default_reaction_emoji(scene: Scene) -> None:
    forum = add_forum(scene, 1)
    forum._update(
        scene.guild,
        {
            **scene.world.payload(
                t.channel.ForumChannel,
                id="1",
                guild_id=str(GUILD_ID),
            ),
            "default_reaction_emoji": {"emoji_id": "321", "emoji_name": None},
        },
    )
    not_cached = forum.default_reaction_emoji
    assert isinstance(not_cached, PartialEmoji)
    assert not_cached.id == 321
    assert scene.run(forum.get_default_reaction_emoji()) is None
    emoji = scene.run(
        scene.state.store_emoji(
            scene.guild,
            scene.world.payload(t.emoji.Emoji, id="321", name="cached", roles=[]),
        )
    )
    assert forum.default_reaction_emoji is emoji
    assert scene.run(forum.get_default_reaction_emoji()) is emoji
    forum._default_reaction_emoji = "x"
    assert forum.default_reaction_emoji == "x"
    assert scene.run(forum.get_default_reaction_emoji()) == "x"


def test_thread_parent_owner_and_members(scene: Scene) -> None:
    channel = add_text(scene, 1)
    owner = scene.add_member(7)
    thread = add_thread(scene, 10, channel.id, owner_id=7)
    assert thread.parent is channel
    assert scene.run(thread.get_parent()) is channel
    assert thread.owner is owner
    assert scene.run(thread.get_owner()) is owner
    assert thread.guild is scene.guild
    assert thread.members == []
    member = ThreadMember(
        thread,
        {
            "user_id": "7",
            "id": "10",
            "join_timestamp": "2024-01-01T00:00:00+00:00",
            "flags": 0,
        },
    )
    scene.run(thread._add_member(member))
    assert thread.members == [member]
    assert scene.run(thread.get_members()) == [member]


def test_thread_parent_is_a_handle_when_not_cached(scene: Scene) -> None:
    thread = add_thread(scene, 10, 404)
    assert isinstance(thread.parent, PartialGuildChannel)
    assert thread.parent.id == 404
    assert scene.run(thread.get_parent()) is None
    assert thread.owner is None
    assert scene.run(thread.get_owner()) is None
    with pytest.raises(ClientException):
        _ = thread.category
    with pytest.raises(ClientException):
        scene.run(thread.get_category())


def test_thread_category_nsfw_and_applied_tags(scene: Scene) -> None:
    category = add_category(scene, 100)
    forum = add_forum(
        scene,
        1,
        category_id=100,
        tags=[
            {
                "id": "50",
                "name": "a",
                "moderated": False,
                "emoji_id": None,
                "emoji_name": None,
            },
            {
                "id": "51",
                "name": "b",
                "moderated": False,
                "emoji_id": None,
                "emoji_name": None,
            },
        ],
    )
    forum.nsfw = True
    thread = add_thread(scene, 10, forum.id, applied_tags=[51])
    assert thread.category is category
    assert scene.run(thread.get_category()) is category
    assert thread.category_id == 100
    assert scene.run(thread.get_category_id()) == 100
    assert thread.is_nsfw() is True
    assert scene.run(thread.check_nsfw()) is True
    assert [tag.id for tag in thread.applied_tags] == [51]
    assert [tag.id for tag in scene.run(thread.get_applied_tags())] == [51]


def test_thread_messages_come_from_the_cache(scene: Scene) -> None:
    channel = add_text(scene, 1)
    thread = add_thread(scene, 10, channel.id)
    message = scene.world.message
    scene.run(scene.state._store_message(message))
    thread.last_message_id = message.id
    assert thread.last_message is message
    assert scene.run(thread.get_last_message()) is message
    assert thread.starting_message is None
    assert scene.run(thread.get_starting_message()) is None


def test_remote_thread_accessors(redis_scene: Scene) -> None:
    channel = add_text(redis_scene, 1)
    thread = add_thread(redis_scene, 10, channel.id, owner_id=7)
    thread.last_message_id = 11
    assert isinstance(thread.parent, PartialGuildChannel)
    assert thread.guild.id == GUILD_ID
    assert redis_scene.run(thread.get_parent()) == channel
    for name in ("owner", "members", "last_message", "starting_message"):
        with pytest.raises(SyncCacheAccessError):
            getattr(thread, name)


def grant(scene: Scene, permissions: Permissions) -> None:
    scene.everyone._permissions = permissions.value
    scene.add_member(scene.world.me.id)


def test_can_send_checks_the_bot_permissions(scene: Scene) -> None:
    grant(scene, VIEW_SEND)
    channel = add_text(scene, 1)
    assert channel.can_send()
    assert scene.run(channel.check_can_send())
    assert not channel.can_send(Embed())
    assert not scene.run(channel.check_can_send(Embed()))
    with pytest.raises(TypeError):
        channel.can_send(object())
    with pytest.raises(TypeError):
        scene.run(channel.check_can_send(object()))


def test_can_send_is_false_without_send_messages(scene: Scene) -> None:
    grant(scene, Permissions(view_channel=True, embed_links=True))
    channel = add_text(scene, 1)
    assert not channel.can_send()
    assert not scene.run(channel.check_can_send())
    assert not channel.can_send(Embed())


def test_can_send_needs_the_bot_member(scene: Scene) -> None:
    channel = add_text(scene, 1)
    with pytest.raises(ClientException):
        channel.can_send()
    with pytest.raises(ClientException):
        scene.run(channel.check_can_send())
