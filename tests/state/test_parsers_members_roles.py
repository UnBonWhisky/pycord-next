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

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    OTHER_USER_ID,
    USER_ID,
    Recorder,
    guild_payload,
    member_payload,
    payload,
    recorder,  # noqa: F401
    user_payload,
)
from tests.state.test_parsers_threads_channels import with_guild

if TYPE_CHECKING:
    from discord.state import ConnectionState

STAGE_ID = 2_100_000_000_000_000_800
ROLE_ID = 2_100_000_000_000_000_801


def stage_payload(**fields: Any) -> dict[str, Any]:
    return payload(
        t.channel.StageInstance,
        id=str(STAGE_ID),
        guild_id=str(GUILD_ID),
        channel_id=str(CHANNEL_ID),
        **fields,
    )


@pytest.mark.asyncio
async def test_stage_instance_lifecycle(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["STAGE_INSTANCE_CREATE"](stage_payload(topic="first"))
    (created,) = recorder.last("stage_instance_create")
    assert created.topic == "first"

    await state.parsers["STAGE_INSTANCE_UPDATE"](stage_payload(topic="second"))
    old, new = recorder.last("stage_instance_update")
    assert old.topic == "first"
    assert new is created
    assert created.topic == "second"

    await state.parsers["STAGE_INSTANCE_DELETE"](stage_payload())
    assert recorder.last("stage_instance_delete") == (created,)
    assert await state._guild_bucket("stage_instances", guild.id).get(STAGE_ID) is None


@pytest.mark.asyncio
async def test_stage_instance_events_for_unknown_objects(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await with_guild(state)
    before = len(recorder.events)
    await state.parsers["STAGE_INSTANCE_UPDATE"](stage_payload())
    await state.parsers["STAGE_INSTANCE_DELETE"](stage_payload())
    unknown = {**stage_payload(), "guild_id": "999"}
    for event in ("CREATE", "UPDATE", "DELETE"):
        await state.parsers[f"STAGE_INSTANCE_{event}"](unknown)
    assert len(recorder.events) == before


def presence(user_id: int, **fields: Any) -> dict[str, Any]:
    return {
        "user": {"id": str(user_id)},
        "guild_id": str(GUILD_ID),
        "status": "idle",
        "activities": [],
        "client_status": {"web": "idle"},
        **fields,
    }


@pytest.mark.asyncio
async def test_presence_updates(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick=None), "guild_id": str(GUILD_ID)}
    )
    member = await guild.get_member(OTHER_USER_ID)

    await state.parsers["PRESENCE_UPDATE"](presence(OTHER_USER_ID))
    old, new = recorder.last("presence_update")
    assert new is member
    assert member.status is discord.Status.idle
    assert old is not new

    full_user = user_payload(OTHER_USER_ID)
    await state.parsers["PRESENCE_UPDATE"](
        presence(OTHER_USER_ID, user={**full_user, "username": "renamed"})
    )
    before, after = recorder.last("user_update")
    assert after.name == "renamed"
    assert before.name != "renamed"

    count = len(recorder.events)
    await state.parsers["PRESENCE_UPDATE"](presence(OTHER_USER_ID + 5))
    await state.parsers["PRESENCE_UPDATE"](
        {**presence(OTHER_USER_ID), "guild_id": "999"}
    )
    assert len(recorder.events) == count


@pytest.mark.asyncio
async def test_member_remove_update_and_chunks(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    state._cache_users = True
    guild._member_count = 5

    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="a"), "guild_id": str(GUILD_ID)}
    )
    assert guild._member_count == 6
    assert (await state.get_user(OTHER_USER_ID)) is not None

    update = {**member_payload(OTHER_USER_ID, nick="b"), "guild_id": str(GUILD_ID)}
    update["user"] = {**update["user"], "username": "renamed"}
    await state.parsers["GUILD_MEMBER_UPDATE"](update)
    assert recorder.last("user_update")[1].name == "renamed"
    assert recorder.last("member_update")[1].nick == "b"

    await state.parsers["GUILD_MEMBER_REMOVE"](
        {"guild_id": str(GUILD_ID), "user": user_payload(OTHER_USER_ID)}
    )
    assert guild._member_count == 5
    assert recorder.last("raw_member_remove")[0].user.id == OTHER_USER_ID
    assert await guild.get_member(OTHER_USER_ID) is None

    before = len(recorder.events)
    await state.parsers["GUILD_MEMBER_REMOVE"](
        {"guild_id": "999", "user": user_payload(OTHER_USER_ID)}
    )
    assert recorder.names()[before:] == ["raw_member_remove"]


