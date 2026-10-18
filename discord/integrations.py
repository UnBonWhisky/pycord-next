"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, cast

from ._internal.aliases import AliasMixin
from .enums import ExpireBehaviour, try_enum
from .errors import InvalidArgument
from .user import User
from .utils import MISSING, _get_as_snowflake, parse_time

__all__ = (
    "BotIntegration",
    "Integration",
    "IntegrationAccount",
    "IntegrationApplication",
    "StreamIntegration",
)

if TYPE_CHECKING:
    from .guild import Guild, PartialGuild
    from .role import Role
    from .state import ConnectionState
    from .types.integration import (
        BotIntegration as BotIntegrationPayload,
        Integration as IntegrationPayload,
        IntegrationAccount as IntegrationAccountPayload,
        IntegrationApplication as IntegrationApplicationPayload,
        IntegrationType,
        StreamIntegration as StreamIntegrationPayload,
    )


class IntegrationAccount:
    """Represents an integration account.

    .. versionadded:: 1.4

    Attributes
    ----------
    id: :class:`str`
        The account ID.
    name: :class:`str`
        The account name.
    """

    __slots__ = ("id", "name")

    def __init__(self, data: IntegrationAccountPayload) -> None:
        self.id: str = data["id"]
        self.name: str = data["name"]

    def __repr__(self) -> str:
        return f"<IntegrationAccount id={self.id} name={self.name!r}>"


