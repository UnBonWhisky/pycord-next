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

"""Dynamic voice regions (upstream #3347)."""

from __future__ import annotations

import dataclasses
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from discord import Client, Guild, PartialGuild, VoiceRegion, VoiceServerRegion
from discord.enums import VoiceRegion as Enum, try_enum
from tests.state.test_parsers import GUILD_ID, guild_payload

if TYPE_CHECKING:
    from discord.http import HTTPClient
    from discord.state import ConnectionState

REGIONS = [
    {
        "id": "us-west",
        "name": "US West",
        "optimal": True,
        "deprecated": False,
        "custom": False,
    },
    {
        "id": "vip-us-east",
        "name": "VIP US East",
        "optimal": False,
        "deprecated": True,
        "custom": True,
    },
]


@pytest.fixture
def requests(http: HTTPClient) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    async def request(route: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        seen.append((route.method, route.path))
        return REGIONS

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    return seen


async def test_routes(http: HTTPClient, requests: list[tuple[str, str]]) -> None:
    assert await http.get_voice_regions() == REGIONS
    assert await http.get_guild_voice_regions(GUILD_ID) == REGIONS
    assert requests == [
        ("GET", "/voice/regions"),
        ("GET", "/guilds/{guild_id}/regions"),
    ]


def expected() -> list[VoiceServerRegion]:
    return [
        VoiceServerRegion("us-west", "US West", True, False, False),
        VoiceServerRegion("vip-us-east", "VIP US East", False, True, True),
    ]


async def test_client_fetch_voice_regions(
    http: HTTPClient, requests: list[tuple[str, str]]
) -> None:
    client = Client()
    client.http = http
    assert await client.fetch_voice_regions() == expected()
    assert requests == [("GET", "/voice/regions")]


async def test_guild_fetch_voice_regions(
    state: ConnectionState, requests: list[tuple[str, str]]
) -> None:
    guild = Guild(data=guild_payload(), state=state)  # pyright: ignore[reportArgumentType]
    assert await guild.fetch_voice_regions() == expected()
    assert requests == [("GET", "/guilds/{guild_id}/regions")]


async def test_partial_guild_fetch_voice_regions(
    state: ConnectionState, requests: list[tuple[str, str]]
) -> None:
    guild = PartialGuild(state=state, id=GUILD_ID)
    assert await guild.fetch_voice_regions() == expected()
    assert requests == [("GET", "/guilds/{guild_id}/regions")]


def test_voice_server_region_is_immutable_and_slotted() -> None:
    region = expected()[0]
    assert dataclasses.is_dataclass(region)
    assert not hasattr(region, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        region.id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["str", "enum", "none"])
async def test_rtc_region_accepts_strings_and_the_enum(
    state: ConnectionState, http: HTTPClient, kind: str
) -> None:
    sent: list[dict[str, Any]] = []

    async def create_channel(
        _guild_id: int, _kind: int, **options: Any
    ) -> dict[str, Any]:
        sent.append(options)
        return {
            "id": "2",
            "guild_id": str(GUILD_ID),
            "type": 2,
            "name": "voice",
            "position": 0,
            "permission_overwrites": [],
            "nsfw": False,
            "parent_id": None,
            "rtc_region": options.get("rtc_region"),
        }

    http.create_channel = create_channel  # pyright: ignore[reportAttributeAccessIssue]
    guild = Guild(data=guild_payload(), state=state)  # pyright: ignore[reportArgumentType]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        region = {"str": "brazil-new", "enum": VoiceRegion.us_west, "none": None}[kind]
        await guild.create_voice_channel("voice", rtc_region=region)

    assert sent[0]["rtc_region"] == (None if region is None else str(region))


def test_every_voice_region_member_is_kept() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        members = {m.name: m.value for m in VoiceRegion}
        assert members["vip_amsterdam"] == "vip-amsterdam"
        assert members["europe"] == "europe"
        assert members["south_korea"] == "south-korea"
        assert members["rotterdam"] == "rotterdam"
        assert VoiceRegion.us_west.value == "us-west"
        assert VoiceRegion("brazil") is VoiceRegion.brazil
        assert VoiceRegion["hongkong"] is VoiceRegion.hongkong
        assert str(VoiceRegion.us_east) == "us-east"


@pytest.mark.parametrize(
    "access",
    [
        lambda: VoiceRegion.us_west,
        lambda: VoiceRegion["us_west"],
        lambda: VoiceRegion("us-west"),
    ],
    ids=["attribute", "item", "call"],
)
def test_direct_access_warns(access: Any) -> None:
    with pytest.warns(DeprecationWarning, match="VoiceRegion"):
        access()


def test_unknown_member_is_still_an_attribute_error() -> None:
    with pytest.raises(AttributeError):
        VoiceRegion.does_not_exist  # noqa: B018


def test_internal_paths_do_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert try_enum(Enum, "us-west").value == "us-west"
        unknown = try_enum(Enum, "brand-new")
        assert (unknown.value, str(unknown)) == ("brand-new", "brand-new")
        assert isinstance(unknown, Enum)
        assert Enum.__members__["us_west"].value == "us-west"
        assert Enum.try_value("us-west").name == "us_west"
