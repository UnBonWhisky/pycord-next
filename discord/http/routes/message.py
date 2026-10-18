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

"""Discord API routes for the message resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ..base import HTTPBase
from ..multipart import message_payload
from ..route import Route

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...file import File
    from ...types import (
        components,
        embed,
        message,
        poll,
        user,
    )
    from ...types.snowflake import Snowflake, SnowflakeList
    from ..base import Response

__all__ = ("MessageRoutes",)


class MessageRoutes(HTTPBase):
    """Endpoints of the message resource."""

    def send_message(
        self,
        channel_id: Snowflake,
        content: str | None,
        *,
        tts: bool = False,
        embed: embed.Embed | None = None,
        embeds: list[embed.Embed] | None = None,
        nonce: int | str | None = None,
        enforce_nonce: bool | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
        message_reference: message.MessageReference | None = None,
        stickers: Sequence[Snowflake] | None = None,
        components: list[components.Component] | None = None,
        flags: int | None = None,
        poll: poll.Poll | None = None,
        shared_client_theme: message.SharedClientTheme | None = None,
    ) -> Response[message.Message]:
        """Send a message to a channel."""
        r = Route("POST", "/channels/{channel_id}/messages", channel_id=channel_id)
        payload = message_payload(
            content=content,
            embed=embed,
            embeds=embeds,
            nonce=nonce,
            enforce_nonce=enforce_nonce,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
            stickers=stickers,
            components=components,
            flags=flags,
            poll=poll,
            shared_client_theme=shared_client_theme,
        )
        if tts:
            payload["tts"] = True

        return self.request(r, json=payload)

    def send_typing(self, channel_id: Snowflake) -> Response[None]:
        """Trigger the typing indicator in a channel."""
        return self.request(
            Route("POST", "/channels/{channel_id}/typing", channel_id=channel_id)
        )

    def send_files(
        self,
        channel_id: Snowflake,
        *,
        files: Sequence[File],
        content: str | None = None,
        tts: bool = False,
        embed: embed.Embed | None = None,
        embeds: list[embed.Embed] | None = None,
        nonce: int | str | None = None,
        enforce_nonce: bool | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
        message_reference: message.MessageReference | None = None,
        stickers: Sequence[Snowflake] | None = None,
        components: list[components.Component] | None = None,
        flags: int | None = None,
        poll: poll.Poll | None = None,
        shared_client_theme: message.SharedClientTheme | None = None,
    ) -> Response[message.Message]:
        """Send a message with attachments to a channel."""
        r = Route("POST", "/channels/{channel_id}/messages", channel_id=channel_id)
        return self.send_multipart_helper(
            r,
            files=files,
            content=content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            nonce=nonce,
            enforce_nonce=enforce_nonce,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
            stickers=stickers,
            components=components,
            flags=flags,
            poll=poll,
            shared_client_theme=shared_client_theme,
        )

    def edit_files(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        files: Sequence[File],
        **fields: Any,
    ) -> Response[message.Message]:
        """Edit a message and upload attachments."""
        r = Route(
            "PATCH",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        payload: dict[str, Any] = {}
        if "attachments" in fields:
            payload["attachments"] = fields["attachments"]
        if "flags" in fields:
            payload["flags"] = fields["flags"]
        if "content" in fields:
            payload["content"] = fields["content"]
        if "embeds" in fields:
            payload["embeds"] = fields["embeds"]
        if "allowed_mentions" in fields:
            payload["allowed_mentions"] = fields["allowed_mentions"]
        if "components" in fields:
            payload["components"] = fields["components"]
        return self.edit_multipart_helper(
            r,
            files=files,
            **payload,
        )

    def delete_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(r, reason=reason)

    def delete_messages(
        self,
        channel_id: Snowflake,
        message_ids: SnowflakeList,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Bulk delete messages."""
        r = Route(
            "POST", "/channels/{channel_id}/messages/bulk-delete", channel_id=channel_id
        )
        payload = {
            "messages": message_ids,
        }

        return self.request(r, json=payload, reason=reason)

    def edit_message(
        self, channel_id: Snowflake, message_id: Snowflake, **fields: Any
    ) -> Response[message.Message]:
        """Edit a message."""
        r = Route(
            "PATCH",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(r, json=fields)

    def add_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str
    ) -> Response[None]:
        """Add a reaction to a message."""
        r = Route(
            "PUT",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
        )
        return self.request(r)

    def remove_reaction(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: str,
        member_id: Snowflake,
    ) -> Response[None]:
        """Remove another member's reaction from a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/{member_id}",
            channel_id=channel_id,
            message_id=message_id,
            member_id=member_id,
            emoji=emoji,
        )
        return self.request(r)

    def remove_own_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str
    ) -> Response[None]:
        """Remove the current user's reaction from a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
        )
        return self.request(r)

    def get_reaction_users(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: str,
        limit: int,
        after: Snowflake | None = None,
        type: int | None = None,
    ) -> Response[list[user.User]]:
        """Fetch the users who reacted to a message with an emoji."""
        r = Route(
            "GET",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
        )

        params: dict[str, Any] = {
            "limit": limit,
        }
        if after:
            params["after"] = after
        if type:
            params["type"] = type
        return self.request(r, params=params)

    def clear_reactions(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> Response[None]:
        """Remove every reaction from a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}/reactions",
            channel_id=channel_id,
            message_id=message_id,
        )

        return self.request(r)

    def clear_single_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str
    ) -> Response[None]:
        """Remove every reaction of one emoji from a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
        )
        return self.request(r)

    def get_message(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> Response[message.Message]:
        """Fetch a message."""
        r = Route(
            "GET",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(r)

    def logs_from(
        self,
        channel_id: Snowflake,
        limit: int,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        around: Snowflake | None = None,
    ) -> Response[list[message.Message]]:
        """Fetch the message history of a channel."""
        params: dict[str, Any] = {
            "limit": limit,
        }

        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if around is not None:
            params["around"] = around

        return self.request(
            Route("GET", "/channels/{channel_id}/messages", channel_id=channel_id),
            params=params,
        )

    def publish_message(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> Response[message.Message]:
        """Crosspost a message from an announcement channel."""
        return self.request(
            Route(
                "POST",
                "/channels/{channel_id}/messages/{message_id}/crosspost",
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    def pin_message(
        self, channel_id: Snowflake, message_id: Snowflake, reason: str | None = None
    ) -> Response[None]:
        """Pin a message."""
        r = Route(
            "PUT",
            "/channels/{channel_id}/messages/pins/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(r, reason=reason)

    def unpin_message(
        self, channel_id: Snowflake, message_id: Snowflake, reason: str | None = None
    ) -> Response[None]:
        """Unpin a message."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/messages/pins/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(r, reason=reason)

    def pins_from(
        self,
        channel_id: Snowflake,
        limit: int | None = None,
        before: str | None = None,
    ) -> Response[message.MessagePinPagination]:
        """Fetch the pinned messages of a channel."""
        r = Route("GET", "/channels/{channel_id}/messages/pins", channel_id=channel_id)
        params: dict[str, Any] = {}
        if limit:
            params["limit"] = limit
        if before:
            params["before"] = before

        return self.request(r, params=params)

    def legacy_pins_from(
        self, channel_id: Snowflake
    ) -> Response[list[message.Message]]:
        """Fetch the pinned messages of a channel using the legacy endpoint."""
        return self.request(
            Route("GET", "/channels/{channel_id}/pins", channel_id=channel_id)
        )

    def search_guild_messages(
        self,
        guild_id: Snowflake,
        *,
        limit: int | None = None,
        offset: int | None = None,
        max_id: Snowflake | None = None,
        min_id: Snowflake | None = None,
        slop: int | None = None,
        content: str | None = None,
        channel_id: SnowflakeList | None = None,
        author_type: list[message.SearchAuthorType | str] | None = None,
        author_id: SnowflakeList | None = None,
        mentions: SnowflakeList | None = None,
        mentions_role_id: SnowflakeList | None = None,
        mention_everyone: bool | None = None,
        replied_to_user_id: SnowflakeList | None = None,
        replied_to_message_id: SnowflakeList | None = None,
        pinned: bool | None = None,
        has: list[message.SearchHasType | str] | None = None,
        embed_type: list[message.SearchEmbedType] | None = None,
        embed_provider: list[str] | None = None,
        link_hostname: list[str] | None = None,
        attachment_filename: list[str] | None = None,
        attachment_extension: list[str] | None = None,
        sort_by: message.SearchSortMode | None = None,
        sort_order: message.SearchSortOrder | None = None,
        include_nsfw: bool | None = None,
    ) -> Response[message.MessageSearchResults | message.MessageSearchIndexing]:
        """Search the messages of a guild.

        Discord answers ``202`` with a body holding ``retry_after`` and no
        ``messages`` while the guild is not indexed yet.
        """
        r = Route("GET", "/guilds/{guild_id}/messages/search", guild_id=guild_id)
        candidates: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "max_id": max_id,
            "min_id": min_id,
            "slop": slop,
            "content": content,
            "channel_id": channel_id,
            "author_type": author_type,
            "author_id": author_id,
            "mentions": mentions,
            "mentions_role_id": mentions_role_id,
            "mention_everyone": mention_everyone,
            "replied_to_user_id": replied_to_user_id,
            "replied_to_message_id": replied_to_message_id,
            "pinned": pinned,
            "has": has,
            "embed_type": embed_type,
            "embed_provider": embed_provider,
            "link_hostname": link_hostname,
            "attachment_filename": attachment_filename,
            "attachment_extension": attachment_extension,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_nsfw": include_nsfw,
        }
        params: dict[str, Any] = {}
        for key, value in candidates.items():
            if value is None:
                continue
            if isinstance(value, bool):
                params[key] = "true" if value else "false"
            elif isinstance(value, list):
                params[key] = [str(item) for item in cast("list[object]", value)]
            else:
                params[key] = value
        return self.request(r, params=params)
