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

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord import ui
from discord.components import _component_factory
from discord.enums import ChannelType
from discord.errors import NotFound
from discord.ui.view import (
    ViewStore,
    _component_to_item,
    _ViewWeights,
    _walk_all_components,
)


class FakeClient:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def dispatch(self, *args: Any) -> None:
        self.events.append(args)


def fake_interaction(message_id: int | None = None) -> Any:
    message = SimpleNamespace(id=message_id) if message_id is not None else None
    return SimpleNamespace(client=FakeClient(), message=message, view=None, data={})


def btn(custom_id: str = "b", **kwargs: Any) -> ui.Button:
    return ui.Button(label="x", custom_id=custom_id, **kwargs)


def sel(custom_id: str = "s") -> ui.Select:
    return ui.Select(
        custom_id=custom_id, options=[discord.SelectOption(label="a", value="a")]
    )


PAYLOADS: dict[str, dict[str, Any]] = {
    "button": {"type": 2, "style": 1, "label": "go", "custom_id": "go"},
    "select": {
        "type": 3,
        "custom_id": "s",
        "options": [{"label": "a", "value": "a"}],
    },
    "text": {"type": 10, "id": 1, "content": "hi"},
    "section": {
        "type": 9,
        "id": 2,
        "components": [{"type": 10, "id": 3, "content": "in"}],
        "accessory": {"type": 2, "style": 1, "label": "go", "custom_id": "acc"},
    },
    "thumbnail": {"type": 11, "id": 4, "media": {"url": "https://x.io/a.png"}},
    "gallery": {
        "type": 12,
        "id": 5,
        "items": [{"media": {"url": "https://x.io/a.png"}}],
    },
    "file": {"type": 13, "id": 6, "file": {"url": "attachment://a.txt"}},
    "separator": {"type": 14, "id": 7, "divider": True, "spacing": 1},
    "container": {
        "type": 17,
        "id": 8,
        "components": [{"type": 10, "id": 9, "content": "in"}],
    },
    "row": {
        "type": 1,
        "id": 10,
        "components": [{"type": 2, "style": 2, "label": "go", "custom_id": "r"}],
    },
    "label": {
        "type": 18,
        "id": 11,
        "label": "L",
        "component": {"type": 4, "custom_id": "t", "style": 1},
    },
    "input": {"type": 4, "custom_id": "t2", "style": 1, "label": "L"},
    "file_upload": {"type": 19, "id": 12, "custom_id": "fu"},
    "radio": {
        "type": 21,
        "id": 13,
        "custom_id": "rg",
        "options": [
            {"label": "a", "value": "a"},
            {"label": "b", "value": "b"},
        ],
    },
    "checkbox_group": {
        "type": 22,
        "id": 14,
        "custom_id": "cg",
        "options": [
            {"label": "a", "value": "a"},
            {"label": "b", "value": "b"},
        ],
    },
    "checkbox": {"type": 23, "id": 15, "custom_id": "cb"},
}

EXPECTED = {
    "button": ui.Button,
    "select": ui.Select,
    "text": ui.TextDisplay,
    "section": ui.Section,
    "thumbnail": ui.Thumbnail,
    "gallery": ui.MediaGallery,
    "file": ui.File,
    "separator": ui.Separator,
    "container": ui.Container,
    "row": ui.ActionRow,
    "label": ui.Label,
    "input": ui.InputText,
    "file_upload": ui.FileUpload,
    "radio": ui.RadioGroup,
    "checkbox_group": ui.CheckboxGroup,
    "checkbox": ui.Checkbox,
}


@pytest.mark.parametrize("name", list(PAYLOADS))
async def test_component_to_item(name: str) -> None:
    component = _component_factory(PAYLOADS[name])
    item = _component_to_item(component)
    assert isinstance(item, EXPECTED[name])


async def test_component_to_item_unknown_type_falls_back_to_item() -> None:
    item = _component_to_item(SimpleNamespace(id=3))
    assert type(item) is ui.Item


