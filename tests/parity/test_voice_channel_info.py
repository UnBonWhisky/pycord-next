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

"""Voice channel info and start time (upstream #3210)."""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
from typing import TYPE_CHECKING, Any

import pytest

from discord import Client, StageChannel, VoiceChannel
from discord.raw_models import ChannelInfo, RawVoiceChannelStartTimeUpdateEvent
from discord.state import AutoShardedConnectionState
from tests.state.conftest import build_state
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    OTHER_USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    ready,
    user_payload,
)

if TYPE_CHECKING:
    from discord.guild import Guild
    from discord.http import HTTPClient
    from discord.state import ConnectionState

VOICE_ID = CHANNEL_ID + 100
STAGE_ID = CHANNEL_ID + 101
START = 1_700_000_000
BOTH = ("status", "voice_start_time")


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[int, tuple[str, ...]]] = []
        self.sent = asyncio.Event()

    async def request_channel_info(self, guild_id: int, fields: Any) -> None:
        self.requests.append((guild_id, tuple(fields)))
        self.sent.set()


def voice_payload(channel_id: int, kind: int, **fields: Any) -> dict[str, Any]:
    return {
        "id": str(channel_id),
        "guild_id": str(GUILD_ID),
        "type": kind,
        "name": "voice",
        "position": 0,
        "permission_overwrites": [],
        "nsfw": False,
        "parent_id": None,
        "bitrate": 64000,
        "user_limit": 0,
        **fields,
    }


async def setup(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, kind: str, **options: Any
) -> tuple[ConnectionState, Recorder, FakeTransport]:
    state = build_state(loop, http, kind, cache_default_sounds=False, **options)
    recorder = Recorder()
    state.dispatch = recorder
    transport = FakeTransport()
    state._get_websocket = lambda *_args, **_kwargs: transport  # type: ignore[assignment]
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())
    await state.parsers["CHANNEL_CREATE"](voice_payload(VOICE_ID, 2, status="old"))
    await state.parsers["CHANNEL_CREATE"](voice_payload(STAGE_ID, 13))
    return state, recorder, transport


async def cached_voice(
    state: ConnectionState,
) -> tuple[Guild, VoiceChannel, StageChannel]:
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    voice = await guild.get_channel(VOICE_ID)
    stage = await guild.get_channel(STAGE_ID)
    assert isinstance(voice, VoiceChannel)
    assert isinstance(stage, StageChannel)
    return guild, voice, stage


def queue_ready_guild(state: ConnectionState, guild: Guild) -> None:
    queue: asyncio.Queue[Guild] = asyncio.Queue()
    queue.put_nowait(guild)
    state._ready_state = queue  # pyright: ignore[reportAttributeAccessIssue]


async def respond(state: ConnectionState, transport: FakeTransport) -> None:
    await asyncio.wait_for(transport.sent.wait(), timeout=5)
    await state.parsers["CHANNEL_INFO"](
        {
            "guild_id": str(GUILD_ID),
            "channels": [
                {"id": str(VOICE_ID), "status": "live", "voice_start_time": START},
                {"id": str(STAGE_ID), "voice_start_time": START + 5},
                {"id": str(CHANNEL_ID), "status": "ignored"},
            ],
        }
    )


@pytest.fixture(params=["memory", "redis"])
def backend_kind(request: pytest.FixtureRequest) -> str:
    return request.param


async def test_channels_start_without_status_and_start_time(
    http: HTTPClient, backend_kind: str
) -> None:
    state, _, _ = await setup(asyncio.get_running_loop(), http, backend_kind)
    _, voice, stage = await cached_voice(state)

    assert voice.status == "old"
    assert voice.voice_start_time is None
    assert stage.status is None
    assert stage.voice_start_time is None


async def test_request_channel_info_updates_the_cache(
    http: HTTPClient, backend_kind: str
) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, backend_kind)
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    result, _ = await asyncio.gather(
        guild.request_channel_info(), respond(state, transport)
    )

    assert transport.requests == [(GUILD_ID, BOTH)]
    assert result is not None
    assert [info.id for info in result] == [VOICE_ID, STAGE_ID, CHANNEL_ID]
    assert all(isinstance(info, ChannelInfo) for info in result)
    assert result[0].voice_start_time == START
    _, voice, stage = await cached_voice(state)
    assert voice.status == "live"
    assert voice.voice_start_time == dt.datetime.fromtimestamp(
        START, tz=dt.timezone.utc
    )
    assert stage.voice_start_time == dt.datetime.fromtimestamp(
        START + 5, tz=dt.timezone.utc
    )
    assert state._channel_info_requests == {}


