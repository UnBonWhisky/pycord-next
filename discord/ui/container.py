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

from typing import TYPE_CHECKING, Any, cast

from typing_extensions import TypeVar, override

from .._internal.aliases import AliasMixin
from ..colour import Colour
from ..components import (
    Container as ContainerComponent,
    MediaGalleryItem,
)
from ..enums import ComponentType, SeparatorSpacingSize
from ._fields import Field
from .action_row import ActionRow
from .button import Button
from .core import _insertion_index, _item_getter, _resolve_item, _validate_position
from .file import File
from .item import ViewItem, _set_disabled, _walk_nested
from .media_gallery import MediaGallery
from .section import Section
from .select import Select
from .separator import Separator
from .text_display import TextDisplay

__all__ = ("Container",)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Self

    from ..components import Component
    from ..types.components import ContainerComponent as ContainerComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class Container(ViewItem[V_co], AliasMixin):
    """Represents a UI Container.

    The current items supported are as follows:

    - :class:`discord.ui.ActionRow`
    - :class:`discord.ui.Section`
    - :class:`discord.ui.TextDisplay`
    - :class:`discord.ui.MediaGallery`
    - :class:`discord.ui.File`
    - :class:`discord.ui.Separator`

    .. versionadded:: 2.7

    .. container:: operations

        .. describe:: len(x)

            Returns the total count of all items in this container.
            This includes the container itself, counting towards Discord's component limits.

    Parameters
    ----------
    *items: :class:`ViewItem`
        The initial items in this container.
    colour: Union[:class:`Colour`, :class:`int`]
        The accent colour of the container.
    spoiler: Optional[:class:`bool`]
        Whether this container has the spoiler overlay.
    id: Optional[:class:`int`]
        The container's ID.

    Attributes
    ----------
    items: List[:class:`ViewItem`]
        The list of items in this container.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "items",
        "colour",
        "spoiler",
        "id",
    )

    __component__ = ContainerComponent
    __component_type__ = ComponentType.container

    if TYPE_CHECKING:

        @property
        def underlying(self) -> ContainerComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    spoiler: Field[bool] = Field(
        "Whether the container has the spoiler overlay. Defaults to ``False``."
    )
    colour: Field[Colour | None, int | Colour | None] = Field(
        "The accent colour of the container.",
        attr="accent_color",
        coerce=Colour.resolve_value,
    )

    def __init_subclass__(cls) -> None:
        for base in reversed(cls.__mro__):
            for member in base.__dict__.values():
                if hasattr(member, "__discord_ui_model_type__"):
                    raise ValueError(
                        "The @button and @select decorators are incompatible with Container. Use ActionRow instead."
                    )
        super().__init_subclass__()

    def __init__(
        self,
        *items: ViewItem,
        colour: int | Colour | None = None,
        color: int | Colour | None = None,
        spoiler: bool | None = False,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self.items: list[ViewItem] = []

        self._build_underlying(
            id=id, components=[], accent_color=colour, spoiler=spoiler
        )
        for i in items:
            self.add_item(i)

    def __len__(self) -> int:
        return sum(len(i) for i in self.items) + 1

    def _add_component_from_item(self, item: ViewItem) -> None:
        self.underlying.components.append(item._generate_underlying())

    def _set_components(self, items: list[ViewItem]) -> None:
        self.underlying.components.clear()
        for item in items:
            self._add_component_from_item(item)

    def _generate_underlying(self) -> ContainerComponent:
        container = cast("ContainerComponent", super()._generate_underlying())
        container.components = [i._generate_underlying() for i in self.items]
        return container

    def add_item(
        self,
        item: ViewItem,
        *,
        index: int | None = None,
        before: ViewItem[V_co] | str | int | None = None,
        after: ViewItem[V_co] | str | int | None = None,
        into: ViewItem[V_co] | str | int | None = None,
    ) -> Self:
        """Adds an item to the container.

        .. warning::

            You may specify only **one** of ``index``, ``before`` and ``after``. ``into`` works together with those parameters.

        .. versionchanged:: 3.0
            Added the ``index``, ``before``, ``after`` and ``into`` parameters.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to add to the container.
        index: Optional[:class:`int`]
            Add the new item at the specific index of :attr:`items`. Same behavior as Python's :func:`~list.insert`.
        before: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **before** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.
            Nested items are searched too, the new item is added to the parent of the specified item.
        after: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **after** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.
            Nested items are searched too, the new item is added to the parent of the specified item.
        into: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **into** the specified item. This is equivalent to ``into.add_item(item)``.
            If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.

        Raises
        ------
        TypeError
            A :class:`ViewItem` was not passed.
        ValueError
            More than one of ``index``, ``before`` and ``after`` was given,
            or a searched item could not be found in the container.
        """
        _validate_position(index, before, after)

        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected ViewItem not {item.__class__!r}")

        if into is not None:
            target = _resolve_item(self, into, "the container")
            if target is not self:
                target.add_item(item, index=index, before=before, after=after)
                return self

        if before is not None or after is not None:
            ref = _resolve_item(
                self, before if before is not None else after, "the container"
            )
            if ref.parent is not self:
                owner = ref.parent
                if owner is None or not hasattr(owner, "add_item"):
                    raise ValueError(f"Could not find {ref!r} in the container.")
                if before is not None:
                    owner.add_item(item, before=ref)
                else:
                    owner.add_item(item, after=ref)
                return self

        if isinstance(item, (Button, Select)):
            raise TypeError(
                f"{type(cast('object', item))!r} cannot be added directly. Use ActionRow instead."
            )

        position = _insertion_index(
            self, self.items, index, before, after, "the container"
        )

        item.parent = self
        if position is None:
            self.items.append(item)
            self._add_component_from_item(item)
        else:
            self.items.insert(position, item)
            self._underlying = self._generate_underlying()
        return self

    def remove_item(self, item: ViewItem | str | int) -> Self:
        """Removes an item from the container. If an int or str is passed, it will remove by Item :attr:`id` or ``custom_id`` respectively.

        Parameters
        ----------
        item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, ``id``, or item ``custom_id`` to remove from the container.
        """
        if isinstance(item, (str, int)):
            found = self.get_item(item)
            if found is None:
                return self
            item = found
        try:
            if item.parent is self:
                self.items.remove(item)
                item.parent = None
            else:
                cast("Any", item.parent).remove_item(item)
        except (ValueError, AttributeError):
            pass
        return self

    def replace_item(
        self, original_item: ViewItem | str | int, new_item: ViewItem
    ) -> Self:
        """Directly replace an item in this container, including nested items.

        If an :class:`int` is provided, the item will be replaced by ``id``, otherwise by ``custom_id``.

        .. versionadded:: 3.0

        Parameters
        ----------
        original_item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to replace in the container.
        new_item: :class:`ViewItem`
            The new item to insert into the container.

        Raises
        ------
        TypeError
            The new item is not a :class:`ViewItem`, or is a :class:`Button` or :class:`Select`
            replacing a direct child of the container.
        ValueError
            The original item could not be found in the container.
        """
        if not isinstance(cast("object", new_item), ViewItem):
            raise TypeError(
                f"expected new_item to be ViewItem, not {new_item.__class__!r}"
            )

        original = _resolve_item(self, original_item, "the container")
        if original.parent is self:
            if isinstance(new_item, (Button, Select)):
                raise TypeError(
                    f"{type(cast('object', new_item))!r} cannot be added directly. Use ActionRow instead."
                )
            try:
                i = self.items.index(original)
            except ValueError:
                raise ValueError(
                    f"Could not find {original_item!r} in the container."
                ) from None
            new_item.parent = self
            self.items[i] = new_item
            original.parent = None
            self._underlying = self._generate_underlying()
        else:
            owner = original.parent
            if owner is None or not hasattr(owner, "replace_item"):
                raise ValueError(f"Could not find {original_item!r} in the container.")
            owner.replace_item(original, new_item)
        return self

    def get_item(self, id: str | int | None = None, **attrs: Any) -> ViewItem | None:
        r"""Get an item from this container. Roughly equivalent to `utils.get(container.items, ...)`.

        If an ``int`` is provided, the item will be retrieved by ``id``, otherwise by ``custom_id``.
        This method will also search for nested items.
        If ``attrs`` are provided, they are all checked (logical AND) as done in :func:`~discord.utils.get`.
        To have a nested attribute search (i.e. search by ``x.y``) then pass in ``x__y`` as the keyword argument.

        .. versionchanged:: 3.0
            Added support for ``attrs``.

        Parameters
        ----------
        id: Optional[Union[:class:`str`, :class:`int`]]
            The id or custom_id of the item to get.
        \*\*attrs
            Keyword arguments that denote attributes to search with.

        Returns
        -------
        Optional[:class:`ViewItem`]
            The item with the matching ``id``, ``custom_id`` or ``attrs`` if it exists.
        """
        if id:
            attr = "id" if isinstance(id, int) else "custom_id"
            attrs[attr] = id
        return cast("ViewItem | None", _item_getter(self.items, **attrs))

    def add_row(
        self,
        *items: ViewItem,
        id: int | None = None,
    ) -> Self:
        """Adds an :class:`ActionRow` to the container.

        To append a pre-existing :class:`ActionRow`, use :meth:`add_item` instead.

        Parameters
        ----------
        *items: Union[:class:`Button`, :class:`Select`]
            The items this action row contains.
        id: Optional[:class:`int`]
            The action row's ID.
        """
        row = ActionRow(*items, id=id)

        return self.add_item(row)

    def add_section(
        self,
        *items: ViewItem,
        accessory: ViewItem,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Section` to the container.

        To append a pre-existing :class:`Section`, use the
        :meth:`add_item` method, instead.

        Parameters
        ----------
        *items: :class:`ViewItem`
            The items contained in this section, up to 3.
            Currently only supports :class:`~discord.ui.TextDisplay`.
        accessory: Optional[:class:`ViewItem`]
            The section's accessory. This is displayed in the top right of the section.
            Currently only supports :class:`~discord.ui.Button` and :class:`~discord.ui.Thumbnail`.
        id: Optional[:class:`int`]
            The section's ID.
        """
        section = Section(*items, accessory=accessory, id=id)

        return self.add_item(section)

    def add_text(self, content: str, id: int | None = None) -> Self:
        """Adds a :class:`TextDisplay` to the container.

        Parameters
        ----------
        content: :class:`str`
            The content of the TextDisplay
        id: Optional[:class:`int`]
            The text displays' ID.
        """
        text = TextDisplay(content, id=id)

        return self.add_item(text)

    def add_gallery(
        self,
        *items: MediaGalleryItem,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`MediaGallery` to the container.

        To append a pre-existing :class:`MediaGallery`, use :meth:`add_item` instead.

        Parameters
        ----------
        *items: :class:`MediaGalleryItem`
            The media this gallery contains.
        id: Optional[:class:`int`]
            The gallery's ID.
        """
        g = MediaGallery(*items, id=id)

        return self.add_item(g)

    def add_file(self, url: str, spoiler: bool = False, id: int | None = None) -> Self:
        """Adds a :class:`File` to the container.

        Parameters
        ----------
        url: :class:`str`
            The URL of this file's media. This must be an ``attachment://`` URL that references a :class:`~discord.File`.
        spoiler: Optional[:class:`bool`]
            Whether the file has the spoiler overlay. Defaults to ``False``.
        id: Optional[:class:`int`]
            The file's ID.
        """
        f = File(url, spoiler=spoiler, id=id)

        return self.add_item(f)

    def add_separator(
        self,
        *,
        divider: bool = True,
        spacing: SeparatorSpacingSize = SeparatorSpacingSize.small,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Separator` to the container.

        Parameters
        ----------
        divider: :class:`bool`
            Whether the separator is a divider. Defaults to ``True``.
        spacing: :class:`~discord.SeparatorSpacingSize`
            The spacing size of the separator. Defaults to :attr:`~discord.SeparatorSpacingSize.small`.
        id: Optional[:class:`int`]
            The separator's ID.
        """
        s = Separator(divider=divider, spacing=spacing, id=id)

        return self.add_item(s)

    def copy_text(self) -> str:
        """Returns the text of all :class:`~discord.ui.TextDisplay` items in this container.

        Equivalent to the `Copy Text` option on Discord clients.
        """
        return "\n".join(t for i in self.items if (t := i.copy_text()))

    @override
    def is_dispatchable(self) -> bool:
        return any(item.is_dispatchable() for item in self.items)

    @override
    def is_persistent(self) -> bool:
        return all(item.is_persistent() for item in self.items)

    @override
    def refresh_component(self, component: ContainerComponent) -> None:
        self.underlying = component
        for i, y in enumerate(component.components):
            x = self.items[i]
            x.refresh_component(y)

    def disable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """
        Disables all buttons and select menus in the container.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.items` to not disable from the view.
        """
        for item in self.walk_items():
            if hasattr(item, "disabled") and (
                exclusions is None or item not in exclusions
            ):
                _set_disabled(item, True)
        return self

    def enable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """
        Enables all buttons and select menus in the container.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.items` to not enable from the view.
        """
        for item in self.walk_items():
            if hasattr(item, "disabled") and (
                exclusions is None or item not in exclusions
            ):
                _set_disabled(item, False)
        return self

    def walk_items(self) -> Iterator[ViewItem]:
        """Iterates over the items of this container, nested ones included."""
        for item in self.items:
            yield from _walk_nested(item)

    @override
    def to_component_dict(self) -> ContainerComponentPayload:
        self._underlying = self._generate_underlying()
        return cast("ContainerComponentPayload", super().to_component_dict())

    @classmethod
    @override
    def from_component(cls, component: ContainerComponent) -> Self:
        from .view import _component_to_item

        items = [_component_to_item(c) for c in component.components]
        return cls(
            *items,
            colour=component.accent_color,
            spoiler=component.spoiler,
            id=component.id,
        )

    callback = None  # pyright: ignore[reportAssignmentType]

    if TYPE_CHECKING:
        color = colour