def test_walk_all_components_flattens_rows() -> None:
    comps = [_component_factory(PAYLOADS["row"]), _component_factory(PAYLOADS["text"])]
    walked = list(_walk_all_components(comps))
    assert [type(c).__name__ for c in walked] == ["Button", "TextDisplay"]


class TestViewWeights:
    async def test_open_space_and_rows(self) -> None:
        weights = _ViewWeights([btn("a"), btn("b")])
        assert weights.weights[0] == 2
        full = _ViewWeights([sel("a")])
        assert full.weights[0] == 5
        item = btn("c", row=1)
        weights.add_item(item)
        assert item._rendered_row == 1
        with pytest.raises(ValueError, match="would not fit at row 0"):
            weights.add_item(
                ui.Select(
                    custom_id="z",
                    row=0,
                    options=[discord.SelectOption(label="a", value="a")],
                )
            )
        weights.remove_item(item)
        weights.remove_item(item)
        weights.clear()
        assert weights.weights == [0] * 5

    async def test_no_open_space(self) -> None:
        weights = _ViewWeights([sel(str(i)) for i in range(5)])
        with pytest.raises(ValueError, match="open space"):
            weights.find_open_space(btn("late"))


class TestLegacyView:
    async def test_decorated_items_and_to_components(self) -> None:
        class MyView(ui.View):
            @ui.button(label="one", custom_id="one")
            async def one(self, button: Any, interaction: Any) -> None:
                pass

            @ui.select(custom_id="pick", options=[discord.SelectOption(label="a")])
            async def pick(self, select: Any, interaction: Any) -> None:
                pass

        view = MyView(btn("extra"))
        assert [c.custom_id for c in view.children] == ["one", "pick", "extra"]
        rows = view.to_components()
        assert [len(r["components"]) for r in rows] == [1, 1, 1]
        assert view.is_components_v2() is False

    async def test_too_many_decorated_children(self) -> None:
        namespace: dict[str, Any] = {}
        for i in range(41):

            async def cb(self: Any, b: Any, i_: Any) -> None:
                pass

            namespace[f"cb{i}"] = ui.button(custom_id=f"c{i}")(cb)
        with pytest.raises(TypeError, match="cannot have more than"):
            type("Big", (ui.View,), namespace)

    async def test_add_remove_clear(self) -> None:
        view = ui.View()
        with pytest.raises(ValueError, match="V2"):
            view.add_item(ui.TextDisplay("x"))  # type: ignore[arg-type]
        row = ui.ActionRow(btn("a"), btn("b"))
        view.add_item(row)
        assert [c.custom_id for c in view.children] == ["a", "b"]
        view.remove_item("a")
        view.remove_item("missing")
        view.remove_item(view.children[0])
        assert view.children == []
        view.add_item(btn("c"))
        view.clear_items()
        assert view.children == []
        assert view._View__weights.weights == [0] * 5

    async def test_overflow(self) -> None:
        view = ui.View()
        for i in range(25):
            view.add_item(btn(str(i)))
        with pytest.raises(ValueError, match="maximum number of children"):
            view.add_item(btn("one more"))
        with pytest.raises(TypeError, match="ViewItem"):
            ui.View().add_item(object())  # type: ignore[arg-type]

    async def test_from_message_and_dict(self) -> None:
        message = SimpleNamespace(components=[_component_factory(PAYLOADS["row"])])
        view = ui.View.from_message(message, timeout=5)
        assert view.timeout == 5
        assert view.children[0].custom_id == "r"
        view = ui.View.from_dict([PAYLOADS["row"]])
        assert view.children[0].custom_id == "r"

    async def test_refresh_replaces_dispatchable_state(self) -> None:
        view = ui.View(btn("keep"), btn("gone"))
        row = {
            "type": 1,
            "components": [
                {"type": 2, "style": 1, "label": "new", "custom_id": "keep"},
                {"type": 2, "style": 1, "label": "added", "custom_id": "added"},
                {"type": 2, "style": 5, "label": "link", "url": "https://x.io"},
            ],
        }
        original = view.children[0]
        view._refresh([_component_factory(row)])
        assert [c.custom_id for c in view.children] == ["keep", "added"]
        assert view.children[0] is original
        assert original.label == "new"


