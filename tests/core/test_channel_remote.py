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

from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.errors import ClientException
from tests.core.rig import (
    Case,
    Rig,
    check_list,
    check_type,
    execute,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World

CHANNEL_TYPES = {
    "text": (discord.TextChannel, t.channel.TextChannel, 0),
    "voice": (discord.VoiceChannel, t.channel.VoiceChannel, 2),
    "stage": (discord.StageChannel, t.channel.StageChannel, 13),
    "category": (discord.CategoryChannel, t.channel.CategoryChannel, 4),
    "forum": (discord.ForumChannel, t.channel.ForumChannel, 15),
    "media": (discord.MediaChannel, t.channel.ForumChannel, 16),
}


def make_channel(
    rig: Rig, kind: str, channel_id: int | None = None, **fields: Any
) -> Any:
    cls, tp, number = CHANNEL_TYPES[kind]
    channel_id = channel_id or 9000 + len(rig.guild.channels) + 1
    defaults: dict[str, Any] = {
        "id": str(channel_id),
        "guild_id": str(rig.guild.id),
        "type": number,
        "parent_id": None,
        "permission_overwrites": [],
        "position": 0,
    }
    payload = rig.payload(tp, **{**defaults, **fields})
    channel = cls(state=rig.state, guild=rig.guild, data=payload)
    rig.run(rig.guild._add_channel(channel))
    return channel


def channel_of(kind: str) -> Any:
    def get(rig: Rig) -> Any:
        if not hasattr(rig, f"_{kind}"):
            setattr(rig, f"_{kind}", make_channel(rig, kind, 9100))
        return getattr(rig, f"_{kind}")

    return get


def channel_payload(kind: str, **fields: Any) -> Any:
    _, tp, number = CHANNEL_TYPES[kind]

    def build(rig: Rig) -> Any:
        return rig.payload(
            tp,
            **{
                "guild_id": str(rig.guild.id),
                "type": number,
                "parent_id": None,
                "permission_overwrites": [],
                **fields,
            },
        )

    return build


MESSAGEABLE = ["text", "voice", "stage"]


def delete_messages_cases(kind: str) -> list[Case]:
    target = channel_of(kind)
    return [
        Case(
            f"{kind}_delete_messages_none",
            target,
            "delete_messages",
            args=lambda r: ([],),
            check=lambda r, res: _nothing_deleted(r),
        ),
        Case(
            f"{kind}_delete_messages_single",
            target,
            "delete_messages",
            "delete_message",
            args=lambda r: ((x for x in [discord.Object(id=5)]),),
            kwargs=lambda r: {"reason": "r"},
            called_with=lambda r: ((target(r).id, 5), {"reason": "r"}),
        ),
        Case(
            f"{kind}_delete_messages_bulk",
            target,
            "delete_messages",
            "delete_messages",
            args=lambda r: ([discord.Object(id=5), discord.Object(id=6)],),
            kwargs=lambda r: {"reason": "r"},
            called_with=lambda r: ((target(r).id, [5, 6]), {"reason": "r"}),
        ),
        Case(
            f"{kind}_delete_messages_too_many",
            target,
            "delete_messages",
            "delete_messages",
            args=lambda r: ([discord.Object(id=i) for i in range(101)],),
            raises=(ClientException, "up to 100"),
        ),
        Case(
            f"{kind}_webhooks",
            target,
            "webhooks",
            "channel_webhooks",
            lambda r: [r.payload(t.webhook.Webhook)],
            called_with=lambda r: ((target(r).id,), {}),
            check=check_list(discord.Webhook),
        ),
        Case(
            f"{kind}_create_webhook",
            target,
            "create_webhook",
            "create_webhook",
            one(t.webhook.Webhook),
            kwargs=lambda r: {"name": 5, "avatar": b"\x89PNG\r\n\x1a\n", "reason": "r"},
            called_with=lambda r: (
                (target(r).id,),
                {
                    "name": "5",
                    "avatar": "data:image/png;base64,iVBORw0KGgo=",
                    "reason": "r",
                },
            ),
            check=check_type(discord.Webhook),
        ),
        Case(
            f"{kind}_create_webhook_without_avatar",
            target,
            "create_webhook",
            "create_webhook",
            one(t.webhook.Webhook),
            kwargs=lambda r: {"name": "hook"},
            kwargs_include=lambda r: {"avatar": None, "reason": None},
        ),
        Case(
            f"{kind}_trigger_typing",
            target,
            "trigger_typing",
            "send_typing",
            called_with=lambda r: ((target(r).id,), {}),
        ),
        Case(
            f"{kind}_clone",
            target,
            "clone",
            "create_channel",
            channel_payload(kind),
            kwargs=lambda r: {"name": "copy", "reason": "r"},
            kwargs_include=lambda r: {
                "name": "copy",
                "reason": "r",
                "parent_id": None,
                "permission_overwrites": [],
            },
            check=check_type(CHANNEL_TYPES[kind][0]),
        ),
    ]


def _nothing_deleted(r: Rig) -> None:
    r.http.delete_messages.assert_not_called()
    r.http.delete_message.assert_not_called()


def test_partial_message_handles(world: World) -> None:
    rig = Rig(world)
    for kind in MESSAGEABLE:
        channel = channel_of(kind)(rig)
        partial = channel.get_partial_message(5)
        assert partial.id == 5
        assert partial.channel is channel or partial.channel.id == channel.id
        assert channel.is_nsfw() in (True, False)


CASES = [
    *[case for kind in MESSAGEABLE for case in delete_messages_cases(kind)],
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_channel_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)
