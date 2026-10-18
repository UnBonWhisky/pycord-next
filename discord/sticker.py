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

import unicodedata
from typing import TYPE_CHECKING, Literal, cast, overload

from .asset import Asset, AssetMixin
from .enums import StickerFormatType, StickerType, try_enum
from .errors import InvalidData
from .mixins import Hashable
from .utils import MISSING, _get_as_snowflake, find, get, snowflake_time

__all__ = (
    "GuildSticker",
    "StandardSticker",
    "Sticker",
    "StickerItem",
    "StickerPack",
)

if TYPE_CHECKING:
    import datetime as dt

    from .guild import Guild, PartialGuild
    from .state import ConnectionState
    from .types.sticker import (
        EditGuildSticker,
        GuildSticker as GuildStickerPayload,
        ListPremiumStickerPacks as ListPremiumStickerPacksPayload,
        StandardSticker as StandardStickerPayload,
        Sticker as StickerPayload,
        StickerItem as StickerItemPayload,
        StickerPack as StickerPackPayload,
    )
    from .user import User


class StickerPack(Hashable):
    """Represents a sticker pack.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker pack.

        .. describe:: x == y

           Checks if the sticker pack is equal to another sticker pack.

        .. describe:: x != y

           Checks if the sticker pack is not equal to another sticker pack.

    Attributes
    ----------
    name: :class:`str`
        The name of the sticker pack.
    description: :class:`str`
        The description of the sticker pack.
    id: :class:`int`
        The id of the sticker pack.
    stickers: List[:class:`StandardSticker`]
        The stickers of this sticker pack.
    sku_id: :class:`int`
        The SKU ID of the sticker pack.
    cover_sticker_id: Optional[:class:`int`]
         The ID of the sticker used for the cover of the sticker pack.
         ``None`` when Discord does not send it.
    cover_sticker: Optional[:class:`StandardSticker`]
        The sticker used for the cover of the sticker pack, ``None`` when there is
        no cover sticker ID or it is not one of :attr:`stickers`.
    """

    __slots__ = (
        "_banner",
        "_state",
        "cover_sticker",
        "cover_sticker_id",
        "description",
        "id",
        "name",
        "sku_id",
        "stickers",
    )

    def __init__(self, *, state: ConnectionState, data: StickerPackPayload) -> None:
        self._state: ConnectionState = state
        self._from_data(data)

    def _from_data(self, data: StickerPackPayload) -> None:
        self.id: int = int(data["id"])
        stickers = data["stickers"]
        self.stickers: list[StandardSticker] = [
            StandardSticker(state=self._state, data=sticker) for sticker in stickers
        ]
        self.name: str = data["name"]
        self.sku_id: int = int(data["sku_id"])
        cover_sticker_id = _get_as_snowflake(data, "cover_sticker_id")
        self.cover_sticker_id: int | None = cover_sticker_id
        self.cover_sticker: StandardSticker | None = (
            get(self.stickers, id=cover_sticker_id)
            if cover_sticker_id is not None
            else None
        )
        self.description: str = data["description"]
        self._banner: int | None = _get_as_snowflake(data, "banner_asset_id")

    @property
    def banner(self) -> Asset | None:
        """The banner asset of the sticker pack, ``None`` when Discord does not send one."""
        if self._banner is None:
            return None
        return Asset._from_sticker_banner(self._state, self._banner)

    def __repr__(self) -> str:
        return (
            "<StickerPack"
            f" id={self.id} name={self.name!r} description={self.description!r}>"
        )

    def __str__(self) -> str:
        return self.name


class _StickerTag(Hashable, AssetMixin):
    __slots__ = ()

    id: int
    format: StickerFormatType
    _url: str

    @property
    def url(self) -> str:
        """The URL for the sticker's image."""
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        self._url = value

    async def read(self) -> bytes:
        """|coro|

        Retrieves the content of this sticker as a :class:`bytes` object.

        .. note::

            Stickers that use the :attr:`StickerFormatType.lottie` format cannot be read.

        Returns
        -------
        :class:`bytes`
            The content of the asset.

        Raises
        ------
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.
        TypeError
            The sticker is a lottie type.
        """
        if self.format is StickerFormatType.lottie:
            raise TypeError('Cannot read stickers of format "lottie".')
        return await super().read()


