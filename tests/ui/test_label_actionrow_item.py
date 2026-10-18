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
# ruff: noqa: PT030

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord import ui
from discord.components import _component_factory
from discord.enums import ComponentType


def field(custom_id: str = "f") -> ui.InputText:
    return ui.InputText(label=None, custom_id=custom_id)


class TestLabel:
    async def test_set_item_and_len(self) -> None:
        label = ui.Label("L")
        assert len(label) == 1
        assert label.get_item("f") is None
        assert list(label.walk_items()) == []
        assert label.is_dispatchable() is False
        assert label.is_persistent() is True
        f = field()
        label.set_item(f)
        assert len(label) == 2
        assert f.parent is label
        assert label.get_item("f") is f
        assert label.get_item(id=999) is None
        assert list(label.walk_items()) == [f]
        assert label.is_dispatchable() is False
        select = ui.Select(options=[discord.SelectOption(label="o")], custom_id="s")
        assert ui.Label("S", select).is_dispatchable() is True
        with pytest.raises(TypeError, match="ModalItem"):
            label.set_item(object())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="cannot be set inside Label"):
            label.set_item(ui.InputText(label="no", custom_id="x"))

    async def test_modal_is_propagated(self) -> None:
        modal = ui.DesignerModal(title="t")
        label = ui.Label("L", field("a"))
        label.modal = modal
        assert label.modal is modal
        assert label.item.modal is modal
        other = field("b")
        label.set_item(other)
        assert other.modal is modal

    async def test_builders(self) -> None:
        label = ui.Label("L").set_input_text(custom_id="a", value="v", id=1)
        assert isinstance(label.item, ui.InputText)
        assert label.item.value == "v"
        label.set_select(custom_id="s", options=[discord.SelectOption(label="o")])
        assert isinstance(label.item, ui.Select)
        label.set_select(ComponentType.user_select, custom_id="u")
        assert label.item.type is ComponentType.user_select
        label.set_file_upload(custom_id="up", min_values=1, max_values=2)
        assert isinstance(label.item, ui.FileUpload)
        label.set_radio_group(
            custom_id="r",
            options=[
                discord.RadioGroupOption(label="a", value="a"),
                discord.RadioGroupOption(label="b", value="b"),
            ],
        )
        assert isinstance(label.item, ui.RadioGroup)
        label.set_checkbox_group(
            custom_id="cg",
            options=[
                discord.CheckboxGroupOption(label="a", value="a"),
                discord.CheckboxGroupOption(label="b", value="b"),
            ],
        )
        assert isinstance(label.item, ui.CheckboxGroup)
        label.set_checkbox(custom_id="c", default=True)
        assert isinstance(label.item, ui.Checkbox)
        payload = label.to_component_dict()
        assert payload["type"] == 18
        assert payload["component"]["custom_id"] == "c"

    async def test_refresh_and_modal_refresh(self) -> None:
        label = ui.Label("L", field("t"))
        component = _component_factory(
            {
                "type": 18,
                "id": 3,
                "label": "L",
                "component": {"type": 4, "custom_id": "t", "style": 1, "value": "new"},
            }
        )
        label.refresh_component(component)
        assert label.underlying is component
        label.refresh_from_modal(
            None, {"component": {"custom_id": "t", "value": "typed"}}
        )  # type: ignore[arg-type]
        assert label.item.value == "typed"
        ui.Label("empty").refresh_from_modal(None, {})  # type: ignore[arg-type]
        ui.Label("empty").refresh_component(component)

    async def test_from_component(self) -> None:
        component = _component_factory(
            {
                "type": 18,
                "id": 3,
                "label": "L",
                "description": "d",
                "component": {"type": 4, "custom_id": "t", "style": 1},
            }
        )
        label = ui.Label.from_component(component)
        assert label.description == "d"
        assert label.item.custom_id == "t"


