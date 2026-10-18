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


"""Guild channel parity: obfuscation, spoiler channels and guild features."""

from __future__ import annotations

import asyncio
import warnings
from typing import TYPE_CHECKING, Any, get_args

import pytest

from discord import ChannelFlags, GatewayCapabilities, StageChannel, TextChannel
from discord.types.guild import GuildFeature
from tests.commands.interaction_support import interaction_payload, make_interaction
from tests.state.conftest import build_state
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    Recorder,
    channel_payload,
    guild_payload,
    ready,
)

if TYPE_CHECKING:
    from discord.http import HTTPClient
    from discord.state import ConnectionState
    from tests.models.context import World

HIDDEN = "___hidden___"
OBFUSCATED = 1 << 17
SPOILER = 1 << 21

DOCUMENTED_FEATURES = (
    "ANIMATED_BANNER",
    "ANIMATED_ICON",
    "APPLICATION_COMMAND_PERMISSIONS_V2",
    "AUTO_MODERATION",
    "BANNER",
    "COMMUNITY",
    "CREATOR_MONETIZABLE_PROVISIONAL",
    "CREATOR_STORE_PAGE",
    "DEVELOPER_SUPPORT_SERVER",
    "DISCOVERABLE",
    "ENHANCED_ROLE_COLORS",
    "FEATURABLE",
    "GUILD_TAGS",
    "GUESTS_ENABLED",
    "INVITES_DISABLED",
    "INVITE_SPLASH",
    "MEMBER_VERIFICATION_GATE_ENABLED",
    "MORE_SOUNDBOARD",
    "MORE_STICKERS",
    "NEWS",
    "PARTNERED",
    "PREVIEW_ENABLED",
    "PRUNE_REQUIRES_ADMIN",
    "RAID_ALERTS_DISABLED",
    "ROLE_ICONS",
    "ROLE_SUBSCRIPTIONS_AVAILABLE_FOR_PURCHASE",
    "ROLE_SUBSCRIPTIONS_ENABLED",
    "SOUNDBOARD",
    "TICKETED_EVENTS_ENABLED",
    "VANITY_URL",
    "VERIFIED",
    "VIP_REGIONS",
    "WELCOME_SCREEN_ENABLED",
)


@pytest.fixture(params=["memory", "redis"])
def backend_kind(request: pytest.FixtureRequest) -> str:
    return request.param


def text_payload(channel_id: int = CHANNEL_ID, **fields: Any) -> dict[str, Any]:
    return {**channel_payload(), "id": str(channel_id), **fields}


async def setup(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, kind: str
) -> tuple[ConnectionState, Recorder]:
    state = build_state(loop, http, kind, cache_default_sounds=False)
    recorder = Recorder()
    state.dispatch = recorder
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    return state, recorder


def test_guild_features_cover_the_documented_table() -> None:
    assert set(DOCUMENTED_FEATURES) <= set(get_args(GuildFeature))


def test_channel_obfuscated_flag_keeps_the_old_name_as_an_alias() -> None:
    assert ChannelFlags.channel_obfuscated.flag == OBFUSCATED
    assert ChannelFlags.obfuscated.flag == OBFUSCATED
    flags = ChannelFlags._from_value(OBFUSCATED)
    assert flags.channel_obfuscated
    assert flags.obfuscated
    assert ChannelFlags(obfuscated=True).value == OBFUSCATED
    assert ChannelFlags(channel_obfuscated=True).value == OBFUSCATED
    assert "obfuscated" not in dict(flags)
    assert dict(flags)["channel_obfuscated"] is True


def test_channel_obfuscation_capability_keeps_the_old_name_as_an_alias() -> None:
    assert GatewayCapabilities.channel_obfuscation.flag == 1 << 15
    assert GatewayCapabilities.obfuscated_channels.flag == 1 << 15
    assert GatewayCapabilities(obfuscated_channels=True).channel_obfuscation
    assert GatewayCapabilities(channel_obfuscation=True).value == 1 << 15


def test_spoiler_channel_flag() -> None:
    assert ChannelFlags.is_spoiler_channel.flag == SPOILER
    assert ChannelFlags.spoiler.flag == SPOILER
    assert ChannelFlags(spoiler=True).is_spoiler_channel
    assert "spoiler" not in dict(ChannelFlags())


async def test_obfuscated_channel_is_replaced_when_access_is_regained(
    http: HTTPClient, backend_kind: str
) -> None:
    state, recorder = await setup(asyncio.get_running_loop(), http, backend_kind)
    await state.parsers["CHANNEL_CREATE"](
        text_payload(name=HIDDEN, flags=OBFUSCATED, topic=None)
    )
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    hidden = await guild.get_channel(CHANNEL_ID)
    assert isinstance(hidden, TextChannel)
    assert hidden.obfuscated
    assert str(hidden) == f"Obfuscated Channel ({CHANNEL_ID})"
    assert hidden.id == CHANNEL_ID

    await state.parsers["CHANNEL_UPDATE"](text_payload(name="general", flags=0))
    visible = await guild.get_channel(CHANNEL_ID)
    assert isinstance(visible, TextChannel)
    assert not visible.obfuscated
    assert str(visible) == "general"
    before, after = recorder.last("guild_channel_update")
    assert before.obfuscated
    assert not after.obfuscated


