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

from typing import TYPE_CHECKING, Any, NoReturn, cast

from .cache import CacheStore
from .guild import Guild
from .utils import MISSING, parse_time

__all__ = ("Template",)

if TYPE_CHECKING:
    import datetime as dt

    from .cache.store import CacheBucket
    from .flags import MemberCacheFlags
    from .member import Member
    from .state import ConnectionState
    from .types.emoji import Emoji as EmojiPayload
    from .types.template import Template as TemplatePayload
    from .types.user import User as UserPayload
    from .user import ClientUser, User


class _FriendlyHttpAttributeErrorHelper:
    __slots__ = ()

    def __getattr__(self, attr: str) -> NoReturn:
        raise AttributeError("PartialTemplateState does not support http methods.")


class _PartialTemplateState:
    def __init__(self, *, state: ConnectionState) -> None:
        self.__state = state
        self.__cache = CacheStore(None, state=state)
        self.http = _FriendlyHttpAttributeErrorHelper()

    @property
    def shard_count(self) -> int | None:
        return self.__state.shard_count

    @property
    def user(self) -> ClientUser | None:
        return self.__state.user

    @property
    def self_id(self) -> int:
        return cast("ClientUser", self.__state.user).id

    @property
    def member_cache_flags(self) -> MemberCacheFlags:
        return self.__state.member_cache_flags

    async def store_user(self, data: UserPayload) -> User:
        return await self.__state.store_user(data)

    def create_user(self, data: UserPayload) -> User:
        return self.__state.create_user(data)

    async def get_channel(self, id: int) -> None:
        return None

    async def store_emoji(self, guild: Guild, packet: EmojiPayload) -> None:
        return None

    def _get_voice_client(self, id: int) -> None:
        return None

    async def _get_message(self, id: int) -> None:
        return None

    async def _get_guild(self, id: int | None) -> Guild | None:
        return await self.__state._get_guild(id)

    @property
    def cache(self) -> CacheStore:
        return self.__cache

    def _guild_bucket(self, kind: str, guild_id: int | None) -> CacheBucket[int, Any]:
        return self.__cache.bucket(kind, scope=guild_id)

    async def query_members(self, **kwargs: Any) -> list[Member]:
        return []

    def __getattr__(self, attr: str) -> NoReturn:
        raise AttributeError(f"PartialTemplateState does not support {attr!r}.")


class Template:
    """Represents a Discord template.

    .. versionadded:: 1.4

    Attributes
    ----------
    code: :class:`str`
        The template code.
    uses: :class:`int`
        How many times the template has been used.
    name: :class:`str`
        The name of the template.
    description: :class:`str`
        The description of the template.
    creator: :class:`User`
        The creator of the template.
    created_at: :class:`datetime.datetime`
        An aware datetime in UTC representing when the template was created.
    updated_at: :class:`datetime.datetime`
        An aware datetime in UTC representing when the template was last updated.
        This is referred to as "last synced" in the official Discord client.
    source_guild_id: :class:`int`
        The ID of the source guild.
    is_dirty: Optional[:class:`bool`]
        Whether the template has unsynced changes.

        .. versionadded:: 2.0
    """

    __slots__ = (
        "_source_guild",
        "_state",
        "code",
        "created_at",
        "creator",
        "description",
        "is_dirty",
        "name",
        "source_guild_id",
        "updated_at",
        "uses",
    )

    def __init__(self, *, state: ConnectionState, data: TemplatePayload) -> None:
        self._state = state
        self._store(data)

    def _store(self, data: TemplatePayload) -> None:
        self.code: str = data["code"]
        self.uses: int = data["usage_count"]
        self.name: str = data["name"]
        self.description: str | None = data["description"]
        creator_data = cast("UserPayload | None", data.get("creator"))
        self.creator: User | None = (
            None if creator_data is None else self._state.create_user(creator_data)
        )

        self.created_at: dt.datetime | None = parse_time(data.get("created_at"))
        self.updated_at: dt.datetime | None = parse_time(data.get("updated_at"))

        self.source_guild_id: int = int(data["source_guild_id"])
        source_serialised = data["serialized_source_guild"]
        source_serialised["id"] = self.source_guild_id
        # Guild expects a ConnectionState, we're passing a _PartialTemplateState
        state = cast("ConnectionState", _PartialTemplateState(state=self._state))
        self._source_guild: Guild = Guild(data=source_serialised, state=state)

        self.is_dirty: bool | None = data.get("is_dirty", None)

    def __repr__(self) -> str:
        return (
            f"<Template code={self.code!r} uses={self.uses} name={self.name!r}"
            f" creator={self.creator!r} source_guild_id={self.source_guild_id} is_dirty={self.is_dirty}>"
        )

    @property
    def source_guild(self) -> Guild:
        """The source guild.

        This is the cached guild when there is one, else the guild as serialised in
        the template, which only holds the guild's own fields, not its channels,
        roles or members. It reads the in-memory cache, use :meth:`get_source_guild`
        with any cache backend.
        """
        return (
            self._state._guilds.get_nowait(self.source_guild_id) or self._source_guild
        )

    async def get_source_guild(self) -> Guild:
        """|coro|

        Returns the source guild.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`Guild`
            The cached guild when there is one, else the guild as serialised in
            the template.
        """
        return await self._state._get_guild(self.source_guild_id) or self._source_guild

    async def sync(self) -> Template:
        """|coro|

        Sync the template to the guild's current state.

        You must have the :attr:`~Permissions.manage_guild` permission in the
        source guild to do this.

        .. versionadded:: 1.7

        .. versionchanged:: 2.0
            The template is no longer synced in-place, instead it is returned.

        Returns
        -------
        :class:`Template`
            The newly synced template.

        Raises
        ------
        HTTPException
            Syncing the template failed.
        Forbidden
            You don't have permissions to sync the template.
        NotFound
            This template does not exist.
        """
        data = await self._state.http.sync_template(self.source_guild_id, self.code)
        return Template(state=self._state, data=data)

    async def edit(
        self,
        *,
        name: str = MISSING,
        description: str | None = MISSING,
    ) -> Template:
        """|coro|

        Edit the template metadata.

        You must have the :attr:`~Permissions.manage_guild` permission in the
        source guild to do this.

        .. versionadded:: 1.7

        .. versionchanged:: 2.0
            The template is no longer edited in-place, instead it is returned.

        Parameters
        ----------
        name: :class:`str`
            The template's new name.
        description: Optional[:class:`str`]
            The template's new description.

        Returns
        -------
        :class:`Template`
            The newly edited template.

        Raises
        ------
        HTTPException
            Editing the template failed.
        Forbidden
            You don't have permissions to edit the template.
        NotFound
            This template does not exist.
        """
        payload: dict[str, Any] = {}

        if name is not MISSING:
            payload["name"] = name
        if description is not MISSING:
            payload["description"] = description

        data = await self._state.http.edit_template(
            self.source_guild_id, self.code, payload
        )
        return Template(state=self._state, data=data)

    async def delete(self) -> None:
        """|coro|

        Delete the template.

        You must have the :attr:`~Permissions.manage_guild` permission in the
        source guild to do this.

        .. versionadded:: 1.7

        Raises
        ------
        HTTPException
            Deleting the template failed.
        Forbidden
            You don't have permissions to delete the template.
        NotFound
            This template does not exist.
        """
        await self._state.http.delete_template(self.source_guild_id, self.code)

    @property
    def url(self) -> str:
        """The template url.

        .. versionadded:: 2.0
        """
        return f"https://discord.new/{self.code}"