class TestBaseViewNesting:
    async def test_add_item_checks(self) -> None:
        class Small(ui.BaseView):
            MAX_ITEMS = 1

        view = Small(ui.TextDisplay("a"))
        with pytest.raises(ValueError, match="maximum number"):
            view.add_item(ui.TextDisplay("b"))
        with pytest.raises(ValueError, match="maximum number"):
            view.add_item(object())  # type: ignore[arg-type]
        loose = Small()
        with pytest.raises(TypeError, match="ViewItem"):
            loose.add_item(object())  # type: ignore[arg-type]

    async def test_remove_nested_item_and_enable_recursion(self) -> None:
        inner = ui.TextDisplay("in", id=2)
        container = ui.Container(inner, id=1)
        view = ui.DesignerView(container)
        view.remove_item(inner)
        assert container.items == []
        view.remove_item(ui.TextDisplay("floating"))
        b = btn("a", disabled=True)
        nested = ui.DesignerView(ui.Container(ui.ActionRow(b)))
        nested.enable_all_items()
        assert not b.disabled


class TestBaseViewBehaviour:
    async def test_basic_state(self) -> None:
        view = ui.View(btn("a"), timeout=None)
        assert view.is_dispatchable()
        assert view.is_persistent()
        assert not view.is_dispatching()
        assert not view.is_finished()
        assert ui.View(timeout=1).is_persistent() is False
        assert view.message is None
        view.message = "m"  # type: ignore[assignment]
        assert view.message == "m"
        with pytest.raises(NotImplementedError):
            ui.BaseView._refresh(view, [])  # type: ignore[arg-type]

    async def test_disable_enable_and_exclusions(self) -> None:
        a, b = btn("a"), btn("b")
        view = ui.DesignerView(ui.ActionRow(a, b), ui.TextDisplay("t"))
        view.disable_all_items(exclusions=[b])
        assert a.disabled
        assert not b.disabled
        view.enable_all_items()
        assert not a.disabled
        view.disable_all_items()
        assert a.disabled
        assert b.disabled
        view.enable_all_items(exclusions=[a])
        assert a.disabled
        assert not b.disabled

    async def test_copy_text_and_walk(self) -> None:
        view = ui.DesignerView(ui.TextDisplay("one"), ui.TextDisplay("two"))
        assert view.copy_text() == "one\ntwo"
        assert len(list(view.walk_children())) == 2

    async def test_stop_wait_and_listening(self) -> None:
        view = ui.View(btn("a"), timeout=30)
        store = ViewStore(SimpleNamespace())
        store.add_view(view, 7)
        assert view.is_dispatching()
        assert view._timeout_task is not None
        first = view._timeout_task
        view._start_listening_from_store(store)
        await asyncio.sleep(0)
        assert first.cancelled()
        view.stop()
        assert await view.wait() is False
        assert view.is_finished()
        assert not view.is_dispatching()
        assert store._views == {}
        assert store._synced_message_views == {}
        view.stop()

    async def test_timeout_dispatch_runs_on_timeout(self) -> None:
        calls: list[str] = []

        class V(ui.View):
            async def on_timeout(self) -> None:
                calls.append("timeout")

        view = V(timeout=0.01)
        store = ViewStore(SimpleNamespace())
        store.add_view(view)
        assert await asyncio.wait_for(view.wait(), 1) is True
        await asyncio.sleep(0.01)
        assert calls == ["timeout"]
        view._dispatch_timeout()
        view._dispatch_item(btn(), fake_interaction())

    async def test_default_hooks(self) -> None:
        view = ui.View()
        assert await view.interaction_check(fake_interaction()) is True
        assert await view.on_check_failure(fake_interaction()) is None
        inter = fake_interaction()
        item = btn()
        err = RuntimeError("x")
        await view.on_error(err, item, inter)
        assert inter.client.events == [("view_error", err, item, inter)]


