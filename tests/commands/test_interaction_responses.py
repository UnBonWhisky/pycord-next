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


"""Interaction responses, original response and followups on both cache backends, HTTP mocked."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from discord import types as t
from discord.interactions import InteractionMessage
from discord.member import Member
from discord.webhook.async_ import AsyncWebhookAdapter, WebhookMessage
from tests.commands.interaction_support import (
    MEMBER_ID,
    add_member,
    backend_world,
    is_memory,
    make_context,
)

if TYPE_CHECKING:
    from tests.models.context import World

__all__ = ("backend_world",)

MESSAGE_ID = 7900


def message_payload(world: World, message_id: int = MESSAGE_ID, **fields: Any) -> Any:
    payload = world.payload(
        t.message.Message,
        id=str(message_id),
        type=0,
        mentions=[],
        mention_roles=[],
        reactions=[],
        guild_id=str(world.guild.id),
        channel_id=str(world.channel.id),
        author={**world.payload(t.user.User), "id": str(MEMBER_ID)},
        **fields,
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "poll",
        "thread",
        "call",
        "interaction",
        "interaction_metadata",
        "member",
    ):
        payload.pop(key, None)
    return payload


class FakeWebhookAPI:
    def __init__(self, world: World) -> None:
        self.world = world
        self.calls: list[tuple[str, str]] = []

    async def request(self, route: Any, *_args: Any, **_kwargs: Any) -> Any:
        self.calls.append((route.method, route.url))
        if route.method == "POST" and route.url.endswith("/callback"):
            return {
                "interaction": {"id": "1", "type": 2},
                "resource": {
                    "type": 4,
                    "message": message_payload(self.world),
                },
            }
        if route.method == "POST":
            return message_payload(self.world, MESSAGE_ID + 1)
        return message_payload(self.world)


@pytest.fixture
def api(backend_world: World, monkeypatch: pytest.MonkeyPatch) -> FakeWebhookAPI:
    fake = FakeWebhookAPI(backend_world)
    monkeypatch.setattr(AsyncWebhookAdapter, "request", fake.request)
    return fake


def author_matches(world: World, message: Any, cached: Member | None) -> None:
    assert isinstance(message.author, Member)
    assert message.author.id == MEMBER_ID
    if cached is not None and is_memory(world):
        assert message.author is cached


def test_send_message_builds_the_original_response(
    backend_world: World, api: FakeWebhookAPI
) -> None:
    cached = add_member(backend_world)
    ctx = make_context(backend_world)
    backend_world.run(ctx.respond("hello"))
    message = backend_world.run(ctx.interaction.original_response())
    assert isinstance(message, InteractionMessage)
    assert message.id == MESSAGE_ID
    author_matches(backend_world, message, cached)
    assert [method for method, _ in api.calls] == ["POST"]


def test_original_response_is_fetched_and_populated(
    backend_world: World, api: FakeWebhookAPI
) -> None:
    cached = add_member(backend_world)
    ctx = make_context(backend_world)
    message = backend_world.run(ctx.interaction.original_response())
    assert isinstance(message, InteractionMessage)
    author_matches(backend_world, message, cached)
    assert backend_world.run(ctx.interaction.original_response()) is message
    assert api.calls == [("GET", api.calls[0][1])]


def test_edit_original_response(backend_world: World, api: FakeWebhookAPI) -> None:
    cached = add_member(backend_world)
    ctx = make_context(backend_world)
    message = backend_world.run(ctx.interaction.edit_original_response(content="x"))
    assert isinstance(message, InteractionMessage)
    author_matches(backend_world, message, cached)
    assert api.calls[0][0] == "PATCH"


@pytest.mark.usefixtures("api")
def test_followup(backend_world: World) -> None:
    cached = add_member(backend_world)
    ctx = make_context(backend_world)
    backend_world.run(ctx.respond("first"))
    message = backend_world.run(ctx.followup.send("second", wait=True))
    assert isinstance(message, WebhookMessage)
    assert message.id == MESSAGE_ID + 1
    author_matches(backend_world, message, cached)
