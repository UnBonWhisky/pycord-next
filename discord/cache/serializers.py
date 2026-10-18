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

"""Serialization of slotted model objects for remote cache backends."""

from __future__ import annotations

import array
import enum
import types
from datetime import datetime, timedelta
from importlib import import_module
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ..enums import try_enum
from ..utils import MISSING

if TYPE_CHECKING:
    from ..state import ConnectionState

C = TypeVar("C", bound="type[Any]")

__all__ = ("ModelSerializer", "register")

_REGISTRY: dict[str, type[Any]] = {}
_SLOTS: dict[type[Any], tuple[str, ...]] = {}
_SKIPPED = frozenset({"_state", "_http", "__dict__", "__weakref__"})
_UNSET: Any = object()
_PRIMITIVES = frozenset({type(None), bool, int, float, str, bytes})
_BUILTIN_BASES = (
    int,
    float,
    str,
    bytes,
    list,
    tuple,
    dict,
    set,
    frozenset,
    datetime,
    timedelta,
)

_LIST, _TUPLE, _SET, _FROZENSET, _DICT = 1, 2, 3, 4, 5
_DATETIME, _TIMEDELTA, _ENUM, _DISCORD_ENUM, _MISSING, _OBJECT = 6, 7, 8, 9, 10, 11
_ARRAY, _CLASS = 12, 13


def qualified_name(cls: type[Any]) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def register(cls: C) -> C:
    """Allow ``cls`` to be restored by :class:`ModelSerializer`.

    Classes living in the ``discord`` package are resolved on demand and do not
    need to be registered. Usable as a class decorator.
    """
    _REGISTRY[qualified_name(cls)] = cls
    return cls


def _resolve(name: str) -> type[Any]:
    cls = _REGISTRY.get(name)
    if cls is not None:
        return cls
    module, _, qualname = name.partition(":")
    if (module == "discord" or module.startswith("discord.")) and qualname:
        target: Any = import_module(module)
        for part in qualname.split("."):
            target = getattr(target, part, None)
        if isinstance(target, type):
            _REGISTRY[name] = target
            return target
    raise TypeError(f"cannot restore unknown or unregistered class {name!r}")


def _check_restorable(cls: type[Any], owner: tuple[type[Any], str] | None) -> None:
    name = qualified_name(cls)
    module = cls.__module__
    if "<locals>" not in cls.__qualname__ and (
        name in _REGISTRY or module == "discord" or module.startswith("discord.")
    ):
        return
    raise TypeError(
        f"cannot serialize {module}.{cls.__qualname__}: "
        f"class is not registered{_where(owner)}"
    )


def _slots(cls: type[Any]) -> tuple[str, ...]:
    cached = _SLOTS.get(cls)
    if cached is not None:
        return cached
    names: list[str] = []
    skipped = _SKIPPED | frozenset(getattr(cls, "__cache_skip__", ()))
    for base in reversed(cls.__mro__):
        declared = base.__dict__.get("__slots__", ())
        if isinstance(declared, str):
            declared = (declared,)
        for name in declared:
            if name in skipped or name.startswith("_cs_"):
                continue
            if name.startswith("__") and not name.endswith("__"):
                names.append(f"_{base.__name__.lstrip('_')}{name}")
            else:
                names.append(name)
    result = tuple(names)
    _SLOTS[cls] = result
    return result


def _where(owner: tuple[type[Any], str] | None) -> str:
    if owner is None:
        return ""
    return f" (slot {owner[0].__qualname__}.{owner[1]})"


