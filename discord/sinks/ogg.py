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

import io
import subprocess
from typing import Any

from .core import CREATE_NO_WINDOW, AudioData, Filters, Sink, default_filters
from .errors import OGGSinkError


class OGGSink(Sink):
    """A special sink for .ogg files.

    .. versionadded:: 2.0

    Parameters
    ----------
    filters: dict[:class:`str`, Any] | None
        The filters of the sink, see :class:`~discord.sinks.Filters`.
    """

    def __init__(self, *, filters: dict[str, Any] | None = None) -> None:
        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)

        self.encoding: str = "ogg"
        self.vc = None
        self.audio_data = {}

    def format_audio(self, audio: AudioData) -> None:
        """Formats the recorded audio.

        Raises
        ------
        OGGSinkError
            Audio may only be formatted after recording is finished.
        OGGSinkError
            Formatting the audio failed.
        """
        if self.recording:
            raise OGGSinkError(
                "Audio may only be formatted after recording is finished."
            )
        args = [
            "ffmpeg",
            "-f",
            "s16le",
            "-ar",
            "48000",
            "-loglevel",
            "error",
            "-ac",
            "2",
            "-i",
            "-",
            "-f",
            "ogg",
            "pipe:1",
        ]
        try:
            process = subprocess.Popen(
                args,
                creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise OGGSinkError("ffmpeg was not found.") from None
        except subprocess.SubprocessError as exc:
            raise OGGSinkError(
                f"Popen failed: {exc.__class__.__name__}: {exc}"
            ) from exc

        out = process.communicate(audio.file.read())[0]
        out = io.BytesIO(out)
        out.seek(0)
        audio.file = out
        audio.on_format(self.encoding)
