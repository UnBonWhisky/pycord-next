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

# The one automatic harness for the async twins of the cache accessors.
#
# For every model class discovered by ``tests/models/discovery.py`` and every
# generated payload variant, the object is built from a populated state and:
#
# a. every public ``async def get_*`` / ``check_*`` (and ``is_*`` twins of
#    properties) whose required parameters are only ids is awaited on the memory
#    backend and on a fakeredis backend and must not raise;
# b. every sync property or method that has an async twin (``x`` / ``is_x`` ->
#    ``get_x`` / ``check_x``) gives an equal result of the same type as the
#    awaited twin on the memory backend, or raises the same exception;
# c. on the fakeredis backend the sync accessor raises ``SyncCacheAccessError``,
#    or returns a partial handle (relationship attributes), or returns what its
#    async twin returns on that backend (a value that comes from the payload and
#    needs no cache read); it never raises anything else.
#
# Relationship attributes (``message.channel``) give the cached object or a
# partial handle, their async twin (``get_channel()``) gives the cached object or
# ``None``: a handle on one side and ``None`` on the other is the same answer.
#
# New models and new twins are picked up without writing a test. Accessors that
# cannot be checked automatically are listed in ``SKIPPED`` with the reason.

from __future__ import annotations

import copy
import inspect
from functools import cached_property
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest

from discord import ClientException, SyncCacheAccessError
from discord.emoji import GuildEmoji
from discord.role import Role
from discord.utils import CachedSlotProperty
from tests.models.context import World, provide
from tests.models.discovery import ModelCase, discover
from tests.payloads.generator import Variant, variants
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient

PROPERTY_LIKE = (property, cached_property, CachedSlotProperty)
ASYNC_PREFIXES = ("get_", "check_")
EXCLUDED_PREFIXES = ("get_or_fetch",)
HANDLE_NAMES = ("Object", "PartialInviteGuild", "PartialInviteChannel")

# (class name, accessor) -> reason. Keep this list short and justified.
SKIPPED: dict[tuple[str, str], str] = {}

# async accessor -> sync name, when the names do not follow the convention.
RENAMED: dict[tuple[str, str], str] = {
    ("Member", "get_voice_state"): "voice",
}

SHARE_EVENT_LOOP = True


class Twin(NamedTuple):
    sync: str
    asynchronous: str


def required_arguments(static: Any) -> list[int] | None:
    """Ones for every required id parameter, ``None`` when the call needs more."""
    params = list(inspect.signature(static).parameters.values())[1:]
    arguments = []
    for param in params:
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if param.default is not param.empty:
            continue
        if param.annotation not in (int, "int"):
            return None
        arguments.append(1)
    return arguments


def async_accessors(cls: type) -> list[str]:
    names = []
    for name in dir(cls):
        if name.startswith("_") or name.startswith(EXCLUDED_PREFIXES):
            continue
        if not name.startswith((*ASYNC_PREFIXES, "is_")):
            continue
        static = inspect.getattr_static(cls, name, None)
        if not inspect.iscoroutinefunction(static):
            continue
        if (cls.__name__, name) in SKIPPED:
            continue
        if required_arguments(static) is not None:
            names.append(name)
    return names


def sync_name(cls: type, asynchronous: str) -> str | None:
    """The sync accessor an async ``get_x`` / ``check_x`` / ``is_x`` is the twin of."""
    renamed = RENAMED.get((cls.__name__, asynchronous))
    if renamed is not None:
        candidates = [renamed]
    elif asynchronous.startswith("get_"):
        candidates = [asynchronous.removeprefix("get_")]
    elif asynchronous.startswith("check_"):
        base = asynchronous.removeprefix("check_")
        candidates = [f"is_{base}", base]
    else:
        candidates = [asynchronous.removeprefix("is_")]
    for candidate in candidates:
        static = inspect.getattr_static(cls, candidate, None)
        if inspect.isfunction(static):
            if not inspect.iscoroutinefunction(static):
                return candidate
        elif isinstance(static, PROPERTY_LIKE) or inspect.ismemberdescriptor(static):
            return candidate
    return None


def twins(cls: type) -> list[Twin]:
    result = []
    for name in async_accessors(cls):
        sync = sync_name(cls, name)
        if sync is not None and (cls.__name__, sync) not in SKIPPED:
            result.append(Twin(sync, name))
    return result


def collect() -> list[Any]:
    cases, _ = discover()
    params = []
    for case in cases:
        if not async_accessors(case.cls):
            continue
        params.extend(
            pytest.param(case, variant, id=f"{case.id}-{variant.id}")
            for variant in variants(case.payload_type)
        )
    return params


PARAMS = collect()


def build(case: ModelCase, variant: Variant, world: World) -> Any:
    obj = case.build(
        copy.deepcopy(variant.payload), lambda c, name: provide(world, c, name)
    )
    return world.run(obj) if inspect.isawaitable(obj) else obj


