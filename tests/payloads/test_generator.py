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

import importlib
import pkgutil
from typing import Any

import pytest
import typing_extensions as te

import discord.types
from discord.types import channel, embed, user
from discord.utils import parse_time
from tests.payloads.generator import generate, is_snowflake, type_hints, variants

SHARE_EVENT_LOOP = True


def all_typeddicts() -> list[Any]:
    found = []
    for info in pkgutil.iter_modules(discord.types.__path__):
        module = importlib.import_module(f"discord.types.{info.name}")
        found.extend(
            value
            for value in vars(module).values()
            if te.is_typeddict(value) and value.__module__ == module.__name__
        )
    return found


@pytest.mark.parametrize(
    "tp", all_typeddicts(), ids=lambda tp: f"{tp.__module__}.{tp.__name__}"
)
@pytest.mark.parametrize("minimal", [False, True], ids=["full", "min"])
def test_every_typeddict_generates(tp: Any, minimal: bool) -> None:
    payload = generate(tp, minimal=minimal)
    assert isinstance(payload, dict)
    assert set(payload) <= set(type_hints(tp))


def test_generation_is_deterministic() -> None:
    assert generate(channel.TextChannel, seed=3) == generate(
        channel.TextChannel, seed=3
    )
    assert generate(channel.TextChannel, seed=3) != generate(
        channel.TextChannel, seed=4
    )


def test_minimal_omits_optional_keys() -> None:
    full = generate(user.User)
    minimal = generate(user.User, minimal=True)
    assert set(minimal) == set(user.PartialUser.__annotations__)
    assert set(minimal) < set(full)
    assert minimal["avatar"] is None


def test_snowflake_values_are_numeric_strings() -> None:
    assert is_snowflake(te.get_type_hints(user.PartialUser)["id"])
    assert generate(user.PartialUser)["id"].isdigit()


def test_literal_values_are_cycled_by_choice() -> None:
    seen = {generate(channel.PartialChannel, choice=i)["type"] for i in range(13)}
    assert seen == set(range(6)) | set(range(10, 17))


def test_union_yields_one_variant_per_branch() -> None:
    kinds = {v.payload["type"] for v in variants(channel.Channel)}
    assert {0, 2, 4}.issubset(kinds)


def test_embed_timestamp_is_iso() -> None:
    assert parse_time(generate(embed.Embed)["timestamp"]) is not None
