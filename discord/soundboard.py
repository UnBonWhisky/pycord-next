"""
The MIT License (MIT)

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

from typing import TYPE_CHECKING, Any

from typing_extensions import override

from .asset import Asset
from .emoji import PartialEmoji
from .mixins import Hashable

if TYPE_CHECKING:
    from .emoji import AppEmoji, GuildEmoji
    from .guild import PartialGuild
    from .http import HTTPClient
    from .state import ConnectionState
    from .types.channel import (
        VoiceChannelEffectSendEvent as VoiceChannelEffectSendEventPayload,
    )
    from .types.soundboard import SoundboardSound as SoundboardSoundPayload
    from .user import User

__all__ = (
    "PartialSoundboardSound",
    "SoundboardSound",
)


class PartialSoundboardSound(Hashable):
    """A partial soundboard sound.

    .. versionadded:: 2.7

    Attributes
    ----------
    id: :class:`int`
        The sound's ID.
    volume: :class:`float`
        The sound's volume.
    emoji: :class:`PartialEmoji` | :class:`None`
        The sound's emoji. Could be ``None`` if the sound has no emoji.
    """

    __slots__ = ("_http", "_state", "emoji", "id", "volume")

    def __init__(
        self,
        data: SoundboardSoundPayload | VoiceChannelEffectSendEventPayload,
        state: ConnectionState,
        http: HTTPClient,
    ) -> None:
        self._http = http
        self._state = state
        self._from_data(data)

    def _from_data(
        self, data: SoundboardSoundPayload | VoiceChannelEffectSendEventPayload
    ) -> None:
        self.id = int(data.get("sound_id", 0))
        self.volume = (
            float(data.get("volume", 0) or data.get("sound_volume", 0)) or None
        )
        self.emoji = None
        if raw_emoji := data.get(
            "emoji"
        ):  # From gateway event (VoiceChannelEffectSendEventPayload)
            self.emoji = PartialEmoji.from_dict(raw_emoji)
        elif data.get("emoji_name") or data.get(
            "emoji_id"
        ):  # From HTTP response (SoundboardSoundPayload)
            self.emoji = PartialEmoji(
                name=data.get("emoji_name"),
                id=int(data.get("emoji_id", 0) or 0) or None,
            )

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, __class__):
            return self.id == other.id
        return NotImplemented

    @override
    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    @override
    def __hash__(self) -> int:
        return super().__hash__()

    @property
    def file(self) -> Asset:
        """:class:`Asset`: Returns the sound's file."""
        return Asset._from_soundboard_sound(self._state, sound_id=self.id)

    def __repr__(self) -> str:
        return f"<PartialSoundboardSound id={self.id} volume={self.volume} emoji={self.emoji!r}>"


class SoundboardSound(PartialSoundboardSound):
    """Represents a soundboard sound.

    .. versionadded:: 2.7

    Attributes
    ----------
    id: :class:`int`
        The sound's ID.
    volume: :class:`float`
        The sound's volume.
    emoji: :class:`PartialEmoji` | :class:`None`
        The sound's emoji. Could be ``None`` if the sound has no emoji.
    name: :class:`str`
        The sound's name.
    available: :class:`bool`
        Whether the sound is available. Could be ``False`` if the sound is not available.
        This is the case, for example, when the guild loses the boost level required to use the sound.
    guild_id: :class:`int` | :class:`None`
        The ID of the guild to which the sound belongs. Could be :class:`None` if the sound is a default sound.
    user: :class:`User` | :class:`None`
        The sound's owner. Could be ``None`` if the sound is a default sound.
    """

    __slots__ = (
        "_state",
        "available",
        "guild_id",
        "name",
        "user",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        http: HTTPClient,
        data: SoundboardSoundPayload,
    ) -> None:
        super().__init__(data, state, http)

    @override
    def _from_data(self, data: SoundboardSoundPayload) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        super()._from_data(data)
        self.name = data["name"]
        self.available: bool = data["available"]
        self.guild_id = int(data.get("guild_id", 0) or 0) or None
        user = data.get("user")
        self.user: User | None = self._state.create_user(user) if user else None

    @property
    def guild(self) -> PartialGuild | None:
        """:class:`PartialGuild` | :class:`None` A handle to the guild the sound belongs to. Is :class:`None` if the sound is a default sound."""
        if not self.guild_id:
            return None
        from .guild import PartialGuild

        return PartialGuild(state=self._state, id=self.guild_id)

    @property
    def is_default_sound(self) -> bool:
        """:class:`bool`: Whether the sound is a default sound."""
        return self.guild_id is None

    async def edit(
        self,
        *,
        name: str | None = None,
        volume: float | None = None,
        emoji: GuildEmoji | AppEmoji | PartialEmoji | str | None = None,
        reason: str | None = None,
    ) -> SoundboardSound:
        """|coro|

        Edits the sound.

        .. versionadded:: 2.7

        Parameters
        ----------
        name: Optional[:class:`str`]
            The new name of the sound.
        volume: Optional[:class:`float`]
            The new volume of the sound.
        emoji: Optional[Union[:class:`PartialEmoji`, :class:`str`]]
            The new emoji of the sound.
        reason: Optional[:class:`str`]
            The reason for editing the sound. Shows up in the audit log.

        Returns
        -------
        :class:`SoundboardSound`
            The edited sound.

        Raises
        ------
        :exc:`ValueError`
            Editing a default sound is not allowed.
        """
        guild_id = self.guild_id
        if guild_id is None:
            raise ValueError("Cannot edit a default sound.")
        payload: dict[str, Any] = {
            "name": name,
            "volume": volume,
            "emoji_id": None,
            "emoji_name": None,
        }
        partial_emoji = None
        if isinstance(emoji, str):
            partial_emoji = PartialEmoji.from_str(emoji)
        elif emoji is not None:
            partial_emoji = emoji._to_partial()

        if partial_emoji is not None:
            if partial_emoji.id is None:
                payload["emoji_name"] = partial_emoji.name
            else:
                payload["emoji_id"] = partial_emoji.id

        data = await self._http.edit_guild_sound(
            guild_id, self.id, reason=reason, **payload
        )
        return SoundboardSound(state=self._state, http=self._http, data=data)

    async def delete(self, *, reason: str | None = None) -> None:
        """|coro|

        Deletes the sound.

        .. versionadded:: 2.7

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting the sound. Shows up in the audit log.

        Raises
        ------
        :exc:`ValueError`
            Deleting a default sound is not allowed.
        """
        if self.is_default_sound:
            raise ValueError("Cannot delete a default sound.")
        await self._http.delete_sound(self, reason=reason)

    @override
    def __repr__(self) -> str:
        return f"<SoundboardSound id={self.id} name={self.name!r} volume={self.volume} emoji={self.emoji!r} guild={self.guild!r} user={self.user!r} available={self.available} default={self.is_default_sound}>"
