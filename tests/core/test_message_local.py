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
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

import discord
from discord import types as t
from discord.enums import ChannelType, MessageReferenceType, MessageType
from discord.errors import InvalidArgument
from discord.message import (
    Attachment,
    DeletedReferencedMessage,
    Message,
    MessageReference,
    PartialMessage,
    convert_emoji_reaction,
)
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


def attachment(rig: Rig, **fields: Any) -> Attachment:
    payload = rig.payload(
        t.message.Attachment,
        **{
            "id": "9",
            "filename": "cat.png",
            "url": "https://cdn.example/cat.png?ex=1a&is=2b&hm=3c",
            "proxy_url": "https://proxy.example/cat.png",
            **fields,
        },
    )
    return Attachment(data=payload, state=rig.state)


def test_attachment_cdn_query_parameters_and_expiry(world: World) -> None:
    rig = Rig(world)
    cat = attachment(rig)
    assert (cat._ex, cat._is, cat.hm) == ("1a", "2b", "3c")
    assert str(cat) == cat.url
    assert cat.expires_at is not None
    assert cat.issued_at is not None
    plain = attachment(rig, url="https://cdn.example/cat.png")
    assert plain.expires_at is None
    assert plain.issued_at is None


def test_attachment_read_uses_the_url_or_the_cached_proxy(world: World) -> None:
    rig = Rig(world)
    rig.respond("get_from_cdn", b"bytes")
    cat = attachment(rig)

    assert rig.run(cat.read()) == b"bytes"
    assert rig.run(cat.read(use_cached=True)) == b"bytes"
    urls = [c.args[0] for c in rig.http.get_from_cdn.call_args_list]
    assert urls == [cat.url, cat.proxy_url]


def test_attachment_to_file(world: World) -> None:
    rig = Rig(world)
    rig.respond("get_from_cdn", b"bytes")
    cat = attachment(rig, description="a cat")

    file = rig.run(cat.to_file(spoiler=True))

    assert file.filename == "SPOILER_cat.png"
    assert file.description == "a cat"
    assert file.fp.read() == b"bytes"


async def chunks(*parts: bytes) -> Any:
    for part in parts:
        yield part


def test_attachment_read_chunked_and_save_to_a_buffer(world: World) -> None:
    rig = Rig(world)
    rig.http.stream_from_cdn.side_effect = lambda _url, _size: chunks(b"ab", b"cd")
    cat = attachment(rig)

    async def collect() -> list[bytes]:
        return [c async for c in cat.read_chunked(2, use_cached=True)]

    assert rig.run(collect()) == [b"ab", b"cd"]
    assert rig.http.stream_from_cdn.call_args.args == (cat.proxy_url, 2)

    buffer = io.BytesIO()
    assert rig.run(cat.save(buffer, chunksize=2)) == 4
    assert buffer.getvalue() == b"abcd"
    assert buffer.tell() == 0

    buffer = io.BytesIO()
    rig.respond("get_from_cdn", b"xyz")
    assert rig.run(cat.save(buffer, seek_begin=False)) == 3
    assert buffer.tell() == 3


def test_attachment_save_to_a_path(world: World, tmp_path: Any) -> None:
    rig = Rig(world)
    rig.respond("get_from_cdn", b"xyz")
    cat = attachment(rig)
    target = tmp_path / "out.bin"
    assert rig.run(cat.save(target)) == 3
    assert target.read_bytes() == b"xyz"

    rig.http.stream_from_cdn.side_effect = lambda _url, _size: chunks(b"12", b"3")
    streamed = tmp_path / "streamed.bin"
    assert rig.run(cat.save(streamed, chunksize=2)) == 3
    assert streamed.read_bytes() == b"123"


@pytest.mark.parametrize(
    ("emoji", "expected"),
    [
        ("<:name:123>", ":name:123"),
        ("\N{THUMBS UP SIGN}", "\N{THUMBS UP SIGN}"),
        (discord.PartialEmoji(name="a", id=5), "a:5"),
        (discord.PartialEmoji(name="\N{FIRE}"), "\N{FIRE}"),
    ],
)
def test_convert_emoji_reaction(emoji: object, expected: str) -> None:
    assert convert_emoji_reaction(emoji) == expected


def test_convert_emoji_reaction_from_a_reaction_and_guild_emoji(world: World) -> None:
    rig = Rig(world)
    guild_emoji = discord.GuildEmoji(
        guild=rig.guild,
        state=rig.state,
        data=rig.payload(t.emoji.Emoji, id="9", name="pycord"),
    )
    assert convert_emoji_reaction(guild_emoji) == "pycord:9"
    reaction = rig.make_message()._add_reaction({"me": False}, "\N{FIRE}", 1)
    assert convert_emoji_reaction(reaction) == "\N{FIRE}"
    with pytest.raises(InvalidArgument, match="int"):
        convert_emoji_reaction(5)
    _ = rig


