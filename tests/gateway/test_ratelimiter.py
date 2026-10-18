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
import time

import pytest

from discord.gateway import GatewayRatelimiter, IdentifyLimiter


def test_gateway_ratelimiter_counts_down() -> None:
    limiter = GatewayRatelimiter(count=3, per=60.0)

    assert [limiter.get_delay() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.remaining == 0
    assert limiter.is_ratelimited()
    assert 0 < limiter.get_delay() <= 60.0


def test_gateway_ratelimiter_resets_after_the_window() -> None:
    limiter = GatewayRatelimiter(count=1, per=0.05)
    limiter.get_delay()
    assert limiter.is_ratelimited()

    time.sleep(0.06)

    assert not limiter.is_ratelimited()
    assert limiter.get_delay() == 0.0


async def test_gateway_ratelimiter_block_waits() -> None:
    limiter = GatewayRatelimiter(count=1, per=0.1)
    start = time.monotonic()
    await limiter.block()
    await limiter.block()
    assert time.monotonic() - start >= 0.09


def test_the_default_leaves_room_for_heartbeats() -> None:
    assert GatewayRatelimiter().max == 110


def test_identify_buckets() -> None:
    limiter = IdentifyLimiter(max_concurrency=4)
    assert [limiter.bucket(shard) for shard in range(10)] == [
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
    ]
    assert limiter.bucket(None) == 0


def test_identify_max_concurrency_is_validated() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        IdentifyLimiter(max_concurrency=0)
    limiter = IdentifyLimiter()
    limiter.max_concurrency = 16
    assert limiter.max_concurrency == 16


async def test_identify_slots_of_a_bucket_are_spaced() -> None:
    limiter = IdentifyLimiter(max_concurrency=1, per=0.1)
    times: list[float] = []

    async def identify(shard_id: int) -> None:
        async with limiter.slot(shard_id):
            times.append(time.monotonic())

    await asyncio.gather(*(identify(shard) for shard in range(3)))

    assert times[1] - times[0] >= 0.09
    assert times[2] - times[1] >= 0.09


async def test_identify_slots_of_different_buckets_do_not_wait() -> None:
    limiter = IdentifyLimiter(max_concurrency=2, per=0.3)
    times: dict[int, float] = {}

    async def identify(shard_id: int) -> None:
        async with limiter.slot(shard_id):
            times[shard_id] = time.monotonic()

    await asyncio.gather(identify(0), identify(1), identify(2), identify(3))

    assert abs(times[0] - times[1]) < 0.1
    assert abs(times[2] - times[3]) < 0.1
    assert times[2] - times[0] >= 0.29
    assert times[3] - times[1] >= 0.29


async def test_the_slot_counts_from_the_end_of_the_identify() -> None:
    limiter = IdentifyLimiter(per=0.1)
    async with limiter.slot(0):
        await asyncio.sleep(0.1)
    start = time.monotonic()
    async with limiter.slot(0):
        pass
    assert time.monotonic() - start >= 0.09


async def test_the_slot_is_released_on_errors() -> None:
    limiter = IdentifyLimiter(per=0.01)
    with pytest.raises(RuntimeError):
        async with limiter.slot(0):
            raise RuntimeError
    async with limiter.slot(0):
        pass
