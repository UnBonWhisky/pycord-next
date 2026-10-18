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

from discord import types as t
from discord.channel import (
    CategoryChannel,
    ForumChannel,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from discord.member import VoiceState
from discord.permissions import Permissions
from discord.threads import Thread
from tests.models_async.a2_support import GUILD_ID, Scene

if TYPE_CHECKING:
    from discord.abc import GuildChannel

ROLE = 0
MEMBER = 1


def overwrite(
    target_id: int,
    kind: int,
    allow: Permissions | None = None,
    deny: Permissions | None = None,
) -> dict[str, Any]:
    return {
        "id": str(target_id),
        "type": kind,
        "allow": str((allow or Permissions.none()).value),
        "deny": str((deny or Permissions.none()).value),
    }


def add_channel(scene: Scene, channel: GuildChannel) -> None:
    scene.run(scene.guild._add_channel(channel))


def add_category(
    scene: Scene, channel_id: int, overwrites: list[dict[str, Any]] | None = None
) -> CategoryChannel:
    channel = CategoryChannel(
        state=scene.state,
        guild=scene.guild,
        data=scene.world.payload(
            t.channel.CategoryChannel,
            id=str(channel_id),
            guild_id=str(GUILD_ID),
            permission_overwrites=overwrites or [],
        ),
    )
    add_channel(scene, channel)
    return channel


def add_text(
    scene: Scene,
    channel_id: int,
    overwrites: list[dict[str, Any]] | None = None,
    *,
    category_id: int | None = None,
    position: int = 0,
) -> TextChannel:
    channel = TextChannel(
        state=scene.state,
        guild=scene.guild,
        data=scene.world.payload(
            t.channel.TextChannel,
            id=str(channel_id),
            guild_id=str(GUILD_ID),
            parent_id=None if category_id is None else str(category_id),
            position=position,
            permission_overwrites=overwrites or [],
        ),
    )
    add_channel(scene, channel)
    return channel


def add_forum(
    scene: Scene,
    channel_id: int,
    *,
    tags: list[dict[str, Any]] | None = None,
    category_id: int | None = None,
) -> ForumChannel:
    channel = ForumChannel(
        state=scene.state,
        guild=scene.guild,
        data=scene.world.payload(
            t.channel.ForumChannel,
            id=str(channel_id),
            guild_id=str(GUILD_ID),
            parent_id=None if category_id is None else str(category_id),
            available_tags=tags or [],
            permission_overwrites=[],
        ),
    )
    add_channel(scene, channel)
    return channel


def add_voice(
    scene: Scene,
    channel_id: int,
    overwrites: list[dict[str, Any]] | None = None,
    *,
    category_id: int | None = None,
) -> VoiceChannel:
    channel = VoiceChannel(
        state=scene.state,
        guild=scene.guild,
        data=scene.world.payload(
            t.channel.VoiceChannel,
            id=str(channel_id),
            guild_id=str(GUILD_ID),
            parent_id=None if category_id is None else str(category_id),
            permission_overwrites=overwrites or [],
        ),
    )
    add_channel(scene, channel)
    return channel


def add_stage(
    scene: Scene, channel_id: int, *, category_id: int | None = None
) -> StageChannel:
    channel = StageChannel(
        state=scene.state,
        guild=scene.guild,
        data=scene.world.payload(
            t.channel.StageChannel,
            id=str(channel_id),
            guild_id=str(GUILD_ID),
            parent_id=None if category_id is None else str(category_id),
            permission_overwrites=[],
        ),
    )
    add_channel(scene, channel)
    return channel


def add_thread(
    scene: Scene,
    thread_id: int,
    parent_id: int,
    *,
    owner_id: int | None = None,
    applied_tags: list[int] | None = None,
) -> Thread:
    payload = scene.world.payload(
        t.threads.Thread,
        id=str(thread_id),
        guild_id=str(GUILD_ID),
        parent_id=str(parent_id),
        owner_id=None if owner_id is None else str(owner_id),
        applied_tags=[str(tag) for tag in applied_tags or []],
    )
    payload.pop("member", None)
    thread = Thread(guild=scene.guild, state=scene.state, data=payload)
    scene.run(scene.guild._add_thread(thread))
    return thread


def add_voice_state(
    scene: Scene,
    user_id: int,
    channel: GuildChannel,
    *,
    suppress: bool = False,
    requested: bool = False,
) -> VoiceState:
    payload = scene.world.payload(
        t.voice.GuildVoiceState,
        user_id=str(user_id),
        channel_id=str(channel.id),
        guild_id=str(GUILD_ID),
        suppress=suppress,
        request_to_speak_timestamp="2024-01-01T00:00:00+00:00" if requested else None,
    )
    payload.pop("member", None)
    voice = VoiceState(data=payload, state=scene.state, channel=channel)  # type: ignore[arg-type]
    scene.run(scene.state._guild_bucket("voice_states", GUILD_ID).set(user_id, voice))
    return voice
