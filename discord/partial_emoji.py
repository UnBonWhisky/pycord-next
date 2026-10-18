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

import re
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from . import utils
from .asset import Asset, AssetMixin
from .errors import InvalidArgument

__all__ = ("PartialEmoji",)

if TYPE_CHECKING:
    from datetime import datetime

    from typing_extensions import Self

    from .state import ConnectionState
    from .types.channel import DefaultReaction
    from .types.message import PartialEmoji as PartialEmojiPayload


class _EmojiTag:
    __slots__ = ()

    id: int | None

    def _to_partial(self) -> PartialEmoji:
        raise NotImplementedError


PE = TypeVar("PE", bound="PartialEmoji")


class PartialEmoji(_EmojiTag, AssetMixin):
    """Represents a "partial" emoji.

    This model will be given in two scenarios:

    - "Raw" data events such as :func:`on_raw_reaction_add`
    - Custom emoji that the bot cannot see from e.g. :attr:`Message.reactions`

    .. container:: operations

        .. describe:: x == y

            Checks if two emoji are the same.

        .. describe:: x != y

            Checks if two emoji are not the same.

        .. describe:: hash(x)

            Return the emoji's hash.

        .. describe:: str(x)

            Returns the emoji rendered for discord.

    Attributes
    ----------
    name: Optional[:class:`str`]
        The custom emoji name, if applicable, or the unicode codepoint
        of the non-custom emoji. This can be ``None`` if the emoji
        got deleted (e.g. removing a reaction with a deleted emoji).
    animated: :class:`bool`
        Whether the emoji is animated or not.
    id: Optional[:class:`int`]
        The ID of the custom emoji, if applicable.
    """

    __slots__ = ("_state", "animated", "id", "name")

    _CUSTOM_EMOJI_RE = re.compile(
        r"<?(?P<animated>a)?:?(?P<name>\w+):(?P<id>[0-9]{13,20})>?"
    )

    if TYPE_CHECKING:
        id: int | None

    def __init__(
        self, *, name: str | None, animated: bool = False, id: int | None = None
    ) -> None:
        self.animated = animated
        self.name = name
        self.id = id
        self._state: ConnectionState | None = None

    @classmethod
    def from_dict(cls, data: PartialEmojiPayload | dict[str, Any]) -> Self:
        """Creates a :class:`PartialEmoji` from its payload.

        Parameters
        ----------
        data
            The emoji payload.

        Returns
        -------
        :class:`PartialEmoji`
            The partial emoji built from ``data``.
        """
        return cls(
            animated=data.get("animated", False),
            id=utils._get_as_snowflake(data, "id"),
            name=data.get("name") or "",
        )

    @classmethod
    def from_str(cls, value: str) -> Self:
        """Converts a Discord string representation of an emoji to a :class:`PartialEmoji`.

        The formats accepted are:

        - ``a:name:id``
        - ``<a:name:id>``
        - ``name:id``
        - ``<:name:id>``

        If the format does not match then it is assumed to be a Unicode emoji block, either as Unicode characters or as a Discord alias (``:smile:``).

        .. versionadded:: 2.0

        Parameters
        ----------
        value: :class:`str`
            The string representation of an emoji.

        Returns
        -------
        :class:`PartialEmoji`
            The partial emoji from this string.
        """
        if unicode_emoji := utils.EMOJIS_MAP.get(
            value.removeprefix(":").removesuffix(":")
        ):
            return cls(name=unicode_emoji, id=None, animated=False)

        match = cls._CUSTOM_EMOJI_RE.match(value)
        if match is not None:
            groups = match.groupdict()
            animated = bool(groups["animated"])
            emoji_id = int(groups["id"])
            name = groups["name"]
            return cls(name=name, animated=animated, id=emoji_id)

        return cls(name=value, id=None, animated=False)

    def to_dict(self) -> dict[str, Any]:
        """Converts this emoji to its payload.

        Returns
        -------
        :class:`dict`
            The emoji payload.
        """
        o: dict[str, Any] = {"name": self.name}
        if self.id:
            o["id"] = self.id
        if self.animated:
            o["animated"] = self.animated
        return o

    def _to_partial(self) -> PartialEmoji:
        return self

    def _to_forum_reaction_payload(self) -> DefaultReaction:
        if self.id is None:
            return {"emoji_id": None, "emoji_name": self.name}
        return {"emoji_id": self.id, "emoji_name": None}

    @classmethod
    def with_state(
        cls,
        state: ConnectionState,
        *,
        name: str | None,
        animated: bool = False,
        id: int | None = None,
    ) -> Self:
        """Creates a :class:`PartialEmoji` bound to a connection state.

        Parameters
        ----------
        state
            The connection state used to download the emoji.
        name
            The emoji name.
        animated
            Whether the emoji is animated.
        id
            The ID of the custom emoji, if applicable.

        Returns
        -------
        :class:`PartialEmoji`
            The partial emoji with ``state`` attached.
        """
        self = cls(name=name, animated=animated, id=id)
        self._state = state
        return self

    def __str__(self) -> str:
        # Emoji won't render if the name is empty
        name = self.name or "_"
        if self.id is None:
            return name
        animated_tag = "a" if self.animated else ""
        return f"<{animated_tag}:{name}:{self.id}>"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} animated={self.animated} name={self.name!r} id={self.id}>"

    def __eq__(self, other: object) -> bool:
        if self.is_unicode_emoji():
            return isinstance(other, PartialEmoji) and self.name == other.name

        if isinstance(other, _EmojiTag):
            return self.id == other.id
        return False

    def __hash__(self) -> int:
        return hash((self.id, self.name))

    def is_custom_emoji(self) -> bool:
        """Checks if this is a custom non-Unicode emoji."""
        return self.id is not None

    def is_unicode_emoji(self) -> bool:
        """Checks if this is a Unicode emoji."""
        return self.id is None

    def _as_reaction(self) -> str:
        if self.id is None:
            return self.name or ""
        return f"{self.name}:{self.id}"

    @property
    def created_at(self) -> datetime | None:
        """Returns the emoji's creation time in UTC, or None if Unicode emoji.

        .. versionadded:: 1.6
        """
        if self.id is None:
            return None

        return utils.snowflake_time(self.id)

    @property
    def url(self) -> str:
        """Returns the URL of the emoji, if it is custom.

        If this isn't a custom emoji then an empty string is returned
        """
        if self.is_unicode_emoji():
            return ""

        url = f"{Asset.BASE}/emojis/{self.id}.{self.extension}"
        if self.animated:
            url += "?animated=true"
        return url

    @property
    def extension(self) -> Literal["webp", "png"]:
        """Return the file extension of the emoji.

        .. versionadded:: 2.7.1
        """
        return "webp" if self.animated else "png"

    async def read(self) -> bytes:
        """|coro|

        Retrieves the content of this emoji as a :class:`bytes` object.

        Returns
        -------
        :class:`bytes`
            The content of the emoji.

        Raises
        ------
        InvalidArgument
            The emoji is not a custom emoji.
        DiscordException
            There was no internal connection state.
        HTTPException
            Downloading the asset failed.
        NotFound
            The asset was deleted.
        """
        if self.is_unicode_emoji():
            raise InvalidArgument("PartialEmoji is not a custom emoji")

        return await super().read()
