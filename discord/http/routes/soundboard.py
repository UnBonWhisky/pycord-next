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

"""Discord API routes for the soundboard resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...soundboard import PartialSoundboardSound, SoundboardSound
from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from ...types.snowflake import Snowflake
    from ...types.soundboard import (
        GuildSoundboardSounds,
        SoundboardSound as SoundboardSoundPayload,
    )
    from ..base import Response

__all__ = ("SoundboardRoutes",)


class SoundboardRoutes(HTTPBase):
    """Endpoints of the soundboard resource."""

    def delete_sound(
        self, sound: SoundboardSound, *, reason: str | None
    ) -> Response[None]:
        """Delete a soundboard sound."""
        return self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
                guild_id=sound.guild_id,
                sound_id=sound.id,
            ),
            reason=reason,
        )

    def get_default_sounds(self) -> Response[list[SoundboardSoundPayload]]:
        """Fetch the default soundboard sounds."""
        return self.request(Route("GET", "/soundboard-default-sounds"))

    def create_guild_sound(
        self, guild_id: Snowflake, reason: str | None, **payload: Any
    ) -> Response[SoundboardSoundPayload]:
        """Create a soundboard sound in a guild."""
        keys = (
            "name",
            "sound",
            "volume",
            "emoji_id",
            "emoji_name",
        )

        fields = {k: v for k, v in payload.items() if k in keys and v is not None}

        return self.request(
            Route("POST", "/guilds/{guild_id}/soundboard-sounds", guild_id=guild_id),
            json=fields,
            reason=reason,
        )

    def get_all_guild_sounds(
        self, guild_id: Snowflake
    ) -> Response[GuildSoundboardSounds]:
        """Fetch the soundboard sounds of a guild."""
        return self.request(
            Route("GET", "/guilds/{guild_id}/soundboard-sounds", guild_id=guild_id)
        )

    def get_guild_sound(
        self, guild_id: Snowflake, sound_id: Snowflake
    ) -> Response[SoundboardSoundPayload]:
        """Fetch a soundboard sound of a guild."""
        return self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
                guild_id=guild_id,
                sound_id=sound_id,
            )
        )

    def edit_guild_sound(
        self,
        guild_id: Snowflake,
        sound_id: Snowflake,
        *,
        reason: str | None,
        **payload: Any,
    ) -> Response[SoundboardSoundPayload]:
        """Edit a soundboard sound of a guild."""
        keys = (
            "name",
            "volume",
            "emoji_id",
            "emoji_name",
        )

        fields = {k: v for k, v in payload.items() if k in keys and v is not None}

        return self.request(
            Route(
                "PATCH",
                "/guilds/{guild_id}/soundboard-sounds/{sound_id}",
                guild_id=guild_id,
                sound_id=sound_id,
            ),
            json=fields,
            reason=reason,
        )

    def send_soundboard_sound(
        self, channel_id: int, sound: PartialSoundboardSound
    ) -> Response[None]:
        """Play a soundboard sound in a voice channel."""
        payload: dict[str, Any] = {
            "sound_id": sound.id,
        }
        if isinstance(sound, SoundboardSound) and not sound.is_default_sound:
            payload["source_guild_id"] = sound.guild_id

        return self.request(
            Route(
                "POST",
                "/channels/{channel_id}/send-soundboard-sound",
                channel_id=channel_id,
            ),
            json=payload,
        )
