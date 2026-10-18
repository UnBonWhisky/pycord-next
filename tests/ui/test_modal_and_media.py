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

import io
from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord import ui
from discord.asset import AssetMixin
from discord.components import UnfurledMediaItem


class FakeHTTP:
    def __init__(self, payload: bytes = b"data") -> None:
        self.payload = payload
        self.urls: list[str] = []

    async def get_from_cdn(self, url: str) -> bytes:
        self.urls.append(url)
        return self.payload


def media(url: str, payload: bytes = b"data") -> UnfurledMediaItem:
    http = FakeHTTP(payload)
    return UnfurledMediaItem.from_dict({"url": url}, state=SimpleNamespace(http=http))


class TestDesignerModal:
    async def test_add_label_and_text(self) -> None:
        field = ui.InputText(label=None, custom_id="name")
        modal = (
            ui.DesignerModal(title="Form")
            .add_text("Intro", id=1)
            .add_label("Name", field, description="Your name", id=2)
            .add_label("Empty")
        )
        assert [type(i) for i in modal.children] == [
            ui.TextDisplay,
            ui.Label,
            ui.Label,
        ]
        assert modal.children[1].item is field
        assert modal.children[1].description == "Your name"
        assert modal.get_item("name") is field

    async def test_from_dict(self) -> None:
        modal = ui.DesignerModal.from_dict(
            {
                "custom_id": "form",
                "title": "Form",
                "components": [
                    {"type": 10, "id": 1, "content": "Intro"},
                    {
                        "type": 18,
                        "id": 2,
                        "label": "Name",
                        "description": "Your name",
                        "component": {
                            "type": 4,
                            "custom_id": "name",
                            "style": 1,
                        },
                    },
                ],
            },
            timeout=30.0,
        )
        assert isinstance(modal, ui.DesignerModal)
        assert modal.custom_id == "form"
        assert modal.title == "Form"
        assert modal.timeout == 30.0
        assert isinstance(modal.children[0], ui.TextDisplay)
        assert modal.get_item("name").custom_id == "name"
        assert modal.to_dict()["components"][1]["label"] == "Name"

    async def test_from_dict_is_positional_only_for_the_payload(self) -> None:
        with pytest.raises(TypeError):
            ui.DesignerModal.from_dict(data={"title": "t", "components": []})  # type: ignore[call-arg]

    async def test_limit_of_components(self) -> None:
        modal = ui.DesignerModal(title="Form")
        for n in range(5):
            modal.add_text(str(n))
        with pytest.raises(ValueError, match="up to 5"):
            modal.add_text("six")

    async def test_remove_item_on_a_legacy_modal(self) -> None:
        first = ui.InputText(label="a", custom_id="a")
        second = ui.InputText(label="b", custom_id="b")
        modal = ui.Modal(first, second, title="Form")
        modal.remove_item(first)
        assert modal.children == [second]
        modal.add_item(ui.InputText(label="c", custom_id="c"))
        assert [c.custom_id for c in modal.children] == ["b", "c"]


class TestUnfurledMediaItem:
    async def test_resolved_name(self) -> None:
        assert UnfurledMediaItem("attachment://cat.png").resolved_name == "cat.png"
        assert (
            UnfurledMediaItem(
                "https://cdn.example.com/a/b/cat.gif?size=4"
            ).resolved_name
            == "cat.gif"
        )
        assert UnfurledMediaItem("https://cdn.example.com/").resolved_name is None

    async def test_read_and_save(self, tmp_path: Any) -> None:
        item = media("https://cdn.example.com/cat.png", b"meow")
        assert await item.read() == b"meow"
        buffer = io.BytesIO()
        assert await item.save(buffer) == 4
        assert buffer.read() == b"meow"
        target = tmp_path / "cat.png"
        assert await item.save(target) == 4
        assert target.read_bytes() == b"meow"

    async def test_local_urls_cannot_be_downloaded(self) -> None:
        item = media("attachment://cat.png")
        with pytest.raises(ValueError, match="local"):
            await item.read()
        with pytest.raises(ValueError, match="local"):
            await item.save(io.BytesIO())
        with pytest.raises(ValueError, match="local"):
            await item.to_file()

    async def test_read_without_state(self) -> None:
        with pytest.raises(discord.DiscordException):
            await UnfurledMediaItem("https://cdn.example.com/cat.png").read()

    async def test_to_file(self) -> None:
        item = media("https://cdn.example.com/a/cat.png", b"meow")
        file = await item.to_file(description="a cat")
        assert isinstance(file, discord.File)
        assert file.filename == "cat.png"
        assert file.description == "a cat"
        assert file.fp.read() == b"meow"
        spoiler = await item.to_file("dog.png", spoiler=True)
        assert spoiler.filename == "SPOILER_dog.png"

    async def test_to_file_needs_a_name(self) -> None:
        item = media("https://cdn.example.com/", b"x")
        with pytest.raises(ValueError, match="filename"):
            await item.to_file()
        assert (await item.to_file("named.bin")).filename == "named.bin"


