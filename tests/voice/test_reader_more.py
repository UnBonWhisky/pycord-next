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
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

import nacl.secret

from discord.voice.packets import RTPPacket
from discord.voice.packets.rtp import decode
from discord.voice.receive import reader as reader_module
from discord.voice.receive.reader import (
    AudioReader,
    PacketDecryptor,
    SpeakingTimer,
    UDPKeepAlive,
    is_rtcp,
)

from .receive_helpers import SECRET_KEY, RecordingSink, make_client, make_rtp_bytes


@pytest.fixture
def client(loop):
    return make_client(loop)


def make_reader(client, sink=None, **kwargs):
    reader = AudioReader(sink or RecordingSink(opus=True), client, **kwargs)
    reader.keep_alive.stop()
    return reader


def test_is_rtcp():
    assert is_rtcp(bytes([0x80, 201]))
    assert not is_rtcp(bytes([0x80, 120]))


# -- reader lifecycle ----------------------------------------------------------


def test_reader_rejects_non_callable_on_finish(client):
    with pytest.raises(TypeError, match="on_finish"):
        AudioReader(RecordingSink(), client, on_finish=3)


def test_start_twice_and_stop_twice(client):
    reader = make_reader(client)
    reader.start()
    assert reader.is_listening()
    reader.start()
    reader.stop()
    assert not reader.is_listening()
    reader.stop()


def test_update_secret_key_swaps_the_box(client):
    reader = make_reader(client)
    box = reader.decryptor.box
    reader.update_secret_key(bytes(range(1, 33)))
    assert reader.decryptor.box is not box


def test_set_sink_returns_the_old_one(client):
    old = RecordingSink()
    reader = make_reader(client, old)
    new = RecordingSink()
    assert reader.set_sink(new) is old
    assert reader.sink is new
    assert new.client is client


def test_stop_survives_router_errors(client):
    sink = RecordingSink()
    after = []
    reader = make_reader(client, sink, after=after.append)
    reader.start()
    reader.packet_router.stop = MagicMock(side_effect=RuntimeError("router"))
    reader.event_router.stop = MagicMock(side_effect=RuntimeError("events"))
    sink.cleanup = MagicMock(side_effect=RuntimeError("cleanup"))
    reader.stop()
    assert isinstance(after[0], RuntimeError)


def test_stop_from_router_thread_does_not_join(client, monkeypatch):
    reader = make_reader(client)
    reader.start()
    reader.packet_router.join = MagicMock()
    reader.packet_router.is_alive = MagicMock(return_value=True)
    monkeypatch.setattr(
        reader_module.threading, "current_thread", lambda: reader.packet_router
    )
    reader._stop()
    reader.packet_router.join.assert_not_called()


def test_stop_warns_when_router_stays_alive(client, caplog):
    reader = make_reader(client)
    reader.stop_timeout = 0.01
    reader.packet_router.is_alive = MagicMock(return_value=True)
    reader.packet_router.stop = MagicMock()
    reader.packet_router.join = MagicMock()
    reader._stop()
    assert "did not stop within" in caplog.text


def test_on_finish_coroutine_runs_on_the_loop(client, loop):
    done = []

    async def finish(sink, *args):
        done.append((sink, args))

    reader = make_reader(client, on_finish=finish, args=(1,))
    t = threading.Thread(target=loop.run_forever)
    t.start()
    try:
        reader._stop()
        deadline = time.monotonic() + 2
        while not done and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(2)
    assert done == [(reader.sink, (1,))]


def test_on_finish_exception_is_logged(client, caplog):
    def boom(sink):
        raise RuntimeError("x")

    reader = make_reader(client, on_finish=boom, args=())
    reader._stop()
    assert "on_finish callback" in caplog.text


def test_log_after_exception(caplog):
    cancelled = MagicMock()
    cancelled.cancelled.return_value = True
    AudioReader._log_after_exception(cancelled)
    failed = MagicMock()
    failed.cancelled.return_value = False
    failed.exception.return_value = RuntimeError("late")
    AudioReader._log_after_exception(failed)
    assert "on_finish callback" in caplog.text
    ok = MagicMock()
    ok.cancelled.return_value = False
    ok.exception.return_value = None
    AudioReader._log_after_exception(ok)


# -- reader.callback ---------------------------------------------------------


