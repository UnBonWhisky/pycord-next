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

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.enums import ChannelType, SortOrder
from discord.errors import ClientException, InvalidArgument
from tests.core.rig import Case, Rig, check_type, execute
from tests.core.test_channel_remote import (
    CHANNEL_TYPES,
    channel_of,
    channel_payload,
    make_channel,
)
from tests.voice.deps import requires_voice

if TYPE_CHECKING:
    from tests.models.context import World


@pytest.mark.parametrize("kind", list(CHANNEL_TYPES))
def test_edit_returns_a_new_channel_of_the_same_class(world: World, kind: str) -> None:
    rig = Rig(world)
    channel = channel_of(kind)(rig)
    rig.respond("edit_channel", channel_payload(kind, id=str(channel.id))(rig))

    edited = rig.run(channel.edit(name="renamed", reason="r"))

    assert type(edited) is type(channel)
    assert rig.http.edit_channel.call_args.args == (channel.id,)
    assert rig.http.edit_channel.call_args.kwargs == {"reason": "r", "name": "renamed"}


@pytest.mark.parametrize("kind", ["text", "voice", "stage", "category", "forum"])
def test_edit_without_options_does_nothing(world: World, kind: str) -> None:
    rig = Rig(world)
    channel = channel_of(kind)(rig)
    assert rig.run(channel.edit()) is None
    rig.http.edit_channel.assert_not_called()


@pytest.mark.parametrize("kind", ["text", "voice"])
def test_edit_spoiler_flag(world: World, kind: str) -> None:
    rig = Rig(world)
    channel = channel_of(kind)(rig)
    rig.respond("edit_channel", channel_payload(kind, id=str(channel.id))(rig))
    rig.run(channel.edit(spoiler=True))
    flags = rig.http.edit_channel.call_args.kwargs["flags"]
    assert discord.ChannelFlags._from_value(flags).is_spoiler_channel is True

    with pytest.warns(UserWarning, match="cannot be NSFW"):
        rig.run(channel.edit(spoiler=True, nsfw=True))


def test_edit_translates_options(world: World) -> None:
    rig = Rig(world)
    forum = channel_of("forum")(rig)
    category = channel_of("category")(rig)
    rig.respond("edit_channel", channel_payload("forum", id=str(forum.id))(rig))

    rig.run(
        forum.edit(
            slowmode_delay=5,
            default_thread_slowmode_delay=6,
            available_tags=[discord.ForumTag(name="tag")],
            default_reaction_emoji="\N{FIRE}",
            default_sort_order=SortOrder.creation_date,
            overwrites={
                rig.world.member: discord.PermissionOverwrite(send_messages=False),
                rig.guild.default_role: discord.PermissionOverwrite(),
            },
            category=category,
            type=ChannelType.forum,
            rtc_region=None,
            video_quality_mode=discord.VideoQualityMode.full,
        )
    )

    kwargs = rig.http.edit_channel.call_args.kwargs
    assert kwargs["rate_limit_per_user"] == 5
    assert kwargs["default_thread_rate_limit_per_user"] == 6
    assert kwargs["available_tags"][0]["name"] == "tag"
    assert kwargs["default_reaction_emoji"] == {
        "emoji_id": None,
        "emoji_name": "\N{FIRE}",
    }
    assert [p["type"] for p in kwargs["permission_overwrites"]] == [1, 0]
    assert kwargs["parent_id"] == category.id
    assert kwargs["type"] == 15
    assert kwargs["rtc_region"] is None
    assert kwargs["video_quality_mode"] == 2


@pytest.mark.parametrize(
    ("option", "message"),
    [
        ({"overwrites": {1: 2}}, "Expected PermissionOverwrite"),
        ({"type": 5}, "ChannelType"),
        ({"default_reaction_emoji": 1.5}, "default_reaction_emoji"),
    ],
)
def test_edit_rejects_bad_options(
    world: World, option: dict[str, Any], message: str
) -> None:
    rig = Rig(world)
    channel = channel_of("forum")(rig)
    with pytest.raises(InvalidArgument, match=message):
        rig.run(channel.edit(**option))
    rig.http.edit_channel.assert_not_called()


