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

"""Get Current User Guilds shard parameter."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from discord import Client, ClientException, HTTPException
from discord.client import GuildIterator
from discord.gateway import SessionStartLimit

if TYPE_CHECKING:
    from discord.http import HTTPClient


class FakeResponse:
    status = 400
    reason = "Bad Request"


class FakeHTTP:
    def __init__(self, shards: dict[int | None, list[int]], *, strict: bool = False):
        self.shards = shards
        self.strict = strict
        self.calls: list[dict[str, Any]] = []

    async def get_guilds(
        self, limit: int, *, shard: int | None = None, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self.calls.append({"limit": limit, "shard": shard, **kwargs})
        if self.strict and shard is None:
            raise HTTPException(FakeResponse(), {"code": 0, "message": "Bad Request"})  # pyright: ignore[reportArgumentType]
        ids = self.shards.get(shard, [])
        if "after" in kwargs and kwargs["after"] is not None:
            ids = [i for i in ids if i > kwargs["after"]]
        return [{"id": str(i)} for i in ids[:limit]]


def make_bot(http: FakeHTTP, max_concurrency: int | None = 2) -> Any:
    limit = (
        SessionStartLimit(
            total=1000, remaining=1000, reset_after=0, max_concurrency=max_concurrency
        )
        if max_concurrency is not None
        else None
    )
    return SimpleNamespace(
        http=http, _connection=None, session_start_limit=limit, fetch_guilds=None
    )


@pytest.fixture(autouse=True)
def _plain_guilds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GuildIterator, "create_guild", lambda _, data: int(data["id"]))


async def test_route_sends_shard(http: HTTPClient) -> None:
    calls: list[dict[str, Any]] = []

    async def request(_route: Any, **kwargs: Any) -> list[Any]:
        calls.append(kwargs)
        return []

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    await http.get_guilds(100, shard=3)
    await http.get_guilds(100)
    assert calls[0]["params"]["shard"] == 3
    assert "shard" not in calls[1]["params"]


def test_client_signature_is_keyword_only() -> None:
    parameters = inspect.signature(Client.fetch_guilds).parameters
    for name in ("shard", "all_shards"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[name].default in (None, False)


async def test_shard_is_forwarded() -> None:
    http = FakeHTTP({0: [1], 1: [2, 3]})
    guilds = await GuildIterator(make_bot(http), 100, shard=1).flatten()
    assert guilds == [3, 2] or sorted(guilds) == [2, 3]
    assert {call["shard"] for call in http.calls} == {1}


async def test_no_shard_is_not_sent() -> None:
    http = FakeHTTP({None: [1]})
    assert await GuildIterator(make_bot(http), 100).flatten() == [1]
    assert http.calls[0]["shard"] is None


@pytest.mark.parametrize("shard", [-1, 2, 10])
async def test_shard_out_of_range(shard: int) -> None:
    http = FakeHTTP({})
    with pytest.raises(ValueError, match="max_concurrency"):
        await GuildIterator(make_bot(http, 2), 100, shard=shard).flatten()
    assert http.calls == []


async def test_shard_range_unchecked_without_session_start_limit() -> None:
    http = FakeHTTP({5: [1]})
    assert await GuildIterator(make_bot(http, None), 100, shard=5).flatten() == [1]


async def test_all_shards_visits_every_shard() -> None:
    http = FakeHTTP({0: [1, 2], 1: [3], 2: [4]})
    guilds = await GuildIterator(make_bot(http, 3), None, all_shards=True).flatten()
    assert sorted(guilds) == [1, 2, 3, 4]
    assert [call["shard"] for call in http.calls if call["limit"]] == [0, 1, 2]


async def test_all_shards_respects_limit() -> None:
    http = FakeHTTP({0: [1, 2], 1: [3, 4]})
    guilds = await GuildIterator(make_bot(http, 2), 3, all_shards=True).flatten()
    assert len(guilds) == 3


async def test_all_shards_needs_session_start_limit() -> None:
    with pytest.raises(ClientException):
        await GuildIterator(make_bot(FakeHTTP({}), None), 5, all_shards=True).flatten()


def test_shard_and_all_shards_are_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        GuildIterator(make_bot(FakeHTTP({})), 5, shard=0, all_shards=True)


async def test_missing_shard_error_message() -> None:
    http = FakeHTTP({}, strict=True)
    with pytest.raises(HTTPException, match="large bot sharding") as info:
        await GuildIterator(make_bot(http), 100).flatten()
    assert info.value.status == 400
    assert "large bot sharding" in info.value.text
