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

"""Discord API routes for the emoji resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...types import (
        emoji,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("EmojiRoutes",)


class EmojiRoutes(HTTPBase):
    """Endpoints of the emoji resource."""

    def get_all_custom_emojis(self, guild_id: Snowflake) -> Response[list[emoji.Emoji]]:
        """Fetch the emojis of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/emojis", guild_id=guild_id)
        )

    def get_custom_emoji(
        self, guild_id: Snowflake, emoji_id: Snowflake
    ) -> Response[emoji.Emoji]:
        """Fetch an emoji of a guild."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/emojis/{emoji_id}",
                guild_id=guild_id,
                emoji_id=emoji_id,
            )
        )

    def create_custom_emoji(
        self,
        guild_id: Snowflake,
        name: str,
        image: str,
        *,
        roles: Sequence[Snowflake] | None = None,
        reason: str | None = None,
    ) -> Response[emoji.Emoji]:
        """Create an emoji in a guild."""
        payload = {
            "name": name,
            "image": image,
            "roles": roles or [],
        }

        r = Route("POST", "/guilds/{guild_id}/emojis", guild_id=guild_id)
        return self.request(r, json=payload, reason=reason)

    def delete_custom_emoji(
        self,
        guild_id: Snowflake,
        emoji_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete an emoji of a guild."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/emojis/{emoji_id}",
            guild_id=guild_id,
            emoji_id=emoji_id,
        )
        return self.request(r, reason=reason)

    def edit_custom_emoji(
        self,
        guild_id: Snowflake,
        emoji_id: Snowflake,
        *,
        payload: dict[str, Any],
        reason: str | None = None,
    ) -> Response[emoji.Emoji]:
        """Edit an emoji of a guild."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/emojis/{emoji_id}",
            guild_id=guild_id,
            emoji_id=emoji_id,
        )
        return self.request(r, json=payload, reason=reason)

    def get_all_application_emojis(
        self, application_id: Snowflake
    ) -> Response[emoji.ApplicationEmojis]:
        """Fetch the emojis of an application."""
        return self.request(
            Route(
                "GET",
                "/applications/{application_id}/emojis",
                application_id=application_id,
            )
        )

    def get_application_emoji(
        self, application_id: Snowflake, emoji_id: Snowflake
    ) -> Response[emoji.Emoji]:
        """Fetch an emoji of an application."""
        return self.request(
            Route(
                "GET",
                "/applications/{application_id}/emojis/{emoji_id}",
                application_id=application_id,
                emoji_id=emoji_id,
            )
        )

    def create_application_emoji(
        self,
        application_id: Snowflake,
        name: str,
        image: str,
    ) -> Response[emoji.Emoji]:
        """Create an emoji for an application."""
        payload = {
            "name": name,
            "image": image,
        }

        r = Route(
            "POST",
            "/applications/{application_id}/emojis",
            application_id=application_id,
        )
        return self.request(r, json=payload)

    def delete_application_emoji(
        self,
        application_id: Snowflake,
        emoji_id: Snowflake,
    ) -> Response[None]:
        """Delete an emoji of an application."""
        r = Route(
            "DELETE",
            "/applications/{application_id}/emojis/{emoji_id}",
            application_id=application_id,
            emoji_id=emoji_id,
        )
        return self.request(r)

    def edit_application_emoji(
        self,
        application_id: Snowflake,
        emoji_id: Snowflake,
        *,
        payload: dict[str, Any],
    ) -> Response[emoji.Emoji]:
        """Edit an emoji of an application."""
        r = Route(
            "PATCH",
            "/applications/{application_id}/emojis/{emoji_id}",
            application_id=application_id,
            emoji_id=emoji_id,
        )
        return self.request(r, json=payload)
