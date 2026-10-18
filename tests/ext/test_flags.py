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

from discord.ext import commands
from discord.ext.commands import flags as flags_module

if TYPE_CHECKING:
    from tests.ext.support import Server


class Basic(commands.FlagConverter):
    name: str
    count: int = 1


class Prefixed(commands.FlagConverter, prefix="--", delimiter="="):
    user: str
    limit: Optional[int]


class Insensitive(commands.FlagConverter, case_insensitive=True):
    Name: str = commands.flag(aliases=["N"])


class Collections(commands.FlagConverter):
    tags: list[str] = commands.flag(default=lambda ctx: [])
    pair: tuple[str, int] = commands.flag(default=("a", 0))
    many: tuple[int, ...] = commands.flag(default=())
    mapping: dict[str, int] = commands.flag(default=lambda ctx: {})
    mode: Literal["a", "b"] = "a"
    either: Union[int, str] = 0


class Positional(commands.FlagConverter):
    text: str = commands.flag(positional=True)
    loud: bool = False


class Overriding(commands.FlagConverter):
    value: int = commands.flag(override=True)


class Inner(commands.FlagConverter):
    a: int = 1


class Outer(commands.FlagConverter):
    inner: Inner


def make_ctx(server: Server) -> commands.Context:
    ctx = server.context("x")
    ctx.current_parameter = inspect.Parameter(
        "p", inspect.Parameter.KEYWORD_ONLY, annotation=Any
    )
    return ctx


def convert(server: Server, cls: Any, argument: str) -> Any:
    return server.run(cls.convert(make_ctx(server), argument))


class TestFlagObject:
    def test_required_follows_default(self) -> None:
        assert commands.Flag().required
        assert not commands.Flag(default=3).required

    def test_flag_helper_stores_options(self) -> None:
        f = commands.flag(name="n", aliases=["a"], default=1, max_args=2)
        assert (f.name, f.aliases, f.default, f.max_args) == ("n", ["a"], 1, 2)


class TestDefinition:
    def test_get_flags_is_a_copy(self) -> None:
        flags = Basic.get_flags()
        assert list(flags) == ["name", "count"]
        flags.clear()
        assert list(Basic.get_flags()) == ["name", "count"]

    def test_max_args_from_annotations(self) -> None:
        flags = Collections.get_flags()
        assert flags["tags"].max_args == -1
        assert flags["pair"].max_args == 1
        assert flags["mapping"].max_args == -1
        assert flags["mapping"].override
        assert flags["mapping"].cast_to_dict
        assert flags["mode"].max_args == 1
        assert flags["either"].max_args == 1
        assert Basic.get_flags()["name"].max_args == 1

    def test_optional_defaults_to_none(self) -> None:
        assert Prefixed.get_flags()["limit"].default is None
        assert Prefixed.get_flags()["user"].default is not None

    def test_nested_flag_converter_with_defaults_is_constructible(self) -> None:
        assert Inner._can_be_constructible()
        assert not Basic._can_be_constructible()
        assert callable(Outer.get_flags()["inner"].default)

    def test_inheritance_merges_flags_and_settings(self) -> None:
        class Child(Prefixed):
            extra: int = 0

        assert list(Child.get_flags()) == ["user", "limit", "extra"]
        assert Child.__commands_flag_prefix__ == "--"
        assert Child.__commands_flag_delimiter__ == "="

    def test_inheritance_can_override_settings(self) -> None:
        class Child(Prefixed, prefix="+", delimiter=":", case_insensitive=True):
            pass

        assert Child.__commands_flag_prefix__ == "+"
        assert Child.__commands_flag_delimiter__ == ":"
        assert Child.__commands_flag_case_insensitive__

    def test_two_positional_flags_conflict(self) -> None:
        with pytest.raises(TypeError, match="positional flag conflicts"):

            class Bad(commands.FlagConverter):
                a: str = commands.flag(positional=True)
                b: str = commands.flag(positional=True)

    def test_unsupported_annotation(self) -> None:
        with pytest.raises(TypeError, match="Unsupported typing annotation"):

            class Bad(commands.FlagConverter):
                a: set[int]

    def test_duplicate_names(self) -> None:
        with pytest.raises(TypeError, match="conflicts with previous flag"):

            class Bad(commands.FlagConverter):
                a: int = commands.flag(name="b")
                b: int

    def test_duplicate_alias(self) -> None:
        with pytest.raises(TypeError, match="alias"):

            class Bad(commands.FlagConverter):
                a: int
                b: int = commands.flag(aliases=["a"])

    def test_case_insensitive_names_conflict(self) -> None:
        with pytest.raises(TypeError, match="conflicts"):

            class Bad(commands.FlagConverter, case_insensitive=True):
                a: int
                A_: int = commands.flag(name="A")

    @pytest.mark.parametrize(
        ("name", "message"),
        [
            ("", "empty"),
            ("a b", "spaces"),
            ("a\\b", "backslashes"),
            ("a:b", "within them"),
        ],
    )
    def test_invalid_flag_names(self, name: str, message: str) -> None:
        with pytest.raises(ValueError, match=message):
            flags_module.validate_flag_name(name, {":"})

    def test_invalid_name_rejected_at_class_creation(self) -> None:
        with pytest.raises(ValueError, match="within them"):

            class Bad(commands.FlagConverter):
                a: int = commands.flag(name="x:y")

    def test_repr_and_iter(self, server: Server) -> None:
        value = convert(server, Basic, "name: bob count: 4")
        assert dict(value) == {"name": "bob", "count": 4}
        assert repr(value) == "<Basic name='bob' count=4>"


