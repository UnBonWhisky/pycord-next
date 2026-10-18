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

"""Invite gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...invite import Invite

if TYPE_CHECKING:
    from ...types.invite import GatewayInviteCreate, GatewayInviteDelete
    from ..state import ConnectionState


async def parse_invite_create(
    state: ConnectionState, data: GatewayInviteCreate
) -> None:
    """Handle the ``INVITE_CREATE`` gateway event."""
    invite = Invite.from_gateway(state=state, data=data)
    state.dispatch("invite_create", invite)


async def parse_invite_delete(
    state: ConnectionState, data: GatewayInviteDelete
) -> None:
    """Handle the ``INVITE_DELETE`` gateway event."""
    invite = Invite.from_gateway(state=state, data=data)
    state.dispatch("invite_delete", invite)
