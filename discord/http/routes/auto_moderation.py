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

"""Discord API routes for the auto moderation resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        automod,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("AutoModerationRoutes",)


class AutoModerationRoutes(HTTPBase):
    """Endpoints of the auto moderation resource."""

    def get_auto_moderation_rules(
        self,
        guild_id: Snowflake,
    ) -> Response[list[automod.AutoModRule]]:
        """Fetch the auto moderation rules of a guild."""
        r = Route(
            "GET",
            "/guilds/{guild_id}/auto-moderation/rules",
            guild_id=guild_id,
        )
        return self.request(r)

    def get_auto_moderation_rule(
        self,
        guild_id: Snowflake,
        rule_id: Snowflake,
    ) -> Response[automod.AutoModRule]:
        """Fetch an auto moderation rule."""
        r = Route(
            "GET",
            "/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            guild_id=guild_id,
            rule_id=rule_id,
        )
        return self.request(r)

    def create_auto_moderation_rule(
        self,
        guild_id: Snowflake,
        payload: automod.CreateAutoModRule,
        reason: str | None = None,
    ) -> Response[automod.AutoModRule]:
        """Create an auto moderation rule."""
        r = Route(
            "POST",
            "/guilds/{guild_id}/auto-moderation/rules",
            guild_id=guild_id,
        )
        return self.request(r, json=payload, reason=reason)

    def edit_auto_moderation_rule(
        self,
        guild_id: Snowflake,
        rule_id: Snowflake,
        payload: automod.EditAutoModRule,
        reason: str | None = None,
    ) -> Response[automod.AutoModRule]:
        """Edit an auto moderation rule."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            guild_id=guild_id,
            rule_id=rule_id,
        )
        return self.request(r, json=payload, reason=reason)

    def delete_auto_moderation_rule(
        self,
        guild_id: Snowflake,
        rule_id: Snowflake,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete an auto moderation rule."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            guild_id=guild_id,
            rule_id=rule_id,
        )
        return self.request(r, reason=reason)