class TestCdnName:
    def test_asset_mixin(self) -> None:
        class Thing(AssetMixin):
            url = "https://cdn.discordapp.com/emojis/123.png?size=64"
            _state = None

        assert Thing().cdn_name == "123.png"

        class Empty(AssetMixin):
            url = "https://cdn.discordapp.com/"
            _state = None

        assert Empty().cdn_name is None


class TestMediaGallery:
    async def test_from_files(self) -> None:
        gallery = ui.MediaGallery.from_files(
            discord.File(io.BytesIO(b"a"), filename="a.png", description="first"),
            discord.File(io.BytesIO(b"b"), filename="b.png", spoiler=True),
            id=5,
        )
        assert gallery.id == 5
        assert [i.url for i in gallery.items] == [
            "attachment://a.png",
            "attachment://SPOILER_b.png",
        ]
        assert gallery.items[0].description == "first"
        assert gallery.items[1].spoiler is True

    async def test_from_assets_keeps_cdn_urls(self) -> None:
        class Thing(AssetMixin):
            url = "https://cdn.discordapp.com/emojis/123.png"
            _state = None

        gallery = ui.MediaGallery.from_assets(Thing())
        assert gallery.items[0].url == "https://cdn.discordapp.com/emojis/123.png"

    async def test_from_assets_for_reupload(self) -> None:
        class Thing(AssetMixin):
            url = "https://cdn.discordapp.com/emojis/123.png"
            _state = None

        attachment = SimpleNamespace(
            filename="doc.png",
            url="https://cdn.discordapp.com/attachments/1/2/doc.png",
            description="alt",
            is_spoiler=lambda: True,
        )
        gallery = ui.MediaGallery.from_assets(Thing(), attachment, new=True)
        assert [i.url for i in gallery.items] == [
            "attachment://123.png",
            "attachment://doc.png",
        ]
        assert gallery.items[1].description == "alt"
        assert gallery.items[1].spoiler is True

    async def test_from_assets_limit(self) -> None:
        class Thing(AssetMixin):
            url = "https://cdn.discordapp.com/emojis/123.png"
            _state = None

        with pytest.raises(ValueError, match=r"\(10\)"):
            ui.MediaGallery.from_assets(*(Thing() for _ in range(11)))

    async def test_to_files(self) -> None:
        http = FakeHTTP(b"pixels")
        state = SimpleNamespace(http=http)
        gallery = ui.MediaGallery(
            discord.MediaGalleryItem(
                "https://cdn.example.com/a.png", description="alt"
            ),
        )
        gallery.items[0].media._state = state
        files = await gallery.to_files()
        assert [f.filename for f in files] == ["a.png"]
        assert files[0].description == "alt"
        assert files[0].fp.read() == b"pixels"
        assert http.urls == ["https://cdn.example.com/a.png"]

    async def test_item_repr(self) -> None:
        item = discord.MediaGalleryItem("https://example.com/a.png", spoiler=True)
        assert (
            repr(item)
            == "<MediaGalleryItem url='https://example.com/a.png' spoiler=True>"
        )
