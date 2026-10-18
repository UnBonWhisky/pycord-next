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

import pytest

from discord import types as t
from discord.poll import Poll, PollAnswer, PollAnswerCount, PollResults
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    MESSAGE_ID,
    OTHER_USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    member_payload,
    payload,
    ready,
    recorder,  # noqa: F401
    user_payload,
)

if TYPE_CHECKING:
    from discord.state import ConnectionState

UNICODE = {"id": None, "name": "\N{THUMBS UP SIGN}"}
CUSTOM = {"id": "2100000000000000099", "name": "pycord"}


async def setup_guild_message(state: ConnectionState, **fields: Any) -> Any:
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick=None), "guild_id": str(GUILD_ID)}
    )
    message = payload(
        t.message.Message,
        id=str(MESSAGE_ID),
        channel_id=str(CHANNEL_ID),
        guild_id=str(GUILD_ID),
        author=user_payload(OTHER_USER_ID),
        content="hello",
        type=0,
        edited_timestamp=None,
        reactions=[],
        **fields,
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "thread",
        "poll",
    ):
        message.pop(key, None)
    await state.parsers["MESSAGE_CREATE"](message)
    cached = await state._get_message(MESSAGE_ID)
    assert cached is not None
    return cached


def reaction_event(
    emoji: dict[str, Any], user_id: int = OTHER_USER_ID
) -> dict[str, Any]:
    return {
        "user_id": str(user_id),
        "channel_id": str(CHANNEL_ID),
        "message_id": str(MESSAGE_ID),
        "guild_id": str(GUILD_ID),
        "emoji": emoji,
        "burst": False,
        "type": 0,
    }


