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

import asyncio
import errno
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from aioresponses import aioresponses

import discord
from discord import DiscordServerError, Forbidden, HTTPException, NotFound, RateLimited
from discord.http import HTTPClient, Route, base
from tests.http.conftest import BASE_URL

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

MESSAGES = f"{BASE_URL}/channels/1/messages"
MESSAGE = f"{BASE_URL}/channels/1/messages/2"
PINS = f"{BASE_URL}/channels/1/pins"
USER = f"{BASE_URL}/users/3"
VIA = {"Via": "1.1 google"}


def messages(channel_id: int = 1) -> Route:
    return Route("GET", "/channels/{channel_id}/messages", channel_id=channel_id)


def message() -> Route:
    return Route(
        "GET",
        "/channels/{channel_id}/messages/{message_id}",
        channel_id=1,
        message_id=2,
    )


def limited(retry_after: float, *, is_global: bool = False) -> dict[str, Any]:
    return {"message": "limited", "retry_after": retry_after, "global": is_global}


@pytest.fixture
def mocked() -> Iterator[aioresponses]:
    with aioresponses() as m:
        yield m


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []

    async def sleep(delay: float) -> None:
        recorded.append(delay)

    monkeypatch.setattr(base, "asyncio", SimpleNamespace(sleep=sleep))
    return recorded


async def test_success(client: HTTPClient, mocked: aioresponses) -> None:
    mocked.get(MESSAGES, payload={"id": "1"})

    assert await client.request(messages()) == {"id": "1"}

    (call,) = next(iter(mocked.requests.values()))
    assert call.kwargs["headers"]["Authorization"] == "Bot token"
    assert call.kwargs["headers"]["User-Agent"] == client.user_agent


async def test_text_response(client: HTTPClient, mocked: aioresponses) -> None:
    mocked.get(MESSAGES, body="plain", content_type="text/plain")

    assert await client.request(messages()) == "plain"


async def test_csv_response(client: HTTPClient, mocked: aioresponses) -> None:
    mocked.get(MESSAGES, body=b"1,2", content_type="text/csv")

    assert await client.request(messages()) == b"1,2"


async def test_reason_and_json_headers(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.post(MESSAGES, payload={})

    await client.request(
        Route("POST", "/channels/{channel_id}/messages", channel_id=1),
        json={"content": "hi"},
        reason="café ok",
    )

    (call,) = next(iter(mocked.requests.values()))
    assert call.kwargs["headers"]["X-Audit-Log-Reason"] == "caf%C3%A9 ok"
    assert call.kwargs["headers"]["Content-Type"] == "application/json"
    assert call.kwargs["data"] == '{"content":"hi"}'


@pytest.mark.parametrize(
    ("status", "error"), [(403, Forbidden), (404, NotFound), (400, HTTPException)]
)
async def test_error_statuses(
    client: HTTPClient,
    mocked: aioresponses,
    status: int,
    error: type[HTTPException],
) -> None:
    mocked.get(MESSAGES, status=status, payload={"message": "no", "code": 5})

    with pytest.raises(error) as raised:
        await client.request(messages())

    assert raised.value.status == status
    assert raised.value.code == 5


async def test_429_waits_and_retries(client: HTTPClient, mocked: aioresponses) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(0.1), headers=VIA)
    mocked.get(MESSAGES, payload={"ok": True})

    started = time.monotonic()
    assert await client.request(messages()) == {"ok": True}

    assert time.monotonic() - started >= 0.09


async def test_429_global_blocks_every_route(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(0.2, is_global=True), headers=VIA)
    mocked.get(MESSAGES, payload={})
    mocked.get(USER, payload={})
    started = time.monotonic()

    first = asyncio.create_task(client.request(messages()))
    await asyncio.sleep(0.05)
    second = asyncio.create_task(
        client.request(Route("GET", "/users/{user_id}", user_id=3))
    )
    await asyncio.gather(first, second)

    assert time.monotonic() - started >= 0.19
    assert client._ratelimiter._global_over.is_set()


async def test_global_rate_limit_is_lifted_when_cancelled(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(30, is_global=True), headers=VIA)

    task = asyncio.create_task(client.request(messages()))
    await asyncio.sleep(0.05)
    assert not client._ratelimiter._global_over.is_set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client._ratelimiter._global_over.is_set()


async def test_exhausted_bucket_defers_next_request(
    client: HTTPClient, mocked: aioresponses
) -> None:
    headers = {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "0.2"}
    mocked.get(MESSAGES, payload={}, headers=headers)
    mocked.get(MESSAGES, payload={})

    await client.request(messages())
    started = time.monotonic()
    await client.request(messages())

    assert time.monotonic() - started >= 0.15


async def test_exhausted_bucket_does_not_block_other_channels(
    client: HTTPClient, mocked: aioresponses
) -> None:
    headers = {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "5"}
    mocked.get(MESSAGES, payload={}, headers=headers)
    mocked.get(f"{BASE_URL}/channels/9/messages", payload={})

    await client.request(messages())
    await asyncio.wait_for(client.request(messages(9)), timeout=1)


async def test_bucket_hash_is_shared_between_routes(
    client: HTTPClient, mocked: aioresponses
) -> None:
    shared = {"X-Ratelimit-Bucket": "abc", "X-Ratelimit-Remaining": "4"}
    exhausted = {
        "X-Ratelimit-Bucket": "abc",
        "X-Ratelimit-Remaining": "0",
        "X-Ratelimit-Reset-After": "0.2",
    }
    mocked.get(MESSAGE, payload={}, headers=shared)
    mocked.get(MESSAGES, payload={}, headers=exhausted)
    mocked.get(MESSAGE, payload={})

    await client.request(message())
    await client.request(messages())
    started = time.monotonic()
    await client.request(message())

    assert time.monotonic() - started >= 0.15


