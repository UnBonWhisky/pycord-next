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

import inspect
from functools import partial
from typing import TYPE_CHECKING, Any

import pytest

from discord.state import AutoShardedConnectionState, ConnectionState
from discord.state.parsers import PARSERS

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

    from discord.http import HTTPClient

LEGACY_EVENTS = frozenset(
    {
        "APPLICATION_COMMAND_PERMISSIONS_UPDATE",
        "AUTO_MODERATION_ACTION_EXECUTION",
        "AUTO_MODERATION_RULE_CREATE",
        "AUTO_MODERATION_RULE_DELETE",
        "AUTO_MODERATION_RULE_UPDATE",
        "CHANNEL_CREATE",
        "CHANNEL_DELETE",
        "CHANNEL_INFO",
        "CHANNEL_PINS_UPDATE",
        "CHANNEL_UPDATE",
        "ENTITLEMENT_CREATE",
        "ENTITLEMENT_DELETE",
        "ENTITLEMENT_UPDATE",
        "GUILD_AUDIT_LOG_ENTRY_CREATE",
        "GUILD_BAN_ADD",
        "GUILD_BAN_REMOVE",
        "GUILD_CREATE",
        "GUILD_DELETE",
        "GUILD_EMOJIS_UPDATE",
        "GUILD_INTEGRATIONS_UPDATE",
        "GUILD_MEMBER_ADD",
        "GUILD_MEMBER_REMOVE",
        "GUILD_MEMBERS_CHUNK",
        "GUILD_MEMBER_UPDATE",
        "GUILD_ROLE_CREATE",
        "GUILD_ROLE_DELETE",
        "GUILD_ROLE_UPDATE",
        "GUILD_SCHEDULED_EVENT_CREATE",
        "GUILD_SCHEDULED_EVENT_DELETE",
        "GUILD_SCHEDULED_EVENT_UPDATE",
        "GUILD_SCHEDULED_EVENT_USER_ADD",
        "GUILD_SCHEDULED_EVENT_USER_REMOVE",
        "GUILD_SOUNDBOARD_SOUND_CREATE",
        "GUILD_SOUNDBOARD_SOUND_DELETE",
        "GUILD_SOUNDBOARD_SOUNDS_UPDATE",
        "GUILD_SOUNDBOARD_SOUND_UPDATE",
        "GUILD_STICKERS_UPDATE",
        "GUILD_UPDATE",
        "INTEGRATION_CREATE",
        "INTEGRATION_DELETE",
        "INTEGRATION_UPDATE",
        "INTERACTION_CREATE",
        "INVITE_CREATE",
        "INVITE_DELETE",
        "MESSAGE_CREATE",
        "MESSAGE_DELETE",
        "MESSAGE_DELETE_BULK",
        "MESSAGE_POLL_VOTE_ADD",
        "MESSAGE_POLL_VOTE_REMOVE",
        "MESSAGE_REACTION_ADD",
        "MESSAGE_REACTION_REMOVE",
        "MESSAGE_REACTION_REMOVE_ALL",
        "MESSAGE_REACTION_REMOVE_EMOJI",
        "MESSAGE_UPDATE",
        "PRESENCE_UPDATE",
        "RATE_LIMITED",
        "READY",
        "RESUMED",
        "SOUNDBOARD_SOUNDS",
        "STAGE_INSTANCE_CREATE",
        "STAGE_INSTANCE_DELETE",
        "STAGE_INSTANCE_UPDATE",
        "SUBSCRIPTION_CREATE",
        "SUBSCRIPTION_DELETE",
        "SUBSCRIPTION_UPDATE",
        "THREAD_CREATE",
        "THREAD_DELETE",
        "THREAD_LIST_SYNC",
        "THREAD_MEMBERS_UPDATE",
        "THREAD_MEMBER_UPDATE",
        "THREAD_UPDATE",
        "TYPING_START",
        "USER_UPDATE",
        "VOICE_CHANNEL_EFFECT_SEND",
        "VOICE_CHANNEL_START_TIME_UPDATE",
        "VOICE_CHANNEL_STATUS_UPDATE",
        "VOICE_SERVER_UPDATE",
        "VOICE_STATE_UPDATE",
        "WEBHOOKS_UPDATE",
    }
)


