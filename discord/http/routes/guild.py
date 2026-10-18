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

"""Discord API routes for the guild resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        guild,
        integration,
        member,
        onboarding,
        role,
        voice,
        welcome_screen,
        widget,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("GuildRoutes",)


class GuildRoutes(HTTPBase):
    """Endpoints of the guild resource."""

    def kick(
        self, user_id: Snowflake, guild_id: Snowflake, reason: str | None = None
    ) -> Response[None]:
        """Remove a member from a guild."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/members/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        return self.request(r, reason=reason)

    def ban(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        delete_message_seconds: int | None = None,
        reason: str | None = None,
    ) -> Response[None]:
        """Ban a user from a guild."""
        r = Route(
            "PUT",
            "/guilds/{guild_id}/bans/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        params: dict[str, Any] = {}

        if delete_message_seconds:
            params["delete_message_seconds"] = delete_message_seconds

        return self.request(r, params=params, reason=reason)

    def bulk_ban(
        self,
        user_ids: list[Snowflake],
        guild_id: Snowflake,
        delete_message_seconds: int | None = None,
        reason: str | None = None,
    ) -> Response[guild.GuildBulkBan]:
        """Ban several users from a guild."""
        r = Route(
            "POST",
            "/guilds/{guild_id}/bulk-ban",
            guild_id=guild_id,
        )
        payload: dict[str, Any] = {
            "user_ids": user_ids,
        }
        if delete_message_seconds:
            payload["delete_message_seconds"] = delete_message_seconds

        return self.request(r, json=payload, reason=reason)

    def unban(
        self, user_id: Snowflake, guild_id: Snowflake, *, reason: str | None = None
    ) -> Response[None]:
        """Unban a user from a guild."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/bans/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        return self.request(r, reason=reason)

    def guild_voice_state(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        *,
        mute: bool | None = None,
        deafen: bool | None = None,
        reason: str | None = None,
    ) -> Response[member.Member]:
        """Server mute or deafen a member."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/members/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        payload = {}
        if mute is not None:
            payload["mute"] = mute

        if deafen is not None:
            payload["deaf"] = deafen

        return self.request(r, json=payload, reason=reason)

    def get_guild_voice_regions(
        self, guild_id: Snowflake
    ) -> Response[list[voice.VoiceRegion]]:
        """Fetch the voice regions of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/regions", guild_id=guild_id)
        )

    def edit_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        reason: str | None = None,
        **fields: Any,
    ) -> Response[member.MemberWithUser]:
        """Edit a guild member."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/members/{user_id}",
            guild_id=guild_id,
            user_id=user_id,
        )
        return self.request(r, json=fields, reason=reason)

    def get_guild(
        self, guild_id: Snowflake, *, with_counts: bool = True
    ) -> Response[guild.Guild]:
        """Fetch a guild."""
        params = {"with_counts": int(with_counts)}
        return self.request(
            Route("GET", "/guilds/{guild_id}", guild_id=guild_id), params=params
        )

    def edit_guild(
        self, guild_id: Snowflake, *, reason: str | None = None, **fields: Any
    ) -> Response[guild.Guild]:
        """Edit a guild."""
        valid_keys = (
            "name",
            "icon",
            "afk_timeout",
            "afk_channel_id",
            "splash",
            "discovery_splash",
            "features",
            "verification_level",
            "system_channel_id",
            "default_message_notifications",
            "description",
            "explicit_content_filter",
            "banner",
            "system_channel_flags",
            "rules_channel_id",
            "public_updates_channel_id",
            "preferred_locale",
            "premium_progress_bar_enabled",
        )

        payload = {k: v for k, v in fields.items() if k in valid_keys}

        return self.request(
            Route("PATCH", "/guilds/{guild_id}", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def get_bans(
        self,
        guild_id: Snowflake,
        limit: int | None = None,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
    ) -> Response[list[guild.Ban]]:
        """Fetch the bans of a guild."""
        params: dict[str, int | Snowflake] = {}

        if limit is not None:
            params["limit"] = limit
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after

        return self.request(
            Route("GET", "/guilds/{guild_id}/bans", guild_id=guild_id), params=params
        )

    def get_ban(self, user_id: Snowflake, guild_id: Snowflake) -> Response[guild.Ban]:
        """Fetch a ban of a guild."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/bans/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            )
        )

    def get_members(
        self, guild_id: Snowflake, limit: int, after: Snowflake | None
    ) -> Response[list[member.MemberWithUser]]:
        """Fetch the members of a guild."""
        params: dict[str, Any] = {
            "limit": limit,
        }
        if after:
            params["after"] = after

        r = Route("GET", "/guilds/{guild_id}/members", guild_id=guild_id)
        return self.request(r, params=params)

    def search_members(
        self,
        guild_id: Snowflake,
        query: str,
        limit: int,
    ) -> Response[list[member.MemberWithUser]]:
        """Search the members of a guild by name."""
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
        }

        r = Route("GET", "/guilds/{guild_id}/members/search", guild_id=guild_id)
        return self.request(r, params=params)

    def get_member(
        self, guild_id: Snowflake, member_id: Snowflake
    ) -> Response[member.MemberWithUser]:
        """Fetch a guild member."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/members/{member_id}",
                guild_id=guild_id,
                member_id=member_id,
            )
        )

    def prune_members(
        self,
        guild_id: Snowflake,
        days: int,
        compute_prune_count: bool,
        roles: list[str],
        *,
        reason: str | None = None,
    ) -> Response[guild.GuildPrune]:
        """Prune inactive members of a guild."""
        payload: dict[str, Any] = {
            "days": days,
            "compute_prune_count": "true" if compute_prune_count else "false",
        }
        if roles:
            payload["include_roles"] = ", ".join(roles)

        return self.request(
            Route("POST", "/guilds/{guild_id}/prune", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def estimate_pruned_members(
        self,
        guild_id: Snowflake,
        days: int,
        roles: list[str],
    ) -> Response[guild.GuildPrune]:
        """Estimate how many members a prune would remove."""
        params: dict[str, Any] = {
            "days": days,
        }
        if roles:
            params["include_roles"] = ", ".join(roles)

        return self.request(
            Route("GET", "/guilds/{guild_id}/prune", guild_id=guild_id), params=params
        )

    def get_all_integrations(
        self, guild_id: Snowflake
    ) -> Response[list[integration.Integration]]:
        """Fetch the integrations of a guild."""
        r = Route("GET", "/guilds/{guild_id}/integrations", guild_id=guild_id)

        return self.request(r)

    def create_integration(
        self, guild_id: Snowflake, type: integration.IntegrationType, id: int
    ) -> Response[None]:
        """Attach an integration to a guild."""
        payload = {
            "type": type,
            "id": id,
        }

        r = Route("POST", "/guilds/{guild_id}/integrations", guild_id=guild_id)
        return self.request(r, json=payload)

    def edit_integration(
        self, guild_id: Snowflake, integration_id: Snowflake, **payload: Any
    ) -> Response[None]:
        """Edit an integration of a guild."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/integrations/{integration_id}",
            guild_id=guild_id,
            integration_id=integration_id,
        )

        return self.request(r, json=payload)

    def sync_integration(
        self, guild_id: Snowflake, integration_id: Snowflake
    ) -> Response[None]:
        """Sync an integration of a guild."""
        r = Route(
            "POST",
            "/guilds/{guild_id}/integrations/{integration_id}/sync",
            guild_id=guild_id,
            integration_id=integration_id,
        )

        return self.request(r)

    def delete_integration(
        self,
        guild_id: Snowflake,
        integration_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Delete an integration of a guild."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/integrations/{integration_id}",
            guild_id=guild_id,
            integration_id=integration_id,
        )

        return self.request(r, reason=reason)

    def get_widget(self, guild_id: Snowflake) -> Response[widget.Widget]:
        """Fetch the widget of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/widget.json", guild_id=guild_id)
        )

    def edit_widget(
        self, guild_id: Snowflake, payload: dict[str, Any]
    ) -> Response[widget.WidgetSettings]:
        """Edit the widget settings of a guild."""
        return self.request(
            Route("PATCH", "/guilds/{guild_id}/widget", guild_id=guild_id), json=payload
        )

    def get_roles(self, guild_id: Snowflake) -> Response[list[role.Role]]:
        """Fetch the roles of a guild."""
        return self.request(Route("GET", "/guilds/{guild_id}/roles", guild_id=guild_id))

    def get_roles_member_counts(self, guild_id: Snowflake) -> Response[dict[str, int]]:
        """Fetch the member count of every role of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/roles/member-counts", guild_id=guild_id)
        )

    def get_role(self, guild_id: Snowflake, role_id: Snowflake) -> Response[role.Role]:
        """Fetch a role of a guild."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/roles/{role_id}",
                guild_id=guild_id,
                role_id=role_id,
            )
        )

    def edit_role(
        self,
        guild_id: Snowflake,
        role_id: Snowflake,
        *,
        reason: str | None = None,
        **fields: Any,
    ) -> Response[role.Role]:
        """Edit a role."""
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/roles/{role_id}",
            guild_id=guild_id,
            role_id=role_id,
        )
        valid_keys = (
            "name",
            "permissions",
            "color",
            "colors",
            "hoist",
            "mentionable",
            "icon",
            "unicode_emoji",
        )
        payload = {k: v for k, v in fields.items() if k in valid_keys}
        return self.request(r, json=payload, reason=reason)

    def delete_role(
        self, guild_id: Snowflake, role_id: Snowflake, *, reason: str | None = None
    ) -> Response[None]:
        """Delete a role."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/roles/{role_id}",
            guild_id=guild_id,
            role_id=role_id,
        )
        return self.request(r, reason=reason)

    def replace_roles(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        role_ids: list[int],
        *,
        reason: str | None = None,
    ) -> Response[member.MemberWithUser]:
        """Replace the roles of a member."""
        return self.edit_member(
            guild_id=guild_id, user_id=user_id, roles=role_ids, reason=reason
        )

    def create_role(
        self, guild_id: Snowflake, *, reason: str | None = None, **fields: Any
    ) -> Response[role.Role]:
        """Create a role."""
        r = Route("POST", "/guilds/{guild_id}/roles", guild_id=guild_id)
        return self.request(r, json=fields, reason=reason)

    def move_role_position(
        self,
        guild_id: Snowflake,
        positions: list[guild.RolePositionUpdate],
        *,
        reason: str | None = None,
    ) -> Response[list[role.Role]]:
        """Update the positions of roles."""
        r = Route("PATCH", "/guilds/{guild_id}/roles", guild_id=guild_id)
        return self.request(r, json=positions, reason=reason)

    def add_role(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        role_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Add a role to a member."""
        r = Route(
            "PUT",
            "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            guild_id=guild_id,
            user_id=user_id,
            role_id=role_id,
        )
        return self.request(r, reason=reason)

    def remove_role(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        role_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[None]:
        """Remove a role from a member."""
        r = Route(
            "DELETE",
            "/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            guild_id=guild_id,
            user_id=user_id,
            role_id=role_id,
        )
        return self.request(r, reason=reason)

    def get_welcome_screen(
        self, guild_id: Snowflake
    ) -> Response[welcome_screen.WelcomeScreen]:
        """Fetch the welcome screen of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/welcome-screen", guild_id=guild_id)
        )

    def edit_welcome_screen(
        self, guild_id: Snowflake, payload: Any, *, reason: str | None = None
    ) -> Response[welcome_screen.WelcomeScreen]:
        """Edit the welcome screen of a guild."""
        keys = (
            "description",
            "welcome_channels",
            "enabled",
        )
        payload = {key: val for key, val in payload.items() if key in keys}
        return self.request(
            Route("PATCH", "/guilds/{guild_id}/welcome-screen", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def move_member(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        channel_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> Response[member.MemberWithUser]:
        """Move a member to another voice channel."""
        return self.edit_member(
            guild_id=guild_id, user_id=user_id, channel_id=channel_id, reason=reason
        )

    def get_onboarding(self, guild_id: Snowflake) -> Response[onboarding.Onboarding]:
        """Fetch the onboarding of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/onboarding", guild_id=guild_id)
        )

    def edit_onboarding(
        self, guild_id: Snowflake, payload: Any, *, reason: str | None = None
    ) -> Response[onboarding.Onboarding]:
        """Edit the onboarding of a guild."""
        keys = (
            "prompts",
            "default_channel_ids",
            "enabled",
            "mode",
        )
        payload = {key: val for key, val in payload.items() if key in keys}
        return self.request(
            Route("PUT", "/guilds/{guild_id}/onboarding", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    def modify_guild_incident_actions(
        self,
        guild_id: Snowflake,
        payload: guild.ModifyIncidents,
        *,
        reason: str | None = None,
    ) -> Response[guild.IncidentsData]:
        """Edit the incident actions of a guild."""
        return self.request(
            Route("PUT", "/guilds/{guild_id}/incident-actions", guild_id=guild_id),
            json=payload,
            reason=reason,
        )
