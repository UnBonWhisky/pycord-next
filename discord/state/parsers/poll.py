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

"""Poll vote gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...poll import PollAnswerCount
from ...raw_models import RawMessagePollVoteEvent

if TYPE_CHECKING:
    from ...member import Member
    from ...types.raw_models import MessagePollVoteEvent
    from ...user import User
    from ..state import ConnectionState


async def _get_voter(
    state: ConnectionState, raw: RawMessagePollVoteEvent
) -> User | Member | None:
    guild = await state._get_guild(raw.guild_id)
    if guild:
        return await guild.get_member(raw.user_id)
    return await state.get_user(raw.user_id)


async def parse_message_poll_vote_add(
    state: ConnectionState, data: MessagePollVoteEvent
) -> None:
    """Handle the ``MESSAGE_POLL_VOTE_ADD`` gateway event."""
    raw = RawMessagePollVoteEvent(data, True)
    user = await _get_voter(state, raw)
    state.dispatch("raw_poll_vote_add", raw)

    poll = await state.get_poll(raw.message_id)
    # if message was cached, poll has already updated but votes haven't
    if poll and poll.results:
        answer = poll.get_answer(raw.answer_id)
        counts = poll.results._answer_counts
        if answer is not None:
            if raw.answer_id in counts:
                counts[raw.answer_id].count += 1
            else:
                counts[raw.answer_id] = PollAnswerCount(
                    {
                        "id": raw.answer_id,
                        "count": 1,
                        "me_voted": False,
                    }
                )
        await state.store_poll(poll, raw.message_id)
    if poll is not None and user is not None:
        answer = poll.get_answer(raw.answer_id)
        if answer is not None:
            state.dispatch("poll_vote_add", poll, user, answer)


async def parse_message_poll_vote_remove(
    state: ConnectionState, data: MessagePollVoteEvent
) -> None:
    """Handle the ``MESSAGE_POLL_VOTE_REMOVE`` gateway event."""
    raw = RawMessagePollVoteEvent(data, False)
    user = await _get_voter(state, raw)
    state.dispatch("raw_poll_vote_remove", raw)

    poll = await state.get_poll(raw.message_id)
    # if message was cached, poll has already updated but votes haven't
    if poll and poll.results:
        answer = poll.get_answer(raw.answer_id)
        counts = poll.results._answer_counts
        if answer is not None and raw.answer_id in counts:
            counts[raw.answer_id].count -= 1
        await state.store_poll(poll, raw.message_id)
    if poll is not None and user is not None:
        answer = poll.get_answer(raw.answer_id)
        if answer is not None:
            state.dispatch("poll_vote_remove", poll, user, answer)
