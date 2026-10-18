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

"""Discord API routes for the audit log resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...enums import AuditLogAction
    from ...types import (
        audit_log,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("AuditLogRoutes",)


class AuditLogRoutes(HTTPBase):
    """Endpoints of the audit log resource."""

    def get_audit_logs(
        self,
        guild_id: Snowflake,
        limit: int = 100,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        user_id: Snowflake | None = None,
        action_type: AuditLogAction | int | None = None,
    ) -> Response[audit_log.AuditLog]:
        """Fetch the audit log of a guild."""
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if user_id:
            params["user_id"] = user_id
        if action_type:
            params["action_type"] = action_type

        r = Route("GET", "/guilds/{guild_id}/audit-logs", guild_id=guild_id)
        return self.request(r, params=params)
