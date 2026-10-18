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

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.poll import Poll, PollAnswer, PollAnswerCount, PollMedia, PollResults
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


def test_poll_media_emoji_forms() -> None:
    assert PollMedia("q").to_dict() == {"text": "q"}
    assert PollMedia("q", "\N{FIRE}").to_dict() == {
        "text": "q",
        "emoji": {"name": "\N{FIRE}"},
    }
    assert PollMedia("q", discord.PartialEmoji(name="x", id=5)).to_dict() == {
        "text": "q",
        "emoji": {"id": "5"},
    }
    assert PollMedia("q", discord.PartialEmoji(name="x")).to_dict() == {
        "text": "q",
        "emoji": {"name": "x"},
    }


def test_answer_counts_and_results() -> None:
    poll = Poll("q", answers=[PollAnswer("a"), PollAnswer("b")])
    first, second = poll.answers
    first.id, second.id = 1, 2
    first._poll = second._poll = poll

    assert first.count is None
    poll.results = PollResults(
        {
            "is_finalized": True,
            "answer_counts": [{"id": 1, "count": 4, "me_voted": True}],
        }
    )
    assert first.count == 4
    assert second.count == 0
    assert poll.total_votes() == 4
    assert poll.has_ended() is True
    assert isinstance(poll.results.answer_counts[0], PollAnswerCount)

    detached = PollAnswer("c")
    assert detached.count is None
    assert Poll("q").has_ended() is None
    assert Poll("q").total_votes() is None


def test_answer_voters_need_a_message_poll() -> None:
    poll = Poll("q", answers=[PollAnswer("a")])
    answer = poll.answers[0]
    with pytest.raises(RuntimeError, match="existing message poll"):
        answer.voters()
    answer._poll = poll
    with pytest.raises(RuntimeError, match="existing message poll"):
        answer.voters()


def test_answer_voters_with_a_message(world: World) -> None:
    rig = Rig(world)
    message = rig.make_message()
    poll = Poll.from_dict(
        {
            "question": {"text": "q"},
            "answers": [{"answer_id": 3, "poll_media": {"text": "a"}}],
            "duration": 24,
            "allow_multiselect": False,
            "layout_type": 1,
            "results": {
                "is_finalized": False,
                "answer_counts": [{"id": 3, "count": 7, "me_voted": False}],
            },
            "expiry": "2030-01-01T00:00:00+00:00",
        },
        message=message,
    )
    answer = poll.answers[0]
    assert poll.expiry is not None
    assert answer.voters(after=discord.Object(id=1)).limit == 7
    assert answer.voters(limit=2).limit == 2
    plain = PollAnswer("b")
    plain._poll = poll
    plain.id = 9
    assert plain.voters().limit == 100


def test_poll_from_dict_and_answers() -> None:
    assert Poll.from_dict({}) is None  # type: ignore[arg-type]
    poll = Poll("q")
    assert poll.add_answer("one", emoji="\N{FIRE}") is poll
    assert poll.answers[0].emoji == "\N{FIRE}"
    with pytest.raises(ValueError, match="between 1 and 55"):
        poll.add_answer("x" * 56)
    for number in range(9):
        poll.add_answer(f"a{number}")
    with pytest.raises(ValueError, match="up to 10 answers"):
        poll.add_answer("overflow")

    started = Poll("q")
    started._expiry = "2030-01-01T00:00:00+00:00"
    with pytest.raises(RuntimeError, match="existing poll"):
        started.add_answer("late")
    attached = Poll("q")
    attached._message = object()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="existing poll"):
        attached.add_answer("late")


async def test_ending_a_poll() -> None:
    detached = Poll("q")
    with pytest.raises(RuntimeError, match="received from a message"):
        await detached.end()
    attached = Poll("q")
    message = AsyncMock()
    message.end_poll.return_value = "ended"
    attached._message = message
    assert await attached.end() == "ended"
    message.end_poll.assert_awaited_once_with()


def test_template_partial_state(world: World) -> None:
    rig = Rig(world)
    template = discord.Template(
        state=rig.state,
        data=rig.payload(
            t.template.Template,
            code="abc",
            source_guild_id="9",
            serialized_source_guild=rig.payload(
                t.guild.Guild,
                id="9",
                channels=[],
                roles=[],
                emojis=[],
                stickers=[],
                members=[],
                voice_states=[],
                threads=[],
                stage_instances=[],
                guild_scheduled_events=[],
                soundboard_sounds=[],
                unavailable=False,
            ),
        ),
    )
    guild_state = template.source_guild._state
    assert guild_state.shard_count == rig.state.shard_count
    rig.state.user = rig.world.me
    assert guild_state.user is rig.world.me
    assert guild_state.self_id == rig.world.me.id
    assert guild_state.member_cache_flags is rig.state.member_cache_flags
    assert guild_state.create_user(rig.payload(t.user.User, id="31")).id == 31
    assert rig.run(guild_state.store_user(rig.payload(t.user.User, id="32"))).id == 32
    assert rig.run(guild_state.get_channel(1)) is None
    assert rig.run(guild_state.store_emoji(template.source_guild, {})) is None
    assert guild_state._get_voice_client(1) is None
    assert rig.run(guild_state._get_message(1)) is None
    assert rig.run(guild_state._get_guild(rig.guild.id)) is rig.guild
    assert guild_state.cache is guild_state.cache
    assert guild_state._guild_bucket("roles", 9) is not None
    assert rig.run(guild_state.query_members()) == []
    with pytest.raises(AttributeError, match="does not support http methods"):
        guild_state.http.anything  # noqa: B018
    with pytest.raises(AttributeError, match="does not support 'nope'"):
        guild_state.nope  # noqa: B018