@pytest.mark.parametrize(
    ("emoji", "expected"),
    [
        (123, {"emoji_id": 123, "emoji_name": None}),
        (None, None),
    ],
)
def test_edit_default_reaction_emoji_forms(
    world: World, emoji: Any, expected: Any
) -> None:
    rig = Rig(world)
    channel = channel_of("forum")(rig)
    rig.respond("edit_channel", channel_payload("forum", id=str(channel.id))(rig))
    rig.run(channel.edit(default_reaction_emoji=emoji))
    assert rig.http.edit_channel.call_args.kwargs["default_reaction_emoji"] == expected


def test_edit_syncs_permissions_with_the_category(world: World) -> None:
    rig = Rig(world)
    category = make_channel(
        rig,
        "category",
        permission_overwrites=[
            {"id": "5", "type": 0, "allow": "1", "deny": "2"},
        ],
    )
    text = make_channel(rig, "text", parent_id=str(category.id))
    rig.respond("edit_channel", channel_payload("text", id=str(text.id))(rig))

    rig.run(text.edit(sync_permissions=True))
    assert rig.http.edit_channel.call_args.kwargs["permission_overwrites"] == [
        {"id": 5, "type": 0, "allow": "1", "deny": "2"}
    ]

    rig.run(text.edit(category=category, sync_permissions=True))
    kwargs = rig.http.edit_channel.call_args.kwargs
    assert kwargs["parent_id"] == category.id
    assert kwargs["permission_overwrites"] == [
        {"id": 5, "type": 0, "allow": "1", "deny": "2"}
    ]

    rig.run(text.edit(category=None))
    assert rig.http.edit_channel.call_args.kwargs["parent_id"] is None


def test_edit_position_moves_the_channel(world: World) -> None:
    rig = Rig(world)
    first = make_channel(rig, "text", position=0)
    second = make_channel(rig, "text", position=1)
    third = make_channel(rig, "text", position=2)

    rig.run(third._edit({"position": 0}, "r"))

    rig.http.bulk_channel_update.assert_called_once()
    args, kwargs = rig.http.bulk_channel_update.call_args
    ordered = [p["id"] for p in args[1]]
    assert ordered.index(third.id) < ordered.index(first.id) < ordered.index(second.id)
    assert [p["position"] for p in args[1]] == list(range(len(ordered)))
    assert kwargs == {"reason": "r"}

    with pytest.raises(InvalidArgument, match="less than 0"):
        rig.run(third._move(-1, reason=None))

    rig.http.bulk_channel_update.reset_mock()
    rig.run(third._edit({"position": 1, "category": None}, None))
    payload = rig.http.bulk_channel_update.call_args.args[1]
    moved = next(p for p in payload if p["id"] == third.id)
    assert moved["parent_id"] is None
    assert moved["lock_permissions"] is False


def test_move_orders_within_the_category(world: World) -> None:
    rig = Rig(world)
    a = make_channel(rig, "text", position=0)
    b = make_channel(rig, "text", position=1)
    c = make_channel(rig, "text", position=2)

    def order() -> list[int]:
        return [p["id"] for p in rig.http.bulk_channel_update.call_args.args[1]]

    rig.run(c.move(beginning=True, reason="r"))
    assert order().index(c.id) == 0
    assert rig.http.bulk_channel_update.call_args.kwargs == {"reason": "r"}

    rig.run(a.move(end=True))
    assert order()[-1] == a.id

    rig.run(c.move(before=a))
    assert order().index(c.id) == order().index(a.id) - 1

    rig.run(a.move(after=b, offset=0))
    assert order().index(a.id) == order().index(b.id) + 1

    rig.run(b.move(beginning=True, offset=-5))
    assert order().index(b.id) == 0

    category = make_channel(rig, "category")
    rig.run(b.move(beginning=True, category=category, sync_permissions=True))
    moved = next(
        p for p in rig.http.bulk_channel_update.call_args.args[1] if p["id"] == b.id
    )
    assert moved["parent_id"] == category.id
    assert moved["lock_permissions"] is True

    rig.http.bulk_channel_update.reset_mock()
    rig.run(b.move())
    rig.http.bulk_channel_update.assert_not_called()


