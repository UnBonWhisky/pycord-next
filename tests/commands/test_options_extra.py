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

import sys
from enum import Enum, IntEnum
from typing import Union

import pytest

import discord
from discord import ChannelType, Option, OptionChoice, ThreadOption
from discord.enums import SlashCommandOptionType as OptionType

if sys.version_info >= (3, 12):
    from typing import TypeAliasType
else:
    from typing_extensions import TypeAliasType


class Letters(Enum):
    """The letters."""

    a = "a"
    b = "b"


class Numbers(IntEnum):
    one = 1
    two = 2


class Mixed(Enum):
    tuple_value = (1, 2)
    text = "text"


Many = Enum("Many", {f"v{i}": i for i in range(30)})


def test_thread_option_types() -> None:
    assert ThreadOption("public")._type is ChannelType.public_thread
    assert ThreadOption("private")._type is ChannelType.private_thread
    assert ThreadOption("news")._type is ChannelType.news_thread


def test_enum_options() -> None:
    letters = Option(Letters)
    assert letters.description == "The letters."
    assert letters.input_type is OptionType.string
    assert [(c.name, c.value) for c in letters.choices] == [("a", "a"), ("b", "b")]

    numbers = Option(Numbers, "Pick one")
    assert numbers.description == "Pick one"
    assert numbers.input_type is OptionType.string
    assert [(c.name, c.value) for c in numbers.choices] == [("one", "1"), ("two", "2")]

    mixed = Option(Mixed)
    assert mixed.input_type is OptionType.string
    assert {c.value for c in mixed.choices} == {"(1, 2)", "text"}


def test_large_enums_use_autocomplete() -> None:
    option = Option(Many)
    assert option.choices == []
    assert option.input_type is OptionType.string
    assert option.autocomplete is not None


def test_long_enum_docstrings_are_truncated(caplog: pytest.LogCaptureFixture) -> None:
    class Long(Enum):
        a = "a"

    Long.__doc__ = "x" * 200
    with caplog.at_level("WARNING"):
        option = Option(Long)
    assert option.description == "x" * 97 + "..."
    assert "was truncated" in caplog.text


def test_type_resolution() -> None:
    assert Option(discord.Member).input_type is OptionType.user
    assert Option(discord.Role).input_type is OptionType.role
    assert (
        Option(Union[discord.Member, discord.Role]).input_type is OptionType.mentionable  # noqa: UP007
    )
    assert Option(discord.Member | None)._raw_type is discord.Member
    assert Option(int).input_type is OptionType.integer
    assert Option(float).input_type is OptionType.number
    assert Option(OptionType.boolean).input_type is OptionType.boolean
    channel = Option(discord.TextChannel)
    assert channel.channel_types == [ChannelType.text]
    both = Option(discord.TextChannel | discord.VoiceChannel)
    assert both.channel_types == [ChannelType.text, ChannelType.voice]
    explicit = Option(str, channel_types=[ChannelType.category])
    assert explicit.input_type is OptionType.channel
    assert Option(discord.abc.GuildChannel).channel_types == []


def test_none_types_are_rejected() -> None:
    with pytest.raises(TypeError, match="only NoneType"):
        Option(type(None))
    with pytest.raises(TypeError, match="only NoneType"):
        Option((type(None), type(None)))


def test_type_aliases() -> None:
    alias = TypeAliasType("Alias", int | None)
    assert Option(alias).input_type is OptionType.integer  # type: ignore[arg-type]


def test_converters() -> None:
    from discord.ext import commands

    class Upper(commands.Converter):  # type: ignore[type-arg]
        async def convert(self, ctx: object, argument: str) -> str:
            return argument.upper()

    option = Option(Upper)
    assert option.converter is Upper
    assert option.input_type is OptionType.string
    assert Option(discord.Colour).converter is not None
    assert Option(discord.Colour).input_type is OptionType.string


def test_defaults_and_required() -> None:
    assert Option(str).required is True
    with_default = Option(str, default="x")
    assert with_default.required is False
    assert with_default.default == "x"
    assert Option(str, required=False).required is False


def test_choices_and_numeric_bounds() -> None:
    option = Option(int, choices=[1, OptionChoice("two", 2)], min_value=0, max_value=5)
    assert [(c.name, c.value) for c in option.choices] == [("1", 1), ("two", 2)]
    assert (option.min_value, option.max_value) == (0, 5)
    assert Option(float, min_value=0.5, max_value=2).max_value == 2
    text = Option(str, min_length=1, max_length=10)
    assert (text.min_length, text.max_length) == (1, 10)


@pytest.mark.parametrize(
    ("args", "kwargs", "error", "message"),
    [
        ((str,), {"min_value": 1}, AttributeError, "min_value or max_value"),
        ((int,), {"min_length": 1}, AttributeError, "min_length or max_length"),
        ((int,), {"min_value": 1.5}, TypeError, "Expected int | None for min_value"),
        ((float,), {"max_value": "x"}, TypeError, "for max_value"),
        ((str,), {"min_length": 1.5}, TypeError, "for min_length"),
        ((str,), {"max_length": "x"}, TypeError, "for max_length"),
        ((str,), {"min_length": -1}, AttributeError, "min_length must be between"),
        ((str,), {"min_length": 7000}, AttributeError, "min_length must be between"),
        ((str,), {"max_length": 0}, AttributeError, "max_length must between"),
        ((str,), {"max_length": 7000}, AttributeError, "max_length must between"),
    ],
)
def test_invalid_bounds(
    args: tuple[object, ...],
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        Option(*args, **kwargs)  # type: ignore[arg-type]


def test_option_representation_and_serialisation() -> None:
    option = Option(
        str,
        "Describe",
        name="thing",
        name_localizations={"fr": "chose"},
        description_localizations={"fr": "decrire"},
    )
    assert repr(option) == "<discord.commands.Option name=thing>"
    data = option.to_dict()
    assert data["name"] == "thing"
    assert data["name_localizations"] == {"fr": "chose"}
    assert data["description_localizations"] == {"fr": "decrire"}
    assert data["type"] == OptionType.string.value
