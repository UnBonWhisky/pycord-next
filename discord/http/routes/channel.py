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

"""Discord API routes for the channel resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..multipart import message_payload, multipart_form
from ..route import Route

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...file import File
    from ...types import (
        channel,
        components,
        embed,
        guild,
        message,
        threads,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("ChannelRoutes",)


class ChannelRoutes(HTTPBase):
    """Endpoints of the channel resource."""

    def leave_group(self, channel_id: Snowflake) -> Response[None]:
        """Leave a group DM."""
        return self.request(
            Route("DELETE", "/channels/{channel_id}", channel_id=channel_id)
        )

    def get_channel(self, channel_id: Snowflake) -> Response[channel.Channel]:
        """Fetch a channel."""
        r = Route("GET", "/channels/{channel_id}", channel_id=channel_id)
        return self.request(r)

    def edit_channel(
        self,
        channel_id: Snowflake,
        *,
        reason: str | None = None,
        **options: Any,
    ) -> Response[channel.Channel]:
        """Edit a channel."""
        r = Route("PATCH", "/channels/{channel_id}", channel_id=channel_id)
        valid_keys = (
            "name",
            "parent_id",
            "topic",
            "bitrate",
            "nsfw",
            "user_limit",
            "position",
            "permission_overwrites",
            "rate_limit_per_user",
            "type",
            "rtc_region",
            "video_quality_mode",
            "archived",
            "auto_archive_duration",
            "locked",
            "invitable",
            "default_auto_archive_duration",
            "flags",
            "default_thread_rate_limit_per_user",
            "default_reaction_emoji",
            "available_tags",
            "applied_tags",
            "default_sort_order",
        )
        payload = {k: v for k, v in options.items() if k in valid_keys}
        return self.request(r, reason=reason, json=payload)

    def bulk_channel_update(
        self,
        guild_id: Snowflake,
        data: list[guild.ChannelPositionUpdate],
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Update the positions of several guild channels."""
        r = Route("PATCH", "/guilds/{guild_id}/channels", guild_id=guild_id)
        return self.request(r, json=data, reason=reason)

    def create_channel(
        self,
        guild_id: Snowflake,
        channel_type: channel.ChannelType,
        *,
        reason: str | None = None,
        **options: Any,
    ) -> Response[channel.GuildChannel]:
        """Create a guild channel."""
        payload = {
            "type": channel_type,
        }

        valid_keys = (
            "name",
            "parent_id",
            "topic",
            "bitrate",
            "nsfw",
            "user_limit",
            "position",
            "permission_overwrites",
            "rate_limit_per_user",
            "rtc_region",
            "video_quality_mode",
            "auto_archive_duration",
            "default_reaction_emoji",
            "default_auto_archive_duration",
            "default_thread_rate_limit_per_user",
            "default_sort_order",
            "available_tags",
            "flags",
        )
        if "default_thread_slowmode_delay" in options:
            options["default_thread_rate_limit_per_user"] = options.pop(
                "default_thread_slowmode_delay"
            )
        payload.update(
            {k: v for k, v in options.items() if k in valid_keys and v is not None}
        )

        return self.request(
            Route("POST", "/guilds/{guild_id}/channels", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def delete_channel(
        self,
        channel_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete a channel."""
        return self.request(
            Route("DELETE", "/channels/{channel_id}", channel_id=channel_id),
            reason=reason,
        )

    def start_thread_with_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        name: str,
        auto_archive_duration: threads.ThreadArchiveDuration,
        rate_limit_per_user: int,
        reason: str | None = None,
    ) -> Response[threads.Thread]:
        """Start a thread from a message."""
        payload = {
            "name": name,
            "auto_archive_duration": auto_archive_duration,
            "rate_limit_per_user": rate_limit_per_user,
        }

        route = Route(
            "POST",
            "/channels/{channel_id}/messages/{message_id}/threads",
            channel_id=channel_id,
            message_id=message_id,
        )
        return self.request(route, json=payload, reason=reason)

    def start_thread_without_message(
        self,
        channel_id: Snowflake,
        *,
        name: str,
        auto_archive_duration: threads.ThreadArchiveDuration,
        type: threads.ThreadType,
        rate_limit_per_user: int,
        invitable: bool,
        reason: str | None = None,
    ) -> Response[threads.Thread]:
        """Start a thread that is not attached to a message."""
        payload = {
            "name": name,
            "auto_archive_duration": auto_archive_duration,
            "type": type,
            "rate_limit_per_user": rate_limit_per_user,
            "invitable": invitable,
        }

        route = Route("POST", "/channels/{channel_id}/threads", channel_id=channel_id)
        return self.request(route, json=payload, reason=reason)

    def start_forum_thread(
        self,
        channel_id: Snowflake,
        content: str | None,
        *,
        name: str,
        auto_archive_duration: threads.ThreadArchiveDuration,
        rate_limit_per_user: int,
        invitable: bool = True,
        applied_tags: Sequence[Snowflake] | None = None,
        reason: str | None = None,
        files: Sequence[File] | None = None,
        embed: embed.Embed | None = None,
        embeds: list[embed.Embed] | None = None,
        nonce: int | str | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
        stickers: Sequence[Snowflake] | None = None,
        components: list[components.Component] | None = None,
        flags: int | None = None,
    ) -> Response[threads.Thread]:
        """Start a thread in a forum or media channel."""
        payload: dict[str, Any] = {
            "name": name,
            "auto_archive_duration": auto_archive_duration,
            "invitable": invitable,
        }

        if applied_tags:
            payload["applied_tags"] = applied_tags

        if rate_limit_per_user:
            payload["rate_limit_per_user"] = rate_limit_per_user

        message_body = message_payload(
            content=content,
            embed=embed,
            embeds=embeds,
            nonce=nonce,
            allowed_mentions=allowed_mentions,
            stickers=stickers,
            components=components,
            flags=flags,
        )
        if message_body:
            payload["message"] = message_body

        route = Route(
            "POST",
            "/channels/{channel_id}/threads",
            channel_id=channel_id,
        )

        if files:
            return self.request(
                route,
                form=multipart_form(payload, files),
                files=files,
                reason=reason,
            )
        return self.request(route, json=payload, reason=reason)

    def join_thread(self, channel_id: Snowflake) -> Response[None]:
        """Join a thread."""
        return self.request(
            Route(
                "PUT",
                "/channels/{channel_id}/thread-members/@me",
                channel_id=channel_id,
            )
        )

    def add_user_to_thread(
        self, channel_id: Snowflake, user_id: Snowflake
    ) -> Response[None]:
        """Add a user to a thread."""
        return self.request(
            Route(
                "PUT",
                "/channels/{channel_id}/thread-members/{user_id}",
                channel_id=channel_id,
                user_id=user_id,
            )
        )

    def leave_thread(self, channel_id: Snowflake) -> Response[None]:
        """Leave a thread."""
        return self.request(
            Route(
                "DELETE",
                "/channels/{channel_id}/thread-members/@me",
                channel_id=channel_id,
            )
        )

    def remove_user_from_thread(
        self, channel_id: Snowflake, user_id: Snowflake
    ) -> Response[None]:
        """Remove a user from a thread."""
        route = Route(
            "DELETE",
            "/channels/{channel_id}/thread-members/{user_id}",
            channel_id=channel_id,
            user_id=user_id,
        )
        return self.request(route)

    def get_public_archived_threads(
        self, channel_id: Snowflake, before: Snowflake | None = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        """Fetch the public archived threads of a channel."""
        route = Route(
            "GET",
            "/channels/{channel_id}/threads/archived/public",
            channel_id=channel_id,
        )

        params = {}
        if before:
            params["before"] = before
        params["limit"] = limit
        return self.request(route, params=params)

    def get_private_archived_threads(
        self, channel_id: Snowflake, before: Snowflake | None = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        """Fetch the private archived threads of a channel."""
        route = Route(
            "GET",
            "/channels/{channel_id}/threads/archived/private",
            channel_id=channel_id,
        )

        params = {}
        if before:
            params["before"] = before
        params["limit"] = limit
        return self.request(route, params=params)

    def get_joined_private_archived_threads(
        self, channel_id: Snowflake, before: Snowflake | None = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        """Fetch the private archived threads the current user joined."""
        route = Route(
            "GET",
            "/channels/{channel_id}/users/@me/threads/archived/private",
            channel_id=channel_id,
        )
        params = {}
        if before:
            params["before"] = before
        params["limit"] = limit
        return self.request(route, params=params)

    def get_active_threads(
        self, guild_id: Snowflake
    ) -> Response[threads.ThreadPaginationPayload]:
        """Fetch the active threads of a guild."""
        route = Route("GET", "/guilds/{guild_id}/threads/active", guild_id=guild_id)
        return self.request(route)

    def get_thread_members(
        self, channel_id: Snowflake
    ) -> Response[list[threads.ThreadMember]]:
        """Fetch the members of a thread."""
        route = Route(
            "GET", "/channels/{channel_id}/thread-members", channel_id=channel_id
        )
        return self.request(route)

    def get_all_guild_channels(
        self, guild_id: Snowflake
    ) -> Response[list[channel.GuildChannel]]:
        """Fetch the channels of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/channels", guild_id=guild_id)
        )

    def edit_channel_permissions(
        self,
        channel_id: Snowflake,
        target: Snowflake,
        allow: int | str,
        deny: int | str,
        type: channel.OverwriteType,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Edit a permission overwrite of a channel."""
        payload = {"id": target, "allow": allow, "deny": deny, "type": type}
        r = Route(
            "PUT",
            "/channels/{channel_id}/permissions/{target}",
            channel_id=channel_id,
            target=target,
        )
        return self.request(r, json=payload, reason=reason)

    def delete_channel_permissions(
        self,
        channel_id: Snowflake,
        target: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete a permission overwrite of a channel."""
        r = Route(
            "DELETE",
            "/channels/{channel_id}/permissions/{target}",
            channel_id=channel_id,
            target=target,
        )
        return self.request(r, reason=reason)
