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

"""Guild message search."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from aiohttp import ClientResponse
from aioresponses import aioresponses, core as aioresponses_core

import discord
from discord import (
    Member,
    Object,
    SearchAuthors,
    SearchEmbedType,
    SearchHas,
    SearchIndexNotReady,
    SearchSortMode,
    SearchSortOrder,
    TextChannel,
    Thread,
    types as t,
)
from discord.http import HTTPClient

if TYPE_CHECKING:
    from tests.models.context import World

INDEXING = {
    "message": "Index not yet available. Try again later",
    "code": 110000,
    "documents_indexed": 3,
    "retry_after": 2,
}


class Pages:
    def __init__(self, world: World, *pages: Any) -> None:
        self.world = world
        self.pages = list(pages)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, guild_id: int, **params: Any) -> dict[str, Any]:
        self.calls.append({"guild_id": guild_id, **params})
        page = self.pages.pop(0)
        if isinstance(page, dict):
            return page
        return self.result(page)

    def message(self, message_id: int, **fields: Any) -> dict[str, Any]:
        return self.world.payload(
            t.message.Message,
            id=str(message_id),
            channel_id=str(self.world.channel.id),
            **fields,
        )

    def result(self, ids: list[int], total: int | None = None) -> dict[str, Any]:
        return {
            "doing_deep_historical_index": False,
            "total_results": total if total is not None else len(ids),
            "messages": [[self.message(i)] for i in ids],
        }


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return delays


def use(world: World, *pages: Any) -> Pages:
    pages_ = Pages(world, *pages)
    world.state.http.search_guild_messages = pages_
    return pages_


async def test_route_encoding() -> None:
    http = HTTPClient()
    calls: list[tuple[str, dict[str, Any]]] = []

    async def request(route: Any, **kwargs: Any) -> None:
        calls.append((route.path, kwargs))

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    await http.search_guild_messages(
        5,
        limit=25,
        content="hello",
        channel_id=[1, 2],
        has=["image", "-link"],
        pinned=False,
        include_nsfw=True,
        sort_by="relevance",
    )
    assert calls == [
        (
            "/guilds/{guild_id}/messages/search",
            {
                "params": {
                    "limit": 25,
                    "content": "hello",
                    "channel_id": ["1", "2"],
                    "has": ["image", "-link"],
                    "pinned": "false",
                    "include_nsfw": "true",
                    "sort_by": "relevance",
                }
            },
        )
    ]


async def test_documented_query_parameters() -> None:
    http = HTTPClient()
    seen: list[str] = []

    async def request(_route: Any, **kwargs: Any) -> None:
        seen.extend(kwargs["params"])

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    every = {
        "limit": 1,
        "offset": 1,
        "max_id": 1,
        "min_id": 1,
        "slop": 1,
        "content": "c",
        "channel_id": [1],
        "author_type": ["bot"],
        "author_id": [1],
        "mentions": [1],
        "mentions_role_id": [1],
        "mention_everyone": True,
        "replied_to_user_id": [1],
        "replied_to_message_id": [1],
        "pinned": True,
        "has": ["image"],
        "embed_type": ["gif"],
        "embed_provider": ["Tenor"],
        "link_hostname": ["discordapp.com"],
        "attachment_filename": ["a.txt"],
        "attachment_extension": ["txt"],
        "sort_by": "timestamp",
        "sort_order": "asc",
        "include_nsfw": False,
    }
    await http.search_guild_messages(5, **every)
    assert sorted(seen) == sorted(every)


def test_filters() -> None:
    assert SearchAuthors(bot=True, user=False).to_query() == ["bot", "-user"]
    assert SearchAuthors().to_query() == []
    assert SearchHas(image=True, link=False, poll=True, snapshot=False).to_query() == [
        "image",
        "poll",
        "-link",
        "-snapshot",
    ]
    with pytest.raises(TypeError):
        SearchHas(True)  # type: ignore[misc]


async def test_every_filter_is_sent(world: World) -> None:
    pages = use(world, [])
    messages = world.guild.search_messages(
        content="pycord",
        slop=3,
        channels=[world.channel],
        author_types=SearchAuthors(webhook=False),
        authors=[Object(id=1)],
        mentions=[Object(id=2)],
        mention_roles=[Object(id=3)],
        mention_everyone=False,
        replied_to_users=[Object(id=4)],
        replied_to_messages=[Object(id=5), Object(id=6)],
        pinned=True,
        has=SearchHas(embed=True),
        embed_types=[SearchEmbedType.gif, SearchEmbedType.article],
        embed_providers=["Tenor"],
        link_hostnames=["discordapp.com"],
        attachment_filenames=["a.txt"],
        attachment_extensions=["txt"],
        sort_by=SearchSortMode.relevance,
        sort_order=SearchSortOrder.asc,
        include_nsfw=True,
        before=Object(id=9),
        after=Object(id=8),
        offset=50,
        limit=10,
    )
    assert await messages.flatten() == []
    assert pages.calls == [
        {
            "guild_id": world.guild.id,
            "limit": 10,
            "offset": 50,
            "max_id": 9,
            "min_id": 8,
            "slop": 3,
            "content": "pycord",
            "channel_id": [world.channel.id],
            "author_type": ["-webhook"],
            "author_id": [1],
            "mentions": [2],
            "mentions_role_id": [3],
            "mention_everyone": False,
            "replied_to_user_id": [4],
            "replied_to_message_id": [5, 6],
            "pinned": True,
            "has": ["embed"],
            "embed_type": ["gif", "article"],
            "embed_provider": ["Tenor"],
            "link_hostname": ["discordapp.com"],
            "attachment_filename": ["a.txt"],
            "attachment_extension": ["txt"],
            "sort_by": "relevance",
            "sort_order": "asc",
            "include_nsfw": True,
        }
    ]


async def test_defaults_send_nothing_unset(world: World) -> None:
    pages = use(world, [])
    await world.guild.search_messages().flatten()
    assert pages.calls == [{"guild_id": world.guild.id, "limit": 25}]


@pytest.mark.parametrize(
    "filters",
    [
        {"limit": 0},
        {"offset": 9976},
        {"offset": -1},
        {"slop": 101},
        {"content": "x" * 1025},
        {"channels": [Object(id=1)] * 501},
        {"authors": [Object(id=1)] * 101},
        {"mentions": [Object(id=1)] * 101},
        {"mention_roles": [Object(id=1)] * 101},
        {"replied_to_users": [Object(id=1)] * 101},
        {"replied_to_messages": [Object(id=1)] * 101},
        {"embed_providers": ["x"] * 101},
        {"embed_providers": ["x" * 257]},
        {"link_hostnames": ["x" * 257]},
        {"attachment_filenames": ["x" * 1025]},
        {"attachment_extensions": ["x" * 257]},
        {"index_retries": -1},
    ],
)
def test_limits_are_checked(world: World, filters: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        world.guild.search_messages(**filters)


def test_parameters_are_keyword_only(world: World) -> None:
    with pytest.raises(TypeError):
        world.guild.search_messages("text")  # type: ignore[misc]


async def test_replied_to_messages_regression(world: World) -> None:
    pages = use(world, [])
    await world.guild.search_messages(
        replied_to_messages=[Object(id=11), Object(id=12)]
    ).flatten()
    assert pages.calls[0]["replied_to_message_id"] == [11, 12]


async def test_pagination_and_attributes(world: World) -> None:
    first = list(range(100, 125))
    second = list(range(200, 205))
    pages = use(world, first, second)
    pages.pages[0] = pages.result(first, total=30)
    pages.pages[1] = pages.result(second, total=30)
    results = world.guild.search_messages(limit=None)
    assert results.total_results is None
    found = await results.flatten()
    assert [m.id for m in found] == first + second
    assert [(c["limit"], c.get("offset")) for c in pages.calls] == [
        (25, None),
        (25, 25),
    ]
    assert results.total_results == 30
    assert results.doing_deep_historical_index is False
    assert all(isinstance(m, discord.Message) for m in found)
    assert all(m.guild_id == world.guild.id for m in found)
    assert all(m.channel is world.channel for m in found)


async def test_limit_counts_messages(world: World) -> None:
    pages = use(world, list(range(25)))
    pages.pages[0] = pages.result(list(range(25)), total=500)
    pages.pages.append(pages.result(list(range(25, 30)), total=500))
    found = await world.guild.search_messages(limit=30).flatten()
    assert len(found) == 30
    assert [c["limit"] for c in pages.calls] == [25, 5]


async def test_short_pages_do_not_end_the_search(world: World) -> None:
    pages = use(world)
    pages.pages += [pages.result([1, 2], total=60), pages.result([3], total=60)]
    pages.pages.append(pages.result([], total=60))
    found = await world.guild.search_messages(limit=None).flatten()
    assert [m.id for m in found] == [1, 2, 3]
    assert [c.get("offset") for c in pages.calls] == [None, 25, 50]


async def test_duplicates_are_skipped(world: World) -> None:
    pages = use(world)
    pages.pages += [pages.result([1, 2], total=40), pages.result([2, 3], total=40)]
    found = await world.guild.search_messages(limit=None).flatten()
    assert [m.id for m in found] == [1, 2, 3]


async def test_search_stops_at_the_documented_offset(world: World) -> None:
    pages = use(world, pages_for(world, 10000))
    found = await world.guild.search_messages(offset=9975, limit=None).flatten()
    assert len(found) == 1
    assert len(pages.calls) == 1


def pages_for(world: World, total: int) -> dict[str, Any]:
    return Pages(world).result([1], total=total)


async def test_count(world: World) -> None:
    pages = use(world, Pages(world).result([1, 2], total=2))
    results = world.guild.search_messages()
    assert await results.count() == 2
    assert [m.id for m in await results.flatten()] == [1, 2]
    assert len(pages.calls) == 1


async def test_threads_and_uncached_channels(world: World) -> None:
    world.state.cache_fetch = True
    thread_payload = world.payload(
        t.threads.Thread, id="777", guild_id=str(world.guild.id)
    )
    pages = use(world)
    result = pages.result([1, 2, 3])
    result["messages"][0][0]["channel_id"] = "777"
    result["messages"][1][0]["channel_id"] = "888"
    result["threads"] = [thread_payload]
    pages.pages.append(result)
    found = await world.guild.search_messages().flatten()
    assert isinstance(found[0].channel, Thread)
    assert found[0].channel.id == 777
    assert isinstance(found[1].channel, discord.PartialMessageable)
    assert found[1].channel.id == 888
    assert isinstance(found[2].channel, TextChannel)


async def test_partial_guild_searches(world: World) -> None:
    pages = use(world, [])
    await world.guild.search_messages().flatten()
    partial = discord.PartialGuild(state=world.state, id=world.guild.id)
    pages.pages.append(Pages(world).result([]))
    await partial.search_messages(content="x").flatten()
    assert pages.calls[1]["content"] == "x"


async def test_indexing_is_retried(world: World, sleeps: list[float]) -> None:
    pages = use(world, INDEXING, {**INDEXING, "retry_after": 0}, [1])
    pages.pages[2] = Pages(world).result([1])
    found = await world.guild.search_messages().flatten()
    assert [m.id for m in found] == [1]
    assert sleeps == [2, 1.0]
    assert len(pages.calls) == 3


async def test_indexing_gives_up(world: World, sleeps: list[float]) -> None:
    pages = use(world, *[INDEXING] * 3)
    with pytest.raises(SearchIndexNotReady) as error:
        await world.guild.search_messages(index_retries=2).flatten()
    assert error.value.retry_after == 2
    assert error.value.documents_indexed == 3
    assert len(pages.calls) == 3
    assert sleeps == [2, 2]


async def test_indexing_without_retries(world: World, sleeps: list[float]) -> None:
    use(world, INDEXING)
    with pytest.raises(SearchIndexNotReady):
        await world.guild.search_messages(index_retries=0).flatten()
    assert sleeps == []


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **filters: Any) -> str:
        self.calls.append(filters)
        return "iterator"


async def test_shortcuts(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(
        discord.Guild, "search_messages", lambda _self, **f: recorder(**f)
    )
    member: Member = world.member
    assert member.search_messages(content="a") == "iterator"
    member.search_replies()
    member.search_mentions()
    world.channel.search_messages(pinned=True)
    world.message.search_replies(limit=3)
    role = await world.guild.get_role(world.guild.id)
    assert role is not None
    role.search_mentions()
    assert recorder.calls == [
        {"authors": [member], "content": "a"},
        {"replied_to_users": [member]},
        {"mentions": [member]},
        {"channels": [world.channel], "pinned": True},
        {"replied_to_messages": [world.message], "limit": 3},
        {"mention_roles": [role]},
    ]


def test_message_without_guild_cannot_search(world: World) -> None:
    payload = world.payload(t.message.Message)
    payload.pop("guild_id", None)
    dm = discord.Message(
        state=world.state,
        channel=discord.PartialMessageable(world.state, 1),
        data=payload,
    )
    with pytest.raises(ValueError, match="guild"):
        dm.search_replies()


@pytest.fixture
def _aioresponses_supports_new_aiohttp(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response(ClientResponse):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(aioresponses_core, "ClientResponse", Response)


@pytest.mark.usefixtures("_aioresponses_supports_new_aiohttp")
async def test_wire_format() -> None:
    http = HTTPClient()
    http.token = "token"  # noqa: S105
    http.recreate()
    url = re.compile(r"^https://discord\.com/api/v10/guilds/5/messages/search\?.*$")
    with aioresponses() as mocked:
        mocked.get(url, status=202, payload=INDEXING)
        body = await http.search_guild_messages(
            5,
            content="a b",
            channel_id=[1, 2],
            has=["image", "-link"],
            pinned=True,
            include_nsfw=False,
        )
        (request,) = mocked.requests
    await http.close()
    assert body == INDEXING
    query = request[1].query_string
    assert sorted(query.split("&")) == [
        "channel_id=1",
        "channel_id=2",
        "content=a b",
        "has=-link",
        "has=image",
        "include_nsfw=false",
        "pinned=true",
    ]
