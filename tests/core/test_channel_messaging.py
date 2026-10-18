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
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

import discord
from discord import types as t
from discord.errors import InvalidArgument
from discord.file import VoiceMessage
from tests.core.rig import Case, Rig, check_type, execute
from tests.core.test_channel_remote import channel_of

if TYPE_CHECKING:
    from tests.models.context import World


def sent_message(rig: Rig) -> Any:
    return rig.message_payload(6000)


def send(
    case_id: str, kwargs: Any = None, args: Any = ("hi",), **expected: Any
) -> Case:
    return Case(
        case_id,
        channel_of("text"),
        "send",
        "send_message",
        sent_message,
        args=lambda r: args,
        kwargs=lambda r: kwargs(r) if callable(kwargs) else (kwargs or {}),
        kwargs_include=lambda r: {
            k: v(r) if callable(v) else v for k, v in expected.items()
        },
        check=check_type(discord.Message),
        setup=lambda r: setattr(r.state, "allowed_mentions", None),
    )


def send_error(case_id: str, kwargs: Any, error: type[Exception], text: str) -> Case:
    return Case(
        case_id,
        channel_of("text"),
        "send",
        kwargs=lambda r: kwargs(r) if callable(kwargs) else kwargs,
        raises=(error, text),
    )


CASES = [
    send("plain", None, tts=False, embed=None, embeds=None, allowed_mentions=None),
    send(
        "tts_and_nonce",
        {"tts": True, "nonce": 4, "enforce_nonce": True},
        tts=True,
        nonce=4,
        enforce_nonce=True,
    ),
    send(
        "embed",
        lambda r: {"embed": discord.Embed(title="e")},
        embed=discord.Embed(title="e").to_dict(),
    ),
    send(
        "embeds",
        lambda r: {"embeds": [discord.Embed(title="e")]},
        embeds=[discord.Embed(title="e").to_dict()],
    ),
    send("stickers", lambda r: {"stickers": [discord.Object(id=3)]}, stickers=[3]),
    send(
        "silent",
        {"silent": True, "suppress_embeds": True},
        flags=discord.MessageFlags(
            suppress_notifications=True, suppress_embeds=True
        ).value,
    ),
    send(
        "allowed_mentions",
        lambda r: {"allowed_mentions": discord.AllowedMentions.none()},
        allowed_mentions=discord.AllowedMentions.none().to_dict(),
    ),
    send(
        "mention_author",
        {"mention_author": True},
        allowed_mentions=discord.AllowedMentions().to_dict() | {"replied_user": True},
    ),
    send(
        "poll",
        lambda r: {"poll": discord.Poll("q?", answers=[discord.PollAnswer("a")])},
        poll=lambda r: discord.Poll("q?", answers=[discord.PollAnswer("a")]).to_dict(),
    ),
    send(
        "theme",
        lambda r: (
            {
                "shared_client_theme": discord.SharedClientTheme(
                    colors=[discord.Colour(1)], base_theme=1
                )
            }
            if hasattr(discord, "SharedClientTheme")
            else {}
        ),
    ),
    send_error(
        "embed_and_embeds",
        lambda r: {"embed": discord.Embed(), "embeds": []},
        InvalidArgument,
        "both embed and embeds",
    ),
    send_error(
        "too_many_embeds",
        lambda r: {"embeds": [discord.Embed()] * 11},
        InvalidArgument,
        "up to 10",
    ),
    send_error(
        "file_and_files",
        lambda r: {"file": 1, "files": []},
        InvalidArgument,
        "both file and files",
    ),
    send_error("bad_file", {"file": 1}, InvalidArgument, "must be File"),
    send_error(
        "too_many_files", lambda r: {"files": [1] * 11}, InvalidArgument, "up to 10"
    ),
    send_error("bad_files", {"files": [1]}, InvalidArgument, "list of File"),
    send_error(
        "bad_reference", {"reference": 5}, InvalidArgument, "reference parameter"
    ),
    send_error("bad_view", {"view": object()}, InvalidArgument, "BaseView"),
]


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.id != "theme"], ids=lambda c: c.id
)
def test_send_variants(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_send_with_files_closes_them_and_marks_voice_messages(world: World) -> None:
    rig = Rig(world)
    rig.state.allowed_mentions = None
    rig.respond("send_files", sent_message(rig))
    channel = channel_of("text")(rig)
    plain = discord.File(io.BytesIO(b"x"), "a.txt")
    voice = VoiceMessage(io.BytesIO(b"ogg"), waveform="AA==", duration_secs=1.0)

    message = rig.run(channel.send(files=[plain, voice]))

    assert isinstance(message, discord.Message)
    kwargs = rig.http.send_files.call_args.kwargs
    assert kwargs["files"] == [plain, voice]
    assert discord.MessageFlags._from_value(kwargs["flags"]).is_voice_message is True

    single = discord.File(io.BytesIO(b"x"), "b.txt")
    rig.run(channel.send("hi", file=single))
    assert rig.http.send_files.call_args.kwargs["files"] == [single]
    assert rig.http.send_files.call_args.kwargs["content"] == "hi"


def test_send_reply_forms_and_default_mentions(world: World) -> None:
    rig = Rig(world)
    rig.respond("send_message", sent_message(rig))
    channel = channel_of("text")(rig)
    rig.state.allowed_mentions = discord.AllowedMentions(everyone=False)
    original = rig.make_message()

    rig.run(channel.send("a"))
    assert rig.http.send_message.call_args.kwargs["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False).to_dict()
    )
    rig.run(channel.send("a", allowed_mentions=discord.AllowedMentions(users=False)))
    assert rig.http.send_message.call_args.kwargs["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False, users=False).to_dict()
    )

    with pytest.warns(DeprecationWarning, match="MessageReference"):
        rig.run(channel.send("a", reference=original))
    reference = rig.http.send_message.call_args.kwargs["message_reference"]
    assert reference["message_id"] == original.id

    rig.run(channel.send("a", reference=original.to_reference()))
    assert (
        rig.http.send_message.call_args.kwargs["message_reference"]["message_id"]
        == original.id
    )


def test_send_suppress_is_deprecated(world: World) -> None:
    rig = Rig(world)
    rig.respond("send_message", sent_message(rig))
    with pytest.warns(DeprecationWarning, match="suppress"):
        rig.run(channel_of("text")(rig).send("a", suppress=True))
    flags = rig.http.send_message.call_args.kwargs["flags"]
    assert discord.MessageFlags._from_value(flags).suppress_embeds is True


def test_send_delete_after_schedules_the_deletion(world: World) -> None:
    rig = Rig(world)
    rig.respond("send_message", sent_message(rig))
    channel = channel_of("text")(rig)
    with patch("discord.message.Message.delete", new=AsyncMock()) as delete:
        rig.run(channel.send("a", delete_after=0.5))
    delete.assert_awaited_once_with(delay=0.5)


def test_send_permission_requirements(world: World) -> None:
    rig = Rig(world)
    text = channel_of("text")(rig)
    guild_emoji = discord.GuildEmoji(
        guild=rig.guild,
        state=rig.state,
        data=rig.payload(t.emoji.Emoji, id="9"),
    )
    other_guild = SimpleNamespace(id=1)
    foreign = discord.GuildEmoji(
        guild=other_guild,  # type: ignore[arg-type]
        state=rig.state,
        data=rig.payload(t.emoji.Emoji, id="10"),
    )
    sticker = discord.GuildSticker(
        state=rig.state, data=rig.payload(t.sticker.GuildSticker, guild_id="1")
    )

    channel, required = text._send_permissions(())
    assert channel is text
    assert required == ["send_messages"]
    _, required = text._send_permissions(
        (discord.Embed, discord.File, foreign, sticker)
    )
    assert required == [
        "send_messages",
        "embed_links",
        "attach_files",
        "use_external_emojis",
        "use_external_stickers",
    ]
    _, required = text._send_permissions((guild_emoji,))
    assert required == ["send_messages"]
    with pytest.raises(TypeError, match="invalid type"):
        text._send_permissions((object(),))

    dm = SimpleNamespace(channel=type("DMChannel", (), {})())
    assert discord.abc.Messageable._send_permissions(dm, ()) is None  # type: ignore[arg-type]
    group = type("GroupChannel", (), {"permissions_for": None})()
    assert discord.abc.Messageable._send_permissions(group, ()) is None  # type: ignore[arg-type]


async def history(*items: Any) -> Any:
    for item in items:
        yield item


def test_purge_helper_groups_deletions(world: World) -> None:
    rig = Rig(world)
    channel = SimpleNamespace(
        history=lambda **kwargs: history(*messages),
        delete_messages=AsyncMock(),
    )
    new = [
        SimpleNamespace(id=10_000_000_000_000_000_000 + i, delete=AsyncMock())
        for i in range(3)
    ]
    messages = new
    result = rig.run(discord.abc.purge_messages_helper(channel, limit=10, reason="r"))  # type: ignore[arg-type]
    assert result == new
    channel.delete_messages.assert_awaited_once_with(new, reason="r")

    channel.delete_messages.reset_mock()
    messages = new[:1]
    assert rig.run(discord.abc.purge_messages_helper(channel)) == new[:1]  # type: ignore[arg-type]
    new[0].delete.assert_awaited_once_with(reason=None)
    channel.delete_messages.assert_not_called()


def test_purge_helper_filters_old_messages_and_single_deletes(world: World) -> None:
    rig = Rig(world)
    old = [SimpleNamespace(id=1000 + i, delete=AsyncMock()) for i in range(3)]
    fresh = [
        SimpleNamespace(id=10_000_000_000_000_000_000 + i, delete=AsyncMock())
        for i in range(2)
    ]
    unwanted = SimpleNamespace(id=10_000_000_000_000_000_100, delete=AsyncMock())
    messages = [*fresh, unwanted, *old]
    channel = SimpleNamespace(
        history=lambda **kwargs: history(*messages), delete_messages=AsyncMock()
    )

    kept = rig.run(
        discord.abc.purge_messages_helper(
            channel,  # type: ignore[arg-type]
            check=lambda m: m is not unwanted,
            bulk=False,
        )
    )

    assert kept == [*fresh, *old]
    for message in [*fresh, *old]:
        message.delete.assert_awaited_once_with(reason=None)
    unwanted.delete.assert_not_called()
    channel.delete_messages.assert_not_called()


def test_purge_helper_flushes_every_hundred_messages(world: World) -> None:
    rig = Rig(world)
    fresh = [
        SimpleNamespace(id=10_000_000_000_000_000_000 + i, delete=AsyncMock())
        for i in range(101)
    ]
    channel = SimpleNamespace(
        history=lambda **kwargs: history(*fresh), delete_messages=AsyncMock()
    )
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        result = rig.run(discord.abc.purge_messages_helper(channel, limit=None))  # type: ignore[arg-type]
    assert len(result) == 101
    channel.delete_messages.assert_awaited_once()
    assert len(channel.delete_messages.await_args.args[0]) == 100
    fresh[-1].delete.assert_awaited_once_with(reason=None)
    sleep.assert_awaited_once_with(1)


def test_purge_on_channel_classes(world: World) -> None:
    rig = Rig(world)
    for kind in ("text", "voice", "stage"):
        channel = channel_of(kind)(rig)
        with patch(
            "discord.abc.purge_messages_helper", new=AsyncMock(return_value=["m"])
        ) as helper:
            assert rig.run(channel.purge(limit=5, bulk=False, reason="r")) == ["m"]
        assert helper.await_args.args == (channel,)
        assert helper.await_args.kwargs["limit"] == 5
        assert helper.await_args.kwargs["bulk"] is False
        assert helper.await_args.kwargs["reason"] == "r"


def forum_thread_payload(rig: Rig) -> Any:
    forum = channel_of("forum")(rig)
    return rig.payload(
        t.threads.Thread,
        guild_id=str(rig.guild.id),
        parent_id=str(forum.id),
        last_message_id="6000",
    )


def test_forum_create_thread(world: World) -> None:
    rig = Rig(world)
    rig.state.allowed_mentions = None
    forum = channel_of("forum")(rig)
    rig.respond("start_forum_thread", forum_thread_payload(rig))
    file = discord.File(io.BytesIO(b"x"), "a.txt")

    thread = rig.run(
        forum.create_thread(
            "post",
            "body",
            embed=discord.Embed(title="e"),
            file=file,
            stickers=[discord.Object(id=3)],
            nonce=4,
            allowed_mentions=discord.AllowedMentions.none(),
            applied_tags=[discord.ForumTag(name="t")],
            suppress=True,
            silent=True,
            auto_archive_duration=60,
            slowmode_delay=2,
            reason="r",
        )
    )

    assert isinstance(thread, discord.Thread)
    args, kwargs = rig.http.start_forum_thread.call_args
    assert args == (forum.id,)
    assert kwargs["name"] == "post"
    assert kwargs["content"] == "body"
    assert kwargs["files"] == [file]
    assert kwargs["embed"] == discord.Embed(title="e").to_dict()
    assert kwargs["stickers"] == [3]
    assert kwargs["nonce"] == 4
    assert kwargs["allowed_mentions"] == discord.AllowedMentions.none().to_dict()
    assert kwargs["applied_tags"] == ["0"]
    assert kwargs["auto_archive_duration"] == 60
    assert kwargs["rate_limit_per_user"] == 2
    assert kwargs["reason"] == "r"
    flags = discord.MessageFlags._from_value(kwargs["flags"])
    assert flags.suppress_embeds
    assert flags.suppress_notifications


def test_forum_create_thread_defaults_and_deletion(world: World) -> None:
    rig = Rig(world)
    rig.state.allowed_mentions = discord.AllowedMentions(everyone=False)
    forum = channel_of("forum")(rig)
    rig.respond("start_forum_thread", forum_thread_payload(rig))

    with patch("discord.PartialMessage.delete", new=AsyncMock()) as delete:
        rig.run(
            forum.create_thread(
                "post",
                embeds=[discord.Embed(title="e")],
                files=[discord.File(io.BytesIO(b"x"), "a.txt")],
                allowed_mentions=discord.AllowedMentions(users=False),
                delete_message_after=2,
            )
        )
    delete.assert_awaited_once_with(delay=2)
    kwargs = rig.http.start_forum_thread.call_args.kwargs
    assert kwargs["auto_archive_duration"] == forum.default_auto_archive_duration
    assert kwargs["rate_limit_per_user"] == forum.slowmode_delay
    assert kwargs["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False, users=False).to_dict()
    )
    assert kwargs["embeds"] == [discord.Embed(title="e").to_dict()]

    rig.run(forum.create_thread("post"))
    assert rig.http.start_forum_thread.call_args.kwargs["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False).to_dict()
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"embed": discord.Embed(), "embeds": []}, "both embed and embeds"),
        ({"embeds": [discord.Embed()] * 11}, "up to 10"),
        ({"file": 1, "files": []}, "both file and files"),
        ({"files": [1] * 11}, "up to 10"),
        ({"files": [1]}, "list of File"),
        ({"file": 1}, "must be File"),
        ({"view": object()}, "BaseView"),
    ],
)
def test_forum_create_thread_validation(
    world: World, kwargs: dict[str, Any], message: str
) -> None:
    rig = Rig(world)
    forum = channel_of("forum")(rig)
    with pytest.raises(InvalidArgument, match=message):
        rig.run(forum.create_thread("post", **kwargs))
    rig.http.start_forum_thread.assert_not_called()


