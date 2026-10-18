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

import array
import ctypes
import ctypes.util
import logging
import math
import struct
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict, TypeVar, cast

from .errors import DiscordException

if TYPE_CHECKING:
    from collections.abc import Callable

    import davey

    from discord.member import Member
    from discord.sinks.core import Sink
    from discord.user import User
    from discord.voice.client import VoiceClient
    from discord.voice.packets import VoiceData
    from discord.voice.packets.core import Packet
    from discord.voice.receive.router import PacketRouter

    T = TypeVar("T")
    APPLICATION_CTL = Literal["audio", "voip", "lowdelay"]
    BAND_CTL = Literal["narrow", "medium", "wide", "superwide", "full"]
    SIGNAL_CTL = Literal["auto", "voice", "music"]


class BandCtl(TypedDict):
    """The bandwidth settings of an opus encoder."""

    narrow: int
    medium: int
    wide: int
    superwide: int
    full: int


class SignalCtl(TypedDict):
    """The signal types of an opus encoder."""

    auto: int
    voice: int
    music: int


class ApplicationCtl(TypedDict):
    """The application types of an opus encoder."""

    audio: int
    voip: int
    lowdelay: int


__all__ = (
    "Decoder",
    "Encoder",
    "OpusError",
    "OpusNotLoaded",
)

_log = logging.getLogger(__name__)


def __getattr__(name: str) -> bool:
    if name == "HAS_DAVEY":
        from .voice.utils.dependencies import HAS_DAVEY

        return HAS_DAVEY
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


c_int_ptr = ctypes.POINTER(ctypes.c_int)
c_int16_ptr = ctypes.POINTER(ctypes.c_int16)
c_float_ptr = ctypes.POINTER(ctypes.c_float)
OPUS_SILENCE = b"\xf8\xff\xfe"


class EncoderStruct(ctypes.Structure):
    """Opaque libopus encoder state."""


class DecoderStruct(ctypes.Structure):
    """Opaque libopus decoder state."""


EncoderStructPtr = ctypes.POINTER(EncoderStruct)
DecoderStructPtr = ctypes.POINTER(DecoderStruct)

if TYPE_CHECKING:
    EncoderPtr = ctypes._Pointer[EncoderStruct]
    DecoderPtr = ctypes._Pointer[DecoderStruct]


class _OpusLib(Protocol):
    def opus_get_version_string(self) -> bytes: ...

    def opus_strerror(self, error: int, /) -> bytes: ...

    def opus_encoder_create(
        self, fs: int, channels: int, application: int, error: Any, /
    ) -> EncoderPtr: ...

    def opus_encode(
        self,
        state: EncoderPtr,
        pcm: Any,
        frame_size: int,
        data: Any,
        max_data_bytes: int,
        /,
    ) -> int: ...

    def opus_encoder_ctl(self, state: EncoderPtr, request: int, *args: Any) -> int: ...

    def opus_encoder_destroy(self, state: EncoderPtr, /) -> None: ...

    def opus_decoder_create(
        self, fs: int, channels: int, error: Any, /
    ) -> DecoderPtr: ...

    def opus_decode(
        self,
        state: DecoderPtr,
        data: bytes | None,
        length: int,
        pcm: Any,
        frame_size: int,
        decode_fec: int,
        /,
    ) -> int: ...

    def opus_decoder_ctl(self, state: DecoderPtr, request: int, *args: Any) -> int: ...

    def opus_decoder_destroy(self, state: DecoderPtr, /) -> None: ...

    def opus_packet_get_nb_channels(self, data: bytes, /) -> int: ...

    def opus_packet_get_nb_frames(self, data: bytes, length: int, /) -> int: ...

    def opus_packet_get_samples_per_frame(self, data: bytes, fs: int, /) -> int: ...


_lib: _OpusLib | None = None


def _get_lib() -> _OpusLib:
    if _lib is None:
        raise OpusNotLoaded
    return _lib


# Some constants from opus_defines.h

# Error codes
OK = 0
BAD_ARG = -1
BUFF_TOO_SMALL = -2
INTERNAL_ERROR = -3
INVALID_PACKET = -4
UNIMPLEMENTED = -5
INVALID_STATE = -6
ALLOC_FAIL = -7

