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

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.errors import HTTPException
from discord.guild import _group_by_category
from tests.core.rig import MP3, Rig
from tests.core.test_channel_remote import channel_of, make_channel

if TYPE_CHECKING:
    from tests.models.context import World


def test_channels_are_grouped_by_category(world: World) -> None:
    rig = Rig(world)
    category = make_channel(rig, "category", position=0)
    empty = make_channel(rig, "category", position=1)
    inside = make_channel(rig, "text", parent_id=str(category.id), position=2)
    loose = make_channel(rig, "voice", position=3)
    other = make_channel(rig, "text", parent_id=str(category.id), position=4)

    grouped = _group_by_category([category, empty, inside, loose, other])  # type: ignore[list-item]

    by_id = {key.id if key else None: members for key, members in grouped}
    assert by_id[category.id] == [inside, other]
    assert by_id[empty.id] == []
    assert by_id[None] == [loose]


def test_role_removal_shifts_the_positions_above(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    roles = {}
    for number, position in ((1, 1), (2, 2), (3, 3)):
        roles[number] = discord.Role(
            guild=guild,
            state=rig.state,
            data=rig.payload(
                t.role.Role, id=str(9000 + number), position=position, managed=False
            ),
        )
        rig.run(
            rig.state._guild_bucket("roles", guild.id).set(9000 + number, roles[number])
        )

    removed = rig.run(guild._remove_role(9002))

    assert removed is roles[2]
    assert roles[1].position == 1
    assert roles[3].position == 2
    assert rig.run(guild.get_role(9002)) is None
    with pytest.raises(KeyError):
        rig.run(guild._remove_role(9002))


def test_thread_cleanup_helpers(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    threads = []
    for number, parent in (
        (1, rig.channel.id),
        (2, rig.channel.id),
        (3, rig.channel.id + 7),
    ):
        thread = discord.Thread(
            guild=guild,
            state=rig.state,
            data=rig.payload(
                t.threads.Thread,
                id=str(9100 + number),
                guild_id=str(guild.id),
                parent_id=str(parent),
                type=11,
            ),
        )
        rig.run(rig.state._add_thread(guild.id, thread))
        threads.append(thread)

    removed = rig.run(guild._filter_threads({rig.channel.id}))
    assert {9101, 9102} <= set(removed)
    assert 9103 in {th.id for th in rig.run(guild.get_threads())}
    assert not ({9101, 9102} & {th.id for th in rig.run(guild.get_threads())})

    rig.run(guild._remove_threads_by_channel(rig.channel.id + 7))
    assert 9103 not in {th.id for th in rig.run(guild.get_threads())}

    rig.run(rig.state._add_thread(guild.id, threads[0]))
    rig.run(guild._clear_threads())
    assert rig.run(guild.get_threads()) == []


def test_sound_and_event_bookkeeping(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    sound = discord.SoundboardSound(
        state=rig.state,
        http=rig.http,
        data=rig.payload(
            t.soundboard.SoundboardSound, sound_id="9200", guild_id=str(guild.id)
        ),
    )
    rig.run(guild._add_sound(sound))
    rig.run(guild._remove_sound(9200))
    assert rig.run(guild.get_sound(9200)) is None

    events = [
        discord.ScheduledEvent(
            state=rig.state,
            guild=guild,
            creator=None,
            data=rig.payload(
                t.scheduled_events.ScheduledEvent,
                id=str(9300 + number),
                guild_id=str(guild.id),
                creator_id=None,
            ),
        )
        for number in range(2)
    ]
    rig.run(guild._scheduled_events_from_list(events))
    rig.run(guild._scheduled_events_from_list(events[:1]))
    assert [e.id for e in rig.run(guild.get_scheduled_events())] == [9300]


def test_voice_state_updates(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    voice = make_channel(rig, "voice")
    user_id = 9400

    def event(channel: int | None, **fields: Any) -> Any:
        return rig.payload(
            t.voice.GuildVoiceState,
            user_id=str(user_id),
            channel_id=None if channel is None else str(channel),
            guild_id=str(guild.id),
            **fields,
        )

    member, before, after = rig.run(
        guild._update_voice_state(event(voice.id, member=None), voice.id)
    )
    assert member is None
    assert before.channel is None
    assert after.channel.id == voice.id
    assert rig.run(guild._voice_state_for(user_id)) is after

    member_payload = rig.payload(t.member.Member, roles=[])
    member, before, after = rig.run(
        guild._update_voice_state(event(voice.id, member=member_payload), voice.id)
    )
    assert before is not after

    member, before, after = rig.run(
        guild._update_voice_state(event(None, member=None), None)
    )
    assert after.channel is None
    assert rig.run(guild._voice_state_for(user_id)) is None


def test_self_owner_and_role_properties(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    guild.owner_id = None
    assert guild.owner is None
    assert guild.me is None
    rig.state.user = None
    assert guild.me is None
    rig.state.user = rig.world.me
    assert guild.premium_subscriber_role is None
    assert guild.self_role is None
    assert rig.run(guild.get_premium_subscriber_role()) is None
    assert rig.run(guild.get_self_role()) is None
    assert rig.run(guild.get_member(None)) is None
    assert rig.run(guild._resolve_channel(None)) is None


def test_special_roles_are_found(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    booster = discord.Role(
        guild=guild,
        state=rig.state,
        data=rig.payload(
            t.role.Role, id="9500", tags={"premium_subscriber": None}, managed=True
        ),
    )
    mine = discord.Role(
        guild=guild,
        state=rig.state,
        data=rig.payload(
            t.role.Role, id="9501", tags={"bot_id": str(rig.world.me.id)}, managed=True
        ),
    )
    bucket = rig.state._guild_bucket("roles", guild.id)
    rig.run(bucket.set(9500, booster))
    rig.run(bucket.set(9501, mine))
    rig.state.user = rig.world.me

    assert guild.premium_subscriber_role is booster
    assert rig.run(guild.get_premium_subscriber_role()) is booster
    assert guild.self_role is mine
    assert rig.run(guild.get_self_role()) is mine


def test_large_guild_detection(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    guild._large = None
    guild._member_count = 250
    assert guild.large is True
    guild._member_count = 10
    assert guild.large is False
    guild._member_count = None
    assert guild.large is False
    guild._large = True
    assert guild.large is True


def test_guild_get_or_fetch_swallows_errors(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    member = rig.world.member
    rig.run(guild._add_member(member))
    assert rig.run(guild.get_or_fetch(discord.Member, member.id)) is member

    rig.http.get_member.side_effect = HTTPException(
        type("R", (), {"status": 404, "reason": "x"})(),
        "x",  # type: ignore[arg-type]
    )
    assert rig.run(guild.get_or_fetch(discord.Member, 424242, default="d")) == "d"
    assert rig.run(guild.get_or_fetch(discord.Member, None)) is None


def test_fetch_role_scans_the_guild_roles(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    rig.respond(
        "get_roles",
        [rig.payload(t.role.Role, id="9600"), rig.payload(t.role.Role, id="9601")],
    )
    found = rig.run(guild._fetch_role(9601))
    assert found is not None
    assert found.id == 9601
    assert rig.run(guild._fetch_role(1)) is None


def test_create_sound_emoji_forms(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    rig.respond("create_guild_sound", rig.payload(t.soundboard.SoundboardSound))

    custom = discord.PartialEmoji(name="x", id=77)
    rig.run(guild.create_sound("a", MP3, emoji=custom))
    kwargs = rig.http.create_guild_sound.call_args.kwargs
    assert (kwargs["emoji_id"], kwargs["emoji_name"]) == (77, None)

    guild_emoji = discord.GuildEmoji(
        guild=guild, state=rig.state, data=rig.payload(t.emoji.Emoji, id="78")
    )
    rig.run(guild.create_sound("a", MP3, emoji=guild_emoji))
    assert rig.http.create_guild_sound.call_args.kwargs["emoji_id"] == 78

    rig.run(guild.create_sound("a", MP3, emoji=5))  # type: ignore[arg-type]
    kwargs = rig.http.create_guild_sound.call_args.kwargs
    assert (kwargs["emoji_id"], kwargs["emoji_name"]) == (None, None)
    _ = io


def test_forum_reaction_emoji_from_models(world: World) -> None:
    rig = Rig(world)
    guild = rig.guild
    rig.respond(
        "create_channel",
        rig.payload(
            t.channel.ForumChannel,
            guild_id=str(guild.id),
            type=15,
            parent_id=None,
            permission_overwrites=[],
        ),
    )
    emoji = discord.PartialEmoji(name="x", id=77)
    rig.run(guild.create_forum_channel("forum", default_reaction_emoji=emoji))
    assert rig.http.create_channel.call_args.kwargs["default_reaction_emoji"] == {
        "emoji_id": 77,
        "emoji_name": None,
    }


def test_voice_channel_position_option(world: World) -> None:
    rig = Rig(world)
    rig.respond(
        "create_channel",
        rig.payload(
            t.channel.VoiceChannel,
            guild_id=str(rig.guild.id),
            type=2,
            parent_id=None,
            permission_overwrites=[],
        ),
    )
    rig.run(rig.guild.create_voice_channel("voice", position=4))
    assert rig.http.create_channel.call_args.kwargs["position"] == 4
    _ = channel_of
