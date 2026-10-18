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

import pytest

from discord import types as t
from discord.flags import MemberCacheFlags
from tests.payloads.generator import generate

if TYPE_CHECKING:
    from discord.state import ConnectionState

GUILD_ID = 2_100_000_000_000_000_001
CHANNEL_ID = 2_100_000_000_000_000_002
THREAD_ID = 2_100_000_000_000_000_003
MESSAGE_ID = 2_100_000_000_000_000_004
USER_ID = 2_100_000_000_000_000_005
OTHER_USER_ID = 2_100_000_000_000_000_006


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, event: str, *args: Any, **_kwargs: Any) -> None:
        self.events.append((event, args))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def last(self, event: str) -> tuple[Any, ...]:
        for name, args in reversed(self.events):
            if name == event:
                return args
        raise AssertionError(f"{event} was not dispatched: {self.names()}")


@pytest.fixture
def recorder(state: ConnectionState) -> Recorder:
    recorder = Recorder()
    state.dispatch = recorder
    state.member_cache_flags = MemberCacheFlags.all()
    return recorder


def payload(tp: Any, **fields: Any) -> dict[str, Any]:
    return {**generate(tp, seed=3), **fields}


def user_payload(user_id: int = USER_ID) -> dict[str, Any]:
    return payload(t.user.User, id=str(user_id), discriminator="0")


def guild_payload() -> dict[str, Any]:
    data = payload(
        t.guild.Guild,
        id=str(GUILD_ID),
        channels=[],
        threads=[],
        members=[],
        voice_states=[],
        roles=[],
        emojis=[],
        stickers=[],
        stage_instances=[],
        guild_scheduled_events=[],
        soundboard_sounds=[],
        unavailable=False,
        member_count=0,
    )
    data.pop("presences", None)
    return data


def channel_payload() -> dict[str, Any]:
    return payload(
        t.channel.TextChannel,
        id=str(CHANNEL_ID),
        guild_id=str(GUILD_ID),
        type=0,
        parent_id=None,
        permission_overwrites=[],
    )


def thread_payload(**fields: Any) -> dict[str, Any]:
    data = payload(
        t.threads.Thread,
        id=str(THREAD_ID),
        guild_id=str(GUILD_ID),
        parent_id=str(CHANNEL_ID),
        owner_id=str(USER_ID),
        type=11,
        **fields,
    )
    data.pop("member", None)
    data["thread_metadata"] = {
        **data["thread_metadata"],
        "archived": fields.get("archived", False),
        "archive_timestamp": "2024-01-01T00:00:00+00:00",
        "create_timestamp": "2024-01-01T00:00:00+00:00",
    }
    return data


def member_payload(user_id: int, nick: str | None) -> dict[str, Any]:
    data = payload(t.member.MemberWithUser, roles=[], nick=nick)
    data["user"] = user_payload(user_id)
    data["joined_at"] = "2024-01-01T00:00:00+00:00"
    for key in ("premium_since", "communication_disabled_until", "avatar", "banner"):
        data.pop(key, None)
    return data


async def ready(state: ConnectionState) -> None:
    await state.parsers["READY"](
        {
            "user": {**user_payload(), "bot": True},
            "guilds": [{"id": str(GUILD_ID), "unavailable": True}],
            "application": {"id": str(OTHER_USER_ID), "flags": 0},
        }
    )
    assert state._ready_task is not None
    state._ready_task.cancel()
    await asyncio.sleep(0)
    del state._ready_state


@pytest.mark.asyncio
async def test_ready_populates_user_and_guilds(
    state: ConnectionState, recorder: Recorder
) -> None:
    await ready(state)

    assert state.user is not None
    assert state.user.id == USER_ID
    assert state.application_id == OTHER_USER_ID
    assert recorder.names() == ["connect"]
    assert [guild.id for guild in await state.get_guilds()] == [GUILD_ID]


