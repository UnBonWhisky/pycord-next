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

import importlib.util
import inspect
import sys
import typing
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
import typing_extensions as te

from discord.state.parsers import PARSERS
from tests.payloads.generator import generate
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    OTHER_USER_ID,
    THREAD_ID,
    USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    ready,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.state import ConnectionState

SKIPPED_EXECUTION: dict[str, str] = {}

ID_FIELDS = {
    "guild_id": GUILD_ID,
    "channel_id": CHANNEL_ID,
    "parent_id": CHANNEL_ID,
    "thread_id": THREAD_ID,
    "user_id": USER_ID,
    "owner_id": USER_ID,
    "application_id": OTHER_USER_ID,
}


def resolve_hints(parser: Callable[..., Any]) -> dict[str, Any]:
    module = sys.modules[parser.__module__]
    assert module.__file__ is not None
    spec = importlib.util.spec_from_file_location(
        f"{module.__name__}__typing", module.__file__
    )
    assert spec is not None
    assert spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    fresh.__package__ = module.__package__
    with mock.patch("typing.TYPE_CHECKING", True):
        spec.loader.exec_module(fresh)
    return typing.get_type_hints(getattr(fresh, parser.__name__))


def data_annotation(parser: Callable[..., Any]) -> Any:
    hints = resolve_hints(parser)
    name = list(inspect.signature(parser).parameters)[1]
    return hints[name]


def is_payload(annotation: Any) -> bool:
    if te.is_typeddict(annotation):
        return True
    members = typing.get_args(annotation)
    return bool(members) and all(is_payload(member) for member in members)


def fix_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: str(ID_FIELDS[key])
            if key in ID_FIELDS and isinstance(item, str)
            else fix_ids(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [fix_ids(item) for item in value]
    return value


EVENTS = sorted(PARSERS)


@pytest.mark.parametrize("event", EVENTS)
def test_parser_data_is_a_typeddict(event: str) -> None:
    annotation = data_annotation(PARSERS[event])

    assert is_payload(annotation), (event, annotation)


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.asyncio
async def test_generated_payload_runs_through_the_parser(
    event: str, state: ConnectionState
) -> None:
    if event in SKIPPED_EXECUTION:
        pytest.skip(SKIPPED_EXECUTION[event])

    recorder = Recorder()
    state.dispatch = recorder
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    await state.parsers["CHANNEL_CREATE"](channel_payload())

    annotation = data_annotation(PARSERS[event])
    for seed in range(3):
        data = fix_ids(generate(annotation, seed=seed))
        if event == "READY":
            data["guilds"] = [{"id": str(GUILD_ID), "unavailable": True}]
        await PARSERS[event](state, data)
        if event == "READY":
            assert state._ready_task is not None
            state._ready_task.cancel()
