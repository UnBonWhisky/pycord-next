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

"""Discord API routes for the webhook resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        webhook,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("WebhookRoutes",)


class WebhookRoutes(HTTPBase):
    """Endpoints of the webhook resource."""

    def create_webhook(
        self,
        channel_id: Snowflake,
        *,
        name: str,
        avatar: str | None = None,
        reason: str | None = None,
    ) -> Response[webhook.Webhook]:
        """Create a webhook in a channel."""
        payload: dict[str, Any] = {
            "name": name,
        }
        if avatar is not None:
            payload["avatar"] = avatar

        r = Route("POST", "/channels/{channel_id}/webhooks", channel_id=channel_id)
        return self.request(r, json=payload, reason=reason)

    def channel_webhooks(
        self, channel_id: Snowflake
    ) -> Response[list[webhook.Webhook]]:
        """Fetch the webhooks of a channel."""
        return self.request(
            Route("GET", "/channels/{channel_id}/webhooks", channel_id=channel_id)
        )

    def guild_webhooks(self, guild_id: Snowflake) -> Response[list[webhook.Webhook]]:
        """Fetch the webhooks of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/webhooks", guild_id=guild_id)
        )

    def get_webhook(self, webhook_id: Snowflake) -> Response[webhook.Webhook]:
        """Fetch a webhook."""
        return self.request(
            Route("GET", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        )

    def follow_webhook(
        self,
        channel_id: Snowflake,
        webhook_channel_id: Snowflake,
        reason: str | None = None,
    ) -> Response[None]:
        """Follow an announcement channel."""
        payload = {
            "webhook_channel_id": str(webhook_channel_id),
        }
        return self.request(
            Route("POST", "/channels/{channel_id}/followers", channel_id=channel_id),
            json=payload,
            reason=reason,
        )
