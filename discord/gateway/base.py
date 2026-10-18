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

"""Heartbeating websocket base shared by the main gateway and the voice gateway."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import sys
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import aiohttp

__all__ = ("BaseWebSocket", "KeepAliveHandler")

_log = logging.getLogger(__name__)


class KeepAliveHandler(threading.Thread):
    """Sends the heartbeats of a websocket from a dedicated thread."""

    def __init__(
        self,
        *args: Any,
        ws: BaseWebSocket,
        shard_id: int | None = None,
        interval: float | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("daemon", True)
        kwargs.setdefault("name", f"keep-alive-handler:shard-{shard_id}")
        super().__init__(*args, **kwargs)
        self.ws: BaseWebSocket = ws
        self._main_thread_id = ws.thread_id
        self.interval = interval
        self.shard_id = shard_id
        self.msg = "Keeping shard ID %s websocket alive with sequence %s."
        self.block_msg = "Shard ID %s heartbeat blocked for more than %s seconds."
        self.behind_msg = "Can't keep up, shard ID %s websocket is %.1fs behind."
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self._last_recv = time.perf_counter()
        self.latency = float("inf")
        self.heartbeat_timeout = ws._max_heartbeat_timeout

    def run(self) -> None:
        """Send a heartbeat every interval until stopped or the connection dies."""
        while not self._stop_ev.wait(self.interval):
            if self._last_recv + self.heartbeat_timeout < time.perf_counter():
                _log.warning(
                    (
                        "Shard ID %s has stopped responding to the gateway. Closing and"
                        " restarting."
                    ),
                    self.shard_id,
                )
                coro = self.ws.close(4000)
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                try:
                    f.result()
                except BaseException:
                    _log.exception(
                        "An error occurred while stopping the gateway. Ignoring."
                    )
                finally:
                    self.stop()
                return

            data = self.get_payload()
            _log.debug(self.msg, self.shard_id, data["d"])
            coro = self.ws.send_heartbeat(data)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)
            try:
                # block until sending is complete
                total = 0
                while True:
                    try:
                        f.result(10)
                        break
                    except concurrent.futures.TimeoutError:
                        total += 10
                        try:
                            frame = sys._current_frames()[self._main_thread_id]
                        except KeyError:
                            msg = self.block_msg
                        else:
                            stack = "".join(traceback.format_stack(frame))
                            msg = (
                                f"{self.block_msg}\nLoop thread traceback (most recent"
                                f" call last):\n{stack}"
                            )
                        _log.warning(msg, self.shard_id, total)

            except Exception:
                self.stop()
            else:
                self._last_send = time.perf_counter()

    def get_payload(self) -> dict[str, Any]:
        """The heartbeat payload."""
        return {"op": self.ws.HEARTBEAT, "d": self.ws.sequence}

    def stop(self) -> None:
        """Stop sending heartbeats."""
        self._stop_ev.set()

    def tick(self) -> None:
        """Record that a frame was received."""
        self._last_recv = time.perf_counter()

    def ack(self) -> None:
        """Record a heartbeat acknowledgement and update the latency."""
        ack_time = time.perf_counter()
        self._last_ack = ack_time
        self.latency = ack_time - self._last_send
        if self.latency > 10:
            _log.warning(self.behind_msg, self.shard_id, self.latency)


class BaseWebSocket:
    """A websocket kept alive by a :class:`KeepAliveHandler`."""

    HEARTBEAT: ClassVar[int] = 1

    if TYPE_CHECKING:
        gateway: str

    def __init__(
        self,
        socket: aiohttp.ClientWebSocketResponse,
        *,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.socket: aiohttp.ClientWebSocketResponse = socket
        self.loop: asyncio.AbstractEventLoop = loop
        self.thread_id: int = threading.get_ident()
        self.sequence: int | None = None
        self._keep_alive: KeepAliveHandler | None = None
        self._close_code: int | None = None
        self._max_heartbeat_timeout: float = 60.0

    @property
    def open(self) -> bool:
        """Whether the underlying websocket is still open."""
        return not self.socket.closed

    @property
    def latency(self) -> float:
        """Latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds, ``inf`` before the first one."""
        heartbeat = self._keep_alive
        return float("inf") if heartbeat is None else heartbeat.latency

    def _stop_keep_alive(self) -> None:
        if self._keep_alive:
            self._keep_alive.stop()
            self._keep_alive = None

    async def send_heartbeat(self, data: Any) -> None:
        """Send a heartbeat payload."""
        raise NotImplementedError

    async def close(self, code: int = 1000) -> None:
        """Close the websocket."""
        raise NotImplementedError
