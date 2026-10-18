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

import pytest
from aioresponses import aioresponses

import discord
from discord import (
    Client,
    Forbidden,
    HTTPException,
    InvalidArgument,
    LoginFailure,
    NotFound,
)
from discord.http import API_VERSION, HTTPClient, Route, parse_response
from tests.http.conftest import BASE_URL


class CustomHTTPClient(HTTPClient):
    pass


async def test_recreate_works_before_login() -> None:
    http = HTTPClient()

    http.recreate()
    session = http._session

    assert not session.closed
    http.recreate()
    assert http._session is session
    await http.close()


async def test_recreate_replaces_a_closed_session() -> None:
    http = HTTPClient()
    http.recreate()
    first = http._session
    await first.close()

    http.recreate()

    assert http._session is not first
    assert not http._session.closed
    await http.close()


async def test_close_resets_the_session() -> None:
    http = HTTPClient()
    http.recreate()
    session = http._session

    await http.close()
    await http.close()

    assert session.closed
    assert not http._session


async def test_static_login_closes_the_previous_session() -> None:
    http = HTTPClient()
    http.recreate()
    previous = http._session

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/users/@me", payload={"id": "1"})
        assert await http.static_login("secret") == {"id": "1"}

    assert previous.closed
    assert http._session is not previous
    assert http.token == "secret"  # noqa: S105
    await http.close()


async def test_static_login_rejects_a_bad_token() -> None:
    http = HTTPClient()
    http.token = "old"  # noqa: S105

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/users/@me", status=401, payload={"message": "401"})
        with pytest.raises(LoginFailure):
            await http.static_login("bad")

    assert http.token == "old"  # noqa: S105
    await http.close()


@pytest.mark.parametrize(
    ("status", "error"), [(404, NotFound), (403, Forbidden), (500, HTTPException)]
)
async def test_get_from_cdn(
    client: HTTPClient, status: int, error: type[HTTPException]
) -> None:
    url = "https://cdn.discordapp.com/icons/1/a.png"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=b"png")
        mocked.get(url, status=status, body=b"")
        assert await client.get_from_cdn(url) == b"png"
        with pytest.raises(error):
            await client.get_from_cdn(url)


async def test_stream_from_cdn(client: HTTPClient) -> None:
    url = "https://cdn.discordapp.com/icons/1/a.png"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=b"abcdef")
        chunks = [chunk async for chunk in client.stream_from_cdn(url, 4)]
        mocked.get(url, status=404, body=b"")
        with pytest.raises(NotFound):
            async for _ in client.stream_from_cdn(url, 4):
                pass

    assert b"".join(chunks) == b"abcdef"
    with pytest.raises(InvalidArgument):
        async for _ in client.stream_from_cdn(url, 0):
            pass


async def test_client_uses_the_default_http_class() -> None:
    client = Client()

    assert type(client.http) is HTTPClient
    assert client.http._ratelimiter.max_timeout is None


async def test_client_accepts_a_custom_http_class() -> None:
    client = Client(
        http_cls=CustomHTTPClient, max_ratelimit_timeout=2.5, proxy="http://p"
    )

    assert type(client.http) is CustomHTTPClient
    assert client.http._ratelimiter.max_timeout == 2.5
    assert client.http.proxy == "http://p"
    assert client._connection.http is client.http


def test_public_http_imports() -> None:
    assert API_VERSION == 10
    assert HTTPClient is discord.HTTPClient
    assert discord.Route is Route
    assert callable(parse_response)
