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

import heapq
import logging
import threading
from typing import TYPE_CHECKING

from .wrapped import add_wrapped, gap_wrapped

if TYPE_CHECKING:
    from ..packets import Packet

__all__ = ("JitterBuffer",)

_log = logging.getLogger(__name__)


class JitterBuffer:
    """A jitter buffer that reorders voice packets by their sequence number.

    Parameters
    ----------
    max_size: :class:`int`
        The maximum number of packets held before the oldest are discarded.
    pref_size: :class:`int`
        The number of packets that must be buffered before one is released.
    prefill: :class:`int`
        The number of packets to receive before any packet is released.

    Raises
    ------
    ValueError
        ``max_size`` is lower than 1 or ``pref_size`` is outside of
        ``0..max_size``.
    """

    _threshold: int = 10000

    def __init__(
        self, max_size: int = 10, *, pref_size: int = 1, prefill: int = 1
    ) -> None:
        if max_size < 1:
            raise ValueError(f"max_size must be greater than 1, not {max_size}")

        if not 0 <= pref_size <= max_size:
            raise ValueError(f"pref_size must be between 0 and max_size ({max_size})")

        self.max_size: int = max_size
        self.pref_size: int = pref_size
        self.prefill: int = prefill
        self._prefill: int = prefill
        self._last_tx_seq: int = -1
        self._has_item: threading.Event = threading.Event()
        self._buffer: list[Packet] = []

    def __len__(self) -> int:
        return len(self._buffer)

    def _push(self, packet: Packet) -> None:
        heapq.heappush(self._buffer, packet)

    def _pop(self) -> Packet:
        return heapq.heappop(self._buffer)

    def _get_packet_if_ready(self) -> Packet | None:
        return self._buffer[0] if len(self._buffer) > self.pref_size else None

    def _pop_if_ready(self) -> Packet | None:
        return self._pop() if len(self._buffer) > self.pref_size else None

    def _update_has_item(self) -> None:
        prefilled = self._prefill == 0
        packet_ready = len(self._buffer) > self.pref_size

        if not prefilled or not packet_ready:
            self._has_item.clear()
            return

        next_packet = self._buffer[0]
        sequential = add_wrapped(self._last_tx_seq, 1) == next_packet.sequence
        positive_seq = self._last_tx_seq >= 0

        if (
            (sequential and positive_seq)
            or not positive_seq
            or len(self._buffer) >= self.max_size
        ):
            self._has_item.set()
        else:
            self._has_item.clear()

    def _cleanup(self) -> None:
        while len(self._buffer) > self.max_size:
            heapq.heappop(self._buffer)

    def push(self, packet: Packet) -> bool:
        """Add a packet to the buffer.

        Parameters
        ----------
        packet: :class:`Packet`
            The packet to add.

        Returns
        -------
        :class:`bool`
            ``False`` if the packet is too old and was dropped, ``True`` otherwise.
        """
        seq = packet.sequence

        if (
            gap_wrapped(self._last_tx_seq, seq) > self._threshold
            and self._last_tx_seq != -1
        ):
            _log.debug("Dropping old packet %s", packet)
            return False

        self._push(packet)

        if self._prefill > 0:
            self._prefill -= 1

        self._cleanup()
        self._update_has_item()
        return True

    def is_ready(self) -> bool:
        """Check whether a packet can be popped right now.

        Returns
        -------
        :class:`bool`
            Whether a packet is ready.
        """
        return self._has_item.is_set()

    def pop(self, *, timeout: float | None = 0) -> Packet | None:
        """Remove and return the next packet if it is ready.

        Parameters
        ----------
        timeout: :class:`float` | None
            How long to wait for a packet to become ready, in seconds.
            ``None`` waits indefinitely.

        Returns
        -------
        :class:`Packet` | None
            The next packet, or ``None`` if none became ready in time.
        """
        ok = self._has_item.wait(timeout)
        if not ok:
            return None

        if self._prefill > 0:
            return None

        packet = self._pop_if_ready()

        if packet is not None:
            self._last_tx_seq = packet.sequence

        self._update_has_item()
        return packet

    def peek(self, *, all: bool = False) -> Packet | None:
        """Look at the next packet without removing it.

        Parameters
        ----------
        all: :class:`bool`
            Whether to return the first packet even if the buffer is not yet
            ready to release it.

        Returns
        -------
        :class:`Packet` | None
            The packet, or ``None`` if there is none.
        """
        if not self._buffer:
            return None

        if all:
            return self._buffer[0]
        return self._get_packet_if_ready()

    def peek_next(self) -> Packet | None:
        """Look at the first packet if it directly follows the last released one.

        Returns
        -------
        :class:`Packet` | None
            The packet, or ``None`` if there is a gap or the buffer is empty.
        """
        packet = self.peek(all=True)

        if packet is None:
            return None

        if (
            packet.sequence == add_wrapped(self._last_tx_seq, 1)
            or self._last_tx_seq < 0
        ):
            return packet
        return None

    def gap(self) -> int:
        """Get the number of missing packets before the first buffered packet.

        Returns
        -------
        :class:`int`
            The size of the gap, ``0`` if there is none.
        """
        if self._buffer and self._last_tx_seq > 0:
            return gap_wrapped(self._last_tx_seq, self._buffer[0].sequence)
        return 0

    def flush(self) -> list[Packet]:
        """Remove every buffered packet and return them in order.

        Returns
        -------
        list[:class:`Packet`]
            The packets that were buffered, sorted by sequence.
        """
        packets = sorted(self._buffer)
        self._buffer.clear()

        if packets:
            self._last_tx_seq = packets[-1].sequence

        self._prefill = self.prefill
        self._has_item.clear()
        return packets

    def reset(self) -> None:
        """Discard every buffered packet and reset the sequence tracking."""
        self._buffer.clear()
        self._has_item.clear()
        self._prefill = self.prefill
        self._last_tx_seq = -1
