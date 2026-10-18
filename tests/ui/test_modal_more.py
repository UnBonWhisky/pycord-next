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

from discord import ui
from discord.limits import ComponentLimits
from discord.ui.modal import ModalStore, _ModalWeights


def text(custom_id: str | None = None, **kwargs: Any) -> ui.InputText:
    return ui.InputText(label="L", custom_id=custom_id, **kwargs)


class FakeClient:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def dispatch(self, *args: Any) -> None:
        self.events.append(args)


def interaction(components: list[dict[str, Any]]) -> Any:
    return SimpleNamespace(
        client=FakeClient(), data={"components": components}, modal=None
    )


class TestBaseModal:
    async def test_validation(self) -> None:
        with pytest.raises(TypeError, match="custom_id"):
            ui.Modal(title="t", custom_id=1)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="title"):
            ui.Modal(title="x" * (ComponentLimits.MODAL_TITLE_MAX + 1))

    async def test_title_and_custom_id_setters(self) -> None:
        modal = ui.Modal(title="t", custom_id="cid")
        modal.title = "new"
        assert modal.title == "new"
        with pytest.raises(ValueError, match="title"):
            modal.title = "x" * (ComponentLimits.MODAL_TITLE_MAX + 1)
        with pytest.raises(TypeError, match="title"):
            modal.title = 5  # type: ignore[assignment]
        modal.custom_id = "other"
        assert modal.custom_id == "other"
        with pytest.raises(TypeError, match="custom_id"):
            modal.custom_id = 5  # type: ignore[assignment]
        with pytest.raises(ValueError, match="custom_id"):
            modal.custom_id = "x" * (ComponentLimits.CUSTOM_ID_MAX + 1)
        assert len(ui.Modal(title="t").custom_id) == 32

    async def test_repr_and_to_dict(self) -> None:
        modal = ui.Modal(text("a"), title="Form", custom_id="cid")
        assert repr(modal).startswith("<Modal title='Form' children=[")
        payload = modal.to_dict()
        assert payload["title"] == "Form"
        assert payload["custom_id"] == "cid"
        assert payload["components"][0]["type"] == 1
        assert payload["components"][0]["components"][0]["custom_id"] == "a"

    async def test_add_remove_items(self) -> None:
        modal = ui.Modal(title="t")
        with pytest.raises(TypeError, match="InputText"):
            modal.add_item(ui.TextDisplay("x"))  # type: ignore[arg-type]
        first = text("a")
        modal.add_item(first)
        assert modal.children == [first]
        assert first._rendered_row == 0
        modal.remove_item(first)
        modal.remove_item(first)
        assert modal.children == []
        assert first._rendered_row is None

    async def test_max_items(self) -> None:
        modal = ui.Modal(*[text(f"c{i}") for i in range(5)], title="t")
        with pytest.raises(ValueError, match="open space"):
            modal.add_item(text("overflow"))

    async def test_children_setter(self) -> None:
        modal = ui.Modal(text("a"), title="t")
        new = [text("b"), text("c")]
        modal.children = new
        assert modal.children == new
        assert modal._weights.weights[:2] == [5, 5]
        with pytest.raises(TypeError, match="InputText"):
            modal.children = [ui.TextDisplay("x")]  # type: ignore[list-item]

    async def test_rows_group_items(self) -> None:
        a, b, c = text("a", row=2), text("b", row=1), text("c")
        modal = ui.Modal(a, b, c, title="t")
        rows = modal.to_components()
        ids = [[x["custom_id"] for x in row["components"]] for row in rows]
        assert ids == [["c"], ["b"], ["a"]]

    async def test_refresh_updates_matching_children(self) -> None:
        a, b = text("a"), text("b")
        modal = ui.Modal(a, b, title="t")
        modal._refresh(
            None,  # type: ignore[arg-type]
            [
                {"components": [{"custom_id": "b", "value": "bee"}]},
                {"components": [{"custom_id": "zzz", "value": "x"}]},
            ],
        )
        assert b.value == "bee"
        assert a.value is None

    async def test_get_item_and_walk(self) -> None:
        a = text("a")
        modal = ui.Modal(a, title="t")
        assert modal.get_item("a") is a
        assert list(modal.walk_children()) == [a]

    async def test_stop_and_wait(self) -> None:
        modal = ui.Modal(title="t", timeout=60)
        store = ModalStore(SimpleNamespace())
        store.add_modal(modal, 1)
        assert modal._timeout_task is not None
        modal.stop()
        assert modal._timeout_task is None
        assert modal._timeout_expiry is None
        assert await modal.wait() is True
        modal.stop()

    async def test_default_callback_stops(self) -> None:
        modal = ui.Modal(title="t")
        await modal.callback(None)  # type: ignore[arg-type]
        assert modal._stopped.done()

    async def test_on_error_dispatches(self) -> None:
        modal = ui.Modal(title="t")
        inter = interaction([])
        err = RuntimeError("x")
        await modal.on_error(err, inter)
        assert inter.client.events == [("modal_error", err, inter)]

    async def test_base_refresh_not_implemented(self) -> None:
        modal = ui.BaseModal(title="t")
        with pytest.raises(NotImplementedError):
            modal._refresh(None, [])  # type: ignore[arg-type]

    async def test_timeout_dispatch(self) -> None:
        timed_out: list[bool] = []

        class M(ui.Modal):
            async def on_timeout(self) -> None:
                timed_out.append(True)

        modal = M(title="t", timeout=0.01)
        store = ModalStore(SimpleNamespace())
        store.add_modal(modal, 1)
        assert modal._cancel_callback is not None
        assert await asyncio.wait_for(modal.wait(), 1) is True
        await asyncio.sleep(0.01)
        assert timed_out == [True]
        modal._dispatch_timeout()

    async def test_restarting_listening_cancels_the_old_timeout(self) -> None:
        modal = ui.Modal(title="t", timeout=30)
        store = ModalStore(SimpleNamespace())
        store.add_modal(modal, 1)
        first = modal._timeout_task
        store.add_modal(modal, 1)
        assert first is not None
        assert modal._timeout_task is not first
        await asyncio.sleep(0)
        assert first.cancelled()
        modal.stop()