# Encoder CTLs
application_ctl: ApplicationCtl = {
    "audio": 2049,
    "lowdelay": 2051,
    "voip": 2048,
}

CTL_SET_BITRATE = 4002
CTL_SET_BANDWIDTH = 4008
CTL_SET_FEC = 4012
CTL_SET_PLP = 4014
CTL_SET_SIGNAL = 4024

# Decoder CTLs
CTL_SET_GAIN = 4034
CTL_LAST_PACKET_DURATION = 4039

band_ctl: BandCtl = {
    "narrow": 1101,
    "medium": 1102,
    "wide": 1103,
    "superwide": 1104,
    "full": 1105,
}

signal_ctl: SignalCtl = {
    "auto": -1000,
    "voice": 3001,
    "music": 3002,
}


def _err_lt(result: int, func: Callable[..., Any], _args: list[Any]) -> int:
    if result < OK:
        _log.info("error has happened in %s", func.__name__)
        raise OpusError(result)
    return result


def _err_ne(result: T, func: Callable[..., Any], args: list[Any]) -> T:
    ret = args[-1]._obj
    if ret.value != OK:
        _log.info("error has happened in %s", func.__name__)
        raise OpusError(ret.value)
    return result


# A list of exported functions.
# The first argument is obviously the name.
# The second one are the types of arguments it takes.
# The third is the result type.
# The fourth is the error handler.
exported_functions: list[tuple[Any, ...]] = [
    # Generic
    ("opus_get_version_string", [], ctypes.c_char_p, None),
    ("opus_strerror", [ctypes.c_int], ctypes.c_char_p, None),
    # Encoder functions
    ("opus_encoder_get_size", [ctypes.c_int], ctypes.c_int, None),
    (
        "opus_encoder_create",
        [ctypes.c_int, ctypes.c_int, ctypes.c_int, c_int_ptr],
        EncoderStructPtr,
        _err_ne,
    ),
    (
        "opus_encode",
        [EncoderStructPtr, c_int16_ptr, ctypes.c_int, ctypes.c_char_p, ctypes.c_int32],
        ctypes.c_int32,
        _err_lt,
    ),
    (
        "opus_encode_float",
        [EncoderStructPtr, c_float_ptr, ctypes.c_int, ctypes.c_char_p, ctypes.c_int32],
        ctypes.c_int32,
        _err_lt,
    ),
    ("opus_encoder_ctl", [EncoderStructPtr, ctypes.c_int], ctypes.c_int32, _err_lt),
    ("opus_encoder_destroy", [EncoderStructPtr], None, None),
    # Decoder functions
    ("opus_decoder_get_size", [ctypes.c_int], ctypes.c_int, None),
    (
        "opus_decoder_create",
        [ctypes.c_int, ctypes.c_int, c_int_ptr],
        DecoderStructPtr,
        _err_ne,
    ),
    (
        "opus_decode",
        [
            DecoderStructPtr,
            ctypes.c_char_p,
            ctypes.c_int32,
            c_int16_ptr,
            ctypes.c_int,
            ctypes.c_int,
        ],
        ctypes.c_int,
        _err_lt,
    ),
    (
        "opus_decode_float",
        [
            DecoderStructPtr,
            ctypes.c_char_p,
            ctypes.c_int32,
            c_float_ptr,
            ctypes.c_int,
            ctypes.c_int,
        ],
        ctypes.c_int,
        _err_lt,
    ),
    ("opus_decoder_ctl", [DecoderStructPtr, ctypes.c_int], ctypes.c_int32, _err_lt),
    ("opus_decoder_destroy", [DecoderStructPtr], None, None),
    (
        "opus_decoder_get_nb_samples",
        [DecoderStructPtr, ctypes.c_char_p, ctypes.c_int32],
        ctypes.c_int,
        _err_lt,
    ),
    # Packet functions
    ("opus_packet_get_bandwidth", [ctypes.c_char_p], ctypes.c_int, _err_lt),
    ("opus_packet_get_nb_channels", [ctypes.c_char_p], ctypes.c_int, _err_lt),
    (
        "opus_packet_get_nb_frames",
        [ctypes.c_char_p, ctypes.c_int],
        ctypes.c_int,
        _err_lt,
    ),
    (
        "opus_packet_get_samples_per_frame",
        [ctypes.c_char_p, ctypes.c_int],
        ctypes.c_int,
        _err_lt,
    ),
]


