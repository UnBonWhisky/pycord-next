"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
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

from collections.abc import Callable, Coroutine
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast

from typing_extensions import TypeVar

from ..interactions import Interaction

__all__ = (
    "Item",
    "ModalItem",
    "ViewItem",
)

from ..utils import get_slots, warn_deprecated
from ._fields import Field
from .core import ItemInterface

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Self

    from ..components import Component
    from ..enums import ComponentType
    from ..types.components import Component as ComponentPayload
    from .modal import BaseModal
    from .view import BaseView

ItemT = TypeVar("ItemT", bound="Item", default="Item")
T_co = TypeVar("T_co", bound="ItemInterface", covariant=True, default="ItemInterface")
V_co = TypeVar("V_co", bound="BaseView", covariant=True, default="BaseView")
M_co = TypeVar("M_co", bound="BaseModal", covariant=True, default="BaseModal")
ItemCallbackType = Callable[[Any, ItemT, Interaction], Coroutine[Any, Any, Any]]


class Item(Generic[T_co]):
    """Represents the base UI item that all UI components inherit from.

    .. versionadded:: 2.0

    .. versionchanged:: 2.7
        Now used as base class for :class:`ViewItem` and :class:`ModalItem`.

    .. container:: operations

        .. describe:: len(x)

            Returns how much this item counts towards Discord's component limits.
            This is 1 for all items, plus 1 for each child item.
    """

    __item_repr_attributes__: tuple[str, ...] = ("id",)
    __component__: ClassVar[type[Component]]
    __component_type__: ClassVar[ComponentType]
    __fields__: ClassVar[dict[str, Field[Any, Any]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__fields__ = {
            field.attr: field
            for base in reversed(cls.__mro__)
            for field in vars(base).values()
            if isinstance(field, Field)
        }

    def __init__(self) -> None:
        self._underlying: Component | None = None
        self._provided_custom_id: bool = False
        self.parent: Item | ItemInterface | None = None

    def __len__(self) -> int:
        return 1

    def __bool__(self) -> bool:
        return True

    def to_component_dict(self) -> ComponentPayload:
        """Converts this item to the component payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The payload of the underlying component.
        """
        if not self.underlying:
            raise NotImplementedError
        return self.underlying.to_dict()

    def refresh_component(self, component: Any) -> None:
        """Replaces the underlying component of this item.

        Parameters
        ----------
        component
            The component received from Discord.
        """
        self.underlying = component

    def refresh_state(self, interaction: Any, /) -> None:
        """Updates the state of this item from an interaction.

        Parameters
        ----------
        interaction
            The interaction, or the component data it carries, that triggered
            the update.
        """

    async def _resolve_state(self) -> None:
        return None

    @classmethod
    def from_component(cls, component: Any) -> Self:
        """Creates an item from a component received from Discord.

        Parameters
        ----------
        component
            The component to convert.

        Returns
        -------
        :class:`Item`
            The item built from ``component``.
        """
        factory: Any = cls
        if not cls.__fields__:
            return factory()
        return factory(
            **{
                field.name: getattr(component, attr)
                for attr, field in cls.__fields__.items()
            },
            id=component.id,
        )

    @property
    def underlying(self) -> Component:
        """The component this item wraps."""
        # Concrete items always build their component in ``__init__``.
        return cast("Component", self._underlying)

    @underlying.setter
    def underlying(self, value: Component) -> None:
        self._underlying = value

    @property
    def type(self) -> ComponentType:
        """The underlying component's type."""
        if not self.underlying:
            raise NotImplementedError
        return self.underlying.type

    def _build_underlying(self, **values: Any) -> Component:
        fields = self.__fields__
        data = {
            attr: fields[attr].prepare(value, init=True) if attr in fields else value
            for attr, value in values.items()
        }
        data.setdefault("type", self.__component_type__)
        self._underlying = self.__component__._raw_construct(**data)
        return self._underlying

    def _generate_underlying(self) -> Component:
        cls = type(self.underlying)
        return cls._raw_construct(
            **{slot: getattr(self.underlying, slot, None) for slot in get_slots(cls)}
        )

    def is_dispatchable(self) -> bool:
        """Whether this item can receive interactions."""
        return False

    def is_storable(self) -> bool:
        """Whether this item must be stored to receive interactions."""
        return False

    def is_persistent(self) -> bool:
        """Whether this item can be used in a persistent view."""
        return not self.is_dispatchable() or self._provided_custom_id

    def copy_text(self) -> str:
        """The text of this item, as copied by Discord clients."""
        return ""

    def __repr__(self) -> str:
        attrs = " ".join(
            f"{key}={getattr(self, key)!r}" for key in self.__item_repr_attributes__
        )
        return f"<{self.__class__.__name__} {attrs}>"

    @property
    def id(self) -> int | None:
        """Gets this item's ID.

        This can be set by the user when constructing an Item. If not, Discord will automatically provide one when the item's parent is sent.

        Returns
        -------
        Optional[:class:`int`]
            The ID of this item, or ``None`` if the user didn't set one.
        """
        return self.underlying and self.underlying.id

    @id.setter
    def id(self, value: int | None) -> None:
        if not self.underlying:
            return
        self.underlying.id = value


class ViewItem(Item[ItemInterface], Generic[V_co]):
    """Represents an item used in Views.

    The following are the original items supported in :class:`discord.ui.View`:

    - :class:`discord.ui.Button`
    - :class:`discord.ui.Select`

    And the following are new items under the "Components V2" specification for use in :class:`discord.ui.DesignerView`:

    - :class:`discord.ui.Section`
    - :class:`discord.ui.TextDisplay`
    - :class:`discord.ui.Thumbnail`
    - :class:`discord.ui.MediaGallery`
    - :class:`discord.ui.File`
    - :class:`discord.ui.Separator`
    - :class:`discord.ui.Container`

    Additionally, :class:`discord.ui.ActionRow` should be used in :class:`discord.ui.DesignerView` to support :class:`discord.ui.Button` and :class:`discord.ui.Select`.

    .. versionadded:: 2.7
    """

    _row: int | None
    _rendered_row: int | None

    def __init__(self) -> None:
        super().__init__()
        self._view: V_co | None = None

    @property
    def row(self) -> int | None:
        """Always ``None`` for Components V2 items.

        .. deprecated:: 2.7.1
        """
        warn_deprecated("Accessing .row from CV2 Items", since="2.7.1", removed="3.0")
        return None

    @row.setter
    def row(self, value: int | None) -> None:
        warn_deprecated("Setting .row on CV2 Items", since="2.7.1", removed="3.0")

    @property
    def width(self) -> int:
        """The width of this item in a legacy row, in slots."""
        return 1

    @property
    def view(self) -> V_co | None:
        """Gets the parent view associated with this item.

        The view refers to the structure that holds this item. This is typically set
        automatically when the item is added to a view.

        Returns
        -------
        Optional[:class:`BaseView`]
            The parent view of this item, or ``None`` if the item is not attached to any view.
        """
        if self._view:
            return self._view
        if self.parent:
            from .view import BaseView

            if isinstance(self.parent, BaseView):
                return cast("V_co", self.parent)
            return cast("V_co | None", getattr(self.parent, "view", None))
        return None

    @view.setter
    def view(self, value: V_co | None) -> None:
        warn_deprecated("Manually setting .view", since="2.7", removed="3.0")
        self._view = value

    async def callback(self, interaction: Interaction) -> None:
        """|coro|

        The callback associated with this UI item.

        This can be overridden by subclasses.

        Parameters
        ----------
        interaction: :class:`.Interaction`
            The interaction that triggered this UI item.
        """


def _mark_callback(  # pyright: ignore[reportUnusedFunction]
    func: ItemCallbackType[Any], model: type[ViewItem], kwargs: dict[str, Any]
) -> None:
    """Marks a callback so that the views create an item for it."""
    marked = cast("Any", func)
    marked.__discord_ui_model_type__ = model
    marked.__discord_ui_model_kwargs__ = kwargs


def _callback_item(owner: object, func: ItemCallbackType[Any]) -> ViewItem:  # pyright: ignore[reportUnusedFunction]
    """Creates the item of a callback marked by :func:`_mark_callback`."""
    marked = cast("Any", func)
    item: ViewItem = marked.__discord_ui_model_type__(
        **marked.__discord_ui_model_kwargs__
    )
    cast("Any", item).callback = partial(func, owner, item)
    return item


def _set_disabled(item: Item, value: bool) -> None:  # pyright: ignore[reportUnusedFunction]
    """Sets the ``disabled`` attribute of an item that has one."""
    cast("Any", item).disabled = value


def _walk_nested(item: ItemT) -> Iterator[ItemT]:  # pyright: ignore[reportUnusedFunction]
    """Iterates over the items nested in ``item``, or over ``item`` if it has none."""
    walker = cast(
        "Callable[[], Iterator[ItemT]] | None", getattr(item, "walk_items", None)
    )
    if walker is not None:
        yield from walker()
    else:
        yield item


class ModalItem(Item[ItemInterface], Generic[M_co]):
    """Represents an item used in Modals.

    :class:`discord.ui.InputText` is the original item supported in :class:`discord.ui.Modal`.

    The following are newly available in :class:`discord.ui.DesignerModal`:

    - :class:`discord.ui.Label`
    - :class:`discord.ui.TextDisplay`

    And :class:`discord.ui.Label` should be used in :class:`discord.ui.DesignerModal` to add the following items:

    - :class:`discord.ui.InputText`
    - :class:`discord.ui.Select`
    - :class:`discord.ui.FileUpload`
    - :class:`discord.ui.RadioGroup`
    - :class:`discord.ui.CheckboxGroup`
    - :class:`discord.ui.Checkbox`

    .. versionadded:: 2.7
    """

    def __init__(self) -> None:
        super().__init__()
        self._modal: M_co | None = None
        self.parent = self.modal

    def refresh_from_modal(self, interaction: Interaction, data: Any) -> None:
        """Updates the state of this item from the modal submission.

        Parameters
        ----------
        interaction
            The interaction of the modal submission.
        data
            The payload of the submitted component.
        """

    @property
    def modal(self) -> M_co | None:
        """Gets the parent modal associated with this item. This is typically set automatically when the item is added to a modal.

        Returns
        -------
        Optional[:class:`BaseModal`]
            The parent modal of this item, or ``None`` if the item is not attached to any modal.
        """
        return self._modal

    @modal.setter
    def modal(self, value: M_co | None) -> None:
        self._modal = value
