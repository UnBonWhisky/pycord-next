"""Sink packet handlers.

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .core import Packet
from .rtp import (
    FakePacket,
    ReceiverReportPacket,
    RTCPPacket,
    RTPPacket,
    SenderReportPacket,
    SilencePacket,
)

if TYPE_CHECKING:
    from discord import Member, Object, User

__all__ = (
    "FakePacket",
    "Packet",
    "RTCPPacket",
    "RTPPacket",
    "ReceiverReportPacket",
    "SenderReportPacket",
    "SilencePacket",
    "VoiceData",
)


class VoiceData:
    """Represents an audio data from a source.

    .. versionadded:: 2.7

    Attributes
    ----------
    packet: :class:`~discord.sinks.Packet`
        The packet this source data contains.
    source: :class:`~discord.User` | :class:`~discord.Member` | :class:`~discord.Object` | None
        The user that emitted this audio source.
    pcm: :class:`bytes`
        The PCM bytes of this source.
    """

    def __init__(
        self,
        packet: Packet,
        source: User | Member | Object | None,
        *,
        pcm: bytes | None = None,
    ) -> None:
        self.packet: Packet = packet
        self.source: User | Member | Object | None = source
        self.pcm: bytes = pcm or b""

    @property
    def opus(self) -> bytes | None:
        """The opus encoded data of this source, if any.

        Returns
        -------
        :class:`bytes` | None
            The decrypted opus data, or ``None`` if the packet was not decrypted.
        """
        return self.packet.decrypted_data