def libopus_loader(name: str) -> _OpusLib:
    """Load libopus and register the exported functions.

    Parameters
    ----------
    name: :class:`str`
        The filename of the shared library.

    Returns
    -------
    The loaded library with its function signatures registered.
    """
    # create the library...
    lib = ctypes.cdll.LoadLibrary(name)

    # register the functions...
    for item in exported_functions:
        func = getattr(lib, item[0])

        try:
            if item[1]:
                func.argtypes = item[1]

            func.restype = item[2]
        except KeyError:
            pass

        try:
            if item[3]:
                func.errcheck = item[3]
        except KeyError:
            _log.exception("Error assigning check function to %s", func)

    return cast("_OpusLib", lib)


def _load_default() -> bool:
    global _lib
    try:
        if sys.platform == "win32":
            _basedir = Path(__file__).resolve().parent
            _bitness = struct.calcsize("P") * 8
            _target = "x64" if _bitness > 32 else "x86"
            _filename = _basedir / "bin" / f"libopus-0.{_target}.dll"
            _lib = libopus_loader(str(_filename))
        else:
            _found = ctypes.util.find_library("opus")
            _lib = libopus_loader(_found) if _found is not None else None
    except Exception:
        _lib = None

    return _lib is not None


def load_opus(name: str) -> None:
    """Loads the libopus shared library for use with voice.

    If this function is not called then the library uses the function
    :func:`ctypes.util.find_library` and then loads that one if available.

    Not loading a library and attempting to use PCM based AudioSources will
    lead to voice not working.

    This function propagates the exceptions thrown.

    .. warning::

        The bitness of the library must match the bitness of your python
        interpreter. If the library is 64-bit then your python interpreter
        must be 64-bit as well. Usually if there's a mismatch in bitness then
        the load will throw an exception.

    .. note::

        On Windows, this function should not need to be called as the binaries
        are automatically loaded.

    .. note::

        On Windows, the .dll extension is not necessary. However, on Linux
        the full extension is required to load the library, e.g. ``libopus.so.1``.
        On Linux however, :func:`ctypes.util.find_library` will usually find the library automatically
        without you having to call this.

    Parameters
    ----------
    name: :class:`str`
        The filename of the shared library.
    """
    global _lib
    _lib = libopus_loader(name)


def is_loaded() -> bool:
    """Check if the opus lib is successfully loaded.

    The library is loaded either via the :func:`ctypes.util.find_library`
    call or :func:`load_opus`.

    This must return ``True`` for voice to work.

    Returns
    -------
    :class:`bool`
        Indicates if the opus library has been loaded.
    """
    return _lib is not None


class OpusError(DiscordException):
    """An exception that is thrown for libopus related errors.

    Attributes
    ----------
    code: :class:`int`
        The error code returned.
    """

    def __init__(self, code: int = 0, message: str | None = None) -> None:
        self.code: int = code
        msg = message or _get_lib().opus_strerror(self.code).decode("utf-8")
        _log.info('"%s" has happened', msg)
        super().__init__(msg)


class OpusNotLoaded(DiscordException):
    """An exception that is thrown for when libopus is not loaded."""


class _OpusStruct:
    SAMPLING_RATE = 48000
    CHANNELS = 2
    FRAME_LENGTH = 20  # in milliseconds
    SAMPLE_SIZE = struct.calcsize("h") * CHANNELS
    SAMPLES_PER_FRAME = int(SAMPLING_RATE / 1000 * FRAME_LENGTH)

    FRAME_SIZE = SAMPLES_PER_FRAME * SAMPLE_SIZE

    @staticmethod
    def get_opus_version() -> str:
        if not is_loaded() and not _load_default():
            raise OpusNotLoaded

        return _get_lib().opus_get_version_string().decode("utf-8")


