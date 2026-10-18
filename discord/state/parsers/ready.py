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

"""Session lifecycle gateway event parsers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from ... import utils
from ...flags import ApplicationFlags
from ...raw_models import GatewayRateLimit
from ...user import ClientUser

if TYPE_CHECKING:
    from ...types.gateway import (
        GatewayRateLimit as GatewayRateLimitPayload,
        ReadyEvent,
        ResumedEvent,
    )
    from ...types.guild import Guild as GuildPayload
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_ready(state: ConnectionState, data: ReadyEvent) -> None:
    """Handle the ``READY`` gateway event."""
    if state._ready_task is not None:
        state._ready_task.cancel()

    state._ready_state = asyncio.Queue()
    state.clear(views=False)
    await state._clear_cache()
    state.user = ClientUser(state=state, data=data["user"])
    await state.store_user(data["user"])

    if state.application_id is None:
        try:
            application = data["application"]
        except KeyError:
            pass
        else:
            state.application_id = utils._get_as_snowflake(application, "id")
            # flags will always be present here
            state.application_flags = ApplicationFlags._from_value(application["flags"])

    for guild_data in data["guilds"]:
        await state._add_guild_from_data(cast("GuildPayload", guild_data))

    state.dispatch("connect")
    state._ready_task = asyncio.create_task(state._delay_ready())


async def parse_resumed(state: ConnectionState, _data: ResumedEvent) -> None:
    """Handle the ``RESUMED`` gateway event."""
    state.dispatch("resumed")


async def parse_rate_limited(
    state: ConnectionState, data: GatewayRateLimitPayload
) -> None:
    """Handle the ``RATE_LIMITED`` gateway event."""
    payload = GatewayRateLimit(data)
    _log.warning(
        "Gateway opcode %s is rate limited, retry in %.2f seconds.",
        payload.opcode,
        payload.retry_after,
    )
    state.process_gateway_rate_limit(payload)
    state.dispatch("gateway_rate_limited", payload)
