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

"""Models of the lobby resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .abc import GuildChannel
from .flags import LobbyMemberFlags
from .mixins import Hashable
from .threads import Thread
from .utils import MISSING, snowflake_time

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from .abc import Snowflake
    from .state import ConnectionState
    from .types.lobby import (
        Lobby as LobbyPayload,
        LobbyInvite as LobbyInvitePayload,
        LobbyMember as LobbyMemberPayload,
        LobbyMemberUpdate as LobbyMemberUpdatePayload,
    )
    from .user import User

__all__ = (
    "Lobby",
    "LobbyInvite",
    "LobbyMember",
    "LobbyMemberUpdate",
)


class LobbyMemberUpdate:
    """Describes the changes to make to a member of a lobby.

    Used by :meth:`Client.create_lobby`, :meth:`Lobby.edit` and :meth:`Lobby.bulk_update_members`.

    .. versionadded:: 3.0

    Parameters
    ----------
    user: :class:`abc.Snowflake`
        The user to add, update or remove.
    metadata: Optional[Mapping[:class:`str`, :class:`str`]]
        The metadata of the member, up to 1000 characters in total. Pass ``None`` to clear it.
        Leave unset to keep the current value.
    flags: :class:`LobbyMemberFlags`
        The flags of the member. Leave unset to keep the current value.
    additional_name: Optional[:class:`str`]
        An additional display name for the member, 1 to 80 characters. Pass ``None`` to clear it.
        Leave unset to keep the current value.
    remove: :class:`bool`
        Whether the user is removed from the lobby instead of being added or updated.
        Only used by :meth:`Lobby.bulk_update_members`. Defaults to ``False``.
    """

    __slots__ = ("additional_name", "flags", "metadata", "remove", "user_id")

    def __init__(
        self,
        user: Snowflake,
        *,
        metadata: Mapping[str, str] | None = MISSING,
        flags: LobbyMemberFlags = MISSING,
        additional_name: str | None = MISSING,
        remove: bool = False,
    ) -> None:
        self.user_id: int = user.id
        self.metadata: Mapping[str, str] | None = metadata
        self.flags: LobbyMemberFlags = flags
        self.additional_name: str | None = additional_name
        self.remove: bool = remove

    def __repr__(self) -> str:
        return f"<LobbyMemberUpdate user_id={self.user_id} remove={self.remove}>"

    def to_dict(self) -> LobbyMemberUpdatePayload:
        """Returns the payload sent to Discord."""
        data: dict[str, Any] = {"id": str(self.user_id)}
        data.update(_member_fields(self.metadata, self.flags, self.additional_name))
        if self.remove:
            data["remove_member"] = True
        return data  # type: ignore[return-value]


def _member_fields(
    metadata: Mapping[str, str] | None,
    flags: LobbyMemberFlags,
    additional_name: str | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if metadata is not MISSING:
        fields["metadata"] = None if metadata is None else dict(metadata)
    if flags is not MISSING:
        fields["flags"] = flags.value
    if additional_name is not MISSING:
        fields["additional_name"] = additional_name
    return fields


class LobbyInvite:
    """Represents a single-use invite to the channel linked to a lobby.

    .. versionadded:: 3.0

    Attributes
    ----------
    code: :class:`str`
        The invite code.
    """

    __slots__ = ("code",)

    BASE = "https://discord.gg"

    def __init__(self, *, data: LobbyInvitePayload) -> None:
        self.code: str = data["code"]

    def __repr__(self) -> str:
        return f"<LobbyInvite code={self.code!r}>"

    def __str__(self) -> str:
        return self.url

    @property
    def url(self) -> str:
        """The URL of the invite."""
        return f"{self.BASE}/{self.code}"


class LobbyMember:
    """Represents a member of a lobby.

    .. versionadded:: 3.0

    Attributes
    ----------
    id: :class:`int`
        The ID of the user.
    lobby_id: :class:`int`
        The ID of the lobby the member belongs to.
    metadata: Optional[Dict[:class:`str`, :class:`str`]]
        The metadata of the member.
    flags: :class:`LobbyMemberFlags`
        The flags of the member.
    additional_name: Optional[:class:`str`]
        The additional display name of the member, such as an in-game character name.
    """

    __slots__ = (
        "_state",
        "additional_name",
        "flags",
        "id",
        "lobby_id",
        "metadata",
    )

    def __init__(
        self, *, state: ConnectionState, lobby_id: int, data: LobbyMemberPayload
    ) -> None:
        self._state: ConnectionState = state
        self.lobby_id: int = lobby_id
        self.id: int = int(data["id"])
        self.metadata: dict[str, str] | None = data.get("metadata")
        self.flags: LobbyMemberFlags = LobbyMemberFlags._from_value(
            data.get("flags", 0)
        )
        self.additional_name: str | None = data.get("additional_name")

    def __repr__(self) -> str:
        return (
            f"<LobbyMember id={self.id} lobby_id={self.lobby_id}"
            f" additional_name={self.additional_name!r}>"
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, LobbyMember)
            and self.id == other.id
            and self.lobby_id == other.lobby_id
        )

    def __hash__(self) -> int:
        return hash((self.lobby_id, self.id))

    @property
    def user(self) -> User | None:
        """The user of this member, if it is in the cache.

        This reads the in-memory cache, use :meth:`get_user` with any cache backend.
        """
        return self._state._users.get_nowait(self.id)

    async def get_user(self) -> User | None:
        """|coro|

        Returns the user of this member, if it is in the cache.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[:class:`User`]
            The user, or ``None`` if it is not cached.
        """
        return await self._state.get_user(self.id)

    async def edit(
        self,
        *,
        metadata: Mapping[str, str] | None = MISSING,
        flags: LobbyMemberFlags = MISSING,
        additional_name: str | None = MISSING,
    ) -> LobbyMember:
        """|coro|

        Updates this member.

        Parameters
        ----------
        metadata: Optional[Mapping[:class:`str`, :class:`str`]]
            The new metadata of the member, up to 1000 characters in total. Pass ``None`` to clear it.
        flags: :class:`LobbyMemberFlags`
            The new flags of the member.
        additional_name: Optional[:class:`str`]
            The new additional display name, 1 to 80 characters. Pass ``None`` to clear it.

        Returns
        -------
        :class:`LobbyMember`
            The updated member.

        Raises
        ------
        HTTPException
            Updating the member failed.
        """
        data = await self._state.http.add_lobby_member(
            self.lobby_id,
            self.id,
            payload=_member_fields(metadata, flags, additional_name),
        )
        return LobbyMember(state=self._state, lobby_id=self.lobby_id, data=data)

    async def remove(self) -> None:
        """|coro|

        Removes this member from the lobby.

        Raises
        ------
        HTTPException
            Removing the member failed.
        """
        await self._state.http.remove_lobby_member(self.lobby_id, self.id)

    async def create_invite(self) -> LobbyInvite:
        """|coro|

        Creates a single-use invite, valid for one hour, to the channel linked to the lobby
        and targeted at this member.

        Returns
        -------
        :class:`LobbyInvite`
            The created invite.

        Raises
        ------
        HTTPException
            Creating the invite failed, for example because the lobby has no linked channel.
        """
        data = await self._state.http.create_lobby_invite_for_user(
            self.lobby_id, self.id
        )
        return LobbyInvite(data=data)


class Lobby(Hashable):
    """Represents a lobby, a group of users that can communicate through the Discord Social SDK.

    Lobbies are managed with the bot token. Joining and leaving a lobby, linking a channel and
    sending lobby messages require the bearer token of a user and are not available here.

    .. versionadded:: 3.0

    .. container:: operations

        .. describe:: x == y

            Checks if two lobbies are equal.

        .. describe:: x != y

            Checks if two lobbies are not equal.

        .. describe:: hash(x)

            Returns the lobby's hash.

    Attributes
    ----------
    id: :class:`int`
        The ID of the lobby.
    application_id: :class:`int`
        The ID of the application that created the lobby.
    metadata: Optional[Dict[:class:`str`, :class:`str`]]
        The metadata of the lobby.
    members: List[:class:`LobbyMember`]
        The members of the lobby.
    linked_channel_id: Optional[:class:`int`]
        The ID of the guild channel linked to the lobby, if any.
    """

    __slots__ = (
        "_state",
        "application_id",
        "id",
        "linked_channel_id",
        "members",
        "metadata",
    )

    def __init__(self, *, state: ConnectionState, data: LobbyPayload) -> None:
        self._state: ConnectionState = state
        self.id: int = int(data["id"])
        self._update(data)

    def _update(self, data: LobbyPayload) -> None:
        self.application_id: int = int(data["application_id"])
        self.metadata: dict[str, str] | None = data.get("metadata")
        self.members: list[LobbyMember] = [
            LobbyMember(state=self._state, lobby_id=self.id, data=member)
            for member in data.get("members", [])
        ]
        linked_channel = data.get("linked_channel")
        self.linked_channel_id: int | None = (
            int(linked_channel["id"]) if linked_channel is not None else None
        )

    def __repr__(self) -> str:
        return (
            f"<Lobby id={self.id} application_id={self.application_id}"
            f" members={len(self.members)}>"
        )

    @property
    def created_at(self) -> datetime:
        """When the lobby was created."""
        return snowflake_time(self.id)

    @property
    def linked_channel(self) -> GuildChannel | Thread | None:
        """The channel linked to the lobby, if it is in the cache.

        This reads the in-memory cache, use :meth:`get_linked_channel` with any
        cache backend.
        """
        if self.linked_channel_id is None:
            return None
        state = self._state
        guild_id = state._channel_guild.get_nowait(self.linked_channel_id)
        if guild_id is None:
            return None
        channel = state._guild_bucket("channels", guild_id).get_nowait(
            self.linked_channel_id
        ) or state._guild_bucket("threads", guild_id).get_nowait(self.linked_channel_id)
        return channel if isinstance(channel, (GuildChannel, Thread)) else None

    async def get_linked_channel(self) -> GuildChannel | Thread | None:
        """|coro|

        Returns the channel linked to the lobby, if it is in the cache.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`~discord.abc.GuildChannel`, :class:`Thread`]]
            The channel, or ``None`` if it is not cached.
        """
        channel = await self._state.get_channel(self.linked_channel_id)
        return channel if isinstance(channel, (GuildChannel, Thread)) else None

    def get_member(self, user_id: int, /) -> LobbyMember | None:
        """Returns the member with the given user ID, or ``None``."""
        for member in self.members:
            if member.id == user_id:
                return member
        return None

    async def edit(
        self,
        *,
        metadata: Mapping[str, str] | None = MISSING,
        members: Sequence[LobbyMemberUpdate] = MISSING,
        idle_timeout_seconds: int = MISSING,
    ) -> Lobby:
        """|coro|

        Edits this lobby.

        Parameters
        ----------
        metadata: Optional[Mapping[:class:`str`, :class:`str`]]
            The new metadata of the lobby, up to 1000 characters in total. It replaces the current one.
        members: Sequence[:class:`LobbyMemberUpdate`]
            Up to 25 members that replace the members of the lobby. The members that are not
            in this list are removed from the lobby.
        idle_timeout_seconds: :class:`int`
            Seconds to wait before shutting down the lobby once it is idle, from 5 to 604800 (7 days).

        Returns
        -------
        :class:`Lobby`
            This lobby, updated.

        Raises
        ------
        HTTPException
            Editing the lobby failed.
        """
        payload: dict[str, Any] = {}
        if metadata is not MISSING:
            payload["metadata"] = None if metadata is None else dict(metadata)
        if members is not MISSING:
            payload["members"] = [member.to_dict() for member in members]
        if idle_timeout_seconds is not MISSING:
            payload["idle_timeout_seconds"] = idle_timeout_seconds

        self._update(await self._state.http.edit_lobby(self.id, payload))
        return self

    async def delete(self) -> None:
        """|coro|

        Deletes this lobby. Deleting a lobby that is already deleted does not fail.

        Raises
        ------
        HTTPException
            Deleting the lobby failed.
        """
        await self._state.http.delete_lobby(self.id)

    async def add_member(
        self,
        user: Snowflake,
        *,
        metadata: Mapping[str, str] | None = MISSING,
        flags: LobbyMemberFlags = MISSING,
        additional_name: str | None = MISSING,
    ) -> LobbyMember:
        """|coro|

        Adds a user to this lobby, or updates the user if it is already a member.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
            The user to add.
        metadata: Optional[Mapping[:class:`str`, :class:`str`]]
            The metadata of the member, up to 1000 characters in total.
        flags: :class:`LobbyMemberFlags`
            The flags of the member.
        additional_name: Optional[:class:`str`]
            An additional display name for the member, 1 to 80 characters. Pass ``None`` to clear it.

        Returns
        -------
        :class:`LobbyMember`
            The member.

        Raises
        ------
        HTTPException
            Adding the member failed.
        """
        data = await self._state.http.add_lobby_member(
            self.id, user.id, payload=_member_fields(metadata, flags, additional_name)
        )
        member = LobbyMember(state=self._state, lobby_id=self.id, data=data)
        self._replace_member(member)
        return member

    async def remove_member(self, user: Snowflake) -> None:
        """|coro|

        Removes a user from this lobby. Removing a user that is not a member does not fail.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
            The user to remove.

        Raises
        ------
        HTTPException
            Removing the member failed, for example because the lobby does not exist.
        """
        await self._state.http.remove_lobby_member(self.id, user.id)
        self.members = [m for m in self.members if m.id != user.id]

    async def bulk_update_members(
        self, members: Sequence[LobbyMemberUpdate]
    ) -> list[LobbyMember]:
        """|coro|

        Adds, updates or removes up to 25 members of this lobby in a single request.

        Users that Discord does not know raise :exc:`NotFound`. Users that fail the permission checks
        or that reached the maximum number of lobbies of the application are silently skipped.

        Parameters
        ----------
        members: Sequence[:class:`LobbyMemberUpdate`]
            The changes to make, between 1 and 25.

        Returns
        -------
        List[:class:`LobbyMember`]
            The members that were added or updated. Removed members are not included.

        Raises
        ------
        ValueError
            The number of changes is not between 1 and 25.
        NotFound
            A user is unknown to Discord.
        HTTPException
            Updating the members failed.
        """
        if not 1 <= len(members) <= 25:
            raise ValueError("between 1 and 25 members can be updated at once")

        data = await self._state.http.bulk_update_lobby_members(
            self.id, [member.to_dict() for member in members]
        )
        updated = [
            LobbyMember(state=self._state, lobby_id=self.id, data=m) for m in data
        ]
        removed = {m.user_id for m in members if m.remove}
        self.members = [m for m in self.members if m.id not in removed]
        for member in updated:
            self._replace_member(member)
        return updated

    async def create_invite_for(self, user: Snowflake) -> LobbyInvite:
        """|coro|

        Creates a single-use invite, valid for one hour, to the channel linked to this lobby
        and targeted at ``user``.

        Parameters
        ----------
        user: :class:`abc.Snowflake`
            The user the invite is for.

        Returns
        -------
        :class:`LobbyInvite`
            The created invite.

        Raises
        ------
        HTTPException
            Creating the invite failed, for example because the lobby has no linked channel.
        """
        data = await self._state.http.create_lobby_invite_for_user(self.id, user.id)
        return LobbyInvite(data=data)

    async def set_message_moderation_metadata(
        self, message_id: int, metadata: Mapping[str, str]
    ) -> None:
        """|coro|

        Sets the moderation metadata of a lobby message. It is delivered to the active game
        clients through the Social SDK.

        Parameters
        ----------
        message_id: :class:`int`
            The ID of the lobby message.
        metadata: Mapping[:class:`str`, :class:`str`]
            The moderation decision as up to 5 key and value pairs. Keys are at most 1024
            characters long, values at most 2000.

        Raises
        ------
        ValueError
            The metadata does not respect the limits.
        HTTPException
            Setting the metadata failed.
        """
        if len(metadata) > 5:
            raise ValueError("at most 5 moderation metadata keys are allowed")
        if any(len(k) > 1024 or len(v) > 2000 for k, v in metadata.items()):
            raise ValueError(
                "moderation metadata keys are at most 1024 characters and values at most 2000"
            )

        await self._state.http.update_lobby_message_moderation_metadata(
            self.id, message_id, dict(metadata)
        )

    def _replace_member(self, member: LobbyMember) -> None:
        for index, current in enumerate(self.members):
            if current.id == member.id:
                self.members[index] = member
                return
        self.members.append(member)
