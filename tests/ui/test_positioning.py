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

import pytest

from discord import ui


def text(content: str, id: int) -> ui.TextDisplay:
    return ui.TextDisplay(content, id=id)


def button(custom_id: str, id: int | None = None) -> ui.Button:
    return ui.Button(label=custom_id, custom_id=custom_id, id=id)


def ids(items) -> list[int]:
    return [i.id for i in items]


class TestItemGetter:
    async def test_by_id_and_custom_id(self) -> None:
        row = ui.ActionRow(button("a", 1), button("b", 2))
        view = ui.DesignerView(row)
        assert view.get_item(2).custom_id == "b"
        assert view.get_item("a").id == 1
        assert view.get_item(99) is None
        assert view.get_item("zzz") is None

    async def test_falsy_arguments_match_nothing(self) -> None:
        view = ui.DesignerView(text("x", 1))
        assert view.get_item() is None
        assert view.get_item(0) is None
        assert view.get_item("") is None

    async def test_attribute_matching_is_a_logical_and(self) -> None:
        a = ui.Button(label="Go", custom_id="a", style=discord_style("danger"))
        b = ui.Button(label="Go", custom_id="b", style=discord_style("secondary"))
        view = ui.DesignerView(ui.ActionRow(a, b))
        assert view.get_item(label="Go", style=discord_style("secondary")) is b
        assert view.get_item(label="Go", custom_id="nope") is None

    async def test_nested_attribute_search(self) -> None:
        container = ui.Container(
            ui.Section(text("t", 1), accessory=ui.Button(label="x", custom_id="x"))
        )
        view = ui.DesignerView(container)
        found = view.get_item(underlying__custom_id="x")
        assert found is not None
        assert found.custom_id == "x"

    async def test_recursion_into_every_container_kind(self) -> None:
        thumb = ui.Thumbnail("https://example.com/a.png", id=7)
        section = ui.Section(text("in section", 1), accessory=thumb, id=2)
        container = ui.Container(section, id=3)
        view = ui.DesignerView(container)
        assert view.get_item(7) is thumb
        assert container.get_item(7) is thumb
        assert section.get_item(7) is thumb
        assert section.get_item(1).content == "in section"

    async def test_label_get_item_accepts_attrs(self) -> None:
        item = ui.InputText(label=None, custom_id="field")
        label = ui.Label("Name", item)
        assert label.get_item("field") is item
        assert label.get_item(custom_id="field") is item
        assert label.get_item(custom_id="other") is None
        assert ui.Label("Empty").get_item("field") is None

    async def test_modal_get_item_finds_items_in_labels(self) -> None:
        item = ui.InputText(label=None, custom_id="field")
        modal = ui.DesignerModal(ui.Label("Name", item), title="t")
        assert modal.get_item("field") is item
        assert modal.get_item(custom_id="field") is item


def discord_style(name: str):
    import discord

    return getattr(discord.ButtonStyle, name)


class TestLen:
    async def test_every_item_counts_one(self) -> None:
        assert len(text("x", 1)) == 1
        assert len(button("a")) == 1
        assert len(ui.Separator()) == 1

    async def test_items_are_always_truthy(self) -> None:
        assert ui.ActionRow()
        assert ui.Container()
        assert ui.Section(accessory=button("a"))
        assert ui.DesignerView()
        assert ui.DesignerModal(title="t")

    async def test_action_row(self) -> None:
        assert len(ui.ActionRow(button("a"), button("b"))) == 3

    async def test_section(self) -> None:
        assert len(ui.Section(text("x", 1), accessory=button("a"))) == 3
        assert len(ui.Section(text("x", 1))) == 2

    async def test_container_counts_nested_items(self) -> None:
        container = ui.Container(
            text("x", 1),
            ui.Section(text("y", 2), accessory=button("a")),
            ui.ActionRow(button("b"), button("c")),
        )
        assert len(container) == 1 + 1 + 3 + 3

    async def test_view_counts_everything(self) -> None:
        view = ui.DesignerView(
            text("x", 1), ui.Container(text("y", 2), ui.ActionRow(button("a")))
        )
        assert len(view) == 1 + (1 + 1 + 2)

    async def test_label(self) -> None:
        assert len(ui.Label("x", ui.InputText(label=None))) == 2
        assert len(ui.Label("x")) == 1


