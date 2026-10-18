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

"""Spelling aliases (British/American) applied once for the whole library."""

from __future__ import annotations

import functools
import inspect
import re
import types
from collections.abc import Callable, Mapping
from typing import Any, Final, TypeVar, cast

from typing_extensions import deprecated

from ..utils import MISSING

__all__ = (
    "SPELLING_ALIASES",
    "AliasMixin",
    "accepts_aliases",
    "alias_of",
    "canonical_of",
    "export_module_aliases",
    "install_aliases",
)

F = TypeVar("F", bound=Callable[..., Any])

_deprecated: Any = deprecated

_DESCRIPTOR_WRAPPERS: Final = (classmethod, staticmethod)

SPELLING_ALIASES: Final[Mapping[str, str]] = {
    "colour": "color",
    "behaviour": "behavior",
    "grey": "gray",
}

_REVERSE_ALIASES: Final[Mapping[str, str]] = {
    alias: canonical for canonical, alias in SPELLING_ALIASES.items()
}


def _compile(table: Mapping[str, str]) -> re.Pattern[str]:
    return re.compile("|".join(map(re.escape, table)), re.IGNORECASE)


def _replacer(table: Mapping[str, str]) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        target = table[token.lower()]
        if token.isupper():
            return target.upper()
        if token[0].isupper():
            return target.capitalize()
        return target

    return replace


_ALIAS_PATTERN: Final = _compile(SPELLING_ALIASES)
_ALIAS_REPLACER: Final = _replacer(SPELLING_ALIASES)
_CANONICAL_PATTERN: Final = _compile(_REVERSE_ALIASES)
_CANONICAL_REPLACER: Final = _replacer(_REVERSE_ALIASES)


def _substitute(text: str) -> str:
    return _ALIAS_PATTERN.sub(_ALIAS_REPLACER, text)


@functools.cache
def alias_of(name: str) -> str | None:
    """Return the alternative spelling of ``name``, or ``None`` if it has none.

    Every token listed in :data:`SPELLING_ALIASES` is substituted, preserving
    its case: ``accent_colour`` becomes ``accent_color`` and ``ExpireBehaviour``
    becomes ``ExpireBehavior``.
    """
    result = _substitute(name)
    return None if result == name else result


@functools.cache
def canonical_of(name: str) -> str | None:
    """Return the canonical spelling of an alias, or ``None`` if ``name`` is not an alias."""
    result = _CANONICAL_PATTERN.sub(_CANONICAL_REPLACER, name)
    return None if result == name else result


def _is_unset(value: Any) -> bool:
    return value is None or value is MISSING


def _merge_aliases(
    qualname: str, kwargs: dict[str, Any], mapping: Mapping[str, str]
) -> None:
    for alias, canonical in mapping.items():
        if alias not in kwargs:
            continue
        value = kwargs.pop(alias)
        if canonical in kwargs:
            if _is_unset(value):
                continue
            if not _is_unset(kwargs[canonical]):
                raise TypeError(
                    f"{qualname}() got values for both {canonical!r} and its alias {alias!r}"
                )
        kwargs[canonical] = value


def _parameter_names(func: Callable[..., Any]) -> tuple[str, ...]:
    target: Any = func
    while hasattr(target, "__wrapped__"):
        target = target.__wrapped__
    code = getattr(target, "__code__", None)
    if code is None:
        return ()
    return cast(
        "tuple[str, ...]", code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]
    )


