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

"""Discord API routes for the stage instance resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        channel,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("StageInstanceRoutes",)


class StageInstanceRoutes(HTTPBase):
    """Endpoints of the stage instance resource."""

    def get_stage_instance(
        self, channel_id: Snowflake
    ) -> Response[channel.StageInstance]:
        """Fetch the stage instance of a channel."""
        return self.request(
            Route("GET", "/stage-instances/{channel_id}", channel_id=channel_id)
        )

    def create_stage_instance(
        self, *, reason: str | None, **payload: Any
    ) -> Response[channel.StageInstance]:
        """Create a stage instance."""
        valid_keys = (
            "channel_id",
            "topic",
            "privacy_level",
            "send_start_notification",
        )
        payload = {k: v for k, v in payload.items() if k in valid_keys}

        if payload.get("send_start_notification") is not None:
            payload["send_start_notification"] = int(payload["send_start_notification"])

        return self.request(
            Route("POST", "/stage-instances"), json=payload, reason=reason
        )

    def edit_stage_instance(
        self, channel_id: Snowflake, *, reason: str | None = None, **payload: Any
    ) -> Response[None]:
        """Edit a stage instance."""
        valid_keys = (
            "topic",
            "privacy_level",
        )
        payload = {k: v for k, v in payload.items() if k in valid_keys}

        return self.request(
            Route("PATCH", "/stage-instances/{channel_id}", channel_id=channel_id),
            json=payload,
            reason=reason,
        )

    def delete_stage_instance(
        self, channel_id: Snowflake, *, reason: str | None = None
    ) -> Response[None]:
        """Delete a stage instance."""
        return self.request(
            Route("DELETE", "/stage-instances/{channel_id}", channel_id=channel_id),
            reason=reason,
        )