class TestActionRow:
    async def test_index(self) -> None:
        row = ui.ActionRow(button("a", 1), button("b", 2))
        row.add_item(button("c", 3), index=1)
        assert ids(row.children) == [1, 3, 2]
        assert [c.id for c in row.underlying.children] == [1, 3, 2]

    async def test_before_and_after(self) -> None:
        row = ui.ActionRow(button("a", 1), button("b", 2))
        row.add_item(button("c", 3), before=2)
        row.add_item(button("d", 4), after="a")
        assert ids(row.children) == [1, 4, 3, 2]

    async def test_reference_by_item(self) -> None:
        first = button("a", 1)
        row = ui.ActionRow(first, button("b", 2))
        row.add_item(button("c", 3), before=first)
        assert ids(row.children) == [3, 1, 2]

    async def test_only_one_position(self) -> None:
        row = ui.ActionRow(button("a", 1))
        with pytest.raises(ValueError, match="one of before, after, and index"):
            row.add_item(button("b", 2), index=0, before=1)

    async def test_missing_reference(self) -> None:
        row = ui.ActionRow(button("a", 1))
        with pytest.raises(ValueError, match="Could not find"):
            row.add_item(button("b", 2), after=42)
        assert ids(row.children) == [1]

    async def test_width_is_still_enforced(self) -> None:
        row = ui.ActionRow(*(button(str(n), n + 1) for n in range(5)))
        with pytest.raises(ValueError, match="Not enough space"):
            row.add_item(button("x", 99), index=0)

    async def test_replace_item(self) -> None:
        old = button("a", 1)
        row = ui.ActionRow(old, button("b", 2))
        new = button("c", 3)
        row.replace_item("a", new)
        assert ids(row.children) == [3, 2]
        assert new.parent is row
        assert old.parent is None
        assert row.underlying.children[0].custom_id == "c"

    async def test_replace_item_errors(self) -> None:
        row = ui.ActionRow(button("a", 1))
        with pytest.raises(ValueError, match="Could not find"):
            row.replace_item("missing", button("c", 3))
        with pytest.raises(TypeError):
            row.replace_item(1, text("x", 5))

    async def test_remove_missing_item_is_a_noop(self) -> None:
        row = ui.ActionRow(button("a", 1))
        assert row.remove_item("missing") is row
        assert row.remove_item(404) is row
        assert ids(row.children) == [1]


class TestSection:
    async def test_index_before_after(self) -> None:
        section = ui.Section(text("a", 1), accessory=button("x"))
        section.add_item(text("b", 2), index=0)
        section.add_item(text("c", 3), after=2)
        assert ids(section.items) == [2, 3, 1]
        assert [c.id for c in section.underlying.components] == [2, 3, 1]

    async def test_limit_is_checked_before_position(self) -> None:
        section = ui.Section(
            text("a", 1), text("b", 2), text("c", 3), accessory=button("x")
        )
        with pytest.raises(ValueError, match=r"\(3\)"):
            section.add_item(text("d", 4), index=0)

    async def test_replace_item_and_accessory(self) -> None:
        old = button("x")
        section = ui.Section(text("a", 1), accessory=old)
        section.replace_item(1, text("z", 5))
        assert ids(section.items) == [5]
        new_accessory = ui.Thumbnail("https://example.com/a.png", id=8)
        section.replace_item(old, new_accessory)
        assert section.accessory is new_accessory
        assert new_accessory.parent is section
        assert old.parent is None

    async def test_get_item_searches_the_accessory(self) -> None:
        accessory = button("x", 6)
        section = ui.Section(text("a", 1), accessory=accessory)
        assert section.get_item("x") is accessory
        assert section.get_item(6) is accessory
        assert section.get_item(label="x") is accessory

    async def test_set_button(self) -> None:
        section = ui.Section(text("a", 1))
        section.set_button(label="Hi", custom_id="hi", id=9)
        assert isinstance(section.accessory, ui.Button)
        assert section.accessory.custom_id == "hi"
        assert section.accessory.parent is section
        assert section.underlying.accessory.custom_id == "hi"

    async def test_remove_missing_item_is_a_noop(self) -> None:
        section = ui.Section(text("a", 1), accessory=button("x"))
        assert section.remove_item("missing") is section


class TestContainer:
    async def test_index_before_after(self) -> None:
        container = ui.Container(text("a", 1), text("b", 2))
        container.add_item(text("c", 3), before=2)
        container.add_item(text("d", 4), after=2)
        container.add_item(text("e", 5), index=0)
        assert ids(container.items) == [5, 1, 3, 2, 4]

    async def test_before_a_nested_item_goes_into_its_parent(self) -> None:
        section = ui.Section(text("a", 1), accessory=button("x"), id=10)
        container = ui.Container(section, text("b", 2))
        container.add_item(text("c", 3), before=1)
        assert ids(section.items) == [3, 1]
        assert ids(container.items) == [10, 2]

    async def test_nested_target_still_validates_the_parent(self) -> None:
        row = ui.ActionRow(button("a", 1), id=10)
        container = ui.Container(row)
        with pytest.raises(TypeError):
            container.add_item(text("c", 3), before=1)

    async def test_into(self) -> None:
        row = ui.ActionRow(button("a", 1), id=10)
        container = ui.Container(row)
        container.add_item(button("b", 2), into=10)
        container.add_item(button("c", 3), into=row, index=0)
        assert ids(row.children) == [3, 1, 2]

    async def test_into_missing(self) -> None:
        container = ui.Container(text("a", 1))
        with pytest.raises(ValueError, match="Could not find"):
            container.add_item(text("b", 2), into=77)

    async def test_buttons_cannot_be_added_directly(self) -> None:
        container = ui.Container(text("a", 1))
        with pytest.raises(TypeError, match="ActionRow"):
            container.add_item(button("b", 2), index=0)

    async def test_replace_nested_item(self) -> None:
        section = ui.Section(text("a", 1), accessory=button("x"), id=10)
        container = ui.Container(section)
        container.replace_item(1, text("z", 4))
        assert ids(section.items) == [4]
        container.replace_item(10, text("top", 11))
        assert ids(container.items) == [11]

    async def test_replace_missing(self) -> None:
        container = ui.Container(text("a", 1))
        with pytest.raises(ValueError, match="Could not find"):
            container.replace_item(99, text("z", 4))

    async def test_remove_missing_item_is_a_noop(self) -> None:
        container = ui.Container(text("a", 1))
        assert container.remove_item("missing") is container
        assert ids(container.items) == [1]


