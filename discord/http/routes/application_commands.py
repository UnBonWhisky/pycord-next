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

"""Discord API routes for application commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import (
        interactions,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("ApplicationCommandRoutes",)


class ApplicationCommandRoutes(HTTPBase):
    """Endpoints of the application commands resource."""

    def get_global_commands(
        self,
        application_id: Snowflake,
        *,
        with_localizations: bool = True,
        locale: str | None = None,
    ) -> Response[list[interactions.ApplicationCommand]]:
        """Fetch the global application commands."""
        params = {"with_localizations": int(with_localizations)}

        return self.request(
            Route(
                "GET",
                "/applications/{application_id}/commands",
                application_id=application_id,
            ),
            params=params,
            locale=locale,
        )

    def get_global_command(
        self,
        application_id: Snowflake,
        command_id: Snowflake,
        locale: str | None = None,
    ) -> Response[interactions.ApplicationCommand]:
        """Fetch a global application command."""
        r = Route(
            "GET",
            "/applications/{application_id}/commands/{command_id}",
            application_id=application_id,
            command_id=command_id,
        )
        return self.request(r, locale=locale)

    def upsert_global_command(
        self, application_id: Snowflake, payload: interactions.EditApplicationCommand
    ) -> Response[interactions.ApplicationCommand]:
        """Create or update a global application command."""
        r = Route(
            "POST",
            "/applications/{application_id}/commands",
            application_id=application_id,
        )
        return self.request(r, json=payload)

    def edit_global_command(
        self,
        application_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        """Edit a global application command."""
        valid_keys = (
            "name",
            "description",
            "options",
        )
        fields = {k: v for k, v in payload.items() if k in valid_keys}
        r = Route(
            "PATCH",
            "/applications/{application_id}/commands/{command_id}",
            application_id=application_id,
            command_id=command_id,
        )
        return self.request(r, json=fields)

    def delete_global_command(
        self, application_id: Snowflake, command_id: Snowflake
    ) -> Response[None]:
        """Delete a global application command."""
        r = Route(
            "DELETE",
            "/applications/{application_id}/commands/{command_id}",
            application_id=application_id,
            command_id=command_id,
        )
        return self.request(r)

    def bulk_upsert_global_commands(
        self,
        application_id: Snowflake,
        payload: list[interactions.EditApplicationCommand],
    ) -> Response[list[interactions.ApplicationCommand]]:
        """Overwrite the global application commands."""
        r = Route(
            "PUT",
            "/applications/{application_id}/commands",
            application_id=application_id,
        )
        return self.request(r, json=payload)

    def get_guild_commands(
        self, application_id: Snowflake, guild_id: Snowflake
    ) -> Response[list[interactions.ApplicationCommand]]:
        """Fetch the application commands of a guild."""
        r = Route(
            "GET",
            "/applications/{application_id}/guilds/{guild_id}/commands",
            application_id=application_id,
            guild_id=guild_id,
        )
        return self.request(r)

    def get_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[interactions.ApplicationCommand]:
        """Fetch an application command of a guild."""
        r = Route(
            "GET",
            "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
            application_id=application_id,
            guild_id=guild_id,
            command_id=command_id,
        )
        return self.request(r)

    def upsert_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        """Create or update an application command of a guild."""
        r = Route(
            "POST",
            "/applications/{application_id}/guilds/{guild_id}/commands",
            application_id=application_id,
            guild_id=guild_id,
        )
        return self.request(r, json=payload)

    def edit_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        """Edit an application command of a guild."""
        valid_keys = (
            "name",
            "description",
            "options",
        )
        fields = {k: v for k, v in payload.items() if k in valid_keys}
        r = Route(
            "PATCH",
            "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
            application_id=application_id,
            guild_id=guild_id,
            command_id=command_id,
        )
        return self.request(r, json=fields)

    def delete_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[None]:
        """Delete an application command of a guild."""
        r = Route(
            "DELETE",
            "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
            application_id=application_id,
            guild_id=guild_id,
            command_id=command_id,
        )
        return self.request(r)

    def bulk_upsert_guild_commands(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: list[interactions.EditApplicationCommand],
    ) -> Response[list[interactions.ApplicationCommand]]:
        """Overwrite the application commands of a guild."""
        r = Route(
            "PUT",
            "/applications/{application_id}/guilds/{guild_id}/commands",
            application_id=application_id,
            guild_id=guild_id,
        )
        return self.request(r, json=payload)

    def get_guild_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
    ) -> Response[list[interactions.GuildApplicationCommandPermissions]]:
        """Fetch the command permissions of a guild."""
        r = Route(
            "GET",
            "/applications/{application_id}/guilds/{guild_id}/commands/permissions",
            application_id=application_id,
            guild_id=guild_id,
        )
        return self.request(r)

    def get_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[interactions.GuildApplicationCommandPermissions]:
        """Fetch the permissions of an application command."""
        r = Route(
            "GET",
            "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
            application_id=application_id,
            guild_id=guild_id,
            command_id=command_id,
        )
        return self.request(r)

    def edit_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.BaseGuildApplicationCommandPermissions,
    ) -> Response[None]:
        """Edit the permissions of an application command."""
        r = Route(
            "PUT",
            "/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
            application_id=application_id,
            guild_id=guild_id,
            command_id=command_id,
        )
        return self.request(r, json=payload)

    def bulk_edit_guild_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: list[interactions.PartialGuildApplicationCommandPermissions],
    ) -> Response[None]:
        """Overwrite the command permissions of a guild."""
        r = Route(
            "PUT",
            "/applications/{application_id}/guilds/{guild_id}/commands/permissions",
            application_id=application_id,
            guild_id=guild_id,
        )
        return self.request(r, json=payload)
