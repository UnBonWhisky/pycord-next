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

"""Discord API routes for the poll resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        message,
        poll,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("PollRoutes",)


class PollRoutes(HTTPBase):
    """Endpoints of the poll resource."""

    def expire_poll(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> Response[message.Message]:
        """End a poll."""
        return self.request(
            Route(
                "POST",
                "/channels/{channel_id}/polls/{message_id}/expire",
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    def get_answer_voters(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        answer_id: int,
        limit: int,
        after: Snowflake | None = None,
    ) -> Response[poll.PollAnswerVoters]:
        """Fetch the voters of a poll answer."""
        r = Route(
            "GET",
            "/channels/{channel_id}/polls/{message_id}/answers/{answer_id}",
            channel_id=channel_id,
            message_id=message_id,
            answer_id=answer_id,
        )

        params: dict[str, Any] = {
            "limit": limit,
        }
        if after:
            params["after"] = after
        return self.request(r, params=params)
