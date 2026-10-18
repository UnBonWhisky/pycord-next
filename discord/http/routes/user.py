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

"""Discord API routes for the user resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        channel,
        guild,
        user,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("UserRoutes",)


class UserRoutes(HTTPBase):
    """Endpoints of the user resource."""

    def logout(self) -> Response[None]:
        """Log out of the current session."""
        return self.request(Route("POST", "/auth/logout"))

    def start_group(
        self, user_id: Snowflake, recipients: list[int]
    ) -> Response[channel.GroupDMChannel]:
        """Create a group DM."""
        payload = {
            "recipients": recipients,
        }

        return self.request(
            Route("POST", "/users/{user_id}/channels", user_id=user_id), json=payload
        )

    def start_private_message(self, user_id: Snowflake) -> Response[channel.DMChannel]:
        """Open a DM channel with a user."""
        payload = {
            "recipient_id": user_id,
        }

        return self.request(Route("POST", "/users/@me/channels"), json=payload)

    def edit_profile(self, payload: dict[str, Any]) -> Response[user.User]:
        """Edit the current user."""
        return self.request(Route("PATCH", "/users/@me"), json=payload)

    def get_guilds(
        self,
        limit: int,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        with_counts: bool = True,
        *,
        shard: int | None = None,
    ) -> Response[list[guild.Guild]]:
        """Fetch the guilds of the current user."""
        params: dict[str, Any] = {
            "limit": limit,
        }

        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if with_counts:
            params["with_counts"] = int(with_counts)
        if shard is not None:
            params["shard"] = shard

        return self.request(Route("GET", "/users/@me/guilds"), params=params)

    def leave_guild(self, guild_id: Snowflake) -> Response[None]:
        """Leave a guild."""
        return self.request(
            Route("DELETE", "/users/@me/guilds/{guild_id}", guild_id=guild_id)
        )

    def get_user(self, user_id: Snowflake) -> Response[user.User]:
        """Fetch a user."""
        return self.request(Route("GET", "/users/{user_id}", user_id=user_id))