class TestDesignerModalValidation:
    async def test_input_text_is_rejected(self) -> None:
        modal = ui.DesignerModal(title="t")
        with pytest.raises(TypeError, match="Label"):
            modal.add_item(text("a"))
        with pytest.raises(TypeError, match="Label"):
            modal.children = [text("a")]
        with pytest.raises(TypeError, match="ModalItem"):
            modal.children = [object()]  # type: ignore[list-item]
        label = ui.Label("L", ui.InputText(label=None, custom_id="b"))
        modal.children = [label]
        assert modal.children == [label]

    async def test_refresh_in_order(self) -> None:
        field = ui.InputText(label=None, custom_id="name")
        modal = ui.DesignerModal(title="t").add_label("Name", field)
        seen: list[Any] = []
        label = modal.children[0]
        label.refresh_from_modal = lambda inter, data: seen.append(data)  # type: ignore[method-assign]
        modal._refresh(None, [{"id": 1}])  # type: ignore[arg-type]
        assert seen == [{"id": 1}]


class TestModalWeights:
    def test_row_placement(self) -> None:
        weights = _ModalWeights([text("a", row=2), text("b")])
        assert weights.weights[2] == 5
        assert weights.weights[0] == 5
        item = text("c")
        with pytest.raises(ValueError, match="would not fit at row 2"):
            weights.add_item(text("d", row=2))
        weights.add_item(item)
        weights.remove_item(item)
        assert item._rendered_row is None
        weights.remove_item(item)
        weights.clear()
        assert weights.weights == [0] * 5

    def test_no_open_space(self) -> None:
        weights = _ModalWeights([text(str(i)) for i in range(5)])
        with pytest.raises(ValueError, match="open space"):
            weights.find_open_space(text("x"))


class TestModalStore:
    async def test_add_and_remove(self) -> None:
        store = ModalStore(SimpleNamespace())
        modal = ui.Modal(title="t", custom_id="cid")
        store.add_modal(modal, 5)
        assert (5, "cid") in store._modals
        store.remove_modal(modal, 5)
        assert store._modals == {}
        unstored = ui.Modal(title="t", custom_id="x", store=False)
        store.add_modal(unstored, 5)
        assert store._modals == {}

    async def test_dispatch_runs_callback_and_removes(self) -> None:
        store = ModalStore(SimpleNamespace())
        called: list[Any] = []

        class M(ui.Modal):
            async def callback(self, interaction: Any) -> None:
                called.append(self.children[0].value)

        field = text("a")
        modal = M(field, title="t", custom_id="cid")
        store.add_modal(modal, 5)
        inter = interaction([{"components": [{"custom_id": "a", "value": "hi"}]}])
        await store.dispatch(5, "cid", inter)
        assert called == ["hi"]
        assert inter.modal is modal
        assert store._modals == {}

    async def test_dispatch_unknown_is_ignored(self) -> None:
        store = ModalStore(SimpleNamespace())
        assert await store.dispatch(1, "nope", interaction([])) is None

    async def test_dispatch_error_goes_to_on_error(self) -> None:
        store = ModalStore(SimpleNamespace())
        errors: list[Exception] = []

        class M(ui.Modal):
            async def callback(self, interaction: Any) -> None:
                raise RuntimeError("boom")

            async def on_error(self, error: Exception, interaction: Any) -> None:
                errors.append(error)

        modal = M(title="t", custom_id="cid")
        store.add_modal(modal, 5)
        await store.dispatch(5, "cid", interaction([]))
        assert isinstance(errors[0], RuntimeError)
        assert (5, "cid") in store._modals
        modal.stop()
