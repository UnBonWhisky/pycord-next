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

"""Interaction gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...enums import InteractionType
from ...interactions import Interaction

if TYPE_CHECKING:
    from ...member import Member
    from ...types.interactions import (
        ComponentInteractionData,
        Interaction as InteractionPayload,
    )
    from ...user import User
    from ..state import ConnectionState


async def parse_interaction_create(
    state: ConnectionState, data: InteractionPayload
) -> None:
    """Handle the ``INTERACTION_CREATE`` gateway event."""
    interaction = Interaction(data=data, state=state)
    await state._populate_interaction(interaction, data)
    interaction_data = cast("ComponentInteractionData", interaction.data)
    if data["type"] == 3:  # interaction component
        state._view_store.dispatch(
            interaction_data["component_type"],
            interaction_data["custom_id"],
            interaction,
        )
    if interaction.type == InteractionType.modal_submit:
        user = cast("User | Member", interaction.user)
        state._create_task(
            state._modal_store.dispatch(
                user.id, interaction_data["custom_id"], interaction
            )
        )

    state.dispatch("interaction", interaction)
