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

"""A faked HTTP layer for calling model methods and checking the routes they use."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import create_autospec

import pytest

from discord import types as t

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.models.context import World


class FakeHTTP:
    """Autospecs of the real routes, created on first use and cached."""

    def __init__(self, real: Any) -> None:
        self.__dict__["_real"] = real
        self.__dict__["_fakes"] = {}

    def __getattr__(self, name: str) -> Any:
        fakes = self.__dict__["_fakes"]
        if name not in fakes:
            attribute = getattr(self.__dict__["_real"], name)
            if not callable(attribute):
                return attribute
            fake = create_autospec(attribute)

            is_async = inspect.iscoroutinefunction(attribute)

            def answer(*_args: Any, _fake: Any = fake, **_kwargs: Any) -> Any:
                value = _fake.pages.pop(0) if _fake.pages else _fake.response
                if is_async:
                    return value

                async def respond() -> Any:
                    return value

                return respond()

            fake.response = None
            fake.pages = []
            fake.side_effect = answer
            fakes[name] = fake
        return fakes[name]


class Rig:
    """A populated world whose HTTP client is an autospecced fake.

    The fake rejects calls whose arguments do not match the real route signature.
    """

    def __init__(self, world: World) -> None:
        self.world = world
        self.state = world.state
        self.http: Any = FakeHTTP(world.state.http)
        self.state.http = self.http
        self.guild = world.guild
        self.channel = world.channel

    @property
    def client(self) -> Any:
        if "_client" not in self.__dict__:
            import discord

            client = discord.Client(loop=self.state.loop)
            client._connection = self.state
            client.http = self.http
            self.__dict__["_client"] = client
        return self.__dict__["_client"]

    def run(self, value: Any) -> Any:
        return self.world.run(value) if inspect.isawaitable(value) else value

    def payload(self, tp: Any, **fields: Any) -> Any:
        return self.world.payload(tp, **fields)

    def message_payload(self, message_id: int, **fields: Any) -> Any:
        defaults: dict[str, Any] = {
            "id": str(message_id),
            "type": 0,
            "mentions": [],
            "mention_roles": [],
            "reactions": [],
            "guild_id": str(self.guild.id),
            "channel_id": str(self.channel.id),
        }
        payload = self.payload(t.message.Message, **{**defaults, **fields})
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

    def make_message(self, message_id: int = 5000, **fields: Any) -> Any:
        from discord.message import Message

        payload = self.message_payload(message_id, flags=0, **fields)
        built = Message(state=self.state, channel=self.channel, data=payload)
        self.run(self.state._populate_message(built, payload))
        return built

    def pages(self, route: str, *pages: Any) -> None:
        getattr(self.http, route).pages = list(pages)

    def respond(self, route: str, response: Any) -> None:
        getattr(self.http, route).response = response


@dataclass
class Case:
    """One model method call: what is called, which route answers, what comes back."""

    id: str
    target: Callable[[Rig], Any]
    method: str
    route: str | None = None
    response: Callable[[Rig], Any] | None = None
    args: Callable[[Rig], tuple[Any, ...]] = lambda _r: ()
    kwargs: Callable[[Rig], dict[str, Any]] = lambda _r: {}
    called_with: Callable[[Rig], tuple[tuple[Any, ...], dict[str, Any]]] | None = None
    kwargs_include: Callable[[Rig], dict[str, Any]] | None = None
    check: Callable[[Rig, Any], None] | None = None
    raises: tuple[type[BaseException], str] | None = None
    also: dict[str, Any] | None = None
    setup: Callable[[Rig], None] | None = None
    warns: tuple[type[Warning], str] | None = None


def resolve(value: Any, rig: Rig) -> Any:
    return value(rig) if callable(value) else value


def execute(rig: Rig, case: Case) -> Any:
    if case.setup is not None:
        case.setup(rig)
    if case.route is not None and case.response is not None:
        rig.respond(case.route, resolve(case.response, rig))
    for other, response in (case.also or {}).items():
        rig.respond(other, resolve(response, rig))
    target = case.target(rig)
    call = getattr(target, case.method)
    if case.raises is not None:
        exception, match = case.raises
        with pytest.raises(exception, match=match):
            rig.run(call(*case.args(rig), **case.kwargs(rig)))
        if case.route is not None and case.response is None:
            getattr(rig.http, case.route).assert_not_called()
        return None
    if case.warns is not None:
        with pytest.warns(case.warns[0], match=case.warns[1]):
            result = rig.run(call(*case.args(rig), **case.kwargs(rig)))
    else:
        result = rig.run(call(*case.args(rig), **case.kwargs(rig)))
    if case.route is not None:
        route = getattr(rig.http, case.route)
        route.assert_called_once()
        if case.called_with is not None:
            args, kwargs = case.called_with(rig)
            route.assert_called_once_with(*args, **kwargs)
        if case.kwargs_include is not None:
            sent = route.call_args.kwargs
            for key, value in case.kwargs_include(rig).items():
                assert sent[key] == value
    if case.check is not None:
        case.check(rig, result)
    return result


PNG = b"\x89PNG\r\n\x1a\n"
MP3 = b"ID3\x03"


def lst(tp: Any, **over: Any) -> Callable[[Rig], Any]:
    return lambda r: [r.payload(tp, **over)]


def one(tp: Any, **over: Any) -> Callable[[Rig], Any]:
    return lambda r: r.payload(tp, **over)


def check_type(cls: type) -> Callable[[Rig, Any], None]:
    def check(_r: Rig, result: Any) -> None:
        assert isinstance(result, cls)

    return check


def check_list(cls: type, size: int = 1) -> Callable[[Rig, Any], None]:
    def check(_r: Rig, result: Any) -> None:
        assert len(result) == size
        assert all(isinstance(x, cls) for x in result)

    return check


def guild(r: Rig) -> Any:
    return r.guild


def channel(r: Rig) -> Any:
    return r.channel