def test_deleted_referenced_message_reads_its_reference() -> None:
    reference = MessageReference(message_id=1, channel_id=2, guild_id=3)
    deleted = DeletedReferencedMessage(reference)
    assert (deleted.id, deleted.channel_id, deleted.guild_id) == (1, 2, 3)
    assert repr(deleted) == "<DeletedReferencedMessage id=1 channel_id=2 guild_id=3>"


def test_reaction_bookkeeping_on_a_message(world: World) -> None:
    rig = Rig(world)
    message = rig.make_message(reactions=[])
    me = rig.state.self_id
    data: dict[str, Any] = {"me": False, "emoji": {"name": "x"}}

    reaction = message._add_reaction(data, "x", 1)
    assert reaction.count == 1
    assert reaction.me is False
    message._add_reaction(data, "x", me)
    assert reaction.count == 2
    assert reaction.me is True

    message._remove_reaction(data, "x", me)
    assert reaction.count == 1
    assert reaction.me is False
    message._remove_reaction(data, "x", 1)
    assert message.reactions == []
    with pytest.raises(ValueError, match="already removed"):
        message._remove_reaction(data, "x", 1)

    message._add_reaction(data, "x", 1)
    message._add_reaction(data, "y", 1)
    assert message._clear_emoji("x").emoji == "x"  # type: ignore[union-attr]
    assert message._clear_emoji("x") is None
    assert [str(r.emoji) for r in message.reactions] == ["y"]


def test_message_field_handlers_and_try_patch(world: World) -> None:
    rig = Rig(world)
    message = rig.make_message()

    message._handle_edited_timestamp("2024-01-02T03:04:05+00:00")
    assert message.edited_at is not None
    message._handle_pinned(True)
    assert message.pinned is True
    message._handle_flags(4)
    assert message.flags.suppress_embeds is True
    message._handle_application({"id": 1})  # type: ignore[typeddict-item]
    assert message.application == {"id": 1}
    message._handle_activity({"type": 1})  # type: ignore[typeddict-item]
    assert message.activity == {"type": 1}
    message._handle_mention_everyone(True)
    assert message.mention_everyone is True
    message._handle_tts(True)
    assert message.tts is True
    message._handle_type(0)
    assert message.type is MessageType.default
    message._handle_content("hello")
    assert message.content == "hello"
    message._handle_attachments([])
    assert message.attachments == []
    message._handle_embeds([])
    assert message.embeds == []
    message._handle_nonce("n")
    assert message.nonce == "n"
    message._handle_components([])
    assert message.components == []

    message._try_patch({"content": "patched"}, "content")
    assert message.content == "patched"
    message._try_patch({"content": "patched"}, "content", str.upper)
    assert message.content == "PATCHED"
    message._try_patch({}, "content")
    assert message.content == "PATCHED"


def test_message_interaction_is_deprecated(world: World) -> None:
    message = Rig(world).make_message()
    with pytest.warns(DeprecationWarning, match="interaction"):
        message.interaction = None
    with pytest.warns(DeprecationWarning, match="interaction"):
        assert message.interaction is None


def test_message_reference_helpers(world: World) -> None:
    rig = Rig(world)
    message = rig.make_message()

    assert message.to_message_reference_dict() == {
        "message_id": 5000,
        "channel_id": rig.channel.id,
        "type": None,
        "guild_id": rig.guild.id,
    }
    forward = message.to_message_reference_dict(MessageReferenceType.forward)
    assert forward["type"] == MessageReferenceType.forward.value

    sent = AsyncMock(return_value="sent")
    target = SimpleNamespace(send=sent)
    assert rig.run(message.forward_to(target, content="x")) == "sent"  # type: ignore[arg-type]
    kwargs = sent.await_args.kwargs
    assert kwargs["content"] == "x"
    assert kwargs["reference"].type is MessageReferenceType.forward
    assert kwargs["reference"].message_id == 5000


def test_get_component_searches_nested_components(world: World) -> None:
    message = Rig(world).make_message()
    inner = SimpleNamespace(id=2, custom_id="inner")
    row = SimpleNamespace(
        id=1,
        custom_id=None,
        get_component=lambda value: inner if value in {2, "inner"} else None,
    )
    leaf = SimpleNamespace(id=3, custom_id="leaf")
    message.components = [row, leaf]  # type: ignore[list-item]

    assert message.get_component(3) is leaf
    assert message.get_component("leaf") is leaf
    assert message.get_component(1) is row
    assert message.get_component("inner") is inner
    assert message.get_component(0) is None
    assert message.get_component("") is None