def test_callback_ignores_crypto_errors(client, caplog):
    reader = make_reader(client)
    reader.packet_router.feed_rtp = MagicMock()
    reader.callback(make_rtp_bytes(1, key=bytes(32)))
    reader.packet_router.feed_rtp.assert_not_called()
    assert "CryptoError" in caplog.text


def test_callback_ignores_ip_discovery(client, caplog):
    reader = make_reader(client)
    data = bytes([0, 2]) + bytes(72)
    reader.callback(data)
    assert reader.error is None


def test_callback_logs_garbage_and_continues(client, caplog):
    reader = make_reader(client)
    reader.callback(bytes([0, 5, 0, 0]))
    assert "decoding voice packets" in caplog.text


def test_callback_routes_rtcp(client):
    reader = make_reader(client)
    reader.packet_router.feed_rtcp = MagicMock()
    rr = struct.pack(">BBHI", 0x80, 201, 1, 5)
    reader.callback(rr)
    reader.packet_router.feed_rtcp.assert_called_once()
    sr = struct.pack(">BBHI5I", 0x80, 200, 6, 5, 1, 2, 3, 4, 5)
    reader.packet_router.feed_rtcp.reset_mock()
    reader.callback(sr)
    reader.packet_router.feed_rtcp.assert_called_once()


