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

"""Soundboard gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...raw_models import RawSoundboardSoundDeleteEvent
from ...soundboard import SoundboardSound

if TYPE_CHECKING:
    from ...types.raw_models import (
        SoundboardSoundDeleteEvent,
        SoundboardSoundsEvent,
        SoundboardSoundsUpdateEvent,
    )
    from ...types.soundboard import SoundboardSound as SoundboardSoundPayload
    from ..state import ConnectionState


async def parse_soundboard_sounds(
    state: ConnectionState, data: SoundboardSoundsEvent
) -> None:
    """Handle the ``SOUNDBOARD_SOUNDS`` gateway event."""
    for sound_data in data["soundboard_sounds"]:
        await state._add_sound(
            SoundboardSound(state=state, http=state.http, data=sound_data)
        )


async def parse_guild_soundboard_sounds_update(
    state: ConnectionState, data: SoundboardSoundsUpdateEvent
) -> None:
    """Handle the ``GUILD_SOUNDBOARD_SOUNDS_UPDATE`` gateway event."""
    before_sounds: list[SoundboardSound] = []
    after_sounds: list[SoundboardSound] = []
    for sound_data in data["soundboard_sounds"]:
        after = SoundboardSound(state=state, http=state.http, data=sound_data)
        if before := await state._update_sound(after):
            before_sounds.append(before)
        after_sounds.append(after)
    if len(before_sounds) == len(after_sounds):
        state.dispatch("soundboard_sounds_update", before_sounds, after_sounds)
    state.dispatch("raw_soundboard_sounds_update", after_sounds)


async def parse_guild_soundboard_sound_update(
    state: ConnectionState, data: SoundboardSoundPayload
) -> None:
    """Handle the ``GUILD_SOUNDBOARD_SOUND_UPDATE`` gateway event."""
    after = SoundboardSound(state=state, http=state.http, data=data)
    if before := await state._update_sound(after):
        state.dispatch("soundboard_sound_update", before, after)
    state.dispatch("raw_soundboard_sound_update", after)


async def parse_guild_soundboard_sound_create(
    state: ConnectionState, data: SoundboardSoundPayload
) -> None:
    """Handle the ``GUILD_SOUNDBOARD_SOUND_CREATE`` gateway event."""
    sound = SoundboardSound(state=state, http=state.http, data=data)
    await state._add_sound(sound)
    state.dispatch("soundboard_sound_create", sound)


async def parse_guild_soundboard_sound_delete(
    state: ConnectionState, data: SoundboardSoundDeleteEvent
) -> None:
    """Handle the ``GUILD_SOUNDBOARD_SOUND_DELETE`` gateway event."""
    sound_id = int(data["sound_id"])
    sound = await state._get_sound(sound_id)
    if sound is not None:
        await state._remove_sound(sound)
        state.dispatch("soundboard_sound_delete", sound)
    state.dispatch("raw_soundboard_sound_delete", RawSoundboardSoundDeleteEvent(data))
