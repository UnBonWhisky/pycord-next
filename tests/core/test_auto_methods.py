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

# The automatic harness for the public synchronous methods of every model.
#
# For every model class discovered by ``tests/models/discovery.py`` and every
# generated payload variant, the object is built from a populated state and:
#
# a. ``str(obj)`` is called when the class defines ``__str__``;
# b. every public synchronous method whose parameters are all optional is
#    called without arguments.
#
# Calls must either return or raise one of the documented library errors
# (``EXPECTED_ERRORS``): anything else, including ``TypeError`` or
# ``AttributeError``, is a bug in the model. Methods that cannot be called
# without arguments in a meaningful way are listed in ``SKIPPED``.

from __future__ import annotations

import contextlib
import copy
import inspect
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from discord import ClientException, DiscordException, SyncCacheAccessError
from tests.models.context import provide
from tests.models.discovery import ModelCase, discover
from tests.payloads.generator import Variant, variants

if TYPE_CHECKING:
    from tests.models.context import World

EXPECTED_ERRORS = (DiscordException, SyncCacheAccessError, ClientException, ValueError)

# (class name, method) -> reason.
SKIPPED: dict[tuple[str, str], str] = {
    **{
        (
            cls,
            "get_view",
        ): "creates a future on the running loop, the harness is synchronous"
        for cls in (
            "Message",
            "InteractionMessage",
            "WebhookMessage",
            "SyncWebhookMessage",
        )
    },
    ("PollAnswer", "voters"): "needs a poll attached to a message",
    ("Reaction", "users"): "the generated variants have no emoji name",
    **{
        (cls, name): "performs a request through a session the harness does not provide"
        for cls in ("SyncWebhook", "SyncWebhookMessage")
        for name in ("delete", "edit", "fetch", "send")
    },
}

CASES, _ = discover()


def public_methods(cls: type) -> list[str]:
    names = []
    for name in dir(cls):
        if name.startswith("_") or (cls.__name__, name) in SKIPPED:
            continue
        static = inspect.getattr_static(cls, name, None)
        if not inspect.isfunction(static) or inspect.iscoroutinefunction(static):
            continue
        if inspect.isasyncgenfunction(static):
            continue
        parameters = list(inspect.signature(static).parameters.values())[1:]
        required = [
            p
            for p in parameters
            if p.default is p.empty and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
        ]
        if not required:
            names.append(name)
    return names


def collect() -> list[Any]:
    params = []
    for case in CASES:
        if not public_methods(case.cls) and "__str__" not in case.cls.__dict__:
            continue
        params.extend(
            pytest.param(case, variant, id=f"{case.id}-{variant.id}")
            for variant in list(variants(case.payload_type))[:2]
        )
    return params


PARAMS = collect()


def build(case: ModelCase, variant: Variant, world: World) -> Any:
    built = case.build(
        copy.deepcopy(variant.payload), lambda c, name: provide(world, c, name)
    )
    return world.run(built) if inspect.isawaitable(built) else built


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_public_methods_without_arguments(
    case: ModelCase, variant: Variant, world: World
) -> None:
    obj = build(case, variant, world)
    failures = []
    if "__str__" in type(obj).__dict__:
        assert isinstance(str(obj), str)
    for name in public_methods(type(obj)):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = getattr(obj, name)()
        except EXPECTED_ERRORS:  # noqa: PERF203
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{type(obj).__name__}.{name}: {type(exc).__name__}: {exc}")
        else:
            if inspect.iscoroutine(result):
                result.close()
            elif inspect.isawaitable(result):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    world.run(_consume(result))
    assert not failures, "\n".join(failures)


async def _consume(awaitable: Any) -> None:
    with contextlib.suppress(Exception):
        await awaitable