def test_move_validation(world: World) -> None:
    rig = Rig(world)
    a = make_channel(rig, "text", position=0)
    b = make_channel(rig, "text", position=1)
    with pytest.raises(InvalidArgument, match="Only one of"):
        rig.run(a.move(beginning=True, end=True))
    with pytest.raises(InvalidArgument, match="Could not resolve"):
        rig.run(a.move(offset=1))
    with pytest.raises(InvalidArgument, match="Could not resolve"):
        rig.run(a.move(before=discord.Object(id=1)))
    _ = b


def test_category_move_ignores_the_category_argument(world: World) -> None:
    rig = Rig(world)
    first = make_channel(rig, "category", position=0)
    second = make_channel(rig, "category", position=1)
    rig.run(second.move(beginning=True, category=first))
    payload = rig.http.bulk_channel_update.call_args.args[1]
    assert payload[0]["id"] == second.id
    assert all("parent_id" not in p for p in payload)
    assert second._sorting_bucket == ChannelType.category.value


def test_set_permissions_variants(world: World) -> None:
    rig = Rig(world)
    channel = channel_of("text")(rig)
    member = rig.world.member
    role = rig.guild.default_role

    rig.run(channel.set_permissions(member, send_messages=False, reason="r"))
    args, kwargs = rig.http.edit_channel_permissions.call_args
    assert args[:2] == (channel.id, member.id)
    assert args[2:] == (0, discord.Permissions(send_messages=True).value, 1)
    assert kwargs == {"reason": "r"}

    rig.run(
        channel.set_permissions(
            role, overwrite=discord.PermissionOverwrite(read_messages=True)
        )
    )
    assert rig.http.edit_channel_permissions.call_args.args[4] == 0

    rig.run(channel.set_permissions(role, overwrite=None, reason="r"))
    rig.http.delete_channel_permissions.assert_called_once_with(
        channel.id, role.id, reason="r"
    )


@pytest.mark.parametrize(
    ("target", "kwargs", "message"),
    [
        ("object", {"send_messages": True}, "either Member or Role"),
        ("member", {}, "No overwrite provided"),
        ("member", {"bogus": True}, "Invalid permissions"),
        (
            "member",
            {"overwrite": discord.PermissionOverwrite(), "send_messages": True},
            "Cannot mix",
        ),
        ("member", {"overwrite": 5}, "Invalid overwrite type"),
    ],
)
def test_set_permissions_validation(
    world: World, target: str, kwargs: dict[str, Any], message: str
) -> None:
    rig = Rig(world)
    channel = channel_of("text")(rig)
    who = discord.Object(id=1) if target == "object" else rig.world.member
    with pytest.raises(InvalidArgument, match=message):
        rig.run(channel.set_permissions(who, **kwargs))  # type: ignore[arg-type]


def test_overwrites_for_resolves_members_roles_and_objects(world: World) -> None:
    rig = Rig(world)
    member = rig.world.member
    role = rig.guild.default_role
    channel = make_channel(
        rig,
        "text",
        permission_overwrites=[
            {"id": str(member.id), "type": 1, "allow": "1024", "deny": "0"},
            {"id": str(role.id), "type": 0, "allow": "0", "deny": "2048"},
        ],
    )

    assert channel.overwrites_for(member).read_messages is True
    assert channel.overwrites_for(role).send_messages is False
    assert channel.overwrites_for(discord.Object(id=member.id)).read_messages is True
    assert channel.overwrites_for(discord.Object(id=1)).is_empty()
    assert channel.overwrites_for(rig.world.user).is_empty()