def test_dm_and_group_channels(world: World) -> None:
    rig = Rig(world)
    dm = discord.DMChannel(
        me=rig.world.me,
        state=rig.state,
        data=rig.payload(t.channel.DMChannel, recipients=[rig.payload(t.user.User)]),
    )
    assert rig.run(dm._get_channel()) is dm
    assert str(dm).startswith("Direct Message with")
    perms = dm.permissions_for()
    assert perms.read_messages is True
    assert perms.send_tts_messages is False
    assert perms.manage_messages is False
    assert dm.get_partial_message(4).id == 4

    from_message = discord.DMChannel._from_message(rig.state, 55)
    assert from_message.id == 55
    assert from_message.recipient is None
    assert str(from_message) == "Direct Message with Unknown User"

    group = discord.GroupChannel(
        me=rig.world.me,
        state=rig.state,
        data=rig.payload(
            t.channel.GroupDMChannel, recipients=[rig.payload(t.user.User)]
        ),
    )
    assert rig.run(group._get_channel()) is group
    assert str(group)
    owner = discord.Object(id=group.owner_id)
    assert group.permissions_for(owner).kick_members is True
    assert group.permissions_for(discord.Object(id=1)).kick_members is False
    assert group.permissions_for(owner).mention_everyone is True
    rig.run(group.leave())
    rig.http.leave_group.assert_called_once_with(group.id)