@pytest.mark.asyncio
async def test_reaction_add_and_remove_update_the_cached_message(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    message = await setup_guild_message(state)

    await state.parsers["MESSAGE_REACTION_ADD"](reaction_event(UNICODE))
    assert recorder.names()[-2:] == ["raw_reaction_add", "reaction_add"]
    reaction, user = recorder.last("reaction_add")
    assert message.reactions == [reaction]
    assert reaction.count == 1
    assert user.id == OTHER_USER_ID

    await state.parsers["MESSAGE_REACTION_ADD"](reaction_event(UNICODE))
    assert message.reactions[0].count == 2

    await state.parsers["MESSAGE_REACTION_REMOVE"](reaction_event(UNICODE))
    removed, user = recorder.last("reaction_remove")
    assert removed.count == 1
    assert user.id == OTHER_USER_ID

    await state.parsers["MESSAGE_REACTION_REMOVE"](reaction_event(UNICODE))
    assert message.reactions == []


@pytest.mark.asyncio
async def test_reaction_remove_of_unknown_reaction_only_dispatches_raw(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await setup_guild_message(state)
    before = len(recorder.events)

    await state.parsers["MESSAGE_REACTION_REMOVE"](reaction_event(UNICODE))

    assert recorder.names()[before:] == ["raw_reaction_remove"]


@pytest.mark.asyncio
async def test_reaction_events_for_uncached_messages_are_raw_only(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    for event in ("ADD", "REMOVE"):
        await state.parsers[f"MESSAGE_REACTION_{event}"](reaction_event(UNICODE))
    await state.parsers["MESSAGE_REACTION_REMOVE_ALL"](
        {
            "channel_id": str(CHANNEL_ID),
            "message_id": str(MESSAGE_ID),
            "guild_id": str(GUILD_ID),
        }
    )
    await state.parsers["MESSAGE_REACTION_REMOVE_EMOJI"](
        {
            "channel_id": str(CHANNEL_ID),
            "message_id": str(MESSAGE_ID),
            "guild_id": str(GUILD_ID),
            "emoji": UNICODE,
        }
    )
    assert recorder.names()[1:] == [
        "raw_reaction_add",
        "raw_reaction_remove",
        "raw_reaction_clear",
        "raw_reaction_clear_emoji",
    ]


@pytest.mark.asyncio
async def test_reaction_clear_and_clear_emoji(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    message = await setup_guild_message(state)
    await state.parsers["MESSAGE_REACTION_ADD"](reaction_event(UNICODE))
    await state.parsers["MESSAGE_REACTION_ADD"](reaction_event(CUSTOM))
    assert len(message.reactions) == 2

    base = {
        "channel_id": str(CHANNEL_ID),
        "message_id": str(MESSAGE_ID),
        "guild_id": str(GUILD_ID),
    }
    await state.parsers["MESSAGE_REACTION_REMOVE_EMOJI"]({**base, "emoji": UNICODE})
    (cleared,) = recorder.last("reaction_clear_emoji")
    assert str(cleared.emoji) == UNICODE["name"]
    assert len(message.reactions) == 1

    before = len(recorder.events)
    await state.parsers["MESSAGE_REACTION_REMOVE_EMOJI"]({**base, "emoji": UNICODE})
    assert recorder.names()[before:] == ["raw_reaction_clear_emoji"]

    old = list(message.reactions)
    await state.parsers["MESSAGE_REACTION_REMOVE_ALL"](base)
    assert recorder.last("reaction_clear") == (message, old)
    assert message.reactions == []


def make_poll(with_results: bool = True) -> Poll:
    poll = Poll("Best?", answers=[PollAnswer("a"), PollAnswer("b")])
    for number, answer in enumerate(poll.answers, start=1):
        answer.id = number
        answer._poll = poll
    if with_results:
        poll.results = PollResults(
            {
                "is_finalized": False,
                "answer_counts": [{"id": 1, "count": 2, "me_voted": False}],
            }
        )
    return poll


def vote_event(answer_id: int, *, guild: bool = True) -> dict[str, Any]:
    data = {
        "user_id": str(OTHER_USER_ID),
        "channel_id": str(CHANNEL_ID),
        "message_id": str(MESSAGE_ID),
        "answer_id": answer_id,
    }
    if guild:
        data["guild_id"] = str(GUILD_ID)
    return data


@pytest.mark.asyncio
async def test_poll_vote_add_counts_existing_and_new_answers(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await setup_guild_message(state)
    poll = make_poll()
    await state.store_poll(poll, MESSAGE_ID)

    await state.parsers["MESSAGE_POLL_VOTE_ADD"](vote_event(1))
    assert poll.results is not None
    assert poll.results._answer_counts[1].count == 3
    voted_poll, voter, answer = recorder.last("poll_vote_add")
    assert voted_poll is poll
    assert voter.id == OTHER_USER_ID
    assert answer.id == 1

    await state.parsers["MESSAGE_POLL_VOTE_ADD"](vote_event(2))
    new = poll.results._answer_counts[2]
    assert isinstance(new, PollAnswerCount)
    assert new.count == 1

    await state.parsers["MESSAGE_POLL_VOTE_ADD"](vote_event(99))
    assert 99 not in poll.results._answer_counts
    assert recorder.last("poll_vote_add")[2].id == 2


@pytest.mark.asyncio
async def test_poll_vote_remove_decrements_known_counts(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await setup_guild_message(state)
    poll = make_poll()
    await state.store_poll(poll, MESSAGE_ID)

    await state.parsers["MESSAGE_POLL_VOTE_REMOVE"](vote_event(1))
    assert poll.results is not None
    assert poll.results._answer_counts[1].count == 1
    assert recorder.last("poll_vote_remove")[2].id == 1

    await state.parsers["MESSAGE_POLL_VOTE_REMOVE"](vote_event(2))
    assert 2 not in poll.results._answer_counts
    assert recorder.last("poll_vote_remove")[2].id == 2

    before = len(recorder.events)
    await state.parsers["MESSAGE_POLL_VOTE_REMOVE"](vote_event(99))
    assert recorder.names()[before:] == ["raw_poll_vote_remove"]


@pytest.mark.asyncio
async def test_poll_vote_without_guild_resolves_a_user(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    state._cache_users = True
    await state.store_user(user_payload(OTHER_USER_ID))
    poll = make_poll(with_results=False)
    await state.store_poll(poll, MESSAGE_ID)

    await state.parsers["MESSAGE_POLL_VOTE_ADD"](vote_event(1, guild=False))

    _, voter, answer = recorder.last("poll_vote_add")
    assert voter.id == OTHER_USER_ID
    assert answer.id == 1
    assert poll.results is None


@pytest.mark.asyncio
async def test_poll_vote_for_unknown_poll_is_raw_only(
    state: ConnectionState,
    recorder: Recorder,  # noqa: F811
) -> None:
    await ready(state)
    await state.parsers["MESSAGE_POLL_VOTE_ADD"](vote_event(1))
    await state.parsers["MESSAGE_POLL_VOTE_REMOVE"](vote_event(1))
    assert recorder.names()[1:] == ["raw_poll_vote_add", "raw_poll_vote_remove"]