async def test_request_channel_info_without_cache_leaves_channels_untouched(
    http: HTTPClient,
) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    result, _ = await asyncio.gather(
        guild.request_channel_info(cache=False), respond(state, transport)
    )

    assert result is not None
    assert len(result) == 3
    _, voice, stage = await cached_voice(state)
    assert voice.status == "old"
    assert voice.voice_start_time is None
    assert stage.voice_start_time is None


async def test_only_the_requested_fields_are_cached(http: HTTPClient) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    await asyncio.gather(
        guild.request_channel_info(fields=["voice_start_time"]),
        respond(state, transport),
    )

    assert transport.requests == [(GUILD_ID, ("voice_start_time",))]
    _, voice, _ = await cached_voice(state)
    assert voice.status == "old"
    assert voice.voice_start_time is not None


async def test_identical_requests_share_one_gateway_request(http: HTTPClient) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    first, second, _ = await asyncio.gather(
        guild.request_channel_info(),
        guild.request_channel_info(),
        respond(state, transport),
    )

    assert len(transport.requests) == 1
    assert first is second


async def test_cancelled_request_is_discarded(http: HTTPClient) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(guild.request_channel_info(), timeout=0.05)

    assert transport.requests == [(GUILD_ID, BOTH)]
    assert state._channel_info_requests == {}


async def test_request_channel_info_is_none_for_an_evicted_guild(
    http: HTTPClient,
) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    await state._guilds.clear()

    assert await guild.request_channel_info() is None
    assert transport.requests == []


async def test_unsolicited_channel_info_is_ignored(http: HTTPClient) -> None:
    state, _, _ = await setup(asyncio.get_running_loop(), http, "memory")

    await state.parsers["CHANNEL_INFO"](
        {
            "guild_id": str(GUILD_ID),
            "channels": [{"id": str(VOICE_ID), "status": "live"}],
        }
    )

    _, voice, _ = await cached_voice(state)
    assert voice.status == "old"


async def test_start_time_update_event(http: HTTPClient, backend_kind: str) -> None:
    state, recorder, _ = await setup(asyncio.get_running_loop(), http, backend_kind)

    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](
        {
            "id": str(VOICE_ID),
            "guild_id": str(GUILD_ID),
            "voice_start_time": START,
        }
    )

    raw = recorder.last("raw_voice_channel_start_time_update")[0]
    assert isinstance(raw, RawVoiceChannelStartTimeUpdateEvent)
    assert raw.id == VOICE_ID
    assert raw.guild_id == GUILD_ID
    assert raw.voice_start_time == dt.datetime.fromtimestamp(START, tz=dt.timezone.utc)
    channel, before, after = recorder.last("voice_channel_start_time_update")
    assert channel.id == VOICE_ID
    assert before is None
    assert after == raw.voice_start_time
    _, voice, _ = await cached_voice(state)
    assert voice.voice_start_time == after

    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](
        {"id": str(VOICE_ID), "guild_id": str(GUILD_ID), "voice_start_time": None}
    )

    _, before, after = recorder.last("voice_channel_start_time_update")
    assert before == raw.voice_start_time
    assert after is None
    assert (
        recorder.last("raw_voice_channel_start_time_update")[0].voice_start_time is None
    )


async def test_start_time_update_for_unknown_channels_only_dispatches_raw(
    http: HTTPClient,
) -> None:
    state, recorder, _ = await setup(asyncio.get_running_loop(), http, "memory")

    for channel_id in (CHANNEL_ID, CHANNEL_ID + 999):
        await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](
            {"id": str(channel_id), "guild_id": str(GUILD_ID), "voice_start_time": 1}
        )

    assert recorder.names() == [
        name for name in recorder.names() if name != "voice_channel_start_time_update"
    ]
    assert recorder.names().count("raw_voice_channel_start_time_update") == 2


