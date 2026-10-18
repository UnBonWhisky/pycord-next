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

import ctypes
from types import SimpleNamespace

import pytest

from discord import opus
from tests.voice.deps import requires_voice


class FakeLib:
    def __init__(self):
        self.calls = []
        self.last_duration = 0

    def opus_get_version_string(self):
        return b"libopus fake 1.0"

    def opus_strerror(self, code):
        return f"error {code}".encode()

    def opus_encoder_create(self, fs, channels, application, err):
        self.calls.append(("enc_create", fs, channels, application))
        return "enc"

    def opus_encoder_ctl(self, state, request, *args):
        self.calls.append(("enc_ctl", request, *args))
        return 0

    def opus_encode(self, state, pcm, frame_size, data, max_bytes):
        self.calls.append(("encode", frame_size, max_bytes))
        data[0:3] = b"abc"
        return 3

    def opus_encoder_destroy(self, state):
        self.calls.append(("enc_destroy",))

    def opus_decoder_create(self, fs, channels, err):
        return "dec"

    def opus_decoder_destroy(self, state):
        self.calls.append(("dec_destroy",))

    def opus_decoder_ctl(self, state, request, *args):
        self.calls.append(("dec_ctl", request, *args))
        if request == opus.CTL_LAST_PACKET_DURATION:
            args[0]._obj.value = self.last_duration
        return 0

    def opus_packet_get_nb_frames(self, data, length):
        return 2

    def opus_packet_get_nb_channels(self, data):
        return 2

    def opus_packet_get_samples_per_frame(self, data, fs):
        return 480

    def opus_decode(self, state, data, length, pcm, frame_size, fec):
        self.calls.append(("decode", length, frame_size, fec))
        for i in range(frame_size * 2):
            pcm[i] = i
        return frame_size


@pytest.fixture
def lib(monkeypatch):
    fake = FakeLib()
    monkeypatch.setattr(opus, "_lib", fake)
    return fake


def test_not_loaded(monkeypatch):
    monkeypatch.setattr(opus, "_lib", None)
    monkeypatch.setattr(opus, "_load_default", lambda: False)
    assert opus.is_loaded() is False
    with pytest.raises(opus.OpusNotLoaded):
        opus._get_lib()
    with pytest.raises(opus.OpusNotLoaded):
        opus.Encoder()
    with pytest.raises(opus.OpusNotLoaded):
        opus.Decoder()


def test_opus_error_uses_strerror(lib):
    err = opus.OpusError(-4)
    assert err.code == -4
    assert str(err) == "error -4"
    assert str(opus.OpusError(message="custom")) == "custom"


def test_error_checkers(lib):
    def fn():
        pass

    assert opus._err_lt(5, fn, []) == 5
    with pytest.raises(opus.OpusError):
        opus._err_lt(-1, SimpleNamespace(__name__="f"), [])
    ok = SimpleNamespace(_obj=SimpleNamespace(value=0))
    assert opus._err_ne("ptr", SimpleNamespace(__name__="f"), [ok]) == "ptr"
    bad = SimpleNamespace(_obj=SimpleNamespace(value=-7))
    with pytest.raises(opus.OpusError) as info:
        opus._err_ne("ptr", SimpleNamespace(__name__="f"), [bad])
    assert info.value.code == -7


def test_libopus_loader_registers_functions(monkeypatch):
    class Func:
        pass

    class Lib:
        def __getattr__(self, name):
            f = Func()
            object.__setattr__(self, name, f)
            return f

    fake = Lib()
    monkeypatch.setattr(ctypes.cdll, "LoadLibrary", lambda name: fake)
    assert opus.libopus_loader("x") is fake
    assert fake.opus_encode.restype is ctypes.c_int32
    assert fake.opus_encode.errcheck is opus._err_lt
    assert fake.opus_get_version_string.restype is ctypes.c_char_p
    assert not hasattr(fake.opus_get_version_string, "argtypes")


def test_load_opus_sets_global(monkeypatch):
    monkeypatch.setattr(opus, "_lib", None)
    sentinel = object()
    monkeypatch.setattr(opus, "libopus_loader", lambda name: sentinel)
    opus.load_opus("libopus.so.1")
    assert opus.is_loaded()
    assert opus._lib is sentinel