def test_permissions_for_resolves_overwrites(world: World) -> None:
    rig = Rig(world)
    member = rig.world.member
    role = rig.guild.default_role
    channel = make_channel(
        rig,
        "text",
        permission_overwrites=[
            {
                "id": str(rig.guild.id),
                "type": 0,
                "allow": "0",
                "deny": str(discord.Permissions(send_messages=True).value),
            },
            {
                "id": str(member.id),
                "type": 1,
                "allow": str(discord.Permissions(send_messages=True).value),
                "deny": "0",
            },
        ],
    )
    role._permissions = discord.Permissions(view_channel=True, send_messages=True).value

    assert channel.permissions_for(role).send_messages is False
    assert channel.permissions_for(role).view_channel is True
    assert rig.run(channel.get_permissions_for(member)).send_messages is True


def test_role_base_permissions(world: World) -> None:
    rig = Rig(world)
    role = rig.guild.default_role
    channel = channel_of("text")(rig)
    assert (
        channel._role_base_permissions(role, role.id, None) == discord.Permissions.all()
    )
    other = rig.payload(t.role.Role, id="77", permissions="8")
    custom = discord.Role(guild=rig.guild, state=rig.state, data=other)
    base = channel._role_base_permissions(custom, None, role)
    assert base.administrator is True


def test_create_invite_and_invites(world: World) -> None:
    rig = Rig(world)
    channel = channel_of("text")(rig)
    event = None
    rig.respond(
        "create_invite",
        rig.payload(
            t.invite.Invite,
            channel={"id": str(channel.id), "type": 0, "name": "x"},
        ),
    )
    invite = rig.run(
        channel.create_invite(
            max_age=60,
            max_uses=2,
            temporary=True,
            unique=False,
            target_type=discord.InviteTarget.embedded_application,
            target_user=rig.world.user,
            target_application_id=3,
            roles=[discord.Object(id=8)],
            target_user_ids=(1, 2),
            reason="r",
        )
    )
    assert isinstance(invite, discord.Invite)
    kwargs = rig.http.create_invite.call_args.kwargs
    assert kwargs["target_type"] == 2
    assert kwargs["target_user_id"] == rig.world.user.id
    assert kwargs["roles"] == ["8"]
    assert kwargs["target_user_ids"] == [1, 2]
    assert kwargs["max_age"] == 60
    _ = event

    rig.respond(
        "invites_from_channel",
        [
            rig.payload(
                t.invite.Invite,
                channel={"id": str(channel.id), "type": 0, "name": "x"},
            )
        ],
    )
    invites = rig.run(channel.invites())
    assert [type(i) for i in invites] == [discord.Invite]
    assert invites[0].channel is channel


def test_delete_channel(world: World) -> None:
    rig = Rig(world)
    channel = channel_of("text")(rig)
    rig.run(channel.delete(reason="r"))
    rig.http.delete_channel.assert_called_once_with(channel.id, reason="r")


