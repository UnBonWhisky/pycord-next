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
from typing import Any
from unittest.mock import MagicMock

import pytest

from discord.asset import AssetMixin
from discord.commands.cooldowns import BucketType
from discord.reaction import Reaction
from discord.sticker import StickerItem


class TestStickerUrl:
    def test_url_is_readable_and_writable(self) -> None:
        item = StickerItem(
            state=MagicMock(),
            data={"id": "1", "name": "wave", "format_type": 1},
        )
        assert item.url.endswith("/stickers/1.png")
        item.url = "https://example.com/other.png"
        assert item.url == "https://example.com/other.png"

    def test_the_mixin_does_not_define_url(self) -> None:
        assert "url" not in vars(AssetMixin)


class TestReactionFromEvent:
    def test_missing_flags_are_false(self) -> None:
        message = MagicMock()
        message.id = 10
        message.channel_id = 20
        message.guild_id = None
        event: Any = {
            "user_id": "1",
            "channel_id": "20",
            "message_id": "10",
            "emoji": {"id": None, "name": "x"},
            "burst": False,
            "type": 0,
            "me": True,
        }
        reaction = Reaction(message=message, data=event)
        assert reaction.me is True
        assert reaction.burst is False
        assert reaction.me_burst is False


class TestChannelBucketWithoutChannel:
    def test_context_without_a_channel_raises_value_error(self) -> None:
        context: Any = SimpleNamespace(
            channel=None, author=SimpleNamespace(id=1), guild=None
        )
        with pytest.raises(ValueError, match="no channel"):
            BucketType.channel.get_key(context)

    def test_user_bucket_does_not_need_a_channel(self) -> None:
        context: Any = SimpleNamespace(channel=None, author=SimpleNamespace(id=1))
        assert BucketType.user.get_key(context) == 1
