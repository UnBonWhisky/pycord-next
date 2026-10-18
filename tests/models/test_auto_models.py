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
import inspect
import re
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from discord.utils import CachedSlotProperty
from tests.models.context import provide
from tests.models.discovery import ModelCase, discover
from tests.models.known_issues import KNOWN_ISSUES, PROPERTY_ISSUES, UNTESTED
from tests.payloads.generator import Variant, variants

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.models.context import World

CASES, SKIPPED = discover()
PROPERTY_KINDS = (property, functools.cached_property, CachedSlotProperty)
SKIPPED_PROPERTIES = {(i.cls, i.name) for i in PROPERTY_ISSUES}


def has_custom_eq(cls: type) -> bool:
    return cls.__eq__ is not object.__eq__


def has_custom_repr(cls: type) -> bool:
    return cls.__repr__ is not object.__repr__


def has_to_dict(cls: type) -> bool:
    return callable(getattr(cls, "to_dict", None))


def is_slotted(cls: type) -> bool:
    return all(
        "__slots__" in k.__dict__ and "__dict__" not in k.__dict__["__slots__"]
        for k in cls.__mro__
        if k is not object
    )


def public_properties(cls: type) -> list[str]:
    names = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        try:
            static = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        if isinstance(static, PROPERTY_KINDS):
            names.append(name)
    return names


APPLICABLE: dict[str, Callable[[type], bool]] = {
    "construct": lambda _: True,
    "repr": has_custom_repr,
    "eq_hash": has_custom_eq,
    "roundtrip": has_to_dict,
    "slots": is_slotted,
    "properties": lambda cls: bool(public_properties(cls)),
}

ALL_VARIANTS: dict[str, list[Variant]] = {
    case.id: list(variants(case.payload_type)) for case in CASES
}


def params(check: str) -> list[Any]:
    result = []
    for case in CASES:
        if not APPLICABLE[check](case.cls):
            continue
        for variant in ALL_VARIANTS[case.id]:
            matching = [
                issue
                for issue in KNOWN_ISSUES
                if issue.case == case.id
                and re.search(issue.variant, variant.id)
                and issue.check in ("*", check)
            ]
            if check != "construct" and any(i.check == "*" for i in matching):
                continue
            marks = [pytest.mark.xfail(reason=i.reason, strict=True) for i in matching]
            result.append(
                pytest.param(case, variant, id=f"{case.id}-{variant.id}", marks=marks)
            )
    return result


def build(case: ModelCase, payload: Any, world: World) -> Any:
    built = case.build(copy.deepcopy(payload), lambda c, name: provide(world, c, name))
    if inspect.isawaitable(built):
        return world.run(built)
    return built


@pytest.mark.parametrize(("case", "variant"), params("construct"))
def test_constructs(case: ModelCase, variant: Variant, world: World) -> None:
    obj = build(case, variant.payload, world)
    assert obj is not None
    if case.ctor == "__init__":
        assert isinstance(obj, case.cls)


@pytest.mark.parametrize(("case", "variant"), params("repr"))
def test_repr(case: ModelCase, variant: Variant, world: World) -> None:
    obj = build(case, variant.payload, world)
    text = repr(obj)
    assert isinstance(text, str)
    match = re.match(r"<?(\w+)", text)
    assert match is not None, text
    assert any(match[1] in k.__name__ for k in type(obj).__mro__), text


@pytest.mark.parametrize(("case", "variant"), params("eq_hash"))
def test_eq_hash(case: ModelCase, variant: Variant, world: World) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        first = build(case, variant.payload, world)
        second = build(case, variant.payload, world)
        assert first == second
        assert (first != second) is False
        if type(first).__hash__ is not None:
            assert hash(first) == hash(second)


@pytest.mark.parametrize(("case", "variant"), params("roundtrip"))
def test_to_dict_roundtrip(case: ModelCase, variant: Variant, world: World) -> None:
    exported = build(case, variant.payload, world).to_dict()
    again = build(case, exported, world).to_dict()
    assert again == exported


@pytest.mark.parametrize(("case", "variant"), params("slots"))
def test_slots_have_no_dict(case: ModelCase, variant: Variant, world: World) -> None:
    obj = build(case, variant.payload, world)
    if is_slotted(type(obj)):
        assert not hasattr(obj, "__dict__")


@pytest.mark.parametrize(("case", "variant"), params("properties"))
def test_public_properties_accessible(
    case: ModelCase, variant: Variant, world: World
) -> None:
    obj = build(case, variant.payload, world)
    failures = []
    for name in public_properties(type(obj)):
        owner = next(k for k in type(obj).__mro__ if name in k.__dict__)
        if (type(obj).__name__, name) in SKIPPED_PROPERTIES:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                value = getattr(obj, name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{owner.__name__}.{name}: {type(exc).__name__}: {exc}")
        else:
            if inspect.iscoroutine(value):
                value.close()
    assert not failures, "\n".join(failures)


def test_discovery_skips_are_documented() -> None:
    assert {skipped.target for skipped in SKIPPED} == set(UNTESTED)
