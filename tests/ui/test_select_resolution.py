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
from typing import TYPE_CHECKING, Any

import pytest

from discord import ComponentType, Member, Role, User, types as t, ui
from discord.channel import TextChannel
from discord.threads import Thread
from tests.models.context import World
from tests.models_async.a2_support import GUILD_ID, Scene
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient


@pytest.fixture(params=["memory", "redis"])
def scene(
    request: pytest.FixtureRequest, loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> Scene:
    return Scene(World(build_state(loop, http, request.param)))


@pytest.fixture
def memory_scene(world: World) -> Scene:
    return Scene(world)


def make_select(
    scene: Scene,
    select_type: ComponentType,
    resolved: dict[str, Any],
    values: list[str],
) -> ui.Select:
    interaction = SimpleNamespace(
        _state=scene.state,
        guild=scene.guild,
        guild_id=GUILD_ID,
        data={"resolved": resolved, "values": values},
    )
    select = ui.Select(select_type)
    select.refresh_from_modal(interaction, {"values": values})  # type: ignore[arg-type]
    return select


def member_payload(scene: Scene, user_id: int, **fields: Any) -> tuple[dict, dict]:
    payload = scene.world.payload(
        t.member.MemberWithUser,
        user={**scene.world.payload(t.user.User), "id": str(user_id)},
        roles=[],
        **fields,
    )
    payload.pop("communication_disabled_until", None)
    user = payload.pop("user")
    return user, payload


def test_user_select_uses_the_cached_member(scene: Scene) -> None:
    cached = scene.add_member(11)
    cached._client_status = {None: "online"}
    scene.run(scene.guild._add_member(cached))
    user, member = member_payload(scene, 11, nick="fresh")
    select = make_select(
        scene,
        ComponentType.user_select,
        {"users": {"11": user}, "members": {"11": member}},
        ["11"],
    )

    resolved = scene.run(select.get_values())

    assert [type(v) for v in resolved] == [Member]
    assert resolved[0].id == 11
    assert resolved[0].nick == "fresh"
    assert resolved[0].status.value == "online"
    stored = scene.run(scene.guild.get_member(11))
    assert stored.nick == "fresh"


def test_sync_values_match_pycord_on_the_memory_cache(memory_scene: Scene) -> None:
    scene = memory_scene
    cached = scene.add_member(11)
    user, member = member_payload(scene, 11, nick="fresh")
    select = make_select(
        scene,
        ComponentType.user_select,
        {"users": {"11": user}, "members": {"11": member}},
        ["11"],
    )

    resolved = select.values

    assert resolved == [cached]
    assert resolved[0] is cached
    assert cached.nick == "fresh"


def test_sync_values_work_with_a_remote_cache(scene: Scene) -> None:
    scene.add_member(11)
    user, member = member_payload(scene, 11, nick="fresh")
    select = make_select(
        scene,
        ComponentType.user_select,
        {"users": {"11": user}, "members": {"11": member}},
        ["11"],
    )

    resolved = select.values

    assert resolved is not None
    assert [v.id for v in resolved] == [11]
    assert isinstance(resolved[0], Member)
    assert resolved[0].nick == "fresh"


def test_uncached_member_is_built_from_the_payload_and_cached(scene: Scene) -> None:
    user, member = member_payload(scene, 12, nick="new")
    select = make_select(
        scene,
        ComponentType.mentionable_select,
        {"users": {"12": user}, "members": {"12": member}},
        ["12"],
    )

    assert scene.run(scene.guild.get_member(12)) is None
    resolved = scene.run(select.get_values())

    assert isinstance(resolved[0], Member)
    assert resolved[0].nick == "new"
    cached = scene.run(scene.guild.get_member(12))
    assert cached is not None
    assert cached.id == 12


def test_member_is_not_cached_without_the_interaction_flag(scene: Scene) -> None:
    scene.state.member_cache_flags.interaction = False
    user, member = member_payload(scene, 13)
    select = make_select(
        scene,
        ComponentType.user_select,
        {"users": {"13": user}, "members": {"13": member}},
        ["13"],
    )

    resolved = scene.run(select.get_values())

    assert resolved[0].id == 13
    assert scene.run(scene.guild.get_member(13)) is None


def test_user_without_member_data_is_a_user(scene: Scene) -> None:
    user = {**scene.world.payload(t.user.User), "id": "14"}
    select = make_select(
        scene, ComponentType.user_select, {"users": {"14": user}}, ["14"]
    )

    resolved = scene.run(select.get_values())

    assert [type(v) for v in resolved] == [User]
    assert resolved == select.values


def test_role_select_builds_roles_in_payload_order(scene: Scene) -> None:
    roles = {
        str(rid): {**scene.world.payload(t.role.Role), "id": str(rid)}
        for rid in (21, 22, 23)
    }
    select = make_select(
        scene, ComponentType.role_select, {"roles": roles}, ["23", "21"]
    )

    resolved = scene.run(select.get_values())

    assert [type(v) for v in resolved] == [Role, Role]
    assert [v.id for v in resolved] == [21, 23]
    assert [v.id for v in select.values] == [21, 23]


def test_mentionable_select_mixes_members_and_roles(scene: Scene) -> None:
    user, member = member_payload(scene, 31)
    role = {**scene.world.payload(t.role.Role), "id": "32"}
    select = make_select(
        scene,
        ComponentType.mentionable_select,
        {"users": {"31": user}, "members": {"31": member}, "roles": {"32": role}},
        ["31", "32"],
    )

    resolved = scene.run(select.get_values())

    assert [type(v) for v in resolved] == [Member, Role]


def test_channel_select_updates_the_cached_channel(scene: Scene) -> None:
    channel = scene.world.channel
    scene.run(scene.state._guild_bucket("channels", GUILD_ID).set(channel.id, channel))
    data = {
        **scene.world.payload(t.channel.TextChannel),
        "id": str(channel.id),
        "name": "renamed",
        "guild_id": str(GUILD_ID),
    }
    select = make_select(
        scene,
        ComponentType.channel_select,
        {"channels": {str(channel.id): data}},
        [str(channel.id)],
    )

    resolved = scene.run(select.get_values())

    assert isinstance(resolved[0], TextChannel)
    assert resolved[0].id == channel.id
    assert resolved[0].name == "renamed"
    if scene.state.cache.supports_sync:
        assert resolved[0] is channel
        assert select.values[0] is channel


def test_channel_select_falls_back_to_the_payload(scene: Scene) -> None:
    data = {
        **scene.world.payload(t.channel.TextChannel),
        "id": "4242",
        "guild_id": str(GUILD_ID),
    }
    select = make_select(
        scene, ComponentType.channel_select, {"channels": {"4242": data}}, ["4242"]
    )

    resolved = scene.run(select.get_values())

    assert isinstance(resolved[0], TextChannel)
    assert resolved[0].id == 4242
    assert [v.id for v in select.values] == [4242]


def test_channel_select_resolves_cached_threads(scene: Scene) -> None:
    thread = scene.world.thread
    scene.run(scene.state._guild_bucket("threads", GUILD_ID).set(thread.id, thread))
    data = {
        **scene.world.payload(t.threads.Thread),
        "id": str(thread.id),
        "name": "thread-renamed",
    }
    select = make_select(
        scene,
        ComponentType.channel_select,
        {"channels": {str(thread.id): data}},
        [str(thread.id)],
    )

    resolved = scene.run(select.get_values())

    assert isinstance(resolved[0], Thread)
    assert resolved[0].name == "thread-renamed"


def test_string_select_values_are_the_raw_strings(scene: Scene) -> None:
    select = make_select(scene, ComponentType.string_select, {}, ["a", "b"])

    assert select.values == ["a", "b"]
    assert scene.run(select.get_values()) == ["a", "b"]


def test_values_are_none_before_an_interaction(scene: Scene) -> None:
    select = ui.Select(ComponentType.user_select)

    assert select.values is None
    assert scene.run(select.get_values()) is None


def test_dispatch_resolution_makes_values_cache_aware(scene: Scene) -> None:
    cached = scene.add_member(41)
    cached._client_status = {None: "online"}
    scene.run(scene.guild._add_member(cached))
    user, member = member_payload(scene, 41)
    select = make_select(
        scene,
        ComponentType.user_select,
        {"users": {"41": user}, "members": {"41": member}},
        ["41"],
    )

    scene.run(select._resolve_state())
    resolved = select.values

    assert resolved is not None
    assert resolved[0].status.value == "online"


def test_new_interaction_resets_the_resolved_values(scene: Scene) -> None:
    user, member = member_payload(scene, 42)
    resolved = {"users": {"42": user}, "members": {"42": member}}
    select = make_select(scene, ComponentType.user_select, resolved, ["42"])
    scene.run(select._resolve_state())
    assert select._resolved_values is not None

    interaction = SimpleNamespace(
        _state=scene.state, guild=scene.guild, data={"resolved": {}, "values": []}
    )
    select.refresh_from_modal(interaction, {"values": []})  # type: ignore[arg-type]

    assert select._resolved_values is None
    assert select.values == []


def test_view_dispatch_resolves_before_the_callback(scene: Scene) -> None:
    cached = scene.add_member(51)
    cached._client_status = {None: "online"}
    scene.run(scene.guild._add_member(cached))
    user, member = member_payload(scene, 51)
    seen: list[Any] = []

    async def run() -> None:
        view = ui.View(timeout=None)
        select = ui.Select(ComponentType.user_select, custom_id="pick")

        async def callback(interaction: Any) -> None:
            seen.extend(select.values or [])

        select.callback = callback  # type: ignore[method-assign,assignment]
        view.add_item(select)
        interaction = SimpleNamespace(
            _state=scene.state,
            guild=scene.guild,
            data={"resolved": {"users": {"51": user}, "members": {"51": member}}},
        )
        select.refresh_from_modal(interaction, {"values": ["51"]})  # type: ignore[arg-type]
        await view._scheduled_task(select, interaction)  # type: ignore[arg-type]

    scene.run(run())

    assert [v.id for v in seen] == [51]
    assert seen[0].status.value == "online"