class Encoder(_OpusStruct):
    """An opus encoder.

    Parameters
    ----------
    application: Literal["audio", "voip", "lowdelay"]
        The application the encoder is optimised for.
    bitrate: :class:`int`
        The target bitrate in kbps, between 16 and 512.
    fec: :class:`bool`
        Whether forward error correction is enabled.
    expected_packet_loss: :class:`float`
        The expected packet loss, between 0 (excluded) and 1.
    bandwidth: Literal["narrow", "medium", "wide", "superwide", "full"]
        The bandwidth of the encoded audio.
    signal_type: Literal["auto", "voice", "music"]
        The type of signal being encoded.

    Raises
    ------
    ValueError
        One of the parameters is out of range.
    OpusNotLoaded
        The opus library could not be loaded.
    """

    def __init__(
        self,
        *,
        application: APPLICATION_CTL = "audio",
        bitrate: int = 128,
        fec: bool = True,
        expected_packet_loss: float = 0.15,
        bandwidth: BAND_CTL = "full",
        signal_type: SIGNAL_CTL = "auto",
    ) -> None:
        if application not in application_ctl:
            raise ValueError("invalid application ctl type provided")
        if not 16 <= bitrate <= 512:
            raise ValueError("bitrate must be between 16 and 512, both included")
        if not 0 < expected_packet_loss <= 1:
            raise ValueError(
                "expected_packet_loss must be between 0 and 1, including 1",
            )

        _OpusStruct.get_opus_version()

        self.application: int = application_ctl[application]
        self._state: EncoderPtr = self._create_state()

        self.set_bitrate(bitrate)
        self.set_fec(fec)
        self.set_expected_packet_loss_percent(expected_packet_loss)
        self.set_bandwidth(bandwidth)
        self.set_signal_type(signal_type)

    def __del__(self) -> None:
        if hasattr(self, "_state") and _lib is not None:
            _lib.opus_encoder_destroy(self._state)
            del self._state

    def _create_state(self) -> EncoderPtr:
        ret = ctypes.c_int()
        return _get_lib().opus_encoder_create(
            self.SAMPLING_RATE, self.CHANNELS, self.application, ctypes.byref(ret)
        )

    def set_bitrate(self, kbps: int) -> int:
        """Set the target bitrate.

        Parameters
        ----------
        kbps: :class:`int`
            The bitrate in kbps, clamped between 16 and 512.

        Returns
        -------
        :class:`int`
            The bitrate that was applied.
        """
        kbps = min(512, max(16, int(kbps)))

        _get_lib().opus_encoder_ctl(self._state, CTL_SET_BITRATE, kbps * 1024)
        return kbps

    def set_bandwidth(self, req: BAND_CTL) -> None:
        """Set the bandwidth of the encoded audio.

        Parameters
        ----------
        req: Literal["narrow", "medium", "wide", "superwide", "full"]
            The bandwidth to use.

        Raises
        ------
        KeyError
            The bandwidth is not valid.
        """
        if req not in band_ctl:
            raise KeyError(
                f"{req!r} is not a valid bandwidth setting. Try one of:"
                f" {','.join(band_ctl)}"
            )

        k = band_ctl[req]
        _get_lib().opus_encoder_ctl(self._state, CTL_SET_BANDWIDTH, k)

    def set_signal_type(self, req: SIGNAL_CTL) -> None:
        """Set the type of signal being encoded.

        Parameters
        ----------
        req: Literal["auto", "voice", "music"]
            The signal type to use.

        Raises
        ------
        KeyError
            The signal type is not valid.
        """
        if req not in signal_ctl:
            raise KeyError(
                f"{req!r} is not a valid bandwidth setting. Try one of:"
                f" {','.join(signal_ctl)}"
            )

        k = signal_ctl[req]
        _get_lib().opus_encoder_ctl(self._state, CTL_SET_SIGNAL, k)

    def set_fec(self, enabled: bool = True) -> None:
        """Enable or disable forward error correction.

        Parameters
        ----------
        enabled: :class:`bool`
            Whether forward error correction is enabled.
        """
        _get_lib().opus_encoder_ctl(self._state, CTL_SET_FEC, 1 if enabled else 0)

    def set_expected_packet_loss_percent(self, percentage: float) -> None:
        """Set the expected packet loss percentage.

        Parameters
        ----------
        percentage: :class:`float`
            The expected packet loss, from 0 to 1.
        """
        _get_lib().opus_encoder_ctl(
            self._state, CTL_SET_PLP, min(100, max(0, int(percentage * 100)))
        )

    def encode(self, pcm: bytes, frame_size: int | None = None) -> bytes:
        """Encode PCM audio into an opus packet.

        Parameters
        ----------
        pcm: :class:`bytes`
            The 16-bit stereo PCM data to encode.
        frame_size: :class:`int` | None
            The number of samples per channel in ``pcm``. Defaults to a 20ms frame.

        Returns
        -------
        :class:`bytes`
            The encoded opus packet.
        """
        max_data_bytes = len(pcm)
        # bytes can be used to reference pointer
        pcm_ptr = ctypes.cast(ctypes.c_char_p(pcm), c_int16_ptr)
        data = (ctypes.c_char * max_data_bytes)()

        if frame_size is None:
            frame_size = self.FRAME_SIZE

        ret = _get_lib().opus_encode(
            self._state, pcm_ptr, frame_size, data, max_data_bytes
        )

        return bytes(data[:ret])


