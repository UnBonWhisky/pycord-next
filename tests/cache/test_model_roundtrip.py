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

import copy
from typing import TYPE_CHECKING, Any

import pytest

from discord.cache import ModelSerializer
from tests.models.context import provide
from tests.models.discovery import ModelCase, discover
from tests.payloads.generator import Variant, variants

if TYPE_CHECKING:
    from tests.models.context import World

CASES, _ = discover()
CACHED = {
    "user.User",
    "member.Member",
    "member.VoiceState",
    "message.Message",
    "role.Role",
    "emoji.GuildEmoji",
    "emoji.AppEmoji",
    "sticker.GuildSticker",
    "scheduled_events.ScheduledEvent",
    "stage_instance.StageInstance",
    "soundboard.SoundboardSound",
    "threads.Thread",
    "threads.ThreadMember",
    "channel.TextChannel",
    "channel.VoiceChannel",
    "channel.StageChannel",
    "channel.CategoryChannel",
    "channel.ForumChannel",
    "channel.DMChannel",
    "channel.GroupChannel",
    "guild.Guild",
}
PARAMS = [
    pytest.param(case, variant, id=f"{case.id}-{variant.id}")
    for case in CASES
    if case.id in CACHED
    for variant in variants(case.payload_type)
]


def payload_without_recursion(variant: Variant) -> Any:
    payload = copy.deepcopy(variant.payload)
    if isinstance(payload, dict):
        payload.pop("referenced_message", None)
    return payload


def test_every_cached_model_is_covered() -> None:
    assert {case.id for case in CASES if case.id in CACHED} == CACHED


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_model_survives_the_serializer(
    case: ModelCase, variant: Variant, world: World
) -> None:
    obj = case.build(
        payload_without_recursion(variant), lambda c, n: provide(world, c, n)
    )
    serializer = ModelSerializer(world.state)

    dumped = serializer.dumps(obj)
    loaded = serializer.loads(dumped)

    assert type(loaded) is type(obj)
    assert serializer.dumps(loaded) == dumped
    assert getattr(loaded, "id", None) == getattr(obj, "id", None)
    assert getattr(loaded, "_state", world.state) is world.state
    if hasattr(type(obj), "__eq__") and type(obj).__eq__ is not object.__eq__:
        assert loaded == obj