class StickerItem(_StickerTag):
    """Represents a sticker item.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker item.

        .. describe:: x == y

           Checks if the sticker item is equal to another sticker item.

        .. describe:: x != y

           Checks if the sticker item is not equal to another sticker item.

    Attributes
    ----------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    url: :class:`str`
        The URL for the sticker's image.
    """

    __slots__ = ("_state", "_url", "format", "id", "name")

    def __init__(self, *, state: ConnectionState, data: StickerItemPayload) -> None:
        self._state: ConnectionState = state
        self.name: str = data["name"]
        self.id: int = int(data["id"])
        self.format: StickerFormatType = try_enum(
            StickerFormatType, data["format_type"]
        )
        base = (
            "https://media.discordapp.net"
            if self.format is StickerFormatType.gif
            else Asset.BASE
        )
        self._url = f"{base}/stickers/{self.id}.{self.format.file_extension}"

    def __repr__(self) -> str:
        return f"<StickerItem id={self.id} name={self.name!r} format={self.format}>"

    def __str__(self) -> str:
        return self.name

    async def fetch(self) -> StandardSticker | GuildSticker:
        """|coro|

        Attempts to retrieve the full sticker data of the sticker item.

        Returns
        -------
        Union[:class:`StandardSticker`, :class:`GuildSticker`]
            The retrieved sticker.

        Raises
        ------
        HTTPException
            Retrieving the sticker failed.
        """
        data = await self._state.http.get_sticker(self.id)
        cls, _ = _sticker_factory(data["type"])
        return await self._state._cache_fetched(cls(state=self._state, data=data))


class Sticker(_StickerTag):
    """Represents a sticker.

    .. versionadded:: 1.6

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker.

        .. describe:: x == y

           Checks if the sticker is equal to another sticker.

        .. describe:: x != y

           Checks if the sticker is not equal to another sticker.

    Attributes
    ----------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    description: Optional[:class:`str`]
        The description of the sticker.
    pack_id: :class:`int`
        The id of the sticker's pack.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    url: :class:`str`
        The URL for the sticker's image.
    """

    __slots__ = ("_state", "_url", "description", "format", "id", "name")

    def __init__(self, *, state: ConnectionState, data: StickerPayload) -> None:
        self._state: ConnectionState = state
        self._from_data(data)

    def _from_data(self, data: StickerPayload) -> None:
        self.id: int = int(data["id"])
        self.name: str = data["name"]
        self.description: str | None = data["description"]
        self.format: StickerFormatType = try_enum(
            StickerFormatType, data["format_type"]
        )
        base = (
            "https://media.discordapp.net"
            if self.format is StickerFormatType.gif
            else Asset.BASE
        )
        self._url = f"{base}/stickers/{self.id}.{self.format.file_extension}"

    def __repr__(self) -> str:
        return f"<Sticker id={self.id} name={self.name!r}>"

    def __str__(self) -> str:
        return self.name

    @property
    def created_at(self) -> dt.datetime:
        """Returns the sticker's creation time in UTC."""
        return snowflake_time(self.id)


class StandardSticker(Sticker):
    """Represents a sticker that is found in a standard sticker pack.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker.

        .. describe:: x == y

           Checks if the sticker is equal to another sticker.

        .. describe:: x != y

           Checks if the sticker is not equal to another sticker.

    Attributes
    ----------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    description: Optional[:class:`str`]
        The description of the sticker.
    pack_id: :class:`int`
        The id of the sticker's pack.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    tags: List[:class:`str`]
        A list of tags for the sticker.
    sort_value: :class:`int`
        The sticker's sort order within its pack.
    """

    __slots__ = ("pack_id", "sort_value", "tags", "type")

    def _from_data(self, data: StickerPayload) -> None:
        super()._from_data(data)
        standard = cast("StandardStickerPayload", data)
        self.sort_value: int = standard["sort_value"]
        self.pack_id: int = int(standard["pack_id"])
        self.type: StickerType = StickerType.standard

        try:
            self.tags: list[str] = [tag.strip() for tag in standard["tags"].split(",")]
        except KeyError:
            self.tags = []

    def __repr__(self) -> str:
        return (
            f"<StandardSticker id={self.id} name={self.name!r} pack_id={self.pack_id}>"
        )

    async def pack(self) -> StickerPack:
        """|coro|

        Retrieves the sticker pack that this sticker belongs to.

        Returns
        -------
        :class:`StickerPack`
            The retrieved sticker pack.

        Raises
        ------
        InvalidData
            The corresponding sticker pack was not found.
        HTTPException
            Retrieving the sticker pack failed.
        """
        data: ListPremiumStickerPacksPayload = (
            await self._state.http.list_premium_sticker_packs()
        )
        packs = data["sticker_packs"]
        pack = find(lambda d: int(d["id"]) == self.pack_id, packs)

        if pack:
            return StickerPack(state=self._state, data=pack)
        raise InvalidData(f"Could not find corresponding sticker pack for {self!r}")


