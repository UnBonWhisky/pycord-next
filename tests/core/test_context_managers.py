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
from unittest.mock import AsyncMock

import pytest

from discord.context_managers import Typing, _typing_done_callback


def make_messageable(loop: asyncio.AbstractEventLoop) -> Any:
    channel = SimpleNamespace(
        id=55, _state=SimpleNamespace(http=SimpleNamespace(send_typing=AsyncMock()))
    )
    messageable = SimpleNamespace(
        _state=SimpleNamespace(loop=loop), _get_channel=AsyncMock(return_value=channel)
    )
    return messageable, channel


@pytest.mark.asyncio
async def test_async_with_sends_typing_and_cancels_on_exit() -> None:
    messageable, channel = make_messageable(asyncio.get_running_loop())

    async with Typing(messageable) as typing:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        channel._state.http.send_typing.assert_awaited_with(55)
        assert channel._state.http.send_typing.await_count >= 2
        task = typing.task
        assert not task.done()

    await asyncio.sleep(0)
    assert task.cancelled()
    messageable._get_channel.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_with_resolves_the_channel_in_the_task() -> None:
    messageable, channel = make_messageable(asyncio.get_running_loop())

    with Typing(messageable) as typing:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        channel._state.http.send_typing.assert_awaited_once_with(55)
        task = typing.task

    await asyncio.sleep(0)
    assert task.cancelled()
    messageable._get_channel.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_callback_retrieves_the_task_exception() -> None:
    async def boom() -> None:
        raise RuntimeError("x")

    task = asyncio.ensure_future(boom())
    await asyncio.wait([task])
    task.add_done_callback(_typing_done_callback)
    await asyncio.sleep(0)
    assert isinstance(task.exception(), RuntimeError)

    cancelled = asyncio.ensure_future(asyncio.sleep(10))
    cancelled.cancel()
    await asyncio.wait([cancelled])
    _typing_done_callback(cancelled)
