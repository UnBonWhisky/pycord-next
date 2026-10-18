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

"""Discord API routes for interaction responses and followups."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...enums import InteractionResponseType
    from ...file import File
    from ...types import (
        embed,
        interactions,
        message,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("InteractionRoutes",)


class InteractionRoutes(HTTPBase):
    """Endpoints of the interaction resource."""

    def create_interaction_response(
        self,
        interaction_id: Snowflake,
        token: str,
        *,
        type: InteractionResponseType,
        data: interactions.InteractionApplicationCommandCallbackData | None = None,
    ) -> Response[None]:
        """Respond to an interaction."""
        r = Route(
            "POST",
            "/interactions/{interaction_id}/{interaction_token}/callback",
            interaction_id=interaction_id,
            interaction_token=token,
        )
        payload: dict[str, Any] = {
            "type": type,
        }

        if data is not None:
            payload["data"] = data

        return self.request(r, json=payload)

    def get_original_interaction_response(
        self,
        application_id: Snowflake,
        token: str,
    ) -> Response[message.Message]:
        """Fetch the original response of an interaction."""
        r = Route(
            "GET",
            "/webhooks/{application_id}/{interaction_token}/messages/@original",
            application_id=application_id,
            interaction_token=token,
        )
        return self.request(r)

    def edit_original_interaction_response(
        self,
        application_id: Snowflake,
        token: str,
        file: File | None = None,
        content: str | None = None,
        embeds: list[embed.Embed] | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
    ) -> Response[message.Message]:
        """Edit the original response of an interaction."""
        r = Route(
            "PATCH",
            "/webhooks/{application_id}/{interaction_token}/messages/@original",
            application_id=application_id,
            interaction_token=token,
        )
        return self._edit_webhook_helper(
            r,
            file=file,
            content=content,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
        )

    def delete_original_interaction_response(
        self, application_id: Snowflake, token: str
    ) -> Response[None]:
        """Delete the original response of an interaction."""
        r = Route(
            "DELETE",
            "/webhooks/{application_id}/{interaction_token}/messages/@original",
            application_id=application_id,
            interaction_token=token,
        )
        return self.request(r)

    def create_followup_message(
        self,
        application_id: Snowflake,
        token: str,
        files: list[File] | None = None,
        content: str | None = None,
        tts: bool = False,
        embeds: list[embed.Embed] | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
    ) -> Response[message.Message]:
        """Send a followup message to an interaction."""
        r = Route(
            "POST",
            "/webhooks/{application_id}/{interaction_token}",
            application_id=application_id,
            interaction_token=token,
        )
        return self.send_multipart_helper(
            r,
            content=content,
            files=files or [],
            tts=tts,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
        )

    def edit_followup_message(
        self,
        application_id: Snowflake,
        token: str,
        message_id: Snowflake,
        file: File | None = None,
        content: str | None = None,
        embeds: list[embed.Embed] | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
    ) -> Response[message.Message]:
        """Edit a followup message of an interaction."""
        r = Route(
            "PATCH",
            "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
            application_id=application_id,
            interaction_token=token,
            message_id=message_id,
        )
        return self._edit_webhook_helper(
            r,
            file=file,
            content=content,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
        )

    def delete_followup_message(
        self, application_id: Snowflake, token: str, message_id: Snowflake
    ) -> Response[None]:
        """Delete a followup message of an interaction."""
        r = Route(
            "DELETE",
            "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
            application_id=application_id,
            interaction_token=token,
            message_id=message_id,
        )
        return self.request(r)
