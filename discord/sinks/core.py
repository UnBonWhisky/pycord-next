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
import io
import os
import struct
import sys
import threading
import time
from typing import IO, TYPE_CHECKING, Any, ClassVar, TypeVar, cast

from .errors import SinkException

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ..member import Member
    from ..object import Object
    from ..types import snowflake
    from ..user import User
    from ..voice import VoiceClient
    from ..voice.packets import VoiceData

    F = TypeVar("F", bound=Callable[..., Any])

__all__ = (
    "AudioData",
    "Filters",
    "RawData",
    "Sink",
)


if sys.platform != "win32":
    CREATE_NO_WINDOW = 0
else:
    CREATE_NO_WINDOW = 0x08000000


default_filters: dict[str, Any] = {
    "time": 0,
    "users": [],
    "max_size": 0,
}


class Filters:
    """Filters for :class:`~.Sink`

    .. versionadded:: 2.0

    Parameters
    ----------
    users
        The users to record, every user is recorded if empty.
    time
        The number of seconds after which the recording stops, ``0``
        for no limit.
    max_size
        The maximum size of the recording, ``0`` for no limit.
    """

    vc: VoiceClient | None

    def __init__(self, **kwargs: Any) -> None:
        self.filtered_users: list[Any] = kwargs.get("users", default_filters["users"])
        self.seconds: float = kwargs.get("time", default_filters["time"])
        self.max_size: int = kwargs.get("max_size", default_filters["max_size"])
        self.finished: bool = False

    @staticmethod
    def container(func: F) -> F:
        """Wrap a ``write`` method so that it only receives filtered data.

        Parameters
        ----------
        func
            The ``write`` method to wrap.

        Returns
        -------
        The wrapped method, which ignores data from users that are not
        part of the filter.
        """

        def _filter(self: Filters, data: Any, user: Any) -> Any:
            if not self.filtered_users or user in self.filtered_users:
                return func(self, data, user)
            return None

        return cast("F", _filter)

    def init(self, *args: Any, **kwargs: Any) -> None:
        """Start the time limit of the filter, if any."""
        if self.seconds != 0:
            thread = threading.Thread(target=self.wait_and_stop)
            thread.start()

    def wait_and_stop(self) -> None:
        """Wait for the time limit to elapse then stop the recording."""
        time.sleep(self.seconds)
        if self.finished:
            return
        if self.vc is not None:
            self.vc.stop_recording()


class RawData:
    """Handles raw data from Discord so that it can be decrypted and decoded to be used.

    .. versionadded:: 2.0
    """

    def __init__(self, data: bytes, client: VoiceClient) -> None:
        self.data = bytearray(data)
        self.client = client

        unpacker = struct.Struct(">xxHII")
        self.sequence, self.timestamp, self.ssrc = unpacker.unpack_from(self.data[:12])

        # RFC3550 5.1: RTP Fixed Header Fields
        if self.client.mode.endswith("_rtpsize"):
            # If It Has CSRC Chunks
            cutoff = 12 + (data[0] & 0b00_0_0_1111) * 4
            # If It Has A Extension
            if data[0] & 0b00_0_1_0000:
                cutoff += 4
        else:
            cutoff = 12

        self.header = data[:cutoff]
        self.data = self.data[cutoff:]

        self.decrypted_data = getattr(self.client, f"_decrypt_{self.client.mode}")(
            self.header, self.data
        )
        self.decoded_data: bytes | None = None

        self.user_id: int | None = None
        self.receive_time = time.perf_counter()


