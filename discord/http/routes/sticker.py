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

"""Discord API routes for the sticker resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ... import utils
from ...errors import InvalidArgument
from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...file import File
    from ...types import (
        sticker,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("StickerRoutes",)


class StickerRoutes(HTTPBase):
    """Endpoints of the sticker resource."""

    def get_sticker(
        self, sticker_id: Snowflake
    ) -> Response[sticker.StandardSticker | sticker.GuildSticker]:
        """Fetch a sticker."""
        return self.request(
            Route("GET", "/stickers/{sticker_id}", sticker_id=sticker_id)
        )

    def list_premium_sticker_packs(self) -> Response[sticker.ListPremiumStickerPacks]:
        """Fetch the premium sticker packs."""
        return self.request(Route("GET", "/sticker-packs"))

    def get_all_guild_stickers(
        self, guild_id: Snowflake
    ) -> Response[list[sticker.GuildSticker]]:
        """Fetch the stickers of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/stickers", guild_id=guild_id)
        )

    def get_guild_sticker(
        self, guild_id: Snowflake, sticker_id: Snowflake
    ) -> Response[sticker.GuildSticker]:
        """Fetch a sticker of a guild."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/stickers/{sticker_id}",
                guild_id=guild_id,
                sticker_id=sticker_id,
            )
        )

    def create_guild_sticker(
        self,
        guild_id: Snowflake,
        payload: sticker.CreateGuildSticker,
        file: File,
        reason: str | None,
    ) -> Response[sticker.GuildSticker]:
        """Create a sticker in a guild."""
        initial_bytes = file.fp.read(16)

        try:
            mime_type = utils._get_mime_type_for_file(initial_bytes)
        except InvalidArgument:
            if initial_bytes.startswith(b"{"):
                mime_type = "application/json"
            else:
                mime_type = "application/octet-stream"
        finally:
            file.reset()

        form: list[dict[str, Any]] = [
            {
                "name": "file",
                "value": file.fp,
                "filename": file.filename,
                "content_type": mime_type,
            }
        ]

        for k, v in payload.items():
            form.append(
                {
                    "name": k,
                    "value": v,
                }
            )

        return self.request(
            Route("POST", "/guilds/{guild_id}/stickers", guild_id=guild_id),
            form=form,
            files=[file],
            reason=reason,
        )

    def modify_guild_sticker(
        self,
        guild_id: Snowflake,
        sticker_id: Snowflake,
        payload: sticker.EditGuildSticker,
        reason: str | None,
    ) -> Response[sticker.GuildSticker]:
        """Edit a sticker of a guild."""
        return self.request(
            Route(
                "PATCH",
                "/guilds/{guild_id}/stickers/{sticker_id}",
                guild_id=guild_id,
                sticker_id=sticker_id,
            ),
            json=payload,
            reason=reason,
        )

    def delete_guild_sticker(
        self, guild_id: Snowflake, sticker_id: Snowflake, reason: str | None
    ) -> Response[None]:
        """Delete a sticker of a guild."""
        return self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/stickers/{sticker_id}",
                guild_id=guild_id,
                sticker_id=sticker_id,
            ),
            reason=reason,
        )
