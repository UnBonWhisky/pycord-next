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
    THREAD_ID,
    USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    payload,
    ready,
    recorder,  # noqa: F401
    thread_payload,
    user_payload,
)

if TYPE_CHECKING:
    from discord.state import ConnectionState


async def with_guild(state: ConnectionState) -> Any:
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    return guild


def member_event(thread_id: int = THREAD_ID, user_id: int = USER_ID) -> dict[str, Any]:
    return {
        "id": str(thread_id),
        "user_id": str(user_id),
        "join_timestamp": "2024-01-01T00:00:00+00:00",
        "flags": 0,
    }


@pytest.mark.asyncio
async def test_thread_create_for_a_known_thread_is_a_join(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"]({**thread_payload(), "newly_created": True})
    assert recorder.names()[-1] == "thread_create"
    thread = await guild.get_thread(THREAD_ID)
    assert thread is not None
    members = await thread.get_members()
    assert [m.id for m in members] == [USER_ID]

    await state.parsers["THREAD_CREATE"](thread_payload())
    assert recorder.last("thread_join") == (thread,)


@pytest.mark.asyncio
async def test_thread_create_without_newly_created_stays_silent(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    before = len(recorder.events)
    await state.parsers["THREAD_CREATE"](thread_payload())
    assert len(recorder.events) == before
    assert await guild.get_thread(THREAD_ID) is not None


@pytest.mark.asyncio
async def test_thread_events_for_unknown_guilds_are_ignored(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    await state._guilds.clear()
    unknown = {"guild_id": "999", "id": str(THREAD_ID)}
    before = len(recorder.events)
    for event in (
        "THREAD_CREATE",
        "THREAD_UPDATE",
        "THREAD_LIST_SYNC",
        "THREAD_MEMBER_UPDATE",
        "THREAD_MEMBERS_UPDATE",
    ):
        await state.parsers[event](unknown)
    await state.parsers["THREAD_DELETE"](
        {"id": str(THREAD_ID), "guild_id": "999", "parent_id": "1", "type": 11}
    )
    assert len(recorder.events) == before


@pytest.mark.asyncio
async def test_thread_update_adds_archives_and_creates(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"](thread_payload())

    await state.parsers["THREAD_UPDATE"](thread_payload(name="renamed"))
    old, new = recorder.last("thread_update")
    assert new.name == "renamed"
    assert old.name != "renamed"
    assert recorder.names()[-1] == "raw_thread_update"

    archived = thread_payload()
    archived["thread_metadata"] = {**archived["thread_metadata"], "archived": True}
    await state.parsers["THREAD_UPDATE"](archived)
    assert await guild.get_thread(THREAD_ID) is None

    fresh = thread_payload()
    fresh["id"] = str(THREAD_ID + 50)
    await state.parsers["THREAD_UPDATE"](fresh)
    assert recorder.last("thread_join")[0].id == THREAD_ID + 50
    assert await guild.get_thread(THREAD_ID + 50) is not None

    gone = thread_payload()
    gone["id"] = str(THREAD_ID + 60)
    gone["thread_metadata"] = {**gone["thread_metadata"], "archived": True}
    await state.parsers["THREAD_UPDATE"](gone)
    assert await guild.get_thread(THREAD_ID + 60) is None


@pytest.mark.asyncio
async def test_thread_delete_clears_the_message_thread(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"](thread_payload())
    thread = await guild.get_thread(THREAD_ID)
    message = payload(
        t.message.Message,
        id=str(THREAD_ID),
        channel_id=str(CHANNEL_ID),
        guild_id=str(GUILD_ID),
        author=user_payload(OTHER_USER_ID),
        type=0,
        edited_timestamp=None,
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "poll",
        "thread",
    ):
        message.pop(key, None)
    await state.parsers["MESSAGE_CREATE"](message)

    await state.parsers["THREAD_DELETE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "parent_id": str(CHANNEL_ID),
            "type": 11,
        }
    )

    assert recorder.last("thread_delete") == (thread,)
    assert await guild.get_thread(THREAD_ID) is None
    cached = await state._get_message(THREAD_ID)
    assert cached is not None
    assert cached.thread is None

    before = len(recorder.events)
    await state.parsers["THREAD_DELETE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "parent_id": str(CHANNEL_ID),
            "type": 11,
        }
    )
    assert recorder.names()[before:] == ["raw_thread_delete"]


@pytest.mark.asyncio
async def test_thread_list_sync_by_channel_and_for_the_whole_guild(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"](thread_payload())
    other = thread_payload()
    other["id"] = str(THREAD_ID + 1)
    other["parent_id"] = str(CHANNEL_ID + 9)
    await state.parsers["THREAD_CREATE"](other)

    replacement = thread_payload()
    replacement["id"] = str(THREAD_ID + 2)
    await state.parsers["THREAD_LIST_SYNC"](
        {
            "guild_id": str(GUILD_ID),
            "channel_ids": [str(CHANNEL_ID)],
            "threads": [replacement],
            "members": [member_event(THREAD_ID + 2), member_event(THREAD_ID + 99)],
        }
    )
    assert {t_.id for t_ in await guild.get_threads()} == {THREAD_ID + 1, THREAD_ID + 2}
    assert recorder.last("thread_join")[0].id == THREAD_ID + 2
    assert recorder.last("thread_remove")[0].id == THREAD_ID
    new_thread = await guild.get_thread(THREAD_ID + 2)
    assert [m.id for m in await new_thread.get_members()] == [USER_ID]

    await state.parsers["THREAD_LIST_SYNC"](
        {"guild_id": str(GUILD_ID), "threads": [], "members": []}
    )
    assert await guild.get_threads() == []
    assert {e[1][0].id for e in recorder.events if e[0] == "thread_remove"} >= {
        THREAD_ID + 1
    }


@pytest.mark.asyncio
async def test_thread_member_update_sets_me(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"](thread_payload())
    thread = await guild.get_thread(THREAD_ID)

    await state.parsers["THREAD_MEMBER_UPDATE"](
        {**member_event(), "guild_id": str(GUILD_ID)}
    )
    assert thread.me is not None
    assert thread.me.id == USER_ID

    before = len(recorder.events)
    await state.parsers["THREAD_MEMBER_UPDATE"](
        {**member_event(THREAD_ID + 77), "guild_id": str(GUILD_ID)}
    )
    assert len(recorder.events) == before


@pytest.mark.asyncio
async def test_thread_members_update(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    await state.parsers["THREAD_CREATE"](thread_payload())
    thread = await guild.get_thread(THREAD_ID)
    me = state.self_id

    await state.parsers["THREAD_MEMBERS_UPDATE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "member_count": 3,
            "added_members": [
                member_event(user_id=OTHER_USER_ID),
                member_event(user_id=me),
            ],
        }
    )
    assert recorder.last("thread_member_join")[0].id == OTHER_USER_ID
    assert recorder.last("thread_join") == (thread,)
    assert thread.me is not None

    await state.parsers["THREAD_MEMBERS_UPDATE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "member_count": 1,
            "removed_member_ids": [str(OTHER_USER_ID), str(me), "424242"],
        }
    )
    assert recorder.last("thread_member_remove")[0].id == OTHER_USER_ID
    assert recorder.last("thread_remove") == (thread,)
    assert thread.me is None
    assert recorder.names().count("raw_thread_member_remove") == 2

    before = len(recorder.events)
    await state.parsers["THREAD_MEMBERS_UPDATE"](
        {"id": "5", "guild_id": str(GUILD_ID), "member_count": 1}
    )
    assert len(recorder.events) == before


@pytest.mark.asyncio
async def test_channel_events_for_unknown_guilds_and_channels(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    before = len(recorder.events)

    await state.parsers["CHANNEL_DELETE"]({**channel_payload(), "id": "5"})
    await state.parsers["CHANNEL_DELETE"]({**channel_payload(), "guild_id": "999"})
    await state.parsers["CHANNEL_UPDATE"]({**channel_payload(), "id": "5"})
    await state.parsers["CHANNEL_UPDATE"]({**channel_payload(), "guild_id": "999"})
    await state.parsers["CHANNEL_CREATE"]({**channel_payload(), "guild_id": "999"})
    await state.parsers["CHANNEL_CREATE"]({**channel_payload(), "type": 999})
    await state.parsers["CHANNEL_PINS_UPDATE"](
        {"channel_id": "5", "guild_id": str(GUILD_ID)}
    )
    await state.parsers["CHANNEL_PINS_UPDATE"]({"channel_id": "5"})
    assert len(recorder.events) == before
    assert await guild.get_channel(CHANNEL_ID) is not None


@pytest.mark.asyncio
async def test_channel_update_delete_and_pins(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    guild = await with_guild(state)
    channel = await guild.get_channel(CHANNEL_ID)

    await state.parsers["CHANNEL_UPDATE"]({**channel_payload(), "name": "renamed"})
    old, new = recorder.last("guild_channel_update")
    assert new is channel
    assert new.name == "renamed"
    assert old.name != "renamed"

    await state.parsers["CHANNEL_PINS_UPDATE"](
        {
            "channel_id": str(CHANNEL_ID),
            "guild_id": str(GUILD_ID),
            "last_pin_timestamp": "2024-01-01T00:00:00+00:00",
        }
    )
    assert recorder.last("guild_channel_pins_update")[0] is channel

    await state.parsers["CHANNEL_DELETE"](channel_payload())
    assert recorder.last("guild_channel_delete") == (channel,)
    assert await guild.get_channel(CHANNEL_ID) is None


@pytest.mark.asyncio
async def test_group_channel_updates(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    group_payload = payload(
        t.channel.GroupDMChannel,
        id="2100000000000000900",
        type=3,
        recipients=[user_payload(OTHER_USER_ID)],
        name="old",
        owner_id=str(OTHER_USER_ID),
    )
    group = discord.GroupChannel(me=state.user, state=state, data=group_payload)
    await state._add_private_channel(group)

    await state.parsers["CHANNEL_UPDATE"]({**group_payload, "name": "new"})

    old, new = recorder.last("private_channel_update")
    assert new is group
    assert new.name == "new"
    assert old.name == "old"


@pytest.mark.asyncio
async def test_private_channel_pins(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    dm = await state.add_dm_channel(
        payload(
            t.channel.DMChannel,
            id="2100000000000000901",
            recipients=[user_payload(OTHER_USER_ID)],
        )
    )
    await state.parsers["CHANNEL_PINS_UPDATE"](
        {"channel_id": str(dm.id), "last_pin_timestamp": "2024-01-01T00:00:00+00:00"}
    )
    assert recorder.last("private_channel_pins_update")[0] is dm


@pytest.mark.asyncio
async def test_guild_lifecycle_events(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    await state._guilds.clear()
    before = len(recorder.events)

    await state.parsers["GUILD_CREATE"]({**guild_payload(), "unavailable": True})
    assert len(recorder.events) == before
    for event, data in (
        ("GUILD_UPDATE", guild_payload()),
        ("GUILD_DELETE", {"id": str(GUILD_ID)}),
        ("GUILD_BAN_ADD", {"guild_id": str(GUILD_ID), "user": user_payload()}),
    ):
        await state.parsers[event](data)
    assert len(recorder.events) == before

    await state.parsers["GUILD_CREATE"]({**guild_payload(), "unavailable": None})
    guild = await state._get_guild(GUILD_ID)
    assert recorder.last("guild_join") == (guild,)

    await state.parsers["GUILD_UPDATE"]({**guild_payload(), "name": "renamed"})
    old, new = recorder.last("guild_update")
    assert new is guild
    assert new.name == "renamed"
    assert old.name != "renamed"

    await state.parsers["GUILD_BAN_ADD"](
        {"guild_id": str(GUILD_ID), "user": user_payload(OTHER_USER_ID)}
    )
    banned = recorder.last("member_ban")
    assert banned[0] is guild
    assert banned[1].id == OTHER_USER_ID
    await state.parsers["GUILD_BAN_ADD"]({"guild_id": str(GUILD_ID), "user": {}})

    await state.parsers["GUILD_DELETE"]({"id": str(GUILD_ID), "unavailable": True})
    assert recorder.last("guild_unavailable") == (guild,)
    assert guild.unavailable is True
    await state.parsers["GUILD_DELETE"]({"id": str(GUILD_ID)})
    assert recorder.last("guild_remove") == (guild,)
    assert await state._get_guild(GUILD_ID) is None


@pytest.mark.asyncio
async def test_guild_create_waits_for_the_ready_state_and_chunks(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    await state._guilds.clear()
    state._ready_state = asyncio.Queue()
    await state.parsers["GUILD_CREATE"]({**guild_payload(), "unavailable": False})
    queued = state._ready_state.get_nowait()
    assert queued.id == GUILD_ID
    assert "guild_available" not in recorder.names()
    del state._ready_state

    await state._guilds.clear()
    state._guild_needs_chunking = AsyncMock(return_value=True)  # type: ignore[method-assign]
    state._chunk_and_dispatch = AsyncMock()  # type: ignore[method-assign]
    await state.parsers["GUILD_CREATE"]({**guild_payload(), "unavailable": False})
    await asyncio.sleep(0)
    state._chunk_and_dispatch.assert_awaited_once()

    state._guild_needs_chunking = AsyncMock(return_value=False)  # type: ignore[method-assign]
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"]({**guild_payload(), "unavailable": False})
    assert recorder.names()[-1] == "guild_available"


@pytest.mark.asyncio
async def test_voice_server_update_is_forwarded_to_the_voice_client(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    client = type("Voice", (), {})()
    client.on_voice_server_update = AsyncMock()  # type: ignore[attr-defined]
    state._add_voice_client(GUILD_ID, client)  # type: ignore[arg-type]

    await state.parsers["VOICE_SERVER_UPDATE"](
        {"token": "t", "guild_id": str(GUILD_ID), "endpoint": "voice.example:443"}
    )
    await asyncio.sleep(0.01)
    client.on_voice_server_update.assert_awaited_once()  # type: ignore[attr-defined]
    raw = client.on_voice_server_update.await_args.args[0]  # type: ignore[attr-defined]
    assert raw.token == "t"  # noqa: S105

    await state.parsers["VOICE_SERVER_UPDATE"](
        {"token": "t", "guild_id": "999", "endpoint": None}
    )


@pytest.mark.asyncio
async def test_logging_coroutine_reports_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from discord.state.parsers.voice import logging_coroutine

    async def fine() -> None: ...

    async def broken() -> None:
        raise RuntimeError("boom")

    await logging_coroutine(fine(), info="fine")
    with caplog.at_level("ERROR"):
        await logging_coroutine(broken(), info="the handler")
    assert "Exception occurred during the handler" in caplog.text
