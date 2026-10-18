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

import contextlib
import logging
import queue
import threading
from collections import deque
from typing import TYPE_CHECKING, Any

from discord.opus import PacketDecoder

from ...sinks.errors import RecordingException
from ..utils.multidataevent import MultiDataEvent

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Unpack

    from discord.sinks import Sink

    from ..packets import RTCPPacket, RTPPacket
    from .reader import AudioReader

    AnyAudioReader = AudioReader[Unpack[tuple[Any, ...]]]
    EventCB = Callable[..., Any]
    EventData = tuple[str, tuple[Any, ...], dict[str, Any]]

_log = logging.getLogger(__name__)


class PacketRouter(threading.Thread):
    """A thread that routes the received RTP packets to per-SSRC decoders and the sink.

    Parameters
    ----------
    sink: :class:`~discord.sinks.Sink`
        The sink the decoded audio is written to.
    reader: :class:`AudioReader`
        The reader that owns this router.
    """

    _poll_interval: float = 0.25

    def __init__(self, sink: Sink, reader: AnyAudioReader) -> None:
        super().__init__(
            daemon=True,
            name=f"voice-receiver-packet-router:{id(self):#x}",
        )

        self.sink: Sink = sink
        self.decoders: dict[int, PacketDecoder] = {}
        self.reader: AnyAudioReader = reader
        self.waiter: MultiDataEvent[PacketDecoder] = MultiDataEvent()

        self._lock: threading.RLock = threading.RLock()
        self._end_thread: threading.Event = threading.Event()
        self._dropped_ssrcs: deque[int] = deque(maxlen=16)

    def feed_rtp(self, packet: RTPPacket) -> None:
        """Route a received RTP packet to its decoder.

        Parameters
        ----------
        packet: :class:`RTPPacket`
            The decrypted packet.
        """
        if packet.ssrc in self._dropped_ssrcs:
            _log.debug("Ignoring packet from dropped ssrc %s", packet.ssrc)
            return

        with self._lock:
            decoder = self.get_decoder(packet.ssrc)
            if decoder is None:
                return

            if self.sink.is_opus():
                decoder.push_packet(packet)
            else:
                data = decoder.process_packet(packet)
                self.sink.write(data, data.source)

    def feed_rtcp(self, packet: RTCPPacket) -> None:
        """Dispatch a received RTCP packet as an ``rtcp_packet`` event.

        Parameters
        ----------
        packet: :class:`RTCPPacket`
            The packet.
        """
        guild = self.sink.client.guild if self.sink.client else None
        event_router = self.reader.event_router
        event_router.dispatch("rtcp_packet", packet, guild)

    def get_decoder(self, ssrc: int) -> PacketDecoder | None:
        """Get the decoder of an SSRC, creating it if needed.

        Parameters
        ----------
        ssrc: :class:`int`
            The SSRC of the stream.

        Returns
        -------
        :class:`PacketDecoder` | None
            The decoder of the stream.
        """
        with self._lock:
            decoder = self.decoders.get(ssrc)
            if decoder is None:
                decoder = self.decoders[ssrc] = PacketDecoder(self, ssrc)
            return decoder

    def set_sink(self, sink: Sink) -> None:
        """Replace the sink the decoded audio is written to.

        Parameters
        ----------
        sink: :class:`~discord.sinks.Sink`
            The new sink.
        """
        with self._lock:
            self.sink = sink

    def set_user_id(self, ssrc: int, user_id: int) -> None:
        """Associate an SSRC with a user.

        Parameters
        ----------
        ssrc: :class:`int`
            The SSRC of the stream.
        user_id: :class:`int`
            The ID of the user the stream belongs to.
        """
        with self._lock:
            if ssrc in self._dropped_ssrcs:
                self._dropped_ssrcs.remove(ssrc)

            decoder = self.decoders.get(ssrc)
            if decoder is not None:
                decoder.set_user_id(user_id)

    def destroy_decoder(self, ssrc: int) -> None:
        """Destroy the decoder of an SSRC.

        Parameters
        ----------
        ssrc: :class:`int`
            The SSRC of the stream.
        """
        with self._lock:
            decoder = self.decoders.pop(ssrc, None)
            if decoder is not None:
                self._dropped_ssrcs.append(ssrc)
                decoder.destroy()

    def destroy_all_decoders(self) -> None:
        """Destroy every decoder."""
        with self._lock:
            for ssrc in list(self.decoders):
                self.destroy_decoder(ssrc)

    def stop(self) -> None:
        """Ask the router thread to stop."""
        self._end_thread.set()
        self.waiter.notify()

    def run(self) -> None:
        """Route the buffered packets to the sink until stopped."""
        try:
            self._do_run()
        except Exception as exc:
            _log.exception("Error in %s loop", self)
            self.reader.error = exc
        finally:
            self._drain_all_decoders()
            client = self.reader.client
            if client._reader is self.reader:
                with contextlib.suppress(RecordingException):
                    client.stop_recording()
            self.waiter.clear()

    def _do_run(self) -> None:
        while not self._end_thread.is_set():
            self.waiter.wait(self._poll_interval)

            with self._lock:
                for decoder in self.waiter.items:
                    data = decoder.pop_data()
                    if data is not None:
                        self.sink.write(data, data.source)

    def _drain_all_decoders(self) -> None:
        with self._lock:
            for decoder in list(self.decoders.values()):
                try:
                    for packet in decoder._buffer.flush():
                        data = decoder.process_packet(packet)
                        self.sink.write(data, data.source)
                except Exception:
                    _log.exception(
                        "Error draining decoder for ssrc=%s at end-of-recording",
                        decoder.ssrc,
                    )


