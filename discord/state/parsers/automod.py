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

"""Auto moderation gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...automod import AutoModRule
from ...raw_models import AutoModActionExecutionEvent

if TYPE_CHECKING:
    from ...types.automod import AutoModRule as AutoModRulePayload
    from ...types.raw_models import (
        AutoModActionExecutionEvent as AutoModActionExecutionPayload,
    )
    from ..state import ConnectionState


async def parse_auto_moderation_rule_create(
    state: ConnectionState, data: AutoModRulePayload
) -> None:
    """Handle the ``AUTO_MODERATION_RULE_CREATE`` gateway event."""
    rule = AutoModRule(state=state, data=data)
    state.dispatch("auto_moderation_rule_create", rule)


async def parse_auto_moderation_rule_update(
    state: ConnectionState, data: AutoModRulePayload
) -> None:
    """Handle the ``AUTO_MODERATION_RULE_UPDATE`` gateway event."""
    # somehow get a 'before' object?
    rule = AutoModRule(state=state, data=data)
    state.dispatch("auto_moderation_rule_update", rule)


async def parse_auto_moderation_rule_delete(
    state: ConnectionState, data: AutoModRulePayload
) -> None:
    """Handle the ``AUTO_MODERATION_RULE_DELETE`` gateway event."""
    rule = AutoModRule(state=state, data=data)
    state.dispatch("auto_moderation_rule_delete", rule)


async def parse_auto_moderation_action_execution(
    state: ConnectionState, data: AutoModActionExecutionPayload
) -> None:
    """Handle the ``AUTO_MODERATION_ACTION_EXECUTION`` gateway event."""
    event = AutoModActionExecutionEvent(state, data)
    event.guild = await state._get_guild(event.guild_id)
    if event.guild is not None:
        if event.channel_id is not None:
            event.channel = await event.guild.get_channel_or_thread(event.channel_id)
        event.member = await event.guild.get_member(event.user_id)
    event.message = await state._get_message(event.message_id)
    event.alert_system_message = await state._get_message(event.alert_system_message_id)
    state.dispatch("auto_moderation_action_execution", event)