class TestParseFlags:
    def test_basic(self) -> None:
        assert Basic.parse_flags("name: bob smith count: 3") == {
            "name": ["bob smith"],
            "count": ["3"],
        }

    def test_no_flags(self) -> None:
        assert Basic.parse_flags("nothing here") == {}

    def test_repeated_flag_collects_values(self) -> None:
        assert Collections.parse_flags("tags: a tags: b") == {"tags": ["a", "b"]}

    def test_missing_value_at_end(self) -> None:
        with pytest.raises(commands.MissingFlagArgument):
            Basic.parse_flags("count: 3 name:")

    def test_missing_value_in_middle(self) -> None:
        with pytest.raises(commands.MissingFlagArgument):
            Basic.parse_flags("name: count: 3")

    def test_prefix_and_delimiter(self) -> None:
        assert Prefixed.parse_flags("--user=bob --limit=5") == {
            "user": ["bob"],
            "limit": ["5"],
        }

    def test_case_insensitive_and_alias(self) -> None:
        assert Insensitive.parse_flags("NAME: a") == {"name": ["a"]}
        assert Insensitive.parse_flags("n: a") == {"name": ["a"]}

    def test_positional_before_flags(self) -> None:
        assert Positional.parse_flags("hello world loud: yes") == {
            "text": ["hello world"],
            "loud": ["yes"],
        }

    def test_positional_alone(self) -> None:
        assert Positional.parse_flags("  hello  ") == {"text": ["hello"]}

    def test_positional_empty(self) -> None:
        assert Positional.parse_flags("loud: 1") == {"loud": ["1"]}


class TestConvert:
    def test_converts_values(self, server: Server) -> None:
        value = convert(server, Basic, "name: bob count: 3")
        assert (value.name, value.count) == ("bob", 3)

    def test_default_used_when_absent(self, server: Server) -> None:
        assert convert(server, Basic, "name: bob").count == 1

    def test_missing_required(self, server: Server) -> None:
        with pytest.raises(commands.MissingRequiredFlag) as info:
            convert(server, Basic, "count: 3")
        assert info.value.flag.name == "name"

    def test_bad_argument(self, server: Server) -> None:
        with pytest.raises(commands.BadArgument):
            convert(server, Basic, "name: bob count: many")

    def test_unexpected_converter_failure_is_a_bad_flag_argument(
        self, server: Server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(flags_module, "run_converters", boom)
        with pytest.raises(commands.BadFlagArgument) as info:
            convert(server, Basic, "name: bob count: 1")
        assert info.value.flag.name in {"name", "count"}
        with pytest.raises(commands.BadFlagArgument):
            convert(server, Collections, "pair: a 1")
        with pytest.raises(commands.BadFlagArgument):
            convert(server, Collections, "many: 1 2")

    def test_too_many(self, server: Server) -> None:
        with pytest.raises(commands.TooManyFlags) as info:
            convert(server, Basic, "name: a name: b")
        assert info.value.values == ["a", "b"]

    def test_override_keeps_last(self, server: Server) -> None:
        assert convert(server, Overriding, "value: 1 value: 2").value == 2

    def test_optional(self, server: Server) -> None:
        value = convert(server, Prefixed, "--user=bob")
        assert value.limit is None
        assert convert(server, Prefixed, "--user=bob --limit=7").limit == 7

    def test_optional_bad_value_is_a_command_error(self, server: Server) -> None:
        with pytest.raises(commands.CommandError):
            convert(server, Prefixed, "--user=bob --limit=x")

    def test_list(self, server: Server) -> None:
        value = convert(server, Collections, "tags: a tags: b")
        assert value.tags == ["a", "b"]

    def test_list_default_callable(self, server: Server) -> None:
        assert convert(server, Collections, "").tags == []

    def test_tuple(self, server: Server) -> None:
        value = convert(server, Collections, 'pair: "hello there" 5')
        assert value.pair == ("hello there", 5)

    def test_tuple_too_short(self, server: Server) -> None:
        with pytest.raises(commands.BadFlagArgument):
            convert(server, Collections, "pair: hello")

    def test_tuple_bad_member(self, server: Server) -> None:
        with pytest.raises(commands.BadArgument):
            convert(server, Collections, "pair: hello x")

    def test_variadic_tuple(self, server: Server) -> None:
        assert convert(server, Collections, "many: 1 2  3").many == (1, 2, 3)

    def test_variadic_tuple_bad_member(self, server: Server) -> None:
        with pytest.raises(commands.BadArgument):
            convert(server, Collections, "many: 1 x")

    def test_dict(self, server: Server) -> None:
        value = convert(server, Collections, "mapping: a 1 mapping: b 2")
        assert value.mapping == {"a": 1, "b": 2}

    def test_literal(self, server: Server) -> None:
        assert convert(server, Collections, "mode: b").mode == "b"
        with pytest.raises(commands.CommandError):
            convert(server, Collections, "mode: z")

    def test_union(self, server: Server) -> None:
        assert convert(server, Collections, "either: 5").either == 5
        assert convert(server, Collections, "either: five").either == "five"

    def test_positional(self, server: Server) -> None:
        value = convert(server, Positional, "some text loud: yes")
        assert (value.text, value.loud) == ("some text", True)

    def test_nested_flag_default(self, server: Server) -> None:
        value = convert(server, Outer, "")
        assert isinstance(value.inner, Inner)
        assert value.inner.a == 1

    def test_nested_default_with_plain_defaults(self, server: Server) -> None:
        value = server.run(Inner._construct_default(make_ctx(server)))
        assert value.a == 1

    def test_case_insensitive_alias_convert(self, server: Server) -> None:
        assert convert(server, Insensitive, "n: z").Name == "z"