def _auto_sharded(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> AutoShardedConnectionState:
    return AutoShardedConnectionState(
        dispatch=lambda *_args, **_kwargs: None,
        handlers={},
        hooks={},
        http=http,
        loop=loop,
    )


def test_registry_keeps_every_legacy_event() -> None:
    assert set(PARSERS) == LEGACY_EVENTS
    assert len(LEGACY_EVENTS) == 79


@pytest.mark.parametrize("event", sorted(LEGACY_EVENTS))
def test_registry_entries_are_named_after_their_event(event: str) -> None:
    parser = PARSERS[event]
    assert parser.__name__ == f"parse_{event.lower()}"
    assert parser.__module__.startswith("discord.state.parsers.")
    assert inspect.iscoroutinefunction(parser)
    names = list(inspect.signature(parser).parameters)
    assert names[0] == "state"
    assert len(names) == 2


def test_connection_state_exposes_every_event(state: ConnectionState) -> None:
    assert set(state.parsers) == LEGACY_EVENTS
    assert all(callable(parser) for parser in state.parsers.values())


@pytest.mark.parametrize("event", sorted(LEGACY_EVENTS))
def test_connection_state_binds_registry_parsers(
    state: ConnectionState, event: str
) -> None:
    parser = state.parsers[event]
    assert isinstance(parser, partial)
    assert parser.func is PARSERS[event]
    assert parser.args == (state,)


def test_auto_sharded_state_exposes_every_event(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> None:
    sharded = _auto_sharded(loop, http)
    assert set(sharded.parsers) == LEGACY_EVENTS


@pytest.mark.parametrize("event", ["READY", "RESUMED"])
def test_auto_sharded_overrides_take_precedence(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, event: str
) -> None:
    sharded = _auto_sharded(loop, http)
    parser = sharded.parsers[event]
    method = f"parse_{event.lower()}"
    assert parser.__self__ is sharded  # type: ignore[attr-defined]
    assert parser.__func__ is getattr(AutoShardedConnectionState, method)  # type: ignore[attr-defined]
    assert parser.__func__ is not PARSERS[event]  # type: ignore[attr-defined]


def test_auto_sharded_only_overrides_ready_and_resumed(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> None:
    sharded = _auto_sharded(loop, http)
    overridden = {
        event
        for event, parser in sharded.parsers.items()
        if not isinstance(parser, partial)
    }
    assert overridden == {"READY", "RESUMED"}


def test_connection_state_uses_registry_ready_and_resumed(
    state: ConnectionState,
) -> None:
    for event in ("READY", "RESUMED"):
        parser: Callable[[Any], Coroutine[Any, Any, None]] = state.parsers[event]
        assert isinstance(parser, partial)
        assert parser.func is PARSERS[event]


@pytest.mark.asyncio
async def test_state_subclass_can_override_any_parser(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> None:
    seen: list[dict[str, Any]] = []

    class CustomState(ConnectionState):
        async def parse_message_create(self, data: dict[str, Any]) -> None:
            seen.append(data)

    custom = CustomState(
        dispatch=lambda *_args, **_kwargs: None,
        handlers={},
        hooks={},
        http=http,
        loop=loop,
    )
    await custom.parsers["MESSAGE_CREATE"]({"id": 1})
    assert seen == [{"id": 1}]
    assert isinstance(custom.parsers["MESSAGE_DELETE"], partial)


def test_unknown_event_has_no_parser(state: ConnectionState) -> None:
    assert state.parsers.get("NOT_A_REAL_EVENT") is None
