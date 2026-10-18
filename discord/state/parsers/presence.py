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

"""Presence gateway event parsers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ... import utils
from ...member import Member

if TYPE_CHECKING:
    from ...types.activity import PartialPresenceUpdate
    from ...types.user import User as UserPayload
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_presence_update(
    state: ConnectionState, data: PartialPresenceUpdate
) -> None:
    """Handle the ``PRESENCE_UPDATE`` gateway event."""
    guild_id = utils._get_as_snowflake(data, "guild_id")
    # guild_id won't be None here
    guild = await state._get_guild(guild_id)
    if guild is None:
        _log.debug(
            "PRESENCE_UPDATE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )
        return

    user = data["user"]
    member_id = int(user["id"])
    member = await guild.get_member(member_id)
    if member is None:
        _log.debug(
            "PRESENCE_UPDATE referencing an unknown member ID: %s. Discarding",
            member_id,
        )
        return

    old_member = Member._copy(member)
    user_update = member._presence_update(data=data, user=cast("UserPayload", user))
    await guild._add_member(member)
    if user_update:
        state.dispatch("user_update", user_update[0], user_update[1])

    state.dispatch("presence_update", old_member, member)