class Integration(AliasMixin):
    """Represents a guild integration.

    .. versionadded:: 1.4

    Attributes
    ----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild_id: :class:`int`
        The ID of the guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    account: :class:`IntegrationAccount`
        The account linked to this integration.
    user: Optional[:class:`User`]
        The user that added this integration. Some older integrations
        do not have an attached user.
    """

    __slots__ = (
        "_state",
        "account",
        "enabled",
        "guild_id",
        "id",
        "name",
        "type",
        "user",
    )

    def __init__(
        self, *, data: IntegrationPayload, guild: Guild | PartialGuild
    ) -> None:
        self.guild_id: int = guild.id
        self._state = guild._state
        self._from_data(data)

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild of the integration.

        This is the cached :class:`Guild` when the in-process cache holds it,
        otherwise a :class:`PartialGuild` handle (always the case with a remote cache backend).
        """
        from .guild import PartialGuild

        state = self._state
        if state.cache.supports_sync:
            guild = state._guilds.get_nowait(self.guild_id)
            if guild is not None:
                return guild
        return PartialGuild(state=state, id=self.guild_id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r}>"

    def _from_data(self, data: IntegrationPayload) -> None:
        self.id: int = int(data["id"])
        self.type: IntegrationType = data["type"]
        self.name: str = data["name"]
        self.account: IntegrationAccount = IntegrationAccount(data["account"])

        user = data.get("user")
        self.user: User | None = User(state=self._state, data=user) if user else None
        self.enabled: bool = data["enabled"]

    async def delete(self, *, reason: str | None = None) -> None:
        """|coro|

        Deletes the integration.

        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.

        Parameters
        ----------
        reason: :class:`str`
            The reason the integration was deleted. Shows up on the audit log.

            .. versionadded:: 2.0

        Raises
        ------
        Forbidden
            You do not have permission to delete the integration.
        HTTPException
            Deleting the integration failed.
        """
        await self._state.http.delete_integration(self.guild.id, self.id, reason=reason)


class StreamIntegration(Integration):
    """Represents a stream integration for Twitch or YouTube.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild_id: :class:`int`
        The ID of the guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    syncing: Optional[:class:`bool`]
        Where the integration is currently syncing, if provided.
    enable_emoticons: Optional[:class:`bool`]
        Whether emoticons should be synced for this integration (currently twitch only), if provided.
    expire_behaviour: Optional[:class:`ExpireBehaviour`]
        The behaviour of expiring subscribers, if provided.
    expire_grace_period: Optional[:class:`int`]
        The grace period (in days) for expiring subscribers, if provided.
    user: Optional[:class:`User`]
        The user for the integration.
    account: :class:`IntegrationAccount`
        The integration account information.
    synced_at: Optional[:class:`datetime.datetime`]
        An aware UTC datetime representing when the integration was last synced, if provided.
    role_id: Optional[:class:`int`]
        The ID of the role which the integration uses for subscribers, if provided.
    subscriber_count: Optional[:class:`int`]
        How many subscribers the integration has, if provided.
    revoked: Optional[:class:`bool`]
        Whether the integration has been revoked, if provided.
    """

    __slots__ = (
        "enable_emoticons",
        "expire_behaviour",
        "expire_grace_period",
        "revoked",
        "role_id",
        "subscriber_count",
        "synced_at",
        "syncing",
    )

    def _from_data(self, data: IntegrationPayload) -> None:
        super()._from_data(data)
        stream = cast("StreamIntegrationPayload", data)
        expire_behavior = stream.get("expire_behavior")
        synced_at = stream.get("synced_at")
        self.revoked: bool | None = stream.get("revoked")
        self.expire_behaviour: ExpireBehaviour | None = (
            try_enum(ExpireBehaviour, expire_behavior)
            if expire_behavior is not None
            else None
        )
        self.expire_grace_period: int | None = stream.get("expire_grace_period")
        self.synced_at: dt.datetime | None = (
            parse_time(synced_at) if synced_at else None
        )
        self.role_id: int | None = _get_as_snowflake(stream, "role_id")
        self.syncing: bool | None = stream.get("syncing")
        self.enable_emoticons: bool | None = stream.get("enable_emoticons")
        self.subscriber_count: int | None = stream.get("subscriber_count")

    @property
    def role(self) -> Role | None:
        """The role which the integration uses for subscribers.

        This reads the in-process cache and raises :exc:`SyncCacheAccessError`
        with a remote cache backend, use :meth:`get_role` instead.
        """
        if self.role_id is None:
            return None
        return self._state._guild_bucket("roles", self.guild_id).get_nowait(
            self.role_id
        )

    async def get_role(self) -> Role | None:
        """|coro|

        Returns the cached role which the integration uses for subscribers.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`Role`]
            The role, or ``None`` if the integration has none or it is not cached.
        """
        if self.role_id is None:
            return None
        return await self._state._guild_bucket("roles", self.guild_id).get(self.role_id)

    async def edit(
        self,
        *,
        expire_behaviour: ExpireBehaviour = MISSING,
        expire_behavior: ExpireBehaviour = MISSING,
        expire_grace_period: int = MISSING,
        enable_emoticons: bool = MISSING,
    ) -> None:
        """|coro|

        Edits the integration.

        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.

        Parameters
        ----------
        expire_behaviour: :class:`ExpireBehaviour`
            The behaviour when an integration subscription lapses.
        expire_grace_period: :class:`int`
            The period (in days) where the integration will ignore lapsed subscriptions.
        enable_emoticons: :class:`bool`
            Where emoticons should be synced for this integration (currently twitch only).

        Raises
        ------
        Forbidden
            You do not have permission to edit the integration.
        HTTPException
            Editing the guild failed.
        InvalidArgument
            ``expire_behaviour`` did not receive a :class:`ExpireBehaviour`.
        """
        payload: dict[str, Any] = {}
        if expire_behaviour is not MISSING:
            behaviour = cast("object", expire_behaviour)
            if not isinstance(behaviour, ExpireBehaviour):
                raise InvalidArgument(
                    "expire_behaviour field must be of type ExpireBehaviour"
                )

            payload["expire_behavior"] = behaviour.value

        if expire_grace_period is not MISSING:
            payload["expire_grace_period"] = expire_grace_period

        if enable_emoticons is not MISSING:
            payload["enable_emoticons"] = enable_emoticons

        # This endpoint is undocumented.
        # Unsure if it returns the data or not as a result
        await self._state.http.edit_integration(self.guild.id, self.id, **payload)

    async def sync(self) -> None:
        """|coro|

        Syncs the integration.

        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.

        Raises
        ------
        Forbidden
            You do not have permission to sync the integration.
        HTTPException
            Syncing the integration failed.
        """
        await self._state.http.sync_integration(self.guild.id, self.id)
        self.synced_at = dt.datetime.now(dt.timezone.utc)

    if TYPE_CHECKING:
        expire_behavior: ExpireBehaviour


class IntegrationApplication:
    """Represents an application for a bot integration.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The ID for this application.
    name: :class:`str`
        The application's name.
    icon: Optional[:class:`str`]
        The application's icon hash.
    description: :class:`str`
        The application's description. Can be an empty string.
    summary: :class:`str`
        The summary of the application. Can be an empty string, which is also
        the value when Discord does not provide it.
    user: Optional[:class:`User`]
        The bot user on this application.
    """

    __slots__ = (
        "description",
        "icon",
        "id",
        "name",
        "summary",
        "user",
    )

    def __init__(
        self, *, data: IntegrationApplicationPayload, state: ConnectionState
    ) -> None:
        self.id: int = int(data["id"])
        self.name: str = data["name"]
        self.icon: str | None = data["icon"]
        self.description: str = data["description"]
        self.summary: str = data.get("summary", "")
        user = data.get("bot")
        self.user: User | None = User(state=state, data=user) if user else None


class BotIntegration(Integration):
    """Represents a bot integration on discord.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild_id: :class:`int`
        The ID of the guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    user: :class:`User`
        The user that added this integration.
    account: :class:`IntegrationAccount`
        The integration account information.
    application: :class:`IntegrationApplication`
        The application tied to this integration.
    scopes: List[:class:`str`]
        The OAuth2 scopes the application has been authorized for. Empty if not provided.
    """

    __slots__ = ("application", "scopes")

    def _from_data(self, data: IntegrationPayload) -> None:
        super()._from_data(data)
        bot = cast("BotIntegrationPayload", data)
        self.application = IntegrationApplication(
            data=bot["application"], state=self._state
        )
        self.scopes: list[str] = list(bot.get("scopes", []))


def _integration_factory(  # pyright: ignore[reportUnusedFunction]
    value: str,
) -> tuple[type[Integration], str]:
    if value == "discord":
        return BotIntegration, value
    if value in {"twitch", "youtube"}:
        return StreamIntegration, value
    return Integration, value
