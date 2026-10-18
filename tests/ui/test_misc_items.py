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

import pytest

import discord
from discord import ui
from discord.components import _component_factory
from discord.ui.button import _resolve_emoji
from discord.ui.core import _insertion_index, _item_getter


class TestButton:
    async def test_emoji_resolution(self) -> None:
        assert _resolve_emoji("\N{THUMBS UP SIGN}").name == "\N{THUMBS UP SIGN}"
        partial = discord.PartialEmoji(name="x", id=1)
        assert _resolve_emoji(partial).id == 1
        with pytest.raises(TypeError, match="expected str"):
            _resolve_emoji(5)

    async def test_argument_conflicts(self) -> None:
        with pytest.raises(TypeError, match="url and custom_id"):
            ui.Button(custom_id="a", url="https://x.io")
        with pytest.raises(TypeError, match="url and sku_id"):
            ui.Button(url="https://x.io", sku_id=1)
        with pytest.raises(TypeError, match="sku_id and custom_id"):
            ui.Button(custom_id="a", sku_id=1)

    async def test_link_button_persistence(self) -> None:
        link = ui.Button(label="x", url="https://x.io")
        assert link.style is discord.ButtonStyle.link
        assert link.is_persistent() is True
        blank = ui.Button(label="x", url="https://x.io")
        blank.url = None
        assert blank.is_persistent() is False

    async def test_decorator_requires_coroutine(self) -> None:
        with pytest.raises(TypeError, match="coroutine"):
            ui.button()(lambda self, b, i: None)  # type: ignore[arg-type]


class TestMediaGallery:
    async def test_item_editing(self) -> None:
        a = discord.MediaGalleryItem("https://x.io/a.png")
        b = discord.MediaGalleryItem("https://x.io/b.png")
        gallery = ui.MediaGallery(a, id=3)
        with pytest.raises(TypeError, match="MediaGalleryItem"):
            gallery.append_item(object())  # type: ignore[arg-type]
        gallery.append_item(b)
        gallery.remove_item(0)
        gallery.remove_item(99)
        assert gallery.items == [b]
        gallery.replace_item(0, a)
        assert gallery.items == [a]

    async def test_from_assets_and_files(self) -> None:
        file = discord.File(
            __import__("io").BytesIO(b"x"), filename="pic.png", spoiler=True
        )
        gallery = ui.MediaGallery.from_files(file, id=2)
        assert gallery.items[0].url.endswith("SPOILER_pic.png")
        assert gallery.items[0].url.startswith("attachment://")

        class Asset(discord.asset.AssetMixin):
            url = "https://cdn.x/a.png"
            cdn_name = None

        with pytest.raises(ValueError, match="could not determine a filename"):
            ui.MediaGallery.from_assets(Asset(), new=True)  # type: ignore[call-arg]


class TestFileAndThumbnail:
    async def test_file_url_and_refresh(self) -> None:
        f = ui.File("attachment://a.txt", spoiler=True, id=1)
        assert f.url == "attachment://a.txt"
        f.url = "attachment://b.txt"
        assert f.underlying.file.url == "attachment://b.txt"
        component = _component_factory(
            {"type": 13, "id": 1, "file": {"url": "https://cdn.x/files/c.txt?x=1"}}
        )
        f.refresh_component(component)
        assert f.underlying is component
        built = ui.File.from_component(component)
        assert built.url == "attachment://c.txt"
        again = ui.File.from_component(
            _component_factory(
                {"type": 13, "id": 1, "file": {"url": "attachment://d.txt"}}
            )
        )
        assert again.url == "attachment://d.txt"
        assert built.to_component_dict()["type"] == 13

    async def test_thumbnail_url_setter(self) -> None:
        t = ui.Thumbnail("https://x.io/a.png", description="d", id=1)
        t.url = "https://x.io/b.png"
        assert t.url == "https://x.io/b.png"


