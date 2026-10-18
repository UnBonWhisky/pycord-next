"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from discord import SyncCacheAccessError, types as t
from discord.channel import PartialGuildChannel, PartialMessageable
from discord.enums import MessageType, ReactionType
from discord.guild import PartialGuild
from discord.iterators import MessagePinIterator
from discord.member import Member
from discord.message import (
    Attachment,
    ForwardedMessage,
    Message,
    MessageCall,
    MessageReference,
    PartialMessage,
)
from discord.raw_models import (
    RawReactionClearEmojiEvent,
    RawVoiceServerUpdateEvent,
    RawVoiceStateUpdateEvent,
)
from discord.reaction import Reaction
from discord.role import Role
from discord.ui import DesignerView, View
from tests.models.context import World
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient

CHANNEL_MENTION_ID = 5_000_000_000_000_000_001
ROLE_ID = 5_000_000_000_000_000_002
UNCACHED_ROLE_ID = 5_000_000_000_000_000_003


@pytest.fixture(params=["memory", "redis"])
def kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def w(loop: asyncio.AbstractEventLoop, http: HTTPClient, kind: str) -> World:
    return World(build_state(loop, http, kind))


def message(world: World, **fields: Any) -> Message:
    defaults: dict[str, Any] = {
        "type": 0,
        "mentions": [],
        "mention_roles": [],
        "reactions": [],
        "guild_id": str(world.guild.id),
        "channel_id": str(world.channel.id),
    }
    payload = world.payload(t.message.Message, **{**defaults, **fields})
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "poll",
        "thread",
        "call",
        "interaction",
        "interaction_metadata",
        "member",
    ):
        payload.pop(key, None)
    built = Message(state=world.state, channel=world.channel, data=payload)
    world.run(world.state._populate_message(built, payload))
    return built


def add_role(world: World, role_id: int, name: str = "mod") -> Role:
    role = Role(
        guild=world.guild,
        state=world.state,
        data=world.payload(t.role.Role, id=str(role_id), name=name, position=1),
    )
    world.run(world.state._guild_bucket("roles", world.guild.id).set(role_id, role))
    return role


class TestAttachment:
    def attachment(self, world: World, **fields: Any) -> Attachment:
        return Attachment(
            data=world.payload(t.message.Attachment, **fields), state=world.state
        )

    def test_spoiler_from_flag(self, w: World) -> None:
        assert self.attachment(w, filename="a.png", flags=1 << 3).is_spoiler()

    def test_spoiler_from_filename(self, w: World) -> None:
        assert self.attachment(w, filename="SPOILER_a.png", flags=0).is_spoiler()

    def test_not_spoiler(self, w: World) -> None:
        assert not self.attachment(w, filename="a.png", flags=1 << 1).is_spoiler()

    def test_with_changes_sets_description_and_spoiler(self, w: World) -> None:
        original = self.attachment(w, filename="a.png", flags=0, description="old")
        changed = original.with_changes(description="new", is_spoiler=True)
        assert changed.description == "new"
        assert changed.is_spoiler()
        assert changed.flags.is_spoiler
        assert original.description == "old"
        assert not original.is_spoiler()
        payload = changed.to_dict()
        assert payload["description"] == "new"
        assert payload["is_spoiler"] is True

    def test_with_changes_can_clear_a_legacy_spoiler(self, w: World) -> None:
        original = self.attachment(w, filename="SPOILER_a.png", flags=0)
        assert original.is_spoiler()
        assert not original.with_changes(is_spoiler=False).is_spoiler()
        assert original.with_changes(is_spoiler=False).to_dict()["is_spoiler"] is False

    def test_with_changes_keeps_untouched_values(self, w: World) -> None:
        original = self.attachment(w, filename="a.png", flags=1 << 3, description="d")
        same = original.with_changes()
        assert same.description == "d"
        assert same.is_spoiler()