@pytest.mark.asyncio
async def test_gateway_sequence_updates_the_stores(
    state: ConnectionState, recorder: Recorder
) -> None:
    await ready(state)
    await state._guilds.clear()

    await state.parsers["GUILD_CREATE"](guild_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    assert recorder.last("guild_available") == (guild,)

    await state.parsers["CHANNEL_CREATE"](channel_payload())
    channel = await guild.get_channel(CHANNEL_ID)
    assert channel is not None
    assert recorder.last("guild_channel_create") == (channel,)
    assert await state.get_channel(CHANNEL_ID) is channel

    message = payload(
        t.message.Message,
        id=str(MESSAGE_ID),
        channel_id=str(CHANNEL_ID),
        guild_id=str(GUILD_ID),
        author=user_payload(OTHER_USER_ID),
        content="hello",
        type=0,
        edited_timestamp=None,
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "thread",
        "poll",
    ):
        message.pop(key, None)
    await state.parsers["MESSAGE_CREATE"](message)
    cached = await state._get_message(MESSAGE_ID)
    assert cached is not None
    assert cached.content == "hello"
    assert channel.last_message_id == MESSAGE_ID  # type: ignore[union-attr]
    assert recorder.last("message") == (cached,)

    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="old"), "guild_id": str(GUILD_ID)}
    )
    member = await guild.get_member(OTHER_USER_ID)
    assert member is not None
    assert member.nick == "old"
    assert recorder.last("member_join") == (member,)

    update = payload(t.member.MemberUpdateEvent, nick="new", roles=[])
    update["guild_id"] = str(GUILD_ID)
    update["user"] = user_payload(OTHER_USER_ID)
    for key in ("avatar", "banner", "premium_since", "communication_disabled_until"):
        update.pop(key, None)
    update["joined_at"] = "2024-01-01T00:00:00+00:00"
    await state.parsers["GUILD_MEMBER_UPDATE"](update)
    before, after = recorder.last("member_update")
    assert before.nick == "old"
    assert after is member
    assert member.nick == "new"

    await state.parsers["MESSAGE_DELETE"](
        {
            "id": str(MESSAGE_ID),
            "channel_id": str(CHANNEL_ID),
            "guild_id": str(GUILD_ID),
        }
    )
    assert await state._get_message(MESSAGE_ID) is None
    assert recorder.last("message_delete") == (cached,)

    await state.parsers["GUILD_MEMBER_REMOVE"](
        {"guild_id": str(GUILD_ID), "user": user_payload(OTHER_USER_ID)}
    )
    assert await guild.get_member(OTHER_USER_ID) is None
    assert recorder.last("member_remove") == (member,)


@pytest.mark.asyncio
async def test_thread_events_update_the_guild_threads(
    state: ConnectionState, recorder: Recorder
) -> None:
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    await state.parsers["THREAD_CREATE"]({**thread_payload(), "newly_created": True})
    thread = await guild.get_thread(THREAD_ID)
    assert thread is not None
    assert recorder.last("thread_create") == (thread,)
    assert (
        USER_ID
        in await thread._state._store.bucket("thread_members", scope=thread.id).keys()
    )

    await state.parsers["THREAD_UPDATE"](thread_payload(name="renamed"))
    old, new = recorder.last("thread_update")
    assert new is thread
    assert thread.name == "renamed"
    assert old.name != "renamed"
    assert recorder.last("raw_thread_update")[0].thread is thread

    await state.parsers["THREAD_UPDATE"](thread_payload(name="renamed", archived=True))
    assert await guild.get_thread(THREAD_ID) is None

    await state.parsers["THREAD_CREATE"]({**thread_payload(), "newly_created": True})
    thread = await guild.get_thread(THREAD_ID)
    assert thread is not None
    await state.parsers["THREAD_DELETE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "parent_id": str(CHANNEL_ID),
            "type": 11,
        }
    )
    assert await guild.get_thread(THREAD_ID) is None
    assert recorder.last("thread_delete") == (thread,)


@pytest.mark.asyncio
async def test_guild_delete_clears_guild_and_messages(
    state: ConnectionState, recorder: Recorder
) -> None:
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    await state.parsers["GUILD_DELETE"]({"id": str(GUILD_ID)})

    assert await state._get_guild(GUILD_ID) is None
    assert recorder.last("guild_remove") == (guild,)


@pytest.mark.asyncio
async def test_events_for_unknown_guilds_are_discarded(
    state: ConnectionState, recorder: Recorder
) -> None:
    await ready(state)
    await state._guilds.clear()
    recorder.events.clear()

    await state.parsers["GUILD_ROLE_DELETE"](
        {"guild_id": str(GUILD_ID), "role_id": str(OTHER_USER_ID)}
    )
    await state.parsers["GUILD_MEMBER_UPDATE"](
        {"guild_id": str(GUILD_ID), "user": user_payload(), "roles": []}
    )
    await state.parsers["THREAD_DELETE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "parent_id": str(CHANNEL_ID),
            "type": 11,
        }
    )

    assert recorder.events == []