class TestModalFields:
    async def test_radio_group(self) -> None:
        rg = ui.RadioGroup(custom_id="r")
        rg.add_option(label="a", value="a").add_option(label="b")
        assert [o.value for o in rg.underlying.options] == ["a", "b"]
        assert rg.value is None
        rg.refresh_from_modal(None, {"value": "a"})  # type: ignore[arg-type]
        assert rg.value == "a"
        assert rg.to_component_dict()["type"] == 21
        rg.clear_options()
        assert rg.underlying.options == []

    async def test_checkbox_group(self) -> None:
        cg = ui.CheckboxGroup(custom_id="c")
        cg.add_option(label="a", value="a").add_option(label="b", value="b")
        assert cg.values is None
        cg.refresh_from_modal(None, {"values": ["a"]})  # type: ignore[arg-type]
        assert cg.values == ["a"]
        assert cg.to_component_dict()["type"] == 22
        cg.clear_options()
        assert cg.underlying.options == []

    async def test_checkbox(self) -> None:
        cb = ui.Checkbox(custom_id="c")
        assert cb.value is None
        cb.refresh_from_modal(None, {"value": True})  # type: ignore[arg-type]
        assert cb.value is True
        assert cb.to_component_dict()["type"] == 23

    async def test_file_upload(self) -> None:
        fu = ui.FileUpload(custom_id="f")
        assert fu.values is None
        interaction = SimpleNamespace(
            data={
                "resolved": {
                    "attachments": {
                        "9": {
                            "id": "9",
                            "filename": "a.txt",
                            "size": 3,
                            "url": "https://cdn.x/a.txt",
                            "proxy_url": "https://cdn.x/a.txt",
                        }
                    }
                }
            },
            _state=SimpleNamespace(http=SimpleNamespace()),
        )
        fu.refresh_from_modal(interaction, {"values": ["9"]})  # type: ignore[arg-type]
        assert [a.filename for a in fu.values] == ["a.txt"]
        assert fu.to_component_dict()["type"] == 19


class TestCoreHelpers:
    async def test_insertion_index(self) -> None:
        a, b = ui.TextDisplay("a", id=1), ui.TextDisplay("b", id=2)
        view = ui.DesignerView(a, b)
        assert _insertion_index(view, view.children, None, None, None, "x") is None
        assert _insertion_index(view, view.children, 3, None, None, "x") == 3
        assert _insertion_index(view, view.children, None, 2, None, "x") == 1
        assert _insertion_index(view, view.children, None, None, 1, "x") == 1
        with pytest.raises(ValueError, match="Could not find"):
            _insertion_index(view, view.children, None, None, ui.TextDisplay("z"), "x")
        with pytest.raises(ValueError, match="Could not find"):
            _insertion_index(view, view.children, None, 99, None, "the view")
        stray = ui.TextDisplay("s", id=7)
        view.children.append(stray)
        view.children.remove(stray)
        with pytest.raises(ValueError, match="Could not find"):
            _insertion_index(
                SimpleNamespace(get_item=lambda ref: stray),
                view.children,
                None,
                7,
                None,
                "w",
            )

    def test_item_getter(self) -> None:
        a = ui.TextDisplay("a", id=1)
        assert _item_getter([a]) is None
        assert _item_getter([a], id=1) is a
        assert _item_getter([a], nope=3) is None
        container = ui.Container(a, id=5)
        assert _item_getter([container], id=1) is a

    async def test_timeout_task_paths(self) -> None:
        view = ui.View(timeout=None)
        await view._timeout_task_impl()
        view.timeout = 0.01
        view._timeout_expiry = None
        await view._timeout_task_impl()
        assert view.is_finished()
        waiting = ui.View(timeout=0.02)
        import time as _time

        waiting._timeout_expiry = _time.monotonic() + 0.02
        await asyncio.wait_for(waiting._timeout_task_impl(), 1)
        assert waiting.is_finished()
        assert waiting._expires_at is not None
        assert ui.View(timeout=None)._expires_at is None
        base = ui.core.ItemInterface()
        with pytest.raises(NotImplementedError):
            base._dispatch_timeout()
        with pytest.raises(NotImplementedError):
            base.add_item(None)
        with pytest.raises(NotImplementedError):
            base.remove_item(None)
        with pytest.raises(NotImplementedError):
            base.clear_items()
        assert await base.on_timeout() is None
