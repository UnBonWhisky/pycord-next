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
from types import SimpleNamespace
from typing import Any

import pytest

from discord.commands.cooldowns import (
    BucketType,
    Cooldown,
    CooldownMapping,
    DynamicCooldownMapping,
    MaxConcurrency,
    _Semaphore,
)


def message(
    author: int = 1,
    guild: int | None = 10,
    channel: int = 20,
) -> Any:
    return SimpleNamespace(
        author=SimpleNamespace(id=author),
        guild=None if guild is None else SimpleNamespace(id=guild),
        channel=SimpleNamespace(id=channel),
    )


def test_bucket_type_keys() -> None:
    msg = message()
    assert BucketType.default.get_key(msg) is None
    assert BucketType.user.get_key(msg) == 1
    assert BucketType.guild.get_key(msg) == 10
    assert BucketType.guild.get_key(message(guild=None)) == 1
    assert BucketType.member.get_key(msg) == (10, 1)
    assert BucketType.member.get_key(message(guild=None)) == (None, 1)
    assert BucketType.channel.get_key(msg) == 20


def test_cooldown_tokens_and_representation() -> None:
    cooldown = Cooldown(2, 60)
    assert cooldown.get_tokens() == 2
    assert cooldown.get_tokens(current=1.0) == 2
    cooldown.update_rate_limit(100.0)
    cooldown.update_rate_limit(101.0)
    assert cooldown.get_tokens(102.0) == 0
    assert cooldown.get_tokens(1000.0) == 2
    assert repr(cooldown).startswith("<Cooldown rate: 2 per: 60")


def test_cooldown_mapping_copies_and_buckets() -> None:
    mapping = CooldownMapping(Cooldown(1, 10), BucketType.user)
    first = mapping.get_bucket(message(author=1))
    first.update_rate_limit()
    assert mapping.get_bucket(message(author=1)) is first
    assert mapping.get_bucket(message(author=2)) is not first
    clone = mapping.copy()
    assert clone is not mapping
    assert clone._cache == mapping._cache
    assert clone.valid

    default = CooldownMapping(Cooldown(1, 10), BucketType.default)
    assert default.get_bucket(message()) is default._cooldown

    with pytest.raises(TypeError, match="must be a BucketType or callable"):
        CooldownMapping(Cooldown(1, 10), 5)  # type: ignore[arg-type]


def test_dynamic_cooldown_mapping() -> None:
    created: list[Any] = []

    def factory(msg: Any) -> Cooldown:
        created.append(msg)
        return Cooldown(1, 5)

    mapping = DynamicCooldownMapping(factory, BucketType.user)
    assert mapping.valid is True
    bucket = mapping.get_bucket(message())
    assert isinstance(bucket, Cooldown)
    assert len(created) == 1
    clone = mapping.copy()
    assert isinstance(clone, DynamicCooldownMapping)
    assert clone._cache == mapping._cache


async def test_semaphore_blocks_and_wakes_waiters() -> None:
    semaphore = _Semaphore(1)
    assert repr(semaphore) == "<_Semaphore value=1 waiters=0>"
    assert semaphore.locked() is False
    assert await semaphore.acquire() is True
    assert semaphore.locked() is True
    assert await semaphore.acquire() is False

    waiter = asyncio.ensure_future(semaphore.acquire(wait=True))
    await asyncio.sleep(0)
    assert repr(semaphore) == "<_Semaphore value=0 waiters=1>"
    assert semaphore.is_active()
    semaphore.release()
    assert await waiter is True
    assert semaphore.locked()


async def test_cancelled_waiters_pass_the_slot_on() -> None:
    semaphore = _Semaphore(1)
    await semaphore.acquire()
    cancelled = asyncio.ensure_future(semaphore.acquire(wait=True))
    survivor = asyncio.ensure_future(semaphore.acquire(wait=True))
    await asyncio.sleep(0)
    cancelled.cancel()
    semaphore.release()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert await survivor is True

    semaphore.wake_up()
    semaphore2 = _Semaphore(1)
    await semaphore2.acquire()
    first = asyncio.ensure_future(semaphore2.acquire(wait=True))
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.sleep(0)
    semaphore2.wake_up()


async def test_max_concurrency_acquire_and_release() -> None:
    from discord.ext.commands.errors import MaxConcurrencyReached

    concurrency = MaxConcurrency(1, per=BucketType.user, wait=False)
    assert (
        repr(concurrency)
        == "<MaxConcurrency per=<BucketType.user: 1> number=1 wait=False>"
    )
    clone = concurrency.copy()
    assert (clone.number, clone.per, clone.wait) == (1, BucketType.user, False)
    msg = message()
    assert concurrency.get_key(msg) == 1

    await concurrency.acquire(msg)
    with pytest.raises(MaxConcurrencyReached):
        await concurrency.acquire(msg)
    await concurrency.release(msg)
    assert concurrency._mapping == {}
    await concurrency.release(msg)
    await concurrency.acquire(message(author=2))
    await concurrency.release(message(author=2))


def test_max_concurrency_validation() -> None:
    with pytest.raises(ValueError, match="cannot be less than 1"):
        MaxConcurrency(0, per=BucketType.user, wait=False)
    with pytest.raises(TypeError, match="must be of type BucketType"):
        MaxConcurrency(1, per="user", wait=False)  # type: ignore[arg-type]
