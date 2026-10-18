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
# DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import datetime as dt

import pytest

import discord
from discord import Embed, EmbedAuthor, EmbedField, EmbedFooter, EmbedMedia


def test_embed_constructor_converts_values() -> None:
    embed = Embed(
        title=5,
        description=6,
        url=7,
        colour=0x123456,
        timestamp=dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc),
        fields=[EmbedField("n", "v")],
        author=EmbedAuthor("me", url="https://example.com", icon_url="https://i/a.png"),
        footer=EmbedFooter("foot", icon_url="https://i/f.png"),
        image="https://i/image.png",
        thumbnail=EmbedMedia("https://i/thumb.png"),
    )

    assert (embed.title, embed.description, embed.url) == ("5", "6", "7")
    assert embed.colour == discord.Colour(0x123456)
    assert embed.author is not None
    assert embed.author.name == "me"
    assert embed.footer is not None
    assert embed.footer.text == "foot"
    assert embed.image is not None
    assert embed.image.url == "https://i/image.png"
    assert embed.thumbnail is not None
    assert embed.thumbnail.url == "https://i/thumb.png"
    assert embed.to_dict() == {
        "type": "rich",
        "title": "5",
        "description": "6",
        "url": "7",
        "color": 0x123456,
        "timestamp": "2024-01-02T00:00:00+00:00",
        "fields": [{"name": "n", "value": "v", "inline": False}],
        "author": {
            "name": "me",
            "url": "https://example.com",
            "icon_url": "https://i/a.png",
        },
        "footer": {"text": "foot", "icon_url": "https://i/f.png"},
        "image": {"url": "https://i/image.png"},
        "thumbnail": {"url": "https://i/thumb.png"},
    }


def test_embed_length_counts_visible_text() -> None:
    embed = Embed(title="abc", description="de")
    assert len(embed) == 5
    embed.add_field(name="n", value="vv")
    embed.set_footer(text="foot")
    embed.set_author(name="auth")
    assert len(embed) == 5 + 3 + 4 + 4
    assert len(Embed()) == 0


def test_embed_timestamp_setter() -> None:
    embed = Embed()
    assert embed.timestamp is None
    embed.timestamp = dt.datetime(2024, 1, 1)  # noqa: DTZ001
    assert embed.timestamp is not None
    assert embed.timestamp.tzinfo is not None
    embed.timestamp = None
    assert embed.timestamp is None
    with pytest.raises(TypeError, match=r"Expected datetime\.datetime or None"):
        embed.timestamp = "now"  # type: ignore[assignment]
    naive = Embed()
    naive._timestamp = dt.datetime(2024, 1, 1)  # noqa: DTZ001
    assert naive.to_dict()["timestamp"] == "2024-01-01T00:00:00+00:00"


def test_footer_property_and_setter() -> None:
    embed = Embed()
    assert embed.footer is None
    embed.footer = EmbedFooter("text")
    assert embed.footer is not None
    assert embed.footer.text == "text"
    embed.footer = None
    assert embed.footer is None
    with pytest.raises(TypeError, match="Expected EmbedFooter or None"):
        embed.footer = "text"  # type: ignore[assignment]

    assert embed.set_footer(text="a", icon_url="https://i/x.png") is embed
    assert embed.to_dict()["footer"] == {"text": "a", "icon_url": "https://i/x.png"}
    assert embed.set_footer().to_dict()["footer"] == {}
    assert embed.remove_footer() is embed
    assert "footer" not in embed.to_dict()
    embed.remove_footer()


@pytest.mark.parametrize("name", ["image", "thumbnail"])
def test_media_properties(name: str) -> None:
    embed = Embed()
    assert getattr(embed, name) is None
    setattr(embed, name, "https://i/a.png")
    assert getattr(embed, name).url == "https://i/a.png"
    setattr(embed, name, EmbedMedia("https://i/b.png"))
    assert getattr(embed, name).url == "https://i/b.png"
    setattr(embed, name, None)
    assert getattr(embed, name) is None
    with pytest.raises(TypeError, match=r"Expected discord\.EmbedMedia, or None"):
        setattr(embed, name, 5)

    assert getattr(embed, f"set_{name}")(url=123) is embed
    assert embed.to_dict()[name] == {"url": "123"}
    getattr(embed, f"set_{name}")(url=None)
    assert name not in embed.to_dict()
    getattr(embed, f"set_{name}")(url=None)
    assert getattr(embed, f"remove_{name}")() is embed