def test_load_default_posix(monkeypatch):
    monkeypatch.setattr(opus, "_lib", None)
    monkeypatch.setattr(opus.sys, "platform", "linux")
    monkeypatch.setattr(opus.ctypes.util, "find_library", lambda n: None)
    assert opus._load_default() is False
    monkeypatch.setattr(opus.ctypes.util, "find_library", lambda n: "libopus.so")
    sentinel = object()
    monkeypatch.setattr(opus, "libopus_loader", lambda name: sentinel)
    assert opus._load_default() is True
    assert opus._lib is sentinel


def test_load_default_windows_and_failure(monkeypatch):
    monkeypatch.setattr(opus, "_lib", None)
    monkeypatch.setattr(opus.sys, "platform", "win32")
    seen = []
    monkeypatch.setattr(opus, "libopus_loader", lambda name: seen.append(name) or 1)
    assert opus._load_default() is True
    assert seen[0].endswith(("libopus-0.x64.dll", "libopus-0.x86.dll"))

    def boom(name):
        raise OSError

    monkeypatch.setattr(opus, "libopus_loader", boom)
    assert opus._load_default() is False
    assert opus._lib is None


def test_get_opus_version_loads_default(monkeypatch):
    monkeypatch.setattr(opus, "_lib", None)

    def load():
        monkeypatch.setattr(opus, "_lib", FakeLib())
        return True

    monkeypatch.setattr(opus, "_load_default", load)
    assert opus._OpusStruct.get_opus_version() == "libopus fake 1.0"


def test_encoder_validation(lib):
    with pytest.raises(ValueError, match="application"):
        opus.Encoder(application="nope")
    with pytest.raises(ValueError, match="bitrate"):
        opus.Encoder(bitrate=8)
    with pytest.raises(ValueError, match="expected_packet_loss"):
        opus.Encoder(expected_packet_loss=0)


def test_encoder_configures_state(lib):
    enc = opus.Encoder(
        application="voip",
        bitrate=64,
        fec=False,
        expected_packet_loss=0.5,
        bandwidth="wide",
        signal_type="music",
    )
    assert ("enc_create", 48000, 2, 2048) in lib.calls
    ctls = [c[1:] for c in lib.calls if c[0] == "enc_ctl"]
    assert ctls == [
        (opus.CTL_SET_BITRATE, 64 * 1024),
        (opus.CTL_SET_FEC, 0),
        (opus.CTL_SET_PLP, 50),
        (opus.CTL_SET_BANDWIDTH, 1103),
        (opus.CTL_SET_SIGNAL, 3002),
    ]
    assert enc.set_bitrate(10000) == 512
    assert enc.set_bitrate(1) == 16
    with pytest.raises(KeyError):
        enc.set_bandwidth("bad")
    with pytest.raises(KeyError):
        enc.set_signal_type("bad")
    del enc
    assert ("enc_destroy",) in lib.calls


def test_encoder_encode(lib):
    enc = opus.Encoder()
    pcm = b"\x00" * opus.Encoder.FRAME_SIZE
    assert enc.encode(pcm) == b"abc"
    assert ("encode", opus.Encoder.FRAME_SIZE, len(pcm)) in lib.calls
    assert enc.encode(pcm, 480) == b"abc"
    assert ("encode", 480, len(pcm)) in lib.calls


def test_decoder_packet_helpers_and_gain(lib):
    dec = opus.Decoder()
    assert dec.packet_get_nb_frames(b"x") == 2
    assert dec.packet_get_nb_channels(b"x") == 2
    assert dec.packet_get_samples_per_frame(b"x") == 480
    dec.set_gain(1)
    dec.set_gain(1000)
    dec.set_volume(1.0)
    gains = [c[2] for c in lib.calls if c[:2] == ("dec_ctl", opus.CTL_SET_GAIN)]
    assert gains == [256, 32767, 0]
    del dec
    assert ("dec_destroy",) in lib.calls


def test_decoder_decode(lib):
    dec = opus.Decoder()
    out = dec.decode(b"packet", fec=False)
    assert ("decode", 6, 960, 0) in lib.calls
    assert len(out) == 960 * 2 * 2
    assert out[:4] == b"\x00\x00\x01\x00"


