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

"""Discord API routes for the voice resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types.snowflake import Snowflake
    from ...types.voice import VoiceRegion
    from ..base import Response

__all__ = ("VoiceRoutes",)


class VoiceRoutes(HTTPBase):
    """Endpoints of the voice resource."""

    def get_voice_regions(self) -> Response[list[VoiceRegion]]:
        """List the voice regions."""
        return self.request(Route("GET", "/voice/regions"))

    def edit_my_voice_state(
        self, guild_id: Snowflake, payload: dict[str, Any]
    ) -> Response[None]:
        """Edit the voice state of the current user."""
        r = Route("PATCH", "/guilds/{guild_id}/voice-states/@me", guild_id=guild_id)
        return self.request(r, json=payload)

    def edit_voice_state(
        self, guild_id: Snowflake, user_id: Snowflake, payload: dict[str, Any]
    ) -> Response[None]:
        """Edit the voice state of another user."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/voice-states/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        return self.request(r, json=payload)

    def set_voice_channel_status(
        self, channel_id: Snowflake, status: str | None, *, reason: str | None = None
    ) -> Response[None]:
        """Set the status of a voice channel."""
        payload = {"status": status}
        r = Route("PUT", "/channels/{channel_id}/voice-status", channel_id=channel_id)
        return self.request(r, json=payload, reason=reason)