EXTRA = [
    Case(
        "follow_needs_a_news_channel",
        channel_of("text"),
        "follow",
        "follow_webhook",
        kwargs=lambda r: {"destination": channel_of("text")(r)},
        raises=(ClientException, "news channel"),
    ),
    Case(
        "voice_set_status",
        channel_of("voice"),
        "set_status",
        "set_voice_channel_status",
        kwargs=lambda r: {"status": "live", "reason": "r"},
        called_with=lambda r: ((channel_of("voice")(r).id, "live"), {"reason": "r"}),
    ),
    Case(
        "stage_create_instance",
        channel_of("stage"),
        "create_instance",
        "create_stage_instance",
        lambda r: r.payload(
            t.channel.StageInstance,
            guild_id=str(r.guild.id),
            channel_id=str(channel_of("stage")(r).id),
        ),
        kwargs=lambda r: {
            "topic": "talk",
            "privacy_level": discord.StagePrivacyLevel.guild_only,
            "send_notification": True,
            "reason": "r",
        },
        called_with=lambda r: (
            (),
            {
                "channel_id": channel_of("stage")(r).id,
                "topic": "talk",
                "send_start_notification": True,
                "privacy_level": 2,
                "reason": "r",
            },
        ),
        check=check_type(discord.StageInstance),
    ),
    Case(
        "stage_create_instance_bad_privacy",
        channel_of("stage"),
        "create_instance",
        "create_stage_instance",
        kwargs=lambda r: {"topic": "talk", "privacy_level": 2},
        raises=(InvalidArgument, "PrivacyLevel"),
    ),
    Case(
        "stage_fetch_instance",
        channel_of("stage"),
        "fetch_instance",
        "get_stage_instance",
        lambda r: r.payload(
            t.channel.StageInstance,
            guild_id=str(r.guild.id),
            channel_id=str(channel_of("stage")(r).id),
        ),
        called_with=lambda r: ((channel_of("stage")(r).id,), {}),
        check=check_type(discord.StageInstance),
    ),
    Case(
        "text_create_private_thread",
        channel_of("text"),
        "create_thread",
        "start_thread_without_message",
        lambda r: r.payload(
            t.threads.Thread,
            guild_id=str(r.guild.id),
            parent_id=str(channel_of("text")(r).id),
        ),
        kwargs=lambda r: {"name": "t", "slowmode_delay": 3, "invitable": False},
        kwargs_include=lambda r: {
            "name": "t",
            "type": ChannelType.private_thread.value,
            "rate_limit_per_user": 3,
            "invitable": False,
            "auto_archive_duration": channel_of("text")(
                r
            ).default_auto_archive_duration,
        },
        check=check_type(discord.Thread),
    ),
    Case(
        "text_create_thread_from_message",
        channel_of("text"),
        "create_thread",
        "start_thread_with_message",
        lambda r: r.payload(
            t.threads.Thread,
            guild_id=str(r.guild.id),
            parent_id=str(channel_of("text")(r).id),
        ),
        kwargs=lambda r: {
            "name": "t",
            "message": discord.Object(id=5),
            "auto_archive_duration": 60,
            "reason": "r",
        },
        called_with=lambda r: (
            (channel_of("text")(r).id, 5),
            {
                "name": "t",
                "auto_archive_duration": 60,
                "rate_limit_per_user": 0,
                "reason": "r",
            },
        ),
        check=check_type(discord.Thread),
    ),
]


