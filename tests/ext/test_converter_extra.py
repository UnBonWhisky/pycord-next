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

# ruff: noqa: UP007, UP045

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Literal, Optional, Union

import pytest

import discord
from discord.ext import commands
from discord.ext.commands.converter import get_converter, run_converters

if TYPE_CHECKING:
    from tests.ext.support import Server


def param(
    annotation: Any = inspect.Parameter.empty,
    default: Any = inspect.Parameter.empty,
    kind: Any = inspect.Parameter.POSITIONAL_OR_KEYWORD,
) -> inspect.Parameter:
    return inspect.Parameter("p", kind, annotation=annotation, default=default)


def convert(server: Server, converter: Any, argument: str, p: Any = None) -> Any:
    ctx = server.context("x")
    return server.run(run_converters(ctx, converter, argument, p or param(converter)))


class TestColourConverter:
    def colour(self, server: Server, argument: str) -> discord.Colour:
        return server.run(
            commands.ColourConverter().convert(server.context("x"), argument)
        )

    @pytest.mark.parametrize(
        ("argument", "value"),
        [
            ("#ff0000", 0xFF0000),
            ("#f00", 0xFF0000),
            ("0xabcdef", 0xABCDEF),
            ("0x#00ff00", 0x00FF00),
            ("rgb(255, 0, 128)", 0xFF0080),
            ("RGB(100%, 0%, 50%)", 0xFF0080),
            ("red", discord.Colour.red().value),
            ("dark red", discord.Colour.dark_red().value),
        ],
    )
    def test_valid(self, server: Server, argument: str, value: int) -> None:
        assert self.colour(server, argument).value == value

    @pytest.mark.parametrize(
        "argument",
        [
            "#xyz",
            "#1234567",
            "rgb(300, 0, 0)",
            "rgb(0, 0)",
            "rgb(101%, 0%, 0%)",
            "from_rgb",
            "not a colour",
            "to_rgb",
        ],
    )
    def test_invalid(self, server: Server, argument: str) -> None:
        with pytest.raises(commands.BadColourArgument):
            self.colour(server, argument)


class TestGreedyValidation:
    def test_valid(self) -> None:
        greedy = commands.Greedy[int]
        assert greedy.converter is int
        assert repr(greedy) == "Greedy[int]"
        assert "Greedy" in repr(commands.Greedy[commands.MemberConverter()])

    @pytest.mark.parametrize(
        "bad", [str, type(None), commands.Greedy[int], Optional[int]]
    )
    def test_invalid(self, bad: Any) -> None:
        with pytest.raises(TypeError):
            commands.Greedy[bad]

    def test_not_a_converter(self) -> None:
        with pytest.raises(TypeError, match="expects a type or a Converter"):
            commands.Greedy[5]

    def test_single_argument_only(self) -> None:
        with pytest.raises(TypeError, match="single argument"):
            commands.Greedy[int, str]


class TestGetConverter:
    def test_annotation_wins(self) -> None:
        assert get_converter(param(int, default="x")) is int

    def test_defaults(self) -> None:
        assert get_converter(param()) is str
        assert get_converter(param(default=None)) is str
        assert get_converter(param(default=3)) is int


class TestRunConverters:
    def test_bool(self, server: Server) -> None:
        assert convert(server, bool, "yes") is True
        assert convert(server, bool, "Off") is False
        with pytest.raises(commands.BadBoolArgument):
            convert(server, bool, "perhaps")

    def test_callable_failure_is_a_bad_argument(self, server: Server) -> None:
        with pytest.raises(commands.BadArgument, match='Converting to "int" failed'):
            convert(server, int, "x")

    def test_failing_converter_class_is_a_conversion_error(
        self, server: Server
    ) -> None:
        class Broken(commands.Converter):
            async def convert(self, ctx: Any, argument: str) -> None:
                raise RuntimeError("bug")

        for converter in (Broken, Broken()):
            with pytest.raises(commands.ConversionError) as info:
                convert(server, converter, "x")
            assert isinstance(info.value.original, RuntimeError)

    def test_command_errors_from_converters_propagate(self, server: Server) -> None:
        class Picky(commands.Converter):
            async def convert(self, ctx: Any, argument: str) -> None:
                raise commands.BadArgument("nope")

        with pytest.raises(commands.BadArgument, match="nope"):
            convert(server, Picky, "x")

    def test_converter_class_with_classmethod(self, server: Server) -> None:
        class WithClassmethod(commands.Converter):
            @classmethod
            async def convert(cls, ctx: Any, argument: str) -> str:
                return f"cls:{argument}"

        assert convert(server, WithClassmethod, "x") == "cls:x"

    def test_converter_class_with_instance_method(self, server: Server) -> None:
        class Plain(commands.Converter):
            async def convert(self, ctx: Any, argument: str) -> str:
                return f"inst:{argument}"

        assert convert(server, Plain, "x") == "inst:x"
        assert convert(server, Plain(), "x") == "inst:x"

    def test_union(self, server: Server) -> None:
        assert convert(server, Union[int, str], "5") == 5
        assert convert(server, Union[int, str], "x") == "x"
        with pytest.raises(commands.BadUnionArgument) as info:
            convert(server, Union[int, float], "x")
        assert len(info.value.errors) == 2

    def test_optional_falls_back_to_the_default(self, server: Server) -> None:
        ctx = server.context("hello")
        ctx.view.read(2)
        result = server.run(
            run_converters(ctx, Optional[int], "x", param(Optional[int], default=7))
        )
        assert result == 7
        assert ctx.view.index == 0
        assert (
            server.run(run_converters(ctx, Optional[int], "x", param(Optional[int])))
            is None
        )

    def test_optional_in_var_positional_does_not_swallow(self, server: Server) -> None:
        with pytest.raises(commands.BadUnionArgument):
            convert(
                server,
                Optional[int],
                "x",
                param(Optional[int], kind=inspect.Parameter.VAR_POSITIONAL),
            )

    def test_literal(self, server: Server) -> None:
        assert convert(server, Literal["a", "b"], "b") == "b"
        assert convert(server, Literal[1, 2], "2") == 2
        with pytest.raises(commands.BadLiteralArgument) as info:
            convert(server, Literal[1, 2, "z"], "x")
        assert info.value.literals == (1, 2, "z")
        assert len(info.value.errors) == 1
        with pytest.raises(commands.BadLiteralArgument):
            convert(server, Literal[1, 2], "9")

    def test_literal_with_mixed_types(self, server: Server) -> None:
        assert convert(server, Literal[1, "one"], "one") == "one"
        assert convert(server, Literal[True, "t"], "yes") is True

    def test_generic_aliases_use_their_origin(self, server: Server) -> None:
        assert convert(server, list[int], "5") == ["5"]

    def test_discord_types_use_the_mapping(self, server: Server) -> None:
        role = server.add_role(None, "Mods", position=2)
        assert convert(server, discord.Role, str(role.id)).id == role.id

    def test_objects_without_a_module(self, server: Server) -> None:
        class Callable:
            __module__ = None

            def __call__(self, argument: str) -> str:
                return argument * 2

        assert convert(server, Callable(), "ab") == "abab"

    def test_failing_plain_callable_without_a_name(self, server: Server) -> None:
        class Failing:
            def __call__(self, argument: str) -> None:
                raise ValueError

        with pytest.raises(commands.BadArgument, match='"Failing"'):
            convert(server, Failing(), "x")
