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

"""Voice gateway event parsers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ... import utils
from ...channel import VocalGuildChannel, VoiceChannelEffectSendEvent
from ...raw_models import (
    ChannelInfo,
    RawVoiceChannelStartTimeUpdateEvent,
    RawVoiceChannelStatusUpdateEvent,
    RawVoiceServerUpdateEvent,
    RawVoiceStateUpdateEvent,
)
from ...soundboard import PartialSoundboardSound

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

    from ...soundboard import SoundboardSound
    from ...types.channel import (
        VoiceChannelEffectSendEvent as VoiceChannelEffectSendPayload,
    )
    from ...types.raw_models import (
        ChannelInfoEvent,
        VoiceChannelStartTimeUpdateEvent,
        VoiceChannelStatusUpdateEvent,
    )
    from ...types.voice import (
        VoiceServerUpdate as VoiceServerUpdateEvent,
        VoiceState as VoiceStateEvent,
    )
    from ...user import ClientUser
    from ..state import ConnectionState

logger = logging.getLogger(__name__)


async def logging_coroutine(coroutine: Coroutine[Any, Any, Any], *, info: str) -> None:
    """Await ``coroutine`` and log any exception it raises."""
    try:
        await coroutine
    except Exception:
        logger.exception("Exception occurred during %s", info)


async def parse_voice_state_update(
    state: ConnectionState, data: VoiceStateEvent
) -> None:
    """Handle the ``VOICE_STATE_UPDATE`` gateway event."""
    guild = await state._get_guild(utils._get_as_snowflake(data, "guild_id"))
    channel_id = utils._get_as_snowflake(data, "channel_id")
    flags = state.member_cache_flags
    # state.user is *always* cached when this is called
    self_id = cast("ClientUser", state.user).id
    if guild is not None:
        if int(data["user_id"]) == self_id:
            voice = state._get_voice_client(guild.id)
            if voice is not None:
                payload = RawVoiceStateUpdateEvent(data=data, state=state)
                payload.afk = (
                    channel_id is not None and guild.afk_channel_id == channel_id
                )
                coro = voice.on_voice_state_update(payload)
                state._create_task(
                    logging_coroutine(
                        coro, info="Voice Protocol voice state update handler"
                    )
                )
        member, before, after = await guild._update_voice_state(data, channel_id)
        if member is not None:
            if flags.voice:
                if channel_id is None and flags._voice_only and member.id != self_id:
                    # Only remove from cache if we only have the voice flag enabled
                    # Member doesn't meet the Snowflake protocol currently
                    await guild._remove_member(member)
                elif channel_id is not None:
                    await guild._add_member(member)

            state.dispatch("voice_state_update", member, before, after)
        else:
            logger.debug(
                (
                    "VOICE_STATE_UPDATE referencing an unknown member ID: %s."
                    " Discarding."
                ),
                data["user_id"],
            )


async def parse_voice_server_update(
    state: ConnectionState, data: VoiceServerUpdateEvent
) -> None:
    """Handle the ``VOICE_SERVER_UPDATE`` gateway event."""
    vc = state._get_voice_client(int(data["guild_id"]))
    payload = RawVoiceServerUpdateEvent(data=data, state=state)
    if vc is not None:
        coro = vc.on_voice_server_update(payload)
        state._create_task(
            logging_coroutine(coro, info="Voice Protocol voice server update handler")
        )


async def parse_voice_channel_status_update(
    state: ConnectionState, data: VoiceChannelStatusUpdateEvent
) -> None:
    """Handle the ``VOICE_CHANNEL_STATUS_UPDATE`` gateway event."""
    raw = RawVoiceChannelStatusUpdateEvent(data)
    state.dispatch("raw_voice_channel_status_update", raw)
    guild = await state._get_guild(int(data["guild_id"]))
    channel_id = int(data["id"])
    if guild is not None:
        channel = await guild.get_channel(channel_id)
        if isinstance(channel, VocalGuildChannel):
            old_status = channel.status
            channel._update_status(status=data.get("status"))
            await guild._add_channel(channel)
            state.dispatch(
                "voice_channel_status_update", channel, old_status, channel.status
            )
        else:
            logger.debug(
                "VOICE_CHANNEL_STATUS_UPDATE referencing an unknown channel ID: %s. Discarding.",
                channel_id,
            )
    else:
        logger.debug(
            "VOICE_CHANNEL_STATUS_UPDATE referencing unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )


async def parse_voice_channel_start_time_update(
    state: ConnectionState, data: VoiceChannelStartTimeUpdateEvent
) -> None:
    """Handle the ``VOICE_CHANNEL_START_TIME_UPDATE`` gateway event."""
    raw = RawVoiceChannelStartTimeUpdateEvent(data)
    state.dispatch("raw_voice_channel_start_time_update", raw)
    guild = await state._get_guild(int(data["guild_id"]))
    channel_id = int(data["id"])
    if guild is not None:
        channel = await guild.get_channel(channel_id)
        if isinstance(channel, VocalGuildChannel):
            old_start_time = channel.voice_start_time
            channel._update_status(voice_start_time=data.get("voice_start_time"))
            await guild._add_channel(channel)
            state.dispatch(
                "voice_channel_start_time_update",
                channel,
                old_start_time,
                channel.voice_start_time,
            )
        else:
            logger.debug(
                "VOICE_CHANNEL_START_TIME_UPDATE referencing an unknown voice channel ID: %s. Discarding.",
                channel_id,
            )
    else:
        logger.debug(
            "VOICE_CHANNEL_START_TIME_UPDATE referencing unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )


async def parse_channel_info(state: ConnectionState, data: ChannelInfoEvent) -> None:
    """Handle the ``CHANNEL_INFO`` gateway event."""
    guild_id = int(data["guild_id"])
    channel_info = [ChannelInfo(channel) for channel in data["channels"]]
    logger.debug(
        "Processed channel info for %s channels in guild ID %s.",
        len(channel_info),
        guild_id,
    )
    await state.process_info_requests(guild_id, channel_info)


async def parse_voice_channel_effect_send(
    state: ConnectionState, data: VoiceChannelEffectSendPayload
) -> None:
    """Handle the ``VOICE_CHANNEL_EFFECT_SEND`` gateway event."""
    sound: SoundboardSound | PartialSoundboardSound | None = None
    if sound_id := int(data.get("sound_id", 0)):
        sound = await state._get_sound(sound_id)
        if sound is None:
            sound = PartialSoundboardSound(data, state, state.http)
    guild_id = int(data["guild_id"])
    raw = VoiceChannelEffectSendEvent(
        data,
        state,
        sound,
        user=await state._get_member(guild_id, int(data["user_id"])),
        channel=await state._guild_bucket("channels", guild_id).get(
            int(data["channel_id"])
        ),
    )

    state.dispatch("voice_channel_effect_send", raw)
