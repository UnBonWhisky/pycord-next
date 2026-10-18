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

import datetime as dt
import re
import warnings
from importlib.metadata import PackageNotFoundError, version

from typing_extensions import TypedDict, deprecated

__all__ = ("VersionInfo", "__version__", "version_info")

from typing import Literal, NamedTuple

try:
    __version__: str = version("py-cord")
except PackageNotFoundError:
    # Package is not installed
    try:
        from setuptools_scm import get_version  # type: ignore[import-not-found]

        __version__ = str(get_version())  # pyright: ignore[reportUnknownArgumentType]
    except ImportError:
        # setuptools_scm is not installed
        __version__ = "0.0.0"
        warnings.warn(
            (
                "Package is not installed, and setuptools_scm is not installed. "
                f"As a fallback, {__name__}.__version__ will be set to {__version__}"
            ),
            RuntimeWarning,
            stacklevel=2,
        )


class AdvancedVersionInfo(TypedDict):
    """The advanced version information of the library."""

    serial: int
    build: int | None
    commit: str | None
    date: dt.date | None


class VersionInfo(NamedTuple):
    """A named tuple representing the library version.

    Attributes
    ----------
    major: :class:`int`
        The major version.
    minor: :class:`int`
        The minor version.
    micro: :class:`int`
        The micro version.
    releaselevel: :class:`str`
        The release level, one of ``alpha``, ``beta``, ``candidate`` or ``final``.
    """

    major: int
    minor: int
    micro: int
    releaselevel: Literal["alpha", "beta", "candidate", "final"]

    # We can't set instance attributes on a NamedTuple, so we have to use a
    # global variable to store the advanced version info.
    @property
    def advanced(self) -> AdvancedVersionInfo:
        """The advanced version information."""
        return _advanced_holder[0]

    @advanced.setter
    def advanced(self, value: AdvancedVersionInfo) -> None:
        _advanced_holder[0] = value

    @property
    @deprecated(
        "VersionInfo.release_level is deprecated since version 2.4, consider using releaselevel instead."
    )
    def release_level(self) -> Literal["alpha", "beta", "candidate", "final"]:
        return self.releaselevel

    @property
    @deprecated(
        'VersionInfo.serial is deprecated since version 2.4, consider using .advanced["serial"] instead.'
    )
    def serial(self) -> int:
        return self.advanced["serial"]

    @property
    @deprecated(
        'VersionInfo.build is deprecated since version 2.4, consider using .advanced["build"] instead.'
    )
    def build(self) -> int | None:
        return self.advanced["build"]

    @property
    @deprecated(
        'VersionInfo.commit is deprecated since version 2.4, consider using .advanced["commit"] instead.'
    )
    def commit(self) -> str | None:
        return self.advanced["commit"]

    @property
    @deprecated(
        'VersionInfo.date is deprecated since version 2.4, consider using .advanced["date"] instead.'
    )
    def date(self) -> dt.date | None:
        return self.advanced["date"]


version_regex = re.compile(
    r"^(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?"
    r"(?:(?P<level>rc|a|b)(?P<serial>\d+))?"
    r"(?:\.dev(?P<build>\d+))?"
    r"(?:\+(?:(?:g(?P<commit>[a-fA-F0-9]{4,40})(?:\.d(?P<date>\d{4}\d{2}\d{2})|))|d(?P<date1>\d{4}\d{2}\d{2})))?$"
)
version_match = version_regex.match(__version__)
if version_match is None:
    raise RuntimeError(f"Invalid version string: {__version__}")
raw_info = version_match.groupdict()

level_info: Literal["alpha", "beta", "candidate", "final"]

if raw_info["level"] == "a":
    level_info = "alpha"
elif raw_info["level"] == "b":
    level_info = "beta"
elif raw_info["level"] == "rc":
    level_info = "candidate"
elif raw_info["level"] is None:
    level_info = "final"
else:
    raise RuntimeError("Invalid release level")

date_info: dt.date | None
if (raw_date := raw_info["date"] or raw_info["date1"]) is not None:
    date_info = dt.date(
        int(raw_date[:4]),
        int(raw_date[4:6]),
        int(raw_date[6:]),
    )
else:
    date_info = None

version_info: VersionInfo = VersionInfo(
    major=int(raw_info["major"] or 0),
    minor=int(raw_info["minor"] or 0),
    micro=int(raw_info["patch"] or 0),
    releaselevel=level_info,
)

_advanced_holder: list[AdvancedVersionInfo] = [
    AdvancedVersionInfo(
        serial=int(raw_info["serial"] or 0),
        build=int(raw_info["build"] or 0) or None,
        commit=raw_info["commit"],
        date=date_info,
    )
]
