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

"""Discord API routes for the invite resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ... import utils
from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...file import File
    from ...types import (
        invite,
    )
    from ...types.invite import (
        InviteTargetUsersJobStatus as InviteTargetUsersJobStatusPayload,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("InviteRoutes",)


class InviteRoutes(HTTPBase):
    """Endpoints of the invite resource."""

    def get_vanity_code(self, guild_id: Snowflake) -> Response[invite.VanityInvite]:
        """Fetch the vanity invite of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/vanity-url", guild_id=guild_id)
        )

    def create_invite(
        self,
        channel_id: Snowflake,
        *,
        reason: str | None = None,
        max_age: int = 0,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = True,
        target_type: invite.InviteTargetType | None = None,
        target_user_id: Snowflake | None = None,
        target_application_id: Snowflake | None = None,
        roles: list[Snowflake] | None = None,
        target_users_file: File | None = None,
        target_user_ids: Sequence[Snowflake] | None = None,
    ) -> Response[invite.Invite]:
        """Create an invite for a channel."""
        if target_users_file is not None and target_user_ids is not None:
            raise TypeError(
                "target_users_file and target_user_ids are mutually exclusive"
            )

        payload: dict[str, Any] = {
            "max_age": max_age,
            "max_uses": max_uses,
            "temporary": temporary,
            "unique": unique,
        }

        if target_type:
            payload["target_type"] = target_type

        if target_user_id:
            payload["target_user_id"] = target_user_id

        if target_application_id:
            payload["target_application_id"] = str(target_application_id)

        if roles:
            payload["role_ids"] = roles

        if target_user_ids is not None:
            payload["target_user_ids"] = [str(i) for i in target_user_ids]

        route = Route("POST", "/channels/{channel_id}/invites", channel_id=channel_id)

        if target_users_file is not None:
            form: list[dict[str, Any]] = [
                {
                    "name": "target_users_file",
                    "value": target_users_file.fp,
                    "filename": target_users_file.filename,
                    "content_type": "text/csv",
                },
                {
                    "name": "payload_json",
                    "value": utils._to_json(payload),
                },
            ]
            return self.request(
                route, reason=reason, form=form, files=[target_users_file]
            )

        return self.request(route, reason=reason, json=payload)

    def get_invite(
        self,
        invite_id: str,
        *,
        with_counts: bool = True,
        with_expiration: bool = True,
        guild_scheduled_event_id: int | None = None,
    ) -> Response[invite.Invite]:
        """Fetch an invite."""
        params = {
            "with_counts": int(with_counts),
            "with_expiration": int(with_expiration),
        }

        if guild_scheduled_event_id is not None:
            params["guild_scheduled_event_id"] = int(guild_scheduled_event_id)

        return self.request(
            Route("GET", "/invites/{invite_id}", invite_id=invite_id), params=params
        )

    def get_invite_target_users(
        self,
        invite_id: str,
    ) -> Response[bytes]:
        """Fetch the target users of an invite."""
        return self.request(
            Route("GET", "/invites/{invite_id}/target-users", invite_id=invite_id)
        )

    def update_invite_target_users(
        self,
        invite_id: str,
        *,
        target_users_file: File,
    ) -> Response[invite.Invite]:
        """Update the target users of an invite."""
        form: list[dict[str, Any]] = [
            {
                "name": "target_users_file",
                "value": target_users_file.fp,
                "filename": target_users_file.filename,
                "content_type": "text/csv",
            },
        ]

        return self.request(
            Route("PUT", "/invites/{invite_id}/target-users", invite_id=invite_id),
            form=form,
            files=[target_users_file],
        )

    def add_invite_target_user(
        self, invite_id: str, user_id: Snowflake
    ) -> Response[None]:
        """Add a target user to an invite."""
        return self.request(
            Route(
                "PUT",
                "/invites/{invite_id}/target-users/{user_id}",
                invite_id=invite_id,
                user_id=user_id,
            )
        )

    def remove_invite_target_user(
        self, invite_id: str, user_id: Snowflake
    ) -> Response[None]:
        """Remove a target user from an invite."""
        return self.request(
            Route(
                "DELETE",
                "/invites/{invite_id}/target-users/{user_id}",
                invite_id=invite_id,
                user_id=user_id,
            )
        )

    def bulk_add_invite_target_users(
        self, invite_id: str, *, user_ids: Sequence[Snowflake]
    ) -> Response[None]:
        """Add several target users to an invite."""
        return self.request(
            Route(
                "POST",
                "/invites/{invite_id}/target-users/bulk-add",
                invite_id=invite_id,
            ),
            json={"user_ids": [str(i) for i in user_ids]},
        )

    def bulk_remove_invite_target_users(
        self, invite_id: str, *, user_ids: Sequence[Snowflake]
    ) -> Response[None]:
        """Remove several target users from an invite."""
        return self.request(
            Route(
                "POST",
                "/invites/{invite_id}/target-users/bulk-delete",
                invite_id=invite_id,
            ),
            json={"user_ids": [str(i) for i in user_ids]},
        )

    def get_invite_target_users_job_status(
        self,
        invite_id: str,
    ) -> Response[InviteTargetUsersJobStatusPayload]:
        """Fetch the status of an invite target users update."""
        return self.request(
            Route(
                "GET",
                "/invites/{invite_id}/target-users/job-status",
                invite_id=invite_id,
            ),
        )

    def invites_from(self, guild_id: Snowflake) -> Response[list[invite.Invite]]:
        """Fetch the invites of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/invites", guild_id=guild_id)
        )

    def invites_from_channel(
        self, channel_id: Snowflake
    ) -> Response[list[invite.Invite]]:
        """Fetch the invites of a channel."""
        return self.request(
            Route("GET", "/channels/{channel_id}/invites", channel_id=channel_id)
        )

    def delete_invite(
        self, invite_id: str, *, reason: str | None = None
    ) -> Response[None]:
        """Delete an invite."""
        return self.request(
            Route("DELETE", "/invites/{invite_id}", invite_id=invite_id), reason=reason
        )
