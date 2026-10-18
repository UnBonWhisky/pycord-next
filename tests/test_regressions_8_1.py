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

import importlib.util
import inspect
from typing import Any, cast
from unittest.mock import MagicMock

import discord
import discord.gateway
import discord.opus
import discord.utils
from discord.ext import pages, tasks


def test_top_level_missing_and_ws_response() -> None:
    assert discord.MISSING is discord.utils.MISSING
    assert (
        discord.DiscordClientWebSocketResponse
        is discord.gateway.DiscordClientWebSocketResponse
    )


def test_opus_has_davey() -> None:
    assert discord.opus.HAS_DAVEY is (importlib.util.find_spec("davey") is not None)


def test_sleep_handle_recalculate_param_name() -> None:
    params = list(inspect.signature(tasks.SleepHandle.recalculate).parameters)
    assert params == ["self", "dt"]


def test_button_component_param_names() -> None:
    for cls in (discord.ui.Button, pages.PaginatorButton):
        assert list(inspect.signature(cls.from_component).parameters) == ["button"]
        assert list(inspect.signature(cls.refresh_component).parameters) == [
            "self",
            "button",
        ]


def test_button_from_component_roundtrip() -> None:
    component = discord.components.Button(
        cast(
            "Any",
            {"type": 2, "style": 1, "label": "x", "custom_id": "cid"},
        )
    )
    item = discord.ui.Button.from_component(component)
    assert item.label == "x"
    assert item.custom_id == "cid"
    other = discord.components.Button(
        cast(
            "Any",
            {"type": 2, "style": 1, "label": "y", "custom_id": "cid"},
        )
    )
    item.refresh_component(other)
    assert item.underlying is other


def _text_channel(extra: dict[str, Any]) -> discord.TextChannel:
    guild = MagicMock()
    guild.id = 1
    state = MagicMock()
    data: dict[str, Any] = {
        "id": "2",
        "type": 0,
        "name": "general",
        "position": 0,
    } | extra
    return discord.TextChannel(state=state, guild=guild, data=cast("Any", data))


def test_text_channel_default_reaction_emoji() -> None:
    assert _text_channel({}).default_reaction_emoji is None
    assert (
        _text_channel(
            {"default_reaction_emoji": {"emoji_name": "x", "emoji_id": None}}
        ).default_reaction_emoji
        == "x"
    )
