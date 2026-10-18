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

from __future__ import annotations

import pytest

import discord
from discord import Colour

FACTORIES = [
    ("dark_teal", 0x11806A),
    ("brand_green", 0x57F287),
    ("green", 0x2ECC71),
    ("dark_green", 0x1F8B4C),
    ("blue", 0x3498DB),
    ("dark_blue", 0x206694),
    ("purple", 0x9B59B6),
    ("dark_purple", 0x71368A),
    ("magenta", 0xE91E63),
    ("dark_magenta", 0xAD1457),
    ("gold", 0xF1C40F),
    ("dark_gold", 0xC27C0E),
    ("orange", 0xE67E22),
    ("dark_orange", 0xA84300),
    ("brand_red", 0xED4245),
    ("red", 0xE74C3C),
    ("dark_red", 0x992D22),
    ("lighter_grey", 0x95A5A6),
    ("dark_grey", 0x607D8B),
    ("light_grey", 0x979C9F),
    ("darker_grey", 0x546E7A),
    ("og_blurple", 0x7289DA),
    ("blurple", 0x5865F2),
    ("greyple", 0x99AAB5),
    ("light_theme", 0xFBFBFB),
    ("ash_theme", 0x323339),
    ("dark_theme", 0x1A1A1E),
    ("onyx_theme", 0x070709),
    ("fuchsia", 0xEB459E),
    ("yellow", 0xFEE75C),
    ("nitro_pink", 0xF47FFF),
]


@pytest.mark.parametrize(("name", "value"), FACTORIES)
def test_named_colours(name: str, value: int) -> None:
    colour = getattr(Colour, name)()
    assert isinstance(colour, Colour)
    assert colour.value == value


def test_the_british_spellings_alias_the_american_ones() -> None:
    assert Colour.lighter_gray() == Colour.lighter_grey()
    assert Colour.dark_gray() == Colour.dark_grey()
    assert Colour.light_gray() == Colour.light_grey()
    assert Colour.darker_gray() == Colour.darker_grey()
    assert Colour.grayple() == Colour.greyple()
    assert discord.Color is Colour


def test_colour_value_and_representations() -> None:
    colour = Colour(0x1A2B3C)
    assert (colour.r, colour.g, colour.b) == (0x1A, 0x2B, 0x3C)
    assert colour.to_rgb() == (0x1A, 0x2B, 0x3C)
    assert str(colour) == "#1a2b3c"
    assert str(Colour(0xF)) == "#00000f"
    assert int(colour) == 0x1A2B3C
    assert repr(colour) == f"<Colour value={0x1A2B3C}>"
    assert hash(colour) == hash(0x1A2B3C)
    assert colour == Colour(0x1A2B3C)
    assert colour != Colour(1)
    assert colour != 0x1A2B3C
    assert Colour.default().value == 0


def test_colour_requires_an_integer() -> None:
    with pytest.raises(TypeError, match="Expected int parameter, received str"):
        Colour("red")  # type: ignore[arg-type]


def test_resolve_value() -> None:
    colour = Colour(5)
    assert Colour.resolve_value(None) is None
    assert Colour.resolve_value(colour) is colour
    assert Colour.resolve_value(7) == Colour(7)
    with pytest.raises(TypeError, match=r"Expected discord\.Colour, int, or None"):
        Colour.resolve_value("x")  # type: ignore[call-overload]


def test_colour_factories_from_components() -> None:
    assert Colour.from_rgb(1, 2, 3).value == 0x010203
    assert Colour.from_hsv(0, 1, 1) == Colour(0xFF0000)
    assert Colour.from_hsv(1 / 3, 1, 1) == Colour(0x00FF00)
    assert Colour.from_hsv(2 / 3, 1, 1).to_rgb() == (0, 0, 255)


def test_random_colours_are_reproducible_with_a_seed() -> None:
    assert Colour.random(seed=3) == Colour.random(seed=3)
    assert Colour.random(seed="a") != Colour.random(seed="b")
    unseeded = Colour.random()
    assert 0 <= unseeded.value <= 0xFFFFFF


@pytest.mark.parametrize(
    ("theme", "value"), [("dark", 0x2B2D31), ("light", 0xEEEFF1), ("amoled", 0)]
)
def test_embed_background(theme: str, value: int) -> None:
    with pytest.warns(DeprecationWarning, match="embed_background"):
        assert Colour.embed_background(theme).value == value


def test_embed_background_rejects_unknown_themes() -> None:
    with (
        pytest.warns(DeprecationWarning, match="embed_background"),
        pytest.raises(TypeError, match="Theme must be"),
    ):
        Colour.embed_background("sepia")
