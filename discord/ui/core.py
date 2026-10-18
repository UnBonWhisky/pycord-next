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

import asyncio
import time
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, cast

from typing_extensions import TypeVar

__all__ = ("ItemInterface",)


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from typing_extensions import Self

    from ..types.components import Component as ComponentPayload
    from .item import Item


def _item_getter(iterable: Iterable[Item], /, **attrs: Any) -> Item | None:
    if not attrs:
        return None
    predicates = [
        (attrgetter(attr.replace("__", ".")), value) for attr, value in attrs.items()
    ]
    for item in iterable:
        try:
            if all(pred(item) == value for pred, value in predicates):
                return item
        except AttributeError:
            pass
        getter = cast(
            "Callable[..., Item | None] | None", getattr(item, "get_item", None)
        )
        if getter is not None and (child := getter(**attrs)):
            return child
    return None


def _validate_position(
    index: int | None, before: object | None, after: object | None
) -> None:
    if sum(x is not None for x in (index, before, after)) > 1:
        raise ValueError("Can only specify one of before, after, and index.")


def _resolve_item(owner: Any, ref: Any, where: str) -> Any:
    found = owner.get_item(ref) if isinstance(ref, (str, int)) else ref
    if found is None:
        raise ValueError(f"Could not find {ref!r} in {where}.")
    return found


def _insertion_index(  # pyright: ignore[reportUnusedFunction]
    owner: Any,
    items: list[Any],
    index: int | None,
    before: Any,
    after: Any,
    where: str,
) -> int | None:
    _validate_position(index, before, after)
    if index is not None:
        return index
    ref = before if before is not None else after
    if ref is None:
        return None
    found = _resolve_item(owner, ref, where)
    try:
        position = items.index(found)
    except ValueError:
        raise ValueError(f"Could not find {ref!r} in {where}.") from None
    return position if before is not None else position + 1


ItemT = TypeVar("ItemT", bound="Item", default=Any)


class ItemInterface(Generic[ItemT]):
    """The base structure for classes that contain :class:`~discord.ui.Item`.

    .. versionadded:: 2.7

    .. container:: operations

        .. describe:: len(x)

            Returns the total count of all items in this interface.
            This includes items that contain other items, which count towards Discord's component limits.

    Parameters
    ----------
    *items: :class:`Item`
        The initial items contained in this structure.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input. Defaults to 180.0.
        If ``None`` then there is no timeout.
    store: Optional[:class:`bool`]
        Whether this interface should be stored for callback listening. Setting it to ``False`` will ignore callbacks and prevent item values from being refreshed. Defaults to ``True``.

    Attributes
    ----------
    timeout: Optional[:class:`float`]
        Timeout from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    children: List[:class:`Item`]
        The list of children attached to this structure.
    """

    if TYPE_CHECKING:

        @property
        def children(self) -> list[ItemT]:
            """The list of children attached to this structure."""
            ...

        @children.setter
        def children(self, value: list[ItemT]) -> None: ...

    def __init__(
        self,
        *items: ItemT,
        timeout: float | None = 180.0,
        store: bool = True,
    ) -> None:
        self.timeout: float | None = timeout
        self.children = []
        for item in items:
            self.add_item(item)

        loop = asyncio.get_running_loop()
        self._cancel_callback: Callable[..., None] | None = None
        self._timeout_expiry: float | None = None
        self._timeout_task: asyncio.Task[None] | None = None
        self._stopped: asyncio.Future[bool] = loop.create_future()
        self._store = store

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} timeout={self.timeout} children={len(self.children)}>"

    async def _timeout_task_impl(self) -> None:
        while True:
            # Guard just in case someone changes the value of the timeout at runtime
            if self.timeout is None:
                return None

            if self._timeout_expiry is None:
                return self._dispatch_timeout()

            # Check if we've elapsed our currently set timeout
            now = time.monotonic()
            if now >= self._timeout_expiry:
                return self._dispatch_timeout()

            # Wait N seconds to see if timeout data has been refreshed
            await asyncio.sleep(self._timeout_expiry - now)

    @property
    def _expires_at(self) -> float | None:
        if self.timeout:
            return time.monotonic() + self.timeout
        return None

    def _dispatch_timeout(self) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        return sum(len(i) for i in self.children)

    def __bool__(self) -> bool:
        return True

    def to_components(self) -> list[ComponentPayload]:
        """Converts the children of this structure to component payloads."""
        return [item.to_component_dict() for item in self.children]

    def get_item(
        self, custom_id: str | int | None = None, **attrs: Any
    ) -> ItemT | None:
        r"""Gets an item from this structure. Roughly equal to `utils.get(self.children, **attrs)`.

        If an :class:`int` is provided, the item will be retrieved by ``id``, otherwise by  ``custom_id``.
        This method will also search nested items.
        If ``attrs`` are provided, they are all checked (logical AND) as done in :func:`~discord.utils.get`.
        To have a nested attribute search (i.e. search by ``x.y``) then pass in ``x__y`` as the keyword argument.

        Examples
        --------
        Basic usage:

        .. code-block:: python3

            container = my_view.get_item(1234)

        Attribute matching:

        .. code-block:: python3

            button = my_view.get_item(
                label="Click me!", style=discord.ButtonStyle.danger
            )

        Parameters
        ----------
        custom_id: Optional[Union[:class:`str`, :class:`int`]]
            The id of the item to get
        \*\*attrs
            Keyword arguments that denote attributes to search with.

        Returns
        -------
        Optional[:class:`Item`]
            The item with the matching ``custom_id``, ``id`` or ``attrs`` if it exists.
        """
        if custom_id:
            attr = "id" if isinstance(custom_id, int) else "custom_id"
            attrs[attr] = custom_id
        return cast("ItemT | None", _item_getter(self.children, **attrs))

    def add_item(self, item: ItemT) -> Self:
        """Adds an item to this structure.

        Parameters
        ----------
        item
            The item to add.

        Returns
        -------
        :class:`ItemInterface`
            This structure, to allow chaining.
        """
        raise NotImplementedError

    def remove_item(self, item: ItemT) -> Self:
        """Removes an item from this structure.

        Parameters
        ----------
        item
            The item to remove.

        Returns
        -------
        :class:`ItemInterface`
            This structure, to allow chaining.
        """
        raise NotImplementedError

    def clear_items(self) -> Self:
        """Removes every item from this structure."""
        raise NotImplementedError

    async def on_timeout(self) -> None:
        """|coro|

        A callback that is called when this structure's timeout elapses without being explicitly stopped.
        """
