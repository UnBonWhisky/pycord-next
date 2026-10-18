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

from typing import Any

import pytest

from discord.gateway import SessionStartLimit
from discord.http import HTTPClient
from discord.http.route import API_VERSION


class Recorder:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    async def __call__(self, *_: Any, **__: Any) -> dict[str, Any]:
        return self.response


def http_with(response: dict[str, Any]) -> HTTPClient:
    http = HTTPClient()
    http.request = Recorder(response)  # type: ignore[method-assign]
    return http


async def test_get_gateway_defaults_to_zlib_stream() -> None:
    http = http_with({"url": "wss://gateway.discord.gg"})
    assert (
        await http.get_gateway()
        == f"wss://gateway.discord.gg?encoding=json&v={API_VERSION}&compress=zlib-stream"
    )


@pytest.mark.parametrize(
    ("kwargs", "suffix"),
    [
        ({"compress": "zstd-stream"}, "&compress=zstd-stream"),
        ({"compress": None}, ""),
        ({"zlib": False}, ""),
    ],
)
async def test_get_gateway_compression(kwargs: dict[str, Any], suffix: str) -> None:
    http = http_with({"url": "wss://gateway.discord.gg"})
    assert (
        await http.get_gateway(**kwargs)
        == f"wss://gateway.discord.gg?encoding=json&v={API_VERSION}{suffix}"
    )


async def test_get_bot_gateway_info_exposes_the_session_start_limit() -> None:
    limit = {
        "total": 1000,
        "remaining": 990,
        "reset_after": 5000,
        "max_concurrency": 16,
    }
    http = http_with(
        {"url": "wss://gateway.discord.gg", "shards": 4, "session_start_limit": limit}
    )

    info = await http.get_bot_gateway_info(compress="zstd-stream")

    assert info.shards == 4
    assert info.session_start_limit == SessionStartLimit(**limit)
    assert info.url.endswith("&compress=zstd-stream")


async def test_get_bot_gateway_keeps_returning_a_tuple() -> None:
    http = http_with({"url": "wss://gateway.discord.gg", "shards": 2})
    shards, url = await http.get_bot_gateway()
    assert shards == 2
    assert url.endswith("&compress=zlib-stream")
    info = await http.get_bot_gateway_info()
    assert info.session_start_limit == SessionStartLimit()
