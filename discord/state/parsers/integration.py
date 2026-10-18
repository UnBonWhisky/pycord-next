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

"""Integration and webhook gateway event parsers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ...integrations import _integration_factory
from ...raw_models import RawIntegrationDeleteEvent
from ._common import get_guild_or_log, strip_guild_id

if TYPE_CHECKING:
    from ...types.raw_models import (
        GuildIntegrationsUpdateEvent,
        IntegrationCreateEvent,
        IntegrationDeleteEvent,
        IntegrationUpdateEvent,
        WebhooksUpdateEvent,
    )
    from ...types.snowflake import Snowflake
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_guild_integrations_update(
    state: ConnectionState, data: GuildIntegrationsUpdateEvent
) -> None:
    """Handle the ``GUILD_INTEGRATIONS_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_INTEGRATIONS_UPDATE")
    if guild is None:
        return

    state.dispatch("guild_integrations_update", guild)


async def parse_integration_create(
    state: ConnectionState, data: IntegrationCreateEvent
) -> None:
    """Handle the ``INTEGRATION_CREATE`` gateway event."""
    guild_id = int(data["guild_id"])
    guild = await state._get_guild(guild_id)
    if guild is not None:
        cls, _ = _integration_factory(data["type"])
        integration = cls(data=strip_guild_id(data), guild=guild)
        state.dispatch("integration_create", integration)
    else:
        _log.debug(
            "INTEGRATION_CREATE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )


async def parse_integration_update(
    state: ConnectionState, data: IntegrationUpdateEvent
) -> None:
    """Handle the ``INTEGRATION_UPDATE`` gateway event."""
    guild_id = int(data["guild_id"])
    guild = await state._get_guild(guild_id)
    if guild is not None:
        cls, _ = _integration_factory(data["type"])
        integration = cls(data=strip_guild_id(data), guild=guild)
        state.dispatch("integration_update", integration)
    else:
        _log.debug(
            "INTEGRATION_UPDATE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )


async def parse_integration_delete(
    state: ConnectionState, data: IntegrationDeleteEvent
) -> None:
    """Handle the ``INTEGRATION_DELETE`` gateway event."""
    guild_id = int(data["guild_id"])
    guild = await state._get_guild(guild_id)
    if guild is not None:
        raw = RawIntegrationDeleteEvent(data)
        state.dispatch("raw_integration_delete", raw)
    else:
        _log.debug(
            "INTEGRATION_DELETE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )


async def parse_webhooks_update(
    state: ConnectionState, data: WebhooksUpdateEvent
) -> None:
    """Handle the ``WEBHOOKS_UPDATE`` gateway event."""
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is None:
        _log.debug(
            "WEBHOOKS_UPDATE referencing an unknown guild ID: %s. Discarding",
            data["guild_id"],
        )
        return

    channel_id = cast("Snowflake | None", data["channel_id"])
    if channel_id is not None:
        channel = await guild.get_channel(int(channel_id))
        if channel is not None:
            state.dispatch("webhooks_update", channel)
        else:
            _log.debug(
                "WEBHOOKS_UPDATE referencing an unknown channel ID: %s. Discarding.",
                data["channel_id"],
            )
    else:
        _log.debug(
            "WEBHOOKS_UPDATE channel ID was null for guild: %s. Discarding.",
            data["guild_id"],
        )