class TestDesignerView:
    async def test_index_before_after(self) -> None:
        view = ui.DesignerView(text("a", 1), text("b", 2))
        view.add_item(text("c", 3), index=1)
        view.add_item(text("d", 4), after=2)
        view.add_item(text("e", 5), before=1)
        assert ids(view.children) == [5, 1, 3, 2, 4]

    async def test_before_a_nested_item(self) -> None:
        container = ui.Container(text("a", 1), id=10)
        view = ui.DesignerView(container)
        view.add_item(text("b", 2), before=1)
        view.add_item(text("c", 3), after=1)
        assert ids(container.items) == [2, 1, 3]
        assert ids(view.children) == [10]

    async def test_into(self) -> None:
        container = ui.Container(id=10)
        view = ui.DesignerView(container)
        view.add_item(text("a", 1), into=10)
        view.add_item(text("b", 2), into=container, index=0)
        assert ids(container.items) == [2, 1]
        assert view.children == [container]

    async def test_into_with_before(self) -> None:
        container = ui.Container(text("a", 1), id=10)
        view = ui.DesignerView(container)
        view.add_item(text("b", 2), into=10, before=1)
        assert ids(container.items) == [2, 1]

    async def test_only_one_position(self) -> None:
        view = ui.DesignerView(text("a", 1))
        with pytest.raises(ValueError, match="one of before, after, and index"):
            view.add_item(text("b", 2), before=1, after=1)

    async def test_buttons_cannot_be_added_directly(self) -> None:
        view = ui.DesignerView()
        with pytest.raises(ValueError, match="ActionRow"):
            view.add_item(button("a"))

    async def test_button_before_a_button_goes_into_its_row(self) -> None:
        view = ui.DesignerView(ui.ActionRow(button("a", 1), id=10))
        view.add_item(button("b", 2), before=1)
        assert ids(view.get_item(10).children) == [2, 1]

    async def test_non_items_are_rejected(self) -> None:
        view = ui.DesignerView()
        with pytest.raises(TypeError):
            view.add_item("nope")

    async def test_limit_counts_nested_items(self) -> None:
        view = ui.DesignerView()
        for n in range(13):
            view.add_item(ui.Container(ui.ActionRow(button(f"b{n}"))))
        assert len(view) == 39
        with pytest.raises(ValueError, match="maximum number of children"):
            view.add_item(ui.Container(ui.ActionRow(button("last"))))
        assert len(view) == 39
        view.add_item(text("fits", 1))
        assert len(view) == 40
        with pytest.raises(ValueError, match="maximum number of children"):
            view.add_item(text("one too many", 2))

    async def test_replace_item(self) -> None:
        container = ui.Container(text("a", 1), id=10)
        view = ui.DesignerView(container, text("b", 2))
        view.replace_item(2, text("c", 3))
        assert ids(view.children) == [10, 3]
        view.replace_item(1, text("d", 4))
        assert ids(container.items) == [4]
        view.replace_item(container, text("e", 5))
        assert ids(view.children) == [5, 3]

    async def test_replace_item_errors(self) -> None:
        view = ui.DesignerView(text("a", 1))
        with pytest.raises(ValueError, match="Could not find"):
            view.replace_item(99, text("b", 2))
        with pytest.raises(TypeError):
            view.replace_item(1, "nope")
        with pytest.raises(ValueError, match="ActionRow"):
            view.replace_item(1, button("a"))

    async def test_remove_missing_item_is_a_noop(self) -> None:
        view = ui.DesignerView(text("a", 1))
        assert view.remove_item("missing") is view
        assert view.remove_item(404) is view
        assert ids(view.children) == [1]


class TestMediaGallery:
    async def test_replace_item(self) -> None:
        import discord

        gallery = ui.MediaGallery(
            discord.MediaGalleryItem("https://example.com/a.png"),
            discord.MediaGalleryItem("https://example.com/b.png"),
        )
        gallery.replace_item(1, discord.MediaGalleryItem("https://example.com/c.png"))
        assert [i.url for i in gallery.items] == [
            "https://example.com/a.png",
            "https://example.com/c.png",
        ]
        with pytest.raises(IndexError):
            gallery.replace_item(
                5, discord.MediaGalleryItem("https://example.com/d.png")
            )
        with pytest.raises(TypeError):
            gallery.replace_item(0, "nope")
