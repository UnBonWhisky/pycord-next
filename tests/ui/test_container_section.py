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

from typing import Any

import pytest

import discord
from discord import ui
from discord.components import _component_factory


def btn(custom_id: str = "b", **kwargs: Any) -> ui.Button:
    return ui.Button(label="x", custom_id=custom_id, **kwargs)


class TestContainer:
    async def test_decorators_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="ActionRow"):

            class Bad(ui.Container):
                @ui.button(custom_id="x")
                async def x(self, b: Any, i: Any) -> None:
                    pass

    async def test_builders_and_len(self) -> None:
        c = (
            ui.Container(id=1, colour=0xFF0000, spoiler=True)
            .add_text("hello", id=2)
            .add_row(btn("a"), id=3)
            .add_section(ui.TextDisplay("s", id=5), accessory=btn("acc"), id=4)
            .add_gallery(discord.MediaGalleryItem("https://x.io/a.png"), id=6)
            .add_file("attachment://a.txt", spoiler=True, id=7)
            .add_separator(divider=False, id=8)
        )
        assert [type(i) for i in c.items] == [
            ui.TextDisplay,
            ui.ActionRow,
            ui.Section,
            ui.MediaGallery,
            ui.File,
            ui.Separator,
        ]
        assert len(c) == sum(len(i) for i in c.items) + 1
        assert c.copy_text() == "hello\ns"
        assert c.is_dispatchable()
        assert c.is_persistent() is True
        assert ui.Container(ui.ActionRow(ui.Button(label="x"))).is_persistent() is False
        payload = c.to_component_dict()
        assert payload["type"] == 17
        assert len(payload["components"]) == 6
        assert len(list(c.walk_items())) == 7

    async def test_add_item_positions(self) -> None:
        c = ui.Container(
            ui.TextDisplay("a", id=1),
            ui.Section(ui.TextDisplay("in", id=3), accessory=btn("acc"), id=2),
            ui.TextDisplay("b", id=4),
        )
        c.add_item(ui.TextDisplay("i", id=10), index=0)
        c.add_item(ui.TextDisplay("bf", id=11), before=4)
        c.add_item(ui.TextDisplay("af", id=12), after=1)
        assert [i.id for i in c.items] == [10, 1, 12, 2, 11, 4]
        c.add_item(ui.TextDisplay("nested", id=13), after=3)
        assert [i.id for i in c.get_item(2).items] == [3, 13]
        c.add_item(ui.TextDisplay("into", id=14), into=2)
        assert c.get_item(2).items[-1].id == 14
        c.add_item(ui.TextDisplay("self", id=15), into=c)
        assert c.items[-1].id == 15

    async def test_add_item_errors(self) -> None:
        c = ui.Container(ui.TextDisplay("a", id=1))
        with pytest.raises(ValueError, match="one of"):
            c.add_item(ui.TextDisplay("x"), index=0, after=1)
        with pytest.raises(TypeError, match="ViewItem"):
            c.add_item(object())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Could not find"):
            c.add_item(ui.TextDisplay("x"), before=99)
        c.get_item(1).parent = None
        with pytest.raises(ValueError, match="Could not find"):
            c.add_item(ui.TextDisplay("x"), before=1)

    async def test_remove_item(self) -> None:
        inner = ui.TextDisplay("in", id=3)
        c = ui.Container(
            ui.TextDisplay("a", id=1), ui.Section(inner, accessory=btn("acc"), id=2)
        )
        c.remove_item(1)
        c.remove_item("missing")
        c.remove_item(3)
        assert [i.id for i in c.items] == [2]
        assert inner.parent is None
        stray = ui.TextDisplay("stray")
        c.remove_item(stray)

    async def test_replace_item(self) -> None:
        inner = ui.TextDisplay("in", id=3)
        c = ui.Container(
            ui.TextDisplay("a", id=1), ui.Section(inner, accessory=btn("acc"), id=2)
        )
        new = ui.TextDisplay("new", id=20)
        c.replace_item(1, new)
        assert c.items[0] is new
        assert new.parent is c
        replacement = ui.TextDisplay("r", id=21)
        c.replace_item(3, replacement)
        assert c.get_item(2).items[0] is replacement
        with pytest.raises(TypeError, match="ViewItem"):
            c.replace_item(1, object())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="ActionRow"):
            c.replace_item(20, btn("z"))
        with pytest.raises(ValueError, match="Could not find"):
            c.replace_item(999, ui.TextDisplay("x"))
        new.parent = None
        with pytest.raises(ValueError, match="Could not find"):
            c.replace_item(new, ui.TextDisplay("x"))

    async def test_disable_enable(self) -> None:
        a, b = btn("a"), btn("b")
        c = ui.Container(ui.ActionRow(a, b))
        c.disable_all_items(exclusions=[b])
        assert a.disabled
        assert not b.disabled
        c.enable_all_items()
        assert not a.disabled
        c.disable_all_items()
        c.enable_all_items(exclusions=[a])
        assert a.disabled
        assert not b.disabled

    async def test_refresh_component(self) -> None:
        c = ui.Container(ui.TextDisplay("old", id=1))
        component = _component_factory(
            {
                "type": 17,
                "id": 9,
                "components": [{"type": 10, "id": 1, "content": "new"}],
            }
        )
        c.refresh_component(component)
        assert c.items[0].content == "new"
        assert c.underlying is component

    async def test_from_component_roundtrip(self) -> None:
        component = _component_factory(
            {
                "type": 17,
                "id": 9,
                "accent_color": 255,
                "spoiler": True,
                "components": [
                    {"type": 10, "id": 1, "content": "x"},
                    {"type": 14, "id": 2, "divider": True, "spacing": 1},
                ],
            }
        )
        c = ui.Container.from_component(component)
        assert [type(i) for i in c.items] == [ui.TextDisplay, ui.Separator]
        assert c.spoiler is True
        assert c.to_component_dict()["accent_color"] == 255