def system_message(rig: Rig, kind: MessageType, **fields: Any) -> Any:
    return rig.make_message(type=kind.value, **fields)


@pytest.mark.parametrize(
    ("kind", "content", "expected"),
    [
        (MessageType.channel_name_change, "new", "changed the channel name: **new**"),
        (MessageType.channel_icon_change, "", "changed the channel icon."),
        (MessageType.pins_add, "", "pinned a message to this channel."),
        (MessageType.premium_guild_subscription, "", "just boosted the server!"),
        (
            MessageType.premium_guild_subscription,
            "3",
            "boosted the server **3** times!",
        ),
        (MessageType.premium_guild_tier_1, "", "G has achieved **Level 1!**"),
        (
            MessageType.premium_guild_tier_1,
            "3",
            "**3** times! G has achieved **Level 1!**",
        ),
        (MessageType.premium_guild_tier_2, "", "G has achieved **Level 2!**"),
        (
            MessageType.premium_guild_tier_2,
            "3",
            "**3** times! G has achieved **Level 2!**",
        ),
        (MessageType.premium_guild_tier_3, "", "G has achieved **Level 3!**"),
        (
            MessageType.premium_guild_tier_3,
            "3",
            "**3** times! G has achieved **Level 3!**",
        ),
        (MessageType.channel_follow_add, "news", "has added news to this channel"),
        (MessageType.thread_created, "t", "started a thread: **t**"),
        (MessageType.guild_discovery_disqualified, "", "removed from Server Discovery"),
        (MessageType.guild_discovery_requalified, "", "eligible for Server Discovery"),
        (MessageType.guild_discovery_grace_period_initial_warning, "", "for 1 week"),
        (MessageType.guild_discovery_grace_period_final_warning, "", "for 3 weeks"),
        (MessageType.guild_invite_reminder, "", "Wondering who to invite?"),
    ],
)
def test_system_content(
    world: World, kind: MessageType, content: str, expected: str
) -> None:
    rig = Rig(world)
    message = system_message(rig, kind, content=content)
    text = message._system_content("G")
    assert text is not None
    assert expected in text
    assert message.is_system()


def test_system_content_other_types(world: World) -> None:
    rig = Rig(world)
    author = rig.make_message().author.name

    default = system_message(rig, MessageType.default, content="plain")
    assert default._system_content("G") == "plain"
    assert not default.is_system()
    assert (
        system_message(rig, MessageType.reply, content="r")._system_content("G") == "r"
    )
    assert system_message(rig, MessageType.call)._system_content("G") is None

    joined = system_message(rig, MessageType.new_member)._system_content("G")
    assert joined is not None
    assert author in joined

    for kind, verb in (
        (MessageType.recipient_add, "added"),
        (MessageType.recipient_remove, "removed"),
    ):
        message = system_message(rig, kind, mentions=[rig.payload(t.user.User)])
        message.mentions = [message.author]
        text = message._system_content("G")
        assert text is not None
        assert verb in text
        assert "thread" in text
        with patch.object(
            Message,
            "channel",
            new_callable=PropertyMock,
            return_value=SimpleNamespace(type=ChannelType.group),
        ):
            group_text = message._system_content("G")
        assert group_text is not None
        assert "group" in group_text

    streaming = system_message(rig, MessageType.guild_stream)
    streaming.author = SimpleNamespace(
        name="streamer", activity=SimpleNamespace(name="game")
    )  # type: ignore[assignment]
    assert streaming._system_content("G") == "streamer is live! Now streaming game"

    starter = system_message(rig, MessageType.thread_starter_message)
    starter.reference = None
    assert "couldn't load" in starter._system_content("G")  # type: ignore[operator]
    starter.reference = SimpleNamespace(resolved=SimpleNamespace(content="first"))  # type: ignore[assignment]
    assert starter._system_content("G") == "first"


def test_default_system_content_prefers_a_forwarded_snapshot(world: World) -> None:
    message = Rig(world).make_message(content="outer")
    message.snapshots = [SimpleNamespace(message=SimpleNamespace(content="inner"))]  # type: ignore[list-item]
    assert message._system_content("G") == "inner"


def test_partial_message_basics(world: World) -> None:
    rig = Rig(world)
    partial = PartialMessage(
        channel=rig.channel, id=discord.utils.time_snowflake(discord.utils.utcnow())
    )
    assert partial.created_at.year >= 2024
    assert "PartialMessage" in repr(partial)
    assert rig.run(partial.get_poll()) is None
    assert partial.poll is None