@pytest.mark.asyncio
async def test_member_update_for_an_uncached_member(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    update = {**member_payload(OTHER_USER_ID, nick="x"), "guild_id": str(GUILD_ID)}
    update["user"] = {**update["user"], "username": "fresh"}

    await state.parsers["GUILD_MEMBER_UPDATE"](update)

    assert "member_update" not in recorder.names()
    cached = await guild.get_member(OTHER_USER_ID)
    assert cached is not None
    assert cached.nick == "x"


@pytest.mark.asyncio
async def test_member_chunks_with_presences(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await with_guild(state)
    state._cache_users = True
    state.process_chunk_requests = AsyncMock()  # type: ignore[method-assign]
    members = [member_payload(OTHER_USER_ID, nick=None)]

    await state.parsers["GUILD_MEMBERS_CHUNK"](
        {
            "guild_id": str(GUILD_ID),
            "members": members,
            "presences": [
                presence(OTHER_USER_ID),
                presence(OTHER_USER_ID + 9),
            ],
            "chunk_index": 0,
            "chunk_count": 1,
            "nonce": "n",
        }
    )

    state.process_chunk_requests.assert_awaited_once()
    args = state.process_chunk_requests.await_args.args
    assert args[0] == GUILD_ID
    assert args[1] == "n"
    assert [m.id for m in args[2]] == [OTHER_USER_ID]
    assert args[3] is True
    assert args[2][0].status is discord.Status.idle
    assert await state.get_user(OTHER_USER_ID) is not None

    await state.parsers["GUILD_MEMBERS_CHUNK"](
        {"guild_id": str(GUILD_ID), "members": [], "chunk_index": 0, "chunk_count": 3}
    )
    assert state.process_chunk_requests.await_args.args[3] is False


@pytest.mark.asyncio
async def test_member_add_without_member_count_or_cache(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    guild._member_count = None
    state.member_cache_flags = discord.MemberCacheFlags.none()
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick=None), "guild_id": str(GUILD_ID)}
    )
    assert recorder.names()[-1] == "member_join"
    assert guild._member_count is None
    assert await guild.get_member(OTHER_USER_ID) is None


@pytest.mark.asyncio
async def test_role_events(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    role = payload(t.role.Role, id=str(ROLE_ID), name="mod", position=2)
    role.pop("tags", None)
    await state.parsers["GUILD_ROLE_CREATE"]({"guild_id": str(GUILD_ID), "role": role})
    (created,) = recorder.last("guild_role_create")
    assert created.name == "mod"

    await state.parsers["GUILD_ROLE_UPDATE"](
        {"guild_id": str(GUILD_ID), "role": {**role, "name": "admin"}}
    )
    old, new = recorder.last("guild_role_update")
    assert old.name == "mod"
    assert new.name == "admin"
    assert await guild.get_role(ROLE_ID) is new

    before = len(recorder.events)
    await state.parsers["GUILD_ROLE_UPDATE"](
        {"guild_id": str(GUILD_ID), "role": {**role, "id": "5"}}
    )
    await state.parsers["GUILD_ROLE_DELETE"](
        {"guild_id": str(GUILD_ID), "role_id": "5"}
    )
    assert len(recorder.events) == before

    await state.parsers["GUILD_ROLE_DELETE"](
        {"guild_id": str(GUILD_ID), "role_id": str(ROLE_ID)}
    )
    assert recorder.last("guild_role_delete") == (new,)

    for event, data in (
        ("GUILD_ROLE_CREATE", {"guild_id": "999", "role": role}),
        ("GUILD_ROLE_UPDATE", {"guild_id": "999", "role": role}),
        ("GUILD_ROLE_DELETE", {"guild_id": "999", "role_id": "1"}),
    ):
        await state.parsers[event](data)
    assert len(recorder.events) == before + 1


@pytest.mark.asyncio
async def test_integration_and_webhook_events(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)

    await state.parsers["GUILD_INTEGRATIONS_UPDATE"]({"guild_id": str(GUILD_ID)})
    assert recorder.last("guild_integrations_update") == (guild,)

    integration = payload(
        t.integration.BotIntegration, id="2100000000000000900", type="discord"
    )
    await state.parsers["INTEGRATION_CREATE"](
        {**integration, "guild_id": str(GUILD_ID)}
    )
    assert recorder.last("integration_create")[0].id == 2_100_000_000_000_000_900
    await state.parsers["INTEGRATION_UPDATE"](
        {**integration, "guild_id": str(GUILD_ID)}
    )
    assert recorder.last("integration_update")[0].id == 2_100_000_000_000_000_900
    await state.parsers["INTEGRATION_DELETE"](
        {"id": "2100000000000000900", "guild_id": str(GUILD_ID)}
    )
    assert (
        recorder.last("raw_integration_delete")[0].integration_id
        == 2_100_000_000_000_000_900
    )

    await state.parsers["WEBHOOKS_UPDATE"](
        {"guild_id": str(GUILD_ID), "channel_id": str(CHANNEL_ID)}
    )
    assert recorder.last("webhooks_update")[0].id == CHANNEL_ID

    before = len(recorder.events)
    unknown = {"guild_id": "999"}
    for event in (
        "GUILD_INTEGRATIONS_UPDATE",
        "INTEGRATION_CREATE",
        "INTEGRATION_UPDATE",
        "INTEGRATION_DELETE",
        "WEBHOOKS_UPDATE",
    ):
        await state.parsers[event]({**unknown, **integration, "channel_id": "1"})
    await state.parsers["WEBHOOKS_UPDATE"](
        {"guild_id": str(GUILD_ID), "channel_id": "5"}
    )
    await state.parsers["WEBHOOKS_UPDATE"](
        {"guild_id": str(GUILD_ID), "channel_id": None}
    )
    assert len(recorder.events) == before


def voice_payload(
    user_id: int, channel_id: int | None, **fields: Any
) -> dict[str, Any]:
    return payload(
        t.voice.GuildVoiceState,
        user_id=str(user_id),
        channel_id=None if channel_id is None else str(channel_id),
        guild_id=str(GUILD_ID),
        **fields,
    )


@pytest.mark.asyncio
async def test_voice_state_updates_for_the_bot_and_members(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    state.member_cache_flags = discord.MemberCacheFlags._from_value(1)
    voice_channel = payload(
        t.channel.VoiceChannel,
        id=str(CHANNEL_ID + 1),
        guild_id=str(GUILD_ID),
        type=2,
        parent_id=None,
        permission_overwrites=[],
    )
    await state.parsers["CHANNEL_CREATE"](voice_channel)
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick=None), "guild_id": str(GUILD_ID)}
    )
    await guild._add_member(
        discord.Member(
            data=member_payload(OTHER_USER_ID, nick=None), guild=guild, state=state
        )
    )

    client = type("Voice", (), {})()
    client.on_voice_state_update = AsyncMock()  # type: ignore[attr-defined]
    state._add_voice_client(GUILD_ID, client)  # type: ignore[arg-type]
    guild.afk_channel_id = CHANNEL_ID + 1

    await state.parsers["VOICE_STATE_UPDATE"](
        voice_payload(USER_ID, CHANNEL_ID + 1, member=None)
    )
    await asyncio.sleep(0.01)
    client.on_voice_state_update.assert_awaited_once()  # type: ignore[attr-defined]
    assert client.on_voice_state_update.await_args.args[0].afk is True  # type: ignore[attr-defined]

    await state.parsers["VOICE_STATE_UPDATE"](
        voice_payload(OTHER_USER_ID, CHANNEL_ID + 1)
    )
    member, before, after = recorder.last("voice_state_update")
    assert member.id == OTHER_USER_ID
    assert after.channel.id == CHANNEL_ID + 1
    assert before.channel is None

    await state.parsers["VOICE_STATE_UPDATE"](voice_payload(OTHER_USER_ID, None))
    assert await guild.get_member(OTHER_USER_ID) is None
    assert recorder.last("voice_state_update")[2].channel is None

    count = len(recorder.events)
    stranger = voice_payload(OTHER_USER_ID + 77, CHANNEL_ID + 1)
    stranger.pop("member", None)
    await state.parsers["VOICE_STATE_UPDATE"](stranger)
    assert len(recorder.events) == count


