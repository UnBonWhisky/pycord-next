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

"""Stage instance gateway event parsers."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from ...stage_instance import StageInstance

if TYPE_CHECKING:
    from ...types.channel import StageInstance as StageInstancePayload
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_stage_instance_create(
    state: ConnectionState, data: StageInstancePayload
) -> None:
    """Handle the ``STAGE_INSTANCE_CREATE`` gateway event."""
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None:
        stage_instance = StageInstance(guild=guild, state=state, data=data)
        await state._guild_bucket("stage_instances", guild.id).set(
            stage_instance.id, stage_instance
        )
        state.dispatch("stage_instance_create", stage_instance)
    else:
        _log.debug(
            "STAGE_INSTANCE_CREATE referencing unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )


async def parse_stage_instance_update(
    state: ConnectionState, data: StageInstancePayload
) -> None:
    """Handle the ``STAGE_INSTANCE_UPDATE`` gateway event."""
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None:
        stage_instances = state._guild_bucket("stage_instances", guild.id)
        stage_instance = await stage_instances.get(int(data["id"]))
        if stage_instance is not None:
            old_stage_instance = copy.copy(stage_instance)
            stage_instance._update(data)
            await stage_instances.set(stage_instance.id, stage_instance)
            state.dispatch("stage_instance_update", old_stage_instance, stage_instance)
        else:
            _log.debug(
                (
                    "STAGE_INSTANCE_UPDATE referencing unknown stage instance ID:"
                    " %s. Discarding."
                ),
                data["id"],
            )
    else:
        _log.debug(
            "STAGE_INSTANCE_UPDATE referencing unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )


async def parse_stage_instance_delete(
    state: ConnectionState, data: StageInstancePayload
) -> None:
    """Handle the ``STAGE_INSTANCE_DELETE`` gateway event."""
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None:
        stage_instance = await state._guild_bucket("stage_instances", guild.id).pop(
            int(data["id"])
        )
        if stage_instance is not None:
            state.dispatch("stage_instance_delete", stage_instance)
    else:
        _log.debug(
            "STAGE_INSTANCE_DELETE referencing unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )
