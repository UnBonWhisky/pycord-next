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

import struct
import threading
from types import SimpleNamespace
from typing import Any

import nacl.secret
import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord.sinks import Sink
from discord.utils import MISSING
from discord.voice.packets import RTPPacket

SECRET_KEY = bytes(range(32))


def make_rtp_bytes(
    sequence: int,
    *,
    ssrc: int = 1,
    timestamp: int | None = None,
    payload: bytes = b"opus",
    padding: bool = False,
    key: bytes = SECRET_KEY,
) -> bytes:
    if timestamp is None:
        timestamp = sequence * 960

    first = 0x80 | (0x20 if padding else 0)
    header = struct.pack(">BBHII", first, 120, sequence, timestamp, ssrc)
    box = nacl.secret.SecretBox(key)
    return header + box.encrypt(payload, nonce=header + bytes(12)).ciphertext


def make_rtp(sequence: int, **kwargs: Any) -> RTPPacket:
    return RTPPacket(make_rtp_bytes(sequence, **kwargs))


class RecordingSink(Sink):
    def __init__(self, *, opus: bool = False) -> None:
        super().__init__()
        self.opus = opus
        self.writes: list[tuple[Any, Any]] = []
        self.cleaned = threading.Event()

    def is_opus(self) -> bool:
        return self.opus

    def write(self, data: Any, user: Any) -> None:
        self.writes.append((data, user))

    def cleanup(self) -> None:
        self.cleaned.set()


class FakeConnection:
    def __init__(self, ssrc_user_map: dict[int, int] | None = None) -> None:
        self.ssrc_user_map: dict[int, int] = ssrc_user_map or {}
        self.dave_session: Any = None
        self.listeners: list[Any] = []
        self.socket: Any = None
        self.endpoint_ip: str | None = None
        self.voice_port: int | None = None

    def wait_for(self, timeout: float | None = None) -> None:
        return None

    def is_connected(self) -> bool:
        return False

    def add_socket_listener(self, callback: Any) -> None:
        self.listeners.append(callback)

    def remove_socket_listener(self, callback: Any) -> None:
        if callback in self.listeners:
            self.listeners.remove(callback)


def make_client(loop: Any, ssrc_user_map: dict[int, int] | None = None) -> Any:
    connection = FakeConnection(ssrc_user_map)
    return SimpleNamespace(
        loop=loop,
        mode="xsalsa20_poly1305",
        secret_key=list(SECRET_KEY),
        guild=None,
        _reader=MISSING,
        _connection=connection,
        _ssrc_to_id=connection.ssrc_user_map,
        _peek_member=lambda user_id: None,
        wait_until_connected=lambda: None,
        is_connected=lambda: False,
        stop_recording=lambda: None,
    )