class GuildSticker(Sticker):
    """Represents a sticker that belongs to a guild.

    .. versionadded:: 2.0

    .. container:: operations

        .. describe:: str(x)

            Returns the name of the sticker.

        .. describe:: x == y

           Checks if the sticker is equal to another sticker.

        .. describe:: x != y

           Checks if the sticker is not equal to another sticker.

    Attributes
    ----------
    name: :class:`str`
        The sticker's name.
    id: :class:`int`
        The id of the sticker.
    description: Optional[:class:`str`]
        The description of the sticker.
    format: :class:`StickerFormatType`
        The format for the sticker's image.
    available: :class:`bool`
        Whether this sticker is available for use.
    guild_id: :class:`int`
        The ID of the guild that this sticker is from.
    user: Optional[:class:`User`]
        The user that created this sticker. This can only be retrieved using :meth:`Guild.fetch_sticker` and
        having the :attr:`~Permissions.manage_emojis_and_stickers` permission.
    emoji: :class:`str`
        The name of a unicode emoji that represents this sticker.
    """

    __slots__ = ("available", "emoji", "guild_id", "type", "user")

    def _from_data(self, data: StickerPayload) -> None:
        super()._from_data(data)
        guild_sticker = cast("GuildStickerPayload", data)
        self.available: bool = guild_sticker["available"]
        self.guild_id: int = int(guild_sticker["guild_id"])
        user = guild_sticker.get("user")
        self.user: User | None = self._state.create_user(user) if user else None
        self.emoji: str = guild_sticker["tags"]
        self.type: StickerType = StickerType.guild

    def __repr__(self) -> str:
        return (
            "<GuildSticker"
            f" name={self.name!r} id={self.id} guild_id={self.guild_id} user={self.user!r}>"
        )

    @property
    def guild(self) -> Guild | PartialGuild:
        """The guild that this sticker is from.

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

    async def edit(
        self,
        *,
        name: str = MISSING,
        description: str | None = MISSING,
        emoji: str = MISSING,
        reason: str | None = None,
    ) -> GuildSticker:
        """|coro|

        Edits a :class:`GuildSticker` for the guild.

        Parameters
        ----------
        name: :class:`str`
            The sticker's new name. Must be at least 2 characters.
        description: Optional[:class:`str`]
            The sticker's new description. Can be ``None``.
        emoji: :class:`str`
            The name of a unicode emoji that represents the sticker's expression.
        reason: :class:`str`
            The reason for editing this sticker. Shows up on the audit log.

        Returns
        -------
        :class:`GuildSticker`
            The newly modified sticker.

        Raises
        ------
        Forbidden
            You are not allowed to edit stickers.
        HTTPException
            An error occurred editing the sticker.
        """
        payload: EditGuildSticker = {}

        if name is not MISSING:
            payload["name"] = name

        if description is not MISSING:
            payload["description"] = description

        if emoji is not MISSING:
            try:
                emoji = unicodedata.name(emoji)
            except TypeError:
                pass
            else:
                emoji = emoji.replace(" ", "_")

            payload["tags"] = emoji

        data: GuildStickerPayload = await self._state.http.modify_guild_sticker(
            self.guild_id, self.id, payload, reason
        )
        return GuildSticker(state=self._state, data=data)

    async def delete(self, *, reason: str | None = None) -> None:
        """|coro|

        Deletes the custom :class:`Sticker` from the guild.

        You must have :attr:`~Permissions.manage_emojis_and_stickers` permission to
        do this.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this sticker. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You are not allowed to delete stickers.
        HTTPException
            An error occurred deleting the sticker.
        """
        await self._state.http.delete_guild_sticker(self.guild_id, self.id, reason)


@overload
def _sticker_factory(
    sticker_type: Literal[1],
) -> tuple[type[StandardSticker], StickerType]: ...
@overload
def _sticker_factory(
    sticker_type: Literal[2],
) -> tuple[type[GuildSticker], StickerType]: ...
def _sticker_factory(
    sticker_type: Literal[1, 2],
) -> tuple[type[StandardSticker | GuildSticker | Sticker], StickerType]:
    value = try_enum(StickerType, sticker_type)
    if value == StickerType.standard:
        return StandardSticker, value
    if value == StickerType.guild:
        return GuildSticker, value
    return Sticker, value
