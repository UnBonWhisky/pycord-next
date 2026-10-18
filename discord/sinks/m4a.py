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
import time
from pathlib import Path
from typing import Any

from .core import CREATE_NO_WINDOW, AudioData, Filters, Sink, default_filters
from .errors import M4ASinkError


class M4ASink(Sink):
    """A special sink for .m4a files.

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

        self.encoding: str = "m4a"
        self.vc = None
        self.audio_data = {}

    def format_audio(self, audio: AudioData) -> None:
        """Formats the recorded audio.

        Raises
        ------
        M4ASinkError
            Audio may only be formatted after recording is finished.
        M4ASinkError
            Formatting the audio failed.
        """
        if self.recording:
            raise M4ASinkError(
                "Audio may only be formatted after recording is finished."
            )
        m4a_file = Path(f"{time.time()}.tmp")
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
            "ipod",
            str(m4a_file),
        ]
        if m4a_file.exists():
            m4a_file.unlink()  # process will get stuck asking whether to overwrite, if file already exists.
        try:
            process = subprocess.Popen(
                args, creationflags=CREATE_NO_WINDOW, stdin=subprocess.PIPE
            )
        except FileNotFoundError:
            raise M4ASinkError("ffmpeg was not found.") from None
        except subprocess.SubprocessError as exc:
            raise M4ASinkError(
                f"Popen failed: {exc.__class__.__name__}: {exc}"
            ) from exc

        process.communicate(audio.file.read())

        with m4a_file.open("rb") as f:
            audio.file = io.BytesIO(f.read())
            audio.file.seek(0)
        m4a_file.unlink()

        audio.on_format(self.encoding)