class TestSection:
    async def test_accessory_helpers(self) -> None:
        s = ui.Section(ui.TextDisplay("a", id=1), id=9)
        assert s.is_dispatchable() is False
        assert s.is_persistent() is True
        s.set_thumbnail("https://x.io/t.png", description="d", spoiler=True, id=2)
        assert isinstance(s.accessory, ui.Thumbnail)
        assert s.accessory.parent is s
        s.set_button(label="go", custom_id="go", id=3)
        assert isinstance(s.accessory, ui.Button)
        assert s.is_dispatchable()
        assert s.is_persistent() is True
        s.set_button(label="auto", id=4)
        assert s.is_persistent() is False
        with pytest.raises(TypeError, match="ViewItem"):
            s.set_accessory(object())  # type: ignore[arg-type]
        assert len(s) == 3

    async def test_decorated_accessory(self) -> None:
        class MySection(ui.Section):
            @ui.button(label="go", custom_id="go")
            async def go(self, button: Any, interaction: Any) -> None:
                pass

        s = MySection(ui.TextDisplay("t"))
        assert s.accessory is s.go
        assert s.accessory.parent is s

    async def test_text_limit_and_type_check(self) -> None:
        s = ui.Section(accessory=btn("a"))
        s.add_text("1").add_text("2").add_text("3")
        with pytest.raises(ValueError, match="maximum number"):
            s.add_text("4")
        with pytest.raises(ValueError, match="maximum number"):
            s.add_item(ui.TextDisplay("4"))
        s2 = ui.Section()
        with pytest.raises(TypeError, match="ViewItem"):
            s2.add_item(object())  # type: ignore[arg-type]

    async def test_add_item_positions(self) -> None:
        s = ui.Section(ui.TextDisplay("a", id=1), ui.TextDisplay("b", id=2))
        s.add_item(ui.TextDisplay("i", id=3), index=0)
        assert [i.id for i in s.items] == [3, 1, 2]
        with pytest.raises(ValueError, match="maximum"):
            s.add_item(ui.TextDisplay("x"), before=1)
        s.remove_item(3)
        s.add_item(ui.TextDisplay("bf", id=4), before=2)
        assert [i.id for i in s.items] == [1, 4, 2]
        with pytest.raises(ValueError, match="one of"):
            ui.Section().add_item(ui.TextDisplay("x"), index=0, before=1)

    async def test_remove_item(self) -> None:
        t = ui.TextDisplay("a", id=1)
        acc = btn("acc")
        s = ui.Section(t, accessory=acc)
        s.remove_item("missing")
        s.remove_item(acc)
        assert s.accessory is None
        assert acc.parent is None
        s.remove_item(1)
        assert s.items == []
        s.remove_item(ui.TextDisplay("not there"))

    async def test_replace_item(self) -> None:
        t = ui.TextDisplay("a", id=1)
        acc = btn("acc")
        s = ui.Section(t, accessory=acc)
        new = ui.TextDisplay("n", id=5)
        s.replace_item(1, new)
        assert s.items == [new]
        assert new.parent is s
        assert t.parent is None
        new_acc = btn("acc2")
        s.replace_item(acc, new_acc)
        assert s.accessory is new_acc
        with pytest.raises(TypeError):
            s.replace_item(5, object())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Could not find"):
            s.replace_item(404, ui.TextDisplay("x"))
        with pytest.raises(ValueError, match="Could not find"):
            s.replace_item(ui.TextDisplay("loose"), ui.TextDisplay("x"))

    async def test_disable_enable_and_walk(self) -> None:
        acc = btn("acc")
        s = ui.Section(ui.TextDisplay("a", id=1), accessory=acc)
        assert list(s.walk_items())[-1] is acc
        s.disable_all_items()
        assert acc.disabled
        s.enable_all_items(exclusions=[acc])
        assert acc.disabled
        s.enable_all_items()
        assert not acc.disabled
        s.disable_all_items(exclusions=[acc])
        assert not acc.disabled
        assert [i.id for i in ui.Section(ui.TextDisplay("a", id=1)).walk_items()] == [1]
        assert s.copy_text() == "a"

    async def test_refresh_and_roundtrip(self) -> None:
        s = ui.Section(ui.TextDisplay("old", id=1), accessory=btn("acc"), id=9)
        component = _component_factory(
            {
                "type": 9,
                "id": 9,
                "components": [{"type": 10, "id": 1, "content": "new"}],
                "accessory": {
                    "type": 2,
                    "style": 1,
                    "label": "fresh",
                    "custom_id": "acc",
                },
            }
        )
        s.refresh_component(component)
        assert s.items[0].content == "new"
        assert s.accessory.label == "fresh"
        built = ui.Section.from_component(component)
        assert built.accessory.custom_id == "acc"
        assert built.to_component_dict()["type"] == 9