async def test_http_omission_does_not_evict_the_cached_stub(
    http: HTTPClient,
) -> None:
    state, _ = await setup(asyncio.get_running_loop(), http, "memory")
    await state.parsers["CHANNEL_CREATE"](text_payload(name=HIDDEN, flags=OBFUSCATED))
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    async def omit(_guild_id: int) -> list[Any]:
        return []

    state.http.get_all_guild_channels = omit  # pyright: ignore[reportAttributeAccessIssue]
    assert await guild.fetch_channels() == []
    stub = await guild.get_channel(CHANNEL_ID)
    assert stub is not None
    assert stub.obfuscated


def interaction_for(world: World) -> Any:
    payload = interaction_payload(world)
    payload["channel"]["flags"] = 0
    return make_interaction(world, payload)


def test_interaction_channel_is_not_replaced_by_an_obfuscated_cached_stub(
    world: World,
) -> None:
    world.channel.flags = ChannelFlags._from_value(OBFUSCATED)
    interaction = interaction_for(world)
    assert interaction.channel is not world.channel
    assert interaction.channel.id == world.channel.id
    assert not interaction.channel.obfuscated
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert interaction.cached_channel is interaction.channel


def test_interaction_channel_is_still_the_cached_one(world: World) -> None:
    world.channel.flags = ChannelFlags._from_value(0)
    interaction = interaction_for(world)
    assert interaction.channel is world.channel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert interaction.cached_channel is world.channel


class Capture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, route: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((route.method, route.path, kwargs.get("json", {})))
        return {**channel_payload(), **kwargs.get("json", {}), "id": "1"}


async def guild_with_capture(http: HTTPClient) -> tuple[Any, Capture]:
    state, _ = await setup(asyncio.get_running_loop(), http, "memory")
    capture = Capture()
    http.request = capture.request  # pyright: ignore[reportAttributeAccessIssue]
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    return guild, capture


@pytest.mark.parametrize("name", ["create_text_channel", "create_voice_channel"])
@pytest.mark.parametrize("spoiler", [True, False])
async def test_create_sends_the_spoiler_flag(
    http: HTTPClient, name: str, spoiler: bool
) -> None:
    guild, capture = await guild_with_capture(http)
    await getattr(guild, name)("name", spoiler=spoiler)
    method, path, payload = capture.calls[0]
    assert (method, path) == ("POST", "/guilds/{guild_id}/channels")
    assert payload["flags"] == (SPOILER if spoiler else 0)


async def test_create_forum_sends_the_spoiler_flag_and_documented_keys(
    http: HTTPClient,
) -> None:
    guild, capture = await guild_with_capture(http)
    await guild.create_forum_channel(
        "forum",
        spoiler=True,
        default_thread_slowmode_delay=5,
        default_auto_archive_duration=60,
    )
    payload = capture.calls[0][2]
    assert payload["flags"] == SPOILER
    assert payload["default_thread_rate_limit_per_user"] == 5
    assert payload["default_auto_archive_duration"] == 60


async def test_create_without_spoiler_sends_no_flags(http: HTTPClient) -> None:
    guild, capture = await guild_with_capture(http)
    await guild.create_text_channel("name")
    assert "flags" not in capture.calls[0][2]


async def test_create_warns_when_spoiler_and_nsfw_are_both_set(
    http: HTTPClient,
) -> None:
    guild, _ = await guild_with_capture(http)
    with pytest.warns(UserWarning, match="spoiler channel cannot be NSFW"):
        await guild.create_text_channel("name", spoiler=True, nsfw=True)


async def test_stage_channels_have_no_spoiler_option() -> None:
    assert not hasattr(StageChannel, "spoiler")
    assert hasattr(TextChannel, "spoiler")


async def test_edit_sets_the_spoiler_flag_and_keeps_other_flags(
    world: World,
) -> None:
    capture = Capture()
    world.state.http.request = capture.request
    world.channel.flags = ChannelFlags._from_value(1 << 4)
    assert not world.channel.spoiler

    await world.channel.edit(spoiler=True)
    assert capture.calls[0][2]["flags"] == (1 << 4) | SPOILER

    world.channel.flags = ChannelFlags._from_value(SPOILER)
    assert world.channel.spoiler
    await world.channel.edit(spoiler=False)
    assert capture.calls[1][2]["flags"] == 0


async def test_edit_warns_when_spoiler_and_nsfw_are_both_set(world: World) -> None:
    capture = Capture()
    world.state.http.request = capture.request
    with pytest.warns(UserWarning, match="spoiler channel cannot be NSFW"):
        await world.channel.edit(spoiler=True, nsfw=True)
    assert capture.calls[0][2]["nsfw"] is True