class TestOnTimeoutDisable:
    async def test_edits_the_message(self) -> None:
        edits: list[Any] = []

        class Msg:
            flags = SimpleNamespace(ephemeral=False)
            channel = SimpleNamespace(type=ChannelType.text)

            async def edit(self, **kwargs: Any) -> Any:
                edits.append(kwargs)
                return "edited"

        view = ui.View(btn("a"), disable_on_timeout=True)
        view.message = Msg()  # type: ignore[assignment]
        await view.on_timeout()
        assert view.children[0].disabled
        assert edits == [{"view": view}]
        assert view.message == "edited"

    async def test_uses_the_interaction_for_ephemeral_messages(self) -> None:
        edits: list[Any] = []

        class Parent:
            async def edit(self, **kwargs: Any) -> Any:
                edits.append(kwargs)
                raise NotFound(SimpleNamespace(status=404, reason=""), "gone")

        class Msg:
            flags = SimpleNamespace(ephemeral=True)
            channel = SimpleNamespace(type=ChannelType.text)

        view = ui.View(btn("a"), disable_on_timeout=True)
        view.message = Msg()  # type: ignore[assignment]
        view.parent = Parent()  # type: ignore[assignment]
        await view.on_timeout()
        assert len(edits) == 1

    async def test_without_message_and_when_disabled_flag_off(self) -> None:
        view = ui.View(btn("a"), disable_on_timeout=True)
        await view.on_timeout()
        assert view.children[0].disabled
        other = ui.View(btn("b"))
        await other.on_timeout()
        assert not other.children[0].disabled


class TestScheduledTasks:
    async def test_dispatch_item_runs_callback(self) -> None:
        seen: list[Any] = []

        class V(ui.View):
            @ui.button(custom_id="go")
            async def go(self, button: Any, interaction: Any) -> None:
                seen.append(interaction)

        view = V()
        inter = fake_interaction(5)
        view._dispatch_item(view.children[0], inter)
        await asyncio.gather(*view._background_tasks)
        assert seen == [inter]
        assert view.message.id == 5

    async def test_check_failure_and_errors(self) -> None:
        calls: list[str] = []

        class V(ui.View):
            @ui.button(custom_id="go")
            async def go(self, button: Any, interaction: Any) -> None:
                raise RuntimeError("cb")

            async def interaction_check(self, interaction: Any) -> bool:
                return interaction.allow

            async def on_check_failure(self, interaction: Any) -> None:
                calls.append("denied")

            async def on_error(self, error: Any, item: Any, interaction: Any) -> None:
                calls.append(f"error:{error}")

        view = V(timeout=10)
        denied = fake_interaction()
        denied.allow = False
        await view._scheduled_task(view.children[0], denied)
        allowed = fake_interaction()
        allowed.allow = True
        await view._scheduled_task(view.children[0], allowed)
        assert calls == ["denied", "error:cb"]
        assert view._timeout_expiry is not None