@pytest.mark.asyncio
async def test_voice_events_for_unknown_channels_and_guilds(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await with_guild(state)
    before = len(recorder.events)
    status = {"id": "5", "guild_id": str(GUILD_ID), "status": "hi"}
    await state.parsers["VOICE_CHANNEL_STATUS_UPDATE"](status)
    await state.parsers["VOICE_CHANNEL_STATUS_UPDATE"]({**status, "guild_id": "999"})
    start = {
        "id": "5",
        "guild_id": str(GUILD_ID),
        "voice_start_time": 1_700_000_000,
    }
    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](start)
    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"]({**start, "guild_id": "999"})
    assert [n for n in recorder.names()[before:] if not n.startswith("raw_")] == []


_ = guild_payload


@pytest.mark.asyncio
async def test_voice_channel_status_and_start_time(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    voice_id = CHANNEL_ID + 1
    await state.parsers["CHANNEL_CREATE"](
        payload(
            t.channel.VoiceChannel,
            id=str(voice_id),
            guild_id=str(GUILD_ID),
            type=2,
            parent_id=None,
            permission_overwrites=[],
        )
    )
    channel = await guild.get_channel(voice_id)

    await state.parsers["VOICE_CHANNEL_STATUS_UPDATE"](
        {"id": str(voice_id), "guild_id": str(GUILD_ID), "status": "live now"}
    )
    updated, old_status, new_status = recorder.last("voice_channel_status_update")
    assert updated is channel
    assert new_status == "live now"
    assert old_status != "live now"
    assert recorder.names()[-2] == "raw_voice_channel_status_update"

    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](
        {
            "id": str(voice_id),
            "guild_id": str(GUILD_ID),
            "voice_start_time": 1_700_000_000,
        }
    )
    updated, _old, new_start = recorder.last("voice_channel_start_time_update")
    assert updated is channel
    assert new_start is not None
    assert channel.voice_start_time == new_start
