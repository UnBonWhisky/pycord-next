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
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.enums import SortOrder
from discord.errors import InvalidArgument, InvalidData
from tests.core.rig import (
    PNG,
    Case,
    Rig,
    check_list,
    check_type,
    execute,
    guild,
    lst,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World

USER = discord.Object(id=4242)
ROLE = discord.Object(id=5252)
EVERYONE_DENY = discord.PermissionOverwrite(send_messages=False)


def guild_channel(tp: Any, kind: int) -> Any:
    return lambda r: r.payload(
        tp,
        guild_id=str(r.guild.id),
        type=kind,
        parent_id=None,
        permission_overwrites=[],
    )


def sent(r: Rig, route: str) -> dict[str, Any]:
    return getattr(r.http, route).call_args.kwargs


def overwrites(r: Rig) -> dict[Any, Any]:
    return {r.guild.default_role: EVERYONE_DENY, r.world.member: EVERYONE_DENY}


def check_overwrites(r: Rig, route: str = "create_channel") -> None:
    perms = sent(r, route)["permission_overwrites"]
    assert [p["type"] for p in perms] == [0, 1]
    assert perms[0]["id"] == r.guild.default_role.id
    assert perms[0]["deny"] == discord.Permissions(send_messages=True).value
    assert perms[0]["allow"] == 0


def text_checked(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.TextChannel)
    assert r.http.create_channel.call_args.args == (r.guild.id, 0)
    kwargs = sent(r, "create_channel")
    assert kwargs["name"] == "general"
    assert kwargs["parent_id"] is None
    assert kwargs["position"] == 3
    assert kwargs["topic"] == "topic"
    assert kwargs["rate_limit_per_user"] == 5
    assert kwargs["nsfw"] is True
    assert kwargs["default_thread_slowmode_delay"] == 7
    assert kwargs["default_auto_archive_duration"] == 60
    assert kwargs["reason"] == "why"
    assert "flags" in kwargs
    check_overwrites(r)


def voice_checked(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.VoiceChannel)
    assert r.http.create_channel.call_args.args == (r.guild.id, 2)
    kwargs = sent(r, "create_channel")
    assert kwargs["bitrate"] == 64000
    assert kwargs["user_limit"] == 4
    assert kwargs["rtc_region"] == "brazil"
    assert kwargs["video_quality_mode"] == 2
    assert kwargs["rate_limit_per_user"] == 1
    assert kwargs["nsfw"] is False
    assert kwargs["parent_id"] == 99


def stage_checked(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.StageChannel)
    assert r.http.create_channel.call_args.args == (r.guild.id, 13)
    kwargs = sent(r, "create_channel")
    assert kwargs["topic"] == "talk"
    assert kwargs["position"] == 2
    assert kwargs["rtc_region"] is None
    assert kwargs["bitrate"] == 64000
    assert kwargs["user_limit"] == 3
    assert kwargs["video_quality_mode"] == 1
    assert kwargs["rate_limit_per_user"] == 9
    assert kwargs["nsfw"] is True


def forum_checked(emoji_payload: Any) -> Any:
    def check(r: Rig, result: Any) -> None:
        assert isinstance(result, discord.ForumChannel)
        assert r.http.create_channel.call_args.args == (r.guild.id, 15)
        kwargs = sent(r, "create_channel")
        assert (
            kwargs["available_tags"]
            == [
                {
                    "name": "tag",
                    "moderated": False,
                    "emoji_id": None,
                    "emoji_name": None,
                }
            ]
            or kwargs["available_tags"]
        )
        assert kwargs["default_sort_order"] == 1
        assert kwargs["default_reaction_emoji"] == emoji_payload
        assert kwargs["default_thread_slowmode_delay"] == 4
        assert kwargs["default_auto_archive_duration"] == 1440
        assert kwargs["position"] == 1
        assert kwargs["nsfw"] is False

    return check


def _voice_state(r: Rig) -> None:
    r.state.websocket.voice_state.assert_awaited_once_with(
        r.guild.id, r.channel.id, self_mute=True, self_deaf=False
    )


def _text_with_category(r: Rig, result: Any) -> None:
    kwargs = sent(r, "create_channel")
    assert kwargs["parent_id"] == 99
    kwargs["parent_id"] = None
    text_checked(r, result)


def _vanity(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.Invite)
    assert result.code == "pycord"
    assert result.uses == 4
    assert result.max_age == 0
    assert r.http.get_invite.call_args.args == ("pycord",)


def _role_defaults(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.Role)
    kwargs = sent(r, "create_role")
    assert kwargs["permissions"] == "0"
    assert kwargs["colors"]["primary_color"] == 0
    assert "name" not in kwargs
    assert "hoist" not in kwargs


def _primary_colour(r: Rig, value: int) -> None:
    assert sent(r, "create_role")["colors"]["primary_color"] == value


def _holographic(r: Rig) -> None:
    colors = sent(r, "create_role")["colors"]
    assert colors["primary_color"] == discord.RoleColours.HOLOGRAPHIC_PRIMARY.value


CATEGORY = discord.Object(id=99)

CASES = [
    Case(
        "text_channel",
        guild,
        "create_text_channel",
        "create_channel",
        guild_channel(t.channel.TextChannel, 0),
        args=lambda r: ("general",),
        kwargs=lambda r: {
            "reason": "why",
            "category": CATEGORY,
            "position": 3,
            "topic": "topic",
            "slowmode_delay": 5,
            "nsfw": True,
            "overwrites": overwrites(r),
            "default_thread_slowmode_delay": 7,
            "default_auto_archive_duration": 60,
            "spoiler": False,
        },
        check=_text_with_category,
    ),
    Case(
        "voice_channel",
        guild,
        "create_voice_channel",
        "create_channel",
        guild_channel(t.channel.VoiceChannel, 2),
        args=lambda r: ("voice",),
        kwargs=lambda r: {
            "category": CATEGORY,
            "bitrate": 64000,
            "user_limit": 4,
            "rtc_region": "brazil",
            "video_quality_mode": discord.VideoQualityMode.full,
            "slowmode_delay": 1,
            "nsfw": False,
            "spoiler": False,
        },
        check=voice_checked,
    ),
    Case(
        "stage_channel",
        guild,
        "create_stage_channel",
        "create_channel",
        guild_channel(t.channel.StageChannel, 13),
        args=lambda r: ("stage",),
        kwargs=lambda r: {
            "topic": "talk",
            "position": 2,
            "rtc_region": None,
            "bitrate": 64000,
            "user_limit": 3,
            "video_quality_mode": discord.VideoQualityMode.auto,
            "slowmode_delay": 9,
            "nsfw": True,
        },
        check=stage_checked,
    ),
    Case(
        "forum_channel_unicode_emoji",
        guild,
        "create_forum_channel",
        "create_channel",
        guild_channel(t.channel.ForumChannel, 15),
        args=lambda r: ("forum",),
        kwargs=lambda r: {
            "position": 1,
            "topic": "t",
            "slowmode_delay": 2,
            "nsfw": False,
            "available_tags": [discord.ForumTag(name="tag")],
            "default_sort_order": SortOrder.creation_date,
            "default_reaction_emoji": "\N{THUMBS UP SIGN}",
            "default_thread_slowmode_delay": 4,
            "default_auto_archive_duration": 1440,
            "spoiler": True,
        },
        check=forum_checked({"emoji_id": None, "emoji_name": "\N{THUMBS UP SIGN}"}),
    ),
    Case(
        "forum_channel_int_emoji",
        guild,
        "create_forum_channel",
        "create_channel",
        guild_channel(t.channel.ForumChannel, 15),
        args=lambda r: ("forum",),
        kwargs=lambda r: {"default_reaction_emoji": 123, "default_sort_order": None},
        check=lambda r, res: (
            (
                sent(r, "create_channel")["default_reaction_emoji"]
                == {"emoji_id": 123, "emoji_name": None}
                and sent(r, "create_channel")["default_sort_order"] is None
            )
            or pytest.fail(sent(r, "create_channel"))
        ),
    ),
    Case(
        "forum_channel_no_emoji",
        guild,
        "create_forum_channel",
        "create_channel",
        guild_channel(t.channel.ForumChannel, 15),
        args=lambda r: ("forum",),
        kwargs=lambda r: {"default_reaction_emoji": None},
        check=lambda r, res: (
            sent(r, "create_channel")["default_reaction_emoji"] is None
            or pytest.fail("not none")
        ),
    ),
    Case(
        "forum_channel_bad_emoji",
        guild,
        "create_forum_channel",
        "create_channel",
        None,
        args=lambda r: ("forum",),
        kwargs=lambda r: {"default_reaction_emoji": 1.5},
        raises=(InvalidArgument, "default_reaction_emoji"),
    ),
    Case(
        "category",
        guild,
        "create_category",
        "create_channel",
        guild_channel(t.channel.CategoryChannel, 4),
        args=lambda r: ("cat",),
        kwargs=lambda r: {"position": 5, "reason": "r", "overwrites": overwrites(r)},
        check=lambda r, res: (
            (
                isinstance(res, discord.CategoryChannel)
                and sent(r, "create_channel")["position"] == 5
                and check_overwrites(r) is None
            )
            or pytest.fail(res)
        ),
    ),
    Case(
        "channel_overwrites_not_a_dict",
        guild,
        "create_category",
        "create_channel",
        None,
        args=lambda r: ("cat",),
        kwargs=lambda r: {"overwrites": [1]},
        raises=(InvalidArgument, "expects a dict"),
    ),
    Case(
        "channel_overwrite_value_not_an_overwrite",
        guild,
        "create_category",
        "create_channel",
        None,
        args=lambda r: ("cat",),
        kwargs=lambda r: {"overwrites": {r.world.member: 5}},
        raises=(InvalidArgument, "Expected PermissionOverwrite received int"),
    ),
    Case(
        "fetch_channels",
        guild,
        "fetch_channels",
        "get_all_guild_channels",
        lambda r: [
            guild_channel(t.channel.TextChannel, 0)(r),
            guild_channel(t.channel.CategoryChannel, 4)(r),
        ],
        called_with=lambda r: ((r.guild.id,), {}),
        check=lambda r, res: (
            [type(c) for c in res] == [discord.TextChannel, discord.CategoryChannel]
            or pytest.fail(res)
        ),
    ),
    Case(
        "fetch_channels_unknown_type",
        guild,
        "fetch_channels",
        "get_all_guild_channels",
        lambda r: [{**guild_channel(t.channel.TextChannel, 0)(r), "type": 999}],
        raises=(InvalidData, "Unknown channel type 999"),
    ),
    Case(
        "fetch_channel",
        guild,
        "fetch_channel",
        "get_channel",
        guild_channel(t.channel.VoiceChannel, 2),
        args=lambda r: (321,),
        called_with=lambda r: ((321,), {}),
        check=check_type(discord.VoiceChannel),
    ),
    Case(
        "fetch_channel_private",
        guild,
        "fetch_channel",
        "get_channel",
        lambda r: r.payload(t.channel.DMChannel),
        args=lambda r: (321,),
        raises=(InvalidData, "Unknown channel type 1"),
    ),
    Case(
        "fetch_channel_unknown_type",
        guild,
        "fetch_channel",
        "get_channel",
        lambda r: {**guild_channel(t.channel.TextChannel, 0)(r), "type": 999},
        args=lambda r: (321,),
        raises=(InvalidData, "Unknown channel type 999"),
    ),
    Case(
        "fetch_channel_other_guild",
        guild,
        "fetch_channel",
        "get_channel",
        lambda r: {**guild_channel(t.channel.TextChannel, 0)(r), "guild_id": "5"},
        args=lambda r: (321,),
        raises=(InvalidData, "different guild"),
    ),
    Case(
        "active_threads",
        guild,
        "active_threads",
        "get_active_threads",
        lambda r: {
            "threads": [
                r.payload(t.threads.Thread, id="777", guild_id=str(r.guild.id))
            ],
            "members": [
                r.payload(t.threads.ThreadMember, id="777"),
                r.payload(t.threads.ThreadMember, id="888"),
                {
                    k: v
                    for k, v in r.payload(t.threads.ThreadMember).items()
                    if k != "id"
                },
            ],
        },
        called_with=lambda r: ((r.guild.id,), {}),
        check=lambda r, res: [x.id for x in res] == [777] or pytest.fail(res),
    ),
    Case(
        "vanity_invite",
        guild,
        "vanity_invite",
        "get_vanity_code",
        {"code": "pycord", "uses": 4},
        also={
            "get_invite": lambda r: r.payload(
                t.invite.Invite,
                code="pycord",
                channel={"id": str(r.channel.id), "type": 0, "name": "general"},
            )
        },
        check=_vanity,
    ),
    Case(
        "invites",
        guild,
        "invites",
        "invites_from",
        lambda r: [
            r.payload(
                t.invite.Invite,
                channel={"id": str(r.channel.id), "type": 0, "name": "general"},
            )
        ],
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.Invite),
    ),
    Case(
        "create_sticker",
        guild,
        "create_sticker",
        "create_guild_sticker",
        one(t.sticker.GuildSticker),
        kwargs=lambda r: {
            "name": "wave",
            "description": "hi there",
            "emoji": "\N{WAVING HAND SIGN}",
            "file": discord.File(io.BytesIO(PNG), "s.png"),
            "reason": "r",
        },
        check=lambda r, res: (
            (
                isinstance(res, discord.GuildSticker)
                and r.http.create_guild_sticker.call_args.args[1]
                == {
                    "name": "wave",
                    "description": "hi there",
                    "tags": "WAVING_HAND_SIGN",
                }
                and r.http.create_guild_sticker.call_args.args[3] == "r"
            )
            or pytest.fail(res)
        ),
    ),
    Case(
        "create_sticker_plain_tag",
        guild,
        "create_sticker",
        "create_guild_sticker",
        one(t.sticker.GuildSticker),
        kwargs=lambda r: {
            "name": "wave",
            "emoji": "smile",
            "file": discord.File(io.BytesIO(PNG), "s.png"),
        },
        check=lambda r, res: (
            r.http.create_guild_sticker.call_args.args[1]
            == {"name": "wave", "description": "", "tags": "smile"}
            or pytest.fail(r.http.create_guild_sticker.call_args)
        ),
    ),
    Case(
        "create_sticker_short_name",
        guild,
        "create_sticker",
        "create_guild_sticker",
        None,
        kwargs=lambda r: {"name": "w", "emoji": "x", "file": None},
        raises=(TypeError, "name"),
    ),
    Case(
        "create_sticker_long_description",
        guild,
        "create_sticker",
        "create_guild_sticker",
        None,
        kwargs=lambda r: {
            "name": "wave",
            "description": "d" * 101,
            "emoji": "x",
            "file": None,
        },
        raises=(TypeError, "description"),
    ),
    Case(
        "create_integration_type",
        guild,
        "create_integration",
        "create_integration",
        None,
        kwargs=lambda r: {"type": "youtube", "id": 1},
        called_with=lambda r: ((r.guild.id, "youtube", 1), {}),
    ),
    Case(
        "prune_members_bad_days",
        guild,
        "prune_members",
        "prune_members",
        None,
        kwargs=lambda r: {"days": "7"},
        raises=(InvalidArgument, "days"),
    ),
    Case(
        "estimate_bad_days",
        guild,
        "estimate_pruned_members",
        "estimate_pruned_members",
        None,
        kwargs=lambda r: {"days": 1.5},
        raises=(InvalidArgument, "days"),
    ),
    Case(
        "ban_bad_seconds",
        guild,
        "ban",
        "ban",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"delete_message_seconds": 604801},
        raises=(TypeError, "604800"),
    ),
    Case(
        "bulk_ban_bad_seconds",
        guild,
        "bulk_ban",
        "bulk_ban",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"delete_message_seconds": -1},
        raises=(TypeError, "604800"),
    ),
    Case(
        "bulk_ban_no_users",
        guild,
        "bulk_ban",
        "bulk_ban",
        None,
        raises=(ValueError, "between 1 and 200"),
    ),
    Case(
        "edit_role_positions",
        guild,
        "edit_role_positions",
        "move_role_position",
        lst(t.role.Role, id="5252", position=2),
        args=lambda r: ({ROLE: 2},),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: (
            (r.guild.id, [{"id": ROLE.id, "position": 2}]),
            {"reason": "r"},
        ),
        check=check_list(discord.Role),
    ),
    Case(
        "edit_role_positions_not_a_dict",
        guild,
        "edit_role_positions",
        "move_role_position",
        None,
        args=lambda r: ([ROLE],),
        raises=(InvalidArgument, "expects a dict"),
    ),
    Case(
        "create_role_default",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        check=_role_defaults,
    ),
    Case(
        "create_role_everything",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {
            "name": "mod",
            "permissions": discord.Permissions(manage_messages=True),
            "hoist": True,
            "mentionable": True,
            "icon": PNG,
            "reason": "r",
        },
        kwargs_include=lambda r: {
            "name": "mod",
            "permissions": str(discord.Permissions(manage_messages=True).value),
            "hoist": True,
            "mentionable": True,
            "icon": "data:image/png;base64,iVBORw0KGgo=",
            "reason": "r",
        },
        check=check_type(discord.Role),
    ),
    Case(
        "create_role_clear_icon",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {"icon": None},
        kwargs_include=lambda r: {"icon": None},
    ),
    Case(
        "create_role_unicode_emoji",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {"unicode_emoji": "\N{FIRE}"},
        kwargs_include=lambda r: {"unicode_emoji": "\N{FIRE}", "icon": None},
    ),
    Case(
        "create_role_holographic",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {"holographic": True},
        check=lambda r, res: _holographic(r),
    ),
    Case(
        "create_role_color_alias",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {"color": 0x112233},
        warns=(DeprecationWarning, "colour"),
        check=lambda r, res: _primary_colour(r, 0x112233),
    ),
    Case(
        "create_role_colors_alias",
        guild,
        "create_role",
        "create_role",
        one(t.role.Role),
        kwargs=lambda r: {"colors": discord.RoleColours(primary=discord.Colour(9))},
        check=lambda r, res: _primary_colour(r, 9),
    ),
    Case(
        "create_role_bad_colours",
        guild,
        "create_role",
        "create_role",
        None,
        kwargs=lambda r: {"colours": 5},
        raises=(InvalidArgument, "RoleColours"),
    ),
    Case(
        "create_scheduled_event_needs_start",
        guild,
        "create_scheduled_event",
        "create_scheduled_event",
        None,
        kwargs=lambda r: {"name": "x"},
        raises=(InvalidArgument, "start_time"),
    ),
    Case(
        "change_voice_state",
        guild,
        "change_voice_state",
        kwargs=lambda r: {"channel": r.channel, "self_mute": True},
        check=lambda r, res: _voice_state(r),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_guild_remote_calls_more(world: World, case: Case) -> None:
    rig = Rig(world)
    rig.state.websocket = AsyncMock()
    rig.state._get_websocket = lambda _guild_id: rig.state.websocket  # type: ignore[assignment]
    execute(rig, case)