async def test_different_bucket_hashes_do_not_share_a_lock(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGE, payload={}, headers={"X-Ratelimit-Bucket": "one"})
    mocked.get(
        MESSAGES,
        payload={},
        headers={
            "X-Ratelimit-Bucket": "two",
            "X-Ratelimit-Remaining": "0",
            "X-Ratelimit-Reset-After": "5",
        },
    )
    mocked.get(MESSAGE, payload={})

    await client.request(message())
    await client.request(messages())
    await asyncio.wait_for(client.request(message()), timeout=1)


def test_webhooks_do_not_share_a_bucket() -> None:
    def route(webhook_id: int, token: str) -> Route:
        return Route(
            "POST",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=webhook_id,
            webhook_token=token,
        )

    keys = {
        route(1, "a").bucket,
        route(2, "a").bucket,
        route(1, "b").bucket,
    }
    assert len(keys) == 3
    assert route(1, "a").bucket == route(1, "a").bucket


async def test_5xx_is_retried_with_backoff(
    client: HTTPClient, mocked: aioresponses, sleeps: list[float]
) -> None:
    mocked.get(MESSAGES, status=502, payload={})
    mocked.get(MESSAGES, status=503, payload={})
    mocked.get(MESSAGES, payload={"ok": True})

    assert await client.request(messages()) == {"ok": True}
    assert sleeps == [1, 3]


async def test_5xx_gives_up_after_five_tries(
    client: HTTPClient, mocked: aioresponses, sleeps: list[float]
) -> None:
    mocked.get(MESSAGES, status=500, payload={"message": "boom"}, repeat=True)

    with pytest.raises(DiscordServerError):
        await client.request(messages())

    assert sleeps == [1, 3, 5, 7, 9]
    assert len(next(iter(mocked.requests.values()))) == 5


@pytest.mark.parametrize("code", [errno.ECONNRESET, 54, 10054])
async def test_connection_reset_is_retried(
    client: HTTPClient, mocked: aioresponses, sleeps: list[float], code: int
) -> None:
    mocked.get(MESSAGES, exception=OSError(code, "reset"))
    mocked.get(MESSAGES, payload={"ok": True})

    assert await client.request(messages()) == {"ok": True}
    assert sleeps == [1]


async def test_other_os_errors_are_raised(
    client: HTTPClient, mocked: aioresponses, sleeps: list[float]
) -> None:
    mocked.get(MESSAGES, exception=OSError(errno.ENOENT, "missing"))

    with pytest.raises(OSError, match="missing"):
        await client.request(messages())

    assert sleeps == []


async def test_cloudflare_429_is_not_retried(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, body="banned", content_type="text/html")

    with pytest.raises(HTTPException) as raised:
        await client.request(messages())

    assert raised.value.status == 429
    assert not isinstance(raised.value, RateLimited)
    assert len(next(iter(mocked.requests.values()))) == 1


@pytest_asyncio.fixture
async def impatient() -> AsyncIterator[HTTPClient]:
    http = HTTPClient(max_ratelimit_timeout=1)
    http.recreate()
    yield http
    await http.close()


@pytest.mark.parametrize("is_global", [False, True])
async def test_long_429_raises_rate_limited(
    impatient: HTTPClient, mocked: aioresponses, is_global: bool
) -> None:
    mocked.get(
        MESSAGES, status=429, payload=limited(30, is_global=is_global), headers=VIA
    )

    with pytest.raises(RateLimited) as raised:
        await impatient.request(messages())

    assert raised.value.retry_after == 30
    assert raised.value.is_global is is_global
    assert raised.value.route.path == "/channels/{channel_id}/messages"
    assert impatient._ratelimiter._global_over.is_set()
    assert not impatient._ratelimiter._locks.get(
        messages().bucket, asyncio.Lock()
    ).locked()


async def test_short_429_still_sleeps(
    impatient: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(0.05), headers=VIA)
    mocked.get(MESSAGES, payload={"ok": True})

    assert await impatient.request(messages()) == {"ok": True}


async def test_long_exhausted_bucket_raises_before_sending(
    impatient: HTTPClient, mocked: aioresponses
) -> None:
    headers = {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "30"}
    mocked.get(MESSAGES, payload={}, headers=headers)

    await impatient.request(messages())
    with pytest.raises(RateLimited) as raised:
        await impatient.request(messages())

    assert 28 < raised.value.retry_after <= 30
    assert not raised.value.is_global
    assert len(next(iter(mocked.requests.values()))) == 1


async def test_long_global_limit_raises_for_other_routes(
    impatient: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(30, is_global=True), headers=VIA)

    impatient._ratelimiter._global_over.clear()
    impatient._ratelimiter._global_reset_at = asyncio.get_running_loop().time() + 30
    with pytest.raises(RateLimited) as raised:
        await impatient.request(messages())

    assert raised.value.is_global


async def test_without_timeout_long_waits_are_not_refused(
    client: HTTPClient, mocked: aioresponses
) -> None:
    mocked.get(MESSAGES, status=429, payload=limited(30), headers=VIA)

    task = asyncio.create_task(client.request(messages()))
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_rate_limited_is_a_public_discord_exception() -> None:
    error = RateLimited(2.5, messages(), is_global=True)

    assert discord.RateLimited is RateLimited
    assert isinstance(error, discord.DiscordException)
    assert (error.retry_after, error.is_global) == (2.5, True)
    assert "2.50" in str(error)