@pytest.mark.parametrize("case", EXTRA, ids=lambda c: c.id)
def test_channel_remote_calls_more(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_follow_a_news_channel(world: World) -> None:
    rig = Rig(world)
    news = make_channel(rig, "text", type=5)
    destination = channel_of("text")(rig)
    rig.respond("follow_webhook", {"webhook_id": "321"})

    webhook = rig.run(news.follow(destination=destination, reason="r"))

    assert isinstance(webhook, discord.Webhook)
    assert rig.http.follow_webhook.call_args.args == (news.id,)
    assert rig.http.follow_webhook.call_args.kwargs == {
        "webhook_channel_id": destination.id,
        "reason": "r",
    }
    with pytest.raises(InvalidArgument, match="Expected TextChannel"):
        rig.run(news.follow(destination=channel_of("voice")(rig)))  # type: ignore[arg-type]


def test_voice_activity_invite(world: World) -> None:
    rig = Rig(world)
    voice = channel_of("voice")(rig)
    rig.respond(
        "create_invite",
        rig.payload(
            t.invite.Invite, channel={"id": str(voice.id), "type": 2, "name": "x"}
        ),
    )
    rig.run(
        voice.create_activity_invite(discord.EmbeddedActivity.poker_night, max_age=5)
    )
    kwargs = rig.http.create_invite.call_args.kwargs
    assert kwargs["target_type"] == discord.InviteTarget.embedded_application.value
    assert kwargs["target_application_id"] == discord.EmbeddedActivity.poker_night.value
    assert kwargs["max_age"] == 5
    rig.run(voice.create_activity_invite(7))
    assert rig.http.create_invite.call_args.kwargs["target_application_id"] == 7
    with pytest.raises(TypeError, match="Invalid type"):
        rig.run(voice.create_activity_invite("x"))  # type: ignore[arg-type]


def test_category_creates_channels_inside_itself(world: World) -> None:
    rig = Rig(world)
    category = channel_of("category")(rig)
    for method, kind, number in (
        ("create_text_channel", "text", 0),
        ("create_voice_channel", "voice", 2),
        ("create_stage_channel", "stage", 13),
        ("create_forum_channel", "forum", 15),
    ):
        rig.http.create_channel.pages = []
        rig.respond("create_channel", channel_payload(kind)(rig))
        kwargs: dict[str, Any] = {"topic": "t"} if kind == "stage" else {}
        created = rig.run(getattr(category, method)("name", **kwargs))
        assert type(created) is CHANNEL_TYPES[kind][0]
        assert rig.http.create_channel.call_args.args == (rig.guild.id, number)
        assert rig.http.create_channel.call_args.kwargs["parent_id"] == category.id


def test_channel_misc_helpers(world: World) -> None:
    rig = Rig(world)
    voice = channel_of("voice")(rig)
    stage = channel_of("stage")(rig)
    category = channel_of("category")(rig)
    assert voice._get_voice_state_pair() == (rig.guild.id, voice.id)
    assert voice._get_voice_client_key() == (rig.guild.id, "guild_id")
    assert rig.run(voice._get_channel()) is voice
    assert rig.run(stage._get_channel()) is stage
    assert voice.is_nsfw() is False
    assert stage.is_nsfw() is False
    with pytest.warns(DeprecationWarning, match="is_nsfw"):
        assert category.is_nsfw() is False
    tag = discord.ForumTag(name="t", emoji="\N{FIRE}", moderated=True)
    assert str(tag) == "t"
    assert tag.emoji is not None
    with pytest.raises(TypeError, match="emoji must be"):
        discord.ForumTag(name="t", emoji=1.5)  # type: ignore[arg-type]


@requires_voice
def test_voice_connect_delegates_to_the_voice_class(world: World) -> None:
    rig = Rig(world)
    voice = channel_of("voice")(rig)
    from discord.voice._types import VoiceProtocol

    class Protocol(VoiceProtocol):  # type: ignore[type-arg]
        def __init__(self, client: Any, channel: Any) -> None:
            self.client = client
            self.channel = channel
            self.connect = AsyncMock()  # type: ignore[method-assign]
            self.disconnect = AsyncMock()  # type: ignore[method-assign]

        async def on_voice_state_update(self, data: Any) -> None: ...

        async def on_voice_server_update(self, data: Any) -> None: ...

        async def connect(self, *, timeout: float, reconnect: bool) -> None: ...  # type: ignore[no-redef]

        async def disconnect(self, *, force: bool = False) -> None: ...  # type: ignore[no-redef]

        def cleanup(self) -> None: ...

    client = rig.run(voice.connect(cls=Protocol))  # type: ignore[arg-type]
    assert isinstance(client, Protocol)
    client.connect.assert_awaited_once_with(timeout=60.0, reconnect=True)
    with pytest.raises(ClientException, match="Already connected"):
        rig.run(voice.connect(cls=Protocol))  # type: ignore[arg-type]
    rig.state._remove_voice_client(rig.guild.id)
    with pytest.raises(TypeError, match="VoiceProtocol"):
        rig.run(voice.connect(cls=lambda c, ch: object()))  # type: ignore[arg-type,return-value]