async def test_status_update_still_updates_the_status(
    http: HTTPClient, backend_kind: str
) -> None:
    state, recorder, _ = await setup(asyncio.get_running_loop(), http, backend_kind)

    await state.parsers["VOICE_CHANNEL_STATUS_UPDATE"](
        {"id": str(VOICE_ID), "guild_id": str(GUILD_ID), "status": "new"}
    )
    assert recorder.last("voice_channel_status_update")[1:] == ("old", "new")

    await state.parsers["VOICE_CHANNEL_STATUS_UPDATE"](
        {"id": str(VOICE_ID), "guild_id": str(GUILD_ID), "status": None}
    )
    _, voice, _ = await cached_voice(state)
    assert voice.status is None


async def test_channel_update_keeps_the_start_time(http: HTTPClient) -> None:
    state, _, _ = await setup(asyncio.get_running_loop(), http, "memory")
    await state.parsers["VOICE_CHANNEL_START_TIME_UPDATE"](
        {"id": str(VOICE_ID), "guild_id": str(GUILD_ID), "voice_start_time": START}
    )

    await state.parsers["CHANNEL_UPDATE"](voice_payload(VOICE_ID, 2, name="renamed"))

    _, voice, _ = await cached_voice(state)
    assert voice.name == "renamed"
    assert voice.voice_start_time is not None


async def test_cache_channel_info_requests_every_guild_on_ready(
    http: HTTPClient,
) -> None:
    state, _, transport = await setup(
        asyncio.get_running_loop(), http, "memory", cache_channel_info=True
    )
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    state.guild_ready_timeout = 0.05
    queue_ready_guild(state, guild)
    ready_task = asyncio.ensure_future(state._delay_ready())

    await respond(state, transport)
    await asyncio.wait_for(ready_task, timeout=5)

    assert transport.requests == [(GUILD_ID, BOTH)]
    _, voice, _ = await cached_voice(state)
    assert voice.status == "live"
    assert voice.voice_start_time is not None


async def test_channel_info_is_not_requested_by_default(http: HTTPClient) -> None:
    state, _, transport = await setup(asyncio.get_running_loop(), http, "memory")
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    state.guild_ready_timeout = 0.05
    queue_ready_guild(state, guild)

    await asyncio.wait_for(state._delay_ready(), timeout=5)

    assert transport.requests == []
    assert state.cache_channel_info is False


def test_client_documents_the_option() -> None:
    assert "cache_channel_info" in (inspect.getdoc(Client) or "")


def test_raw_models_keep_the_gateway_values() -> None:
    info = ChannelInfo({"id": "5"})
    assert (info.id, info.status, info.voice_start_time) == (5, None, None)
    info = ChannelInfo({"id": "5", "status": "x", "voice_start_time": 3})
    assert (info.status, info.voice_start_time) == ("x", 3)


async def test_auto_sharded_state_requests_channel_info(http: HTTPClient) -> None:
    state = AutoShardedConnectionState(
        dispatch=Recorder(),
        handlers={},
        hooks={},
        http=http,
        loop=asyncio.get_running_loop(),
        cache_channel_info=True,
        cache_default_sounds=False,
    )
    transport = FakeTransport()
    state._get_websocket = lambda *_args, **_kwargs: transport  # type: ignore[assignment]
    state.shard_count = 1
    state.shard_ids = [0]
    state.shards_launched.set()
    await state.parsers["READY"](
        {
            "user": {**user_payload(), "bot": True},
            "guilds": [{"id": str(GUILD_ID), "unavailable": True}],
            "application": {"id": str(OTHER_USER_ID), "flags": 0},
            "__shard_id__": 0,
        }
    )
    assert state._ready_task is not None
    state._ready_task.cancel()
    state._ready_task = None
    del state._ready_state
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](voice_payload(VOICE_ID, 2))
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    state.guild_ready_timeout = 0.05
    queue_ready_guild(state, guild)
    ready_task = asyncio.ensure_future(state._delay_ready())

    await respond(state, transport)
    await asyncio.wait_for(ready_task, timeout=5)

    assert transport.requests == [(GUILD_ID, BOTH)]
    voice = await guild.get_channel(VOICE_ID)
    assert isinstance(voice, VoiceChannel)
    assert voice.status == "live"
