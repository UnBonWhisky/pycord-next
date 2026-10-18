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

from types import SimpleNamespace

import pytest

import discord
from discord import ui
from discord.components import _component_factory


def message_with(*payloads: dict) -> SimpleNamespace:
    return SimpleNamespace(
        components=[_component_factory(payload) for payload in payloads]
    )


TEXT = {"type": 10, "id": 1, "content": "hello"}
CONTAINER = {
    "type": 17,
    "id": 2,
    "components": [{"type": 10, "id": 3, "content": "inner"}],
}
ROW = {
    "type": 1,
    "id": 4,
    "components": [{"type": 2, "style": 2, "label": "go", "custom_id": "go"}],
}


class TestDesignerViewBuilders:
    async def test_add_helpers(self) -> None:
        view = (
            ui.DesignerView()
            .add_text("hello", id=1)
            .add_row(ui.Button(label="a", custom_id="a"), id=2)
            .add_container(ui.TextDisplay("in container", id=4), id=3)
            .add_section(
                ui.TextDisplay("in section"),
                accessory=ui.Button(label="b", custom_id="b"),
                id=5,
            )
            .add_gallery(discord.MediaGalleryItem("https://example.com/a.png"), id=6)
            .add_file("attachment://a.txt", spoiler=True, id=7)
            .add_separator(
                divider=False, spacing=discord.SeparatorSpacingSize.large, id=8
            )
        )
        kinds = [type(i) for i in view.children]
        assert kinds == [
            ui.TextDisplay,
            ui.ActionRow,
            ui.Container,
            ui.Section,
            ui.MediaGallery,
            ui.File,
            ui.Separator,
        ]
        assert [i.id for i in view.children] == [1, 2, 3, 5, 6, 7, 8]
        assert view.get_item(4).content == "in container"
        assert view.get_item(7).spoiler is True
        assert view.get_item(8).divider is False
        assert all(i.parent is view for i in view.children)

    async def test_helpers_respect_the_limit(self) -> None:
        view = ui.DesignerView()
        for n in range(40):
            view.add_text(str(n))
        with pytest.raises(ValueError, match="maximum number of children"):
            view.add_text("one too many")

    async def test_from_message_options(self) -> None:
        view = ui.DesignerView.from_message(
            message_with(TEXT, CONTAINER),
            timeout=12.0,
            disable_on_timeout=True,
            store=False,
        )
        assert isinstance(view, ui.DesignerView)
        assert view.timeout == 12.0
        assert view.disable_on_timeout is True
        assert view._store is False
        assert len(view) == 3

    async def test_from_dict_options(self) -> None:
        view = ui.DesignerView.from_dict(
            [TEXT, ROW], disable_on_timeout=True, store=False
        )
        assert view.disable_on_timeout is True
        assert view._store is False
        assert [type(i) for i in view.children] == [ui.TextDisplay, ui.ActionRow]

    async def test_legacy_view_options(self) -> None:
        message = message_with(ROW)
        view = ui.View.from_message(message, disable_on_timeout=True, store=False)
        assert view.disable_on_timeout is True
        assert view._store is False
        assert len(view.children) == 1
        view = ui.View.from_dict([ROW], disable_on_timeout=True, store=False)
        assert view.disable_on_timeout is True
        assert view._store is False

    async def test_options_are_keyword_only(self) -> None:
        with pytest.raises(TypeError):
            ui.DesignerView.from_dict([TEXT], 180.0, True)

    async def test_base_view_from_message_builds_the_class(self) -> None:
        class Custom(ui.BaseView):
            MAX_ITEMS = 40

        view = Custom.from_message(message_with(TEXT), disable_on_timeout=True)
        assert type(view) is Custom
        assert view.disable_on_timeout is True
        assert len(view.children) == 1


class TestViewLen:
    async def test_legacy_view_len_and_limit(self) -> None:
        view = ui.View()
        for n in range(25):
            view.add_item(ui.Button(label=str(n), custom_id=str(n)))
        assert len(view) == 25
        with pytest.raises(ValueError, match="maximum number of children"):
            view.add_item(ui.Button(label="x", custom_id="x"))

    async def test_empty_view_is_truthy(self) -> None:
        assert ui.View()
        assert ui.DesignerView()
        assert len(ui.DesignerView()) == 0
