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

"""Shared client themes and component embeds."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

import discord
from discord import (
    Colour,
    Embed,
    File,
    SharedClientTheme,
    SharedClientThemeBaseType,
    types as t,
)
from discord.components import Container, TextDisplay
from discord.http import HTTPClient

if TYPE_CHECKING:
    from tests.models.context import World

DOCS_COLORS = ["5865F2", "7258F2", "9858F2", "BE58F2", "E558F2"]
DOCS_EXAMPLE = {
    "colors": DOCS_COLORS,
    "gradient_angle": 0,
    "base_mix": 58,
    "base_theme": 1,
}


def test_base_theme_types_match_the_docs() -> None:
    assert {m.name: m.value for m in SharedClientThemeBaseType} == {
        "unset": 0,
        "dark": 1,
        "light": 2,
        "darker": 3,
        "midnight": 4,
    }


def test_docs_example_round_trips() -> None:
    theme = SharedClientTheme.from_dict(DOCS_EXAMPLE)  # pyright: ignore[reportArgumentType]
    assert theme.colours[0] == Colour(0x5865F2)
    assert theme.base_theme is SharedClientThemeBaseType.dark
    assert (theme.gradient_angle, theme.base_mix) == (0, 58)
    assert theme.to_dict() == {
        **DOCS_EXAMPLE,
        "colors": [c.lower() for c in DOCS_COLORS],
    }


def test_colors_and_colours_are_the_same() -> None:
    american = SharedClientTheme(colors=[Colour(1), 2])
    british = SharedClientTheme(colours=[Colour(1), Colour(2)])
    assert american == british
    assert american.colors == american.colours == [Colour(1), Colour(2)]
    assert hash(american) == hash(british)
    assert american != SharedClientTheme(colours=[Colour(1)])
    assert american != SharedClientTheme(
        colours=[1, 2], base_theme=SharedClientThemeBaseType.light
    )
    with pytest.raises(TypeError):
        SharedClientTheme(colors=[1], colours=[2])


def test_arguments_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        SharedClientTheme([1])  # type: ignore[misc]
    with pytest.raises(TypeError):
        SharedClientTheme()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "fields",
    [
        {"colours": [1] * 6},
        {"colours": [], "gradient_angle": 361},
        {"colours": [], "gradient_angle": -1},
        {"colours": [], "base_mix": 101},
        {"colours": [], "base_mix": -1},
    ],
)
def test_ranges_are_checked(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        SharedClientTheme(**fields)


def test_base_theme_type_is_checked() -> None:
    with pytest.raises(TypeError):
        SharedClientTheme(colours=[], base_theme=1)  # type: ignore[arg-type]


def test_null_base_theme_is_omitted_and_parsed() -> None:
    theme = SharedClientTheme(colours=[Colour(255)], base_theme=None)
    assert "base_theme" not in theme.to_dict()
    parsed = SharedClientTheme.from_dict(
        {"colors": ["0000ff"], "gradient_angle": 1, "base_mix": 2, "base_theme": None}
    )
    assert parsed.base_theme is None
    assert (
        SharedClientTheme.from_dict(
            {"colors": [], "gradient_angle": 1, "base_mix": 2}
        ).base_theme
        is None
    )


def test_unknown_base_theme_is_kept() -> None:
    theme = SharedClientTheme.from_dict(
        {"colors": [], "gradient_angle": 0, "base_mix": 0, "base_theme": 9}  # pyright: ignore[reportArgumentType]
    )
    assert theme.base_theme is not None
    assert theme.base_theme.value == 9


def test_colour_values_are_padded() -> None:
    assert SharedClientTheme(colours=[Colour(0xFF)]).to_dict()["colors"] == ["0000ff"]


def test_message_shared_client_theme(world: World) -> None:
    payload = world.payload(t.message.Message, shared_client_theme=DOCS_EXAMPLE)
    message = discord.Message(state=world.state, channel=world.channel, data=payload)
    assert message.shared_client_theme is not None
    assert message.shared_client_theme.base_mix == 58
    del payload["shared_client_theme"]
    plain = discord.Message(state=world.state, channel=world.channel, data=payload)
    assert plain.shared_client_theme is None


def test_message_update_replaces_the_theme(world: World) -> None:
    message = world.message
    message._handle_shared_client_theme(DOCS_EXAMPLE)  # pyright: ignore[reportArgumentType]
    assert message.shared_client_theme is not None
    message._handle_shared_client_theme(None)  # type: ignore[arg-type]
    assert message.shared_client_theme is None


@pytest.fixture
def sent(world: World) -> Mock:
    payload = world.payload(
        t.message.Message, channel_id=str(world.channel.id), id="123"
    )
    http = Mock()
    http.send_message = AsyncMock(return_value=payload)
    http.send_files = AsyncMock(return_value=payload)
    world.state.http = http
    return http


async def test_send_theme(world: World, sent: Mock) -> None:
    theme = SharedClientTheme.from_dict(DOCS_EXAMPLE)  # pyright: ignore[reportArgumentType]
    await world.channel.send(shared_client_theme=theme)
    assert sent.send_message.await_args.kwargs["shared_client_theme"] == theme.to_dict()
    await world.channel.send(
        "x", file=File(BytesIO(b"x"), "x.txt"), shared_client_theme=theme
    )
    assert sent.send_files.await_args.kwargs["shared_client_theme"] == theme.to_dict()


async def test_send_without_theme(world: World, sent: Mock) -> None:
    await world.channel.send("x")
    assert sent.send_message.await_args.kwargs["shared_client_theme"] is None


async def test_reply_forwards_the_theme(world: World, sent: Mock) -> None:
    theme = SharedClientTheme(colours=[1])
    await world.message.reply(shared_client_theme=theme)
    assert sent.send_message.await_args.kwargs["shared_client_theme"] == theme.to_dict()


async def test_theme_is_rejected_with_components_v2(world: World, sent: Mock) -> None:
    view = SimpleNamespace(
        __discord_ui_view__=True,
        to_components=list,
        is_components_v2=lambda: True,
    )
    theme = SharedClientTheme(colours=[1])
    with pytest.raises(TypeError, match="v2"):
        await world.channel.send(view=view, shared_client_theme=theme)
    sent.send_message.assert_not_awaited()


async def test_route_payloads() -> None:
    http = HTTPClient()
    calls: list[dict[str, Any]] = []

    async def request(_route: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    theme = SharedClientTheme(colours=[1]).to_dict()
    await http.send_message(1, None, shared_client_theme=theme)
    await http.send_message(1, "x")
    await http.send_files(
        1, files=[File(BytesIO(b"x"), "x.txt")], shared_client_theme=theme
    )
    assert calls[0]["json"] == {"shared_client_theme": theme}
    assert "shared_client_theme" not in calls[1]["json"]
    form = calls[2]["form"]
    assert json.loads(form[0]["value"])["shared_client_theme"] == theme


COMPONENT_EMBED = {
    "type": "components",
    "components": [
        {
            "type": 17,
            "accent_color": 5793266,
            "components": [{"type": 10, "content": "# Patch Notes"}],
        }
    ],
}


def test_component_embed_is_received(world: World) -> None:
    payload = world.payload(t.message.Message, embeds=[COMPONENT_EMBED])
    message = discord.Message(state=world.state, channel=world.channel, data=payload)
    (embed,) = message.embeds
    assert embed.type == "components"
    (container,) = embed.components
    assert isinstance(container, Container)
    assert isinstance(container.components[0], TextDisplay)
    assert container.components[0].content == "# Patch Notes"
    assert bool(embed)
    assert embed.to_dict()["components"] == COMPONENT_EMBED["components"]
    (copied,) = embed.copy().components
    assert isinstance(copied, Container)
    assert copied.accent_color == Colour(5793266)


def test_rich_embed_has_no_components() -> None:
    embed = Embed(title="x")
    assert embed.components == []
    assert "components" not in embed.to_dict()


def test_component_embed_type_is_documented() -> None:
    assert "components" in t.embed.EmbedType.__args__  # type: ignore[attr-defined]
    assert "components" in t.embed.Embed.__annotations__
