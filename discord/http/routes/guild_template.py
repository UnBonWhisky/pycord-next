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

"""Discord API routes for the guild template resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        template,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("GuildTemplateRoutes",)


class GuildTemplateRoutes(HTTPBase):
    """Endpoints of the guild template resource."""

    def get_template(self, code: str) -> Response[template.Template]:
        """Fetch a guild template."""
        return self.request(Route("GET", "/guilds/templates/{code}", code=code))

    def guild_templates(self, guild_id: Snowflake) -> Response[list[template.Template]]:
        """Fetch the templates of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/templates", guild_id=guild_id)
        )

    def create_template(
        self, guild_id: Snowflake, payload: template.CreateTemplate
    ) -> Response[template.Template]:
        """Create a template from a guild."""
        return self.request(
            Route("POST", "/guilds/{guild_id}/templates", guild_id=guild_id),
            json=payload,
        )

    def sync_template(
        self, guild_id: Snowflake, code: str
    ) -> Response[template.Template]:
        """Sync a template with its guild."""
        return self.request(
            Route(
                "PUT",
                "/guilds/{guild_id}/templates/{code}",
                guild_id=guild_id,
                code=code,
            )
        )

    def edit_template(
        self, guild_id: Snowflake, code: str, payload: dict[str, Any]
    ) -> Response[template.Template]:
        """Edit a guild template."""
        valid_keys = (
            "name",
            "description",
        )
        fields = {k: v for k, v in payload.items() if k in valid_keys}
        return self.request(
            Route(
                "PATCH",
                "/guilds/{guild_id}/templates/{code}",
                guild_id=guild_id,
                code=code,
            ),
            json=fields,
        )

    def delete_template(self, guild_id: Snowflake, code: str) -> Response[None]:
        """Delete a guild template."""
        return self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/templates/{code}",
                guild_id=guild_id,
                code=code,
            )
        )