def test_callback_reraises_base_exceptions(client):
    reader = make_reader(client)
    reader.decryptor.decrypt_rtp = MagicMock(side_effect=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        reader.callback(make_rtp_bytes(1))


def test_callback_stops_after_a_previous_error(client):
    reader = make_reader(client)
    reader.start()
    reader.error = RuntimeError("old")
    reader.callback(make_rtp_bytes(1))
    assert not reader.is_listening()


def test_callback_without_packet_returns(client):
    reader = make_reader(client)
    reader.packet_router.feed_rtp = MagicMock()
    reader.callback(bytes([0, 5, 0, 0]))
    reader.packet_router.feed_rtp.assert_not_called()


def test_callback_unknown_ssrc_silence_dropped_and_others_fed(client):
    reader = make_reader(client)
    reader.packet_router.feed_rtp = MagicMock()
    reader.speaking_timer.notify = MagicMock()
    reader.callback(make_rtp_bytes(1, payload=b"\xf8\xff\xfe"))
    reader.packet_router.feed_rtp.assert_not_called()
    reader.callback(make_rtp_bytes(2, payload=b"frame"))
    reader.packet_router.feed_rtp.assert_called_once()
    reader.speaking_timer.notify.assert_called_once_with(1)


def test_callback_empty_decrypted_payload_is_dropped(client):
    reader = make_reader(client)
    reader.packet_router.feed_rtp = MagicMock()
    reader.callback(make_rtp_bytes(1, payload=b""))
    reader.packet_router.feed_rtp.assert_not_called()


def test_callback_router_failure_stops_the_reader(client):
    reader = make_reader(client)
    reader.start()
    client._connection.ssrc_user_map[1] = 4
    reader.packet_router.feed_rtp = MagicMock(side_effect=RuntimeError("route"))
    reader.callback(make_rtp_bytes(1, payload=b"frame"))
    assert isinstance(reader.error, RuntimeError)
    assert not reader.is_listening()


# -- decryptor -----------------------------------------------------------------


def rtp_header(first=0x80, seq=1, ts=960, ssrc=1):
    return struct.pack(">BBHII", first, 120, seq, ts, ssrc)


def make_decryptor(client, mode):
    client.mode = mode
    return PacketDecryptor(mode, SECRET_KEY, client)


def test_unsupported_mode(client):
    with pytest.raises(NotImplementedError):
        PacketDecryptor("nope", SECRET_KEY, client)


def test_decrypt_rtp_suffix(client):
    d = make_decryptor(client, "xsalsa20_poly1305_suffix")
    header = rtp_header()
    nonce = bytes(range(24))
    body = nacl.secret.SecretBox(SECRET_KEY).encrypt(b"audio", nonce).ciphertext
    packet = RTPPacket(header + body + nonce)
    assert d.decrypt_rtp(packet) == b"audio"


def test_decrypt_rtp_lite(client):
    d = make_decryptor(client, "xsalsa20_poly1305_lite")
    nonce4 = b"\x01\x02\x03\x04"
    body = nacl.secret.SecretBox(SECRET_KEY).encrypt(b"audio", nonce4 + bytes(20))
    packet = RTPPacket(rtp_header() + body.ciphertext + nonce4)
    assert d.decrypt_rtp(packet) == b"audio"


def test_decrypt_rtp_aead(client):
    d = make_decryptor(client, "aead_xchacha20_poly1305_rtpsize")
    header = rtp_header()
    nonce4 = b"\x09\x00\x00\x00"
    aead = nacl.secret.Aead(SECRET_KEY)
    body = aead.encrypt(b"audio", header, nonce4 + bytes(20)).ciphertext
    packet = RTPPacket(header + body + nonce4)
    assert d.decrypt_rtp(packet) == b"audio"


def test_decrypt_rtp_aead_failure_raises_crypto_error(client):
    from nacl.exceptions import CryptoError

    d = make_decryptor(client, "aead_xchacha20_poly1305_rtpsize")
    packet = RTPPacket(rtp_header() + bytes(40))
    with pytest.raises(CryptoError):
        d.decrypt_rtp(packet)


def test_decrypt_rtp_aead_with_extension(client):
    d = make_decryptor(client, "aead_xchacha20_poly1305_rtpsize")
    header = rtp_header(first=0x90)
    ext_header = b"\xbe\xde" + struct.pack(">H", 1)
    plaintext = b"\x10A\x00\x00" + b"audio"
    nonce4 = b"\x00\x00\x00\x07"
    aead = nacl.secret.Aead(SECRET_KEY)
    body = aead.encrypt(plaintext, header + ext_header, nonce4 + bytes(20)).ciphertext
    packet = RTPPacket(header + ext_header + body + nonce4)
    assert d.decrypt_rtp(packet) == b"audio"
    assert packet.extension_data == {1: b"A"}


def test_decrypt_rtp_xsalsa_with_extension(client):
    d = make_decryptor(client, "xsalsa20_poly1305")
    header = rtp_header(first=0x90)
    plaintext = b"\x10\x00" + struct.pack(">H", 1) + b"WXYZ" + b"audio"
    box = nacl.secret.SecretBox(SECRET_KEY)
    body = box.encrypt(plaintext, header + bytes(12)).ciphertext
    packet = RTPPacket(header + body)
    assert d.decrypt_rtp(packet) == b"audio"


def rtcp_plain():
    return struct.pack(">BBHI", 0x80, 201, 1, 5)


@pytest.mark.parametrize(
    "mode",
    [
        "xsalsa20_poly1305",
        "xsalsa20_poly1305_suffix",
        "xsalsa20_poly1305_lite",
        "aead_xchacha20_poly1305_rtpsize",
    ],
)
def test_decrypt_rtcp_all_modes(client, mode):
    d = make_decryptor(client, mode)
    header = rtcp_plain()
    secret = b"reports!"
    if mode == "xsalsa20_poly1305":
        nonce = header + bytes(16)
        data = (
            header + nacl.secret.SecretBox(SECRET_KEY).encrypt(secret, nonce).ciphertext
        )
    elif mode == "xsalsa20_poly1305_suffix":
        nonce = bytes(range(24))
        data = (
            header
            + nacl.secret.SecretBox(SECRET_KEY).encrypt(secret, nonce).ciphertext
            + nonce
        )
    elif mode == "xsalsa20_poly1305_lite":
        nonce4 = b"\x01\x00\x00\x00"
        data = (
            header
            + nacl.secret.SecretBox(SECRET_KEY)
            .encrypt(secret, nonce4 + bytes(20))
            .ciphertext
            + nonce4
        )
    else:
        nonce4 = b"\x02\x00\x00\x00"
        data = (
            header
            + nacl.secret.Aead(SECRET_KEY)
            .encrypt(secret, header, nonce4 + bytes(20))
            .ciphertext
            + nonce4
        )
    assert d._decryptor_rtcp(data) == header + secret


class DaveStub:
    ready = True

    def __init__(self, error=None):
        self.error = error

    def decrypt(self, uid, media, data):
        if self.error:
            raise self.error
        return b"dave"


def test_decrypt_rtcp_short_data_and_dave(client):
    d = make_decryptor(client, "xsalsa20_poly1305")
    d._decryptor_rtcp = lambda data: data
    assert d.decrypt_rtcp(b"1234") == b"1234"
    plain = rtcp_plain() + b"x"
    assert d.decrypt_rtcp(plain) == plain
    client._connection.ssrc_user_map[5] = 77
    client._connection.dave_session = DaveStub()
    assert d.decrypt_rtcp(plain) == b"dave"
    client._connection.dave_session = DaveStub(ValueError("x"))
    assert d.decrypt_rtcp(plain) == plain


# -- SpeakingTimer ---------------------------------------------------------------


def make_timer(members=None):
    dispatched = []
    members = members if members is not None else {7: "member"}
    client = SimpleNamespace(
        _connection=SimpleNamespace(ssrc_user_map={1: 7, 2: 8}),
        _peek_member=members.get,
        _dispatch_sink=lambda event, member: dispatched.append((event, member)),
    )
    reader = SimpleNamespace(client=client)
    return SpeakingTimer(reader), dispatched


def test_speaking_timer_start_dispatches_once_per_burst():
    timer, dispatched = make_timer()
    timer.notify(1)
    timer.notify(1)
    assert dispatched == [("member_speaking_start", "member")]
    assert timer.get_speaking(1) is True
    assert timer.get_speaking(9) is None
    timer.notify(2)
    assert len(dispatched) == 1
    timer.notify(9)


def test_speaking_timer_drop_ssrc_dispatches_stop():
    timer, dispatched = make_timer()
    timer.notify(1)
    dispatched.clear()
    timer.drop_ssrc(1)
    assert dispatched == [("member_speaking_stop", "member")]
    timer.drop_ssrc(1)
    assert len(dispatched) == 1
    assert timer.get_speaking(1) is None


def test_speaking_timer_thread_emits_stop_after_silence():
    timer, dispatched = make_timer()
    timer.speaking_timeout_delay = 0.02
    timer.start()
    timer.notify(1)
    deadline = time.monotonic() + 2
    while len(dispatched) < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    timer.stop()
    timer.join(2)
    assert [e for e, _ in dispatched] == [
        "member_speaking_start",
        "member_speaking_stop",
    ]
    assert timer.get_speaking(1) is False
    assert not timer.is_alive()


def test_speaking_timer_idle_wakes_on_notify():
    timer, _dispatched = make_timer()
    timer.start()
    time.sleep(0.02)
    timer.notify()
    timer.stop()
    timer.join(2)
    assert not timer.is_alive()


# -- UDPKeepAlive ------------------------------------------------------------------


class KAClient:
    def __init__(self, sendto_effects, connected=True):
        self.effects = list(sendto_effects)
        self.sent = []
        self.connected = connected
        self.waited = 0
        self.keep = None
        sock = SimpleNamespace(sendto=self._sendto)
        self._connection = SimpleNamespace(
            socket=sock, endpoint_ip="1.2.3.4", voice_port=4000
        )

    def _sendto(self, packet, addr):
        self.sent.append((packet, addr))
        effect = self.effects.pop(0) if self.effects else None
        if isinstance(effect, Exception):
            raise effect
        if callable(effect):
            effect()

    def wait_until_connected(self):
        self.waited += 1

    def is_connected(self):
        return self.connected


def test_udp_keep_alive_sends_counter_until_stopped():
    client = KAClient([None, None])
    keep = UDPKeepAlive(client)
    keep.delay = 0
    client.effects[1] = keep.stop
    keep.run()
    assert [p for p, _ in client.sent] == [
        (0).to_bytes(8, "big"),
        (1).to_bytes(8, "big"),
    ]
    assert client.sent[0][1] == ("1.2.3.4", 4000)
    assert client.waited == 1


def test_udp_keep_alive_recovers_or_gives_up_after_errors():
    client = KAClient([OSError("x")], connected=False)
    keep = UDPKeepAlive(client)
    keep.run()
    assert client.waited == 2
    client2 = KAClient([OSError("x"), None], connected=True)
    keep2 = UDPKeepAlive(client2)
    keep2.delay = 0
    client2.effects[1] = keep2.stop
    keep2.run()
    assert len(client2.sent) == 2


def test_udp_keep_alive_counter_overflow_resets():
    client = KAClient([None])
    keep = UDPKeepAlive(client)
    keep.delay = 0
    keep.counter = 2**64
    client.effects[0] = keep.stop
    keep.run()
    assert client.sent[0][0] == (0).to_bytes(8, "big")


def test_decode_rtcp_roundtrip_type():
    assert decode(rtcp_plain()).type == 201
