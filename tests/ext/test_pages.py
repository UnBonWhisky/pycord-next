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
from unittest.mock import AsyncMock, Mock

import pytest

import discord
from discord.ext import commands, pages


def sent_message() -> Mock:
    message = Mock(spec=discord.Message)
    message.flags = discord.MessageFlags()
    return message


def interaction(*, done: bool = False) -> Mock:
    result = Mock(spec=discord.Interaction)
    result.user = SimpleNamespace(id=1)
    result.response = Mock()
    result.response.is_done = Mock(return_value=done)
    result.response.defer = AsyncMock()
    result.followup = Mock()
    result.followup.send = AsyncMock()
    result.followup.edit_message = AsyncMock()
    return result


def context() -> Mock:
    ctx = Mock(spec=commands.Context)
    ctx.author = SimpleNamespace(id=7)
    ctx.send = AsyncMock(return_value=sent_message())
    return ctx


class TestPaginator:
    async def test_pages_and_buttons(self) -> None:
        paginator = pages.Paginator(pages=["one", "two", "three"])
        assert paginator.page_count == 2
        assert paginator.current_page == 0
        buttons = paginator.update_buttons()
        assert {"first", "prev", "page_indicator", "next", "last"} <= set(buttons)
        assert paginator.buttons["prev"]["object"].disabled
        assert not paginator.buttons["next"]["object"].disabled

    async def test_embed_and_page_objects(self) -> None:
        paginator = pages.Paginator(
            pages=[
                pages.Page(content="text", embeds=[discord.Embed(title="e")]),
                discord.Embed(title="solo"),
                [discord.Embed(title="a"), discord.Embed(title="b")],
            ]
        )
        assert paginator.get_page_content(paginator.pages[0]).content == "text"
        solo = paginator.get_page_content(paginator.pages[1])
        assert solo.embeds[0].title == "solo"
        assert len(paginator.get_page_content(paginator.pages[2]).embeds) == 2

    async def test_goto_page_edits_the_message(self) -> None:
        paginator = pages.Paginator(pages=["one", "two"])
        paginator.message = Mock()
        paginator.message.edit = AsyncMock()
        await paginator.goto_page(1)
        assert paginator.current_page == 1
        assert paginator.message.edit.await_args.kwargs["content"] == "two"

    async def test_goto_page_through_an_interaction(self) -> None:
        paginator = pages.Paginator(pages=["one", "two"])
        paginator.message = SimpleNamespace(id=1500000000000000001)
        target = interaction()
        await paginator.goto_page(1, interaction=target)
        target.response.defer.assert_awaited_once()
        assert target.followup.edit_message.await_args.kwargs["content"] == "two"

    async def test_interaction_check_follows_the_invoker(self) -> None:
        paginator = pages.Paginator(pages=["one"], author_check=True)
        paginator.user = SimpleNamespace(id=1)
        same = interaction()
        same.user = paginator.user
        other = interaction()
        other.user = SimpleNamespace(id=2)
        assert await paginator.interaction_check(same)
        assert not await paginator.interaction_check(other)
        paginator.usercheck = False
        assert await paginator.interaction_check(other)


class TestPaginatorDelivery:
    async def test_send_to_the_context_channel(self) -> None:
        ctx = context()
        paginator = pages.Paginator(pages=["one", "two"])
        result = await paginator.send(ctx)
        assert result is ctx.send.return_value
        assert paginator.message is result
        assert paginator.user is ctx.author
        assert ctx.send.await_args.kwargs["view"] is paginator
        assert ctx.send.await_args.kwargs["content"] == "one"

    async def test_send_to_another_target(self) -> None:
        ctx = context()
        target = Mock(spec=discord.abc.Messageable)
        target.send = AsyncMock(return_value=sent_message())
        paginator = pages.Paginator(pages=["one"])
        await paginator.send(ctx, target=target, target_message="moved")
        ctx.send.assert_awaited_once()
        assert ctx.send.await_args.args[0] == "moved"
        target.send.assert_awaited_once()
        assert paginator.message is target.send.return_value

    async def test_send_rejects_other_contexts(self) -> None:
        with pytest.raises(TypeError):
            await pages.Paginator(pages=["one"]).send(object())

    async def test_respond_to_an_interaction(self) -> None:
        target = interaction()
        original = sent_message()
        returned = Mock(spec=discord.Interaction)
        returned.original_response = AsyncMock(return_value=original)
        target.response.send_message = AsyncMock(return_value=returned)
        paginator = pages.Paginator(pages=["one"])
        result = await paginator.respond(target)
        assert result is original
        assert paginator.user is target.user
        assert target.response.send_message.await_args.kwargs["view"] is paginator

    async def test_respond_after_the_interaction_was_answered(self) -> None:
        target = interaction(done=True)
        followup = sent_message()
        full = sent_message()
        followup.channel = Mock()
        followup.channel.fetch_message = AsyncMock(return_value=full)
        target.followup.send = AsyncMock(return_value=followup)
        paginator = pages.Paginator(pages=["one"])
        result = await paginator.respond(target)
        assert result is full
        followup.channel.fetch_message.assert_awaited_once_with(followup.id)

    async def test_ephemeral_responses_are_not_refetched(self) -> None:
        target = interaction(done=True)
        followup = sent_message()
        target.followup.send = AsyncMock(return_value=followup)
        paginator = pages.Paginator(pages=["one"], timeout=60)
        assert await paginator.respond(target, ephemeral=True) is followup

    async def test_respond_rejects_other_objects(self) -> None:
        with pytest.raises(TypeError):
            await pages.Paginator(pages=["one"]).respond(object())

    async def test_edit_replaces_an_existing_message(self) -> None:
        paginator = pages.Paginator(pages=["one"])
        edited = sent_message()
        message = sent_message()
        message.edit = AsyncMock(return_value=edited)
        result = await paginator.edit(message, user=SimpleNamespace(id=1))
        assert result is edited
        assert message.edit.await_args.kwargs["view"] is paginator
