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

"""Shared client themes of messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._internal.aliases import AliasMixin
from .colour import Colour
from .enums import SharedClientThemeBaseType, try_enum

__all__ = ("SharedClientTheme", "SharedClientThemeBaseType")

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Self

    from .types.message import SharedClientTheme as SharedClientThemePayload


class SharedClientTheme(AliasMixin):
    """Represents a custom client-side theme shared via a message.

    .. container:: operations

        .. describe:: x == y

            Checks if two themes are equal.

        .. describe:: x != y

            Checks if two themes are not equal.

        .. describe:: hash(x)

            Returns the theme's hash.

    .. versionadded:: 3.0

    Attributes
    ----------
    colours: List[:class:`Colour`]
        The colours of the theme, up to 5.
    gradient_angle: :class:`int`
        The direction of the theme's colours in degrees, from ``0`` to ``360``.
    base_mix: :class:`int`
        The intensity of the theme's colours, from ``0`` to ``100``.
    base_theme: Optional[:class:`SharedClientThemeBaseType`]
        The mode of the theme. :attr:`SharedClientThemeBaseType.unset` is
        equivalent to :attr:`SharedClientThemeBaseType.dark`.
    """

    __slots__ = ("base_mix", "base_theme", "colours", "gradient_angle")

    def __init__(
        self,
        *,
        colours: Sequence[Colour | int],
        gradient_angle: int = 0,
        base_mix: int = 0,
        base_theme: SharedClientThemeBaseType | None = SharedClientThemeBaseType.unset,
    ) -> None:
        if len(colours) > 5:
            raise ValueError("colours must contain at most 5 colours")
        if not 0 <= gradient_angle <= 360:
            raise ValueError("gradient_angle must be between 0 and 360")
        if not 0 <= base_mix <= 100:
            raise ValueError("base_mix must be between 0 and 100")
        if base_theme is not None and not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            base_theme, SharedClientThemeBaseType
        ):
            raise TypeError("base_theme must be a SharedClientThemeBaseType or None")

        self.colours: list[Colour] = [
            c if isinstance(c, Colour) else Colour(c) for c in colours
        ]
        self.gradient_angle: int = gradient_angle
        self.base_mix: int = base_mix
        self.base_theme: SharedClientThemeBaseType | None = base_theme

    def __repr__(self) -> str:
        return (
            f"<SharedClientTheme colours={self.colours!r}"
            f" gradient_angle={self.gradient_angle} base_mix={self.base_mix}"
            f" base_theme={self.base_theme!r}>"
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, SharedClientTheme)
            and self.colours == other.colours
            and self.gradient_angle == other.gradient_angle
            and self.base_mix == other.base_mix
            and self.base_theme == other.base_theme
        )

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(
            (
                tuple(c.value for c in self.colours),
                self.gradient_angle,
                self.base_mix,
                self.base_theme,
            )
        )

    def to_dict(self) -> SharedClientThemePayload:
        """Converts this theme into the payload Discord expects."""
        payload: SharedClientThemePayload = {
            "colors": [f"{c.value:06x}" for c in self.colours],
            "gradient_angle": self.gradient_angle,
            "base_mix": self.base_mix,
        }
        if self.base_theme is not None:
            payload["base_theme"] = self.base_theme.value
        return payload

    @classmethod
    def from_dict(cls, data: SharedClientThemePayload) -> Self:
        """Creates a theme from the payload Discord sends."""
        base_theme = data.get("base_theme")
        theme = cls.__new__(cls)
        theme.colours = [Colour(int(c.lstrip("#"), 16)) for c in data["colors"]]
        theme.gradient_angle = data["gradient_angle"]
        theme.base_mix = data["base_mix"]
        theme.base_theme = (
            None
            if base_theme is None
            else try_enum(SharedClientThemeBaseType, base_theme)
        )
        return theme

    if TYPE_CHECKING:
        colors: list[Colour]