class AudioData:
    """Handles data that's been completely decrypted and decoded and is ready to be saved to file.

    .. versionadded:: 2.0

    Parameters
    ----------
    file
        The binary file the audio is written to.
    """

    def __init__(self, file: IO[bytes]) -> None:
        self.file: IO[bytes] = file
        self.finished: bool = False

    def write(self, data: bytes) -> None:
        """Writes audio data.

        Parameters
        ----------
        data: :class:`bytes`
            The audio data to write.

        Raises
        ------
        ClientException
            The AudioData is already finished writing.
        """
        if self.finished:
            raise SinkException("The AudioData is already finished writing.")
        with contextlib.suppress(ValueError):
            self.file.write(data)

    def cleanup(self) -> None:
        """Finishes and cleans up the audio data.

        Raises
        ------
        ClientException
            The AudioData is already finished writing.
        """
        if self.finished:
            raise SinkException("The AudioData is already finished writing.")
        self.file.seek(0)
        self.finished = True

    def on_format(self, encoding: str) -> None:
        """Called when audio data is formatted.

        Parameters
        ----------
        encoding: :class:`str`
            The encoding the audio data was formatted to.

        Raises
        ------
        ClientException
            The AudioData is still writing.
        """
        if not self.finished:
            raise SinkException("The AudioData is still writing.")


class Sink(Filters):
    """A sink "stores" recorded audio data.

    Can be subclassed for extra customizablilty.

    .. warning::
        It is recommended you use
        the officially provided sink classes,
        such as :class:`~discord.sinks.WaveSink`.

    just replace the following like so: ::

        vc.start_recording(
            MySubClassedSink(),
            finished_callback,
            ctx.channel,
        )

    .. versionadded:: 2.0

    Parameters
    ----------
    filters: dict[:class:`str`, Any] | None
        The filters of the sink, see :class:`Filters`.

    Raises
    ------
    ClientException
        An invalid encoding type was specified.
    ClientException
        Audio may only be formatted after recording is finished.
    """

    __sink_listeners__: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, *, filters: dict[str, Any] | None = None) -> None:
        if filters is None:
            filters = default_filters
        self.filters: dict[str, Any] = filters
        Filters.__init__(self, **self.filters)
        self.vc: VoiceClient | None = None
        self.audio_data: dict[User | Member | Object | None, AudioData] = {}

    @property
    def client(self) -> VoiceClient | None:
        """The voice client this sink is recording from, if any."""
        return self.vc

    @property
    def recording(self) -> bool:
        """Whether the voice client is currently recording."""
        return self.vc is not None and bool(self.vc.is_recording())

    def is_opus(self) -> bool:
        """Whether this sink accepts raw opus packets instead of decoded PCM."""
        return False

    def walk_children(self) -> Iterator[Sink]:
        """Yields child sinks. Base implementation yields nothing."""
        return
        yield  # make it a generator

    def init(self, vc: VoiceClient) -> None:  # called under listen
        """Attach the sink to a voice client when recording starts.

        Parameters
        ----------
        vc: :class:`VoiceClient`
            The voice client the sink records from.
        """
        self.vc = vc
        super().init()

    @Filters.container
    def write(
        self, data: VoiceData | bytes, user: User | Member | Object | None
    ) -> None:
        """Write the audio of a user to the sink.

        Parameters
        ----------
        data: :class:`VoiceData` | :class:`bytes`
            The audio data to write.
        user: :class:`User` | :class:`Member` | :class:`Object` | None
            The user the audio comes from.
        """
        pcm_data = data if isinstance(data, (bytes, bytearray)) else data.pcm

        if user not in self.audio_data:
            file = io.BytesIO()
            self.audio_data.update({user: AudioData(file)})

        self.audio_data[user].write(pcm_data)

    def format_audio(self, audio: AudioData) -> None:
        """Format the recorded audio, implemented by the sink subclasses.

        Parameters
        ----------
        audio: :class:`AudioData`
            The audio data to format.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """Finish the recording and format the audio of every user."""
        self.finished = True
        for file in self.audio_data.values():
            file.cleanup()
            self.format_audio(file)

    def get_all_audio(self) -> list[IO[bytes]]:
        """Gets all audio files."""
        return [x.file for x in self.audio_data.values()]

    def get_user_audio(self, user: snowflake.Snowflake) -> str:
        """Gets the audio file(s) of one specific user."""
        audio_data = cast("dict[Any, Any]", self.audio_data)
        return os.path.realpath(audio_data.pop(user))