class SinkEventRouter(threading.Thread):
    """A thread that dispatches voice events to the listeners of a sink.

    Parameters
    ----------
    sink: :class:`~discord.sinks.Sink`
        The sink whose listeners receive the events.
    reader: :class:`AudioReader`
        The reader that owns this router.
    """

    def __init__(self, sink: Sink, reader: AnyAudioReader) -> None:
        super().__init__(
            daemon=True, name=f"voice-receiver-sink-event-router:{id(self):#x}"
        )

        self.sink: Sink = sink
        self.reader: AnyAudioReader = reader

        self._event_listeners: dict[str, list[EventCB]] = {}
        self._buffer: queue.SimpleQueue[EventData] = queue.SimpleQueue()
        self._lock = threading.RLock()
        self._end_thread = threading.Event()

        self.register_events()

    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        """Queue an event for the sink listeners.

        Parameters
        ----------
        event: :class:`str`
            The name of the event, without the ``on_`` prefix.
        *args
            The positional arguments of the event.
        **kwargs
            The keyword arguments of the event.
        """
        _log.debug("Dispatch voice event %s", event)
        self._buffer.put_nowait((event, args, kwargs))

    def set_sink(self, sink: Sink) -> None:
        """Replace the sink whose listeners receive the events.

        Parameters
        ----------
        sink: :class:`~discord.sinks.Sink`
            The new sink.
        """
        with self._lock:
            self.unregister_events()
            self.sink = sink
            self.register_events()

    def register_events(self) -> None:
        """Register the listeners of the sink and of its children."""
        with self._lock:
            self._register_listeners(self.sink)
            for child in self.sink.walk_children():
                self._register_listeners(child)

    def unregister_events(self) -> None:
        """Unregister the listeners of the sink and of its children."""
        with self._lock:
            self._unregister_listeners(self.sink)
            for child in self.sink.walk_children():
                self._unregister_listeners(child)

    def _register_listeners(self, sink: Sink) -> None:
        _log.debug("Registering events for %s: %s", sink, sink.__sink_listeners__)

        for name, method_name in sink.__sink_listeners__:
            func = getattr(sink, method_name)
            _log.debug("Registering event: %r (callback at %r)", name, method_name)

            if name in self._event_listeners:
                self._event_listeners[name].append(func)
            else:
                self._event_listeners[name] = [func]

    def _unregister_listeners(self, sink: Sink) -> None:
        for name, method_name in sink.__sink_listeners__:
            func = getattr(sink, method_name)

            if name in self._event_listeners:
                with contextlib.suppress(ValueError):
                    self._event_listeners[name].remove(func)

    def _dispatch_to_listeners(self, event: str, *args: Any, **kwargs: Any) -> None:
        for listener in self._event_listeners.get(f"on_{event}", []):
            try:
                listener(*args, **kwargs)
            except Exception as exc:
                _log.exception(
                    "Unhandled exception while dispatching event %s (args: %s; kwargs: %s)",
                    event,
                    args,
                    kwargs,
                    exc_info=exc,
                )

    def stop(self) -> None:
        """Ask the router thread to stop."""
        self._end_thread.set()

    def run(self) -> None:
        """Dispatch the queued events to the listeners until stopped."""
        try:
            self._do_run()
        except Exception as exc:
            _log.exception("Error in sink event router", exc_info=exc)
            self.reader.error = exc
            self.reader.client.stop_recording()

    def _do_run(self) -> None:
        while not self._end_thread.is_set():
            try:
                event, args, kwargs = self._buffer.get(timeout=0.5)
            except queue.Empty:
                continue
            else:
                with self._lock, self.reader.packet_router._lock:
                    self._dispatch_to_listeners(event, *args, **kwargs)
