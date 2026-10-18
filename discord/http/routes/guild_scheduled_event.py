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

"""Discord API routes for the guild scheduled event resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        scheduled_events,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("GuildScheduledEventRoutes",)


class GuildScheduledEventRoutes(HTTPBase):
    """Endpoints of the guild scheduled event resource."""

    def get_scheduled_events(
        self, guild_id: Snowflake, with_user_count: bool = True
    ) -> Response[list[scheduled_events.ScheduledEvent]]:
        """Fetch the scheduled events of a guild."""
        params = {
            "with_user_count": int(with_user_count),
        }

        return self.request(
            Route("GET", "/guilds/{guild_id}/scheduled-events", guild_id=guild_id),
            params=params,
        )

    def get_scheduled_event(
        self, guild_id: Snowflake, event_id: Snowflake, with_user_count: bool = True
    ) -> Response[scheduled_events.ScheduledEvent]:
        """Fetch a scheduled event."""
        params = {
            "with_user_count": int(with_user_count),
        }

        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/scheduled-events/{event_id}",
                guild_id=guild_id,
                event_id=event_id,
            ),
            params=params,
        )

    def create_scheduled_event(
        self, guild_id: Snowflake, reason: str | None = None, **payload: Any
    ) -> Response[scheduled_events.ScheduledEvent]:
        """Create a scheduled event."""
        valid_keys = (
            "channel_id",
            "name",
            "privacy_level",
            "scheduled_start_time",
            "scheduled_end_time",
            "description",
            "entity_type",
            "entity_metadata",
            "image",
            "recurrence_rule",
        )
        payload = {k: v for k, v in payload.items() if k in valid_keys}

        return self.request(
            Route("POST", "/guilds/{guild_id}/scheduled-events", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def delete_scheduled_event(
        self, guild_id: Snowflake, event_id: Snowflake
    ) -> Response[None]:
        """Delete a scheduled event."""
        return self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/scheduled-events/{event_id}",
                guild_id=guild_id,
                event_id=event_id,
            )
        )

    def edit_scheduled_event(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        reason: str | None = None,
        **payload: Any,
    ) -> Response[scheduled_events.ScheduledEvent]:
        """Edit a scheduled event."""
        valid_keys = (
            "channel_id",
            "name",
            "privacy_level",
            "scheduled_start_time",
            "scheduled_end_time",
            "description",
            "entity_type",
            "status",
            "entity_metadata",
            "image",
            "recurrence_rule",
        )
        payload = {k: v for k, v in payload.items() if k in valid_keys}

        return self.request(
            Route(
                "PATCH",
                "/guilds/{guild_id}/scheduled-events/{event_id}",
                guild_id=guild_id,
                event_id=event_id,
            ),
            json=payload,
            reason=reason,
        )

    def get_scheduled_event_users(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        limit: int,
        with_member: bool = False,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
    ) -> Response[list[scheduled_events.ScheduledEventSubscriber]]:
        """Fetch the users subscribed to a scheduled event."""
        params = {
            "limit": int(limit),
            "with_member": int(with_member),
        }

        if before is not None:
            params["before"] = int(before)

        if after is not None:
            params["after"] = int(after)

        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/scheduled-events/{event_id}/users",
                guild_id=guild_id,
                event_id=event_id,
            ),
            params=params,
        )
