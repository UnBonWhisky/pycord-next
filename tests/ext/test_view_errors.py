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

# ruff: noqa: UP007, PT018

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Union

import pytest

from discord.ext import commands
from discord.ext.commands.view import StringView


class TestStringView:
    def test_cursor_basics(self) -> None:
        view = StringView("ab cd")
        assert view.current == "a" and not view.eof
        assert view.get() == "b"
        assert view.current == "b"
        view.undo()
        assert view.current == "a"
        assert view.read(3) == "ab "
        assert view.read_rest() == "cd"
        assert view.eof and view.current is None
        assert view.get() is None
        assert "eof: True" in repr(view)

    def test_skip_ws_and_skip_string(self) -> None:
        view = StringView("   !cmd")
        assert view.skip_ws() is True
        assert view.skip_ws() is False
        assert view.skip_string("?") is False
        assert view.skip_string("!") is True
        assert view.get_word() == "cmd"
        assert view.get_word() == ""

    def test_skip_ws_on_empty_buffer(self) -> None:
        assert StringView("").skip_ws() is False

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("hello world", "hello"),
            ('"hello world" tail', "hello world"),
            ("“curly quotes” tail", "curly quotes"),
            ('"a \\"b\\"" tail', 'a "b"'),
            ("a\\ b", "a\\"),
            ("a\\nb", "a\\nb"),
            ("plain", "plain"),
            ('"quoted"', "quoted"),
            ("trailing\\", "trailing"),
        ],
    )
    def test_get_quoted_word(self, text: str, expected: str) -> None:
        assert StringView(text).get_quoted_word() == expected

    def test_get_quoted_word_at_the_end(self) -> None:
        view = StringView("")
        assert view.get_quoted_word() is None

    def test_unterminated_quote(self) -> None:
        with pytest.raises(commands.ExpectedClosingQuoteError) as info:
            StringView('"abc').get_quoted_word()
        assert info.value.close_quote == '"'
        with pytest.raises(commands.ExpectedClosingQuoteError):
            StringView('"abc\\').get_quoted_word()

    def test_quote_inside_a_plain_word(self) -> None:
        with pytest.raises(commands.UnexpectedQuoteError) as info:
            StringView('ab"c').get_quoted_word()
        assert info.value.quote == '"'

    def test_text_after_a_closing_quote(self) -> None:
        with pytest.raises(commands.InvalidEndOfQuotedStringError) as info:
            StringView('"abc"d').get_quoted_word()
        assert info.value.char == "d"

    def test_words_in_sequence(self) -> None:
        view = StringView('one "two three"   four')
        words = []
        while True:
            view.skip_ws()
            word = view.get_quoted_word()
            if word is None:
                break
            words.append(word)
        assert words == ["one", "two three", "four"]


class TestErrorMessages:
    def test_conversion_error(self) -> None:
        original = ValueError("x")

        class Mine(commands.Converter):
            async def convert(self, ctx: Any, argument: str) -> None: ...

        converter = Mine()
        error = commands.ConversionError(converter, original)
        assert error.original is original and error.converter is converter

    def test_role_errors(self) -> None:
        assert str(commands.MissingAnyRole(["a", "b", 3])) == (
            "You are missing at least one of the required roles: 'a', 'b', or '3'"
        )
        assert str(commands.MissingAnyRole(["a", "b"])).endswith("'a' or 'b'")
        assert str(commands.BotMissingAnyRole(["a", "b", "c"])).endswith(
            "'a', 'b', or 'c'"
        )
        assert str(commands.BotMissingAnyRole([1, 2])).endswith("'1' or '2'")

    def test_permission_errors(self) -> None:
        error = commands.MissingPermissions(
            ["manage_guild", "ban_members", "kick_members"]
        )
        assert str(error) == (
            "You are missing Manage Server, Ban Members, and Kick Members"
            " permission(s) to run this command."
        )
        assert str(
            commands.MissingPermissions(["ban_members", "kick_members"])
        ).startswith("You are missing Ban Members and Kick Members")
        error = commands.BotMissingPermissions(["a_b", "c", "d"])
        assert "A B, C, and D" in str(error)
        assert "Bot requires Ban Members and Kick Members" in str(
            commands.BotMissingPermissions(["ban_members", "kick_members"])
        ) or "Ban Members and Kick Members" in str(
            commands.BotMissingPermissions(["ban_members", "kick_members"])
        )

    def test_bad_union_argument(self) -> None:
        param = inspect.Parameter("p", inspect.Parameter.POSITIONAL_ONLY)
        error = commands.BadUnionArgument(
            param, (int, str, float), [commands.CommandError("e")]
        )
        assert str(error) == 'Could not convert "p" into int, str, or float.'
        generic = SimpleNamespace(__origin__=list)
        error = commands.BadUnionArgument(param, (int, generic), [])
        assert str(error) == f'Could not convert "p" into int or {generic!r}.'
        error = commands.BadUnionArgument(param, (int, 5), [])
        assert str(error) == 'Could not convert "p" into int or int.'
        assert error.converters == (int, 5)

    def test_bad_literal_argument(self) -> None:
        param = inspect.Parameter("p", inspect.Parameter.POSITIONAL_ONLY)
        three = commands.BadLiteralArgument(param, ("a", 1, None), [])
        assert str(three) == "Could not convert \"p\" into the literal 'a', 1, or None."
        two = commands.BadLiteralArgument(param, ("a", "b"), [])
        assert str(two).endswith("'a' or 'b'.")

    def test_bad_flag_argument_names(self) -> None:
        class Plain(commands.FlagConverter):
            a: int = 1

        named = commands.Flag(name="n", annotation=int)
        assert str(commands.BadFlagArgument(named)) == (
            "Could not convert to 'int' for flag 'n'"
        )
        unnamed = commands.Flag(name="n", annotation=Union[int, str])
        assert "Union" in str(commands.BadFlagArgument(unnamed)) or "UnionType" in str(
            commands.BadFlagArgument(unnamed)
        )

    def test_flag_errors(self) -> None:
        flag = commands.Flag(name="n", annotation=int)
        assert "n" in str(commands.MissingFlagArgument(flag))
        assert "n" in str(commands.MissingRequiredFlag(flag))
        too_many = commands.TooManyFlags(flag, ["a", "b"])
        assert too_many.values == ["a", "b"]

    def test_quote_errors(self) -> None:
        assert "'x'" in str(commands.UnexpectedQuoteError("x"))
        assert "'y'" in str(commands.InvalidEndOfQuotedStringError("y"))
        assert commands.ExpectedClosingQuoteError('"').close_quote == '"'
