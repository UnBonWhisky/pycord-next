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

"""Discord API routes for the lobby resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types import lobby
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("LobbyRoutes",)


class LobbyRoutes(HTTPBase):
    """Endpoints of the lobby resource."""

    def create_lobby(
        self,
        *,
        metadata: dict[str, str] | None = None,
        members: list[lobby.LobbyMemberUpdate] | None = None,
        idle_timeout_seconds: int | None = None,
    ) -> Response[lobby.Lobby]:
        """Create a lobby."""
        payload: dict[str, Any] = {}

        if metadata is not None:
            payload["metadata"] = metadata
        if members is not None:
            payload["members"] = members
        if idle_timeout_seconds is not None:
            payload["idle_timeout_seconds"] = idle_timeout_seconds

        return self.request(Route("POST", "/lobbies"), json=payload)

    def get_lobby(self, lobby_id: Snowflake) -> Response[lobby.Lobby]:
        """Fetch a lobby."""
        return self.request(Route("GET", "/lobbies/{lobby_id}", lobby_id=lobby_id))

    def edit_lobby(
        self, lobby_id: Snowflake, payload: dict[str, Any]
    ) -> Response[lobby.Lobby]:
        """Modify a lobby."""
        return self.request(
            Route("PATCH", "/lobbies/{lobby_id}", lobby_id=lobby_id), json=payload
        )

    def delete_lobby(self, lobby_id: Snowflake) -> Response[None]:
        """Delete a lobby."""
        return self.request(Route("DELETE", "/lobbies/{lobby_id}", lobby_id=lobby_id))

    def add_lobby_member(
        self,
        lobby_id: Snowflake,
        user_id: Snowflake,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Response[lobby.LobbyMember]:
        """Add a member to a lobby or update an existing one."""
        return self.request(
            Route(
                "PUT",
                "/lobbies/{lobby_id}/members/{user_id}",
                lobby_id=lobby_id,
                user_id=user_id,
            ),
            json=payload or {},
        )

    def bulk_update_lobby_members(
        self, lobby_id: Snowflake, members: list[lobby.LobbyMemberUpdate]
    ) -> Response[list[lobby.LobbyMember]]:
        """Add, update or remove up to 25 members of a lobby."""
        return self.request(
            Route("POST", "/lobbies/{lobby_id}/members/bulk", lobby_id=lobby_id),
            json=members,
        )

    def remove_lobby_member(
        self, lobby_id: Snowflake, user_id: Snowflake
    ) -> Response[None]:
        """Remove a member from a lobby."""
        return self.request(
            Route(
                "DELETE",
                "/lobbies/{lobby_id}/members/{user_id}",
                lobby_id=lobby_id,
                user_id=user_id,
            )
        )

    def create_lobby_invite_for_user(
        self, lobby_id: Snowflake, user_id: Snowflake
    ) -> Response[lobby.LobbyInvite]:
        """Create a single-use invite to the linked channel of a lobby for a user."""
        return self.request(
            Route(
                "POST",
                "/lobbies/{lobby_id}/members/{user_id}/invites",
                lobby_id=lobby_id,
                user_id=user_id,
            )
        )

    def update_lobby_message_moderation_metadata(
        self,
        lobby_id: Snowflake,
        message_id: Snowflake,
        metadata: dict[str, str],
    ) -> Response[None]:
        """Set the moderation metadata of a lobby message."""
        return self.request(
            Route(
                "PUT",
                "/lobbies/{lobby_id}/messages/{message_id}/moderation-metadata",
                lobby_id=lobby_id,
                message_id=message_id,
            ),
            json=metadata,
        )
