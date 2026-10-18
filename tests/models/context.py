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

import copy
import functools
from functools import cached_property
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, TypeVar
from unittest.mock import Mock

import discord
from discord import types as t
from discord.channel import TextChannel
from discord.guild import Guild
from discord.message import Message, MessageReference
from discord.partial_emoji import PartialEmoji
from discord.role import Role
from discord.team import Team
from discord.threads import Thread
from discord.user import ClientUser, User
from tests.payloads.generator import generate
from tests.payloads.overrides import CHANNEL_ID

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from discord.state import ConnectionState
    from tests.models.discovery import ModelCase


T = TypeVar("T")


@functools.cache
def cached_payload(tp: Any) -> Any:
    return generate(tp)


class World:
    def __init__(self, state: ConnectionState) -> None:
        self.state = state
        self.client = Mock()
        state._get_client = lambda: self.client
        self.me = ClientUser(state=state, data=self.payload(t.user.User))
        state.user = self.me
        guild_payload = self.payload(t.guild.Guild)
        self.guild = Guild(data=guild_payload, state=state)
        self.run(state._populate_guild(self.guild, guild_payload))
        self.run(state._add_guild(self.guild))
        self.run(
            state._guild_bucket("roles", self.guild.id).set(
                self.guild.id,
                Role(
                    guild=self.guild,
                    state=state,
                    data=self.payload(t.role.Role, id=str(self.guild.id)),
                ),
            )
        )
        self.channel = TextChannel(
            state=state,
            guild=self.guild,
            data=self.payload(
                t.channel.TextChannel, id=CHANNEL_ID, guild_id=str(self.guild.id)
            ),
        )
        self.run(self.guild._add_channel(self.channel))

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self.state.loop.run_until_complete(coro)

    def payload(self, tp: Any, **fields: Any) -> Any:
        return {**copy.deepcopy(cached_payload(tp)), **fields}

    @cached_property
    def http(self) -> Any:
        return self.state.http

    @cached_property
    def user(self) -> User:
        return User(state=self.state, data=self.payload(t.user.User))

    @cached_property
    def message(self) -> Message:
        return Message(
            state=self.state,
            channel=self.channel,
            data=self.payload(t.message.Message),
        )

    @cached_property
    def thread(self) -> Thread:
        return Thread(
            guild=self.guild, state=self.state, data=self.payload(t.threads.Thread)
        )

    @cached_property
    def emoji(self) -> PartialEmoji:
        return PartialEmoji.from_dict(self.payload(t.emoji.PartialEmoji))

    @cached_property
    def team(self) -> Team:
        return Team(self.state, self.payload(t.team.Team))

    @cached_property
    def reference(self) -> MessageReference:
        return MessageReference(
            message_id=int(self.message.id), channel_id=int(self.channel.id)
        )

    @cached_property
    def member(self) -> discord.Member:
        return discord.Member(
            data=self.payload(t.member.MemberWithUser),
            guild=self.guild,
            state=self.state,
        )

    @cached_property
    def entry(self) -> Any:
        return discord.AuditLogEntry(
            users={}, data=self.payload(t.audit_log.AuditLogEntry), guild=self.guild
        )

    @cached_property
    def session(self) -> Mock:
        return Mock()


PROVIDERS: dict[str, Callable[[World], Any]] = {
    "state": lambda w: w.state,
    "http": lambda w: w.http,
    "guild": lambda w: w.guild,
    "channel": lambda w: w.channel,
    "me": lambda w: w.me,
    "user": lambda w: w.user,
    "message": lambda w: w.message,
    "new_message": lambda w: w.message,
    "parent": lambda w: w.thread,
    "emoji": lambda w: w.emoji,
    "team": lambda w: w.team,
    "reference": lambda w: w.reference,
    "member": lambda w: w.member,
    "entry": lambda w: w.entry,
    "users": lambda _: {},
    "creator": lambda _: None,
    "application_id": lambda _: 1234567890123456,
    "id": lambda _: 1234567890123456,
    "lobby_id": lambda _: 1234567890123456,
    "added": lambda _: True,
    "session": lambda w: w.session,
}

CLASS_PROVIDERS: dict[tuple[str, str], Callable[[World], Any]] = {
    ("Member", "message"): lambda w: SimpleNamespace(
        author=w.user, guild=w.guild, _state=w.state
    ),
    ("RawReactionActionEvent", "event_type"): lambda _: "REACTION_ADD",
    ("RawScheduledEventSubscription", "event_type"): lambda _: "USER_ADD",
}


def provide(world: World, case: ModelCase, name: str) -> Any:
    provider = CLASS_PROVIDERS.get((case.cls.__name__, name)) or PROVIDERS.get(name)
    if provider is None:
        raise LookupError(
            f"add a context provider for parameter {name!r} (required by {case.id})"
        )
    return provider(world)