class TestDesignerViewPositions:
    def make(self) -> ui.DesignerView:
        return ui.DesignerView(
            ui.TextDisplay("a", id=1),
            ui.Container(ui.TextDisplay("in", id=3), id=2),
            ui.TextDisplay("b", id=4),
        )

    async def test_add_item_index_before_after(self) -> None:
        view = self.make()
        view.add_item(ui.TextDisplay("i", id=10), index=0)
        view.add_item(ui.TextDisplay("bf", id=11), before=4)
        view.add_item(ui.TextDisplay("af", id=12), after=1)
        assert [c.id for c in view.children] == [10, 1, 12, 2, 11, 4]

    async def test_add_item_relative_to_nested_and_into(self) -> None:
        view = self.make()
        view.add_item(ui.TextDisplay("n", id=20), after=3)
        view.add_item(ui.TextDisplay("m", id=21), before=3)
        container = view.get_item(2)
        assert [c.id for c in container.items] == [21, 3, 20]
        view.add_item(ui.TextDisplay("z", id=22), into=2)
        assert container.items[-1].id == 22
        view.add_item(ui.TextDisplay("top", id=23), into=view)

    async def test_add_item_errors(self) -> None:
        view = self.make()
        with pytest.raises(ValueError, match="one of"):
            view.add_item(ui.TextDisplay("x"), index=0, before=1)
        with pytest.raises(TypeError, match="ViewItem"):
            view.add_item(object())  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Could not find"):
            view.add_item(ui.TextDisplay("x"), before=999)
        with pytest.raises(ValueError, match="Select or Button"):
            view.add_item(btn())
        view.get_item(4).parent = None
        with pytest.raises(ValueError, match="Could not find"):
            view.add_item(ui.TextDisplay("x"), before=4)

    async def test_replace_item(self) -> None:
        view = self.make()
        new = ui.TextDisplay("new", id=30)
        view.replace_item(1, new)
        assert view.children[0] is new
        assert new.parent is view
        inner = ui.TextDisplay("inner", id=31)
        view.replace_item(3, inner)
        assert view.get_item(2).items[0] is inner
        with pytest.raises(ValueError, match="Could not find"):
            view.replace_item(999, ui.TextDisplay("x"))
        with pytest.raises(ValueError, match="Select or Button"):
            view.replace_item(4, btn())
        orphan = view.get_item(4)
        orphan.parent = None
        with pytest.raises(ValueError, match="Could not find"):
            view.replace_item(orphan, ui.TextDisplay("x"))

    async def test_refresh_and_v2(self) -> None:
        view = ui.DesignerView(ui.TextDisplay("a"))
        view._refresh([])
        view._refresh([_component_factory(PAYLOADS["text"])])
        assert view.children[0].content == "hi"
        assert view.is_components_v2() is True
        assert ui.DesignerView().is_components_v2() is False

    async def test_buttons_decorators_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="ActionRow"):

            class Bad(ui.DesignerView):
                @ui.button(custom_id="x")
                async def x(self, b: Any, i: Any) -> None:
                    pass

    async def test_items_property(self) -> None:
        view = ui.DesignerView()
        items = [ui.TextDisplay("a")]
        view.items = items
        assert view.items is items
        assert view.children is items


class TestViewStore:
    async def test_add_dispatch_and_remove(self) -> None:
        store = ViewStore(SimpleNamespace())
        seen: list[Any] = []

        class V(ui.View):
            @ui.button(custom_id="go")
            async def go(self, button: Any, interaction: Any) -> None:
                seen.append(1)

        view = V(timeout=None)
        store.add_view(view, 9)
        assert store.persistent_views == [view]
        assert store.is_message_tracked(9)
        assert store.get_message_view(9) is view
        inter = fake_interaction(9)
        store.dispatch(2, "go", inter)
        await asyncio.gather(*view._background_tasks)
        assert seen == [1]
        assert inter.view is view
        store.dispatch(2, "nope", fake_interaction(9))
        store.dispatch(3, "go", fake_interaction(9))
        assert store.remove_message_tracking(9) is view
        assert store.remove_message_tracking(9) is None
        store.remove_view(view)
        assert store._views == {}

    async def test_dispatch_falls_back_to_messageless_registration(self) -> None:
        store = ViewStore(SimpleNamespace())
        view = ui.View(btn("go"), timeout=None)
        store.add_view(view)
        store.dispatch(2, "go", fake_interaction(77))
        await asyncio.gather(*view._background_tasks)

    async def test_unstored_views_are_ignored_and_finished_ones_pruned(self) -> None:
        store = ViewStore(SimpleNamespace())
        store.add_view(ui.View(btn("a"), store=False))
        assert store._views == {}
        view = ui.View(btn("a"), timeout=None)
        store.add_view(view)
        view._stopped.set_result(True)
        store.add_view(ui.View(btn("b"), timeout=None))
        assert all(k[2] != "a" for k in store._views)

    async def test_update_from_message(self) -> None:
        state = SimpleNamespace()
        store = ViewStore(state)
        view = ui.DesignerView(ui.TextDisplay("old"), timeout=None)
        store.add_view(view, 4)
        store.update_from_message(4, [PAYLOADS["text"]])
        assert view.children[0].content == "hi"

        class Broken(ui.DesignerView):
            def _refresh(self, components: Any) -> None:
                raise RuntimeError("mismatch")

        broken = Broken(timeout=None)
        store.add_view(broken, 5)
        store.update_from_message(5, [PAYLOADS["text"]])