class ModelSerializer:
    """aiocache serializer that stores slotted model objects as msgpack.

    Every slot is stored except ``_state`` and ``_http`` (rebound on load),
    ``_cs_*`` memoisation slots and the slots named in a class'
    ``__cache_skip__``. A class defining ``__cache_restore__`` has it called
    once its slots are restored, to rebuild the skipped back-references. Value objects, enums, datetimes and builtin containers
    are handled recursively; anything else raises :exc:`TypeError`.
    """

    encoding: None = None

    def __init__(self, state: ConnectionState | None, *, max_depth: int = 32) -> None:
        try:
            self._msgpack: Any = import_module("msgspec.msgpack")
        except ImportError as exc:
            raise ImportError(
                "msgspec is required to use a remote cache backend"
            ) from exc
        self._state = state
        self._max_depth = max_depth

    def dumps(self, value: Any) -> bytes:
        """Encode ``value`` to msgpack bytes, raising :exc:`TypeError` if unsupported."""
        return cast("bytes", self._msgpack.encode(self._enc(value, 0, None)))

    def loads(self, value: bytes | None) -> Any:
        """Decode bytes produced by :meth:`dumps`; ``None`` stays ``None``."""
        if value is None:
            return None
        return self._dec(self._msgpack.decode(value), 0)

    def _enc(self, obj: Any, depth: int, owner: tuple[type[Any], str] | None) -> Any:
        t: type[Any] = obj.__class__
        if t in _PRIMITIVES:
            return obj
        if depth >= self._max_depth:
            raise TypeError(
                f"cannot serialize {t.__qualname__}: nesting too deep or cyclic"
                f"{_where(owner)}"
            )
        depth += 1
        if obj is MISSING:
            return [_MISSING]
        if t is list:
            return [_LIST, [self._enc(v, depth, owner) for v in obj]]
        if t is tuple:
            return [_TUPLE, [self._enc(v, depth, owner) for v in obj]]
        if t is set or t is frozenset:
            tag = _SET if t is set else _FROZENSET
            return [tag, [self._enc(v, depth, owner) for v in obj]]
        if t is dict:
            return [
                _DICT,
                [
                    [self._enc(k, depth, owner), self._enc(v, depth, owner)]
                    for k, v in obj.items()
                ],
            ]
        enum_cls = getattr(t, "_actual_enum_cls_", None)
        if enum_cls is not None:
            _check_restorable(enum_cls, owner)
            return [
                _DISCORD_ENUM,
                qualified_name(enum_cls),
                self._enc(obj.value, depth, owner),
            ]
        if isinstance(obj, enum.Enum):
            _check_restorable(t, owner)
            return [_ENUM, qualified_name(t), self._enc(obj.value, depth, owner)]
        if isinstance(obj, type):
            _check_restorable(obj, owner)
            return [_CLASS, qualified_name(obj)]
        if isinstance(obj, array.array):
            if t is array.array:
                return [_ARRAY, "", obj.typecode, obj.tolist()]
            _check_restorable(t, owner)
            return [_ARRAY, qualified_name(t), obj.typecode, obj.tolist()]
        if isinstance(obj, datetime):
            return [_DATETIME, obj.isoformat()]
        if isinstance(obj, timedelta):
            return [_TIMEDELTA, obj.days, obj.seconds, obj.microseconds]
        if isinstance(obj, (*_BUILTIN_BASES, type)):
            raise TypeError(
                f"cannot serialize {t.__module__}.{t.__qualname__}{_where(owner)}"
            )
        return self._enc_object(obj, t, depth, owner)

    def _enc_object(
        self, obj: Any, cls: type[Any], depth: int, owner: tuple[type[Any], str] | None
    ) -> list[Any]:
        _check_restorable(cls, owner)
        extra = [k for k in getattr(obj, "__dict__", ()) if k not in _SKIPPED]
        if extra:
            raise TypeError(
                f"cannot serialize {cls.__module__}.{cls.__qualname__}: "
                f"instance attributes {extra!r} are not declared in __slots__"
            )
        fields: dict[str, Any] = {}
        for name in _slots(cls):
            value = getattr(obj, name, _UNSET)
            if value is _UNSET:
                continue
            fields[name] = self._enc(value, depth, (cls, name))
        return [_OBJECT, qualified_name(cls), fields]

    def _dec(self, node: Any, depth: int) -> Any:
        if type(node) is not list:
            return node
        if depth >= self._max_depth:
            raise TypeError("cannot restore value: nesting too deep")
        depth += 1
        data = cast("list[Any]", cast("object", node))
        tag: int = data[0]
        if tag == _OBJECT:
            return self._dec_object(data[1], data[2], depth)
        if tag == _LIST:
            return [self._dec(v, depth) for v in data[1]]
        if tag == _TUPLE:
            return tuple(self._dec(v, depth) for v in data[1])
        if tag == _SET:
            return {self._dec(v, depth) for v in data[1]}
        if tag == _FROZENSET:
            return frozenset(self._dec(v, depth) for v in data[1])
        if tag == _DICT:
            return {self._dec(k, depth): self._dec(v, depth) for k, v in data[1]}
        if tag == _DATETIME:
            return datetime.fromisoformat(data[1])
        if tag == _CLASS:
            return _resolve(data[1])
        if tag == _ARRAY:
            return self._dec_array(data[1], data[2], data[3])
        if tag == _TIMEDELTA:
            return timedelta(days=data[1], seconds=data[2], microseconds=data[3])
        if tag == _MISSING:
            return MISSING
        if tag == _DISCORD_ENUM:
            return try_enum(_resolve(data[1]), self._dec(data[2], depth))
        if tag == _ENUM:
            return _resolve(data[1])(self._dec(data[2], depth))
        raise TypeError(f"corrupt cache entry: unknown tag {tag!r}")

    def _dec_array(self, name: str, typecode: str, values: list[int]) -> Any:
        if not name:
            return array.array(typecode, values)
        cls = _resolve(name)
        if not issubclass(cls, array.array):
            raise TypeError(f"cannot restore {name}: not an array")
        return cast("Any", cls)(values, is_sorted=True)

    def _dec_object(self, name: str, fields: dict[str, Any], depth: int) -> Any:
        cls = _resolve(name)
        obj: Any = object.__new__(cls)
        unknown = fields.keys() - set(_slots(cls))
        if unknown:
            raise TypeError(f"cannot restore {name}: unknown slots {sorted(unknown)!r}")
        for slot, node in fields.items():
            object.__setattr__(obj, slot, self._dec(node, depth))
        if isinstance(getattr(cls, "_state", None), types.MemberDescriptorType):
            object.__setattr__(obj, "_state", self._state)
        if isinstance(getattr(cls, "_http", None), types.MemberDescriptorType):
            object.__setattr__(obj, "_http", getattr(self._state, "http", None))
        restore = getattr(obj, "__cache_restore__", None)
        if restore is not None:
            restore()
        return obj