class TestMentions:
    def test_channel_mentions_sync_matches_async(self, w: World) -> None:
        msg = message(
            w, content=f"hi <#{w.channel.id}> <#{w.channel.id}> <#{CHANNEL_MENTION_ID}>"
        )
        assert msg.raw_channel_mentions == [
            w.channel.id,
            w.channel.id,
            CHANNEL_MENTION_ID,
        ]
        assert w.run(msg.get_channel_mentions()) == [w.channel]
        if w.state.cache.supports_sync:
            assert msg.channel_mentions == [w.channel]
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = msg.channel_mentions

    def test_role_mentions(self, w: World) -> None:
        role = add_role(w, ROLE_ID)
        msg = message(w, mention_roles=[str(ROLE_ID), str(UNCACHED_ROLE_ID)])
        assert msg.role_mention_ids == [ROLE_ID, UNCACHED_ROLE_ID]
        assert w.run(msg.get_role_mentions()) == [role]
        assert msg.role_mentions == [role]

    def test_role_mentions_are_empty_outside_guilds(self, w: World) -> None:
        msg = message(w)
        msg.guild_id = None
        assert w.run(msg.get_role_mentions()) == []
        assert w.run(msg.get_channel_mentions()) == []

    def test_clean_content_matches(self, w: World) -> None:
        add_role(w, ROLE_ID, name="mod")
        msg = message(
            w,
            content=f"<#{w.channel.id}> <@&{ROLE_ID}> @everyone",
            mention_roles=[str(ROLE_ID)],
        )
        cleaned = w.run(msg.get_clean_content())
        assert cleaned.startswith(f"#{w.channel.name} @mod")
        assert "@everyone" not in cleaned.replace("@\u200beveryone", "")
        if w.state.cache.supports_sync:
            assert msg.clean_content == cleaned
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = msg.clean_content

    @pytest.mark.parametrize(
        ("kind_", "content", "expected"),
        [
            (MessageType.premium_guild_tier_1, "", "has achieved **Level 1!**"),
            (MessageType.premium_guild_tier_2, "3", "has achieved **Level 2!**"),
            (MessageType.premium_guild_tier_3, "", "has achieved **Level 3!**"),
        ],
    )
    def test_system_content_names_the_guild(
        self, w: World, kind_: MessageType, content: str, expected: str
    ) -> None:
        msg = message(w, type=kind_.value, content=content)
        text = w.run(msg.get_system_content())
        assert text is not None
        assert f"{w.guild.name} {expected}" in text
        if w.state.cache.supports_sync:
            assert msg.system_content == text
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = msg.system_content

    def test_system_content_default_returns_content(self, w: World) -> None:
        msg = message(w, content="plain")
        assert w.run(msg.get_system_content()) == "plain"


class TestRelationships:
    def test_message_channel_and_guild(self, w: World) -> None:
        msg = message(w)
        assert w.run(msg.get_channel()) == w.channel
        assert w.run(msg.get_guild()) == w.guild
        if w.state.cache.supports_sync:
            assert msg.channel is w.channel
            assert msg.guild is w.guild
        else:
            assert isinstance(msg.channel, PartialMessageable)
            assert isinstance(msg.guild, PartialGuild)
        assert msg.channel.id == w.channel.id
        assert msg.guild is not None
        assert msg.guild.id == w.guild.id

    def test_message_channel_falls_back_to_a_partial(self, w: World) -> None:
        msg = message(w)
        msg.channel_id = 123
        assert isinstance(msg.channel, PartialMessageable)
        assert w.run(msg.get_channel()) is None

    def test_jump_url(self, w: World) -> None:
        msg = message(w)
        assert msg.jump_url == (
            f"https://discord.com/channels/{w.guild.id}/{w.channel.id}/{msg.id}"
        )

    def test_reaction_message(self, w: World) -> None:
        msg = message(w)
        w.run(w.state._store_message(msg))
        reaction = Reaction(
            message=msg,
            data={"count": 1, "me": False, "emoji": {"id": None, "name": "x"}},  # type: ignore[typeddict-item]
        )
        assert reaction.guild_id == w.guild.id
        assert w.run(reaction.get_message()) == msg
        if w.state.cache.supports_sync and w.state._messages is not None:
            assert reaction.message is msg
        else:
            assert isinstance(reaction.message, PartialMessage)
            assert reaction.message.guild is not None
            assert reaction.message.guild.id == w.guild.id

    def test_partial_message_guild(self, w: World) -> None:
        partial = PartialMessage(
            channel=PartialMessageable(state=w.state, id=1), id=2, guild_id=3
        )
        assert partial.guild is not None
        assert partial.guild.id == 3
        assert (
            PartialMessage(channel=PartialMessageable(state=w.state, id=1), id=2).guild
            is None
        )


