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

"""Typing gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...raw_models import RawTypingEvent
from ._common import get_raw_member

if TYPE_CHECKING:
    from ...types.raw_models import TypingEvent
    from ..state import ConnectionState


async def parse_typing_start(state: ConnectionState, data: TypingEvent) -> None:
    """Handle the ``TYPING_START`` gateway event."""
    raw = RawTypingEvent(data)

    raw.member = await get_raw_member(state, data, raw.guild_id)
    state.dispatch("raw_typing", raw)

    channel, _ = await state._get_guild_channel(data)
    user = raw.member or await state._get_typing_user(channel, raw.user_id)

    if user is not None:
        state.dispatch("typing", channel, user, raw.when)