class Decoder(_OpusStruct):
    """An opus decoder."""

    def __init__(self) -> None:
        _OpusStruct.get_opus_version()

        self._state: DecoderPtr = self._create_state()

    def __del__(self) -> None:
        if hasattr(self, "_state") and _lib is not None:
            _lib.opus_decoder_destroy(self._state)
            del self._state

    def _create_state(self) -> DecoderPtr:
        ret = ctypes.c_int()
        return _get_lib().opus_decoder_create(
            self.SAMPLING_RATE, self.CHANNELS, ctypes.byref(ret)
        )

    @staticmethod
    def packet_get_nb_frames(data: bytes) -> int:
        """Get the number of frames in an Opus packet."""
        return _get_lib().opus_packet_get_nb_frames(data, len(data))

    @staticmethod
    def packet_get_nb_channels(data: bytes) -> int:
        """Get the number of channels in an Opus packet."""
        return _get_lib().opus_packet_get_nb_channels(data)

    @classmethod
    def packet_get_samples_per_frame(cls, data: bytes) -> int:
        """Get the number of samples per frame from an Opus packet."""
        return _get_lib().opus_packet_get_samples_per_frame(data, cls.SAMPLING_RATE)

    def _set_gain(self, adjustment: int) -> int:
        """Configure decoder gain adjustment.

        Scales the decoded output by a factor specified in Q8 dB units.
        This has a maximum range of -32768 to 32767 inclusive, and returns
        OPUS_BAD_ARG (-1) otherwise. The default is zero indicating no adjustment.
        This setting survives decoder reset (irrelevant for now).
        gain = 10**x/(20.0*256)
        (from opus_defines.h)
        """
        return _get_lib().opus_decoder_ctl(self._state, CTL_SET_GAIN, adjustment)

    def set_gain(self, dB: float) -> int:
        """Set the decoder gain in dB, from -128 to 128."""
        gain_q8 = max(-32768, min(32767, round(dB * 256)))  # dB * 2^n where n is 8 (Q8)
        return self._set_gain(gain_q8)

    def set_volume(self, mult: float) -> int:
        """Set the output volume as a float percent, i.e. 0.5 for 50%, 1.75 for 175%, etc."""
        return self.set_gain(20 * math.log10(mult))  # amplitude ratio

    def _get_last_packet_duration(self) -> int:
        """Get the duration (in samples) of the last packet successfully decoded or concealed."""
        ret = ctypes.c_int32()
        _get_lib().opus_decoder_ctl(
            self._state, CTL_LAST_PACKET_DURATION, ctypes.byref(ret)
        )
        return ret.value

    def decode(self, data: bytes | None, *, fec: bool = True) -> bytes:
        """Decode an opus packet into PCM audio.

        Parameters
        ----------
        data: :class:`bytes` | None
            The opus packet to decode, or ``None`` to conceal a lost packet.
        fec: :class:`bool`
            Whether to use forward error correction to recover a lost packet.

        Returns
        -------
        :class:`bytes`
            The 16-bit stereo PCM data.

        Raises
        ------
        OpusError
            The packet could not be decoded, or ``fec`` is used with no ``data``.
        """
        if data is None and fec:
            raise OpusError(
                message="Invalid arguments: FEC cannot be used with null data"
            )

        channel_count = self.CHANNELS

        if data is None:
            frame_size = self._get_last_packet_duration() or self.SAMPLES_PER_FRAME
        else:
            frames = self.packet_get_nb_frames(data)
            samples_per_frame = self.packet_get_samples_per_frame(data)
            frame_size = frames * samples_per_frame

        pcm = (ctypes.c_int16 * (frame_size * channel_count))()
        pcm_ptr = ctypes.cast(pcm, c_int16_ptr)

        ret = _get_lib().opus_decode(
            self._state, data, len(data) if data else 0, pcm_ptr, frame_size, fec
        )

        return array.array("h", pcm[: ret * channel_count]).tobytes()