class TestReference:
    def test_cached_message(self, w: World) -> None:
        msg = message(w)
        w.run(w.state._store_message(msg))
        ref = MessageReference.with_state(
            w.state, {"message_id": str(msg.id), "channel_id": str(w.channel.id)}
        )
        assert w.run(ref.get_cached_message()) == msg
        if w.state.cache.supports_sync:
            assert ref.cached_message == msg
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = ref.cached_message

    def test_no_message_id(self, w: World) -> None:
        ref = MessageReference(message_id=None, channel_id=1)  # type: ignore[arg-type]
        ref._state = w.state
        assert ref.cached_message is None
        assert w.run(ref.get_cached_message()) is None


class TestCall:
    def test_participants(self, w: World) -> None:
        w.run(w.state.store_user(w.payload(t.user.User, id="77")))
        call = MessageCall(w.state, {"participants": ["77", "78"]})
        assert call.participant_ids == [77, 78]
        participants = w.run(call.get_participants())
        assert [p.id for p in participants] == [77, 78]
        assert type(participants[1]).__name__ == "Object"
        if w.state.cache.supports_sync:
            assert call.participants == participants
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = call.participants


class TestForwarded:
    def forwarded(self, world: World, guild_id: int | None) -> ForwardedMessage:
        ref = MessageReference.with_state(
            world.state,
            {
                "message_id": "9",
                "channel_id": str(world.channel.id),
                **({"guild_id": str(guild_id)} if guild_id else {}),
                "type": 1,
            },
        )
        data = world.payload(
            t.message.ForwardedMessage,
            type=0,
            mentions=[],
            mention_roles=[str(ROLE_ID), str(UNCACHED_ROLE_ID)],
        )
        return ForwardedMessage(state=world.state, reference=ref, data=data)

    def test_role_mentions(self, w: World) -> None:
        role = add_role(w, ROLE_ID)
        fm = self.forwarded(w, w.guild.id)
        assert fm.role_mention_ids == [ROLE_ID, UNCACHED_ROLE_ID]
        assert w.run(fm.get_role_mentions()) == [role]
        if w.state.cache.supports_sync:
            assert fm.role_mentions == [role]
        else:
            with pytest.raises(SyncCacheAccessError):
                _ = fm.role_mentions

    def test_role_mentions_without_a_guild(self, w: World) -> None:
        fm = self.forwarded(w, None)
        assert w.run(fm.get_role_mentions()) == []
        assert fm.role_mentions == []

    def test_relationships(self, w: World) -> None:
        fm = self.forwarded(w, w.guild.id)
        assert fm.channel.id == w.channel.id
        assert fm.guild.id == w.guild.id  # type: ignore[union-attr]
        if w.state.cache.supports_sync:
            assert fm.channel is w.channel
            assert fm.guild is w.guild
        else:
            assert isinstance(fm.channel, PartialMessageable)
            assert isinstance(fm.guild, PartialGuild)


class TestGetView:
    def test_tracked_view_is_returned(self, w: World) -> None:
        msg = message(w, flags=0, components=[])
        sentinel = object()
        w.state.get_message_view = lambda message_id: (  # type: ignore[attr-defined]
            sentinel if message_id == msg.id else None
        )
        assert msg.get_view() is sentinel

    def test_view_is_built_from_the_components(self, w: World) -> None:
        msg = message(w, flags=0, components=[])
        w.state.get_message_view = lambda _: None  # type: ignore[attr-defined]
        v2 = message(w, flags=1 << 15, components=[])

        async def build() -> tuple[Any, Any]:
            return msg.get_view(), v2.get_view()

        view, designer = w.run(build())
        assert isinstance(view, View)
        assert not view._store
        assert isinstance(designer, DesignerView)