def normalize(value: Any) -> Any:
    """Compare results by type and identity, not by object instance."""
    if isinstance(value, dict):
        return {normalize(k): normalize(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [normalize(v) for v in value]
    if value is None or isinstance(value, bool | int | float | str | bytes):
        return value
    identity = getattr(value, "id", None)
    if identity is None:
        identity = getattr(value, "value", None)
    if identity is None or inspect.isclass(identity):
        return type(value).__name__
    return type(value).__name__, identity


def read(obj: Any, name: str, arguments: list[int]) -> Any:
    static = inspect.getattr_static(type(obj), name)
    if inspect.isfunction(static):
        return getattr(obj, name)(*arguments)
    return getattr(obj, name)


def same_answer(sync: Any, asynchronous: Any) -> bool:
    """A handle (or nothing) on the sync side is ``None`` on the async side."""
    if normalize(sync) == normalize(asynchronous):
        return True
    return asynchronous is None and is_handle(sync)


def is_handle(value: Any) -> bool:
    if isinstance(value, list | tuple):
        return all(is_handle(v) for v in value)
    if value is None:
        return True
    name = type(value).__name__
    return name.startswith("Partial") or name in HANDLE_NAMES


def test_accessors_are_discovered() -> None:
    discovered = {param.values[0].cls.__name__ for param in PARAMS}
    assert {
        "Guild",
        "Member",
        "Role",
        "TextChannel",
        "Thread",
        "Message",
        "Reaction",
        "GuildEmoji",
        "ScheduledEvent",
        "AuditLogEntry",
        "Webhook",
        "Onboarding",
        "WelcomeScreen",
    } <= discovered
    assert len(PARAMS) > 380


EXPECTED_TWINS: dict[str, set[str]] = {
    "Member": {"get_roles", "get_top_role", "get_guild_permissions", "get_voice_state"},
    "Role": {"get_members", "check_assignable"},
    "Guild": {"get_channels", "get_members", "get_roles", "get_me", "is_chunked"},
    "TextChannel": {
        "get_category",
        "get_overwrites",
        "get_changed_roles",
        "get_threads",
    },
    "VoiceChannel": {"get_voice_states", "get_members"},
    "StageChannel": {"get_instance", "get_speakers", "get_moderators"},
    "CategoryChannel": {"get_channels", "get_text_channels"},
    "Thread": {"get_parent", "get_owner", "get_members", "check_nsfw"},
    "Message": {
        "get_channel",
        "get_guild",
        "get_channel_mentions",
        "get_clean_content",
        "get_poll",
    },
    "Reaction": {"get_message"},
    "GuildEmoji": {"get_roles", "check_usable"},
    "ScheduledEvent": {"get_creator", "get_channel"},
    "AuditLogEntry": {"get_user", "get_target", "get_extra", "get_changes"},
}


def test_twins_are_paired_by_name() -> None:
    discovered: dict[str, set[str]] = {}
    for param in PARAMS:
        cls = param.values[0].cls
        discovered.setdefault(cls.__name__, {t.asynchronous for t in twins(cls)})
    for name, expected in EXPECTED_TWINS.items():
        assert expected <= discovered[name], (name, expected - discovered[name])


def test_predicate_twins_use_check() -> None:
    assert Twin("is_usable", "check_usable") in twins(GuildEmoji)
    assert Twin("is_assignable", "check_assignable") in twins(Role)


@pytest.fixture
def redis_world(loop: asyncio.AbstractEventLoop, http: HTTPClient) -> World:
    return World(build_state(loop, http, "redis"))


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_async_accessors_do_not_raise(
    case: ModelCase, variant: Variant, world: World, redis_world: World
) -> None:
    failures = []
    for backend, where in (("memory", world), ("fakeredis", redis_world)):
        obj = build(case, variant, where)
        for name in async_accessors(type(obj)):
            if not hasattr(obj, name):
                continue
            arguments = required_arguments(inspect.getattr_static(type(obj), name))
            assert arguments is not None
            try:
                result = where.run(getattr(obj, name)(*arguments))
            except ClientException:
                continue
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{backend} {name}: {type(exc).__name__}: {exc}")
            else:
                assert not inspect.isawaitable(result)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_async_twins_match_the_sync_accessors(
    case: ModelCase, variant: Variant, world: World
) -> None:
    obj = build(case, variant, world)
    failures = []
    for sync, asynchronous in twins(type(obj)):
        if not hasattr(obj, asynchronous):
            continue
        arguments = required_arguments(inspect.getattr_static(type(obj), asynchronous))
        assert arguments is not None
        try:
            raw = read(obj, sync, arguments)
            expected = normalize(raw)
        except Exception as exc:  # noqa: BLE001
            try:
                world.run(getattr(obj, asynchronous)(*arguments))
            except type(exc):
                continue
            except Exception as other:  # noqa: BLE001
                failures.append(
                    f"{asynchronous}: {type(other).__name__}, but {sync} raised "
                    f"{type(exc).__name__}"
                )
                continue
            failures.append(f"{asynchronous} did not raise but {sync} raised {exc!r}")
            continue
        try:
            awaited = world.run(getattr(obj, asynchronous)(*arguments))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{asynchronous} raised {exc!r}, {sync} gave {expected!r}")
            continue
        if not same_answer(raw, awaited):
            failures.append(
                f"{asynchronous} gave {normalize(awaited)!r}, {sync} gave {expected!r}"
            )
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_sync_accessors_on_a_remote_backend(
    case: ModelCase, variant: Variant, redis_world: World
) -> None:
    assert not redis_world.state.cache.supports_sync
    obj = build(case, variant, redis_world)
    failures = []
    for sync, asynchronous in twins(type(obj)):
        if not hasattr(obj, asynchronous):
            continue
        arguments = required_arguments(inspect.getattr_static(type(obj), asynchronous))
        assert arguments is not None
        try:
            value = read(obj, sync, arguments)
        except SyncCacheAccessError as exc:
            if "use " not in str(exc):
                failures.append(f"{sync}: the error does not name the replacement")
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{sync} raised {type(exc).__name__}: {exc}")
            continue
        if is_handle(value):
            continue
        try:
            awaited = redis_world.run(getattr(obj, asynchronous)(*arguments))
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{sync} returned {value!r} instead of raising, and {asynchronous} "
                f"raised {exc!r}"
            )
            continue
        if normalize(value) != normalize(awaited):
            failures.append(
                f"{sync} returned {value!r} instead of raising or a handle, "
                f"{asynchronous} gave {awaited!r}"
            )
    assert not failures, "\n".join(failures)