def test_decoder_decode_loss(lib):
    dec = opus.Decoder()
    with pytest.raises(opus.OpusError, match="FEC cannot be used"):
        dec.decode(None)
    assert len(dec.decode(None, fec=False)) == 960 * 4
    lib.last_duration = 240
    assert len(dec.decode(None, fec=False)) == 240 * 4


class FakeBuffer:
    def __init__(self):
        self.packets = []
        self.ready = False
        self.resets = 0

    def push(self, packet):
        self.packets.append(packet)

    def is_ready(self):
        return self.ready

    def pop(self, *, timeout=0):
        return self.packets.pop(0) if self.packets else None

    def reset(self):
        self.resets += 1


def make_packet_decoder(monkeypatch, lib, *, is_opus=False, members=None):
    registered = []
    waiter = SimpleNamespace(
        register=lambda d: registered.append(("r", d)),
        unregister=lambda d: registered.append(("u", d)),
    )
    members = members or {}
    client = SimpleNamespace(
        _ssrc_to_id={5: 42},
        _peek_member=members.get,
        _connection=SimpleNamespace(dave_session=None),
    )
    sink = SimpleNamespace(is_opus=lambda: is_opus, client=client)
    router = SimpleNamespace(sink=sink, waiter=waiter)
    dec = opus.PacketDecoder(router, 5)
    dec._buffer = FakeBuffer()
    return dec, registered, client


def make_packet(seq=1, ts=960, data=b"opus"):
    return SimpleNamespace(sequence=seq, timestamp=ts, decrypted_data=data, ssrc=5)


@requires_voice
def test_packet_decoder_pop_decodes_with_object_member(monkeypatch, lib):
    from discord.object import Object

    dec, registered, _ = make_packet_decoder(monkeypatch, lib)
    dec.push_packet(make_packet())
    assert registered[-1][0] == "u"
    dec._buffer.ready = True
    data = dec.pop_data()
    assert registered[-1][0] == "r"
    assert isinstance(data.source, Object)
    assert data.source.id == 42
    assert len(data.pcm) == 960 * 4
    assert (dec._last_seq, dec._last_ts) == (1, 960)
    assert dec.pop_data() is None


@requires_voice
def test_packet_decoder_uses_cached_member_and_opus_sink(monkeypatch, lib):
    member = SimpleNamespace(id=77)
    dec, _, _ = make_packet_decoder(
        monkeypatch, lib, is_opus=True, members={77: member}
    )
    assert dec._decoder is None
    dec.set_user_id(77)
    data = dec.process_packet(make_packet())
    assert data.source is member


@requires_voice
def test_packet_decoder_cached_id_refreshed_from_member(monkeypatch, lib):
    member = SimpleNamespace(id=9)
    dec, _, _ = make_packet_decoder(monkeypatch, lib, members={3: member})
    dec._cached_id = 3
    dec._get_user = lambda uid: member
    dec.process_packet(make_packet())
    assert dec._cached_id == 9


@requires_voice
def test_packet_decoder_plc_and_failure(monkeypatch, lib):
    dec, _, _ = make_packet_decoder(monkeypatch, lib)
    calls = []

    class Failing:
        def decode(self, data, *, fec):
            calls.append(data)
            raise opus.OpusError(message="bad")

    dec._decoder = Failing()
    data = dec.process_packet(make_packet())
    assert data.pcm == b""
    assert calls == [b"opus", None]

    class PlcOnly:
        def decode(self, data, *, fec):
            if data is not None:
                raise opus.OpusError(message="bad")
            return b"plc"

    dec._decoder = PlcOnly()
    assert dec.process_packet(make_packet()).pcm == b"plc"


@requires_voice
def test_packet_decoder_reset_and_destroy(monkeypatch, lib):
    dec, _registered, _ = make_packet_decoder(monkeypatch, lib)
    dec._last_seq = 4
    dec.reset()
    assert dec._buffer.resets == 1
    assert dec._last_seq == dec._last_ts == -1
    assert isinstance(dec._decoder, opus.Decoder)
    dec.destroy()
    assert dec._decoder is None
    assert dec._buffer.resets == 2
    assert dec._get_cached_member() is None
