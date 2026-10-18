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


"""CDN asset extensions and sizes (upstream #3294), per the Discord image formatting docs."""

from __future__ import annotations

import pytest

from discord import Asset, InvalidArgument

BASE = "https://cdn.discordapp.com"


def animated() -> Asset:
    return Asset._from_avatar(None, 1, "a_abc")


def static() -> Asset:
    return Asset._from_avatar(None, 1, "abc")


def test_default_urls_are_unchanged() -> None:
    assert animated().url == f"{BASE}/avatars/1/a_abc.gif?size=1024"
    assert static().url == f"{BASE}/avatars/1/abc.png?size=1024"


def test_extension_and_size() -> None:
    assert animated().extension == "gif"
    assert animated().size == 1024
    assert static().extension == "png"
    assert static().with_size(64).size == 64
    assert Asset._from_soundboard_sound(None, 5).extension is None
    assert Asset._from_soundboard_sound(None, 5).size is None
    assert Asset._from_scheduled_event_image(None, 5, "hash").size is None


def test_animated_webp_requests_the_animated_query() -> None:
    asset = animated().with_format("webp")
    assert asset.extension == "webp"
    assert asset.url == f"{BASE}/avatars/1/a_abc.webp?size=1024&animated=true"
    assert asset.is_animated()


def test_animated_query_survives_a_resize_and_is_dropped_for_other_formats() -> None:
    webp = animated().with_format("webp")
    assert webp.with_size(64).url == (
        f"{BASE}/avatars/1/a_abc.webp?size=64&animated=true"
    )
    assert webp.replace(size=128).size == 128
    assert webp.replace(size=128).url.endswith("animated=true")
    assert webp.with_format("gif").url == f"{BASE}/avatars/1/a_abc.gif?size=1024"
    assert "animated" not in animated().replace(format="png", size=32).url


def test_replace_with_webp_on_an_animated_asset() -> None:
    assert animated().replace(format="webp", size=256).url == (
        f"{BASE}/avatars/1/a_abc.webp?size=256&animated=true"
    )


def test_static_assets_never_get_the_animated_query() -> None:
    assert static().with_format("webp").url == f"{BASE}/avatars/1/abc.webp?size=1024"
    assert static().with_static_format("jpg").extension == "jpg"
    assert animated().with_static_format("jpg") is not None
    assert animated().with_static_format("jpg").extension == "gif"


def test_invalid_formats_still_raise() -> None:
    with pytest.raises(InvalidArgument):
        static().with_format("gif")
    with pytest.raises(InvalidArgument):
        animated().with_format("bmp")  # type: ignore[arg-type]
    with pytest.raises(InvalidArgument):
        animated().with_size(100)
