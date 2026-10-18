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

"""Application flags_new, Rich Presence URLs, display name styles and invite creation."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from discord import (
    Activity,
    Colour,
    Member,
    StatusDisplayType,
    TextChannel,
    User,
    types as t,
)
from discord.activity import create_activity
from discord.appinfo import AppInfo
from discord.file import File
from discord.http import HTTPClient
from discord.user import DisplayNameStyles

if TYPE_CHECKING:
    from tests.models.context import World


def app_info(world: World, **fields: object) -> AppInfo:
    payload = world.payload(t.appinfo.AppInfo)
    payload.pop("flags_new", None)
    payload.update(fields)
    return AppInfo(world.state, payload)  # pyright: ignore[reportArgumentType]


def test_flags_new_wins_over_flags(world: World) -> None:
    info = app_info(world, flags=1 << 12, flags_new=str((1 << 12) | (1 << 40)))
    assert info.flags.value == (1 << 12) | (1 << 40)


def test_flags_without_flags_new(world: World) -> None:
    assert app_info(world, flags=1 << 12).flags.value == 1 << 12


def test_activity_urls() -> None:
    activity = Activity(
        name="n",
        type=0,
        state="s",
        state_url="https://example.com/state",
        details="d",
        details_url="https://example.com/details",
        assets={
            "large_image": "a",
            "large_url": "https://example.com/large",
            "small_image": "b",
            "small_url": "https://example.com/small",
        },
    )
    assert activity.state_url == "https://example.com/state"
    assert activity.details_url == "https://example.com/details"
    assert activity.large_url == "https://example.com/large"
    assert activity.small_url == "https://example.com/small"
    data = activity.to_dict()
    assert data["state_url"] == "https://example.com/state"
    assert data["details_url"] == "https://example.com/details"
    assert Activity(name="n").state_url is None
    assert Activity(name="n").large_url is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, "name"), (1, "state"), (2, "details")],
)
def test_activity_status_display_type(raw: int, expected: str) -> None:
    activity = Activity(name="n", type=2, status_display_type=raw)
    assert activity.status_display_type is StatusDisplayType[expected]
    assert int(activity.status_display_type) == raw
    assert activity.to_dict()["status_display_type"] == raw
    rebuilt = create_activity(activity.to_dict())
    assert isinstance(rebuilt, Activity)
    assert rebuilt.status_display_type is StatusDisplayType[expected]


def test_activity_status_display_type_defaults_and_unknown() -> None:
    assert Activity(name="n").status_display_type is None
    assert "status_display_type" not in Activity(name="n").to_dict()
    assert Activity(name="n", status_display_type=None).status_display_type is None
    unknown = Activity(name="n", status_display_type=9).status_display_type
    assert unknown is not None
    assert int(unknown) == 9
    given = Activity(name="n", status_display_type=StatusDisplayType.details)
    assert given.status_display_type is StatusDisplayType.details


def test_member_exposes_the_display_name_styles_of_its_user(world: World) -> None:
    payload = world.payload(
        t.member.MemberWithUser,
        user={
            **world.payload(t.user.User),
            "display_name_styles": {"colors": [255], "effect_id": 4, "font_id": 3},
        },
    )
    payload.pop("communication_disabled_until", None)
    member = Member(data=payload, guild=world.guild, state=world.state)
    styles = member.display_name_styles
    assert isinstance(styles, DisplayNameStyles)
    assert styles == member._user.display_name_styles
    assert styles.colours == [Colour(255)]
    payload["user"]["display_name_styles"] = None
    assert (
        Member(data=payload, guild=world.guild, state=world.state).display_name_styles
        is None
    )


def test_display_name_styles(world: World) -> None:
    payload = world.payload(
        t.user.User,
        display_name_styles={"colors": [16777215, 255], "effect_id": 4, "font_id": 3},
    )
    user = User(state=world.state, data=payload)
    styles = user.display_name_styles
    assert isinstance(styles, DisplayNameStyles)
    assert styles.colours == [Colour(16777215), Colour(255)]
    assert styles.colors == styles.colours
    assert (styles.effect_id, styles.font_id) == (4, 3)
    assert User._copy(user).display_name_styles == styles
    payload["display_name_styles"] = None
    assert User(state=world.state, data=payload).display_name_styles is None
    del payload["display_name_styles"]
    assert User(state=world.state, data=payload).display_name_styles is None


async def test_create_invite_target_user_ids(world: World) -> None:
    http = Mock()
    http.create_invite = AsyncMock(
        return_value={"code": "abc", "channel": {"id": "1", "name": "n", "type": 0}}
    )
    world.state.http = http
    channel: TextChannel = world.channel
    await channel.create_invite(target_user_ids=[1, 2, 3])
    assert http.create_invite.await_args.kwargs["target_user_ids"] == [1, 2, 3]
    await channel.create_invite()
    assert http.create_invite.await_args.kwargs["target_user_ids"] is None


async def test_create_invite_route_payload() -> None:
    http = HTTPClient()
    recorder = AsyncMock(return_value={})
    http.request = recorder  # pyright: ignore[reportAttributeAccessIssue]
    await http.create_invite(5, target_user_ids=[1, 2])
    assert recorder.await_args.kwargs["json"]["target_user_ids"] == ["1", "2"]
    await http.create_invite(5)
    assert "target_user_ids" not in recorder.await_args.kwargs["json"]
    with pytest.raises(TypeError):
        await http.create_invite(
            5, target_user_ids=[1], target_users_file=File(BytesIO(b"x"))
        )