def accepts_aliases(func: F) -> F:
    """Make ``func`` accept the alternative spelling of its parameters as keyword arguments.

    The alias is renamed to the canonical parameter before the call. Passing
    both spellings raises :class:`TypeError`. The function is returned
    unchanged if none of its parameters has an alias.
    """
    if getattr(func, "__accepts_aliases__", False):
        return func

    mapping: dict[str, str] = {}
    for parameter in _parameter_names(func):
        alias = alias_of(parameter)
        if alias is not None:
            mapping[alias] = parameter
    if not mapping:
        return func

    alias_names = frozenset(mapping)
    qualname = func.__qualname__

    wrapper: Callable[..., Any]
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not alias_names.isdisjoint(kwargs):
                _merge_aliases(qualname, kwargs, mapping)
            return await func(*args, **kwargs)

        wrapper = async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not alias_names.isdisjoint(kwargs):
                _merge_aliases(qualname, kwargs, mapping)
            return func(*args, **kwargs)

        wrapper = sync_wrapper

    cast("Any", wrapper).__accepts_aliases__ = True
    return cast("F", wrapper)


def _wrap_callable(value: Any) -> Any:
    if isinstance(value, types.FunctionType):
        return accepts_aliases(value)
    if type(value) in _DESCRIPTOR_WRAPPERS:
        function = accepts_aliases(value.__func__)
        if function is not value.__func__:
            return type(value)(function)
    return value


def _delegate(canonical: str) -> property:
    def fget(self: Any) -> Any:
        return getattr(self, canonical)

    def fset(self: Any, value: Any) -> None:
        setattr(self, canonical, value)

    def fdel(self: Any) -> None:
        delattr(self, canonical)

    return property(fget, fset, fdel, f"Alias of :attr:`{canonical}`.")


def _redeprecate(function: Any) -> Any:
    message = getattr(function, "__deprecated__", None)
    if message is None:
        return None
    return _deprecated(_substitute(message))(getattr(function, "__wrapped__", function))


def _alias_for(value: Any, canonical: str) -> Any:
    if isinstance(value, types.MemberDescriptorType):
        return _delegate(canonical)
    if isinstance(value, property):
        fget = _redeprecate(value.fget)
        if fget is not None:
            return property(fget, value.fset, value.fdel, value.__doc__)
    elif type(value) in _DESCRIPTOR_WRAPPERS:
        function = _redeprecate(value.__func__)
        if function is not None:
            return type(value)(function)
    elif isinstance(value, types.FunctionType):
        function = _redeprecate(value)
        if function is not None:
            return function
    return value


def install_aliases(cls: type) -> None:
    """Bind the alternative spelling of every public name defined by ``cls``.

    Functions are wrapped with :func:`accepts_aliases`, properties, class
    methods and static methods are bound to their alias as is, and slots or
    plain instance attributes get a delegating property. A name that the class
    defines explicitly is never overwritten.
    """
    for name, value in tuple(vars(cls).items()):
        wrapped = _wrap_callable(value)
        if wrapped is not value:
            setattr(cls, name, wrapped)

    for name, value in tuple(vars(cls).items()):
        if name.startswith("_"):
            continue
        alias = alias_of(name)
        if alias is None or alias in vars(cls):
            continue
        setattr(cls, alias, _alias_for(value, name))

    annotations = inspect.get_annotations(cls)
    for name in annotations:
        if name.startswith("_") or name in vars(cls):
            continue
        alias = alias_of(name)
        if alias is None or alias in vars(cls) or alias in annotations:
            continue
        setattr(cls, alias, _delegate(name))


class AliasMixin:
    """Gives a class the alternative spelling of all its public names.

    Subclasses are processed when they are created, see :func:`install_aliases`.
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        install_aliases(cls)


def export_module_aliases(namespace: dict[str, Any]) -> None:
    """Add the alternative spelling of every name in ``__all__`` to a module namespace.

    Meant to be called as ``export_module_aliases(globals())`` at the end of a
    module. The aliases are also appended to ``__all__``.
    """
    exported: tuple[str, ...] = tuple(namespace["__all__"])
    missing: list[str] = []
    for name in exported:
        alias = alias_of(name)
        if alias is None:
            continue
        namespace.setdefault(alias, namespace[name])
        if alias not in exported and alias not in missing:
            missing.append(alias)
    if missing:
        namespace["__all__"] = (*exported, *missing)