class TestActionRow:
    async def test_validation(self) -> None:
        row = ui.ActionRow()
        with pytest.raises(TypeError, match="Select or Button"):
            row.add_item(ui.TextDisplay("x"))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="row is not supported"):
            row.add_item(ui.Button(label="x", custom_id="x", row=1))
        for i in range(5):
            row.add_button(label=str(i), custom_id=f"b{i}")
        with pytest.raises(ValueError, match="Not enough space"):
            row.add_button(label="x", custom_id="x")
        assert len(row) == 6
        assert row.items is row.children
        row.items = []
        assert row.children == []

    async def test_positions_remove_replace(self) -> None:
        row = ui.ActionRow(
            ui.Button(label="a", custom_id="a", id=1),
            ui.Button(label="b", custom_id="b", id=2),
        )
        row.add_item(ui.Button(label="i", custom_id="i", id=3), index=0)
        row.add_item(ui.Button(label="bf", custom_id="bf", id=4), before=2)
        row.add_item(ui.Button(label="af", custom_id="af", id=5), after=1)
        assert [c.id for c in row.children] == [3, 1, 5, 4, 2]
        row.remove_item(3)
        row.remove_item("missing")
        row.remove_item(row.children[0])
        row.remove_item(ui.Button(label="stray", custom_id="stray"))
        assert [c.id for c in row.children] == [5, 4, 2]
        new = ui.Button(label="n", custom_id="n", id=9)
        row.replace_item(5, new)
        assert row.children[0] is new
        assert new.parent is row
        with pytest.raises(ValueError, match="Could not find"):
            row.replace_item("nope", new)
        with pytest.raises(ValueError, match="Could not find"):
            row.replace_item(ui.Button(label="s", custom_id="s"), new)

    async def test_add_select_variants(self) -> None:
        row = ui.ActionRow()
        row.add_select(options=[discord.SelectOption(label="a")], custom_id="s")
        assert isinstance(row.children[0], ui.Select)
        assert row.width == 5
        assert row.is_dispatchable()
        assert row.is_persistent() is True

    async def test_disable_enable(self) -> None:
        a, b = ui.Button(label="a", custom_id="a"), ui.Button(label="b", custom_id="b")
        row = ui.ActionRow(a, b)
        row.disable_all_items(exclusions=[b])
        assert a.disabled
        assert not b.disabled
        row.enable_all_items()
        assert not a.disabled
        row.disable_all_items()
        row.enable_all_items(exclusions=[a])
        assert a.disabled
        assert not b.disabled
        assert list(row.walk_items()) == [a, b]

    async def test_refresh_component_and_roundtrip(self) -> None:
        row = ui.ActionRow(ui.Button(label="old", custom_id="a"), id=4)
        component = _component_factory(
            {
                "type": 1,
                "id": 4,
                "components": [
                    {"type": 2, "style": 1, "label": "new", "custom_id": "a"}
                ],
            }
        )
        row.refresh_component(component)
        assert row.children[0].label == "new"
        built = ui.ActionRow.from_component(component)
        assert built.children[0].custom_id == "a"
        assert built.to_component_dict()["type"] == 1

    async def test_decorated_children(self) -> None:
        class MyRow(ui.ActionRow):
            @ui.button(label="go", custom_id="go")
            async def go(self, button: Any, interaction: Any) -> None:
                pass

        row = MyRow(ui.Button(label="extra", custom_id="extra"))
        assert row.go is row.children[0]
        assert row.go.parent is row


class TestItemBase:
    async def test_defaults(self) -> None:
        item = ui.Item()
        assert len(item) == 1
        assert bool(item) is True
        assert item.is_dispatchable() is False
        assert item.is_storable() is False
        assert item.is_persistent() is True
        assert item.copy_text() == ""
        assert item.id is None
        item.id = 5
        with pytest.raises(NotImplementedError):
            item.to_component_dict()
        with pytest.raises(NotImplementedError):
            _ = item.type
        assert repr(item).startswith("<Item")

    async def test_view_item_row_and_view(self) -> None:
        text = ui.TextDisplay("x")
        with pytest.warns(DeprecationWarning):
            assert text.row is None
        with pytest.warns(DeprecationWarning):
            text.row = 1
        assert text.width == 1
        assert text.view is None
        view = ui.DesignerView(text)
        assert text.view is view
        container = ui.Container(ui.TextDisplay("in", id=7))
        view.add_item(container)
        assert container.get_item(7).view is view
        with pytest.warns(DeprecationWarning):
            text.view = view
        assert text.view is view

    async def test_modal_item_attach(self) -> None:
        modal = ui.Modal(title="t")
        f = ui.InputText(label="L", custom_id="f")
        assert f.modal is None
        f.modal = modal
        assert f.modal is modal
        assert f.refresh_from_modal(SimpleNamespace(), {"value": "x"}) is None

    async def test_generate_underlying_copies(self) -> None:
        text = ui.TextDisplay("x", id=2)
        copy = text._generate_underlying()
        assert copy is not text.underlying
        assert copy.content == "x"