class PacketDecoder:
    def __init__(self, router: PacketRouter, ssrc: int) -> None:
        self.router: PacketRouter = router
        self.ssrc: int = ssrc

        self._decoder: Decoder | None = None if self.sink.is_opus() else Decoder()

        from discord.voice.utils.buffer import JitterBuffer

        self._buffer: JitterBuffer = JitterBuffer()
        self._cached_id: int | None = None

        self._last_seq: int = -1
        self._last_ts: int = -1

    @property
    def sink(self) -> Sink:
        return self.router.sink

    def _get_user(self, user_id: int) -> User | Member | None:
        vc = cast("VoiceClient", self.sink.client)
        return vc._peek_member(user_id)

    def _get_cached_member(self) -> User | Member | None:
        return self._get_user(self._cached_id) if self._cached_id else None

    def _flag_ready_state(self) -> None:
        if self._buffer.is_ready():
            self.router.waiter.register(self)
        else:
            self.router.waiter.unregister(self)

    def push_packet(self, packet: Packet) -> None:
        self._buffer.push(packet)
        self._flag_ready_state()

    def process_packet(self, packet: Packet) -> VoiceData:
        return self._process_packet(packet)

    def pop_data(self, *, timeout: float = 0) -> VoiceData | None:
        packet = self._get_next_packet(timeout)
        self._flag_ready_state()

        if packet is None:
            return None
        return self._process_packet(packet)

    def set_user_id(self, user_id: int) -> None:
        self._cached_id = user_id

    def reset(self) -> None:
        self._buffer.reset()
        self._decoder = None if self.sink.is_opus() else Decoder()
        self._last_seq = self._last_ts = -1
        self._flag_ready_state()

    def destroy(self) -> None:
        self._buffer.reset()
        self._decoder = None
        self._flag_ready_state()

    def _get_next_packet(self, timeout: float) -> Packet | None:
        return self._buffer.pop(timeout=timeout)

    def _process_packet(self, packet: Packet) -> VoiceData:
        _log.debug("Processing packet %s", packet)
        from discord.object import Object
        from discord.voice import VoiceData

        assert self.sink.client

        pcm = None

        member = self._get_cached_member()

        if member is None:
            self._cached_id = self.sink.client._ssrc_to_id.get(self.ssrc)
            member = self._get_cached_member()
        else:
            self._cached_id = member.id

        # yet still none, use Object
        if member is None and self._cached_id:
            member = Object(id=self._cached_id)

        if not self.sink.is_opus():
            _log.debug("Decoding packet %s (type %s)", packet, type(packet))
            packet, pcm = self._decode_packet(packet)

        data = VoiceData(packet, member, pcm=pcm)
        self._last_seq = packet.sequence
        self._last_ts = packet.timestamp
        return data

    def _decode_packet(self, packet: Packet) -> tuple[Packet, bytes]:
        assert self._decoder is not None
        assert self.sink.client

        user_id: int | None = self._cached_id
        dave: davey.DaveSession | None = self.sink.client._connection.dave_session
        in_dave = dave is not None

        _log.debug(
            "Decrypting packet for user %s (DAVE enabled: %s). Has decrypted data?: %s",
            user_id,
            in_dave,
            packet.decrypted_data is not None,
        )

        try:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
        except OpusError:
            _log.warning(
                "Opus decode failed for packet seq=%s, using PLC",
                packet.sequence,
                exc_info=True,
            )
            try:
                pcm = self._decoder.decode(None, fec=False)
            except OpusError:
                _log.debug("Opus PLC failed too, emitting no audio", exc_info=True)
                pcm = b""

        return packet, pcm