class TestRawEvents:
    def test_clear_emoji_reads_the_optional_fields_with_defaults(
        self, w: World
    ) -> None:
        emoji = w.emoji
        raw = RawReactionClearEmojiEvent(
            {
                "channel_id": "2",
                "message_id": "3",
                "guild_id": "4",
                "emoji": {"id": None, "name": "x"},
            },
            emoji,
        )
        assert (raw.channel_id, raw.message_id, raw.guild_id) == (2, 3, 4)
        assert raw.burst is False
        assert raw.burst_colours == []
        assert raw.burst_colors == []
        assert raw.type is ReactionType.normal

    def voice_state(self, world: World) -> RawVoiceStateUpdateEvent:
        return RawVoiceStateUpdateEvent(
            data={
                "guild_id": str(world.guild.id),
                "channel_id": str(world.channel.id),
                "user_id": "1",
                "session_id": "s",
            },  # type: ignore[arg-type]
            state=world.state,
        )

    def test_voice_state_relationships(self, w: World) -> None:
        raw = self.voice_state(w)
        assert w.run(raw.get_guild()) == w.guild
        assert w.run(raw.get_channel()) == w.channel
        assert raw.guild is not None
        assert raw.guild.id == w.guild.id
        assert raw.channel is not None
        assert raw.channel.id == w.channel.id
        if w.state.cache.supports_sync:
            assert raw.guild is w.guild
            assert raw.channel is w.channel
        else:
            assert isinstance(raw.guild, PartialGuild)
            assert isinstance(raw.channel, PartialGuildChannel)

    def test_voice_state_without_channel(self, w: World) -> None:
        raw = RawVoiceStateUpdateEvent(
            data={
                "guild_id": "1",
                "channel_id": None,
                "user_id": "1",
                "session_id": "s",
            },  # type: ignore[arg-type]
            state=w.state,
        )
        assert raw.channel is None

    def test_voice_server_guild(self, w: World) -> None:
        raw = RawVoiceServerUpdateEvent(
            data={"guild_id": str(w.guild.id), "token": "t", "endpoint": None},  # type: ignore[arg-type]
            state=w.state,
        )
        assert w.run(raw.get_guild()) == w.guild
        assert raw.guild.id == w.guild.id
        if w.state.cache.supports_sync:
            assert raw.guild is w.guild
        else:
            assert isinstance(raw.guild, PartialGuild)


class TestIterators:
    def user_payloads(self, world: World) -> list[Any]:
        return [
            world.payload(t.user.User, id="31"),
            world.payload(t.user.User, id="32"),
        ]

    def test_reaction_users_prefer_cached_members(self, w: World) -> None:
        member = Member(
            data=w.payload(
                t.member.MemberWithUser, user=w.payload(t.user.User, id="31")
            ),
            guild=w.guild,
            state=w.state,
        )
        w.run(w.state._guild_bucket("members", w.guild.id).set(31, member))
        w.state.http.get_reaction_users = AsyncMock(return_value=self.user_payloads(w))
        msg = message(w)
        reaction = Reaction(
            message=msg,
            data={"count": 2, "me": False, "emoji": {"id": None, "name": "x"}},  # type: ignore[typeddict-item]
        )
        users = w.run(reaction.users().flatten())
        assert sorted(u.id for u in users) == [31, 32]
        by_id = {u.id: u for u in users}
        assert by_id[31].id == member.id
        assert isinstance(by_id[31], Member)
        if w.state.cache.supports_sync:
            assert by_id[31] is member
        assert not isinstance(by_id[32], Member)

    def test_pins_are_populated(self, w: World) -> None:
        inner = w.payload(
            t.message.Message,
            type=0,
            mentions=[],
            mention_roles=[str(ROLE_ID)],
            reactions=[],
            guild_id=str(w.guild.id),
        )
        for key in (
            "message_reference",
            "referenced_message",
            "message_snapshots",
            "poll",
            "thread",
            "call",
            "interaction",
            "interaction_metadata",
            "member",
        ):
            inner.pop(key, None)
        role = add_role(w, ROLE_ID)
        w.state.http.pins_from = AsyncMock(
            return_value={
                "items": [{"pinned_at": "2024-01-01T00:00:00+00:00", "message": inner}],
                "has_more": False,
            }
        )
        pins = w.run(MessagePinIterator(w.channel, 10).flatten())
        assert len(pins) == 1
        assert pins[0].message.role_mentions == [role]
