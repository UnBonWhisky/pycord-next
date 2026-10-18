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

import ast
import os
import sys
import types
from collections.abc import Callable
from typing import Any, Generic, cast, overload

from typing_extensions import Self, TypeVar

from ..limits import ComponentLimits

__all__ = (
    "Check",
    "Field",
    "count_limit",
    "custom_id_checks",
    "get_row",
    "in_range",
    "length_limit",
    "list_of",
    "new_custom_id",
    "set_row",
    "track_custom_id",
    "type_check",
)

T = TypeVar("T")
S = TypeVar("S", default=T)

Check = Callable[[str, Any], None]


def new_custom_id() -> str:
    return os.urandom(16).hex()


def track_custom_id(item: Any, value: str | None) -> None:
    item._provided_custom_id = value is not None


def type_check(*types: type, nullable: bool = False) -> Check:
    names = " or ".join(t.__name__ for t in types)

    def check(name: str, value: Any) -> None:
        if value is None and nullable:
            return
        if not isinstance(value, types):
            expected = f"None or {names}" if nullable else names
            raise TypeError(f"{name} must be {expected} not {value.__class__.__name__}")

    return check


def length_limit(limit: int) -> Check:
    def check(name: str, value: Any) -> None:
        if value is not None and len(str(value)) > limit:
            raise ValueError(f"{name} must be {limit} characters or fewer")

    return check


def in_range(lowest: int, highest: int, *, skip_falsy: bool = False) -> Check:
    def check(name: str, value: Any) -> None:
        if value is None or (skip_falsy and not value):
            return
        if not lowest <= value <= highest:
            raise ValueError(f"{name} must be between {lowest} and {highest}")

    return check


def count_limit(limit: int) -> Check:
    def check(name: str, value: Any) -> None:
        if len(value) > limit:
            raise ValueError(f"you may only provide up to {limit} {name}.")

    return check


def list_of(cls: type) -> Check:
    def check(name: str, value: object) -> None:
        if not isinstance(value, list):
            raise TypeError(f"{name} must be a list of {cls.__name__}")
        if not all(isinstance(obj, cls) for obj in cast("list[object]", value)):
            raise TypeError(f"all list items must subclass {cls.__name__}")

    return check


def get_row(item: Any) -> int | None:
    return item._row


def set_row(item: Any, value: int | None) -> None:
    if value is not None and not 0 <= value < ComponentLimits.LEGACY_VIEW_ROWS_MAX:
        raise ValueError(
            f"row cannot be negative or greater than or equal to {ComponentLimits.LEGACY_VIEW_ROWS_MAX}"
        )
    item._row = value


custom_id_checks: tuple[Check, ...] = (
    type_check(str),
    length_limit(ComponentLimits.CUSTOM_ID_MAX),
)


class Field(property, Generic[T, S]):
    """A property forwarding to a component's attribute, validated by its checks.

    The same checks run when the owning item is constructed and when the
    attribute is assigned, so they are declared only once.
    """

    def __init__(
        self,
        doc: str | None = None,
        *checks: Check,
        attr: str | None = None,
        default: Callable[[], Any] | None = None,
        coerce: Callable[[Any], Any] | None = None,
        on_set: Callable[[Any, Any], None] | None = None,
        read: Callable[[Any, Any], Any] | None = None,
        readonly: bool = False,
    ) -> None:
        super().__init__(None, None, None, doc)
        self.name: str = ""
        self.attr: str = attr or ""
        self.checks = checks
        self.default = default
        self.coerce = coerce
        self.on_set = on_set
        self.read = read
        self.readonly = readonly

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.attr = self.attr or name
        self._expose_type(owner, name)

    def _expose_type(self, owner: type, name: str) -> None:
        """Give the property a ``fget`` annotated with the type of the field.

        ``Field`` is a :class:`property` subclass whose ``__get__`` is overridden,
        so it has no getter of its own. Tools that introspect properties, like
        Sphinx, read the return type from the annotation of ``fget``: it is built from
        the ``Field[...]`` annotation of the attribute, which is also what type
        checkers use.
        """
        annotation = getattr(owner, "__annotations__", {}).get(name)
        if not isinstance(annotation, str):
            return
        try:
            subscript = ast.parse(annotation, mode="eval").body
            if not isinstance(subscript, ast.Subscript):
                return
            slice_ = subscript.slice
            value_type = slice_.elts[0] if isinstance(slice_, ast.Tuple) else slice_
            return_annotation = ast.unparse(value_type)
        except SyntaxError:
            return

        field: Field[Any, Any] = self

        def getter(instance: object) -> Any:
            return field.__get__(instance)

        module = sys.modules.get(owner.__module__)
        fget = types.FunctionType(
            getter.__code__,
            vars(module) if module is not None else {},
            name,
            None,
            getter.__closure__,
        )
        fget.__qualname__ = f"{owner.__qualname__}.{name}"
        fget.__module__ = owner.__module__
        fget.__doc__ = self.__doc__
        fget.__annotations__ = {"return": return_annotation}
        property.__init__(self, fget, None, None, self.__doc__)

    @overload
    def __get__(self, instance: None, owner: type | None = None) -> Self: ...

    @overload
    def __get__(self, instance: Any, owner: type | None = None) -> T: ...

    def __get__(self, instance: Any, owner: type | None = None) -> Self | T:
        if instance is None:
            return self
        value = getattr(instance.underlying, self.attr)
        return value if self.read is None else self.read(instance, value)

    def __set__(self, instance: Any, value: S) -> None:
        if self.readonly:
            raise AttributeError(
                f"property {self.name!r} of {type(instance).__name__!r} object has no setter"
            )
        setattr(instance.underlying, self.attr, self.prepare(value))
        if self.on_set is not None:
            self.on_set(instance, value)

    def prepare(self, value: Any, *, init: bool = False) -> Any:
        if init and value is None:
            return self.default() if self.default is not None else None
        for check in self.checks:
            check(self.name, value)
        if self.coerce is None or value is None:
            return value
        return self.coerce(value)