def test_author_property_and_setter() -> None:
    embed = Embed()
    assert embed.author is None
    embed.author = EmbedAuthor("me")
    assert embed.author is not None
    assert embed.author.name == "me"
    embed.author = None
    assert embed.author is None
    with pytest.raises(TypeError, match=r"Expected discord\.EmbedAuthor, or None"):
        embed.author = "me"  # type: ignore[assignment]

    assert embed.set_author(name=1, url="https://u", icon_url="https://i") is embed
    assert embed.to_dict()["author"] == {
        "name": "1",
        "url": "https://u",
        "icon_url": "https://i",
    }
    assert embed.set_author(name="plain").to_dict()["author"] == {"name": "plain"}
    assert embed.remove_author() is embed
    assert "author" not in embed.to_dict()


def test_author_and_footer_from_dict() -> None:
    author = EmbedAuthor.from_dict(
        {"name": "n", "url": "u", "icon_url": "i", "proxy_icon_url": "p"}
    )
    assert (author.name, author.url, author.icon_url, author.proxy_icon_url) == (
        "n",
        "u",
        "i",
        "p",
    )
    assert len(author) == 1
    with pytest.raises(ValueError, match="name field is required"):
        EmbedAuthor.from_dict({"url": "u"})
    footer = EmbedFooter.from_dict(
        {"text": "tt", "icon_url": "i", "proxy_icon_url": "p"}
    )
    assert (footer.text, footer.icon_url, footer.proxy_icon_url) == ("tt", "i", "p")
    assert len(footer) == 2
    with pytest.raises(ValueError, match="text field is required"):
        EmbedFooter.from_dict({})
    assert EmbedAuthor("a").proxy_icon_url is None
    assert EmbedFooter("a").proxy_icon_url is None
    media = EmbedMedia("https://u")
    assert (media.proxy_url, media.height, media.width) == (None, None, None)


def test_field_management() -> None:
    embed = Embed()
    assert embed.add_field(name="a", value="1", inline=False) is embed
    embed.append_field(EmbedField("b", "2", True))
    embed.insert_field_at(1, name="mid", value=5)
    assert [f.name for f in embed.fields] == ["a", "mid", "b"]
    assert embed.fields[1].value == "5"
    assert embed.set_field_at(0, name="A", value="x", inline=True) is embed
    assert (embed.fields[0].name, embed.fields[0].value, embed.fields[0].inline) == (
        "A",
        "x",
        True,
    )
    with pytest.raises(IndexError, match="out of range"):
        embed.set_field_at(9, name="a", value="b")
    with pytest.raises(IndexError, match="out of range"):
        embed.set_field_at("x", name="a", value="b")  # type: ignore[arg-type]
    embed.remove_field(1)
    embed.remove_field(99)
    assert [f.name for f in embed.fields] == ["A", "b"]
    embed.clear_fields()
    assert embed.fields == []

    embed.fields = [EmbedField("n", "v")]
    assert len(embed.fields) == 1
    with pytest.raises(TypeError, match="list of EmbedField"):
        embed.fields = ["x"]  # type: ignore[list-item]
    with pytest.raises(TypeError, match="EmbedField object"):
        embed.append_field("x")  # type: ignore[arg-type]


def test_embed_round_trip_and_copy() -> None:
    data = {
        "type": "rich",
        "title": "t",
        "description": "d",
        "color": 5,
        "fields": [{"name": "n", "value": "v", "inline": True}],
        "footer": {"text": "f"},
        "video": {"url": "https://v", "height": 1, "width": 2},
        "provider": {"name": "p", "url": "https://p"},
    }
    embed = Embed.from_dict(data)
    assert embed.colour == discord.Colour(5)
    assert embed.video is not None
    assert embed.video.url == "https://v"
    assert embed.provider is not None
    assert embed.provider.name == "p"
    assert embed.to_dict()["footer"] == {"text": "f"}
    duplicate = embed.copy()
    assert duplicate is not embed
    assert duplicate.to_dict() == embed.to_dict()
    duplicate.add_field(name="x", value="y")
    assert len(embed.fields) == 1


def test_colour_property() -> None:
    embed = Embed(color=0xFF0000)
    assert embed.color == discord.Colour(0xFF0000)
    embed.colour = discord.Colour(1)
    assert embed.colour == discord.Colour(1)
    embed.colour = None
    assert embed.colour is None
    with pytest.raises(TypeError):
        embed.colour = "red"  # type: ignore[assignment]
